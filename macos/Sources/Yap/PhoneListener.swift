import Foundation
import Network
import YapCore

enum PhoneEvent: Sendable {
    case status(pin: String, deviceName: String?)
    case down
    case up
    case lost
}

/// Advertises `_yap._tcp` and accepts one paired iPhone. Audio is ingested on
/// the connection queue; press and release are ordered events for the pipeline.
final class PhoneListener: @unchecked Sendable {
    let microphone: RemoteMicrophone
    let events: AsyncStream<PhoneEvent>
    private let yield: AsyncStream<PhoneEvent>.Continuation
    private let queue = DispatchQueue(label: "yap.phone-link")
    private let lock = NSLock()
    private var pinValue: String
    private var listener: NWListener?
    private var connection: NWConnection?
    private var generation = 0
    private var decoder = PhoneLink.Decoder()
    private var paired = false
    private var deviceName: String?
    private var utterance = false
    private var started = false

    init(microphone: RemoteMicrophone) {
        self.microphone = microphone
        pinValue = Self.makePIN()
        let pair = AsyncStream<PhoneEvent>.makeStream(bufferingPolicy: .unbounded)
        events = pair.stream
        yield = pair.continuation
    }

    var currentPIN: String { lock.withLock { pinValue } }

    func start() {
        queue.async {
            guard !self.started else { return }
            self.started = true
            self.listen()
            let code = self.lock.withLock { self.pinValue }
            YapLog.info("iPhone pairing code \(code)")
            self.publish()
        }
    }

    func stop() {
        queue.async {
            self.listener?.cancel()
            self.listener = nil
            self.connection?.cancel()
            self.connection = nil
            self.yield.finish()
        }
    }

    /// Ask the paired phone to start forwarding the mic. No-op when nobody is paired.
    func beginCapture() {
        queue.async {
            guard self.paired, let connection = self.connection else { return }
            self.send(.capture, on: connection)
        }
    }

    /// Ask the phone to flush and send `stop`. The pipeline ends on that message.
    func endCapture() {
        queue.async {
            guard let connection = self.connection else { return }
            self.send(.release, on: connection)
        }
    }

    /// New code, and drop whoever was paired with the old one.
    func regeneratePIN() -> String {
        let pin = Self.makePIN()
        queue.async {
            self.lock.withLock { self.pinValue = pin }
            self.connection?.cancel()
            self.publish()
        }
        return pin
    }

    private func listen() {
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        tcp.enableKeepalive = true
        let parameters = NWParameters(tls: nil, tcp: tcp)
        parameters.includePeerToPeer = true
        do {
            let listener = try NWListener(using: parameters)
            listener.service = NWListener.Service(name: "Yap", type: PhoneLink.serviceType)
            listener.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    YapLog.info("iPhone link listening")
                case .failed(let error):
                    YapLog.error("iPhone link failed: \(error.localizedDescription)")
                default:
                    break
                }
            }
            listener.newConnectionHandler = { [weak self] connection in
                self?.accept(connection)
            }
            listener.start(queue: queue)
            self.listener = listener
        } catch {
            YapLog.error("iPhone link could not listen: \(error.localizedDescription)")
        }
    }

    private func accept(_ connection: NWConnection) {
        generation += 1
        let token = generation
        self.connection?.cancel()
        self.connection = connection
        paired = false
        deviceName = nil
        decoder = PhoneLink.Decoder()
        if utterance {
            utterance = false
            microphone.disarm()
            yield.yield(.lost)
        }
        connection.stateUpdateHandler = { [weak self] state in
            guard let self, token == self.generation else { return }
            if case .failed(let error) = state {
                self.drop(token: token, reason: error.localizedDescription)
            } else if case .cancelled = state {
                self.drop(token: token, reason: "cancelled")
            }
        }
        connection.start(queue: queue)
        receive(connection, token: token)
    }

    /// The connection queue is `queue`, so audio is ingested on the read callback
    /// with no extra hop.
    private func receive(_ connection: NWConnection, token: Int) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: PhoneLink.maxPayload + 5) { [weak self] data, _, isComplete, error in
            guard let self, token == self.generation else { return }
            if let data, !data.isEmpty {
                self.consume(data, on: connection, token: token)
            }
            if token != self.generation { return }
            if isComplete || error != nil {
                self.drop(token: token, reason: error?.localizedDescription ?? "closed")
                return
            }
            self.receive(connection, token: token)
        }
    }

    private func consume(_ data: Data, on connection: NWConnection, token: Int) {
        let messages: [PhoneLink.Message]
        do {
            messages = try decoder.append(data)
        } catch {
            YapLog.warning("iPhone link closed a bad frame")
            connection.cancel()
            return
        }
        for message in messages {
            guard token == generation else { return }
            switch message {
            case .hello(let pin, let name):
                let expected = lock.withLock { pinValue }
                guard pinEquals(pin, expected) else {
                    YapLog.info("iPhone link rejected a code")
                    send(.rejected, on: connection)
                    connection.cancel()
                    return
                }
                paired = true
                deviceName = name
                YapLog.info("iPhone paired name=\(name)")
                send(.ready, on: connection)
                publish()
            case .audio(let pcm):
                guard paired else { continue }
                if !utterance {
                    utterance = true
                    microphone.arm()
                    yield.yield(.down)
                }
                microphone.ingest(pcm)
            case .stop:
                utterance = false
                yield.yield(.up)
            case .ready, .rejected, .capture, .release:
                continue
            }
        }
    }

    private func drop(token: Int, reason: String) {
        guard token == generation else { return }
        generation += 1
        connection = nil
        paired = false
        deviceName = nil
        decoder = PhoneLink.Decoder()
        if utterance {
            utterance = false
            microphone.disarm()
            yield.yield(.lost)
        }
        YapLog.info("iPhone link dropped: \(reason)")
        publish()
    }

    private func send(_ message: PhoneLink.Message, on connection: NWConnection) {
        connection.send(
            content: PhoneLink.encode(message),
            completion: .contentProcessed { error in
                if let error {
                    YapLog.warning("iPhone link send failed: \(error.localizedDescription)")
                }
            }
        )
    }

    private func publish() {
        let pin = lock.withLock { pinValue }
        yield.yield(.status(pin: pin, deviceName: paired ? deviceName : nil))
    }

    private static func makePIN() -> String {
        String(format: "%06d", Int.random(in: 0...999_999))
    }

    private func pinEquals(_ offered: String, _ expected: String) -> Bool {
        guard offered.count == expected.count else { return false }
        var mismatch: UInt8 = 0
        for (left, right) in zip(offered.utf8, expected.utf8) {
            mismatch |= left ^ right
        }
        return mismatch == 0
    }
}

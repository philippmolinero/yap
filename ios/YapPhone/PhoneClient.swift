import Foundation
import Network

enum PhoneClientEvent: Sendable {
    case status(String)
    case paired(Bool)
    case capture
    case release
}

/// Finds the Mac over Bonjour and sends PCM as soon as each buffer is ready.
final class PhoneClient: @unchecked Sendable {
    private let queue = DispatchQueue(label: "yap.phone-client")
    private let lock = NSLock()
    private var handler: (@Sendable (PhoneClientEvent) -> Void)?
    private var browser: NWBrowser?
    private var connection: NWConnection?
    private var endpoint: NWEndpoint?
    private var decoder = PhoneLink.Decoder()
    private var pin = ""
    private var rejectedPIN: String?
    private var ready = false
    private var helloSent = false
    private var capturing = false

    func setHandler(_ handler: @escaping @Sendable (PhoneClientEvent) -> Void) {
        lock.withLock { self.handler = handler }
    }

    func start() {
        queue.async {
            guard self.browser == nil else { return }
            self.browse()
        }
    }

    func setPIN(_ pin: String) {
        queue.async {
            guard pin != self.pin else { return }
            self.pin = pin
            self.rejectedPIN = nil
            self.helloSent = false
            if self.ready {
                self.sendHelloIfReady()
            } else if self.connection == nil, let endpoint = self.endpoint {
                self.connect(to: endpoint)
            }
        }
    }

    func sendAudio(_ pcm: Data) {
        queue.async { [weak self] in
            guard let self, self.capturing else { return }
            self.transmit(.audio(pcm))
        }
    }

    /// On-screen button. The Mac hotkey uses the `capture` message instead.
    func beginForwarding() {
        queue.async { [weak self] in
            self?.capturing = true
        }
    }

    func endForwarding() {
        queue.async { [weak self] in
            guard let self else { return }
            self.capturing = false
            self.transmit(.stop)
        }
    }

    private func browse() {
        let browser = NWBrowser(for: .bonjour(type: PhoneLink.serviceType, domain: nil), using: parameters())
        browser.stateUpdateHandler = { [weak self] state in
            if case .failed(let error) = state {
                self?.emit(.status(error.localizedDescription))
            }
        }
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let self else { return }
            let endpoint = results.first?.endpoint
            if self.connection == nil, let endpoint {
                self.endpoint = endpoint
                self.connect(to: endpoint)
            } else if results.isEmpty {
                self.endpoint = nil
                self.emit(.status("Searching for Yap…"))
            }
        }
        browser.start(queue: queue)
        self.browser = browser
        emit(.status("Searching for Yap…"))
    }

    private func connect(to endpoint: NWEndpoint) {
        connection?.cancel()
        decoder = PhoneLink.Decoder()
        ready = false
        helloSent = false
        let connection = NWConnection(to: endpoint, using: parameters())
        self.connection = connection
        self.endpoint = endpoint
        connection.stateUpdateHandler = { [weak self] state in
            guard let self else { return }
            switch state {
            case .ready:
                self.ready = true
                self.emit(.status(self.pin.count == 6 ? "Checking code…" : "Enter the code from the Yap menu"))
                self.sendHelloIfReady()
                self.read(connection)
            case .failed(let error):
                self.ready = false
                self.connection = nil
                self.emit(.paired(false))
                self.emit(.status(error.localizedDescription))
            case .waiting(let error):
                self.emit(.status(error.localizedDescription))
            case .cancelled:
                self.ready = false
                if self.connection === connection {
                    self.connection = nil
                }
            default:
                break
            }
        }
        connection.start(queue: queue)
    }

    private func sendHelloIfReady() {
        guard ready, !helloSent, pin.count == 6, pin != rejectedPIN, connection != nil else { return }
        helloSent = true
        transmit(.hello(pin: pin, deviceName: ProcessInfo.processInfo.hostName))
    }

    private func read(_ connection: NWConnection) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 1024) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let data, !data.isEmpty {
                self.consume(data, on: connection)
            }
            if self.connection === connection, error == nil, !isComplete {
                self.read(connection)
            }
        }
    }

    private func consume(_ data: Data, on connection: NWConnection) {
        let messages: [PhoneLink.Message]
        do {
            messages = try decoder.append(data)
        } catch {
            connection.cancel()
            emit(.status("Could not talk to Yap"))
            return
        }
        for message in messages {
            switch message {
            case .ready:
                emit(.paired(true))
                emit(.status("Ready. Use the Mac key."))
            case .rejected:
                rejectedPIN = pin
                helloSent = false
                emit(.paired(false))
                emit(.status("Wrong code"))
                connection.cancel()
                return
            case .capture:
                capturing = true
                emit(.capture)
            case .release:
                capturing = false
                transmit(.stop)
                emit(.release)
            case .hello, .audio, .stop:
                break
            }
        }
    }

    private func transmit(_ message: PhoneLink.Message) {
        connection?.send(content: PhoneLink.encode(message), completion: .idempotent)
    }

    private func emit(_ event: PhoneClientEvent) {
        let handler = lock.withLock { self.handler }
        handler?(event)
    }

    private func parameters() -> NWParameters {
        let tcp = NWProtocolTCP.Options()
        tcp.noDelay = true
        tcp.enableKeepalive = true
        let parameters = NWParameters(tls: nil, tcp: tcp)
        parameters.includePeerToPeer = true
        return parameters
    }
}

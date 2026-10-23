import Foundation
import YapCore

/// One recorder for the pipeline, with the Mac mic and the iPhone mic behind it.
/// The trigger claims a source before `pipeline.start`. The claim that lands
/// first is the one `start` opens, so a hotkey and a phone press cannot swap
/// devices across the await inside the pipeline.
final class CaptureRouter: AudioRecording, @unchecked Sendable {
    enum Source: Equatable {
        case local
        case phone
    }

    private let lock = NSLock()
    private var local: Microphone
    private let phone: RemoteMicrophone
    private var owner: Source?
    private var ownerTicket = 0
    private var ticket = 0
    private var active: Source = .local

    init(local: Microphone, phone: RemoteMicrophone) {
        self.local = local
        self.phone = phone
    }

    var audioLevel: Double {
        let source = lock.withLock { active }
        return source == .phone ? phone.audioLevel : local.audioLevel
    }

    var isRecording: Bool {
        let source = lock.withLock { active }
        return source == .phone ? phone.isRecording : local.isRecording
    }

    /// Returns a ticket. Only the first claim while one is outstanding wins.
    func claim(_ source: Source) -> Int {
        lock.withLock {
            ticket += 1
            if owner == nil {
                owner = source
                ownerTicket = ticket
            }
            return ticket
        }
    }

    func cancelClaim(_ ticket: Int) {
        lock.withLock {
            guard ownerTicket == ticket else { return }
            owner = nil
            ownerTicket = 0
        }
    }

    func replaceLocal(_ microphone: Microphone) {
        lock.withLock {
            local.forceStop()
            local = microphone
        }
    }

    func warm() {
        local.warm()
    }

    func start(
        onFrame: @escaping @Sendable (Data) -> Void,
        onFirstFrame: @escaping @Sendable () -> Void,
        onSilence: @escaping @Sendable () -> Void
    ) throws {
        let source = lock.withLock { () -> Source in
            let source = owner ?? .local
            owner = nil
            ownerTicket = 0
            active = source
            return source
        }
        if source == .phone {
            try phone.start(onFrame: onFrame, onFirstFrame: onFirstFrame, onSilence: onSilence)
        } else {
            try local.start(onFrame: onFrame, onFirstFrame: onFirstFrame, onSilence: onSilence)
        }
    }

    func stop(abort: Bool) throws -> Data {
        let source = lock.withLock { active }
        if source == .phone {
            return try phone.stop(abort: abort)
        }
        return try local.stop(abort: abort)
    }

    func forceStop() {
        let source = lock.withLock { active }
        if source == .phone {
            phone.forceStop()
        } else {
            local.forceStop()
        }
    }
}

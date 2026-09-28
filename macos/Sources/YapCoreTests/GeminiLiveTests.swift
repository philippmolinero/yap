import Foundation
import YapCore

/// Socket double whose `send` suspends, so a client that overlaps writes will
/// reorder or drop them. The live session has to keep setup, audio, and
/// activity end in that order anyway.
final class ScriptedLiveSocket: LiveSocket, @unchecked Sendable {
    private let lock = NSLock()
    private var sentTexts: [String] = []
    private var inbound: [String] = []
    private var waiters: [CheckedContinuation<String, Error>] = []
    private var cancelled = false

    var onSend: (@Sendable (String) -> Void)?

    var sent: [String] {
        lock.withLock { sentTexts }
    }

    func connect() {}

    func send(text: String) async throws {
        await Task.yield()
        let dropped = lock.withLock { () -> Bool in
            if cancelled { return true }
            sentTexts.append(text)
            return false
        }
        if dropped { throw CancellationError() }
        onSend?(text)
    }

    func receiveText() async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            let ready: String? = lock.withLock {
                if cancelled {
                    continuation.resume(throwing: CancellationError())
                    return nil
                }
                if inbound.isEmpty {
                    waiters.append(continuation)
                    return nil
                }
                return inbound.removeFirst()
            }
            if let ready {
                continuation.resume(returning: ready)
            }
        }
    }

    func push(_ text: String) {
        let waiter: CheckedContinuation<String, Error>? = lock.withLock {
            if cancelled { return nil }
            if waiters.isEmpty {
                inbound.append(text)
                return nil
            }
            return waiters.removeFirst()
        }
        waiter?.resume(returning: text)
    }

    func cancel() {
        let pending: [CheckedContinuation<String, Error>] = lock.withLock {
            cancelled = true
            let pending = waiters
            waiters = []
            return pending
        }
        for waiter in pending {
            waiter.resume(throwing: CancellationError())
        }
    }
}

private func messageKind(_ text: String) -> String {
    if text.contains("\"setup\"") { return "setup" }
    if text.contains("activityStart") { return "activityStart" }
    if text.contains("activityEnd") { return "activityEnd" }
    if text.contains("\"audio\"") { return "audio" }
    return "other"
}

func geminiLiveSuite() -> Suite {
    let suite = Suite("Gemini live session")

    suite.test("audio stays ahead of activity end and the transcript returns") {
        let socket = ScriptedLiveSocket()
        let session = GeminiLiveSession(
            configuration: GeminiConfiguration(apiKey: "secret", languageCodes: ["en"]),
            socket: socket,
            setupTimeout: 2,
            finalTimeout: 2,
            grace: 0.2
        )
        socket.onSend = { text in
            if text.contains("\"setup\"") {
                socket.push(#"{"setupComplete":{}}"#)
            }
            if text.contains("activityEnd") {
                socket.push(
                    #"{"serverContent":{"inputTranscription":{"text":"Hello there","languageCode":"en"}}}"#
                )
                socket.push(#"{"serverContent":{"turnComplete":true}}"#)
            }
        }

        let started = Date()
        await session.start()
        await session.write(Data([1, 2, 0, 0]))
        await session.write(Data([3, 4, 0, 0]))
        let result = try await session.finish()

        try expect(result.text == "Hello there")
        try expect(result.language == "en")
        try expect(Date().timeIntervalSince(started) < 2, "a finished live turn must not sit on the spinner")
        try expect(socket.sent.map(messageKind) == ["setup", "activityStart", "audio", "audio", "activityEnd"])
        try expect(socket.sent.allSatisfy { !$0.contains("secret") })
    }

    suite.test("a silent socket fails the turn instead of spinning") {
        let socket = ScriptedLiveSocket()
        let session = GeminiLiveSession(
            configuration: GeminiConfiguration(apiKey: "secret"),
            socket: socket,
            setupTimeout: 2,
            finalTimeout: 0.4,
            grace: 0.2
        )
        socket.onSend = { text in
            if text.contains("\"setup\"") {
                socket.push(#"{"setupComplete":{}}"#)
            }
        }

        await session.start()
        await session.write(Data([1, 2, 0, 0]))
        let started = Date()
        do {
            _ = try await session.finish()
            throw TestFailure(description: "expected the live turn to time out")
        } catch let error as TranscriptionError {
            try expect(error == .timedOut)
        }
        let elapsed = Date().timeIntervalSince(started)
        try expect(elapsed < 1.5, "silent live turn held the spinner for \(elapsed)s")
        try expect(socket.sent.map(messageKind).contains("activityEnd"))
    }

    return suite
}

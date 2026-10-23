import Foundation

public struct GeminiConfiguration: Sendable, Equatable {
    public var apiKey: String
    /// Batch model used for the unary fallback call.
    public var unaryModel: String
    /// Streaming model used while the trigger key is held.
    public var liveModel: String
    public var mode: TranscriptionMode
    public var languageCodes: [String]
    public var vocabulary: [String]

    public static let vocabularyLimit = 100

    public init(
        apiKey: String,
        model: String = "gemini-3.5-transcribe",
        mode: TranscriptionMode = .smart,
        languageCodes: [String] = ["auto"],
        vocabulary: [String] = []
    ) {
        let base = model.hasSuffix("-live") ? String(model.dropLast("-live".count)) : model
        self.apiKey = apiKey
        self.unaryModel = base.isEmpty ? "gemini-3.5-transcribe" : base
        self.liveModel = self.unaryModel + "-live"
        self.mode = mode
        self.languageCodes = languageCodes.isEmpty ? ["auto"] : languageCodes
        self.vocabulary = Array(
            vocabulary
                .map { $0.trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
                .prefix(Self.vocabularyLimit)
        )
    }
}

/// Pure message shaping for both Gemini endpoints. Kept free of I/O so every
/// payload can be checked in tests.
public enum GeminiMessage {
    public static let liveURL = URL(
        string: "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
    )!
    public static let unaryURL = URL(string: "https://generativelanguage.googleapis.com/v1beta/interactions")!

    public static func setup(_ config: GeminiConfiguration) -> Data {
        let transcription: [String: Any] = [
            "languageCodes": config.languageCodes,
            "mode": config.mode == .smart ? "SMART" : "VERBATIM",
        ]
        // Vocabulary is not sent. Gemini treats the list as a phrase prior and
        // will emit a term the speaker never said. Spelling help cannot insert words.
        let payload: [String: Any] = [
            "setup": [
                "model": "models/\(config.liveModel)",
                "generationConfig": ["responseModalities": ["TEXT"]],
                "inputAudioTranscription": transcription,
                "realtimeInputConfig": [
                    "automaticActivityDetection": ["disabled": true],
                ],
            ] as [String: Any],
        ]
        return encode(payload)
    }

    public static func activityStart() -> Data {
        encode(["realtimeInput": ["activityStart": [String: String]()]])
    }

    public static func activityEnd() -> Data {
        encode(["realtimeInput": ["activityEnd": [String: String]()]])
    }

    public static func audio(pcm: Data) -> Data {
        encode([
            "realtimeInput": [
                "audio": [
                    "data": pcm.base64EncodedString(),
                    "mimeType": "audio/pcm;rate=16000",
                ],
            ],
        ])
    }

    public static func unaryRequest(wav: Data, config: GeminiConfiguration) -> Data {
        let transcriptionConfig: [String: Any] = [
            "language_codes": config.languageCodes,
            // Interactions documents smart mode as the string "smart".
            // Verbatim stays an object because that is where its options live.
            "mode": config.mode == .smart ? "smart" : ["type": "verbatim"],
        ]
        let payload: [String: Any] = [
            "model": config.unaryModel,
            "input": [
                [
                    "type": "audio",
                    "data": wav.base64EncodedString(),
                    "mime_type": "audio/wav",
                ],
            ],
            "generation_config": ["transcription_config": transcriptionConfig],
        ]
        return encode(payload)
    }

    /// Extract transcript text and language from an Interactions response,
    /// tolerating the three shapes the endpoint has returned.
    public static func transcript(from response: Data) -> (text: String, language: String) {
        guard let object = try? JSONSerialization.jsonObject(with: response) as? [String: Any] else {
            return ("", "")
        }
        var text = (object["output_text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)

        if text.isEmpty, let steps = object["steps"] as? [[String: Any]] {
            for step in steps {
                guard let content = step["content"] as? [[String: Any]] else { continue }
                for item in content {
                    let candidate = (item["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                    if !candidate.isEmpty {
                        text = candidate
                        break
                    }
                }
                if !text.isEmpty { break }
            }
        }

        if text.isEmpty, let candidates = object["candidates"] as? [[String: Any]] {
            for candidate in candidates {
                let content = candidate["content"] as? [String: Any]
                let parts = content?["parts"] as? [[String: Any]] ?? []
                for part in parts {
                    let piece = (part["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
                    if !piece.isEmpty {
                        text = piece
                        break
                    }
                }
                if !text.isEmpty { break }
            }
        }

        let language = (object["language"] as? String ?? "").trimmingCharacters(in: .whitespaces)
        return (text, language)
    }

    private static func encode(_ payload: [String: Any]) -> Data {
        (try? JSONSerialization.data(withJSONObject: payload)) ?? Data()
    }
}

public struct GeminiTranscriber: Transcribing {
    public var configuration: GeminiConfiguration
    private let client: RetryingHTTPClient

    public init(configuration: GeminiConfiguration, client: RetryingHTTPClient = RetryingHTTPClient()) {
        self.configuration = configuration
        self.client = client
    }

    public var providerName: String { "gemini" }
    public var modelName: String { configuration.unaryModel }

    public func makeLiveSession() -> (any LiveTranscribing)? {
        GeminiLiveSession(configuration: configuration)
    }

    public func transcribe(wav: Data) async throws -> TranscriptionResult {
        var request = URLRequest(url: GeminiMessage.unaryURL)
        request.httpMethod = "POST"
        request.timeoutInterval = 45
        request.setValue(configuration.apiKey, forHTTPHeaderField: "x-goog-api-key")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = GeminiMessage.unaryRequest(wav: wav, config: configuration)

        let startedAt = Date()
        let data = try await client.send(request)
        let (text, language) = GeminiMessage.transcript(from: data)
        guard !text.isEmpty else { throw TranscriptionError.empty }
        return TranscriptionResult(text: text, language: language, latency: Date().timeIntervalSince(startedAt))
    }
}

/// Bidirectional live-socket transport. Sends must be awaited one at a time:
/// `URLSessionWebSocketTask` drops or stalls a send that overlaps another.
public protocol LiveSocket: AnyObject, Sendable {
    func connect()
    func send(text: String) async throws
    func receiveText() async throws -> String
    func cancel()
}

final class URLSessionLiveSocket: LiveSocket, @unchecked Sendable {
    private let task: URLSessionWebSocketTask?

    init(session: URLSession, socketURL: URL, apiKey: String) {
        var components = URLComponents(url: socketURL, resolvingAgainstBaseURL: false)
        components?.queryItems = [URLQueryItem(name: "key", value: apiKey)]
        if let url = components?.url {
            self.task = session.webSocketTask(with: url)
        } else {
            self.task = nil
        }
    }

    func connect() {
        task?.resume()
    }

    func send(text: String) async throws {
        guard let task else { throw TranscriptionError.transport("invalid live url") }
        try await task.send(.string(text))
    }

    func receiveText() async throws -> String {
        guard let task else { throw TranscriptionError.transport("invalid live url") }
        switch try await task.receive() {
        case .string(let value):
            return value
        case .data(let data):
            return String(data: data, encoding: .utf8) ?? ""
        @unknown default:
            return ""
        }
    }

    func cancel() {
        task?.cancel(with: .normalClosure, reason: nil)
    }
}

/// One push-to-talk turn on the streaming Gemini model.
///
/// Semantics (matching the proven protocol):
/// - no audio byte leaves before the setup completes; early frames are buffered
/// - websocket writes are strictly ordered: setup, activity start, audio, activity end
/// - activity start opens the turn, activity end closes it on release
/// - the paste text is the speaker's `inputTranscription` (or the latest interim)
/// - a model reply (`modelTurn`, `outputTranscription`) is never the transcript
/// - a transport failure with partial finals keeps the partial text
public actor GeminiLiveSession: LiveTranscribing {
    private let configuration: GeminiConfiguration
    private let socket: any LiveSocket
    private let setupTimeoutSeconds: TimeInterval
    private let finalTimeoutSeconds: TimeInterval
    private let finalGraceSeconds: TimeInterval
    private let modelReplyWaitSeconds: TimeInterval

    private var receiveTask: Task<Void, Never>?
    private var setupTimeoutTask: Task<Void, Never>?
    private var finalTimeoutTask: Task<Void, Never>?
    private var graceTask: Task<Void, Never>?

    private var outbound: [Data] = []
    private var pumping = false
    private var socketClosed = false
    private var buffered: [Data] = []
    private var streaming = false
    private var endRequested = false
    private var endSent = false
    private var finals: [String] = []
    private var interim = ""
    private var language = ""
    private var sawModelReply = false
    private var modelReplyArmed = false
    private var loggedContentKeys: Set<String> = []
    private var finished = false
    private var result: TranscriptionResult?
    private var failure: TranscriptionError?
    private var continuation: CheckedContinuation<TranscriptionResult, Error>?

    public init(
        configuration: GeminiConfiguration,
        urlSession: URLSession = .shared,
        socketURL: URL = GeminiMessage.liveURL,
        socket: (any LiveSocket)? = nil,
        setupTimeout: TimeInterval = 10,
        finalTimeout: TimeInterval = 8,
        grace: TimeInterval = 0.75,
        modelReplyWait: TimeInterval = 3
    ) {
        self.configuration = configuration
        self.socket = socket ?? URLSessionLiveSocket(
            session: urlSession,
            socketURL: socketURL,
            apiKey: configuration.apiKey
        )
        self.setupTimeoutSeconds = setupTimeout
        self.finalTimeoutSeconds = finalTimeout
        self.finalGraceSeconds = grace
        self.modelReplyWaitSeconds = modelReplyWait
    }

    public func start() {
        guard receiveTask == nil, !finished else { return }
        socket.connect()
        enqueue(GeminiMessage.setup(configuration))
        receiveLoop()
        scheduleSetupTimeout()
    }

    public func write(_ pcm: Data) {
        guard !pcm.isEmpty, !endRequested, !finished else { return }
        if streaming {
            enqueue(GeminiMessage.audio(pcm: pcm))
        } else {
            buffered.append(pcm)
        }
    }

    public func finish() async throws -> TranscriptionResult {
        try await withCheckedThrowingContinuation { continuation in
            if finished {
                if let result {
                    continuation.resume(returning: result)
                } else if let failure {
                    continuation.resume(throwing: failure)
                } else {
                    continuation.resume(throwing: TranscriptionError.empty)
                }
                return
            }
            self.continuation = continuation
            endRequested = true
            sendActivityEndIfNeeded()
        }
    }

    public func close() {
        guard !finished else { return }
        fail(.transport("cancelled"))
    }

    // MARK: - Protocol plumbing

    /// Queue a websocket message. `URLSessionWebSocketTask` only delivers sends
    /// that are started after the previous send finishes, so this pump is the
    /// only writer.
    private func enqueue(_ data: Data) {
        guard !finished, !data.isEmpty else { return }
        outbound.append(data)
        guard !pumping else { return }
        pumping = true
        Task { await self.pumpOutbound() }
    }

    private func pumpOutbound() async {
        while !outbound.isEmpty, !finished {
            let next = outbound.removeFirst()
            await transmit(next)
        }
        pumping = false
        if !outbound.isEmpty, !finished {
            pumping = true
            await pumpOutbound()
        }
    }

    private func transmit(_ data: Data) async {
        guard !finished, let text = String(data: data, encoding: .utf8) else { return }
        do {
            try await socket.send(text: text)
        } catch {
            guard !finished else { return }
            YapLog.warning("Gemini live send failed: \(redacted(error.localizedDescription))")
            handleSocketFailure(error)
        }
    }

    private func receiveLoop() {
        receiveTask = Task {
            do {
                while true {
                    let text = try await self.socket.receiveText()
                    if text.isEmpty { continue }
                    if self.handle(text) { return }
                }
            } catch {
                self.handleSocketFailure(error)
            }
        }
    }

    /// Returns true when the receive loop should stop.
    private func handle(_ text: String) -> Bool {
        guard let data = text.data(using: .utf8),
              let message = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return finished
        }

        if message["setupComplete"] != nil || message["setup_complete"] != nil {
            onSetupComplete()
            return finished
        }

        if let error = message["error"] {
            let detail: String
            if let object = error as? [String: Any] {
                detail = String(describing: object["message"] ?? object["status"] ?? "gemini live error")
            } else {
                detail = String(describing: error)
            }
            fail(.transport(redacted(detail)))
            return true
        }

        guard let content = serverContent(from: message) else {
            let keys = message.keys.sorted().joined(separator: ",")
            if !keys.isEmpty {
                YapLog.info("Gemini live ignored keys=\(keys)")
            }
            return finished
        }
        noteContentKeys(content)

        if let transcription = inputTranscription(in: content) {
            let text = (transcription["text"] as? String ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                finals.append(text)
                YapLog.info("Gemini live transcript chars=\(text.count)")
                if endSent {
                    scheduleGrace()
                }
            }
            rememberLanguage(transcription)
        }
        if finals.isEmpty, let text = interimTranscription(in: content) {
            // Keep the latest hypothesis, but do not finish on it. An early
            // interim is a prefix; the final is what includes the last words.
            interim = text
        }

        if isModelReply(content) {
            if !sawModelReply {
                YapLog.info("Gemini live model reply ignored")
            }
            sawModelReply = true
            // No finalized speaker text yet. One bounded wait, which a later
            // final cancels. Further reply chunks must not keep resetting it.
            if endSent, finals.isEmpty {
                scheduleModelReplyDeadline()
            }
        }

        if turnIsComplete(content) {
            YapLog.info("Gemini live turn complete")
            if speakerTranscript().isEmpty, endSent {
                // Transcription can arrive after turnComplete. Give it the grace
                // window instead of falling through immediately.
                scheduleGrace()
            } else if !speakerTranscript().isEmpty {
                complete()
            }
        }
        return finished
    }

    private func noteContentKeys(_ content: [String: Any]) {
        let keys = content.keys.sorted().joined(separator: ",")
        guard loggedContentKeys.insert(keys).inserted, !keys.isEmpty else { return }
        YapLog.info("Gemini live server keys=\(keys)")
    }

    private func inputTranscription(in content: [String: Any]) -> [String: Any]? {
        (content["inputTranscription"] as? [String: Any])
            ?? (content["input_transcription"] as? [String: Any])
    }

    /// Latest hypothesis of the speaker's words. Replaced, not appended.
    private func interimTranscription(in content: [String: Any]) -> String? {
        let transcription = (content["interimInputTranscription"] as? [String: Any])
            ?? (content["interim_input_transcription"] as? [String: Any])
        guard let transcription else { return nil }
        let text = (transcription["text"] as? String ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return nil }
        rememberLanguage(transcription)
        return text
    }

    private func rememberLanguage(_ transcription: [String: Any]) {
        for key in ["language", "languageCode", "language_code"] {
            let value = (transcription[key] as? String ?? "").trimmingCharacters(in: .whitespaces)
            if !value.isEmpty {
                language = value
                break
            }
        }
    }

    /// Text the model generated on its own. That is not dictation.
    private func isModelReply(_ content: [String: Any]) -> Bool {
        if content["modelTurn"] != nil || content["model_turn"] != nil { return true }
        if content["outputTranscription"] != nil || content["output_transcription"] != nil { return true }
        return false
    }

    /// Final speaker text when the server sent any, otherwise the latest interim.
    private func speakerTranscript() -> String {
        let finalText = finals.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        if !finalText.isEmpty { return finalText }
        return interim.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func serverContent(from message: [String: Any]) -> [String: Any]? {
        if let content = message["serverContent"] as? [String: Any] { return content }
        if let content = message["server_content"] as? [String: Any] { return content }
        let transcription = (message["inputTranscription"] as? [String: Any])
            ?? (message["input_transcription"] as? [String: Any])
        if let transcription {
            return ["inputTranscription": transcription]
        }
        return nil
    }

    private func turnIsComplete(_ content: [String: Any]) -> Bool {
        for key in ["turnComplete", "turn_complete"] {
            guard let value = content[key] else { continue }
            if let flag = value as? Bool { return flag }
            if let number = value as? NSNumber { return number.boolValue }
            return true
        }
        return false
    }

    private func onSetupComplete() {
        guard !streaming, !finished else { return }
        streaming = true
        setupTimeoutTask?.cancel()
        setupTimeoutTask = nil
        YapLog.info("Gemini live setup complete")
        enqueue(GeminiMessage.activityStart())
        for chunk in buffered {
            enqueue(GeminiMessage.audio(pcm: chunk))
        }
        buffered.removeAll()
        sendActivityEndIfNeeded()
    }

    private func sendActivityEndIfNeeded() {
        guard streaming, endRequested, !endSent, !finished else { return }
        endSent = true
        enqueue(GeminiMessage.activityEnd())
        YapLog.info("Gemini live activity end queued")
        scheduleFinalTimeout()
        // A finalized transcript can settle immediately. An interim hypothesis
        // stays open so the final, which often arrives just after release, can
        // replace it. A model reply must not hold that wait open.
        if !finals.isEmpty {
            scheduleGrace()
        } else if sawModelReply {
            scheduleModelReplyDeadline()
        }
    }

    private func handleSocketFailure(_ error: Error) {
        // Teardown after a completed turn is not a failure.
        guard !finished else { return }
        let message = redacted(error.localizedDescription)
        if speakerTranscript().isEmpty, sawModelReply {
            YapLog.warning("Gemini live socket failed after a model reply: \(message)")
            complete()
            return
        }
        if speakerTranscript().isEmpty {
            fail(.transport(message))
        } else {
            YapLog.warning("Gemini live socket failed with partial transcript: \(message)")
            complete()
        }
    }

    // MARK: - Timers

    private func scheduleSetupTimeout() {
        setupTimeoutTask?.cancel()
        setupTimeoutTask = Task {
            do {
                try await Task.sleep(for: .seconds(self.setupTimeoutSeconds))
            } catch {
                return
            }
            self.setupTimeoutElapsed()
        }
    }

    private func setupTimeoutElapsed() {
        guard !streaming, !finished else { return }
        YapLog.warning("Gemini live setup timed out")
        fail(.timedOut)
    }

    private func scheduleFinalTimeout() {
        finalTimeoutTask?.cancel()
        finalTimeoutTask = Task {
            do {
                try await Task.sleep(for: .seconds(self.finalTimeoutSeconds))
            } catch {
                return
            }
            self.finalTimeoutElapsed()
        }
    }

    private func finalTimeoutElapsed() {
        guard !finished else { return }
        if !speakerTranscript().isEmpty || sawModelReply {
            if speakerTranscript().isEmpty {
                YapLog.warning("Gemini live final timed out after a model reply")
            }
            complete()
        } else {
            YapLog.warning("Gemini live final timed out")
            fail(.timedOut)
        }
    }

    /// One bounded wait for a speaker transcript after the model starts replying.
    /// Further reply chunks must not keep the spinner up.
    private func scheduleModelReplyDeadline() {
        guard !modelReplyArmed, !finished else { return }
        modelReplyArmed = true
        graceTask?.cancel()
        graceTask = Task {
            do {
                try await Task.sleep(for: .seconds(self.modelReplyWaitSeconds))
            } catch {
                return
            }
            self.graceElapsed()
        }
    }

    private func scheduleGrace() {
        graceTask?.cancel()
        graceTask = Task {
            do {
                try await Task.sleep(for: .seconds(self.finalGraceSeconds))
            } catch {
                return
            }
            self.graceElapsed()
        }
    }

    private func graceElapsed() {
        guard !finished else { return }
        complete()
    }

    private func cancelTimers() {
        setupTimeoutTask?.cancel()
        finalTimeoutTask?.cancel()
        graceTask?.cancel()
        setupTimeoutTask = nil
        finalTimeoutTask = nil
        graceTask = nil
    }

    // MARK: - Settlement

    private func complete() {
        guard !finished else { return }
        finished = true
        cancelTimers()
        buffered.removeAll()
        let text = speakerTranscript()
        if finals.isEmpty, !text.isEmpty {
            YapLog.info("Gemini live used interim transcript chars=\(text.count)")
        }
        let result = TranscriptionResult(
            text: text,
            language: language,
            latency: 0,
            modelReplyOnly: text.isEmpty && sawModelReply
        )
        self.result = result
        closeSocket()
        if let continuation {
            self.continuation = nil
            continuation.resume(returning: result)
        }
    }

    private func fail(_ error: TranscriptionError) {
        guard !finished else { return }
        if !speakerTranscript().isEmpty {
            // A transport failure after partial transcript keeps that text.
            complete()
            return
        }
        finished = true
        cancelTimers()
        buffered.removeAll()
        failure = error
        closeSocket()
        if let continuation {
            self.continuation = nil
            continuation.resume(throwing: error)
        }
    }

    private func closeSocket() {
        receiveTask?.cancel()
        receiveTask = nil
        guard !socketClosed else { return }
        socketClosed = true
        socket.cancel()
    }

    private func redacted(_ text: String) -> String {
        guard !configuration.apiKey.isEmpty, text.contains(configuration.apiKey) else { return text }
        return text.replacingOccurrences(of: configuration.apiKey, with: "[redacted]")
    }
}

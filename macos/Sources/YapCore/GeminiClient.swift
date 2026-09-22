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
        var transcription: [String: Any] = [
            "languageCodes": config.languageCodes,
            "mode": config.mode == .smart ? "SMART" : "VERBATIM",
        ]
        if !config.vocabulary.isEmpty {
            transcription["customVocabulary"] = config.vocabulary
        }
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
        var transcriptionConfig: [String: Any] = [
            "language_codes": config.languageCodes,
            "mode": ["type": config.mode.rawValue],
        ]
        if !config.vocabulary.isEmpty {
            transcriptionConfig["custom_vocabulary"] = config.vocabulary
        }
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

/// One push-to-talk turn on the streaming Gemini model.
///
/// Semantics (matching the proven protocol):
/// - no audio byte leaves before the setup completes; early frames are buffered
/// - activity start opens the turn, activity end closes it on release
/// - finalization waits for the finalized `inputTranscription`
/// - a transport failure with partial finals keeps the partial text
public actor GeminiLiveSession: LiveTranscribing {
    private let configuration: GeminiConfiguration
    private let urlSession: URLSession
    private let socketURL: URL

    private var socket: URLSessionWebSocketTask?
    private var receiveTask: Task<Void, Never>?
    private var setupTimeoutTask: Task<Void, Never>?
    private var finalTimeoutTask: Task<Void, Never>?
    private var graceTask: Task<Void, Never>?

    private var buffered: [Data] = []
    private var streaming = false
    private var endRequested = false
    private var endSent = false
    private var finals: [String] = []
    private var language = ""
    private var finished = false
    private var result: TranscriptionResult?
    private var failure: TranscriptionError?
    private var continuation: CheckedContinuation<TranscriptionResult, Error>?

    private static let setupTimeoutSeconds = 10.0
    private static let finalTimeoutSeconds = 20.0
    private static let finalGraceSeconds = 0.75

    public init(
        configuration: GeminiConfiguration,
        urlSession: URLSession = .shared,
        socketURL: URL = GeminiMessage.liveURL
    ) {
        self.configuration = configuration
        self.urlSession = urlSession
        self.socketURL = socketURL
    }

    public func start() {
        guard socket == nil, !finished else { return }
        var components = URLComponents(url: socketURL, resolvingAgainstBaseURL: false)
        components?.queryItems = [URLQueryItem(name: "key", value: configuration.apiKey)]
        guard let url = components?.url else {
            fail(.transport("invalid live url"))
            return
        }
        let task = urlSession.webSocketTask(with: url)
        socket = task
        task.resume()
        send(GeminiMessage.setup(configuration))
        receiveLoop()
        scheduleSetupTimeout()
    }

    public func write(_ pcm: Data) {
        guard !pcm.isEmpty, !endRequested, !finished else { return }
        if streaming {
            send(GeminiMessage.audio(pcm: pcm))
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

    private func send(_ data: Data) {
        guard let socket, let text = String(data: data, encoding: .utf8) else { return }
        socket.send(.string(text)) { error in
            if let error {
                YapLog.warning("Gemini live send failed: \(error.localizedDescription)")
            }
        }
    }

    private func receiveLoop() {
        guard let socket else { return }
        receiveTask = Task {
            do {
                while true {
                    let message = try await socket.receive()
                    let text: String
                    switch message {
                    case .string(let value): text = value
                    case .data(let data): text = String(data: data, encoding: .utf8) ?? ""
                    @unknown default: text = ""
                    }
                    if text.isEmpty { continue }
                    let done = self.handle(text)
                    if done { return }
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

        let content = (message["serverContent"] as? [String: Any])
            ?? (message["server_content"] as? [String: Any])
        guard let content else { return finished }

        let transcription = (content["inputTranscription"] as? [String: Any])
            ?? (content["input_transcription"] as? [String: Any])
        if let transcription {
            let text = (transcription["text"] as? String ?? "")
                .trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                finals.append(text)
            }
            for key in ["language", "languageCode", "language_code"] {
                let value = (transcription[key] as? String ?? "").trimmingCharacters(in: .whitespaces)
                if !value.isEmpty {
                    language = value
                    break
                }
            }
            if endSent {
                scheduleGrace()
            }
        }

        if content["turnComplete"] != nil || content["turn_complete"] != nil {
            YapLog.info("Gemini live turn complete")
            complete()
        }
        return finished
    }

    private func onSetupComplete() {
        guard !streaming, !finished else { return }
        streaming = true
        setupTimeoutTask?.cancel()
        setupTimeoutTask = nil
        YapLog.info("Gemini live setup complete")
        send(GeminiMessage.activityStart())
        for chunk in buffered {
            send(GeminiMessage.audio(pcm: chunk))
        }
        buffered.removeAll()
        sendActivityEndIfNeeded()
    }

    private func sendActivityEndIfNeeded() {
        guard streaming, endRequested, !endSent, !finished else { return }
        endSent = true
        send(GeminiMessage.activityEnd())
        scheduleFinalTimeout()
    }

    private func handleSocketFailure(_ error: Error) {
        let message = redacted(error.localizedDescription)
        if finals.isEmpty {
            fail(.transport(message))
        } else {
            YapLog.warning("Gemini live socket failed with partial finals: \(message)")
            complete()
        }
    }

    // MARK: - Timers

    private func scheduleSetupTimeout() {
        setupTimeoutTask?.cancel()
        setupTimeoutTask = Task {
            try? await Task.sleep(for: .seconds(Self.setupTimeoutSeconds))
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
            try? await Task.sleep(for: .seconds(Self.finalTimeoutSeconds))
            self.finalTimeoutElapsed()
        }
    }

    private func finalTimeoutElapsed() {
        guard !finished else { return }
        if finals.isEmpty {
            YapLog.warning("Gemini live final timed out")
            fail(.timedOut)
        } else {
            complete()
        }
    }

    private func scheduleGrace() {
        graceTask?.cancel()
        graceTask = Task {
            try? await Task.sleep(for: .seconds(Self.finalGraceSeconds))
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
        let text = finals.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
        let result = TranscriptionResult(text: text, language: language, latency: 0)
        self.result = result
        closeSocket()
        if let continuation {
            self.continuation = nil
            continuation.resume(returning: result)
        }
    }

    private func fail(_ error: TranscriptionError) {
        guard !finished else { return }
        if !finals.isEmpty {
            // A transport failure after partial finals keeps the partial text.
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
        if let socket {
            self.socket = nil
            socket.cancel(with: .normalClosure, reason: nil)
        }
    }

    private func redacted(_ text: String) -> String {
        guard !configuration.apiKey.isEmpty, text.contains(configuration.apiKey) else { return text }
        return text.replacingOccurrences(of: configuration.apiKey, with: "[redacted]")
    }
}

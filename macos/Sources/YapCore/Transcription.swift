import Foundation

public enum TranscriptionMode: String, Sendable, CaseIterable, Codable {
    /// Gemini returns cleaned, punctuated dictation text directly.
    case smart
    /// Exact words, fillers included, no post-processing.
    case verbatim

    public var displayName: String {
        switch self {
        case .smart: return "Smart (cleaned text)"
        case .verbatim: return "Verbatim (exact words)"
        }
    }
}

public struct TranscriptionResult: Sendable, Equatable, Codable {
    public var text: String
    public var language: String
    public var latency: TimeInterval

    public init(text: String, language: String = "", latency: TimeInterval = 0) {
        self.text = text
        self.language = language
        self.latency = latency
    }
}

public enum TranscriptionError: Error, Sendable, Equatable, CustomStringConvertible {
    case transport(String)
    case http(Int)
    case malformedResponse
    case timedOut
    case empty

    public var description: String {
        switch self {
        case .transport(let message): return "transport(\(message))"
        case .http(let status): return "http(\(status))"
        case .malformedResponse: return "malformed_response"
        case .timedOut: return "timed_out"
        case .empty: return "empty"
        }
    }

    /// Transient failures worth one more attempt: network trouble, 429, 5xx.
    public var isRetryable: Bool {
        switch self {
        case .transport: return true
        case .http(let status): return status == 429 || (500...599).contains(status)
        default: return false
        }
    }
}

/// One push-to-talk streaming session. Audio written before the socket is ready
/// is buffered and sent in order once the session opens.
public protocol LiveTranscribing: AnyObject, Sendable {
    func start() async
    func write(_ pcm: Data) async
    /// Finalize the turn and return the transcript. Throws on transport failure;
    /// an empty transcript is a normal result the caller can fall back from.
    func finish() async throws -> TranscriptionResult
    func close() async
}

/// A transcription backend. `makeLiveSession` returns nil when the provider
/// cannot stream during the hold.
public protocol Transcribing: Sendable {
    var providerName: String { get }
    var modelName: String { get }
    func makeLiveSession() -> (any LiveTranscribing)?
    func transcribe(wav: Data) async throws -> TranscriptionResult
}

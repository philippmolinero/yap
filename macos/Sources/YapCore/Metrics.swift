import Foundation

/// Privacy-preserving pipeline measurement: timings, model identities, and
/// outcome reasons only. Transcript text and credentials never belong here.
public struct PipelineMeasurement: Codable, Sendable, Equatable {
    public var recordingID: Int?
    public var source: String
    public var audioDurationSeconds: Double?
    public var recorderStopSeconds: Double
    public var transcriptionSeconds: Double?
    public var totalSeconds: Double
    public var transcriptionProvider: String
    public var transcriptionModel: String
    public var language: String
    public var textChars: Int
    public var success: Bool
    public var error: String
    public var usedLive: Bool
    public var timestamp: String

    enum CodingKeys: String, CodingKey {
        case recordingID = "recording_id"
        case source
        case audioDurationSeconds = "audio_duration_s"
        case recorderStopSeconds = "recorder_stop_s"
        case transcriptionSeconds = "transcription_s"
        case totalSeconds = "total_s"
        case transcriptionProvider = "transcription_provider"
        case transcriptionModel = "transcription_model"
        case language
        case textChars = "text_chars"
        case success
        case error
        case usedLive = "used_live"
        case timestamp
    }

    public init(
        recordingID: Int? = nil,
        source: String,
        audioDurationSeconds: Double? = nil,
        recorderStopSeconds: Double = 0,
        transcriptionSeconds: Double? = nil,
        totalSeconds: Double,
        transcriptionProvider: String = "",
        transcriptionModel: String = "",
        language: String = "",
        textChars: Int = 0,
        success: Bool,
        error: String = "",
        usedLive: Bool = false,
        timestamp: String = ""
    ) {
        self.recordingID = recordingID
        self.source = source
        self.audioDurationSeconds = audioDurationSeconds
        self.recorderStopSeconds = recorderStopSeconds
        self.transcriptionSeconds = transcriptionSeconds
        self.totalSeconds = totalSeconds
        self.transcriptionProvider = transcriptionProvider
        self.transcriptionModel = transcriptionModel
        self.language = language
        self.textChars = textChars
        self.success = success
        self.error = error
        self.usedLive = usedLive
        self.timestamp = timestamp.isEmpty ? Self.currentTimestamp() : timestamp
    }

    public static func currentTimestamp() -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: Date())
    }
}

public protocol MetricsWriting: Sendable {
    func append(_ measurement: PipelineMeasurement)
}

/// Appends measurements to a local, mode-0600 JSONL file. Metrics must never
/// break dictation, so every failure is swallowed after a log line.
public struct FileMetricsWriter: MetricsWriting {
    public let url: URL

    public init(url: URL = AppConfig.metricsURL) {
        self.url = url
    }

    public func append(_ measurement: PipelineMeasurement) {
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            var line = try encoder.encode(measurement)
            line.append(Data("\n".utf8))
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            if let handle = try? FileHandle(forWritingTo: url) {
                defer { try? handle.close() }
                _ = try handle.seekToEnd()
                try handle.write(contentsOf: line)
            } else {
                try line.write(to: url)
            }
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        } catch {
            YapLog.warning("Failed to write pipeline measurement: \(error.localizedDescription)")
        }
    }
}

public struct NoopMetricsWriter: MetricsWriting {
    public init() {}
    public func append(_ measurement: PipelineMeasurement) {}
}

/// Collects measurements in memory for tests.
public final class MemoryMetricsWriter: MetricsWriting, @unchecked Sendable {
    private let lock = NSLock()
    private var _measurements: [PipelineMeasurement] = []

    public init() {}

    public var measurements: [PipelineMeasurement] {
        lock.withLock { _measurements }
    }

    public func append(_ measurement: PipelineMeasurement) {
        lock.withLock { _measurements.append(measurement) }
    }
}

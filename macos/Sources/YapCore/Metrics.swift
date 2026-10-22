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
        isoTimestamp(from: Date())
    }

    public static func isoTimestamp(from date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }

    public static func parseTimestamp(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: value)
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

// MARK: - Summary

/// One JSONL read. Older Python-era lines omit `used_live` and are skipped so
/// they cannot be mixed into the Gemini live percentiles.
public struct MetricsLogLoad: Equatable, Sendable {
    public var measurements: [PipelineMeasurement]
    public var skipped: Int
    public var fileExists: Bool

    public init(measurements: [PipelineMeasurement], skipped: Int, fileExists: Bool) {
        self.measurements = measurements
        self.skipped = skipped
        self.fileExists = fileExists
    }
}

public enum MetricsLog {
    public static func load(from url: URL) throws -> MetricsLogLoad {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return MetricsLogLoad(measurements: [], skipped: 0, fileExists: false)
        }
        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            throw MetricsLogError.unreadable
        }
        guard let text = String(data: data, encoding: .utf8) else {
            return MetricsLogLoad(measurements: [], skipped: 1, fileExists: true)
        }

        let decoder = JSONDecoder()
        var measurements: [PipelineMeasurement] = []
        var skipped = 0
        for rawLine in text.split(separator: "\n", omittingEmptySubsequences: false) {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            if line.isEmpty { continue }
            guard let lineData = line.data(using: .utf8),
                  let measurement = try? decoder.decode(PipelineMeasurement.self, from: lineData) else {
                skipped += 1
                continue
            }
            measurements.append(measurement)
        }
        return MetricsLogLoad(measurements: measurements, skipped: skipped, fileExists: true)
    }
}

public enum MetricsLogError: Error, Equatable {
    case unreadable
}

/// Nearest-rank percentile. With one sample, p50 and p95 are that sample.
/// With ten sorted samples, p95 is the last one.
public enum MetricsPercentile {
    public static func nearestRank(_ values: [Double], percentile: Double) -> Double? {
        let finite = values.filter(\.isFinite).sorted()
        guard !finite.isEmpty else { return nil }
        // (index + 1) / n >= percentile, in integer arithmetic so 0.95 * 20
        // cannot round to either side of 19.
        let (numerator, denominator) = Self.ratio(for: percentile)
        let n = finite.count
        var index = n - 1
        for candidate in 0..<n where (candidate + 1) * denominator >= numerator * n {
            index = candidate
            break
        }
        return finite[index]
    }

    /// Percentile as a reduced-enough fraction. 0.50 and 0.95 are exact.
    private static func ratio(for percentile: Double) -> (numerator: Int, denominator: Int) {
        if percentile <= 0 { return (0, 1) }
        if percentile >= 1 { return (1, 1) }
        if abs(percentile - 0.50) < 0.000_001 { return (1, 2) }
        if abs(percentile - 0.95) < 0.000_001 { return (19, 20) }
        let denominator = 10_000
        let numerator = Int((percentile * Double(denominator)).rounded())
        return (min(denominator, max(0, numerator)), denominator)
    }
}

public struct MetricsTiming: Equatable, Sendable {
    public var name: String
    public var count: Int
    public var p50: Double?
    public var p95: Double?

    public init(name: String, values: [Double]) {
        let present = values.filter(\.isFinite)
        self.name = name
        self.count = present.count
        self.p50 = MetricsPercentile.nearestRank(present, percentile: 0.50)
        self.p95 = MetricsPercentile.nearestRank(present, percentile: 0.95)
    }
}

public struct MetricsCount: Equatable, Sendable {
    public var name: String
    public var count: Int

    public init(name: String, count: Int) {
        self.name = name
        self.count = count
    }
}

public struct MetricsGroup: Equatable, Sendable {
    public var title: String
    public var count: Int
    public var timings: [MetricsTiming]
    public var errors: [MetricsCount]

    public init(title: String, count: Int, timings: [MetricsTiming], errors: [MetricsCount]) {
        self.title = title
        self.count = count
        self.timings = timings
        self.errors = errors
    }
}

/// Counts, p50, and p95 for the timings already on disk. The report never
/// includes transcript text.
public struct MetricsReport: Equatable, Sendable {
    public var fileExists: Bool
    public var included: Int
    public var skipped: Int
    public var oldest: String?
    public var newest: String?
    public var models: [MetricsCount]
    public var groups: [MetricsGroup]
    public var recentGroups: [MetricsGroup]
    /// True when every included row is already inside the last-24-hour window,
    /// so the recent table would repeat the full table.
    public var recentCoversAll: Bool

    public static let recentWindow: TimeInterval = 24 * 60 * 60

    public static func build(from load: MetricsLogLoad, now: Date = Date()) -> MetricsReport {
        let measurements = load.measurements
        let timestamps = measurements.compactMap { measurement -> (String, Date)? in
            let raw = measurement.timestamp
            guard let date = PipelineMeasurement.parseTimestamp(raw) else { return nil }
            return (raw, date)
        }
        let oldest = timestamps.min { $0.1 < $1.1 }?.0
        let newest = timestamps.max { $0.1 < $1.1 }?.0
        let cutoff = now.addingTimeInterval(-recentWindow)
        let recent = measurements.filter { measurement in
            guard let date = PipelineMeasurement.parseTimestamp(measurement.timestamp) else { return false }
            return date >= cutoff
        }
        return MetricsReport(
            fileExists: load.fileExists,
            included: measurements.count,
            skipped: load.skipped,
            oldest: oldest,
            newest: newest,
            models: tally(measurements.map(\.transcriptionModel), accepting: Self.isSafeModel),
            groups: group(measurements),
            recentGroups: group(recent),
            recentCoversAll: !measurements.isEmpty && recent.count == measurements.count
        )
    }

    public func render(path: String) -> String {
        var lines: [String] = []
        lines.append("Yap metrics")
        lines.append(row("file", path))
        lines.append(row("included", "\(included)"))
        if skipped == 0 {
            lines.append(row("skipped", "0"))
        } else {
            lines.append(row("skipped", "\(skipped) (unreadable or older format, not counted)"))
        }
        if let oldest, let newest {
            lines.append(row("span", "\(oldest) to \(newest)"))
        }
        if !models.isEmpty {
            let listed = models.map { "\($0.name) (\($0.count))" }.joined(separator: ", ")
            lines.append(row("models", listed))
        }
        lines.append("")
        lines.append("total_s            key release until the transcript is on the clipboard")
        lines.append("transcription_s    wait for Gemini inside total_s")
        lines.append("recorder_stop_s    stopping the microphone")
        lines.append("audio_duration_s   length of the recording, not a wait")
        lines.append("percentiles        nearest-rank p50 and p95 inside each group")
        lines.append("paste delay        not included; Cmd+V is posted about 50 ms after total_s")
        lines.append("")

        guard fileExists else {
            lines.append("No metrics file yet. Dictate normally, then run this again.")
            return lines.joined(separator: "\n")
        }
        guard included > 0 else {
            lines.append("No current-format measurements yet. Dictate normally, then run this again.")
            return lines.joined(separator: "\n")
        }

        lines.append("All included rows")
        lines.append("")
        lines.append(contentsOf: render(groups))

        if recentCoversAll {
            lines.append("")
            lines.append("All included rows are from the last 24 hours.")
        } else if recentGroups.contains(where: { $0.count > 0 }) {
            lines.append("")
            lines.append("Last 24 hours")
            lines.append("")
            lines.append(contentsOf: render(recentGroups))
        } else {
            lines.append("")
            lines.append("Nothing in the last 24 hours.")
        }
        return lines.joined(separator: "\n")
    }

    private func render(_ groups: [MetricsGroup]) -> [String] {
        var lines: [String] = []
        for group in groups {
            if !lines.isEmpty { lines.append("") }
            lines.append(row(group.title, "n=\(group.count)"))
            for timing in group.timings {
                let p50 = formatSeconds(timing.p50)
                let p95 = formatSeconds(timing.p95)
                lines.append(row("  \(timing.name)", "n=\(timing.count)  p50=\(p50)  p95=\(p95)"))
            }
            if !group.errors.isEmpty {
                let listed = group.errors.map { "\($0.name) (\($0.count))" }.joined(separator: ", ")
                lines.append(row("  errors", listed))
            }
        }
        return lines
    }

    private func row(_ label: String, _ value: String) -> String {
        let column = 32
        let padded = label.count >= column ? label + "  " : label.padding(toLength: column, withPad: " ", startingAt: 0)
        return padded + value
    }

    private func formatSeconds(_ value: Double?) -> String {
        guard let value else { return "n/a" }
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.numberStyle = .decimal
        formatter.minimumFractionDigits = 3
        formatter.maximumFractionDigits = 3
        formatter.usesGroupingSeparator = false
        let number = formatter.string(from: NSNumber(value: value)) ?? "0.000"
        return number + "s"
    }

    private static func group(_ measurements: [PipelineMeasurement]) -> [MetricsGroup] {
        let slices: [(String, Bool, Bool)] = [
            ("live path, successful", true, true),
            ("live path, failed", true, false),
            ("batch fallback, successful", false, true),
            ("batch fallback, failed", false, false),
        ]
        return slices.map { title, usedLive, success in
            let rows = measurements.filter { $0.usedLive == usedLive && $0.success == success }
            let timings = [
                MetricsTiming(name: "total_s", values: rows.map(\.totalSeconds)),
                MetricsTiming(name: "transcription_s", values: rows.compactMap(\.transcriptionSeconds)),
                MetricsTiming(name: "recorder_stop_s", values: rows.map(\.recorderStopSeconds)),
                MetricsTiming(name: "audio_duration_s", values: rows.compactMap(\.audioDurationSeconds)),
            ]
            let errors = success
                ? []
                : tally(rows.map(\.error), accepting: Self.isSafeErrorCode)
            return MetricsGroup(title: title, count: rows.count, timings: timings, errors: errors)
        }
    }

    /// Counts only tokens that cannot be a dictated sentence. Anything else
    /// is folded into one bucket so a bad line cannot print transcript text.
    private static func tally(_ raw: [String], accepting: (String) -> Bool) -> [MetricsCount] {
        var counts: [String: Int] = [:]
        for value in raw where !value.isEmpty {
            let name = accepting(value) ? value : "unrecognized"
            counts[name, default: 0] += 1
        }
        return counts
            .map { MetricsCount(name: $0.key, count: $0.value) }
            .sorted { lhs, rhs in
                if lhs.count != rhs.count { return lhs.count > rhs.count }
                return lhs.name < rhs.name
            }
    }

    private static func isSafeModel(_ value: String) -> Bool {
        isSafeToken(value, maxLength: 80, extra: ".-_/")
    }

    private static func isSafeErrorCode(_ value: String) -> Bool {
        isSafeToken(value, maxLength: 40, extra: "_")
    }

    private static func isSafeToken(_ value: String, maxLength: Int, extra: String) -> Bool {
        guard (1...maxLength).contains(value.count) else { return false }
        let extras = Set(extra.unicodeScalars)
        return value.unicodeScalars.allSatisfy { scalar in
            let value = scalar.value
            let isDigit = value >= 48 && value <= 57
            let isLower = value >= 97 && value <= 122
            let isUpper = value >= 65 && value <= 90
            return isDigit || isLower || isUpper || extras.contains(scalar)
        }
    }
}

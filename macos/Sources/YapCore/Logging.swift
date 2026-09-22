import Foundation

/// File + stderr logging. Transcript content never belongs in these lines.
public enum YapLog {
    public static let logURL = AppConfig.directory.appendingPathComponent("yap.log")

    private static let lock = NSLock()
    private static let timestampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "HH:mm:ss.SSS"
        return formatter
    }()

    /// Start a fresh log file for this launch.
    public static func truncate() {
        lock.lock()
        defer { lock.unlock() }
        try? FileManager.default.createDirectory(at: AppConfig.directory, withIntermediateDirectories: true)
        FileManager.default.createFile(atPath: logURL.path, contents: Data())
    }

    public static func info(_ message: String) {
        write(level: "INFO", message)
    }

    public static func warning(_ message: String) {
        write(level: "WARN", message)
    }

    public static func error(_ message: String) {
        write(level: "ERROR", message)
    }

    private static func write(level: String, _ message: String) {
        let line = "\(timestampFormatter.string(from: Date())) [\(level)] \(message)"
        lock.lock()
        defer { lock.unlock() }
        fputs(line + "\n", stderr)
        guard let data = (line + "\n").data(using: .utf8) else { return }
        try? FileManager.default.createDirectory(at: AppConfig.directory, withIntermediateDirectories: true)
        if FileManager.default.fileExists(atPath: logURL.path),
           let handle = try? FileHandle(forWritingTo: logURL) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: data)
        } else {
            try? data.write(to: logURL)
        }
    }
}

import Foundation

/// Persistent dictation history for the Recent menu (most recent first).
public protocol HistoryStoring: Sendable {
    func load() -> [String]
    func prepend(_ text: String)
}

public struct FileHistoryStore: HistoryStoring {
    public let url: URL
    public let limit: Int

    public init(url: URL = AppConfig.historyURL, limit: Int = 15) {
        self.url = url
        self.limit = max(1, limit)
    }

    public func load() -> [String] {
        read(limit: limit)
    }

    public func prepend(_ text: String) {
        var items = read(limit: max(limit, 50))
        items.insert(text, at: 0)
        items = Array(items.prefix(limit))
        write(items)
    }

    private func read(limit: Int) -> [String] {
        guard let data = try? Data(contentsOf: url) else { return [] }
        guard let items = try? JSONDecoder().decode([String].self, from: data) else {
            YapLog.warning("History file \(url.lastPathComponent) has unexpected format, ignoring")
            return []
        }
        return Array(items.filter { !$0.isEmpty }.prefix(limit))
    }

    private func write(_ items: [String]) {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            let data = try JSONEncoder().encode(items)
            try data.write(to: url, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        } catch {
            YapLog.warning("Failed to save history: \(error.localizedDescription)")
        }
    }
}

/// In-memory history for tests and previews.
public struct MemoryHistoryStore: HistoryStoring {
    private let box: LockedBox<[String]>
    public let limit: Int

    public init(items: [String] = [], limit: Int = 15) {
        self.box = LockedBox(items)
        self.limit = limit
    }

    public func load() -> [String] { box.value }

    public func prepend(_ text: String) {
        box.value = Array(([text] + box.value).prefix(limit))
    }
}

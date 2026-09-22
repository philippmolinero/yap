import Foundation
import YapCore

/// Keeps a second Yap from starting while one is already running.
enum SingleInstanceLock {
    private nonisolated(unsafe) static var handle: FileHandle?

    static func acquire() -> Bool {
        let url = AppConfig.lockURL
        try? FileManager.default.createDirectory(at: AppConfig.directory, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: url.path) {
            FileManager.default.createFile(atPath: url.path, contents: nil)
        }
        guard let file = try? FileHandle(forWritingTo: url) else { return false }
        if flock(file.fileDescriptor, LOCK_EX | LOCK_NB) != 0 {
            try? file.close()
            return false
        }
        handle = file
        return true
    }

    static func release() {
        if let file = handle {
            flock(file.fileDescriptor, LOCK_UN)
            try? file.close()
        }
        handle = nil
    }
}

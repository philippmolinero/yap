import AppKit
import ApplicationServices
import Foundation
import YapCore

/// Clipboard paste that restores what the user had on the clipboard and puts
/// the text back into the app that was focused when the trigger went down.
final class MacPaster: TextPasting, @unchecked Sendable {
    private struct SavedItem {
        var entries: [(type: NSPasteboard.PasteboardType, data: Data)]
    }

    private let lock = NSLock()
    private let restoreDelay: TimeInterval
    private static let generationLock = NSLock()
    private nonisolated(unsafe) static var currentGeneration = 0

    /// `restoreDelay` is how long the transcript stays on the clipboard before
    /// the previous contents go back. The target app needs time to read it.
    init(restoreDelay: TimeInterval = 0.35) {
        self.restoreDelay = restoreDelay
    }

    /// A pending clipboard restore only applies while no newer paste happened.
    static func isCurrentGeneration(_ generation: Int) -> Bool {
        generationLock.withLock { currentGeneration == generation }
    }

    func paste(_ text: String, target: PasteTarget?, delay: TimeInterval) -> PasteOutcome {
        let board = NSPasteboard.general
        let saved = Self.snapshot(board)
        let myGeneration: Int = Self.generationLock.withLock {
            Self.currentGeneration += 1
            return Self.currentGeneration
        }

        board.clearContents()
        board.setString(text, forType: .string)
        YapLog.info("paste wrote \(text.count) chars to the clipboard")

        if let target {
            guard let app = NSRunningApplication(processIdentifier: target.pid), !app.isTerminated else {
                YapLog.info("paste target missing")
                return .clipboardOnly(reason: "Paste target closed. Text is on the clipboard.")
            }
        }

        guard AXIsProcessTrusted() else {
            YapLog.warning("Accessibility permission missing — copied text but skipped Cmd+V")
            return .clipboardOnly(reason: "Accessibility permission missing. Text is on the clipboard.")
        }

        let restoreDelay = self.restoreDelay
        DispatchQueue.global(qos: .userInitiated).async {
            if delay > 0 {
                Thread.sleep(forTimeInterval: delay)
            }
            if let target {
                guard let app = NSRunningApplication(processIdentifier: target.pid), !app.isTerminated else {
                    YapLog.info("paste target closed before keystroke; text stays on the clipboard")
                    return
                }
                if !app.isActive {
                    app.activate()
                    // Give the target a moment to take focus before Cmd+V lands.
                    Thread.sleep(forTimeInterval: 0.05)
                }
            }
            Self.postCommandV()
            DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + restoreDelay) {
                guard MacPaster.isCurrentGeneration(myGeneration) else { return }
                Self.restore(saved, on: NSPasteboard.general)
                YapLog.info("paste restored clipboard")
            }
        }
        return .pasted
    }

    // MARK: - Pasteboard

    private static func snapshot(_ board: NSPasteboard) -> [SavedItem] {
        (board.pasteboardItems ?? []).map { item in
            SavedItem(entries: item.types.compactMap { type in
                guard let data = item.data(forType: type) else { return nil }
                return (type, data)
            })
        }
    }

    private static func restore(_ items: [SavedItem], on board: NSPasteboard) {
        board.clearContents()
        guard !items.isEmpty else { return }
        let pasteboardItems = items.map { saved -> NSPasteboardItem in
            let item = NSPasteboardItem()
            for entry in saved.entries {
                item.setData(entry.data, forType: entry.type)
            }
            return item
        }
        board.writeObjects(pasteboardItems)
    }

    // MARK: - Keystroke

    private static func postCommandV() {
        let source = CGEventSource(stateID: .combinedSessionState)
        let keyDown = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: true)
        let keyUp = CGEvent(keyboardEventSource: source, virtualKey: 9, keyDown: false)
        keyDown?.flags = .maskCommand
        keyUp?.flags = .maskCommand
        keyDown?.post(tap: .cghidEventTap)
        keyUp?.post(tap: .cghidEventTap)
    }
}

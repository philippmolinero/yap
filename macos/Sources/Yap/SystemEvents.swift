import AppKit
import Foundation
import YapCore

/// Sleep/wake handling plus the paste-target capture at key-down time.
@MainActor
final class SystemEvents {
    var onWillSleep: () -> Void = {}
    var onDidWake: () -> Void = {}

    private var observers: [NSObjectProtocol] = []

    func start() {
        guard observers.isEmpty else { return }
        let center = NSWorkspace.shared.notificationCenter
        observers.append(center.addObserver(
            forName: NSWorkspace.willSleepNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            YapLog.info("System going to sleep")
            Task { @MainActor in self?.onWillSleep() }
        })
        observers.append(center.addObserver(
            forName: NSWorkspace.didWakeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            YapLog.info("System woke from sleep")
            Task { @MainActor in self?.onDidWake() }
        })
    }

    func stop() {
        let center = NSWorkspace.shared.notificationCenter
        observers.forEach(center.removeObserver(_:))
        observers = []
    }

    /// The app that was focused when the trigger went down. Safe to call from
    /// any thread — the pipeline asks for it at key-down time.
    nonisolated static func frontmostPasteTarget() -> PasteTarget? {
        guard let app = NSWorkspace.shared.frontmostApplication else { return nil }
        return PasteTarget(pid: app.processIdentifier, bundleURL: app.bundleURL)
    }
}

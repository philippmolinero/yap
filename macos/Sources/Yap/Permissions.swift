import AppKit
import ApplicationServices
import AVFoundation
import Foundation

/// The three TCC permissions Yap needs.
enum Permissions {
    enum Kind: String, CaseIterable {
        case microphone
        case inputMonitoring
        case accessibility

        var displayName: String {
            switch self {
            case .microphone: return "Microphone"
            case .inputMonitoring: return "Input Monitoring"
            case .accessibility: return "Accessibility"
            }
        }

        var rationale: String {
            switch self {
            case .microphone: return "Dictation records what you say."
            case .inputMonitoring: return "The trigger key is heard system-wide."
            case .accessibility: return "Cmd+V pastes your text into the focused app."
            }
        }

        var settingsURL: URL {
            switch self {
            case .microphone:
                return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")!
            case .inputMonitoring:
                return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent")!
            case .accessibility:
                return URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")!
            }
        }
    }

    static func isGranted(_ kind: Kind) -> Bool {
        switch kind {
        case .microphone:
            return AVAudioApplication.shared.recordPermission == .granted
        case .inputMonitoring:
            return CGPreflightListenEventAccess()
        case .accessibility:
            return AXIsProcessTrusted()
        }
    }

    /// Ask macOS for a permission. `completion` runs on an arbitrary thread.
    static func request(_ kind: Kind, completion: (@Sendable (Bool) -> Void)? = nil) {
        switch kind {
        case .microphone:
            AVAudioApplication.requestRecordPermission { granted in
                completion?(granted)
            }
        case .inputMonitoring:
            CGRequestListenEventAccess()
            completion?(CGPreflightListenEventAccess())
        case .accessibility:
            // The literal key avoids the concurrency-unsafe kAXTrustedCheckOptionPrompt global.
            let prompt = ["AXTrustedCheckOptionPrompt": true] as CFDictionary
            let granted = AXIsProcessTrustedWithOptions(prompt)
            completion?(granted)
        }
    }

    static func openSettings(for kind: Kind) {
        NSWorkspace.shared.open(kind.settingsURL)
    }
}

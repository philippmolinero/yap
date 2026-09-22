import AppKit
import Foundation

/// Resolves bundled resources across the three ways Yap runs: a signed
/// Yap.app bundle, `swift run` from the package, and the CLI tools.
enum AppResources {
    static func url(_ name: String, extension ext: String) -> URL? {
        if let url = Bundle.main.url(forResource: name, withExtension: ext) {
            return url
        }
        let executable = URL(fileURLWithPath: CommandLine.arguments[0])
            .resolvingSymlinksInPath()
            .deletingLastPathComponent()
        let bundle = executable.appendingPathComponent("Yap_Yap.bundle")
        let candidates = [
            executable.appendingPathComponent("\(name).\(ext)"),
            bundle.appendingPathComponent("\(name).\(ext)"),
            bundle.appendingPathComponent("Contents/Resources/\(name).\(ext)"),
            executable.appendingPathComponent("Yap_Yap.bundle/Contents/\(name).\(ext)"),
        ]
        for candidate in candidates where FileManager.default.fileExists(atPath: candidate.path) {
            return candidate
        }
        return Bundle.module.url(forResource: name, withExtension: ext)
    }
}

/// Subtle audio cues for recording events.
final class SoundFeedback: @unchecked Sendable {
    private let lock = NSLock()
    private var startSound: NSSound?
    private var stopSound: NSSound?
    private var errorSound: NSSound?

    init() {
        let fallback = AppResources.url("ui_click", extension: "wav").flatMap { NSSound(contentsOf: $0, byReference: false) }
        startSound = AppResources.url("record_start", extension: "wav").flatMap { NSSound(contentsOf: $0, byReference: false) } ?? fallback
        stopSound = AppResources.url("record_stop", extension: "wav").flatMap { NSSound(contentsOf: $0, byReference: false) } ?? fallback
        errorSound = NSSound(named: "Basso")
    }

    /// Rising chime — played once the first audio frame arrives.
    func playStart() {
        play(startSound)
    }

    /// Falling chime — recording ended, transcription begins.
    func playStop() {
        play(stopSound)
    }

    func playError() {
        play(errorSound)
    }

    private func play(_ sound: NSSound?) {
        guard let sound else { return }
        DispatchQueue.main.async {
            sound.stop()
            sound.play()
        }
    }
}

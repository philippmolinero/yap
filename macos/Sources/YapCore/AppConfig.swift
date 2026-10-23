import Foundation

public struct HotkeyConfig: Sendable, Equatable {
    /// Virtual keycodes that trigger dictation. 61 = Right Option, 62 = Right Control.
    public var keycodes: [Int]
    /// Two presses within this window switch to hands-free toggle mode.
    public var doubleTapMS: Int

    public init(keycodes: [Int] = [61, 62], doubleTapMS: Int = 300) {
        self.keycodes = keycodes.isEmpty ? [61, 62] : keycodes
        self.doubleTapMS = doubleTapMS
    }

    public static let `default` = HotkeyConfig()
}

public struct TranscriptionConfig: Sendable, Equatable {
    public var model: String
    public var mode: TranscriptionMode
    /// ISO-639-1 hint. Empty keeps automatic detection.
    public var language: String
    public var allowedLanguages: [String]
    public var sampleRate: Int

    public init(
        model: String = "gemini-3.5-transcribe",
        mode: TranscriptionMode = .smart,
        language: String = "",
        allowedLanguages: [String] = ["en", "de"],
        sampleRate: Int = 16_000
    ) {
        self.model = model
        self.mode = mode
        self.language = language
        self.allowedLanguages = allowedLanguages
        self.sampleRate = sampleRate
    }

    /// Streaming model for push-to-talk turns.
    public var liveModel: String {
        model.hasSuffix("-live") ? model : model + "-live"
    }

    public static let `default` = TranscriptionConfig()
}

public struct PasteConfig: Sendable, Equatable {
    /// Delay between writing the clipboard and posting Cmd+V.
    public var delayMS: Int

    public init(delayMS: Int = 50) {
        self.delayMS = max(0, delayMS)
    }

    public var delay: TimeInterval { TimeInterval(delayMS) / 1000 }
}

public struct SilenceConfig: Sendable, Equatable {
    /// Seconds of quiet that auto-stop a recording. Zero disables the feature.
    public var timeout: Double
    /// RMS level below this counts as silence.
    public var threshold: Double

    public init(timeout: Double = 5.0, threshold: Double = 0.008) {
        self.timeout = max(0, timeout)
        self.threshold = threshold
    }
}

public struct AppConfig: Sendable, Equatable {
    public var hotkey: HotkeyConfig
    public var transcription: TranscriptionConfig
    public var paste: PasteConfig
    public var silence: SilenceConfig
    public var vocabulary: [String]

    public init(
        hotkey: HotkeyConfig = .default,
        transcription: TranscriptionConfig = .default,
        paste: PasteConfig = PasteConfig(),
        silence: SilenceConfig = SilenceConfig(),
        vocabulary: [String] = []
    ) {
        self.hotkey = hotkey
        self.transcription = transcription
        self.paste = paste
        self.silence = silence
        self.vocabulary = vocabulary
    }

    public var pasteDelay: TimeInterval { paste.delay }
}

// MARK: - Locations

public extension AppConfig {
    /// `YAP_CONFIG_DIR` overrides the location for tests and isolated runs.
    static let directory: URL = {
        if let override = ProcessInfo.processInfo.environment["YAP_CONFIG_DIR"], !override.isEmpty {
            return URL(fileURLWithPath: override, isDirectory: true)
        }
        return FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/yap", isDirectory: true)
    }()
    static let configURL = directory.appendingPathComponent("config.toml")
    static let vocabularyURL = directory.appendingPathComponent("vocabulary.txt")
    static let secretsURL = directory.appendingPathComponent("secrets.toml")
    static let historyURL = directory.appendingPathComponent("history.json")
    static let metricsURL = directory.appendingPathComponent("pipeline_metrics.jsonl")
    static let failedRecordingURL = directory.appendingPathComponent("last_failed_recording.wav")
    static let lockURL = directory.appendingPathComponent(".yap.lock")
}

// MARK: - Loading and saving

public extension AppConfig {
    /// Load config.toml + vocabulary.txt. Unknown keys and sections are tolerated
    /// so a config shared with older Yap versions keeps working.
    static func load(from directory: URL = AppConfig.directory) -> AppConfig {
        let document = TOMLDocument(text: (try? String(contentsOf: directory.appendingPathComponent("config.toml"), encoding: .utf8)) ?? "")

        let keycodes = document.intArray("keycodes", in: "hotkey")
            ?? document.int("keycode", in: "hotkey").map { [$0] }
            ?? HotkeyConfig.default.keycodes
        let hotkey = HotkeyConfig(
            keycodes: keycodes,
            doubleTapMS: document.int("double_tap_ms", in: "hotkey") ?? HotkeyConfig.default.doubleTapMS
        )

        let rawMode = document.string("mode", in: "transcription") ?? ""
        let transcription = TranscriptionConfig(
            model: document.string("model", in: "transcription") ?? TranscriptionConfig.default.model,
            mode: TranscriptionMode(rawValue: rawMode.lowercased()) ?? .smart,
            language: document.string("language", in: "transcription") ?? "",
            allowedLanguages: document.stringArray("allowed_languages", in: "transcription") ?? ["en", "de"],
            sampleRate: document.int("sample_rate", in: "transcription") ?? 16_000
        )

        let paste = PasteConfig(delayMS: document.int("delay_ms", in: "paste") ?? 50)
        let silence = SilenceConfig(
            timeout: document.double("timeout", in: "silence") ?? 5.0,
            threshold: document.double("threshold", in: "silence") ?? 0.008
        )

        return AppConfig(
            hotkey: hotkey,
            transcription: transcription,
            paste: paste,
            silence: silence,
            vocabulary: loadVocabulary(from: directory)
        )
    }

    /// Write the keys Yap manages, preserving comments and foreign sections.
    func save(in directory: URL = AppConfig.directory) throws {
        let configURL = directory.appendingPathComponent("config.toml")
        var document = TOMLDocument(text: (try? String(contentsOf: configURL, encoding: .utf8)) ?? "")

        document.set(.array(hotkey.keycodes.map { .integer($0) }), forKey: "keycodes", in: "hotkey")
        document.set(.integer(hotkey.doubleTapMS), forKey: "double_tap_ms", in: "hotkey")

        document.set(.string(transcription.model), forKey: "model", in: "transcription")
        document.set(.string(transcription.mode.rawValue), forKey: "mode", in: "transcription")
        document.set(.string(transcription.language), forKey: "language", in: "transcription")
        document.set(.integer(transcription.sampleRate), forKey: "sample_rate", in: "transcription")
        document.set(.array(transcription.allowedLanguages.map { .string($0) }), forKey: "allowed_languages", in: "transcription")

        document.set(.integer(paste.delayMS), forKey: "delay_ms", in: "paste")

        document.set(.double(silence.timeout), forKey: "timeout", in: "silence")
        document.set(.double(silence.threshold), forKey: "threshold", in: "silence")

        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try document.text.write(to: configURL, atomically: true, encoding: .utf8)
    }

    static func loadVocabulary(from directory: URL = AppConfig.directory) -> [String] {
        let url = directory.appendingPathComponent("vocabulary.txt")
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return [] }
        return text
            .split(whereSeparator: \.isNewline)
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    static func saveVocabulary(_ terms: [String], in directory: URL = AppConfig.directory) throws {
        let url = directory.appendingPathComponent("vocabulary.txt")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let body = terms
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
            .joined(separator: "\n")
        try (body + (body.isEmpty ? "" : "\n")).write(to: url, atomically: true, encoding: .utf8)
    }

    /// Seed a fresh config directory from the bundled defaults.
    static func ensureConfigFiles(
        defaultConfigURL: URL?,
        defaultVocabularyURL: URL?,
        in directory: URL = AppConfig.directory
    ) {
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let configURL = directory.appendingPathComponent("config.toml")
        if !FileManager.default.fileExists(atPath: configURL.path), let source = defaultConfigURL {
            try? FileManager.default.copyItem(at: source, to: configURL)
        }
        let vocabularyURL = directory.appendingPathComponent("vocabulary.txt")
        if !FileManager.default.fileExists(atPath: vocabularyURL.path), let source = defaultVocabularyURL {
            try? FileManager.default.copyItem(at: source, to: vocabularyURL)
        }
    }
}

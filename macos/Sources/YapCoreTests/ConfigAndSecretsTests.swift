import Foundation
import YapCore

func configSuite() -> Suite {
    let suite = Suite("App config load and save")

    func makeDirectory() throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-config-tests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        return url
    }

    suite.test("loads defaults when files are missing") {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        let config = AppConfig.load(from: directory)
        try expect(config.hotkey.keycodes == [61, 62])
        try expect(config.hotkey.doubleTapMS == 300)
        try expect(config.transcription.model == "gemini-3.5-transcribe")
        try expect(config.transcription.mode == .smart)
        try expect(config.transcription.language == "")
        try expect(config.transcription.allowedLanguages == ["en", "de"])
        try expect(config.paste.delayMS == 50)
        try expect(config.silence.timeout == 5.0)
        try expect(config.silence.threshold == 0.008)
        try expect(config.vocabulary.isEmpty)
    }

    suite.test("loads values and the legacy single keycode") {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        try """
        [hotkey]
        keycode = 62
        double_tap_ms = 250

        [transcription]
        model = "gemini-3.5-transcribe"
        mode = "verbatim"
        language = "de"
        allowed_languages = ["en", "de", "th"]

        [paste]
        delay_ms = 120

        [silence]
        timeout = 0
        threshold = 0.01
        """.write(to: directory.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)
        try "Claude Code\nYap\n\n".write(to: directory.appendingPathComponent("vocabulary.txt"), atomically: true, encoding: .utf8)

        let config = AppConfig.load(from: directory)
        try expect(config.hotkey.keycodes == [62])
        try expect(config.hotkey.doubleTapMS == 250)
        try expect(config.transcription.mode == .verbatim)
        try expect(config.transcription.language == "de")
        try expect(config.transcription.allowedLanguages == ["en", "de", "th"])
        try expect(config.paste.delayMS == 120)
        try expect(config.silence.timeout == 0)
        try expect(config.vocabulary == ["Claude Code", "Yap"])
    }

    suite.test("save round trip preserves foreign sections") {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        try """
        # my comment
        [hotkey]
        keycodes = [62]

        [cleanup]
        provider = "groq"
        """.write(to: directory.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)

        var config = AppConfig.load(from: directory)
        config.hotkey.keycodes = [61, 62]
        config.transcription.mode = .verbatim
        config.transcription.language = "th"
        config.silence.timeout = 8
        try config.save(in: directory)

        let reloaded = AppConfig.load(from: directory)
        try expect(reloaded.hotkey.keycodes == [61, 62])
        try expect(reloaded.transcription.mode == .verbatim)
        try expect(reloaded.transcription.language == "th")
        try expect(reloaded.silence.timeout == 8)

        let text = try String(contentsOf: directory.appendingPathComponent("config.toml"), encoding: .utf8)
        try expect(text.contains("# my comment"), "comments survive a save")
        try expect(text.contains("[cleanup]"), "foreign sections survive a save")
        try expect(text.contains("provider = \"groq\""))
    }

    suite.test("seeds default files only when missing") {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }
        let source = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: source) }

        let defaultConfig = source.appendingPathComponent("default.toml")
        let defaultVocabulary = source.appendingPathComponent("vocabulary.txt")
        try "[silence]\ntimeout = 9\n".write(to: defaultConfig, atomically: true, encoding: .utf8)
        try "Term\n".write(to: defaultVocabulary, atomically: true, encoding: .utf8)

        AppConfig.ensureConfigFiles(
            defaultConfigURL: defaultConfig,
            defaultVocabularyURL: defaultVocabulary,
            in: directory
        )
        try expect(AppConfig.load(from: directory).silence.timeout == 9)
        try expect(AppConfig.loadVocabulary(from: directory) == ["Term"])

        try "[silence]\ntimeout = 3\n".write(to: directory.appendingPathComponent("config.toml"), atomically: true, encoding: .utf8)
        AppConfig.ensureConfigFiles(
            defaultConfigURL: defaultConfig,
            defaultVocabularyURL: defaultVocabulary,
            in: directory
        )
        try expect(AppConfig.load(from: directory).silence.timeout == 3, "a second run must not overwrite user files")
    }

    suite.test("vocabulary save is normalized") {
        let directory = try makeDirectory()
        defer { try? FileManager.default.removeItem(at: directory) }

        try AppConfig.saveVocabulary([" Claude Code ", "", "Yap"], in: directory)
        try expect(AppConfig.loadVocabulary(from: directory) == ["Claude Code", "Yap"])
    }

    suite.test("live model is derived from the unary model") {
        let config = GeminiConfiguration(apiKey: "k", model: "gemini-3.5-transcribe")
        try expect(config.liveModel == "gemini-3.5-transcribe-live")
        try expect(config.unaryModel == "gemini-3.5-transcribe")

        let backwards = GeminiConfiguration(apiKey: "k", model: "gemini-3.5-transcribe-live")
        try expect(backwards.liveModel == "gemini-3.5-transcribe-live")
        try expect(backwards.unaryModel == "gemini-3.5-transcribe")
    }

    return suite
}

func secretsSuite() -> Suite {
    let suite = Suite("Gemini key storage and migration")

    func makeSecretsFile(_ text: String) throws -> URL {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-secrets-\(UUID().uuidString).toml")
        try text.write(to: url, atomically: true, encoding: .utf8)
        return url
    }

    suite.test("reads the legacy google key") {
        let url = try makeSecretsFile("""
        [api_keys]
        mistral = "m-key"
        groq = "g-key"
        google = "AIza-legacy"

        [preferences]
        cleanup_provider = "groq"
        """)
        defer { try? FileManager.default.removeItem(at: url) }

        try expect(LegacySecrets.geminiKey(inTomlAt: url) == "AIza-legacy")
    }

    suite.test("missing file yields no key") {
        let url = URL(fileURLWithPath: "/nonexistent/secrets.toml")
        try expect(LegacySecrets.geminiKey(inTomlAt: url) == nil)
    }

    suite.test("migrates the legacy key into an empty store") {
        let url = try makeSecretsFile("[api_keys]\ngoogle = \"AIza-legacy\"\n")
        defer { try? FileManager.default.removeItem(at: url) }
        let store = MemoryGeminiKeyStore()

        let outcome = LegacySecrets.migrateGeminiKey(into: store, secretsURL: url)
        try expect(outcome == .migrated)
        try expect(store.load() == "AIza-legacy")
        try expect(LegacySecrets.migrateGeminiKey(into: store, secretsURL: url) == .alreadyStored)
    }

    suite.test("keeps an existing store key") {
        let url = try makeSecretsFile("[api_keys]\ngoogle = \"AIza-legacy\"\n")
        defer { try? FileManager.default.removeItem(at: url) }
        let store = MemoryGeminiKeyStore(key: "AIza-modern")

        let outcome = LegacySecrets.migrateGeminiKey(into: store, secretsURL: url)
        try expect(outcome == .alreadyStored)
        try expect(store.load() == "AIza-modern")
    }

    suite.test("nothing to migrate without a legacy key") {
        let url = try makeSecretsFile("[api_keys]\ngroq = \"g-key\"\n")
        defer { try? FileManager.default.removeItem(at: url) }
        let store = MemoryGeminiKeyStore()

        try expect(LegacySecrets.migrateGeminiKey(into: store, secretsURL: url) == .nothingToMigrate)
        try expect(store.load() == nil)
    }

    suite.test("resolver prefers store, then legacy, then environment") {
        let url = try makeSecretsFile("[api_keys]\ngoogle = \"AIza-legacy\"\n")
        defer { try? FileManager.default.removeItem(at: url) }

        let withStore = MemoryGeminiKeyStore(key: "AIza-modern")
        try expect(GeminiKeyResolver.resolve(
            store: withStore,
            secretsURL: url,
            environment: ["GEMINI_API_KEY": "env-key"]
        ) == "AIza-modern")

        let empty = MemoryGeminiKeyStore()
        try expect(GeminiKeyResolver.resolve(
            store: empty,
            secretsURL: url,
            environment: ["GEMINI_API_KEY": "env-key"]
        ) == "AIza-legacy")
        try expect(empty.load() == "AIza-legacy", "the legacy key migrates during resolve")

        let missing = MemoryGeminiKeyStore()
        try expect(GeminiKeyResolver.resolve(
            store: missing,
            secretsURL: URL(fileURLWithPath: "/nonexistent/secrets.toml"),
            environment: ["GOOGLE_API_KEY": "env-key"]
        ) == "env-key")

        try expect(GeminiKeyResolver.resolve(
            store: MemoryGeminiKeyStore(),
            secretsURL: URL(fileURLWithPath: "/nonexistent/secrets.toml"),
            environment: [:]
        ) == "")
    }

    suite.test("memory store round trip") {
        let store = MemoryGeminiKeyStore()
        try expect(store.load() == nil)
        try store.save("key-1")
        try expect(store.load() == "key-1")
        try store.save("key-2")
        try expect(store.load() == "key-2")
        try store.delete()
        try expect(store.load() == nil)
    }

    suite.test("keychain store round trip") {
        // A test-only service keeps the user's real key untouched. Keychain
        // access can be unavailable in restricted environments; skip then.
        let store = KeychainGeminiKeyStore(service: "com.yap.dictation.tests-\(UUID().uuidString)")
        guard (try? store.save("keychain-value")) != nil else { return }
        try expect(store.load() == "keychain-value")
        try store.delete()
        try expect(store.load() == nil)
    }

    suite.test("a blocking keychain read never blocks resolution") {
        // Simulates the authorization dialog: the read never returns in time.
        let store = HangingKeyStore(delay: 5)
        let started = Date()
        let probe = GeminiKeyResolver.probe(store, timeout: 0.2)
        try expect(Date().timeIntervalSince(started) < 2, "probe must give up quickly")
        try expect(probe == .blocked)
    }

    suite.test("resolve falls back while the keychain is blocked and leaves the item alone") {
        let url = try makeSecretsFile("[api_keys]\ngoogle = \"AIza-legacy\"\n")
        defer { try? FileManager.default.removeItem(at: url) }
        let store = HangingKeyStore(delay: 5)

        let resolved = GeminiKeyResolver.resolveDetailed(
            store: store,
            secretsURL: url,
            environment: ["GEMINI_API_KEY": "env-key"]
        )
        try expect(resolved.key == "AIza-legacy")
        try expect(resolved.source == .legacySecrets)
        try expect(store.saveCount == 0, "a blocked read must not trigger an overwrite")
    }

    suite.test("resolve reports its source") {
        let url = try makeSecretsFile("[api_keys]\ngoogle = \"AIza-legacy\"\n")
        defer { try? FileManager.default.removeItem(at: url) }

        let fromStore = GeminiKeyResolver.resolveDetailed(
            store: MemoryGeminiKeyStore(key: "k1"),
            secretsURL: url,
            environment: [:]
        )
        try expect(fromStore.source == .keychain)

        let fromEnvironment = GeminiKeyResolver.resolveDetailed(
            store: MemoryGeminiKeyStore(),
            secretsURL: URL(fileURLWithPath: "/nonexistent/secrets.toml"),
            environment: ["GEMINI_API_KEY": "env-key"]
        )
        try expect(fromEnvironment.source == .environment)

        let none = GeminiKeyResolver.resolveDetailed(
            store: MemoryGeminiKeyStore(),
            secretsURL: URL(fileURLWithPath: "/nonexistent/secrets.toml"),
            environment: [:]
        )
        try expect(none.source == .none)
    }

    return suite
}

/// A key store whose read hangs, like a keychain waiting for authorization.
private final class HangingKeyStore: GeminiKeyStoring, @unchecked Sendable {
    private let delay: TimeInterval
    private let lock = NSLock()
    private(set) var saveCount = 0

    init(delay: TimeInterval) {
        self.delay = delay
    }

    func load() -> String? {
        Thread.sleep(forTimeInterval: delay)
        return nil
    }

    func save(_ key: String) throws {
        lock.withLock { saveCount += 1 }
    }

    func delete() throws {}
}

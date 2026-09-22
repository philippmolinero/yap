import Foundation
import Security

public enum KeychainError: Error, Equatable, Sendable {
    case unhandled(OSStatus)
}

/// Storage for the Gemini API key.
public protocol GeminiKeyStoring: Sendable {
    func load() -> String?
    func save(_ key: String) throws
    func delete() throws
}

/// Keeps the Gemini API key in the user's Keychain instead of a plaintext file.
public struct KeychainGeminiKeyStore: GeminiKeyStoring {
    public let service: String
    public let account: String

    public init(service: String = "com.yap.dictation.gemini-key", account: String = "gemini") {
        self.service = service
        self.account = account
    }

    public func load() -> String? {
        var item: CFTypeRef?
        let status = SecItemCopyMatching(baseQuery() as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    public func save(_ key: String) throws {
        guard let data = key.data(using: .utf8) else { return }
        let add = baseQuery().merging([
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]) { _, new in new }

        let updateStatus = SecItemUpdate(baseQuery() as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if updateStatus == errSecSuccess { return }
        if updateStatus != errSecItemNotFound { throw KeychainError.unhandled(updateStatus) }

        let addStatus = SecItemAdd(add as CFDictionary, nil)
        guard addStatus == errSecSuccess else { throw KeychainError.unhandled(addStatus) }
    }

    public func delete() throws {
        let status = SecItemDelete(baseQuery() as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainError.unhandled(status)
        }
    }

    private func baseQuery() -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
    }
}

/// An in-memory store for previews and tests.
public struct MemoryGeminiKeyStore: GeminiKeyStoring {
    private let box: LockedBox<String?>

    public init(key: String? = nil) {
        self.box = LockedBox(key)
    }

    public func load() -> String? { box.value }
    public func save(_ key: String) throws { box.value = key }
    public func delete() throws { box.value = nil }
}

/// One-time import of the plaintext key older Yap versions kept in secrets.toml.
public enum LegacySecrets {
    public enum MigrationOutcome: Equatable, Sendable {
        case migrated
        case alreadyStored
        case nothingToMigrate
    }

    public static func geminiKey(inTomlAt url: URL) -> String? {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        // secrets.toml keeps a flat [api_keys] table; read only the google entry.
        let document = TOMLDocument(text: text)
        let key = document.string("google", in: "api_keys")?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (key?.isEmpty == false) ? key : nil
    }

    @discardableResult
    public static func migrateGeminiKey(
        into store: any GeminiKeyStoring,
        secretsURL: URL = AppConfig.secretsURL
    ) -> MigrationOutcome {
        if let existing = store.load(), !existing.isEmpty {
            return .alreadyStored
        }
        guard let legacy = geminiKey(inTomlAt: secretsURL), !legacy.isEmpty else {
            return .nothingToMigrate
        }
        do {
            try store.save(legacy)
            YapLog.info("Migrated Gemini API key from secrets.toml into the Keychain")
            return .migrated
        } catch {
            YapLog.error("Keychain migration failed: \(error)")
            return .nothingToMigrate
        }
    }
}

/// Resolves the Gemini API key: Keychain first, then legacy secrets.toml, then
/// environment variables for development runs.
///
/// Keychain reads can block on a system authorization dialog when a freshly
/// built binary first touches an existing item. Yap never hangs on that dialog:
/// the read gets a short watchdog and the fallbacks cover the run.
public enum GeminiKeyResolver {
    public enum Source: String, Sendable {
        case keychain
        case legacySecrets = "legacy-secrets"
        case environment
        case none
    }

    public enum Probe: Sendable, Equatable {
        case value(String)
        case empty
        case blocked
    }

    /// Read the keychain store without risking a hang on the authorization dialog.
    public static func probe(_ store: any GeminiKeyStoring, timeout: TimeInterval = 3.0) -> Probe {
        let semaphore = DispatchSemaphore(value: 0)
        let box = LockedBox<Probe>(.blocked)
        DispatchQueue.global(qos: .utility).async {
            let loaded = store.load()
            box.value = loaded.map { $0.isEmpty ? Probe.empty : Probe.value($0) } ?? .empty
            semaphore.signal()
        }
        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            YapLog.warning("Keychain read is waiting for authorization — continuing without it")
            return .blocked
        }
        return box.value
    }

    public static func resolve(
        store: any GeminiKeyStoring,
        secretsURL: URL = AppConfig.secretsURL,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> String {
        resolveDetailed(store: store, secretsURL: secretsURL, environment: environment).key
    }

    public static func resolveDetailed(
        store: any GeminiKeyStoring,
        secretsURL: URL = AppConfig.secretsURL,
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> (key: String, source: Source) {
        let legacy = LegacySecrets.geminiKey(inTomlAt: secretsURL)

        switch probe(store) {
        case .value(let key):
            return (key, .keychain)
        case .empty:
            // Write once so future runs use the Keychain. Adds are prompt-free.
            if let legacy, !legacy.isEmpty {
                try? store.save(legacy)
                YapLog.info("Migrated Gemini API key from secrets.toml into the Keychain")
                return (legacy, .legacySecrets)
            }
        case .blocked:
            // A dialog is up. Leave the item alone and cover this run instead.
            if let legacy, !legacy.isEmpty {
                return (legacy, .legacySecrets)
            }
        }

        if let key = environment["GEMINI_API_KEY"], !key.isEmpty {
            return (key, .environment)
        }
        if let key = environment["GOOGLE_API_KEY"], !key.isEmpty {
            return (key, .environment)
        }
        return ("", .none)
    }
}

/// Tiny thread-safe box for the memory store.
final class LockedBox<Value>: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: Value

    init(_ value: Value) {
        self._value = value
    }

    var value: Value {
        get { lock.withLock { _value } }
        set { lock.withLock { _value = newValue } }
    }
}

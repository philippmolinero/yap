import Foundation

private let languageAliases: [String: String] = [
    "english": "en",
    "german": "de",
    "deutsch": "de",
    "thai": "th",
    "japanese": "ja",
    "chinese": "zh",
    "korean": "ko",
]

private let bcp47Map: [String: String] = [
    "en": "en",
    "de": "de-DE",
    "th": "th-TH",
]

/// Normalize a user-facing language hint to a bare ISO-639-1 code.
public func normalizeLanguage(_ language: String) -> String {
    let normalized = language
        .trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "_", with: "-")
    if normalized.isEmpty { return "" }
    if let alias = languageAliases[normalized] { return alias }
    if let dash = normalized.firstIndex(of: "-") {
        return String(normalized[..<dash])
    }
    return normalized
}

/// Map a Yap language setting to the BCP-47 hint Gemini expects.
public func bcp47Code(for language: String) -> String {
    let normalized = normalizeLanguage(language)
    return bcp47Map[normalized] ?? normalized
}

/// Language hints for a Gemini request: the explicit hint when set, otherwise
/// the allowed-language list, otherwise automatic detection.
public func geminiLanguageCodes(language: String, allowedLanguages: [String] = []) -> [String] {
    if !language.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        let normalized = normalizeLanguage(language)
        return normalized.isEmpty ? ["auto"] : [bcp47Map[normalized] ?? normalized]
    }
    let codes = allowedLanguages
        .map(normalizeLanguage)
        .filter { !$0.isEmpty }
        .map { bcp47Map[$0] ?? $0 }
    return codes.isEmpty ? ["auto"] : codes
}

import Foundation

/// Tokens borrowed from the focused field for a single dictation turn.
///
/// Screen text is not stored. Callers pass the extracted tokens in front of
/// the saved vocabulary and drop them when the turn ends.
public enum TurnContext {
    /// How many screen tokens may join one turn. The saved list still has room
    /// under Gemini's 100-term cap.
    public static let termLimit = 40
    /// Characters read from a field. Longer text keeps the head and the tail.
    public static let scanLimit = 8_000
    public static let maxTermLength = 80

    /// Whether the focused element is a password field and its text must not be read.
    ///
    /// Password fields report role `AXTextField` with subrole `AXSecureTextField`
    /// (`kAXSecureTextFieldSubrole`). There is no `kAXSecureTextFieldRole`. A role
    /// of `AXSecureTextField` is also treated as secure.
    public static func isSecureField(role: String?, subrole: String?) -> Bool {
        role == "AXSecureTextField" || subrole == "AXSecureTextField"
    }

    /// Names, CamelCase, snake_case, and file names, in appearance order.
    /// Personal names come only from the window title, so a chat draft cannot
    /// fill the list. Exact duplicates are dropped.
    public static func terms(focusedText: String, windowTitle: String) -> [String] {
        let pieces = scan(bounded(focusedText), includeNames: false)
            + scan(bounded(windowTitle), includeNames: true)
        var result: [String] = []
        var seen = Set<String>()
        for piece in pieces {
            guard piece.count <= maxTermLength else { continue }
            guard seen.insert(piece).inserted else { continue }
            result.append(piece)
            if result.count == termLimit { break }
        }
        return result
    }

    /// Context tokens first, then the saved list. Blank entries and exact
    /// duplicates are dropped. The result is capped at `limit`.
    /// Screen tokens longer than `maxTermLength` are dropped. Saved phrases
    /// are not, so a long line in vocabulary.txt still reaches Gemini.
    public static func merge(context: [String], saved: [String], limit: Int = 100) -> [String] {
        guard limit > 0 else { return [] }
        var result: [String] = []
        var seen = Set<String>()
        func add(_ raw: String, limitLength: Bool) {
            guard result.count < limit else { return }
            let term = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !term.isEmpty else { return }
            if limitLength, term.count > maxTermLength { return }
            guard seen.insert(term).inserted else { return }
            result.append(term)
        }
        for term in context { add(term, limitLength: true) }
        for term in saved { add(term, limitLength: false) }
        return result
    }

    // MARK: - Scanning

    private static func bounded(_ text: String) -> String {
        guard text.count > scanLimit else { return text }
        let headCount = scanLimit / 2
        let tailCount = scanLimit - headCount
        return String(text.prefix(headCount)) + "\n" + String(text.suffix(tailCount))
    }

    private static func scan(_ text: String, includeNames: Bool) -> [String] {
        var found: [String] = []
        var index = text.startIndex
        while index < text.endIndex {
            if isTokenStart(text, index) {
                if let file = matchFile(text, from: index) {
                    found.append(file.term)
                    index = file.end
                    continue
                }
                if let identifier = matchIdentifier(text, from: index) {
                    found.append(identifier.term)
                    index = identifier.end
                    continue
                }
                if includeNames, let name = matchName(text, from: index) {
                    found.append(name.term)
                    index = name.end
                    continue
                }
            }
            index = text.index(after: index)
        }
        return found
    }

    /// A token starts at a letter or digit that is not continuing an identifier.
    private static func isTokenStart(_ text: String, _ index: String.Index) -> Bool {
        guard index < text.endIndex else { return false }
        let character = text[index]
        guard character.isLetter || character.isNumber else { return false }
        guard index > text.startIndex else { return true }
        let previous = text[text.index(before: index)]
        return !(previous.isLetter || previous.isNumber || previous == "_")
    }

    private static func matchFile(_ text: String, from start: String.Index) -> (term: String, end: String.Index)? {
        let (run, end, tooLong) = readRun(text, from: start) { character in
            character.isLetter || character.isNumber || character == "." || character == "_" || character == "-"
        }
        guard !tooLong, let term = fileTerm(run) else { return nil }
        return (term, end)
    }

    private static func fileTerm(_ run: String) -> String? {
        let lowercased = run.lowercased()
        for suffix in extensionSuffixes where lowercased.hasSuffix(suffix) && run.count > suffix.count {
            return run
        }
        return nil
    }

    /// Longest extensions first so `file.mm` is not classified as `file.m`.
    private static let extensionSuffixes: [String] = [
        "swift", "tsx", "jsx", "toml", "json", "yaml", "html", "cpp", "css",
        "wav", "txt", "yml", "md", "py", "rb", "go", "rs", "cc", "mm", "js",
        "ts", "h", "m",
    ].map { "." + $0 }.sorted { $0.count > $1.count }

    private static func matchIdentifier(_ text: String, from start: String.Index) -> (term: String, end: String.Index)? {
        let (run, end, tooLong) = readRun(text, from: start) { character in
            character.isLetter || character.isNumber || character == "_"
        }
        guard !tooLong, run.count >= 3, isSnake(run) || isCamel(run) else { return nil }
        return (run, end)
    }

    /// `[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+`
    private static func isSnake(_ run: String) -> Bool {
        guard let first = run.first, first.isLetter else { return false }
        var sawUnderscore = false
        var charactersAfterUnderscore = 0
        for character in run {
            if character == "_" {
                sawUnderscore = true
                continue
            }
            guard character.isLetter || character.isNumber else { return false }
            if sawUnderscore { charactersAfterUnderscore += 1 }
        }
        return sawUnderscore && charactersAfterUnderscore > 0
    }

    /// `[A-Za-z][a-z0-9]*[A-Z][A-Za-z0-9]*`
    private static func isCamel(_ run: String) -> Bool {
        guard let first = run.first, first.isLetter else { return false }
        var sawHump = false
        var index = run.index(after: run.startIndex)
        while index < run.endIndex {
            let character = run[index]
            if !sawHump {
                if character.isLowercase || character.isNumber {
                    index = run.index(after: index)
                    continue
                }
                guard character.isUppercase else { return false }
                sawHump = true
            } else if !(character.isLetter || character.isNumber) {
                return false
            }
            index = run.index(after: index)
        }
        return sawHump
    }

    /// A capitalized name from a window title, including `O'Brien` and `Mary-Jane`.
    private static func matchName(_ text: String, from start: String.Index) -> (term: String, end: String.Index)? {
        guard text[start].isLetter, text[start].isUppercase else { return nil }
        var end = text.index(after: start)
        while end < text.endIndex, text[end].isLowercase {
            end = text.index(after: end)
        }
        while end < text.endIndex, isNameSeparator(text[end]) {
            let capital = text.index(after: end)
            guard capital < text.endIndex, text[capital].isLetter, text[capital].isUppercase else { break }
            var cursor = text.index(after: capital)
            var lowercaseCount = 0
            while cursor < text.endIndex, text[cursor].isLowercase {
                cursor = text.index(after: cursor)
                lowercaseCount += 1
            }
            guard lowercaseCount >= 1 else { break }
            end = cursor
        }
        if end < text.endIndex {
            let next = text[end]
            if next.isLetter || next.isNumber || next == "_" { return nil }
        }
        let term = String(text[start..<end])
        guard term.count >= 3, term.count <= 40 else { return nil }
        guard !stopwords.contains(term.lowercased()) else { return nil }
        return (term, end)
    }

    private static func isNameSeparator(_ character: Character) -> Bool {
        character == "'" || character == "’" || character == "-"
    }

    private static func readRun(
        _ text: String,
        from start: String.Index,
        allowed: (Character) -> Bool
    ) -> (run: String, end: String.Index, tooLong: Bool) {
        var end = start
        var count = 0
        while end < text.endIndex, allowed(text[end]) {
            if count == maxTermLength {
                while end < text.endIndex, allowed(text[end]) {
                    end = text.index(after: end)
                }
                return ("", end, true)
            }
            end = text.index(after: end)
            count += 1
        }
        return (String(text[start..<end]), end, false)
    }

    /// Function words, weekdays, and generic title words. Real names such as
    /// Geoff are not in this set. Comparison is case-insensitive.
    private static let stopwords: Set<String> = [
        "the", "and", "for", "with", "from", "this", "that", "not", "but", "you",
        "are", "was", "has", "had", "his", "her", "its", "our", "who", "how",
        "why", "what", "when", "where", "which", "will", "can", "may", "all",
        "any", "one", "new", "open", "untitled", "window", "document", "mail",
        "inbox", "messages", "chrome", "safari", "firefox", "cursor", "terminal",
        "notes", "finder", "preview", "slack", "zoom", "calendar", "settings",
        "preferences", "search", "file", "edit", "view", "help", "code", "text",
        "draft", "sent", "fwd", "app", "tab", "general",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag",
        "der", "die", "das", "und", "oder", "aber", "mit", "von", "für", "fur",
        "den", "dem", "ein", "eine", "einer", "eines", "nicht", "auch", "auf",
        "ist", "sind", "war", "hat", "ich", "sie", "wir", "ihr", "uns", "zum",
        "zur", "nach", "über", "uber", "bei", "aus", "nur", "noch", "schon",
        "hier", "dort", "heute", "gestern", "morgen",
    ]
}

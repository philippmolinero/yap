import Foundation

/// The TOML subset Yap's config files use: tables, scalar values, and flat arrays.
/// The document keeps its original text so edits preserve comments and foreign keys.
public enum TOMLValue: Equatable, Sendable {
    case string(String)
    case integer(Int)
    case double(Double)
    case bool(Bool)
    case array([TOMLValue])

    public var stringValue: String? {
        if case .string(let value) = self { return value }
        return nil
    }

    public var intValue: Int? {
        if case .integer(let value) = self { return value }
        return nil
    }

    public var doubleValue: Double? {
        switch self {
        case .double(let value): return value
        case .integer(let value): return Double(value)
        default: return nil
        }
    }

    public var boolValue: Bool? {
        if case .bool(let value) = self { return value }
        return nil
    }

    public var stringArray: [String]? {
        guard case .array(let items) = self else { return nil }
        return items.compactMap(\.stringValue)
    }

    public var intArray: [Int]? {
        guard case .array(let items) = self else { return nil }
        return items.compactMap(\.intValue)
    }

    /// Render the value the way it is written back into a document.
    public var serialized: String {
        switch self {
        case .string(let value):
            return "\"\(Self.escape(value))\""
        case .integer(let value):
            return String(value)
        case .double(let value):
            return String(value)
        case .bool(let value):
            return value ? "true" : "false"
        case .array(let items):
            return "[" + items.map(\.serialized).joined(separator: ", ") + "]"
        }
    }

    static func escape(_ value: String) -> String {
        value
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "\"", with: "\\\"")
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
            .replacingOccurrences(of: "\t", with: "\\t")
    }
}

public struct TOMLDocument: Equatable, Sendable {
    public private(set) var text: String

    public init(text: String = "") {
        self.text = text
    }

    public func value(_ key: String, in section: String) -> TOMLValue? {
        Self.parse(text)[section]?[key]
    }

    public func string(_ key: String, in section: String) -> String? {
        value(key, in: section)?.stringValue
    }

    public func int(_ key: String, in section: String) -> Int? {
        value(key, in: section)?.intValue
    }

    public func double(_ key: String, in section: String) -> Double? {
        value(key, in: section)?.doubleValue
    }

    public func bool(_ key: String, in section: String) -> Bool? {
        value(key, in: section)?.boolValue
    }

    public func stringArray(_ key: String, in section: String) -> [String]? {
        value(key, in: section)?.stringArray
    }

    public func intArray(_ key: String, in section: String) -> [Int]? {
        value(key, in: section)?.intArray
    }

    /// Insert or replace one key while keeping every other line (comments included) intact.
    public mutating func set(_ value: TOMLValue, forKey key: String, in section: String) {
        var lines = text.components(separatedBy: "\n")
        let replacement = "\(key) = \(value.serialized)"

        var currentSection = ""
        var sectionHeaderIndex: Int?
        var insertionIndex: Int?
        var existingKeyIndex: Int?

        for (index, line) in lines.enumerated() {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("["), let close = trimmed.firstIndex(of: "]") {
                if sectionHeaderIndex == nil, currentSection == section {
                    // Leaving the target section without finding the key: insert after its header.
                    insertionIndex = (sectionHeaderIndex ?? 0) + 1
                }
                currentSection = String(trimmed[trimmed.index(after: trimmed.startIndex)..<close])
                    .trimmingCharacters(in: .whitespaces)
                if currentSection == section, sectionHeaderIndex == nil {
                    sectionHeaderIndex = index
                    insertionIndex = index + 1
                }
                continue
            }
            guard currentSection == section, let parsedKey = Self.keyName(ofLine: trimmed) else { continue }
            if parsedKey == key {
                existingKeyIndex = index
                break
            }
        }

        if let existingKeyIndex {
            let indent = String(lines[existingKeyIndex].prefix(while: { $0 == " " || $0 == "\t" }))
            lines[existingKeyIndex] = indent + replacement
            text = lines.joined(separator: "\n")
            return
        }

        if let insertionIndex {
            lines.insert(replacement, at: min(insertionIndex, lines.count))
            text = lines.joined(separator: "\n")
            return
        }

        // Section missing entirely (or root section never seen): append a clean block.
        var block: [String] = []
        if !text.isEmpty, !text.hasSuffix("\n") { block.append("") }
        if !text.isEmpty { block.append("") }
        if !section.isEmpty {
            block.append("[\(section)]")
        }
        block.append(replacement)
        text = lines.joined(separator: "\n") + block.map { "\n" + $0 }.joined()
    }

    // MARK: - Parsing

    static func parse(_ text: String) -> [String: [String: TOMLValue]] {
        var result: [String: [String: TOMLValue]] = [:]
        var section = ""

        for line in text.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.isEmpty || trimmed.hasPrefix("#") { continue }
            if trimmed.hasPrefix("["), let close = trimmed.firstIndex(of: "]") {
                section = String(trimmed[trimmed.index(after: trimmed.startIndex)..<close])
                    .trimmingCharacters(in: .whitespaces)
                continue
            }
            guard let key = keyName(ofLine: trimmed) else { continue }
            let equals = trimmed[trimmed.range(of: "=")!.lowerBound...]
            let rawValue = stripComment(String(equals.dropFirst())).trimmingCharacters(in: .whitespaces)
            guard let value = parseValue(rawValue) else { continue }
            result[section, default: [:]][key] = value
        }
        return result
    }

    /// Key name of a `key = value` line, or nil when the line holds no assignment.
    static func keyName(ofLine line: String) -> String? {
        var inDouble = false
        var inSingle = false
        var index = line.startIndex
        while index < line.endIndex {
            let character = line[index]
            if character == "\"" && !inSingle { inDouble.toggle() }
            if character == "'" && !inDouble { inSingle.toggle() }
            if character == "=", !inDouble, !inSingle {
                let rawKey = String(line[line.startIndex..<index])
                    .trimmingCharacters(in: .whitespaces)
                return rawKey.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            }
            index = line.index(after: index)
        }
        return nil
    }

    static func stripComment(_ value: String) -> String {
        var inDouble = false
        var inSingle = false
        var index = value.startIndex
        while index < value.endIndex {
            let character = value[index]
            if character == "\"" && !inSingle { inDouble.toggle() }
            if character == "'" && !inDouble { inSingle.toggle() }
            if character == "#", !inDouble, !inSingle {
                return String(value[value.startIndex..<index])
            }
            index = line_next(value, index)
        }
        return value
    }

    private static func line_next(_ value: String, _ index: String.Index) -> String.Index {
        value.index(after: index)
    }

    static func parseValue(_ raw: String) -> TOMLValue? {
        let value = raw.trimmingCharacters(in: .whitespaces)
        guard !value.isEmpty else { return nil }

        if value.hasPrefix("\"") {
            return parseBasicString(value).map { .string($0) }
        }
        if value.hasPrefix("'") {
            guard value.count >= 2, value.hasSuffix("'") else { return nil }
            let inner = value.dropFirst().dropLast()
            return .string(String(inner))
        }
        if value.hasPrefix("["), value.hasSuffix("]") {
            let inner = String(value.dropFirst().dropLast())
            let parts = splitArrayElements(inner)
            var items: [TOMLValue] = []
            for part in parts {
                let trimmed = part.trimmingCharacters(in: .whitespaces)
                if trimmed.isEmpty { continue }
                guard let item = parseValue(trimmed) else { return nil }
                items.append(item)
            }
            return .array(items)
        }
        if value == "true" { return .bool(true) }
        if value == "false" { return .bool(false) }
        if let integer = Int(value) { return .integer(integer) }
        if let double = Double(value) { return .double(double) }
        return nil
    }

    private static func parseBasicString(_ value: String) -> String? {
        guard value.hasPrefix("\""), value.hasSuffix("\""), value.count >= 2 else { return nil }
        var output = ""
        var index = value.index(after: value.startIndex)
        let end = value.index(before: value.endIndex)
        while index < end {
            let character = value[index]
            if character == "\\" {
                let next = value.index(after: index)
                guard next < end else { return nil }
                switch value[next] {
                case "n": output.append("\n")
                case "r": output.append("\r")
                case "t": output.append("\t")
                case "\"": output.append("\"")
                case "\\": output.append("\\")
                default: output.append(value[next])
                }
                index = value.index(after: next)
                continue
            }
            output.append(character)
            index = value.index(after: index)
        }
        return output
    }

    private static func splitArrayElements(_ body: String) -> [String] {
        var parts: [String] = []
        var current = ""
        var depth = 0
        var inDouble = false
        var inSingle = false
        for character in body {
            switch character {
            case "\"" where !inSingle: inDouble.toggle(); current.append(character)
            case "'" where !inDouble: inSingle.toggle(); current.append(character)
            case "[" where !inDouble && !inSingle: depth += 1; current.append(character)
            case "]" where !inDouble && !inSingle: depth -= 1; current.append(character)
            case "," where !inDouble && !inSingle && depth == 0:
                parts.append(current)
                current = ""
            default:
                current.append(character)
            }
        }
        parts.append(current)
        return parts
    }
}

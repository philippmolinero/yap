import Foundation

/// Length-prefixed messages for the iPhone mic. PCM is 16 kHz mono little-endian
/// int16, one capture buffer per message, with no codec and no jitter buffer.
public enum PhoneLink {
    public static let serviceType = "_yap._tcp"
    public static let sampleRate = 16_000
    public static let maxPayload = 64 * 1024

    public enum Message: Equatable, Sendable {
        case hello(pin: String, deviceName: String)
        case ready
        case rejected
        case audio(Data)
        case stop
        /// Mac hotkey went down. The phone starts forwarding the mic.
        case capture
        /// Mac hotkey went up. The phone flushes and sends `stop`.
        case release
    }

    public enum Failure: Error, Equatable {
        case oversized
        case malformed
    }

    public static func encode(_ message: Message) -> Data {
        let kind: UInt8
        let payload: Data
        switch message {
        case .hello(let pin, let deviceName):
            kind = 1
            payload = Data((pin + "\n" + sanitize(deviceName)).utf8)
        case .ready:
            kind = 2
            payload = Data()
        case .rejected:
            kind = 3
            payload = Data()
        case .audio(let pcm):
            kind = 4
            payload = pcm
        case .stop:
            kind = 5
            payload = Data()
        case .capture:
            kind = 6
            payload = Data()
        case .release:
            kind = 7
            payload = Data()
        }
        var data = Data(capacity: 5 + payload.count)
        data.append(kind)
        appendUInt32(UInt32(payload.count), to: &data)
        data.append(payload)
        return data
    }

    /// Streams bytes into messages. One TCP read is not one message.
    public struct Decoder {
        private var buffer = Data()
        private var offset = 0

        public init() {}

        public mutating func append(_ chunk: Data) throws -> [Message] {
            guard !chunk.isEmpty else { return [] }
            buffer.append(chunk)
            var messages: [Message] = []
            while buffer.count - offset >= 5 {
                let start = buffer.startIndex + offset
                let kind = buffer[start]
                let length = Int(readUInt32(buffer, at: start + 1))
                if length > maxPayload {
                    buffer.removeAll()
                    offset = 0
                    throw Failure.oversized
                }
                let total = 5 + length
                if buffer.count - offset < total { break }
                let payloadStart = start + 5
                let payload = buffer.subdata(in: payloadStart..<(payloadStart + length))
                offset += total
                messages.append(try message(kind: kind, payload: payload))
            }
            if offset > 0, offset == buffer.count || offset > maxPayload {
                buffer.removeFirst(offset)
                offset = 0
            }
            return messages
        }
    }

    private static func message(kind: UInt8, payload: Data) throws -> Message {
        switch kind {
        case 1:
            guard let text = String(data: payload, encoding: .utf8),
                  let newline = text.firstIndex(of: "\n") else { throw Failure.malformed }
            let pin = String(text[..<newline])
            guard (4...8).contains(pin.count), pin.allSatisfy(\.isNumber) else { throw Failure.malformed }
            let name = String(text[text.index(after: newline)...])
            let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
            return .hello(pin: pin, deviceName: trimmed.isEmpty ? "iPhone" : trimmed)
        case 2:
            guard payload.isEmpty else { throw Failure.malformed }
            return .ready
        case 3:
            guard payload.isEmpty else { throw Failure.malformed }
            return .rejected
        case 4:
            return .audio(payload)
        case 5:
            guard payload.isEmpty else { throw Failure.malformed }
            return .stop
        case 6:
            guard payload.isEmpty else { throw Failure.malformed }
            return .capture
        case 7:
            guard payload.isEmpty else { throw Failure.malformed }
            return .release
        default:
            throw Failure.malformed
        }
    }

    static func sanitize(_ name: String) -> String {
        let cleaned = name
            .replacingOccurrences(of: "\n", with: " ")
            .replacingOccurrences(of: "\r", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let trimmed = cleaned.isEmpty ? "iPhone" : cleaned
        return String(trimmed.prefix(60))
    }

    private static func appendUInt32(_ value: UInt32, to data: inout Data) {
        var bigEndian = value.bigEndian
        withUnsafeBytes(of: &bigEndian) { data.append(contentsOf: $0) }
    }

    private static func readUInt32(_ data: Data, at index: Data.Index) -> UInt32 {
        var value: UInt32 = 0
        for byte in data[index..<index + 4] {
            value = (value << 8) | UInt32(byte)
        }
        return value
    }
}

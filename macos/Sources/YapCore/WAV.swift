import Foundation

/// Mono 16-bit PCM WAV encode/decode. Audio stays in memory only.
public enum WAVCodec {
    /// Wrap raw little-endian PCM16 samples in a WAV container.
    public static func encodeMonoPCM16(_ pcm: Data, sampleRate: Int) -> Data {
        guard !pcm.isEmpty, sampleRate > 0 else { return Data() }

        let dataSize = UInt32(pcm.count)
        let byteRate = UInt32(sampleRate * 2)

        var data = Data()
        data.append(contentsOf: Array("RIFF".utf8))
        append(36 + dataSize, to: &data)
        data.append(contentsOf: Array("WAVE".utf8))

        data.append(contentsOf: Array("fmt ".utf8))
        append(UInt32(16), to: &data)          // PCM fmt chunk size
        append(UInt16(1), to: &data)           // PCM format
        append(UInt16(1), to: &data)           // mono
        append(UInt32(sampleRate), to: &data)
        append(byteRate, to: &data)
        append(UInt16(2), to: &data)           // block align
        append(UInt16(16), to: &data)          // bits per sample

        data.append(contentsOf: Array("data".utf8))
        append(dataSize, to: &data)
        data.append(pcm)
        return data
    }

    /// Duration in seconds, or nil when the buffer is not a readable WAV.
    public static func duration(_ wav: Data) -> TimeInterval? {
        guard wav.count > 44,
              String(data: wav.prefix(4), encoding: .ascii) == "RIFF",
              String(data: wav.subdata(in: 8..<12), encoding: .ascii) == "WAVE" else {
            return nil
        }

        var sampleRate = 0
        var channels = 0
        var bitsPerSample = 0
        var dataBytes = 0

        var offset = 12
        while offset + 8 <= wav.count {
            let chunkID = String(data: wav.subdata(in: offset..<offset + 4), encoding: .ascii) ?? ""
            let chunkSize = Int(readUInt32(wav, at: offset + 4))
            let bodyStart = offset + 8
            guard bodyStart <= wav.count else { return nil }
            let bodyEnd = min(bodyStart + chunkSize, wav.count)

            switch chunkID {
            case "fmt ":
                guard chunkSize >= 16 else { return nil }
                channels = Int(readUInt16(wav, at: bodyStart + 2))
                sampleRate = Int(readUInt32(wav, at: bodyStart + 4))
                bitsPerSample = Int(readUInt16(wav, at: bodyStart + 14))
            case "data":
                dataBytes = bodyEnd - bodyStart
            default:
                break
            }
            offset = bodyStart + chunkSize + (chunkSize % 2)
        }

        let bytesPerFrame = channels * max(bitsPerSample, 1) / 8
        guard sampleRate > 0, bytesPerFrame > 0, dataBytes > 0 else { return nil }
        return Double(dataBytes) / Double(sampleRate * bytesPerFrame)
    }

    private static func append<T: FixedWidthInteger>(_ value: T, to data: inout Data) {
        var littleEndian = value.littleEndian
        withUnsafeBytes(of: &littleEndian) { data.append(contentsOf: $0) }
    }

    private static func readUInt32(_ data: Data, at offset: Int) -> UInt32 {
        guard offset + 4 <= data.count else { return 0 }
        return data.subdata(in: offset..<offset + 4).withUnsafeBytes { $0.loadUnaligned(as: UInt32.self) }.littleEndian
    }

    private static func readUInt16(_ data: Data, at offset: Int) -> UInt16 {
        guard offset + 2 <= data.count else { return 0 }
        return data.subdata(in: offset..<offset + 2).withUnsafeBytes { $0.loadUnaligned(as: UInt16.self) }.littleEndian
    }
}

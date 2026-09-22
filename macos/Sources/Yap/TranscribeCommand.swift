@preconcurrency import AVFoundation
import Foundation
import YapCore

/// `yap --transcribe <file>`: stream an audio file through the same live
/// pipeline the hotkey uses and print the transcript. Used for e2e checks.
enum TranscribeCommand {
    private final class ExitCodeBox: @unchecked Sendable {
        var value: Int32 = 1
    }

    static func run(arguments: [String]) -> Int32 {
        guard let flag = arguments.firstIndex(of: "--transcribe"),
              arguments.index(after: flag) < arguments.endIndex else {
            FileHandle.standardError.write(Data("usage: yap --transcribe <audio-file>\n".utf8))
            return 2
        }
        let path = arguments[arguments.index(after: flag)]
        let config = AppConfig.load()
        let apiKey = GeminiKeyResolver.resolve(store: KeychainGeminiKeyStore())
        guard !apiKey.isEmpty else {
            FileHandle.standardError.write(Data("gemini-key-missing\n".utf8))
            return 1
        }

        let configuration = GeminiConfiguration(
            apiKey: apiKey,
            model: config.transcription.model,
            mode: config.transcription.mode,
            languageCodes: geminiLanguageCodes(
                language: config.transcription.language,
                allowedLanguages: config.transcription.allowedLanguages
            ),
            vocabulary: config.vocabulary
        )
        let transcriber = GeminiTranscriber(configuration: configuration)
        let sampleRate = config.transcription.sampleRate
        let url = URL(fileURLWithPath: path)

        let box = ExitCodeBox()
        let semaphore = DispatchSemaphore(value: 0)
        Task {
            defer { semaphore.signal() }
            do {
                let pcm = try readPCM16Mono(url: url, sampleRate: sampleRate)
                guard !pcm.isEmpty else {
                    FileHandle.standardError.write(Data("wav-unreadable\n".utf8))
                    return
                }
                box.value = await transcribe(pcm: pcm, transcriber: transcriber, sampleRate: sampleRate)
            } catch {
                let nsError = error as NSError
                FileHandle.standardError.write(
                    Data("error: \(error) domain=\(nsError.domain) code=\(nsError.code) \(nsError.localizedDescription)\n".utf8)
                )
            }
        }
        semaphore.wait()
        return box.value
    }

    private static func transcribe(pcm: Data, transcriber: GeminiTranscriber, sampleRate: Int) async -> Int32 {
        if let session = transcriber.makeLiveSession() {
            await session.start()
            let chunkSize = sampleRate  // ~1s of PCM16 mono per message
            var offset = 0
            while offset < pcm.count {
                let end = min(offset + chunkSize * 2, pcm.count)
                await session.write(pcm.subdata(in: offset..<end))
                offset = end
            }
            let startedAt = Date()
            do {
                let result = try await session.finish()
                let wait = Date().timeIntervalSince(startedAt)
                if !result.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    print(result.text)
                    FileHandle.standardError.write(
                        Data("finish_wait_s=\(String(format: "%.3f", wait)) used_live=true\n".utf8)
                    )
                    return 0
                }
                FileHandle.standardError.write(Data("live-transcript-empty\n".utf8))
            } catch {
                FileHandle.standardError.write(Data("live-failed: \(error)\n".utf8))
            }
            await session.close()
            FileHandle.standardError.write(Data("fallback=unary\n".utf8))
        }

        do {
            let wav = WAVCodec.encodeMonoPCM16(pcm, sampleRate: sampleRate)
            let result = try await transcriber.transcribe(wav: wav)
            print(result.text)
            FileHandle.standardError.write(Data("used_live=false\n".utf8))
            return 0
        } catch {
            FileHandle.standardError.write(Data("unary-failed: \(error)\n".utf8))
            return 1
        }
    }

    /// Decode any file AVAudioFile can read into 16 kHz mono PCM16.
    private static func readPCM16Mono(url: URL, sampleRate: Int) throws -> Data {
        let file = try AVAudioFile(forReading: url)
        let target = AVAudioFormat(
            commonFormat: .pcmFormatFloat32,
            sampleRate: Double(sampleRate),
            channels: 1,
            interleaved: false
        )!
        guard let converter = AVAudioConverter(from: file.processingFormat, to: target) else {
            throw MicrophoneError(message: "audio converter unavailable")
        }

        var pcm = Data()
        let totalFrames = Int(file.length)
        var framesRead = 0
        while framesRead < totalFrames {
            let requested = min(4_096, totalFrames - framesRead)
            guard let input = AVAudioPCMBuffer(
                pcmFormat: file.processingFormat,
                frameCapacity: AVAudioFrameCount(requested)
            ) else { break }
            // Read exactly the frames that remain: past EOF this API throws
            // instead of reporting a zero-length buffer.
            try file.read(into: input, frameCount: AVAudioFrameCount(requested))
            if input.frameLength == 0 { break }
            framesRead += Int(input.frameLength)

            let capacity = AVAudioFrameCount(Double(input.frameLength) * target.sampleRate / file.processingFormat.sampleRate) + 32
            guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { break }
            let claim = InputClaim()
            var conversionError: NSError?
            converter.convert(to: output, error: &conversionError) { _, status in
                guard claim.claim() else {
                    status.pointee = .noDataNow
                    return nil
                }
                status.pointee = .haveData
                return input
            }
            guard conversionError == nil, output.frameLength > 0, let channel = output.floatChannelData?[0] else { continue }
            let count = Int(output.frameLength)
            var chunk = Data(count: count * MemoryLayout<Int16>.size)
            chunk.withUnsafeMutableBytes { raw in
                let samples = raw.bindMemory(to: Int16.self)
                for index in 0..<count {
                    let sample = max(-1.0, min(1.0, Double(channel[index])))
                    samples[index] = Int16((sample * 32767.0).rounded())
                }
            }
            pcm.append(chunk)
        }
        return pcm
    }
}

struct MicrophoneError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

/// `yap --doctor`: report what dictation needs and what is missing.
enum DoctorCommand {
    static func run() -> Int32 {
        var ok = true
        func report(_ label: String, _ value: String, good: Bool) {
            print("\(label.padding(toLength: 22, withPad: " ", startingAt: 0)) \(value)")
            if !good { ok = false }
        }

        print("Yap doctor (version \(AppInfo.version))")
        print("")

        let configExists = FileManager.default.fileExists(atPath: AppConfig.configURL.path)
        let config = AppConfig.load()
        let vocabularyCount = AppConfig.loadVocabulary().count
        report("config", "\(AppConfig.configURL.path) (\(configExists ? "present" : "missing, seeded on first launch"))", good: true)
        report("vocabulary", "\(vocabularyCount) terms", good: true)

        let resolved = GeminiKeyResolver.resolveDetailed(store: KeychainGeminiKeyStore())
        report(
            "gemini api key",
            resolved.key.isEmpty ? "MISSING" : resolved.source.rawValue,
            good: !resolved.key.isEmpty
        )

        for kind in Permissions.Kind.allCases {
            report(kind.displayName.lowercased(), Permissions.isGranted(kind) ? "granted" : "MISSING", good: Permissions.isGranted(kind))
        }

        report("trigger keys", config.hotkey.keycodes.map(String.init).joined(separator: ", "), good: true)
        report("mode", config.transcription.mode.rawValue, good: true)
        return ok ? 0 : 1
    }
}

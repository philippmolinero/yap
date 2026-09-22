import Foundation
import YapCore

func wavSuite() -> Suite {
    let suite = Suite("WAV codec")

    suite.test("encodes header and duration") {
        // 16 kHz mono PCM16: 32000 bytes is exactly one second.
        let pcm = Data(count: 32_000)
        let wav = WAVCodec.encodeMonoPCM16(pcm, sampleRate: 16_000)

        try expect(wav.count == 44 + pcm.count)
        try expect(String(data: wav.prefix(4), encoding: .ascii) == "RIFF")
        try expect(String(data: wav.subdata(in: 8..<12), encoding: .ascii) == "WAVE")
        try expect(WAVCodec.duration(wav) == 1.0)
    }

    suite.test("empty PCM produces an empty WAV") {
        try expect(WAVCodec.encodeMonoPCM16(Data(), sampleRate: 16_000).isEmpty)
    }

    suite.test("garbage is not a duration") {
        try expect(WAVCodec.duration(Data("not a wav at all".utf8)) == nil)
        try expect(WAVCodec.duration(Data()) == nil)
    }

    suite.test("duration handles half a second") {
        let wav = WAVCodec.encodeMonoPCM16(Data(count: 16_000), sampleRate: 16_000)
        try expect(WAVCodec.duration(wav) == 0.5)
    }

    return suite
}

func historySuite() -> Suite {
    let suite = Suite("History store")

    func makeFile() -> URL {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-history-\(UUID().uuidString).json")
    }

    suite.test("prepends most recent first") {
        let url = makeFile()
        defer { try? FileManager.default.removeItem(at: url) }
        let store = FileHistoryStore(url: url, limit: 3)
        try expect(store.load().isEmpty)

        store.prepend("one")
        store.prepend("two")
        store.prepend("three")
        try expect(store.load() == ["three", "two", "one"])

        store.prepend("four")
        try expect(store.load() == ["four", "three", "two"])
    }

    suite.test("corrupt file loads empty") {
        let url = makeFile()
        try "{ not json".write(to: url, atomically: true, encoding: .utf8)
        defer { try? FileManager.default.removeItem(at: url) }

        try expect(FileHistoryStore(url: url).load().isEmpty)
    }

    suite.test("written file is private") {
        let url = makeFile()
        defer { try? FileManager.default.removeItem(at: url) }
        FileHistoryStore(url: url).prepend("secret dictation")

        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        try expect((attributes[.posixPermissions] as? NSNumber)?.int16Value == 0o600)
    }

    suite.test("memory store respects the limit") {
        let store = MemoryHistoryStore(limit: 2)
        store.prepend("a")
        store.prepend("b")
        store.prepend("c")
        try expect(store.load() == ["c", "b"])
    }

    return suite
}

func metricsSuite() -> Suite {
    let suite = Suite("Metrics writer")

    suite.test("writes snake_case JSONL without transcript content") {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-metrics-\(UUID().uuidString).jsonl")
        defer { try? FileManager.default.removeItem(at: url) }
        let writer = FileMetricsWriter(url: url)

        writer.append(PipelineMeasurement(
            recordingID: 7,
            source: "hotkey_up",
            audioDurationSeconds: 1.5,
            recorderStopSeconds: 0.01,
            transcriptionSeconds: 0.4,
            totalSeconds: 0.5,
            transcriptionProvider: "gemini",
            transcriptionModel: "gemini-3.5-transcribe",
            language: "en",
            textChars: 12,
            success: true,
            usedLive: true,
            timestamp: "2026-09-22T00:00:00.000Z"
        ))

        let text = try String(contentsOf: url, encoding: .utf8)
        try expect(text.hasSuffix("\n"))
        try expect(text.contains("\"recording_id\":7"))
        try expect(text.contains("\"audio_duration_s\":1.5"))
        try expect(text.contains("\"used_live\":true"))
        try expect(text.contains("\"recorder_stop_s\""))
        try expect(text.contains("\"text_chars\":12"))

        // Privacy: the schema carries sizes, timings, and model identities —
        // never transcript content or credentials.
        let line = try require(String(text.dropLast()).data(using: .utf8))
        let object = try require(try JSONSerialization.jsonObject(with: line) as? [String: Any])
        try expect(Set(object.keys) == [
            "recording_id", "source", "audio_duration_s", "recorder_stop_s",
            "transcription_s", "total_s", "transcription_provider", "transcription_model",
            "language", "text_chars", "success", "error", "used_live", "timestamp",
        ], "measurements must not grow content fields")
        try expect(object["text"] == nil)
        try expect(object["api_key"] == nil)

        let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
        try expect((attributes[.posixPermissions] as? NSNumber)?.int16Value == 0o600)
    }

    suite.test("appends one line per measurement") {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-metrics-\(UUID().uuidString).jsonl")
        defer { try? FileManager.default.removeItem(at: url) }
        let writer = FileMetricsWriter(url: url)

        for index in 0..<3 {
            writer.append(PipelineMeasurement(source: "test", totalSeconds: Double(index), success: true))
        }
        let text = try String(contentsOf: url, encoding: .utf8)
        try expect(text.split(separator: "\n").count == 3)
    }

    return suite
}

func languageSuite() -> Suite {
    let suite = Suite("Language mapping")

    suite.test("normalizes aliases and regions") {
        try expect(normalizeLanguage("EN") == "en")
        try expect(normalizeLanguage("de_DE") == "de")
        try expect(normalizeLanguage("German") == "de")
        try expect(normalizeLanguage("Deutsch") == "de")
        try expect(normalizeLanguage("th-TH") == "th")
        try expect(normalizeLanguage("  ") == "")
    }

    suite.test("maps BCP-47") {
        try expect(bcp47Code(for: "en") == "en")
        try expect(bcp47Code(for: "de") == "de-DE")
        try expect(bcp47Code(for: "th") == "th-TH")
    }

    suite.test("language codes prefer the explicit hint") {
        try expect(geminiLanguageCodes(language: "de", allowedLanguages: ["en", "de"]) == ["de-DE"])
        try expect(geminiLanguageCodes(language: "", allowedLanguages: ["en", "de"]) == ["en", "de-DE"])
        try expect(geminiLanguageCodes(language: "", allowedLanguages: []) == ["auto"])
        try expect(geminiLanguageCodes(language: "   ", allowedLanguages: ["th"]) == ["th-TH"])
    }

    return suite
}

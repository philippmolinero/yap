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

func metricsSummarySuite() -> Suite {
    let suite = Suite("Metrics summary")

    suite.test("nearest-rank percentiles") {
        let samples = (1...10).map(Double.init)
        try expect(MetricsPercentile.nearestRank(samples, percentile: 0.50) == 5)
        try expect(MetricsPercentile.nearestRank(samples, percentile: 0.95) == 10)
        try expect(MetricsPercentile.nearestRank((1...20).map(Double.init), percentile: 0.95) == 19)
        try expect(MetricsPercentile.nearestRank([0.4], percentile: 0.50) == 0.4)
        try expect(MetricsPercentile.nearestRank([0.4], percentile: 0.95) == 0.4)
        try expect(MetricsPercentile.nearestRank([], percentile: 0.95) == nil)
        try expect(MetricsPercentile.nearestRank([.nan, .infinity, 1.5], percentile: 0.95) == 1.5)
    }

    suite.test("splits live and fallback by success") {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let recent = PipelineMeasurement.isoTimestamp(from: now.addingTimeInterval(-3600))
        let older = PipelineMeasurement.isoTimestamp(from: now.addingTimeInterval(-48 * 3600))
        let rows = [
            sample(total: 1, transcription: 0.4, usedLive: true, success: true, timestamp: recent),
            sample(total: 2, transcription: nil, usedLive: true, success: true, timestamp: recent),
            sample(total: 3, transcription: 0.8, usedLive: true, success: true, timestamp: older),
            sample(
                total: 9,
                transcription: nil,
                usedLive: true,
                success: false,
                error: "transcription_failed",
                timestamp: recent
            ),
            sample(total: 4, transcription: 3, usedLive: false, success: true, timestamp: recent, model: "other-model"),
            sample(
                total: 8,
                transcription: 1,
                usedLive: false,
                success: false,
                error: "this is dictated text",
                timestamp: recent
            ),
        ]
        let report = MetricsReport.build(
            from: MetricsLogLoad(measurements: rows, skipped: 0, fileExists: true),
            now: now
        )

        try expect(report.included == 6)
        try expect(report.recentCoversAll == false)
        let live = report.groups[0]
        try expect(live.title == "live path, successful")
        try expect(live.count == 3)
        try expect(live.timings[0].name == "total_s")
        try expect(live.timings[0].p50 == 2)
        try expect(live.timings[0].p95 == 3)
        try expect(live.timings[1].name == "transcription_s")
        try expect(live.timings[1].count == 2)
        try expect(live.timings[1].p50 == 0.4)
        try expect(live.timings[1].p95 == 0.8)

        try expect(report.groups[1].count == 1)
        try expect(report.groups[1].errors == [MetricsCount(name: "transcription_failed", count: 1)])
        try expect(report.groups[2].count == 1)
        try expect(report.groups[3].errors == [MetricsCount(name: "unrecognized", count: 1)])
        try expect(report.models == [
            MetricsCount(name: "gemini-3.5-transcribe", count: 5),
            MetricsCount(name: "other-model", count: 1),
        ])

        try expect(report.recentGroups[0].count == 2)
        try expect(report.recentGroups[0].timings[0].p50 == 1)
        try expect(report.recentGroups[0].timings[0].p95 == 2)

        let text = report.render(path: "/tmp/pipeline_metrics.jsonl")
        try expect(text.contains("live path, successful"))
        try expect(text.contains("p50=2.000s"))
        try expect(text.contains("p95=3.000s"))
        try expect(text.contains("Last 24 hours"))
        try expect(text.contains("transcription_failed (1)"))
        try expect(!text.contains("this is dictated text"))
        try expect(!text.contains("All included rows are from the last 24 hours."))
    }

    suite.test("loader skips older lines and does not print transcript text") {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-metrics-\(UUID().uuidString).jsonl")
        defer { try? FileManager.default.removeItem(at: url) }

        let good = sample(total: 0.5, transcription: 0.25, usedLive: true, success: true, timestamp: "2026-10-22T00:00:00.000Z")
        var object = try jsonObject(good)
        object["text"] = "secret phrase"
        let goodLine = try jsonLine(object)
        let legacy = #"{"total_s":1.2,"success":true,"text":"secret phrase","cleanup_s":0.2}"#
        let garbage = "not json"
        try ([goodLine, legacy, garbage, ""].joined(separator: "\n") + "\n").write(to: url, atomically: true, encoding: .utf8)

        let load = try MetricsLog.load(from: url)
        try expect(load.fileExists)
        try expect(load.measurements.count == 1)
        try expect(load.skipped == 2)
        try expect(load.measurements[0].totalSeconds == 0.5)
        try expect(load.measurements[0].usedLive)

        let text = MetricsReport.build(from: load, now: Date(timeIntervalSince1970: 1_800_000_000)).render(path: url.path)
        try expect(text.contains("included"))
        try expect(text.contains("2 (unreadable or older format, not counted)"))
        try expect(text.contains("All included rows are from the last 24 hours.") == false)
        try expect(text.contains("Nothing in the last 24 hours."))
        try expect(!text.contains("secret phrase"))
    }

    suite.test("missing file is an empty report") {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yap-metrics-missing-\(UUID().uuidString).jsonl")
        let load = try MetricsLog.load(from: url)
        try expect(load.fileExists == false)
        try expect(load.measurements.isEmpty)
        let text = MetricsReport.build(from: load).render(path: url.path)
        try expect(text.contains("No metrics file yet."))
        try expect(!text.contains("secret"))
    }

    suite.test("a day of only recent rows is not printed twice") {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let row = sample(
            total: 0.2,
            transcription: 0.1,
            usedLive: true,
            success: true,
            timestamp: PipelineMeasurement.isoTimestamp(from: now.addingTimeInterval(-60))
        )
        let report = MetricsReport.build(
            from: MetricsLogLoad(measurements: [row], skipped: 0, fileExists: true),
            now: now
        )
        try expect(report.recentCoversAll)
        let text = report.render(path: "/tmp/pipeline_metrics.jsonl")
        let lines = text.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        try expect(lines.contains("All included rows are from the last 24 hours."))
        try expect(lines.contains("Last 24 hours") == false)
    }

    return suite
}

private func sample(
    total: Double,
    transcription: Double?,
    usedLive: Bool,
    success: Bool,
    error: String = "",
    timestamp: String,
    model: String = "gemini-3.5-transcribe"
) -> PipelineMeasurement {
    PipelineMeasurement(
        source: "hotkey_up",
        audioDurationSeconds: 2,
        recorderStopSeconds: 0.01,
        transcriptionSeconds: transcription,
        totalSeconds: total,
        transcriptionProvider: "gemini",
        transcriptionModel: model,
        textChars: 4,
        success: success,
        error: error,
        usedLive: usedLive,
        timestamp: timestamp
    )
}

private func jsonObject(_ measurement: PipelineMeasurement) throws -> [String: Any] {
    let data = try JSONEncoder().encode(measurement)
    return try require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
}

private func jsonLine(_ object: [String: Any]) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: object)
    return try require(String(data: data, encoding: .utf8))
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

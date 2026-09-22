import Foundation
import YapCore

private func decode(_ data: Data) throws -> [String: Any] {
    try require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
}

func geminiMessageSuite() -> Suite {
    let suite = Suite("Gemini message shaping")

    suite.test("setup message streams text with vocabulary") {
        let config = GeminiConfiguration(
            apiKey: "secret",
            model: "gemini-3.5-transcribe",
            mode: .smart,
            languageCodes: ["en", "de-DE"],
            vocabulary: ["Claude Code", " ", "Yap"]
        )
        let message = try decode(GeminiMessage.setup(config))

        try expect(message["setup"] != nil)
        let setup = try require(message["setup"] as? [String: Any])
        try expect(setup["model"] as? String == "models/gemini-3.5-transcribe-live")

        let generation = try require(setup["generationConfig"] as? [String: Any])
        try expect(generation["responseModalities"] as? [String] == ["TEXT"])

        let transcription = try require(setup["inputAudioTranscription"] as? [String: Any])
        try expect(transcription["mode"] as? String == "SMART")
        try expect(transcription["languageCodes"] as? [String] == ["en", "de-DE"])
        try expect(transcription["customVocabulary"] as? [String] == ["Claude Code", "Yap"])

        let realtime = try require(setup["realtimeInputConfig"] as? [String: Any])
        let detection = try require(realtime["automaticActivityDetection"] as? [String: Any])
        try expect(detection["disabled"] as? Bool == true)

        // The API key never belongs in the setup payload.
        try expect(String(data: GeminiMessage.setup(config), encoding: .utf8)?.contains("secret") == false)
    }

    suite.test("verbatim mode and vocabulary cap") {
        let config = GeminiConfiguration(
            apiKey: "k",
            mode: .verbatim,
            vocabulary: (0..<150).map { "term\($0)" }
        )
        try expect(config.vocabulary.count == 100)

        let message = try decode(GeminiMessage.setup(config))
        let setup = try require(message["setup"] as? [String: Any])
        let transcription = try require(setup["inputAudioTranscription"] as? [String: Any])
        try expect(transcription["mode"] as? String == "VERBATIM")

        let vocabulary = try require(transcription["customVocabulary"] as? [String])
        try expect(vocabulary.count == 100)
    }

    suite.test("audio and activity messages") {
        let audio = try decode(GeminiMessage.audio(pcm: Data([1, 2, 3])))
        let realtime = try require(audio["realtimeInput"] as? [String: Any])
        let payload = try require(realtime["audio"] as? [String: Any])
        try expect(payload["mimeType"] as? String == "audio/pcm;rate=16000")
        try expect(payload["data"] as? String == Data([1, 2, 3]).base64EncodedString())

        let start = try decode(GeminiMessage.activityStart())
        try expect((start["realtimeInput"] as? [String: Any])?["activityStart"] != nil)

        let end = try decode(GeminiMessage.activityEnd())
        try expect((end["realtimeInput"] as? [String: Any])?["activityEnd"] != nil)
    }

    suite.test("unary request uses snake_case fields") {
        let config = GeminiConfiguration(
            apiKey: "k",
            model: "gemini-3.5-transcribe",
            mode: .smart,
            languageCodes: ["de-DE"],
            vocabulary: ["Yap"]
        )
        let request = try decode(GeminiMessage.unaryRequest(wav: Data([0, 1]), config: config))

        try expect(request["model"] as? String == "gemini-3.5-transcribe")
        let input = try require(request["input"] as? [[String: Any]])
        try expect(input.count == 1)
        try expect(input[0]["type"] as? String == "audio")
        try expect(input[0]["mime_type"] as? String == "audio/wav")

        let generation = try require(request["generation_config"] as? [String: Any])
        let transcription = try require(generation["transcription_config"] as? [String: Any])
        try expect(transcription["language_codes"] as? [String] == ["de-DE"])
        let mode = try require(transcription["mode"] as? [String: Any])
        try expect(mode["type"] as? String == "smart")
        try expect(transcription["custom_vocabulary"] as? [String] == ["Yap"])
    }

    suite.test("transcript reads all response shapes") {
        let flat = Data(#"{"output_text": "  Hallo Welt  ", "language": "de"}"#.utf8)
        let flatResult = GeminiMessage.transcript(from: flat)
        try expect(flatResult == ("Hallo Welt", "de"))

        let steps = Data(#"{"steps": [{"content": [{"text": "From steps"}]}]}"#.utf8)
        try expect(GeminiMessage.transcript(from: steps).text == "From steps")

        let candidates = Data(#"{"candidates": [{"content": {"parts": [{"text": "From candidates"}]}}]}"#.utf8)
        try expect(GeminiMessage.transcript(from: candidates).text == "From candidates")

        try expect(GeminiMessage.transcript(from: Data("not json".utf8)) == ("", ""))
        try expect(GeminiMessage.transcript(from: Data("{}".utf8)) == ("", ""))
    }

    return suite
}

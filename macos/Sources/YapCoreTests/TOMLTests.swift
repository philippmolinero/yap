import Foundation
import YapCore

func tomlSuite() -> Suite {
    let suite = Suite("TOML parsing and editing")

    suite.test("parses scalars and arrays") {
        let document = TOMLDocument(text: """
        # top comment
        title = "Yap"

        [hotkey]
        keycodes = [61, 62]   # trailing comment
        double_tap_ms = 300
        enabled = true
        threshold = 0.008

        [transcription]
        model = "gemini-3.5-transcribe"
        language = ""
        """)

        try expect(document.string("title", in: "") == "Yap")
        try expect(document.intArray("keycodes", in: "hotkey") == [61, 62])
        try expect(document.int("double_tap_ms", in: "hotkey") == 300)
        try expect(document.bool("enabled", in: "hotkey") == true)
        try expect(document.double("threshold", in: "hotkey") == 0.008)
        try expect(document.string("model", in: "transcription") == "gemini-3.5-transcribe")
        try expect(document.string("language", in: "transcription") == "")
    }

    suite.test("parses escaped strings and literal strings") {
        let document = TOMLDocument(text: """
        [a]
        escaped = "line\\nnext \\"quoted\\""
        literal = 'C:\\raw\\path'
        empty_array = []
        mixed = ["x", 3, true]
        """)
        try expect(document.string("escaped", in: "a") == "line\nnext \"quoted\"")
        try expect(document.string("literal", in: "a") == "C:\\raw\\path")
        try expect(document.value("empty_array", in: "a") == .array([]))
        try expect(document.value("mixed", in: "a") == .array([.string("x"), .integer(3), .bool(true)]))
    }

    suite.test("ignores comments and blank lines") {
        let document = TOMLDocument(text: """
        # [not-a-section]
        [real]
        # key = "commented out"
        key = "value"
        """)
        try expect(document.string("key", in: "real") == "value")
        try expect(document.value("key", in: "not-a-section") == nil)
    }

    suite.test("replaces key in place preserving neighbors") {
        var document = TOMLDocument(text: """
        [hotkey]
        # keep this comment
        keycodes = [62]
        double_tap_ms = 300
        """)
        document.set(.array([.integer(61), .integer(62)]), forKey: "keycodes", in: "hotkey")

        try expect(document.intArray("keycodes", in: "hotkey") == [61, 62])
        try expect(document.text.contains("# keep this comment"))
        try expect(document.text.contains("double_tap_ms = 300"))
    }

    suite.test("inserts key into existing section") {
        var document = TOMLDocument(text: """
        [transcription]
        model = "gemini-3.5-transcribe"

        [paste]
        delay_ms = 50
        """)
        document.set(.string("smart"), forKey: "mode", in: "transcription")

        try expect(document.string("mode", in: "transcription") == "smart")
        try expect(document.text.contains("[paste]"))
        try expect(document.text.contains("delay_ms = 50"))
    }

    suite.test("appends missing section") {
        var document = TOMLDocument(text: "[hotkey]\ndouble_tap_ms = 300")
        document.set(.integer(5), forKey: "delay_ms", in: "paste")

        try expect(document.int("delay_ms", in: "paste") == 5)
        try expect(document.int("double_tap_ms", in: "hotkey") == 300)
        try expect(document.text.contains("[paste]"))
    }

    suite.test("serializes values") {
        try expect(TOMLValue.string("a\"b").serialized == "\"a\\\"b\"")
        try expect(TOMLValue.bool(true).serialized == "true")
        try expect(TOMLValue.integer(42).serialized == "42")
        try expect(TOMLValue.array([.string("x"), .integer(1)]).serialized == "[\"x\", 1]")
    }

    suite.test("round trips through set") {
        var document = TOMLDocument()
        document.set(.string("hello \"world\"\n"), forKey: "text", in: "test")
        try expect(document.string("text", in: "test") == "hello \"world\"\n")
    }

    return suite
}

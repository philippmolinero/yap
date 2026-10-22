import Foundation
import YapCore

private func decode(_ data: Data) throws -> [String: Any] {
    try require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
}

func turnContextSuite() -> Suite {
    let suite = Suite("Turn-local context")

    suite.test("password fields are secure and ordinary fields are not") {
        try expect(TurnContext.isSecureField(role: "AXTextField", subrole: "AXSecureTextField"))
        try expect(TurnContext.isSecureField(role: "AXSecureTextField", subrole: nil))
        try expect(TurnContext.isSecureField(role: "AXSecureTextField", subrole: "AXStandardWindow"))
        try expect(!TurnContext.isSecureField(role: "AXTextField", subrole: nil))
        try expect(!TurnContext.isSecureField(role: "AXTextArea", subrole: nil))
        try expect(!TurnContext.isSecureField(role: "AXTextField", subrole: "AXSearchField"))
        try expect(!TurnContext.isSecureField(role: nil, subrole: nil))
    }

    suite.test("editor tokens and the window name are kept in order") {
        let terms = TurnContext.terms(
            focusedText: "Please open TaskFilters in task_list.tsx and use_task_filters.",
            windowTitle: "Geoff — Mail"
        )
        try expect(terms == ["TaskFilters", "task_list.tsx", "use_task_filters", "Geoff"])
    }

    suite.test("a file name wins over the snake_case prefix") {
        let terms = TurnContext.terms(focusedText: "see task_list.tsx", windowTitle: "")
        try expect(terms == ["task_list.tsx"])
        try expect(TurnContext.terms(focusedText: "Widget.mm and Header.h", windowTitle: "") == ["Widget.mm", "Header.h"])
    }

    suite.test("plain prose and generic titles add nothing") {
        let terms = TurnContext.terms(
            focusedText: "the task filters are ready for Monday",
            windowTitle: "Inbox — Mail"
        )
        try expect(terms.isEmpty)
    }

    suite.test("names come from the window title only") {
        let terms = TurnContext.terms(
            focusedText: "tell Geoff about TaskFilters",
            windowTitle: "Inbox — Mail"
        )
        try expect(terms == ["TaskFilters"])
    }

    suite.test("title names allow apostrophes and hyphens and skip weekdays") {
        try expect(TurnContext.terms(focusedText: "", windowTitle: "O'Brien — Messages") == ["O'Brien"])
        try expect(TurnContext.terms(focusedText: "", windowTitle: "Mary-Jane") == ["Mary-Jane"])
        try expect(TurnContext.terms(focusedText: "", windowTitle: "Monday") == [])
        try expect(TurnContext.terms(focusedText: "", windowTitle: "für Philipp") == ["Philipp"])
    }

    suite.test("duplicate tokens are kept once") {
        let terms = TurnContext.terms(
            focusedText: "TaskFilters and TaskFilters",
            windowTitle: "TaskFilters"
        )
        try expect(terms == ["TaskFilters"])
    }

    suite.test("a long field keeps the head and the tail") {
        let text = "TaskFilters "
            + String(repeating: "a", count: 9_000)
            + " OnlyInMiddle "
            + String(repeating: "b", count: 9_000)
            + " task_list.tsx"
        let terms = TurnContext.terms(focusedText: text, windowTitle: "")
        try expect(terms == ["TaskFilters", "task_list.tsx"])
    }

    suite.test("screen tokens stop at forty so the saved list still fits") {
        let body = (0..<50).map { "Term\($0)Name" }.joined(separator: " ")
        let terms = TurnContext.terms(focusedText: body, windowTitle: "Geoff")
        try expect(terms.count == 40)
        try expect(terms.first == "Term0Name")
        try expect(!terms.contains("Geoff"))
        try expect(!terms.contains("Term40Name"))
    }

    suite.test("merge puts context first and caps the combined list") {
        let merged = TurnContext.merge(
            context: ["TaskFilters", " TaskFilters ", "", "Geoff"],
            saved: ["Yap", "TaskFilters", "Other"]
        )
        try expect(merged == ["TaskFilters", "Geoff", "Yap", "Other"])

        let context = (0..<60).map { "context\($0)" }
        let saved = (0..<50).map { "saved\($0)" }
        let capped = TurnContext.merge(context: context, saved: saved, limit: 100)
        try expect(capped.count == 100)
        try expect(capped.first == "context0")
        try expect(capped[59] == "context59")
        try expect(capped[60] == "saved0")
        try expect(capped.last == "saved39")

        let longPhrase = String(repeating: "a", count: 90)
        try expect(TurnContext.merge(context: [longPhrase], saved: ["Yap"]) == ["Yap"])
        try expect(
            TurnContext.merge(context: ["TaskFilters"], saved: [longPhrase, "Yap"])
                == ["TaskFilters", longPhrase, "Yap"]
        )
    }

    suite.test("adding context does not change the stored configuration") {
        let saved = (0..<100).map { "saved\($0)" }
        let original = GeminiConfiguration(apiKey: "secret", vocabulary: ["Yap"] + saved)
        try expect(original.vocabulary.count == 100)
        try expect(original.vocabulary.first == "Yap")

        let unchanged = original.addingContext([])
        try expect(unchanged == original)

        let updated = original.addingContext(["TaskFilters", "Yap"])
        try expect(original.vocabulary.first == "Yap")
        try expect(!original.vocabulary.contains("TaskFilters"))
        try expect(updated.vocabulary.first == "TaskFilters")
        try expect(updated.vocabulary[1] == "Yap")
        try expect(updated.vocabulary.count == 100)
        try expect(updated.vocabulary.last == "saved97")

        let message = try decode(GeminiMessage.setup(updated))
        let setup = try require(message["setup"] as? [String: Any])
        let transcription = try require(setup["inputAudioTranscription"] as? [String: Any])
        let vocabulary = try require(transcription["customVocabulary"] as? [String])
        try expect(vocabulary.first == "TaskFilters")
        try expect(vocabulary[1] == "Yap")
        try expect(String(data: GeminiMessage.setup(updated), encoding: .utf8)?.contains("secret") == false)

        let request = try decode(GeminiMessage.unaryRequest(wav: Data([0]), config: updated))
        let generation = try require(request["generation_config"] as? [String: Any])
        let unary = try require(generation["transcription_config"] as? [String: Any])
        let unaryVocabulary = try require(unary["custom_vocabulary"] as? [String])
        try expect(unaryVocabulary.first == "TaskFilters")
        try expect(unaryVocabulary[1] == "Yap")
    }

    return suite
}

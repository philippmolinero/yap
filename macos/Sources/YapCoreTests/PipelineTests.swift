import Foundation
import YapCore

// MARK: - Fakes

struct FakeError: Error, Sendable, Equatable {
    let message: String
}

final class FakeRecorder: AudioRecording, @unchecked Sendable {
    private let lock = NSLock()
    var startError: FakeError?
    var wav = WAVCodec.encodeMonoPCM16(Data(count: 3_200), sampleRate: 16_000)

    private var recording = false
    private var onFrame: (@Sendable (Data) -> Void)?
    private var onFirstFrame: (@Sendable () -> Void)?
    private var onSilence: (@Sendable () -> Void)?
    private(set) var startCount = 0
    private(set) var stopCount = 0
    private(set) var forceStopCount = 0

    var isRecording: Bool { lock.withLock { recording } }

    func start(
        onFrame: @escaping @Sendable (Data) -> Void,
        onFirstFrame: @escaping @Sendable () -> Void,
        onSilence: @escaping @Sendable () -> Void
    ) throws {
        try lock.withLock {
            if let startError { throw startError }
            self.onFrame = onFrame
            self.onFirstFrame = onFirstFrame
            self.onSilence = onSilence
            recording = true
            startCount += 1
        }
    }

    func stop(abort: Bool) throws -> Data {
        lock.withLock {
            recording = false
            stopCount += 1
            return wav
        }
    }

    func forceStop() {
        lock.withLock {
            recording = false
            forceStopCount += 1
        }
    }

    func emitFrame(_ data: Data = Data([1])) {
        (lock.withLock { onFrame })?(data)
    }

    func emitFirstFrame() {
        (lock.withLock { onFirstFrame })?()
    }

    func emitSilence() {
        (lock.withLock { onSilence })?()
    }
}

final class FakeLiveSession: LiveTranscribing, @unchecked Sendable {
    private let lock = NSLock()
    var finishResult: Result<TranscriptionResult, FakeError>
    private(set) var written: [Data] = []
    private(set) var startCount = 0
    private(set) var finishCount = 0
    private(set) var closeCount = 0

    init(finishResult: Result<TranscriptionResult, FakeError> = .success(TranscriptionResult(text: "live text", language: "en"))) {
        self.finishResult = finishResult
    }

    func start() async {
        lock.withLock { startCount += 1 }
    }

    func write(_ pcm: Data) async {
        lock.withLock { written.append(pcm) }
    }

    func finish() async throws -> TranscriptionResult {
        lock.withLock { finishCount += 1 }
        return try finishResult.get()
    }

    func close() async {
        lock.withLock { closeCount += 1 }
    }
}

final class FakeTranscriber: Transcribing, @unchecked Sendable {
    let providerName = "fake"
    let modelName = "fake-model"

    private let lock = NSLock()
    private var _liveSession: FakeLiveSession?
    private var _result: Result<TranscriptionResult, FakeError>
    private var _wavs: [Data] = []

    init(
        liveSession: FakeLiveSession? = nil,
        result: Result<TranscriptionResult, FakeError> = .success(TranscriptionResult(text: "unary text", language: "en"))
    ) {
        self._liveSession = liveSession
        self._result = result
    }

    var result: Result<TranscriptionResult, FakeError> {
        get { lock.withLock { _result } }
        set { lock.withLock { _result = newValue } }
    }

    var wavs: [Data] { lock.withLock { _wavs } }

    func makeLiveSession() -> (any LiveTranscribing)? {
        lock.withLock { _liveSession }
    }

    func transcribe(wav: Data) async throws -> TranscriptionResult {
        let result: Result<TranscriptionResult, FakeError> = lock.withLock {
            _wavs.append(wav)
            return _result
        }
        return try result.get()
    }
}

final class FakePaster: TextPasting, @unchecked Sendable {
    struct Call: Equatable, Sendable {
        let text: String
        let target: PasteTarget?
        let delay: TimeInterval
    }

    private let lock = NSLock()
    private var _outcome: PasteOutcome = .pasted
    private var _calls: [Call] = []

    var outcome: PasteOutcome {
        get { lock.withLock { _outcome } }
        set { lock.withLock { _outcome = newValue } }
    }

    var calls: [Call] { lock.withLock { _calls } }

    func paste(_ text: String, target: PasteTarget?, delay: TimeInterval) -> PasteOutcome {
        lock.withLock {
            _calls.append(Call(text: text, target: target, delay: delay))
            return _outcome
        }
    }
}

final class EventLog: @unchecked Sendable {
    private let lock = NSLock()
    private var _states: [PipelineState] = []
    private var _firstFrames = 0
    private var _notices: [String] = []
    private var _errors: [String] = []
    private var _completed: [String] = []

    var states: [PipelineState] { lock.withLock { _states } }
    var firstFrames: Int { lock.withLock { _firstFrames } }
    var notices: [String] { lock.withLock { _notices } }
    var errors: [String] { lock.withLock { _errors } }
    var completed: [String] { lock.withLock { _completed } }

    func recordState(_ state: PipelineState) { lock.withLock { _states.append(state) } }
    func recordFirstFrame() { lock.withLock { _firstFrames += 1 } }
    func recordNotice(_ text: String) { lock.withLock { _notices.append(text) } }
    func recordError(_ text: String) { lock.withLock { _errors.append(text) } }
    func recordCompleted(_ text: String) { lock.withLock { _completed.append(text) } }
}

// MARK: - Fixture

private struct Fixture {
    let pipeline: DictationPipeline
    let recorder: FakeRecorder
    let live: FakeLiveSession
    let transcriber: FakeTranscriber
    let paster: FakePaster
    let history: MemoryHistoryStore
    let metrics: MemoryMetricsWriter
    let events: EventLog
    let failedURL: URL
}

private func makeFixture(
    liveResult: Result<TranscriptionResult, FakeError> = .success(TranscriptionResult(text: "live text", language: "en")),
    unaryResult: Result<TranscriptionResult, FakeError> = .success(TranscriptionResult(text: "unary text", language: "en")),
    wav: Data = WAVCodec.encodeMonoPCM16(Data(count: 3_200), sampleRate: 16_000),
    pasteOutcome: PasteOutcome = .pasted
) -> Fixture {
    let recorder = FakeRecorder()
    recorder.wav = wav
    let live = FakeLiveSession(finishResult: liveResult)
    let transcriber = FakeTranscriber(liveSession: live, result: unaryResult)
    let paster = FakePaster()
    paster.outcome = pasteOutcome
    let history = MemoryHistoryStore()
    let metrics = MemoryMetricsWriter()
    let events = EventLog()
    let failedURL = FileManager.default.temporaryDirectory
        .appendingPathComponent("yap-failed-\(UUID().uuidString).wav")

    let pipeline = DictationPipeline(
        recorder: recorder,
        transcriber: transcriber,
        paster: paster,
        history: history,
        metrics: metrics,
        events: PipelineEvents(
            onStateChange: { events.recordState($0) },
            onFirstFrame: { events.recordFirstFrame() },
            onNotice: { events.recordNotice($0) },
            onDictationError: { events.recordError($0) },
            onDictationComplete: { events.recordCompleted($0) }
        ),
        pasteTargetProvider: { PasteTarget(pid: 4242) },
        pasteDelay: 0.05,
        failedRecordingURL: failedURL
    )
    return Fixture(
        pipeline: pipeline,
        recorder: recorder,
        live: live,
        transcriber: transcriber,
        paster: paster,
        history: history,
        metrics: metrics,
        events: events,
        failedURL: failedURL
    )
}

private func waitUntilIdle(_ pipeline: DictationPipeline, timeout: TimeInterval = 2) async -> Bool {
    let deadline = Date().addingTimeInterval(timeout)
    while Date() < deadline {
        if await pipeline.state == .idle { return true }
        try? await Task.sleep(for: .milliseconds(5))
    }
    return await pipeline.state == .idle
}

// MARK: - Suite

func pipelineSuite() -> Suite {
    let suite = Suite("Dictation pipeline")

    suite.test("live turn pastes text and records history and metrics") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.state == .recording)

        fixture.recorder.emitFrame(Data([1, 2, 3]))
        fixture.recorder.emitFirstFrame()
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)
        try expect(await fixture.pipeline.state == .idle)

        try expect(fixture.paster.calls.map(\.text) == ["live text"])
        try expect(fixture.paster.calls.first?.target == PasteTarget(pid: 4242))
        try expect(fixture.paster.calls.first?.delay == 0.05)
        try expect(fixture.history.load() == ["live text"])
        try expect(fixture.events.completed == ["live text"])
        try expect(fixture.events.firstFrames == 1)
        try expect(fixture.events.states == [.recording, .processing, .idle])
        try expect(fixture.transcriber.wavs.isEmpty, "a live transcript must not trigger the unary call")
        try expect(fixture.live.written == [Data([1, 2, 3])], "frames reach the live session in order")

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(measurement.success)
        try expect(measurement.usedLive)
        try expect(measurement.textChars == 9)
        try expect(measurement.source == "test")
        try expect(measurement.transcriptionProvider == "fake")
    }

    suite.test("start while recording is ignored") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.start(source: "first") == true)
        try expect(await fixture.pipeline.start(source: "second") == false)
        try expect(fixture.recorder.startCount == 1)
        await fixture.pipeline.cancel(source: "cleanup")
    }

    suite.test("stop while idle is ignored") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == false)
        try expect(fixture.paster.calls.isEmpty)
    }

    suite.test("empty audio skips paste quietly") {
        let fixture = makeFixture(wav: Data())
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == false)

        try expect(fixture.paster.calls.isEmpty)
        try expect(fixture.events.errors.isEmpty)
        try expect(fixture.events.states == [.recording, .idle])

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(!measurement.success)
        try expect(measurement.error == "empty_audio")
    }

    suite.test("empty transcript skips paste quietly") {
        let fixture = makeFixture(
            liveResult: .success(TranscriptionResult(text: "   ")),
            unaryResult: .success(TranscriptionResult(text: ""))
        )
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)

        try expect(fixture.paster.calls.isEmpty)
        try expect(fixture.events.errors.isEmpty)
        try expect(fixture.events.completed.isEmpty)
        try expect(fixture.transcriber.wavs.count == 1, "empty live text falls back to the unary call")

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(!measurement.success)
        try expect(measurement.error == "empty_transcript")
    }

    suite.test("live failure falls back to unary") {
        let fixture = makeFixture(liveResult: .failure(FakeError(message: "socket dropped")))
        try expect(await fixture.pipeline.start(source: "test") == true)
        fixture.recorder.emitFrame(Data([9]))
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)

        try expect(fixture.paster.calls.map(\.text) == ["unary text"])
        try expect(fixture.transcriber.wavs.count == 1)

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(measurement.success)
        try expect(!measurement.usedLive)
    }

    suite.test("live empty falls back to unary") {
        let fixture = makeFixture(liveResult: .success(TranscriptionResult(text: "")))
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)

        try expect(fixture.paster.calls.map(\.text) == ["unary text"])
        let measurement = try require(fixture.metrics.measurements.last)
        try expect(measurement.success)
        try expect(!measurement.usedLive)
    }

    suite.test("transcription failure stashes recording and notifies") {
        let fixture = makeFixture(
            liveResult: .failure(FakeError(message: "no socket")),
            unaryResult: .failure(FakeError(message: "no network"))
        )
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)

        try expect(fixture.paster.calls.isEmpty)
        try expect(fixture.events.errors == ["transcription_failed"])
        try expect(await fixture.pipeline.hasFailedRecording == true)
        try expect(FileManager.default.fileExists(atPath: fixture.failedURL.path))

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(!measurement.success)
        try expect(measurement.error == "transcription_failed")
        try? FileManager.default.removeItem(at: fixture.failedURL)
    }

    suite.test("retry reuses the stashed recording and clears it") {
        let fixture = makeFixture(
            liveResult: .failure(FakeError(message: "no socket")),
            unaryResult: .failure(FakeError(message: "no network"))
        )
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)
        try expect(await fixture.pipeline.hasFailedRecording == true)

        fixture.transcriber.result = .success(TranscriptionResult(text: "recovered", language: "en"))
        try expect(await fixture.pipeline.retryLastFailure(source: "menu_retry") == true)

        try expect(fixture.paster.calls.map(\.text) == ["recovered"])
        try expect(fixture.history.load() == ["recovered"])
        try expect(await fixture.pipeline.hasFailedRecording == false)
        try expect(!FileManager.default.fileExists(atPath: fixture.failedURL.path))

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(measurement.success)
        try expect(measurement.source == "menu_retry")
    }

    suite.test("retry without stash returns false") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.retryLastFailure() == false)
    }

    suite.test("cancel discards recording without paste") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.cancel(source: "menu_stop") == true)

        try expect(await fixture.pipeline.state == .idle)
        try expect(fixture.paster.calls.isEmpty)
        try expect(fixture.recorder.forceStopCount == 1)
        try expect(fixture.live.closeCount == 1)
        try expect(fixture.metrics.measurements.isEmpty)
        try expect(fixture.events.states == [.recording, .idle])
    }

    suite.test("silence auto-stop processes the turn") {
        let fixture = makeFixture()
        try expect(await fixture.pipeline.start(source: "test") == true)
        fixture.recorder.emitSilence()

        try expect(await waitUntilIdle(fixture.pipeline), "the turn finishes after the silence callback")
        try expect(fixture.paster.calls.map(\.text) == ["live text"])

        let measurement = try require(fixture.metrics.measurements.last)
        try expect(measurement.success)
        try expect(measurement.source == "silence")
    }

    suite.test("clipboard-only paste still records history and notices") {
        let fixture = makeFixture(pasteOutcome: .clipboardOnly(reason: "Paste target closed. Text is on the clipboard."))
        try expect(await fixture.pipeline.start(source: "test") == true)
        try expect(await fixture.pipeline.stopAndProcess(source: "test") == true)

        try expect(fixture.events.notices == ["Paste target closed. Text is on the clipboard."])
        try expect(fixture.history.load() == ["live text"])
        try expect(fixture.events.completed == ["live text"])
    }

    suite.test("recorder start failure leaves the pipeline idle") {
        let fixture = makeFixture()
        fixture.recorder.startError = FakeError(message: "mic busy")
        try expect(await fixture.pipeline.start(source: "test") == false)
        try expect(await fixture.pipeline.state == .idle)
        try expect(fixture.live.closeCount == 1, "a live session opened before the failure gets closed")
        try expect(fixture.events.states.isEmpty)
    }

    return suite
}

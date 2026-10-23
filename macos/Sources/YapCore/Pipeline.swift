import Foundation

public enum PipelineState: String, Sendable, Equatable {
    case idle
    case recording
    case processing
}

/// The app that was focused when the trigger went down — the paste target.
public struct PasteTarget: Sendable, Equatable {
    public var pid: Int32
    public var bundleURL: URL?

    public init(pid: Int32, bundleURL: URL? = nil) {
        self.pid = pid
        self.bundleURL = bundleURL
    }
}

public enum PasteOutcome: Sendable, Equatable {
    case pasted
    /// The transcript stayed on the clipboard instead of being keystroked.
    case clipboardOnly(reason: String)
}

/// Push-to-talk audio capture. Implementations buffer frames in memory and
/// hand back a WAV on stop.
public protocol AudioRecording: AnyObject, Sendable {
    var isRecording: Bool { get }
    /// Open the input device ahead of the next press so capture does not wait on it.
    func warm()
    func start(
        onFrame: @escaping @Sendable (Data) -> Void,
        onFirstFrame: @escaping @Sendable () -> Void,
        onSilence: @escaping @Sendable () -> Void
    ) throws
    /// Stop and return WAV bytes. Empty means nothing was captured.
    func stop(abort: Bool) throws -> Data
    /// Abort and discard the current capture.
    func forceStop()
}

public extension AudioRecording {
    func warm() {}
}

public protocol TextPasting: Sendable {
    func paste(_ text: String, target: PasteTarget?, delay: TimeInterval) -> PasteOutcome
}

/// Callbacks the app shell wires to sounds, overlay, and menu state. All of
/// them may be invoked from the pipeline's executor.
public struct PipelineEvents: Sendable {
    public var onStateChange: @Sendable (PipelineState) -> Void
    /// Fired when the trigger is released, before any audio tail is kept.
    /// The listening capsule and chime follow this, not the tail.
    public var onListeningEnded: @Sendable () -> Void
    /// Fired once per recording when the first audio frame arrives.
    public var onFirstFrame: @Sendable () -> Void
    /// Quiet, non-error status (e.g. paste target closed).
    public var onNotice: @Sendable (String) -> Void
    public var onDictationError: @Sendable (String) -> Void
    public var onDictationComplete: @Sendable (String) -> Void

    public init(
        onStateChange: @escaping @Sendable (PipelineState) -> Void = { _ in },
        onListeningEnded: @escaping @Sendable () -> Void = {},
        onFirstFrame: @escaping @Sendable () -> Void = {},
        onNotice: @escaping @Sendable (String) -> Void = { _ in },
        onDictationError: @escaping @Sendable (String) -> Void = { _ in },
        onDictationComplete: @escaping @Sendable (String) -> Void = { _ in }
    ) {
        self.onStateChange = onStateChange
        self.onListeningEnded = onListeningEnded
        self.onFirstFrame = onFirstFrame
        self.onNotice = onNotice
        self.onDictationError = onDictationError
        self.onDictationComplete = onDictationComplete
    }
}

/// Orchestrates record → transcribe → paste with the state machine, metrics,
/// history, and failed-recording retry around it.
public actor DictationPipeline {
    private let recorder: any AudioRecording
    private let transcriber: any Transcribing
    private let paster: any TextPasting
    private let history: any HistoryStoring
    private let metrics: any MetricsWriting
    private let events: PipelineEvents
    private let pasteTargetProvider: @Sendable () -> PasteTarget?
    /// Turn-local vocabulary. Empty when the Settings switch is off.
    private let contextTermsProvider: @Sendable () -> [String]
    private let pasteDelay: TimeInterval
    private let failedRecordingURL: URL?

    public private(set) var state: PipelineState = .idle
    private var recordingIDSequence = 0
    private var activeRecordingID: Int?
    private var liveSession: (any LiveTranscribing)?
    private var frameContinuation: AsyncStream<Data>.Continuation?
    private var frameTask: Task<Void, Never>?
    private var pasteTarget: PasteTarget?
    /// Screen tokens captured at key down. Cleared when the turn ends.
    private var contextTerms: [String] = []
    private var failedWAV: Data?
    /// Bumped when a new press replaces an in-flight transcription.
    private var turnToken = 0
    private var finishingSession: (any LiveTranscribing)?
    /// The press currently being opened, so a release can name it.
    private var currentPress: Int?
    /// Set when that press's key-up arrives before the microphone is open.
    private var releasedPress: Int?
    /// How long a normal release keeps the mic open so the last word can arrive.
    private let releaseLinger: TimeInterval

    public init(
        recorder: any AudioRecording,
        transcriber: any Transcribing,
        paster: any TextPasting,
        history: any HistoryStoring = FileHistoryStore(),
        metrics: any MetricsWriting = FileMetricsWriter(),
        events: PipelineEvents = PipelineEvents(),
        pasteTargetProvider: @escaping @Sendable () -> PasteTarget? = { nil },
        contextTermsProvider: @escaping @Sendable () -> [String] = { [] },
        pasteDelay: TimeInterval = 0.05,
        failedRecordingURL: URL? = AppConfig.failedRecordingURL,
        releaseLinger: TimeInterval = 0.25
    ) {
        self.recorder = recorder
        self.transcriber = transcriber
        self.paster = paster
        self.history = history
        self.metrics = metrics
        self.events = events
        self.pasteTargetProvider = pasteTargetProvider
        self.contextTermsProvider = contextTermsProvider
        self.pasteDelay = pasteDelay
        self.failedRecordingURL = failedRecordingURL
        self.releaseLinger = releaseLinger
    }

    // MARK: - Lifecycle

    /// Open the input device so the next press does not wait on it.
    public func warmCapture() async {
        recorder.warm()
    }

    /// Begin capturing. Returns without waiting for any transcript.
    /// `pressID` lets a key-up that arrived first cancel this press.
    /// Listening is shown before the microphone or the network does any work.
    @discardableResult
    public func start(source: String = "external", pressID: Int? = nil) async -> Bool {
        if state == .recording {
            YapLog.warning("start_recording ignored in state \(state.rawValue) [source=\(source)]")
            return false
        }
        if let pressID, releasedPress == pressID {
            YapLog.info("start skipped — trigger already released [source=\(source)]")
            return false
        }
        let replacing = state == .processing
        turnToken += 1
        if replacing {
            YapLog.info("start superseded in-flight transcription [source=\(source)]")
            let previous = finishingSession
            finishingSession = nil
            await previous?.close()
        }
        if let pressID, releasedPress == pressID {
            YapLog.info("start skipped — trigger already released [source=\(source)]")
            return false
        }

        recordingIDSequence += 1
        activeRecordingID = recordingIDSequence
        let recordingID = recordingIDSequence
        currentPress = pressID
        // The overlay and chime follow this. It has to land before device and network work.
        setState(.recording, source: source, recordingID: recordingID)
        pasteTarget = pasteTargetProvider()
        let terms = contextTermsProvider()
        contextTerms = terms
        if !terms.isEmpty {
            YapLog.info("turn context terms=\(terms.count)")
        }

        var session: (any LiveTranscribing)?
        if let opened = transcriber.makeLiveSession(vocabulary: terms) {
            session = opened
            liveSession = opened
            await opened.start()
        }
        if state != .recording {
            await abandonSetup(session: session, source: source, recordingID: recordingID)
            return false
        }

        var frameSink: (@Sendable (Data) -> Void)?
        if session != nil {
            let pair = AsyncStream<Data>.makeStream(of: Data.self, bufferingPolicy: .unbounded)
            frameContinuation = pair.continuation
            let continuation = pair.continuation
            frameSink = { chunk in continuation.yield(chunk) }
            let streamSession = session
            frameTask = Task {
                guard let streamSession else { return }
                for await chunk in pair.stream {
                    await streamSession.write(chunk)
                }
            }
        }
        let frameSinkCapture = frameSink

        do {
            try recorder.start(
                onFrame: { chunk in frameSinkCapture?(chunk) },
                onFirstFrame: { [events] in events.onFirstFrame() },
                onSilence: { [weak self] in
                    Task { await self?.stopAndProcess(source: "silence", abort: true) }
                }
            )
        } catch {
            YapLog.error("Recorder start failed [source=\(source) recording=\(recordingID)]: \(error.localizedDescription)")
            liveSession = nil
            contextTerms = []
            pasteTarget = nil
            frameContinuation?.finish()
            frameContinuation = nil
            frameTask = nil
            await session?.close()
            setState(.idle, source: "\(source):start_error", recordingID: recordingID)
            return false
        }

        if let pressID, releasedPress == pressID {
            YapLog.info("trigger released during capture setup [source=\(source)]")
            return await stopAndProcess(source: "\(source):released")
        }
        return true
    }

    /// Drop a capture setup that lost the race with cancel or a newer press.
    private func abandonSetup(
        session: (any LiveTranscribing)?,
        source: String,
        recordingID: Int
    ) async {
        let owned = liveSession
        liveSession = nil
        frameContinuation?.finish()
        frameContinuation = nil
        let pendingFrames = frameTask
        frameTask = nil
        await pendingFrames?.value
        if owned != nil {
            await session?.close()
        }
        if state == .recording {
            setState(.idle, source: "\(source):abandoned", recordingID: recordingID)
        }
    }

    /// Stop capturing, transcribe, and paste. `abort` tears the capture down
    /// without draining (silence auto-stop path). `linger` overrides the
    /// release tail; the iPhone path passes 0 because its stop message is
    /// already ordered after the last audio byte.
    @discardableResult
    public func stopAndProcess(
        source: String = "external",
        abort: Bool = false,
        pressID: Int? = nil,
        linger: TimeInterval? = nil
    ) async -> Bool {
        if let pressID {
            releasedPress = pressID
        }
        guard state == .recording else {
            if pressID != nil {
                YapLog.info("stop deferred — recording has not started [source=\(source)]")
            } else {
                YapLog.warning("stop_recording_and_process ignored in state \(state.rawValue) [source=\(source)]")
            }
            return false
        }
        guard recorder.isRecording else {
            // start() is still opening the device. It stops once the tap is in.
            events.onListeningEnded()
            YapLog.info("stop deferred — microphone is not open yet [source=\(source)]")
            return false
        }

        let recordingID = activeRecordingID
        let target = pasteTarget
        let terms = contextTerms
        let session = liveSession
        let token = turnToken
        let startedAt = Self.now()
        liveSession = nil
        pasteTarget = nil
        contextTerms = []
        // The capsule and chime belong to the key, not to the tail that follows.
        events.onListeningEnded()
        // The key-up arrives before the last buffer, especially on Bluetooth.
        // Leave the tap open so those frames still reach the live socket.
        let tail = linger ?? releaseLinger
        if !abort, tail > 0 {
            YapLog.info("release linger \(String(format: "%.2f", tail))s")
            try? await Task.sleep(for: .seconds(tail))
            guard state == .recording, isCurrent(token) else {
                frameContinuation?.finish()
                frameContinuation = nil
                frameTask = nil
                await session?.close()
                YapLog.info("release linger abandoned [source=\(source)]")
                return false
            }
        }
        frameContinuation?.finish()
        frameContinuation = nil
        let pendingFrames = frameTask
        frameTask = nil
        // Drain every queued frame before finalizing the live turn.
        await pendingFrames?.value

        let stopStarted = Self.now()
        let wav: Data
        do {
            wav = try recorder.stop(abort: abort)
        } catch {
            YapLog.error("Recorder stop failed [source=\(source)]: \(error.localizedDescription)")
            await session?.close()
            emit(
                recordingID: recordingID,
                source: source,
                wav: nil,
                recorderStopSeconds: Self.now() - stopStarted,
                transcriptionSeconds: nil,
                totalSeconds: Self.now() - startedAt,
                success: false,
                error: "recorder_stop_failed"
            )
            setState(.idle, source: "\(source):stop_error", recordingID: recordingID)
            return false
        }
        let recorderStopSeconds = Self.now() - stopStarted

        guard !wav.isEmpty else {
            await session?.close()
            YapLog.warning("No audio captured [source=\(source) recording=\(recordingID.map(String.init) ?? "-")]")
            emit(
                recordingID: recordingID,
                source: source,
                wav: nil,
                recorderStopSeconds: recorderStopSeconds,
                transcriptionSeconds: nil,
                totalSeconds: Self.now() - startedAt,
                success: false,
                error: "empty_audio"
            )
            setState(.idle, source: "\(source):empty_audio", recordingID: recordingID)
            return false
        }

        setState(.processing, source: source, recordingID: recordingID)
        await process(
            wav: wav,
            source: source,
            recordingID: recordingID,
            recorderStopSeconds: recorderStopSeconds,
            startedAt: startedAt,
            target: target,
            session: session,
            vocabulary: terms,
            fromRetry: false,
            token: token
        )
        return true
    }

    /// Abort an active recording without transcribing partial audio.
    @discardableResult
    public func cancel(source: String = "external") async -> Bool {
        let recorderActive = recorder.isRecording
        guard state == .recording || recorderActive else {
            YapLog.info("cancel_recording ignored in state \(state.rawValue) [source=\(source)]")
            return false
        }

        let recordingID = activeRecordingID
        let session = liveSession
        if state == .recording {
            events.onListeningEnded()
        }
        liveSession = nil
        pasteTarget = nil
        contextTerms = []
        frameContinuation?.finish()
        frameContinuation = nil
        let pendingFrames = frameTask
        frameTask = nil
        await pendingFrames?.value
        recorder.forceStop()
        await session?.close()
        setState(.idle, source: "\(source):cancel", recordingID: recordingID)
        return true
    }

    /// True when a transcription-failed recording is available for retry.
    public var hasFailedRecording: Bool {
        if failedWAV != nil { return true }
        guard let url = failedRecordingURL,
              let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
              let size = attributes[.size] as? Int else {
            return false
        }
        return size > 0
    }

    /// Re-run transcription for the last recording that failed to transcribe.
    @discardableResult
    public func retryLastFailure(source: String = "retry") async -> Bool {
        guard state == .idle else {
            YapLog.warning("retry_last_recording ignored in state \(state.rawValue) [source=\(source)]")
            return false
        }
        guard let wav = loadFailedRecording(), !wav.isEmpty else {
            YapLog.info("retry_last_recording: no failed recording available")
            return false
        }

        recordingIDSequence += 1
        let recordingID = recordingIDSequence
        activeRecordingID = recordingID
        setState(.processing, source: source, recordingID: recordingID)
        await process(
            wav: wav,
            source: source,
            recordingID: recordingID,
            recorderStopSeconds: 0,
            startedAt: Self.now(),
            target: nil,
            session: nil,
            vocabulary: [],
            fromRetry: true,
            token: turnToken
        )
        return true
    }

    // MARK: - Processing

    private func process(
        wav: Data,
        source: String,
        recordingID: Int?,
        recorderStopSeconds: TimeInterval,
        startedAt: TimeInterval,
        target: PasteTarget?,
        session: (any LiveTranscribing)?,
        vocabulary: [String],
        fromRetry: Bool,
        token: Int
    ) async {
        let transcriptionStarted = Self.now()
        var result: TranscriptionResult?
        var usedLive = false

        if let session {
            finishingSession = session
            do {
                let live = try await session.finish()
                if !isCurrent(token) {
                    YapLog.info("stale transcription dropped after live finish")
                    return
                }
                if live.modelReplyOnly {
                    // The socket answered instead of transcribing. The batch call
                    // sees the same audio and will answer too, so do not paste it.
                    YapLog.warning("Gemini live replied instead of transcribing")
                    emit(
                        recordingID: recordingID,
                        source: source,
                        wav: wav,
                        recorderStopSeconds: recorderStopSeconds,
                        transcriptionSeconds: Self.now() - transcriptionStarted,
                        totalSeconds: Self.now() - startedAt,
                        success: false,
                        error: "model_reply"
                    )
                    setState(.idle, source: "\(source):model_reply", recordingID: recordingID)
                    events.onDictationError("model_reply")
                    return
                }
                let text = live.text.trimmingCharacters(in: .whitespacesAndNewlines)
                if text.isEmpty {
                    YapLog.info("Live transcript empty")
                } else {
                    YapLog.info("Live transcript used chars=\(live.text.count)")
                    result = live
                    usedLive = true
                }
            } catch {
                YapLog.warning("Live transcription failed: \(error)")
            }
            if finishingSession != nil {
                finishingSession = nil
            }
            if !isCurrent(token) {
                YapLog.info("stale transcription dropped")
                return
            }
            if result == nil {
                YapLog.info("Batch transcription fallback")
            }
        }

        if !isCurrent(token) {
            YapLog.info("stale transcription dropped")
            return
        }

        if result == nil {
            do {
                result = try await transcriber.transcribe(wav: wav, vocabulary: vocabulary)
            } catch {
                if !isCurrent(token) {
                    YapLog.info("stale transcription dropped")
                    return
                }
                YapLog.error(
                    "Transcription failed [provider=\(transcriber.providerName) model=\(transcriber.modelName) source=\(source)]: \(error)"
                )
                stashFailedRecording(wav)
                emit(
                    recordingID: recordingID,
                    source: source,
                    wav: wav,
                    recorderStopSeconds: recorderStopSeconds,
                    transcriptionSeconds: Self.now() - transcriptionStarted,
                    totalSeconds: Self.now() - startedAt,
                    success: false,
                    error: "transcription_failed"
                )
                setState(.idle, source: "\(source):transcription_error", recordingID: recordingID)
                events.onDictationError("transcription_failed")
                return
            }
            if !isCurrent(token) {
                YapLog.info("stale transcription dropped")
                return
            }
        }

        if !isCurrent(token) {
            YapLog.info("stale transcription dropped")
            return
        }

        if fromRetry {
            // The stashed audio reached the provider — the copy is no longer needed.
            clearFailedRecording()
        }
        let transcriptionSeconds = Self.now() - transcriptionStarted

        guard isCurrent(token) else {
            YapLog.info("stale transcription dropped")
            return
        }

        guard let result, !result.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            YapLog.info(
                "Empty transcription [provider=\(transcriber.providerName) model=\(transcriber.modelName) source=\(source)]"
            )
            emit(
                recordingID: recordingID,
                source: source,
                wav: wav,
                recorderStopSeconds: recorderStopSeconds,
                transcriptionSeconds: transcriptionSeconds,
                totalSeconds: Self.now() - startedAt,
                success: false,
                error: "empty_transcript"
            )
            setState(.idle, source: "\(source):empty_transcript", recordingID: recordingID)
            return
        }

        YapLog.info(
            "Transcribed [\(result.language)] live=\(usedLive) transcription=\(String(format: "%.2f", transcriptionSeconds))s [provider=\(transcriber.providerName) model=\(transcriber.modelName) source=\(source) text_chars=\(result.text.count)]"
        )

        let text = result.text
        let outcome = paster.paste(text, target: target, delay: pasteDelay)
        if case .clipboardOnly(let reason) = outcome {
            YapLog.info("paste skipped: \(reason)")
            events.onNotice(reason)
        }
        history.prepend(text)
        events.onDictationComplete(text)

        let totalSeconds = Self.now() - startedAt
        YapLog.info(
            "Total pipeline: \(String(format: "%.2f", totalSeconds))s [source=\(source) recording=\(recordingID.map(String.init) ?? "-") transcription=\(String(format: "%.2f", transcriptionSeconds))s]"
        )
        emit(
            recordingID: recordingID,
            source: source,
            wav: wav,
            recorderStopSeconds: recorderStopSeconds,
            transcriptionSeconds: transcriptionSeconds,
            totalSeconds: totalSeconds,
            language: result.language,
            textChars: result.text.count,
            success: true,
            usedLive: usedLive
        )
        setState(.idle, source: "\(source):complete", recordingID: recordingID)
    }

    // MARK: - Helpers

    private func isCurrent(_ token: Int) -> Bool {
        token == turnToken
    }

    private func setState(_ newState: PipelineState, source: String, recordingID: Int? = nil) {
        let previous = state
        state = newState
        let id = recordingID ?? activeRecordingID
        if newState == .idle {
            activeRecordingID = nil
        }
        YapLog.info(
            "Pipeline transition \(previous.rawValue) -> \(newState.rawValue) [source=\(source) recording=\(id.map(String.init) ?? "-")]"
        )
        events.onStateChange(newState)
    }

    private func emit(
        recordingID: Int?,
        source: String,
        wav: Data?,
        recorderStopSeconds: TimeInterval,
        transcriptionSeconds: TimeInterval?,
        totalSeconds: TimeInterval,
        language: String = "",
        textChars: Int = 0,
        success: Bool,
        error: String = "",
        usedLive: Bool = false
    ) {
        let measurement = PipelineMeasurement(
            recordingID: recordingID,
            source: source,
            audioDurationSeconds: wav.flatMap(WAVCodec.duration),
            recorderStopSeconds: recorderStopSeconds,
            transcriptionSeconds: transcriptionSeconds,
            totalSeconds: totalSeconds,
            transcriptionProvider: transcriber.providerName,
            transcriptionModel: transcriber.modelName,
            language: language,
            textChars: textChars,
            success: success,
            error: error,
            usedLive: usedLive
        )
        metrics.append(measurement)
    }

    private func stashFailedRecording(_ wav: Data) {
        failedWAV = wav
        guard let url = failedRecordingURL else { return }
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try wav.write(to: url, options: .atomic)
            try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
            YapLog.info("Saved failed recording to \(url.lastPathComponent) (\(wav.count) bytes)")
        } catch {
            YapLog.warning("Failed to save failed recording: \(error.localizedDescription)")
        }
    }

    private func loadFailedRecording() -> Data? {
        if let failedWAV { return failedWAV }
        guard let url = failedRecordingURL else { return nil }
        return try? Data(contentsOf: url)
    }

    private func clearFailedRecording() {
        failedWAV = nil
        guard let url = failedRecordingURL else { return }
        try? FileManager.default.removeItem(at: url)
    }

    private static func now() -> TimeInterval {
        ProcessInfo.processInfo.systemUptime
    }
}

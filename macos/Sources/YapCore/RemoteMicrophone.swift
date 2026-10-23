import Foundation

public struct RemoteCaptureStats: Equatable, Sendable {
    public var frames: Int
    public var bytes: Int
    public var meanGapMilliseconds: Double

    public static let empty = RemoteCaptureStats(frames: 0, bytes: 0, meanGapMilliseconds: 0)
}

/// PCM pushed from a paired iPhone. Frames that arrive before `start` stay
/// queued and flush in order once the pipeline is listening. There is no
/// playback jitter buffer: dictation wants the samples as soon as they land.
public final class RemoteMicrophone: AudioRecording, @unchecked Sendable {
    private struct Callbacks {
        var onFrame: @Sendable (Data) -> Void
        var onFirstFrame: @Sendable () -> Void
        var onSilence: @Sendable () -> Void
    }

    private struct Pending {
        var frames: [Data]
        var callbacks: Callbacks
        var first: Bool
    }

    private let lock = NSLock()
    private var armed = false
    private var active = false
    private var callbacks: Callbacks?
    private var chunks: [Data] = []
    private var emitted = 0
    private var firstFrameSent = false
    private var levelValue = 0.0
    private var frameCount = 0
    private var byteCount = 0
    private var gapSum: TimeInterval = 0
    private var lastArrival: TimeInterval?
    public private(set) var lastStats = RemoteCaptureStats.empty

    public init() {}

    public var isRecording: Bool { lock.withLock { active } }
    public var audioLevel: Double { lock.withLock { levelValue } }

    /// Accept audio for the next press. Packets from before this are dropped.
    public func arm() {
        lock.withLock {
            armed = true
            active = false
            callbacks = nil
            chunks.removeAll(keepingCapacity: true)
            emitted = 0
            firstFrameSent = false
            levelValue = 0
            frameCount = 0
            byteCount = 0
            gapSum = 0
            lastArrival = nil
        }
    }

    public func disarm() {
        _ = lock.withLock { shutdownLocked() }
    }

    /// A capture buffer from the phone. Odd lengths are dropped.
    public func ingest(_ pcm: Data) {
        let pending = lock.withLock { () -> Pending? in
            guard armed, !pcm.isEmpty, pcm.count.isMultiple(of: 2) else { return nil }
            noteLocked(pcm)
            chunks.append(pcm)
            return drainLocked()
        }
        deliver(pending)
    }

    public func start(
        onFrame: @escaping @Sendable (Data) -> Void,
        onFirstFrame: @escaping @Sendable () -> Void,
        onSilence: @escaping @Sendable () -> Void
    ) throws {
        let pending: Pending? = try lock.withLock {
            if active {
                throw CaptureError(message: "microphone already active")
            }
            callbacks = Callbacks(onFrame: onFrame, onFirstFrame: onFirstFrame, onSilence: onSilence)
            active = true
            return drainLocked()
        }
        deliver(pending)
    }

    public func stop(abort: Bool) throws -> Data {
        let (pcm, stats) = lock.withLock { () -> (Data, RemoteCaptureStats) in
            let pcm = shutdownLocked()
            return (pcm, lastStats)
        }
        if stats.frames > 0 {
            YapLog.info(
                "iPhone audio frames=\(stats.frames) bytes=\(stats.bytes) mean_gap_ms=\(String(format: "%.1f", stats.meanGapMilliseconds))"
            )
        }
        return WAVCodec.encodeMonoPCM16(pcm, sampleRate: PhoneLink.sampleRate)
    }

    public func forceStop() {
        disarm()
    }

    private func noteLocked(_ pcm: Data) {
        let now = ProcessInfo.processInfo.systemUptime
        if let lastArrival {
            gapSum += now - lastArrival
        }
        lastArrival = now
        frameCount += 1
        byteCount += pcm.count

        var sum = 0.0
        pcm.withUnsafeBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for sample in samples {
                let unit = Double(sample) / 32767.0
                sum += unit * unit
            }
        }
        let rms = (sum / Double(max(pcm.count / 2, 1))).squareRoot()
        levelValue = min(rms * 20.0, 1.0)
    }

    private func drainLocked() -> Pending? {
        guard active, let callbacks, emitted < chunks.count else { return nil }
        let frames = Array(chunks[emitted...])
        let first = !firstFrameSent
        emitted = chunks.count
        if first { firstFrameSent = true }
        return Pending(frames: frames, callbacks: callbacks, first: first)
    }

    private func deliver(_ pending: Pending?) {
        guard let pending else { return }
        var first = pending.first
        for frame in pending.frames {
            pending.callbacks.onFrame(frame)
            if first {
                first = false
                pending.callbacks.onFirstFrame()
            }
        }
    }

    private func shutdownLocked() -> Data {
        let pcm = chunks.reduce(into: Data()) { $0.append($1) }
        let gaps = frameCount > 1 ? gapSum / Double(frameCount - 1) : 0
        lastStats = RemoteCaptureStats(
            frames: frameCount,
            bytes: byteCount,
            meanGapMilliseconds: gaps * 1_000
        )
        armed = false
        active = false
        callbacks = nil
        chunks.removeAll(keepingCapacity: true)
        emitted = 0
        firstFrameSent = false
        levelValue = 0
        return pcm
    }
}

private struct CaptureError: Error, LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

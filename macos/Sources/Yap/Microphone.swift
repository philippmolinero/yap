@preconcurrency import AVFoundation
import Foundation
import YapCore

/// Push-to-talk capture on AVAudioEngine: 16 kHz mono PCM16 frames, an
/// amplified level for the waveform, silence auto-stop, and a first-frame cue.
/// Frames stay in memory and leave as one WAV when the recording stops.
final class Microphone: AudioRecording, @unchecked Sendable {
    struct CaptureError: Error, LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    private struct Callbacks {
        var onFrame: @Sendable (Data) -> Void
        var onFirstFrame: @Sendable () -> Void
        var onSilence: @Sendable () -> Void
    }

    private let lock = NSLock()
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var chunks: [Data] = []
    private var callbacks: Callbacks?
    private var active = false
    private var levelValue = 0.0
    private var silenceStarted: TimeInterval?
    private var silenceFired = false
    private var firstFrameSent = false

    private let sampleRate: Double = 16_000
    private let silenceTimeout: TimeInterval
    private let silenceThreshold: Double

    init(silenceTimeout: TimeInterval, silenceThreshold: Double) {
        self.silenceTimeout = silenceTimeout
        self.silenceThreshold = silenceThreshold
    }

    var isRecording: Bool { lock.withLock { active } }

    /// Current amplified level from 0.0 (quiet) to 1.0 (loud).
    var audioLevel: Double { lock.withLock { levelValue } }

    private var targetFormat: AVAudioFormat {
        AVAudioFormat(commonFormat: .pcmFormatFloat32, sampleRate: sampleRate, channels: 1, interleaved: false)!
    }

    func start(
        onFrame: @escaping @Sendable (Data) -> Void,
        onFirstFrame: @escaping @Sendable () -> Void,
        onSilence: @escaping @Sendable () -> Void
    ) throws {
        guard !isRecording else {
            throw CaptureError(message: "microphone already active")
        }
        lock.withLock {
            chunks = []
            levelValue = 0
            silenceStarted = nil
            silenceFired = false
            firstFrameSent = false
            callbacks = Callbacks(onFrame: onFrame, onFirstFrame: onFirstFrame, onSilence: onSilence)
        }

        let input = engine.inputNode
        let inputFormat = input.outputFormat(forBus: 0)
        guard inputFormat.sampleRate > 0 else {
            lock.withLock { callbacks = nil }
            throw CaptureError(message: "no audio input available")
        }
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            lock.withLock { callbacks = nil }
            throw CaptureError(message: "audio converter unavailable")
        }
        self.converter = converter

        input.installTap(onBus: 0, bufferSize: 2048, format: inputFormat) { [weak self] buffer, _ in
            self?.consume(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            self.converter = nil
            lock.withLock { callbacks = nil }
            throw CaptureError(message: error.localizedDescription)
        }
        lock.withLock { active = true }
        YapLog.info("Microphone started")
    }

    func stop(abort: Bool) throws -> Data {
        let (pcm, wasActive) = lock.withLock { () -> (Data, Bool) in
            let data = chunks.reduce(into: Data()) { $0.append($1) }
            chunks = []
            let wasActive = active
            active = false
            levelValue = 0
            silenceStarted = nil
            silenceFired = false
            firstFrameSent = false
            callbacks = nil
            return (data, wasActive)
        }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
        YapLog.info("Microphone stopped active=\(wasActive) bytes=\(pcm.count)")
        return WAVCodec.encodeMonoPCM16(pcm, sampleRate: Int(sampleRate))
    }

    func forceStop() {
        lock.withLock {
            active = false
            chunks = []
            levelValue = 0
            silenceStarted = nil
            silenceFired = false
            firstFrameSent = false
            callbacks = nil
        }
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
        converter = nil
    }

    // MARK: - Audio tap

    private func consume(_ buffer: AVAudioPCMBuffer) {
        guard let converter else { return }
        let ratio = targetFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let output = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: capacity) else { return }

        let claim = InputClaim()
        var conversionError: NSError?
        converter.convert(to: output, error: &conversionError) { _, status in
            guard claim.claim() else {
                status.pointee = .noDataNow
                return nil
            }
            status.pointee = .haveData
            return buffer
        }
        guard conversionError == nil,
              output.frameLength > 0,
              let channel = output.floatChannelData?[0] else { return }

        let count = Int(output.frameLength)
        var sum = 0.0
        var pcm = Data(count: count * MemoryLayout<Int16>.size)
        pcm.withUnsafeMutableBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for index in 0..<count {
                let sample = max(-1.0, min(1.0, Double(channel[index])))
                sum += sample * sample
                samples[index] = Int16((sample * 32767.0).rounded())
            }
        }

        let outcome: (callbacks: Callbacks?, first: Bool, silence: Bool) = lock.withLock {
            let wasFirst = !firstFrameSent
            firstFrameSent = true
            chunks.append(pcm)

            let rms = (sum / Double(max(count, 1))).squareRoot()
            levelValue = min(rms * 20.0, 1.0)

            var fireSilence = false
            if silenceTimeout > 0, !silenceFired {
                if rms < silenceThreshold {
                    if silenceStarted == nil {
                        silenceStarted = ProcessInfo.processInfo.systemUptime
                    }
                } else {
                    silenceStarted = nil
                }
                if let started = silenceStarted,
                   ProcessInfo.processInfo.systemUptime - started >= silenceTimeout {
                    silenceFired = true
                    fireSilence = true
                }
            }
            return (callbacks, wasFirst, fireSilence)
        }

        guard let callbacks = outcome.callbacks else { return }
        callbacks.onFrame(pcm)
        if outcome.first {
            callbacks.onFirstFrame()
        }
        if outcome.silence {
            YapLog.info("Silence detected — auto-stopping")
            callbacks.onSilence()
        }
    }
}

/// One-shot flag for the AVAudioConverter input callback (which is @Sendable).
final class InputClaim: @unchecked Sendable {
    private let lock = NSLock()
    private var claimed = false

    func claim() -> Bool {
        lock.withLock {
            if claimed { return false }
            claimed = true
            return true
        }
    }
}

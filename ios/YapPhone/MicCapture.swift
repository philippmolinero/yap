import AVFoundation
import Foundation

/// 16 kHz mono PCM16 from the phone mic. The session stays active between
/// presses so the next hold does not pay audio-session startup. Each hardware
/// buffer is converted and handed off immediately.
final class MicCapture: @unchecked Sendable {
    private let engine = AVAudioEngine()
    private var converter: AVAudioConverter?
    private var warmed = false
    private let target = AVAudioFormat(
        commonFormat: .pcmFormatFloat32,
        sampleRate: Double(PhoneLink.sampleRate),
        channels: 1,
        interleaved: false
    )!

    private var tapOn = false

    func warm() throws {
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.record, mode: .measurement, options: [])
        } catch {
            try session.setCategory(.record, mode: .default, options: [])
        }
        try session.setPreferredSampleRate(48_000)
        try session.setPreferredIOBufferDuration(0.005)
        try session.setActive(true)
        warmed = true
    }

    /// Leave the tap running so a locked phone still hears the Mac hotkey.
    func arm(_ onFrame: @escaping @Sendable (Data) -> Void) throws {
        if tapOn { return }
        if !warmed { try warm() }
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else {
            throw MicCaptureError("no audio input")
        }
        guard let converter = AVAudioConverter(from: format, to: target) else {
            throw MicCaptureError("audio converter unavailable")
        }
        self.converter = converter
        input.installTap(onBus: 0, bufferSize: 256, format: format) { [weak self] buffer, _ in
            guard let self, let pcm = self.convert(buffer), !pcm.isEmpty else { return }
            onFrame(pcm)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            self.converter = nil
            throw error
        }
        tapOn = true
    }

    func stop() {
        guard tapOn else { return }
        tapOn = false
        engine.inputNode.removeTap(onBus: 0)
        converter = nil
        if engine.isRunning {
            engine.stop()
        }
    }

    private func convert(_ buffer: AVAudioPCMBuffer) -> Data? {
        guard let converter else { return nil }
        let ratio = target.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 32
        guard let output = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: capacity) else { return nil }
        let claim = InputClaim()
        var error: NSError?
        converter.convert(to: output, error: &error) { _, status in
            guard claim.claim() else {
                status.pointee = .noDataNow
                return nil
            }
            status.pointee = .haveData
            return buffer
        }
        guard error == nil, output.frameLength > 0, let channel = output.floatChannelData?[0] else { return nil }
        let count = Int(output.frameLength)
        var pcm = Data(count: count * MemoryLayout<Int16>.size)
        pcm.withUnsafeMutableBytes { raw in
            let samples = raw.bindMemory(to: Int16.self)
            for index in 0..<count {
                let sample = max(-1.0, min(1.0, Double(channel[index])))
                samples[index] = Int16((sample * 32_767.0).rounded())
            }
        }
        return pcm
    }
}

private struct MicCaptureError: Error, LocalizedError {
    let message: String
    init(_ message: String) { self.message = message }
    var errorDescription: String? { message }
}

private final class InputClaim: @unchecked Sendable {
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

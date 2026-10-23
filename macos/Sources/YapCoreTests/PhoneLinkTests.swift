import Foundation
import YapCore

func phoneLinkSuite() -> Suite {
    let suite = Suite("iPhone link")

    suite.test("messages round trip") {
        var decoder = PhoneLink.Decoder()
        var blob = PhoneLink.encode(.hello(pin: "123456", deviceName: "Phil\nipp"))
        blob.append(PhoneLink.encode(.ready))
        blob.append(PhoneLink.encode(.audio(Data([1, 2, 3, 4]))))
        blob.append(PhoneLink.encode(.stop))
        let messages = try decoder.append(blob)
        try expect(messages == [
            .hello(pin: "123456", deviceName: "Phil ipp"),
            .ready,
            .audio(Data([1, 2, 3, 4])),
            .stop,
        ])
    }

    suite.test("a split header is completed by the next read") {
        var decoder = PhoneLink.Decoder()
        let encoded = PhoneLink.encode(.rejected)
        try expect(try decoder.append(encoded.prefix(3)).isEmpty)
        let rest = encoded.suffix(from: encoded.index(encoded.startIndex, offsetBy: 3))
        try expect(try decoder.append(rest) == [.rejected])
    }

    suite.test("an oversized frame fails the stream") {
        var decoder = PhoneLink.Decoder()
        var header = Data([4])
        header.append(contentsOf: [0x00, 0x02, 0x00, 0x00])
        do {
            _ = try decoder.append(header)
            throw TestFailure(description: "oversized frame was accepted")
        } catch let error as PhoneLink.Failure {
            try expect(error == .oversized)
        }
    }

    suite.test("a hello without a code is malformed") {
        var decoder = PhoneLink.Decoder()
        let payload = Data("nope".utf8)
        var frame = Data([1])
        frame.append(contentsOf: [0, 0, 0, UInt8(payload.count)])
        frame.append(payload)
        do {
            _ = try decoder.append(frame)
            throw TestFailure(description: "malformed hello was accepted")
        } catch let error as PhoneLink.Failure {
            try expect(error == .malformed)
        }
    }

    suite.test("frames that arrive before start flush in order") {
        let mic = RemoteMicrophone()
        let box = FrameBox()
        mic.arm()
        mic.ingest(Data([1, 0]))
        mic.ingest(Data([2, 0]))
        try mic.start(
            onFrame: { box.add($0) },
            onFirstFrame: { box.markFirst() },
            onSilence: {}
        )
        mic.ingest(Data([3, 0]))
        let wav = try mic.stop(abort: false)
        try expect(box.frames == [Data([1, 0]), Data([2, 0]), Data([3, 0])])
        try expect(box.firstCount == 1)
        let duration = try require(WAVCodec.duration(wav))
        try expect(abs(duration - (6.0 / 32_000.0)) < 0.0000001)
    }

    suite.test("audio before arm is ignored") {
        let mic = RemoteMicrophone()
        let box = FrameBox()
        mic.ingest(Data([9, 0]))
        mic.arm()
        try mic.start(onFrame: { box.add($0) }, onFirstFrame: {}, onSilence: {})
        let wav = try mic.stop(abort: false)
        try expect(box.frames.isEmpty)
        try expect(wav.isEmpty)
    }

    suite.test("an odd-sized frame is dropped") {
        let mic = RemoteMicrophone()
        let box = FrameBox()
        mic.arm()
        mic.ingest(Data([1]))
        try mic.start(onFrame: { box.add($0) }, onFirstFrame: {}, onSilence: {})
        let wav = try mic.stop(abort: false)
        try expect(box.frames.isEmpty)
        try expect(wav.isEmpty)
    }

    return suite
}

private final class FrameBox: @unchecked Sendable {
    private let lock = NSLock()
    private var stored: [Data] = []
    private var first = 0

    var frames: [Data] { lock.withLock { stored } }
    var firstCount: Int { lock.withLock { first } }

    func add(_ data: Data) { lock.withLock { stored.append(data) } }
    func markFirst() { lock.withLock { first += 1 } }
}

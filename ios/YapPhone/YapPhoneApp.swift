import SwiftUI
import UIKit

@main
struct YapPhoneApp: App {
    var body: some Scene {
        WindowGroup {
            TalkView()
        }
    }
}

@MainActor
@Observable
final class TalkModel {
    var pin = ""
    var status = "Searching for Yap…"
    var paired = false
    var holding = false
    private let client = PhoneClient()
    private let mic = MicCapture()
    private var started = false

    func onAppear() {
        guard !started else { return }
        started = true
        client.setHandler { [weak self] event in
            Task { @MainActor in self?.apply(event) }
        }
        client.start()
    }

    func pinChanged(_ raw: String) {
        let digits = String(raw.filter(\.isNumber).prefix(6))
        if digits != pin { pin = digits }
        client.setPIN(pin)
    }

    func pressDown() {
        guard paired, !holding else { return }
        holding = true
        status = "Listening"
        client.beginForwarding()
    }

    func pressUp() {
        guard holding else { return }
        holding = false
        client.endForwarding()
        status = paired ? "Ready. Use the Mac key." : status
    }

    private func apply(_ event: PhoneClientEvent) {
        switch event {
        case .status(let text):
            if !holding { status = text }
        case .paired(let value):
            paired = value
            if value {
                armMic()
                if !holding { status = "Ready. Use the Mac key." }
            } else {
                holding = false
                mic.stop()
                status = "Disconnected"
            }
        case .capture:
            status = "Listening"
        case .release:
            if !holding { status = paired ? "Ready. Use the Mac key." : status }
        }
    }

    private func armMic() {
        do {
            try mic.arm { [client] pcm in
                client.sendAudio(pcm)
            }
        } catch {
            status = error.localizedDescription
        }
    }
}

struct TalkView: View {
    @State private var model = TalkModel()

    var body: some View {
        VStack(spacing: 28) {
            VStack(spacing: 8) {
                Text("Yap")
                    .font(.largeTitle.weight(.semibold))
                Text(model.status)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
            }

            TextField("Pairing code", text: Binding(
                get: { model.pin },
                set: { model.pinChanged($0) }
            ))
            .keyboardType(.numberPad)
            .textContentType(.oneTimeCode)
            .multilineTextAlignment(.center)
            .font(.system(size: 32, weight: .medium, design: .rounded))
            .padding(.vertical, 12)
            .background(Color.primary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
            .disabled(model.holding)

            HoldButton(enabled: model.paired, holding: model.holding) {
                model.pressDown()
            } onUp: {
                model.pressUp()
            }
            .frame(width: 220, height: 220)
        }
        .padding(28)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(uiColor: .systemBackground))
        .onAppear { model.onAppear() }
    }
}

private struct HoldButton: UIViewRepresentable {
    var enabled: Bool
    var holding: Bool
    var onDown: () -> Void
    var onUp: () -> Void

    func makeUIView(context: Context) -> HoldControl {
        let view = HoldControl()
        view.onDown = onDown
        view.onUp = onUp
        return view
    }

    func updateUIView(_ view: HoldControl, context: Context) {
        view.onDown = onDown
        view.onUp = onUp
        if view.isTrackingTouch && !enabled {
            view.isTrackingTouch = false
            onUp()
        }
        view.isEnabled = enabled
        view.holding = holding
        view.setNeedsDisplay()
    }
}

private final class HoldControl: UIControl {
    var onDown: () -> Void = {}
    var onUp: () -> Void = {}
    var isTrackingTouch = false
    var holding = false {
        didSet { setNeedsDisplay() }
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        isOpaque = false
        backgroundColor = .clear
    }

    required init?(coder: NSCoder) { nil }

    override func draw(_ rect: CGRect) {
        let diameter = min(bounds.width, bounds.height)
        let circle = CGRect(
            x: (bounds.width - diameter) / 2,
            y: (bounds.height - diameter) / 2,
            width: diameter,
            height: diameter
        ).insetBy(dx: 2, dy: 2)
        let fill = holding ? UIColor.label : UIColor.secondarySystemFill
        fill.setFill()
        UIBezierPath(ovalIn: circle).fill()
        let title = holding ? "Listening" : "Hold"
        let color = holding ? UIColor.systemBackground : (isEnabled ? UIColor.label : UIColor.tertiaryLabel)
        let attributes: [NSAttributedString.Key: Any] = [
            .font: UIFont.systemFont(ofSize: 28, weight: .semibold),
            .foregroundColor: color,
        ]
        let text = title as NSString
        let size = text.size(withAttributes: attributes)
        text.draw(
            at: CGPoint(x: bounds.midX - size.width / 2, y: bounds.midY - size.height / 2),
            withAttributes: attributes
        )
    }

    override func touchesBegan(_ touches: Set<UITouch>, with event: UIEvent?) {
        guard isEnabled, !isTrackingTouch else { return }
        isTrackingTouch = true
        onDown()
    }

    override func touchesEnded(_ touches: Set<UITouch>, with event: UIEvent?) {
        endTouch()
    }

    override func touchesCancelled(_ touches: Set<UITouch>, with event: UIEvent?) {
        endTouch()
    }

    private func endTouch() {
        guard isTrackingTouch else { return }
        isTrackingTouch = false
        onUp()
    }
}

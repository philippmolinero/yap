import SwiftUI
import YapCore

// MARK: - Palette

private enum Palette {
    static let surface = Color(red: 0x17 / 255.0, green: 0x15 / 255.0, blue: 0x12 / 255.0)
    static let sage = Color(red: 0xBF / 255.0, green: 0xE7 / 255.0, blue: 0xA5 / 255.0)
    static let parchment = Color(red: 0xF5 / 255.0, green: 0xF0 / 255.0, blue: 0xE8 / 255.0)
}

// MARK: - Model

@MainActor
@Observable
final class OverlayModel {
    enum State {
        case hidden
        case recording
        case processing
    }

    var state: State = .hidden
    var label = "Listening"
    var visible = false

    // Waveform smoothing state, driven at animation rate.
    private(set) var bars: [Double] = Array(repeating: OverlayGeometry.minBar, count: OverlayGeometry.barCount)
    private var phase = 0.0

    func tick(level rawLevel: Double) {
        phase += 0.16
        let level = max(0, min(rawLevel, 1))
        let count = OverlayGeometry.barCount
        for index in 0..<count {
            let distance = abs(Double(index) - Double(count - 1) / 2)
            let centerWeight = 1.0 - (distance / max(Double(count - 1) / 2, 1)) * 0.42
            let variation = 0.58 + 0.42 * sin(phase + Double(index) * 0.92)
            let idleBreath = 0.5 + 0.5 * sin(phase * 0.7 + Double(index) * 0.45)
            let targetLevel = max(level, 0.05 * idleBreath)
            let target = OverlayGeometry.minBar
                + (OverlayGeometry.maxBar - OverlayGeometry.minBar) * targetLevel * variation * centerWeight

            let current = bars[index]
            if target > current {
                bars[index] = current + (target - current) * 0.48
            } else {
                bars[index] = current + (target - current) * 0.24
            }
        }
    }

    func resetBars() {
        bars = Array(repeating: OverlayGeometry.minBar, count: OverlayGeometry.barCount)
        phase = 0
    }
}

enum OverlayGeometry {
    static let barCount = 11
    static let minBar = 3.0
    static let maxBar = 24.0
}

// MARK: - Capsule view

struct OverlayCapsuleView: View {
    var model: OverlayModel

    var body: some View {
        HStack(spacing: 12) {
            ListeningDot(recording: model.state == .recording)
                .frame(width: 12, height: 12)

            Rectangle()
                .fill(Palette.parchment.opacity(0.16))
                .frame(width: 1, height: 20)

            Text(model.label)
                .font(.system(size: 15, weight: .medium))
                .foregroundStyle(Palette.parchment.opacity(0.96))
                .frame(width: 84, alignment: .leading)

            ZStack {
                switch model.state {
                case .recording:
                    WaveformView(bars: model.bars)
                case .processing:
                    SpinnerView()
                case .hidden:
                    Color.clear
                }
            }
            .frame(width: 110, height: 30)
        }
        .padding(.horizontal, 21)
        .frame(width: 286, height: 46)
        .background(capsule)
        .scaleEffect(model.visible ? 1 : 0.86)
        .opacity(model.visible ? 1 : 0)
        .padding(12)
        .animation(.spring(response: 0.24, dampingFraction: 0.82), value: model.visible)
        .animation(.spring(response: 0.24, dampingFraction: 0.82), value: model.state)
    }

    private var capsule: some View {
        Capsule(style: .continuous)
            .fill(Palette.surface.opacity(0.94))
            .overlay(
                Capsule(style: .continuous)
                    .stroke(Palette.parchment.opacity(0.14), lineWidth: 1)
            )
            .shadow(color: Palette.sage.opacity(0.16), radius: 18)
    }
}

// MARK: - Parts

private struct ListeningDot: View {
    var recording: Bool

    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { timeline in
            let seconds = timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
                let pulse = recording ? 0.5 + 0.5 * sin(seconds * 4.2) : 0
                let glowInset = max(0, 0.5 - pulse * 2)

                if recording {
                    let glow = Path(
                        ellipseIn: CGRect(
                            x: glowInset,
                            y: glowInset,
                            width: size.width - glowInset * 2,
                            height: size.height - glowInset * 2
                        )
                    )
                    context.fill(glow, with: .color(Palette.sage.opacity(0.12 + pulse * 0.22)))
                }

                let inset: CGFloat = recording ? 3.5 : 4.5
                let dot = Path(
                    ellipseIn: CGRect(
                        x: inset,
                        y: inset,
                        width: size.width - inset * 2,
                        height: size.height - inset * 2
                    )
                )
                context.fill(
                    dot,
                    with: .color(recording ? Palette.sage.opacity(0.96) : Palette.parchment.opacity(0.30))
                )
            }
        }
    }
}

private struct WaveformView: View {
    var bars: [Double]

    var body: some View {
        Canvas { context, size in
            let barWidth: CGFloat = 3.5
            let gap: CGFloat = 5
            let totalWidth = CGFloat(bars.count) * barWidth + CGFloat(bars.count - 1) * gap
            let startX = (size.width - totalWidth) / 2

            for (index, height) in bars.enumerated() {
                let barHeight = CGFloat(height)
                let x = startX + CGFloat(index) * (barWidth + gap)
                let y = (size.height - barHeight) / 2
                let intensity = (height - OverlayGeometry.minBar)
                    / max(OverlayGeometry.maxBar - OverlayGeometry.minBar, 1)
                let rect = CGRect(x: x, y: y, width: barWidth, height: barHeight)
                let bar = Path(roundedRect: rect, cornerRadius: barWidth / 2)
                context.fill(
                    bar,
                    with: .color(Palette.sage.opacity(0.60 + 0.36 * min(max(intensity, 0), 1)))
                )
            }
        }
    }
}

private struct SpinnerView: View {
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 20.0)) { timeline in
            let seconds = timeline.date.timeIntervalSinceReferenceDate
            Canvas { context, size in
            let angleOffset = -seconds * 6.0
                let radius: CGFloat = 8
                let dotSize: CGFloat = 2.7
                let count = 8
                let center = CGPoint(x: size.width / 2, y: size.height / 2)

                for index in 0..<count {
                    let angle = angleOffset + 2 * .pi * Double(index) / Double(count)
                    let x = center.x + radius * cos(angle) - dotSize / 2
                    let y = center.y + radius * sin(angle) - dotSize / 2
                    let dot = Path(ellipseIn: CGRect(x: x, y: y, width: dotSize, height: dotSize))
                    let trail = 0.14 + 0.68 * (Double(index) / Double(count))
                    context.fill(dot, with: .color(Palette.parchment.opacity(trail)))
                }
            }
        }
    }
}

// MARK: - Window

/// Borderless always-on-top capsule at the bottom of the main screen.
@MainActor
final class OverlayWindowController {
    let model = OverlayModel()

    private var panel: NSPanel?
    private var levelTimer: Timer?

    func show(_ state: OverlayModel.State, label: String, level: @escaping @Sendable () -> Double) {
        model.label = label
        model.state = state
        if state == .recording {
            model.resetBars()
            startLevelTimer(level: level)
        } else {
            stopLevelTimer()
        }
        presentPanel()
        model.visible = true
    }

    func hide() {
        stopLevelTimer()
        model.visible = false
        model.state = .hidden
        let panel = self.panel
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { [weak self] in
            guard let self, !self.model.visible else { return }
            panel?.orderOut(nil)
        }
    }

    private func presentPanel() {
        let panel = ensurePanel()
        position(panel)
        panel.alphaValue = 1
        panel.orderFrontRegardless()
    }

    private func ensurePanel() -> NSPanel {
        if let panel { return panel }
        let size = NSSize(width: 310, height: 70)
        let panel = NSPanel(
            contentRect: NSRect(origin: .zero, size: size),
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        panel.level = .floating
        panel.hasShadow = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.ignoresMouseEvents = true
        panel.isMovable = false
        panel.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary]
        panel.contentView = NSHostingView(rootView: OverlayCapsuleView(model: model))
        self.panel = panel
        return panel
    }

    private func position(_ panel: NSPanel) {
        guard let screen = NSScreen.main else { return }
        let visible = screen.visibleFrame
        let size = panel.frame.size
        let x = visible.midX - size.width / 2
        let y = visible.minY + 68
        panel.setFrameOrigin(NSPoint(x: x, y: y))
    }

    private func startLevelTimer(level: @escaping @Sendable () -> Double) {
        stopLevelTimer()
        let timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 20.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.model.tick(level: level()) }
        }
        RunLoop.main.add(timer, forMode: .common)
        levelTimer = timer
    }

    private func stopLevelTimer() {
        levelTimer?.invalidate()
        levelTimer = nil
    }
}

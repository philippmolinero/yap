import AppKit
import SwiftUI
import YapCore

@main
enum YapMain {
    static func main() {
        let arguments = CommandLine.arguments
        if arguments.contains("--transcribe") {
            exit(TranscribeCommand.run(arguments: arguments))
        }
        if arguments.contains("--doctor") {
            exit(DoctorCommand.run())
        }

        guard SingleInstanceLock.acquire() else {
            fputs("Yap is already running.\n", stderr)
            exit(0)
        }
        YapApplication.main()
    }
}

struct YapApplication: App {
    @State private var model = AppModel()

    var body: some Scene {
        MenuBarExtra {
            YapMenu(model: model)
        } label: {
            MenuBarLabel(model: model)
        }
        .menuBarExtraStyle(.menu)

        Settings {
            SettingsView(model: model)
        }
    }
}

struct MenuBarLabel: View {
    var model: AppModel

    private static let icon: NSImage? = {
        guard let url = AppResources.url("icon_menubar", extension: "png"),
              let image = NSImage(contentsOf: url) else { return nil }
        // The bundled art is 44x44 px at 72 dpi with *asymmetric* transparent
        // margins (glyph occupies y 6...35 of 44), so a centered canvas renders
        // the glyph off-center. Crop to the visible glyph and scale that to the
        // standard menu bar height.
        return image.menuBarGlyph(height: 16)
    }()

    var body: some View {
        if model.isRecording || model.isProcessing {
            Image(systemName: "waveform")
        } else if let icon = Self.icon {
            Image(nsImage: icon)
        } else {
            Image(systemName: "mic")
        }
    }
}

struct YapMenu: View {
    var model: AppModel

    var body: some View {
        Button("Status: \(model.statusText)") {}
            .disabled(true)

        if model.isRecording {
            Button("Stop Recording") { model.stopRecording() }
        }
        if model.hasFailedRecording {
            Button("Retry Failed Dictation") { model.retryFailedDictation() }
        }

        Divider()

        Menu("Recent") {
            if model.recent.isEmpty {
                Button("Empty") {}
                    .disabled(true)
            } else {
                ForEach(Array(model.recent.enumerated()), id: \.offset) { _, text in
                    Button(model.clip(text, to: 50)) { model.pasteRecent(text) }
                }
            }
        }

        Divider()

        SettingsLink {
            Text("Settings…")
        }
        Button("Open Vocabulary") { model.openVocabulary() }

        Divider()

        Button("Quit Yap") { model.quit() }
    }
}

private extension NSImage {
    /// The visible glyph only: transparent margins cropped, content scaled to
    /// `height` points. Cropping is what makes a centered menu bar icon look
    /// centered — the bundled art carries asymmetric padding.
    func menuBarGlyph(height: CGFloat) -> NSImage {
        guard let rep = bitmapRepresentation,
              let cgImage = rep.cgImage,
              let content = opaquePixelBounds(in: rep),
              let cropped = cgImage.cropping(to: content) else {
            let factor = height / max(size.height, 1)
            size = NSSize(width: (size.width * factor).rounded(), height: height)
            return self
        }

        let target = NSSize(
            width: (CGFloat(content.width) * height / CGFloat(content.height)).rounded(),
            height: height
        )
        let glyph = NSImage(size: target)
        glyph.lockFocus()
        NSGraphicsContext.current?.imageInterpolation = .high
        NSImage(cgImage: cropped, size: target)
            .draw(in: NSRect(origin: .zero, size: target))
        glyph.unlockFocus()
        glyph.isTemplate = true
        return glyph
    }

    private var bitmapRepresentation: NSBitmapImageRep? {
        guard let tiff = tiffRepresentation else { return nil }
        return NSBitmapImageRep(data: tiff)
    }

    /// Pixel rect of the non-transparent region, in CGImage coordinates
    /// (origin top-left, matching `cropping(to:)`).
    private func opaquePixelBounds(in rep: NSBitmapImageRep) -> CGRect? {
        let width = rep.pixelsWide
        let height = rep.pixelsHigh
        guard width > 0, height > 0 else { return nil }

        // NSBitmapImageRep.colorAt uses bottom-left origin; CGImage.cropping
        // uses top-left. Scan in rep coordinates and convert at the end.
        var minX = width
        var maxX = -1
        var minY = height
        var maxY = -1
        for y in 0..<height {
            for x in 0..<width where (rep.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.05 {
                minX = min(minX, x)
                maxX = max(maxX, x)
                minY = min(minY, y)
                maxY = max(maxY, y)
            }
        }
        guard maxX >= minX, maxY >= minY else { return nil }

        let flippedY = height - 1 - maxY
        return CGRect(
            x: minX,
            y: flippedY,
            width: maxX - minX + 1,
            height: maxY - minY + 1
        )
    }
}

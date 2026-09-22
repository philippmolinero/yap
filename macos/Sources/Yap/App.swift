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
        image.isTemplate = true
        // SwiftUI renders menu bar images at their literal point size, and this
        // PNG is 44x44 px at 72 dpi with large transparent margins (the visible
        // glyph is only ~21x30 px). Scale by the visible glyph, not the canvas.
        return image.normalizedToGlyphHeight(16)
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
    /// Scale the image so its *visible* glyph reaches `height` points, keeping
    /// the aspect ratio. Menu bar artwork usually ships with transparent
    /// padding, and SwiftUI renders menu bar images at their literal size.
    func normalizedToGlyphHeight(_ height: CGFloat) -> NSImage {
        let glyphHeight = opaqueBoundsHeight
        guard glyphHeight > 0 else {
            let aspect = size.width / max(size.height, 1)
            size = NSSize(width: (height * aspect).rounded(), height: height)
            return self
        }
        let factor = height / glyphHeight
        size = NSSize(
            width: (size.width * factor).rounded(),
            height: (size.height * factor).rounded()
        )
        return self
    }

    /// Height of the non-transparent region, in the image's own units.
    private var opaqueBoundsHeight: CGFloat {
        guard let tiff = tiffRepresentation,
              let rep = NSBitmapImageRep(data: tiff) else { return 0 }
        let width = rep.pixelsWide
        let height = rep.pixelsHigh
        var minY = height
        var maxY = -1
        for y in 0..<height {
            for x in 0..<width where (rep.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.05 {
                minY = min(minY, y)
                maxY = max(maxY, y)
                break
            }
        }
        guard maxY >= minY else { return 0 }
        let pixelsPerPoint = CGFloat(height) / max(size.height, 1)
        return CGFloat(maxY - minY + 1) / max(pixelsPerPoint, 1)
    }
}

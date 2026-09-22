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
        // The source PNG is 44x44 px at 72 dpi, so NSImage reads it as 44 pt
        // tall. The menu bar wants a ~15 pt glyph: normalize the point size and
        // keep the aspect ratio.
        let targetHeight: CGFloat = 15
        let aspect = image.size.width / max(image.size.height, 1)
        image.size = NSSize(width: (targetHeight * aspect).rounded(), height: targetHeight)
        return image
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

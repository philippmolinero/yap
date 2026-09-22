import ServiceManagement
import SwiftUI
import YapCore

struct SettingsView: View {
    var model: AppModel

    @State private var apiKey = ""
    @State private var silenceEnabled = true

    var body: some View {
        Form {
            Section("Gemini") {
                SecureField("API key", text: $apiKey, onCommit: {
                    model.saveAPIKey(apiKey)
                })
                .textFieldStyle(.roundedBorder)

                Text(model.missingAPIKey
                    ? "No API key stored — dictation is disabled."
                    : "Stored in your Keychain.")
                    .font(.caption)
                    .foregroundStyle(model.missingAPIKey ? .red : .secondary)
            }

            Section("Dictation") {
                Picker("Mode", selection: modeBinding) {
                    ForEach(TranscriptionMode.allCases, id: \.self) { mode in
                        Text(mode.displayName).tag(mode)
                    }
                }

                Picker("Language", selection: languageBinding) {
                    Text("Auto-detect").tag("")
                    Text("English").tag("en")
                    Text("Deutsch").tag("de")
                    Text("ไทย").tag("th")
                }

                Picker("Trigger key", selection: triggerBinding) {
                    Text("Right Option").tag([61])
                    Text("Right Control").tag([62])
                    Text("Right Option + Right Control").tag([61, 62])
                }

                Text("Hold the trigger to dictate. Double-tap for hands-free mode.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Silence auto-stop") {
                Toggle("Stop recording after silence", isOn: $silenceEnabled)
                    .onChange(of: silenceEnabled) { _, enabled in
                        model.updateSilenceTimeout(enabled ? 5.0 : 0)
                    }
                if silenceEnabled {
                    HStack {
                        Text("After")
                        Slider(
                            value: silenceTimeoutBinding,
                            in: 2...20,
                            step: 1
                        ) { editing in
                            if !editing { model.refreshPermissions() }
                        }
                        Text("\(Int(model.config.silence.timeout)) s")
                            .monospacedDigit()
                            .frame(width: 34, alignment: .trailing)
                    }
                }
            }

            Section("Permissions") {
                ForEach(Permissions.Kind.allCases, id: \.self) { kind in
                    PermissionRow(kind: kind, model: model)
                }
            }

            Section("Startup") {
                Toggle("Launch at Login", isOn: launchAtLoginBinding)
            }

            Section {
                HStack {
                    Button("Open Vocabulary File") { model.openVocabulary() }
                    Button("Open Log File") { model.openLog() }
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 520)
        .onAppear {
            apiKey = model.apiKeyDraft
            silenceEnabled = model.config.silence.timeout > 0
        }
    }

    // MARK: - Bindings

    private var modeBinding: Binding<TranscriptionMode> {
        Binding(
            get: { model.config.transcription.mode },
            set: { model.updateMode($0) }
        )
    }

    private var languageBinding: Binding<String> {
        Binding(
            get: { model.config.transcription.language },
            set: { model.updateLanguage($0) }
        )
    }

    private var triggerBinding: Binding<[Int]> {
        Binding(
            get: { model.config.hotkey.keycodes },
            set: { model.updateTrigger($0) }
        )
    }

    private var silenceTimeoutBinding: Binding<Double> {
        Binding(
            get: { model.config.silence.timeout },
            set: { model.updateSilenceTimeout(max($0, 1)) }
        )
    }

    private var launchAtLoginBinding: Binding<Bool> {
        Binding(
            get: { model.launchAtLogin },
            set: { model.setLaunchAtLogin($0) }
        )
    }
}

private struct PermissionRow: View {
    var kind: Permissions.Kind
    var model: AppModel

    private var granted: Bool {
        model.permissionStatus[kind] ?? false
    }

    var body: some View {
        HStack {
            Image(systemName: granted ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(granted ? Color.green : Color.orange)
            VStack(alignment: .leading, spacing: 2) {
                Text(kind.displayName)
                Text(kind.rationale)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if granted {
                Text("Granted")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Button("Open Settings") { model.openPermissionSettings(kind) }
                Button("Request") { model.requestPermission(kind) }
            }
        }
    }
}

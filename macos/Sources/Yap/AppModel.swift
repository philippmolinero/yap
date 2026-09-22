import AppKit
import ServiceManagement
import SwiftUI
import YapCore

/// Wires the core pipeline to the macOS shell: menu, overlay, sounds, hotkey,
/// permissions, sleep/wake, and settings.
@MainActor
@Observable
final class AppModel {
    // MARK: - UI state

    var statusText = "Idle"
    var recent: [String] = []
    var hasFailedRecording = false
    var isRecording = false
    var isProcessing = false
    var missingAPIKey = false
    var apiKeyDraft = ""
    var permissionStatus: [Permissions.Kind: Bool] = [:]
    var launchAtLogin = false
    var config: AppConfig

    // MARK: - Components

    private let keyStore: any GeminiKeyStoring
    private let history = FileHistoryStore()
    private let paster = MacPaster()
    private let sounds = SoundFeedback()
    private let overlay = OverlayWindowController()
    private let systemEvents = SystemEvents()
    private var microphone: Microphone
    private var hotkey: HotkeyMonitor
    private var pipeline: DictationPipeline!
    private var permissionTimer: Timer?
    private var pendingRebuild = false
    private var activated = false

    // MARK: - Init

    init() {
        YapLog.truncate()
        YapLog.info("Yap \(AppInfo.version) starting")

        AppConfig.ensureConfigFiles(
            defaultConfigURL: AppResources.url("default", extension: "toml"),
            defaultVocabularyURL: AppResources.url("vocabulary", extension: "txt")
        )
        let config = AppConfig.load()
        let keyStore = KeychainGeminiKeyStore()
        let apiKey = GeminiKeyResolver.resolve(store: keyStore)

        self.config = config
        self.keyStore = keyStore
        self.apiKeyDraft = apiKey
        self.missingAPIKey = apiKey.isEmpty
        self.microphone = Microphone(
            silenceTimeout: config.silence.timeout,
            silenceThreshold: config.silence.threshold
        )
        self.hotkey = HotkeyMonitor(
            keycodes: config.hotkey.keycodes,
            doubleTapMS: config.hotkey.doubleTapMS
        )
        self.pipeline = buildPipeline()

        // Startup hooks once the application finished launching.
        NotificationCenter.default.addObserver(
            forName: NSApplication.didFinishLaunchingNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.activate() }
        }
    }

    /// Startup work that needs a running application.
    func activate() {
        guard !activated else { return }
        activated = true

        refreshRecent()
        refreshFailed()
        refreshPermissions()
        launchAtLogin = SMAppService.mainApp.status == .enabled

        wireHotkey(hotkey)
        systemEvents.onWillSleep = { [weak self] in self?.handleWillSleep() }
        systemEvents.onDidWake = { [weak self] in self?.handleDidWake() }
        systemEvents.start()

        NotificationCenter.default.addObserver(
            forName: NSApplication.willTerminateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in self?.cleanup() }
        }

        if !hotkey.startIfPossible() {
            statusText = "Needs Input Monitoring"
            startPermissionPolling()
        }
        if missingAPIKey {
            statusText = "Missing API Key"
            openSettings()
        }
    }

    // MARK: - Hotkey

    private func wireHotkey(_ monitor: HotkeyMonitor) {
        monitor.onDown = { [weak self] in self?.handleTriggerDown() }
        monitor.onUp = { [weak self] in self?.handleTriggerUp() }
    }

    private func handleTriggerDown() {
        guard !missingAPIKey else {
            statusText = "Missing API Key"
            openSettings()
            return
        }
        guard Permissions.isGranted(.microphone) else {
            Permissions.request(.microphone) { [weak self] granted in
                Task { @MainActor in
                    self?.refreshPermissions()
                    if granted {
                        self?.handleTriggerDown()
                    } else {
                        self?.statusText = "Needs Microphone"
                    }
                }
            }
            return
        }
        Task { await self.pipeline.start(source: "hotkey_down") }
    }

    private func handleTriggerUp() {
        Task { await self.pipeline.stopAndProcess(source: "hotkey_up") }
    }

    // MARK: - Pipeline events

    private func buildPipeline() -> DictationPipeline {
        let events = PipelineEvents(
            onStateChange: { [weak self] state in
                Task { @MainActor in self?.applyPipelineState(state) }
            },
            onFirstFrame: { [weak self] in
                Task { @MainActor in self?.sounds.playStart() }
            },
            onNotice: { [weak self] reason in
                Task { @MainActor in self?.applyNotice(reason) }
            },
            onDictationError: { [weak self] reason in
                Task { @MainActor in self?.handleDictationError(reason) }
            },
            onDictationComplete: { [weak self] _ in
                Task { @MainActor in self?.handleDictationComplete() }
            }
        )
        return DictationPipeline(
            recorder: microphone,
            transcriber: makeTranscriber(),
            paster: paster,
            history: history,
            metrics: FileMetricsWriter(),
            events: events,
            pasteTargetProvider: { SystemEvents.frontmostPasteTarget() },
            pasteDelay: config.pasteDelay,
            failedRecordingURL: AppConfig.failedRecordingURL
        )
    }

    private func makeTranscriber() -> any Transcribing {
        let key = apiKeyDraft.isEmpty
            ? GeminiKeyResolver.resolve(store: keyStore)
            : apiKeyDraft
        let configuration = GeminiConfiguration(
            apiKey: key,
            model: config.transcription.model,
            mode: config.transcription.mode,
            languageCodes: geminiLanguageCodes(
                language: config.transcription.language,
                allowedLanguages: config.transcription.allowedLanguages
            ),
            vocabulary: config.vocabulary
        )
        return GeminiTranscriber(configuration: configuration)
    }

    private func applyPipelineState(_ state: PipelineState) {
        switch state {
        case .recording:
            isRecording = true
            isProcessing = false
            statusText = "Recording"
            overlay.show(.recording, label: "Listening", level: { [weak self] in
                MainActor.assumeIsolated { self?.microphone.audioLevel ?? 0 }
            })
        case .processing:
            isRecording = false
            isProcessing = true
            statusText = "Transcribing"
            sounds.playStop()
            overlay.show(.processing, label: "Transcribing", level: { 0 })
        case .idle:
            isRecording = false
            isProcessing = false
            statusText = missingAPIKey ? "Missing API Key" : "Idle"
            overlay.hide()
            refreshFailed()
            if pendingRebuild {
                pendingRebuild = false
                rebuildPipeline()
            }
        }
    }

    private func applyNotice(_ reason: String) {
        statusText = reason
    }

    private func handleDictationError(_ reason: String) {
        YapLog.warning("Pipeline error: \(reason)")
        sounds.playError()
        statusText = "Transcription failed"
    }

    private func handleDictationComplete() {
        refreshRecent()
    }

    // MARK: - Menu actions

    func stopRecording() {
        YapLog.info("Emergency stop from menu bar")
        hotkey.reset()
        Task { await self.pipeline.cancel(source: "menu_stop") }
    }

    func retryFailedDictation() {
        Task {
            await self.pipeline.retryLastFailure(source: "menu_retry")
            self.refreshFailed()
        }
    }

    func pasteRecent(_ text: String) {
        _ = paster.paste(text, target: nil, delay: config.pasteDelay)
    }

    func openVocabulary() {
        NSWorkspace.shared.open(AppConfig.vocabularyURL)
    }

    func openLog() {
        NSWorkspace.shared.open(YapLog.logURL)
    }

    func quit() {
        cleanup()
        NSApp.terminate(nil)
    }

    func openSettings() {
        NSApp.activate(ignoringOtherApps: true)
        let modern = Selector(("showSettingsWindow:"))
        let legacy = Selector(("showPreferencesWindow:"))
        if NSApp.responds(to: modern) {
            NSApp.perform(modern, with: nil)
        } else {
            NSApp.sendAction(legacy, to: nil, from: nil)
        }
    }

    func clip(_ text: String, to limit: Int) -> String {
        text.count > limit ? String(text.prefix(limit - 1)) + "…" : text
    }

    // MARK: - Settings actions

    func saveAPIKey(_ key: String) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            if trimmed.isEmpty {
                try keyStore.delete()
            } else {
                try keyStore.save(trimmed)
            }
        } catch {
            YapLog.error("Failed to store the API key: \(error)")
            statusText = "Could not save API key"
            return
        }
        apiKeyDraft = trimmed
        missingAPIKey = trimmed.isEmpty
        YapLog.info("Gemini API key \(trimmed.isEmpty ? "cleared" : "saved to Keychain")")
        rebuildPipeline()
        statusText = missingAPIKey ? "Missing API Key" : "Idle"
    }

    func updateMode(_ mode: TranscriptionMode) {
        config.transcription.mode = mode
        persistAndRebuild()
    }

    func updateLanguage(_ language: String) {
        config.transcription.language = language
        persistAndRebuild()
    }

    func updateTrigger(_ keycodes: [Int]) {
        config.hotkey.keycodes = keycodes
        persistConfiguration()
        restartHotkey()
    }

    func updateSilenceTimeout(_ timeout: Double) {
        config.silence.timeout = timeout
        persistAndRebuild()
    }

    func setLaunchAtLogin(_ enabled: Bool) {
        do {
            if enabled {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
            launchAtLogin = enabled
        } catch {
            YapLog.warning("Launch at Login change failed: \(error.localizedDescription)")
            launchAtLogin = SMAppService.mainApp.status == .enabled
        }
    }

    // MARK: - Configuration

    private func persistConfiguration() {
        do {
            try config.save()
            YapLog.info("Configuration saved")
        } catch {
            YapLog.error("Failed to save configuration: \(error.localizedDescription)")
        }
    }

    private func persistAndRebuild() {
        persistConfiguration()
        rebuildPipeline()
    }

    private func rebuildPipeline() {
        guard !isRecording, !isProcessing else {
            pendingRebuild = true
            return
        }
        microphone.forceStop()
        microphone = Microphone(
            silenceTimeout: config.silence.timeout,
            silenceThreshold: config.silence.threshold
        )
        pipeline = buildPipeline()
    }

    private func restartHotkey() {
        hotkey.stopTap()
        let monitor = HotkeyMonitor(
            keycodes: config.hotkey.keycodes,
            doubleTapMS: config.hotkey.doubleTapMS
        )
        wireHotkey(monitor)
        hotkey = monitor
        if !hotkey.startIfPossible() {
            statusText = "Needs Input Monitoring"
            startPermissionPolling()
        }
    }

    // MARK: - Refresh helpers

    private func refreshRecent() {
        recent = history.load()
    }

    private func refreshFailed() {
        Task {
            let failed = await self.pipeline.hasFailedRecording
            self.hasFailedRecording = failed
        }
    }

    func refreshPermissions() {
        for kind in Permissions.Kind.allCases {
            permissionStatus[kind] = Permissions.isGranted(kind)
        }
    }

    private func startPermissionPolling() {
        guard permissionTimer == nil else { return }
        let timer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.permissionPollTick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        permissionTimer = timer
    }

    private func permissionPollTick() {
        refreshPermissions()
        guard !hotkey.isRunning, permissionStatus[.inputMonitoring] == true else { return }
        if hotkey.startIfPossible() {
            YapLog.info("Hotkey monitor started after permission grant")
            if statusText == "Needs Input Monitoring" {
                statusText = missingAPIKey ? "Missing API Key" : "Idle"
            }
            permissionTimer?.invalidate()
            permissionTimer = nil
        }
    }

    func requestPermission(_ kind: Permissions.Kind) {
        Permissions.request(kind) { [weak self] _ in
            Task { @MainActor in self?.refreshPermissions() }
        }
    }

    func openPermissionSettings(_ kind: Permissions.Kind) {
        Permissions.openSettings(for: kind)
    }

    // MARK: - Sleep/wake and shutdown

    private func handleWillSleep() {
        hotkey.reset()
        Task { await self.pipeline.cancel(source: "sleep") }
        hotkey.stopTap()
    }

    private func handleDidWake() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
            guard let self else { return }
            if self.hotkey.startIfPossible() {
                if self.statusText == "Needs Input Monitoring" {
                    self.statusText = self.missingAPIKey ? "Missing API Key" : "Idle"
                }
            } else {
                self.startPermissionPolling()
            }
            self.refreshPermissions()
        }
    }

    private func cleanup() {
        systemEvents.stop()
        hotkey.stopTap()
        permissionTimer?.invalidate()
        permissionTimer = nil
        SingleInstanceLock.release()
    }
}

enum AppInfo {
    static let version: String = {
        (Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String) ?? "dev"
    }()
}

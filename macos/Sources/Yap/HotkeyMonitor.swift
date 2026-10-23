import AppKit
import CoreGraphics
import Foundation
import YapCore

/// Global trigger-key monitoring via a listen-only CGEventTap.
///
/// - Hold-to-talk: hold the trigger, release to transcribe
/// - Hands-free: double-tap the trigger to toggle recording, tap again to stop
///
/// A watchdog ends the recording when a key-up event is lost (macOS drops them
/// on focus changes and some keyboard firmware).
@MainActor
final class HotkeyMonitor {
    var onDown: () -> Void = {}
    var onUp: () -> Void = {}

    private(set) var keycodes: [Int]
    private var doubleTapMS: Int

    private var tap: CFMachPort?
    private var runLoopSource: CFRunLoopSource?
    private var heldKeycode: Int?
    private var isHeld = false
    private var isActive = false
    private var toggleMode = false
    private var lastDownTime: TimeInterval = 0
    private var releaseMissTicks = 0
    private var watchdog: Timer?
    private(set) var forcedReleaseCount = 0

    /// Device-dependent bits. Left and right share `.maskAlternate` and
    /// `.maskControl`, so a release has to look at the key's own bit.
    static let deviceMaskByKeycode: [Int: UInt64] = [
        54: 0x10,    // Right Command
        55: 0x08,    // Left Command
        56: 0x02,    // Left Shift
        58: 0x20,    // Left Option
        59: 0x01,    // Left Control
        60: 0x04,    // Right Shift
        61: 0x40,    // Right Option
        62: 0x2000,  // Right Control
    ]

    static func modifierIsDown(keycode: Int, flags: CGEventFlags) -> Bool {
        let raw = flags.rawValue
        if let mask = deviceMaskByKeycode[keycode] {
            let anyDeviceBit = deviceMaskByKeycode.values.contains { (raw & $0) != 0 }
            if anyDeviceBit {
                return (raw & mask) != 0
            }
        }
        if let flag = modifierFlagsByCode[keycode] {
            return flags.contains(flag)
        }
        return false
    }

    /// Virtual keycodes that are modifier keys report through flagsChanged.
    static let modifierFlagsByCode: [Int: CGEventFlags] = [
        54: .maskCommand,    // Right Command
        55: .maskCommand,    // Left Command
        56: .maskShift,      // Left Shift
        57: .maskAlphaShift, // Caps Lock
        58: .maskAlternate,  // Left Option
        59: .maskControl,    // Left Control
        60: .maskShift,      // Right Shift
        61: .maskAlternate,  // Right Option
        62: .maskControl,    // Right Control
        63: .maskSecondaryFn,
    ]

    private static let watchdogInterval = 0.2
    private static let watchdogMissTicksRequired = 2

    init(keycodes: [Int], doubleTapMS: Int = 300) {
        let normalized = keycodes.isEmpty ? [61, 62] : keycodes
        self.keycodes = Array(Dictionary(uniqueKeysWithValues: normalized.enumerated().map { ($1, $0) })
            .sorted { $0.value < $1.value }
            .map(\.key))
        self.doubleTapMS = doubleTapMS
    }

    var isRunning: Bool { tap != nil }

    /// Start the event tap when Input Monitoring is granted. Returns false and
    /// triggers the system permission prompt when it is missing. The menu's
    /// status line and the Settings pane track the state — no modal alerts.
    func startIfPossible() -> Bool {
        guard tap == nil else { return true }
        guard CGPreflightListenEventAccess() else {
            YapLog.warning("Input Monitoring permission missing — requesting it")
            CGRequestListenEventAccess()
            return false
        }

        let mask = CGEventMask(
            (1 << CGEventType.flagsChanged.rawValue)
                | (1 << CGEventType.keyDown.rawValue)
                | (1 << CGEventType.keyUp.rawValue)
        )
        guard let tap = CGEvent.tapCreate(
            tap: .cgSessionEventTap,
            place: .headInsertEventTap,
            options: .listenOnly,
            eventsOfInterest: mask,
            callback: HotkeyMonitor.callback,
            userInfo: Unmanaged.passUnretained(self).toOpaque()
        ) else {
            YapLog.error("Failed to create event tap")
            return false
        }

        self.tap = tap
        let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
        runLoopSource = source
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: tap, enable: true)
        YapLog.info("Hotkey monitor started (keycodes \(keycodes))")
        return true
    }

    /// Disable the tap without discarding the monitor (sleep, permission loss).
    func stopTap() {
        if let tap {
            CGEvent.tapEnable(tap: tap, enable: false)
            if let runLoopSource {
                CFRunLoopRemoveSource(CFRunLoopGetMain(), runLoopSource, .commonModes)
            }
        }
        tap = nil
        runLoopSource = nil
        YapLog.info("Hotkey monitor stopped")
        reset()
    }

    /// Clear internal state after an external stop (silence auto-stop, menu stop).
    func reset() {
        cancelWatchdog()
        isHeld = false
        heldKeycode = nil
        releaseMissTicks = 0
        isActive = false
        toggleMode = false
    }

    // MARK: - Event handling

    private func handle(type: CGEventType, keycode: Int, flags: CGEventFlags) {
        switch type {
        case .tapDisabledByTimeout, .tapDisabledByUserInput:
            YapLog.warning("Event tap disabled — re-enabling")
            if isHeld, !isKeyPhysicallyDown() {
                forcedRelease(reason: "event_tap_timeout")
            }
            if let tap {
                CGEvent.tapEnable(tap: tap, enable: true)
            }

        case .flagsChanged:
            if isHeld, let held = heldKeycode, !Self.modifierIsDown(keycode: held, flags: flags) {
                releaseHeld()
            }
            guard keycodes.contains(keycode), Self.modifierIsDown(keycode: keycode, flags: flags), !isHeld else { return }
            beginHeld(keycode: keycode)

        case .keyDown:
            guard keycodes.contains(keycode), Self.modifierFlagsByCode[keycode] == nil else { return }
            if !isHeld {
                beginHeld(keycode: keycode)
            }

        case .keyUp:
            guard keycodes.contains(keycode), isHeld, heldKeycode == keycode else { return }
            releaseHeld()

        default:
            return
        }
    }

    private func beginHeld(keycode: Int) {
        isHeld = true
        heldKeycode = keycode
        releaseMissTicks = 0
        let now = ProcessInfo.processInfo.systemUptime
        let sinceLastDownMS = (now - lastDownTime) * 1000

        if isActive, toggleMode {
            // Another tap while recording hands-free: stop.
            toggleMode = false
            isActive = false
            YapLog.info("Toggle mode off — stopping")
            onUp()
        } else if !isActive, lastDownTime > 0, sinceLastDownMS < Double(doubleTapMS) {
            toggleMode = true
            isActive = true
            YapLog.info("Double-tap — toggle mode on")
            onDown()
        } else if !isActive {
            isActive = true
            toggleMode = false
            YapLog.info("Hold-to-talk — recording")
            onDown()
        }

        lastDownTime = now
        scheduleWatchdog()
    }

    private func releaseHeld() {
        isHeld = false
        heldKeycode = nil
        releaseMissTicks = 0
        cancelWatchdog()
        if isActive, !toggleMode {
            isActive = false
            YapLog.info("Released — stopping")
            onUp()
        }
    }

    private func forcedRelease(reason: String) {
        forcedReleaseCount += 1
        YapLog.warning("Forced hotkey release (\(reason)) [count=\(forcedReleaseCount)]")
        isHeld = false
        heldKeycode = nil
        releaseMissTicks = 0
        cancelWatchdog()
        if isActive, !toggleMode {
            isActive = false
            onUp()
        }
    }

    // MARK: - Release watchdog

    private func scheduleWatchdog() {
        cancelWatchdog()
        let timer = Timer.scheduledTimer(withTimeInterval: Self.watchdogInterval, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.watchdogTick() }
        }
        RunLoop.main.add(timer, forMode: .common)
        watchdog = timer
    }

    private func cancelWatchdog() {
        watchdog?.invalidate()
        watchdog = nil
    }

    private func watchdogTick() {
        guard isHeld else {
            cancelWatchdog()
            return
        }
        if isKeyPhysicallyDown() {
            releaseMissTicks = 0
            return
        }
        releaseMissTicks += 1
        guard releaseMissTicks >= Self.watchdogMissTicksRequired else { return }
        if isKeyPhysicallyDown() {
            releaseMissTicks = 0
        } else {
            forcedRelease(reason: "watchdog")
        }
    }

    private func isKeyPhysicallyDown() -> Bool {
        guard let keycode = heldKeycode else { return false }
        let flags = CGEventSource.flagsState(.combinedSessionState)
        if Self.deviceMaskByKeycode[keycode] != nil || Self.modifierFlagsByCode[keycode] != nil {
            return Self.modifierIsDown(keycode: keycode, flags: flags)
        }
        return CGEventSource.keyState(.combinedSessionState, key: CGKeyCode(keycode))
    }

    // MARK: - Permission

    private static let callback: CGEventTapCallBack = { _, type, event, userInfo in
        guard let userInfo else {
            return Unmanaged.passUnretained(event)
        }
        let monitor = Unmanaged<HotkeyMonitor>.fromOpaque(userInfo).takeUnretainedValue()
        // Read the event's scalar fields on the tap thread and hop only with
        // Sendable values — the tap source runs on the main run loop anyway.
        let keycode = Int(event.getIntegerValueField(.keyboardEventKeycode))
        let flags = event.flags
        MainActor.assumeIsolated {
            monitor.handle(type: type, keycode: keycode, flags: flags)
        }
        return Unmanaged.passUnretained(event)
    }
}

#!/usr/bin/env python3
"""Quick hotkey test — run this directly in your terminal to test permissions.

Usage: python3 test_hotkey.py
"""
import Quartz

def callback(proxy, event_type, event, refcon):
    keycode = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
    flags = Quartz.CGEventGetFlags(event)
    print(f"type={event_type} keycode={keycode} flags={flags:#x}", flush=True)
    return event

mask = (
    Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
    | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
    | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged)
)
tap = Quartz.CGEventTapCreate(
    Quartz.kCGSessionEventTap,
    Quartz.kCGHeadInsertEventTap,
    Quartz.kCGEventTapOptionListenOnly,
    mask,
    callback,
    None,
)

if tap is None:
    print("ERROR: Could not create event tap. Check Accessibility permissions.")
    raise SystemExit(1)

src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
Quartz.CFRunLoopAddSource(
    Quartz.CFRunLoopGetCurrent(), src, Quartz.kCFRunLoopDefaultMode
)
Quartz.CGEventTapEnable(tap, True)
print("Listening — press any key (Ctrl+C to quit)...")

try:
    Quartz.CFRunLoopRun()
except KeyboardInterrupt:
    print("\nDone.")

# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Yap — macOS menubar dictation app."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd()))
from app.version import APP_VERSION

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("config/default.toml", "config"),
        ("config/vocabulary.txt", "config"),
        ("assets/icon_menubar.png", "assets"),
        ("assets/icon_app.png", "assets"),
        ("assets/ui_click.wav", "assets"),
        ("assets/record_start.wav", "assets"),
        ("assets/record_stop.wav", "assets"),
    ],
    hiddenimports=[
        "rumps",
        "sounddevice",
        "soundfile",
        "numpy",
        "groq",
        "httpx",
        "dotenv",
        "AppKit",
        "Quartz",
        "_sounddevice_data",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "test", "unittest", "sqlite3"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Yap",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Yap",
)

app = BUNDLE(
    coll,
    name="Yap.app",
    icon="assets/icon_app.png",
    bundle_identifier="com.yap.dictation",
    info_plist={
        "CFBundleName": "Yap",
        "CFBundleDisplayName": "Yap",
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "LSUIElement": True,
        "NSMicrophoneUsageDescription": "Yap needs microphone access for voice dictation.",
    },
)

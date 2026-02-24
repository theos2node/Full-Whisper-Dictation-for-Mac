# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

hidden = [
    "whisperdictation.app",
    "mlx_whisper",
    "whisper",
    "mlx._reprlib_fix",
    "imageio_ffmpeg",
]
hidden += collect_submodules("mlx_whisper")
hidden += collect_submodules("mlx")
hidden += collect_submodules("imageio_ffmpeg")
datas = collect_data_files("whisper", includes=["assets/*"])
datas += collect_data_files("mlx", includes=["lib/*.metallib"])
datas += collect_data_files("mlx_whisper", includes=["assets/*"])
datas += collect_data_files("imageio_ffmpeg", includes=["binaries/*"])
datas += [("assets/AppIcon.png", "assets"), ("assets/AppIcon.icns", "assets")]

a = Analysis(
    ["src/main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Whisper Dictation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file="entitlements.plist",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Whisper Dictation",
)

app = BUNDLE(
    coll,
    name="Whisper Dictation.app",
    icon="assets/AppIcon.icns",
    bundle_identifier="com.whisperdictation.app",
    info_plist={
        "CFBundleName": "Whisper Dictation",
        "CFBundleDisplayName": "Whisper Dictation",
        "CFBundleIdentifier": "com.whisperdictation.app",
        "CFBundleIconFile": "AppIcon.icns",
        "CFBundleIconName": "AppIcon",
        "CFBundleShortVersionString": "0.4.0",
        "CFBundleVersion": "0.4.0",
        "LSMinimumSystemVersion": "13.0",
        "NSMicrophoneUsageDescription": "Whisper Dictation needs microphone access to transcribe speech.",
    },
)

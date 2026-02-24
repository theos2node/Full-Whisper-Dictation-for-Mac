#!/bin/bash
set -euo pipefail

echo "Building Whisper Dictation.app"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "Error: Python 3 is required"
        exit 1
    fi
fi

if [ -d ".venv" ]; then
    VENV_PYTHON_VERSION="$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    if [ "$VENV_PYTHON_VERSION" != "3.11" ]; then
        echo "Existing .venv is Python $VENV_PYTHON_VERSION, recreating with Python 3.11"
        rm -r .venv
    fi
fi

if [ ! -d ".venv" ]; then
    "$PYTHON_BIN" -m venv .venv
fi

source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt

if [ -f "scripts/generate_app_icon.sh" ] && [ -f "assets/AppIcon-source.jpg" ]; then
    ./scripts/generate_app_icon.sh
fi

rm -rf build dist
pyinstaller --noconfirm --clean "Whisper Dictation.spec"

# Desktop/iCloud can attach metadata that breaks codesign.
APP_NAME="Whisper Dictation.app"
TMP_RELEASE_DIR="/tmp/whisper-dictation-release"
TMP_APP_PATH="$TMP_RELEASE_DIR/$APP_NAME"
rm -r "$TMP_RELEASE_DIR" 2>/dev/null || true
mkdir -p "$TMP_RELEASE_DIR"
ditto --norsrc "dist/$APP_NAME" "$TMP_APP_PATH"
codesign --force --deep --sign - --entitlements entitlements.plist "$TMP_APP_PATH"
codesign --verify --deep --strict --verbose=2 "$TMP_APP_PATH"
rm -r "dist/$APP_NAME"
ditto --norsrc "$TMP_APP_PATH" "dist/$APP_NAME"
xattr -cr "dist/$APP_NAME" || true
if ! codesign --verify --deep --strict --verbose=2 "dist/$APP_NAME"; then
    echo "Warning: strict codesign verification failed in dist due workspace metadata."
    echo "The release app used for zip was already verified in /tmp."
fi
ditto -c -k --sequesterRsrc --keepParent "$TMP_APP_PATH" "dist/Whisper-Dictation-macOS.zip"

echo "Build complete:"
echo "  dist/Whisper Dictation.app"
echo "  dist/Whisper-Dictation-macOS.zip"
echo "Drag it into /Applications and launch by clicking the icon."

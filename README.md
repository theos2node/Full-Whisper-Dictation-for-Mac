# Whisper Dictation for macOS

Open-source local dictation for Apple Silicon Macs.

Hold a hotkey, speak, release to transcribe. A compact overlay shows `Listening...` and `Transcribing...`. Transcripts are saved in-app and copied to clipboard.

## Current behavior (v0.4.0)

- Local UI hold-to-talk by default (reliable mode):
  App listens while Whisper Dictation is the focused app window.
- Clipboard output:
  When transcription completes, text is copied to clipboard.
- Persistent history:
  Every transcription is stored in the app and can be clicked to copy.
- Apple Silicon first backend:
  `mlx-whisper` primary, `openai-whisper` fallback.

## Download and install

1. Download `Whisper-Dictation-macOS.zip` from GitHub Releases.
2. Unzip it.
3. Drag `Whisper Dictation.app` into `/Applications`.
4. Open the app.

If macOS warns the app is from an unidentified developer:
1. Right-click the app in `/Applications`.
2. Click `Open`.
3. Confirm `Open` in the dialog.

## First run permissions

- Microphone is required for dictation.
- Global mode (optional) additionally needs Accessibility and Input Monitoring.

## Usage

1. Launch `Whisper Dictation.app`.
2. Hold hotkey (default `Control`) while focused in the app window.
3. Speak and release.
4. Text is transcribed and copied to clipboard.
5. Click a history item to copy it again.

## Development run

```bash
git clone https://github.com/theos2node/Full-Whisper-Dictation-for-Mac.git
cd Full-Whisper-Dictation-for-Mac
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python src/main.py
```

## Build app bundle

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
./build.sh
```

Build artifacts:

- `dist/Whisper Dictation.app`
- `dist/Whisper-Dictation-macOS.zip`

## Configuration

- `WHISPER_DICTATION_HOTKEY` (default: `ctrl`)
- `WHISPER_DICTATION_HOTKEY_SCOPE` (default: `local`, optional: `global`)
- `WHISPER_DICTATION_MODEL` (default: `mlx-community/whisper-large-v3-turbo`)
- `WHISPER_DICTATION_FALLBACK_MODEL` (default: `base`)
- `WHISPER_DICTATION_LANGUAGE` (default: auto detect)

## Release automation

GitHub Actions workflow builds a macOS app zip on tag pushes (`v*`) and uploads it as a release asset.

## Notes

- First launch warms the model and may take up to about a minute.
- Runtime log path: `~/Library/Application Support/WhisperDictation/runtime.log`
- Python 3.11 is the recommended build/runtime version.

## License

MIT. See [LICENSE](LICENSE).

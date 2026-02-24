# Whisper Dictation for macOS

Wispr Flow-style press-and-hold dictation, running fully local on Apple Silicon.

## What this project is

Whisper Dictation is a local-first voice-to-text system for macOS:

- Press and hold to talk.
- Release to transcribe.
- Keep output in clipboard for paste-anywhere workflows.
- Persist every transcript in an indexed in-app history.

No cloud API keys, no subscription, no remote inference required.

## Product behavior

Default mode is `local` for maximum reliability:

- Hotkey is captured while Whisper Dictation is the active app window.
- Overlay gives immediate state feedback: `Listening...` then `Transcribing...`.
- Completed transcript is copied to clipboard.

Optional `global` mode is available:

- Captures hold-to-talk outside the app window.
- Requires Accessibility + Input Monitoring permissions.

## Technical stack

- UI/runtime: `PyQt6`
- Audio I/O: `sounddevice` (PortAudio backend)
- DSP / serialization: `numpy`, `scipy` (`wavfile`)
- Primary ASR backend: `mlx-whisper` (Apple Silicon optimized local inference)
- Fallback ASR backend: `openai-whisper`
- Packaging: `PyInstaller` (`.app` bundle)
- Distribution automation: GitHub Actions release workflow

## End-to-end pipeline

1. Hotkey edge detection emits `start_recording`/`stop_recording`.
2. Audio stream buffers float32 mono frames at 16kHz.
3. Frames are concatenated and normalized with automatic gain logic.
4. Audio is serialized to temporary WAV.
5. ASR backend transcribes (`mlx-whisper` first, fallback on failure).
6. Transcript is appended to local history (`~/Library/Application Support/WhisperDictation/history.json`).
7. Transcript is copied to clipboard for immediate paste into any text field.

Architecture details: see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Installation (users)

1. Download `Whisper-Dictation-macOS.zip` from GitHub Releases.
2. Unzip.
3. Drag `Whisper Dictation.app` into `/Applications`.
4. Launch the app.

If Gatekeeper warns on first launch:

1. Right-click `Whisper Dictation.app`.
2. Choose `Open`.
3. Confirm the dialog.

## Permissions model

- Required in all modes:
  - Microphone
- Required only in `global` hotkey mode:
  - Accessibility
  - Input Monitoring

## Runtime configuration

- `WHISPER_DICTATION_HOTKEY` default: `ctrl`
- `WHISPER_DICTATION_HOTKEY_SCOPE` default: `local` (`local` or `global`)
- `WHISPER_DICTATION_MODEL` default: `mlx-community/whisper-large-v3-turbo`
- `WHISPER_DICTATION_FALLBACK_MODEL` default: `base`
- `WHISPER_DICTATION_LANGUAGE` default: auto detect

Example:

```bash
WHISPER_DICTATION_HOTKEY=ctrl \
WHISPER_DICTATION_HOTKEY_SCOPE=global \
WHISPER_DICTATION_MODEL=mlx-community/whisper-large-v3-turbo \
python src/main.py
```

## Development

```bash
git clone https://github.com/theos2node/Full-Whisper-Dictation-for-Mac.git
cd Full-Whisper-Dictation-for-Mac
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
python src/main.py
```

## Build and package

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
./build.sh
```

Artifacts:

- `dist/Whisper Dictation.app`
- `dist/Whisper-Dictation-macOS.zip`

## Release process

- Tag-driven release workflow lives at:
  - `.github/workflows/release-macos.yml`
- Pushing a tag like `v0.4.0` triggers:
  - macOS app build
  - zip artifact upload
  - GitHub Release asset publish

## Observability and troubleshooting

- Runtime log:
  - `~/Library/Application Support/WhisperDictation/runtime.log`
- Common checks:
  - Verify backend load and warmup completion in log.
  - Verify hotkey mode (`local-ui` or `global` fallback chain).
  - Verify microphone stream chunk count is non-zero.

## License

MIT. See [LICENSE](LICENSE).

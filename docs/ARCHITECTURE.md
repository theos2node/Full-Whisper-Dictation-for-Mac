# Architecture

## Design goals

- Preserve a Wispr-style press-and-hold UX.
- Keep inference local on Apple Silicon.
- Maintain a deterministic audio/transcription path.
- Keep output transport simple (`clipboard`) for app-agnostic paste.

## Component map

- `src/whisperdictation/app.py`
  - Main application runtime and UI state machine.
- `SignalHandler`
  - Thread-safe bridge from listener/audio worker threads to Qt UI thread.
- Hotkey capture layer
  - `local` mode: Qt event filter.
  - `global` mode: Quartz/AppKit/polling fallback chain.
- Audio capture layer
  - `sounddevice.InputStream` with float32 mono frames at 16kHz.
- ASR backend layer
  - `MLXWhisperBackend` primary.
  - `OpenAIWhisperBackend` fallback.
- Persistence layer
  - Settings and transcript history under `~/Library/Application Support/WhisperDictation/`.

## Hotkey and state transitions

Core transitions:

1. `idle` -> `recording`
2. `recording` -> `transcribing`
3. `transcribing` -> `idle`

Transition triggers:

- Hotkey down edge starts recording.
- Hotkey up edge stops recording.
- `Esc` during recording marks request as cancelled.

UI indicators:

- Main window status label.
- Top overlay (`Listening...`, `Transcribing...`).
- Hotkey indicator (`HOTKEY DOWN`, `HOTKEY IDLE`).

## Audio path

- Stream callback pushes each incoming frame buffer to a lock-protected list.
- On stop:
  - Concatenate buffers.
  - Compute duration/RMS/peak diagnostics.
  - Apply conservative automatic gain if headroom is large.
  - Write temporary PCM16 WAV.

Short/no-audio handling:

- Empty buffer list exits early.
- Clips below `min_audio_seconds` are ignored.

## Inference path

- Primary: `mlx_whisper.transcribe(...)` with model from `WHISPER_DICTATION_MODEL`.
- Fallback: `whisper.load_model(...).transcribe(...)` from `WHISPER_DICTATION_FALLBACK_MODEL`.
- Optional language hint via `WHISPER_DICTATION_LANGUAGE`.

Backend warmup:

- Startup performs a short silent WAV transcription to prime model runtime/cache.

## Output semantics

- Successful transcript is appended to history.
- Transcript is copied to clipboard (`pyperclip.copy`).
- History UI is always authoritative local output ledger.

## Packaging and distribution

- Build entry point: `build.sh`
- App packaging: `PyInstaller` spec (`Whisper Dictation.spec`)
- App icon:
  - Source image: `assets/AppIcon-source.jpg`
  - Generated icon assets: `assets/AppIcon.icns`, `assets/AppIcon.png`
  - Generation script: `scripts/generate_app_icon.sh`

Release automation:

- `.github/workflows/release-macos.yml`
- Trigger: tag push `v*`
- Output: `Whisper-Dictation-macOS.zip` attached to GitHub Release.

import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np
import pyperclip
import sounddevice as sd
from pynput import keyboard as pynput_keyboard
from PyQt6.QtCore import QEvent, QObject, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QMenu,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from scipy.io import wavfile

try:
    from ApplicationServices import AXIsProcessTrusted
except Exception:  # pragma: no cover
    AXIsProcessTrusted = None

try:
    from AppKit import (
        NSActivityLatencyCritical,
        NSActivityUserInitiatedAllowingIdleSystemSleep,
        NSEvent,
        NSEventMaskFlagsChanged,
        NSEventMaskKeyDown,
        NSEventModifierFlagCommand,
        NSEventModifierFlagControl,
        NSEventModifierFlagOption,
        NSEventModifierFlagShift,
    )
    from Foundation import NSProcessInfo

    APPKIT_AVAILABLE = True
except Exception:  # pragma: no cover
    NSActivityLatencyCritical = None
    NSActivityUserInitiatedAllowingIdleSystemSleep = None
    NSEvent = None
    NSEventMaskFlagsChanged = None
    NSEventMaskKeyDown = None
    NSEventModifierFlagCommand = None
    NSEventModifierFlagControl = None
    NSEventModifierFlagOption = None
    NSEventModifierFlagShift = None
    NSProcessInfo = None
    APPKIT_AVAILABLE = False

try:
    from Quartz import (
        CFMachPortCreateRunLoopSource,
        CFRunLoopAddSource,
        CFRunLoopGetCurrent,
        CFRunLoopRun,
        CFRunLoopStop,
        CGEventGetFlags,
        CGEventGetIntegerValueField,
        CGEventMaskBit,
        CGEventSourceKeyState,
        CGEventSourceFlagsState,
        CGEventTapCreate,
        CGEventTapEnable,
        CGPreflightListenEventAccess,
        CGRequestListenEventAccess,
        kCFRunLoopCommonModes,
        kCGEventFlagMaskAlternate,
        kCGEventFlagMaskCommand,
        kCGEventFlagMaskControl,
        kCGEventFlagMaskShift,
        kCGEventFlagsChanged,
        kCGEventKeyDown,
        kCGEventTapDisabledByTimeout,
        kCGEventTapDisabledByUserInput,
        kCGEventTapOptionDefault,
        kCGHeadInsertEventTap,
        kCGKeyboardEventKeycode,
        kCGEventSourceStateCombinedSessionState,
        kCGEventSourceStateHIDSystemState,
        kCGSessionEventTap,
    )

    QUARTZ_AVAILABLE = True
except Exception:  # pragma: no cover
    CFMachPortCreateRunLoopSource = None
    CFRunLoopAddSource = None
    CFRunLoopGetCurrent = None
    CFRunLoopRun = None
    CFRunLoopStop = None
    CGEventGetFlags = None
    CGEventGetIntegerValueField = None
    CGEventMaskBit = None
    CGEventSourceKeyState = None
    CGEventSourceFlagsState = None
    CGEventTapCreate = None
    CGEventTapEnable = None
    CGPreflightListenEventAccess = None
    CGRequestListenEventAccess = None
    kCFRunLoopCommonModes = None
    kCGEventFlagMaskAlternate = None
    kCGEventFlagMaskCommand = None
    kCGEventFlagMaskControl = None
    kCGEventFlagMaskShift = None
    kCGEventFlagsChanged = None
    kCGEventKeyDown = None
    kCGEventTapDisabledByTimeout = None
    kCGEventTapDisabledByUserInput = None
    kCGEventTapOptionDefault = None
    kCGHeadInsertEventTap = None
    kCGKeyboardEventKeycode = None
    kCGEventSourceStateCombinedSessionState = None
    kCGEventSourceStateHIDSystemState = None
    kCGSessionEventTap = None
    QUARTZ_AVAILABLE = False


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _parse_hotkey(hotkey: str) -> list[str]:
    token_map = {
        "command": "cmd",
        "super": "cmd",
        "option": "alt",
        "control": "ctrl",
        "right_command": "cmd_r",
        "left_command": "cmd_l",
        "right_option": "alt_r",
        "left_option": "alt_l",
        "right_control": "ctrl_r",
        "left_control": "ctrl_l",
    }
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    normalized = []
    for part in parts:
        normalized.append(token_map.get(part, part))
    return normalized or ["ctrl"]


def _key_names(key: pynput_keyboard.Key | pynput_keyboard.KeyCode) -> set[str]:
    # Include generic + side-specific tokens so hold/release state remains consistent.
    if key == pynput_keyboard.Key.cmd:
        return {"cmd", "cmd_l", "cmd_r"}
    if key == pynput_keyboard.Key.cmd_l:
        return {"cmd", "cmd_l"}
    if key == pynput_keyboard.Key.cmd_r:
        return {"cmd", "cmd_r"}
    if key == pynput_keyboard.Key.shift:
        return {"shift", "shift_l", "shift_r"}
    if key == pynput_keyboard.Key.shift_l:
        return {"shift", "shift_l"}
    if key == pynput_keyboard.Key.shift_r:
        return {"shift", "shift_r"}
    if key == pynput_keyboard.Key.ctrl:
        return {"ctrl", "ctrl_l", "ctrl_r"}
    if key == pynput_keyboard.Key.ctrl_l:
        return {"ctrl", "ctrl_l"}
    if key == pynput_keyboard.Key.ctrl_r:
        return {"ctrl", "ctrl_r"}
    if key == pynput_keyboard.Key.alt:
        return {"alt", "alt_l", "alt_r"}
    if key == pynput_keyboard.Key.alt_l:
        return {"alt", "alt_l"}
    if key == pynput_keyboard.Key.alt_r:
        return {"alt", "alt_r"}
    if key == pynput_keyboard.Key.space:
        return {"space"}
    if key == pynput_keyboard.Key.esc:
        return {"esc"}
    if isinstance(key, pynput_keyboard.KeyCode) and key.char:
        return {key.char.lower()}
    return set()


def _is_accessibility_enabled() -> bool:
    if AXIsProcessTrusted is None:
        return True
    try:
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _is_input_monitoring_enabled() -> bool:
    if CGPreflightListenEventAccess is None:
        return True
    try:
        return bool(CGPreflightListenEventAccess())
    except Exception:
        return False


class QuartzHotkeyListener:
    MODIFIER_MASKS = {
        "ctrl": kCGEventFlagMaskControl,
        "ctrl_l": kCGEventFlagMaskControl,
        "ctrl_r": kCGEventFlagMaskControl,
        "cmd": kCGEventFlagMaskCommand,
        "cmd_l": kCGEventFlagMaskCommand,
        "cmd_r": kCGEventFlagMaskCommand,
        "alt": kCGEventFlagMaskAlternate,
        "alt_l": kCGEventFlagMaskAlternate,
        "alt_r": kCGEventFlagMaskAlternate,
        "shift": kCGEventFlagMaskShift,
        "shift_l": kCGEventFlagMaskShift,
        "shift_r": kCGEventFlagMaskShift,
    }

    def __init__(
        self,
        hotkey_tokens: list[str],
        on_hotkey_change: Callable[[bool], None],
        on_escape: Callable[[], None],
        on_error: Callable[[str], None],
    ):
        self.hotkey_tokens = hotkey_tokens
        self.on_hotkey_change = on_hotkey_change
        self.on_escape = on_escape
        self.on_error = on_error
        self.required_masks: list[int] = []
        for token in hotkey_tokens:
            mask = self.MODIFIER_MASKS.get(token)
            if mask is None:
                raise ValueError(f"Unsupported quartz hotkey token: {token}")
            self.required_masks.append(mask)

        self._thread: threading.Thread | None = None
        self._run_loop = None
        self._tap = None
        self._active = False
        self._callback_ref = self._event_callback

    @classmethod
    def supports_tokens(cls, hotkey_tokens: list[str]) -> bool:
        if not QUARTZ_AVAILABLE:
            return False
        return all(token in cls.MODIFIER_MASKS for token in hotkey_tokens)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        if self._run_loop is not None:
            try:
                CFRunLoopStop(self._run_loop)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        self._run_loop = None
        self._tap = None

    def _active_for_flags(self, flags: int) -> bool:
        for mask in self.required_masks:
            if (flags & mask) == 0:
                return False
        return True

    def _event_callback(self, proxy, event_type, event, refcon):
        del proxy, refcon
        if event_type in (kCGEventTapDisabledByTimeout, kCGEventTapDisabledByUserInput):
            if self._tap is not None:
                CGEventTapEnable(self._tap, True)
            return event

        if event_type == kCGEventKeyDown:
            keycode = CGEventGetIntegerValueField(event, kCGKeyboardEventKeycode)
            if keycode == 53:  # Esc
                self.on_escape()

        if event_type in (kCGEventFlagsChanged, kCGEventKeyDown):
            flags = CGEventGetFlags(event)
            active = self._active_for_flags(flags)
            if active != self._active:
                self._active = active
                self.on_hotkey_change(active)

        return event

    def _run(self):
        try:
            mask = CGEventMaskBit(kCGEventFlagsChanged) | CGEventMaskBit(kCGEventKeyDown)
            self._tap = CGEventTapCreate(
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventTapOptionDefault,
                mask,
                self._callback_ref,
                None,
            )
            if self._tap is None:
                self.on_error(
                    "Global hotkey monitor unavailable. Grant Accessibility and Input Monitoring."
                )
                return
            source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
            self._run_loop = CFRunLoopGetCurrent()
            CFRunLoopAddSource(self._run_loop, source, kCFRunLoopCommonModes)
            CGEventTapEnable(self._tap, True)
            CFRunLoopRun()
        except Exception as exc:
            self.on_error(f"Quartz hotkey listener failed: {exc}")


class ModifierPollingHotkeyListener:
    MODIFIER_MASKS = QuartzHotkeyListener.MODIFIER_MASKS

    def __init__(
        self,
        hotkey_tokens: list[str],
        on_hotkey_change: Callable[[bool], None],
        on_error: Callable[[str], None],
        poll_interval: float = 0.02,
    ):
        self.hotkey_tokens = hotkey_tokens
        self.on_hotkey_change = on_hotkey_change
        self.on_error = on_error
        self.poll_interval = poll_interval
        self.required_masks: list[int] = []
        for token in hotkey_tokens:
            mask = self.MODIFIER_MASKS.get(token)
            if mask is None:
                raise ValueError(f"Unsupported polling hotkey token: {token}")
            self.required_masks.append(mask)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._active = False

    @classmethod
    def supports_tokens(cls, hotkey_tokens: list[str]) -> bool:
        if not QUARTZ_AVAILABLE:
            return False
        if CGEventSourceFlagsState is None or kCGEventSourceStateCombinedSessionState is None:
            return False
        return all(token in cls.MODIFIER_MASKS for token in hotkey_tokens)

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _active_for_flags(self, flags: int) -> bool:
        for mask in self.required_masks:
            if (flags & mask) == 0:
                return False
        return True

    def _run(self):
        try:
            while not self._stop_event.is_set():
                flags = int(CGEventSourceFlagsState(kCGEventSourceStateCombinedSessionState))
                active = self._active_for_flags(flags)
                if active != self._active:
                    self._active = active
                    self.on_hotkey_change(active)
                time.sleep(self.poll_interval)
        except Exception as exc:
            self.on_error(f"Modifier polling listener failed: {exc}")


class AppKitHotkeyListener:
    MODIFIER_MASKS = {
        "ctrl": NSEventModifierFlagControl,
        "ctrl_l": NSEventModifierFlagControl,
        "ctrl_r": NSEventModifierFlagControl,
        "cmd": NSEventModifierFlagCommand,
        "cmd_l": NSEventModifierFlagCommand,
        "cmd_r": NSEventModifierFlagCommand,
        "alt": NSEventModifierFlagOption,
        "alt_l": NSEventModifierFlagOption,
        "alt_r": NSEventModifierFlagOption,
        "shift": NSEventModifierFlagShift,
        "shift_l": NSEventModifierFlagShift,
        "shift_r": NSEventModifierFlagShift,
    }

    def __init__(
        self,
        hotkey_tokens: list[str],
        on_hotkey_change: Callable[[bool], None],
        on_escape: Callable[[], None],
        on_error: Callable[[str], None],
    ):
        self.hotkey_tokens = hotkey_tokens
        self.on_hotkey_change = on_hotkey_change
        self.on_escape = on_escape
        self.on_error = on_error
        self.required_masks: list[int] = []
        for token in hotkey_tokens:
            mask = self.MODIFIER_MASKS.get(token)
            if mask is None:
                raise ValueError(f"Unsupported AppKit hotkey token: {token}")
            self.required_masks.append(mask)
        self._active = False
        self._global_flags_monitor = None
        self._global_keydown_monitor = None
        self._local_flags_monitor = None
        self._local_keydown_monitor = None
        self._global_flags_handler = None
        self._global_keydown_handler = None
        self._local_flags_handler = None
        self._local_keydown_handler = None

    @classmethod
    def supports_tokens(cls, hotkey_tokens: list[str]) -> bool:
        if not APPKIT_AVAILABLE:
            return False
        return all(token in cls.MODIFIER_MASKS for token in hotkey_tokens)

    def _active_for_flags(self, flags: int) -> bool:
        for mask in self.required_masks:
            if (flags & mask) == 0:
                return False
        return True

    def _handle_flags_event(self, event):
        try:
            flags = int(event.modifierFlags())
            active = self._active_for_flags(flags)
            if active != self._active:
                self._active = active
                self.on_hotkey_change(active)
        except Exception as exc:
            self.on_error(f"AppKit flags monitor failed: {exc}")

    def _handle_keydown_event(self, event):
        try:
            keycode = int(event.keyCode())
            if keycode == 53:  # Esc
                self.on_escape()
        except Exception as exc:
            self.on_error(f"AppKit key monitor failed: {exc}")

    def start(self):
        try:
            def global_flags_handler(event):
                self._handle_flags_event(event)

            def global_keydown_handler(event):
                self._handle_keydown_event(event)

            def local_flags_handler(event):
                self._handle_flags_event(event)
                return event

            def local_keydown_handler(event):
                self._handle_keydown_event(event)
                return event

            self._global_flags_handler = global_flags_handler
            self._global_keydown_handler = global_keydown_handler
            self._local_flags_handler = local_flags_handler
            self._local_keydown_handler = local_keydown_handler

            self._global_flags_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskFlagsChanged,
                self._global_flags_handler,
            )
            self._global_keydown_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown,
                self._global_keydown_handler,
            )
            self._local_flags_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskFlagsChanged,
                self._local_flags_handler,
            )
            self._local_keydown_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                NSEventMaskKeyDown,
                self._local_keydown_handler,
            )
            # If global monitor creation fails, this listener would only work while focused.
            if self._global_flags_monitor is None:
                self.on_error(
                    "AppKit global hotkey monitor unavailable. Grant Accessibility/Input Monitoring."
                )
        except Exception as exc:
            self.on_error(f"AppKit hotkey listener failed: {exc}")

    def stop(self):
        for attr in (
            "_global_flags_monitor",
            "_global_keydown_monitor",
            "_local_flags_monitor",
            "_local_keydown_monitor",
        ):
            monitor = getattr(self, attr)
            if monitor is None:
                continue
            try:
                NSEvent.removeMonitor_(monitor)
            except Exception:
                pass
            setattr(self, attr, None)


class KeyStatePollingHotkeyListener:
    TOKEN_KEYCODES = {
        "cmd": [55, 54],
        "cmd_l": [55],
        "cmd_r": [54],
        "ctrl": [59, 62],
        "ctrl_l": [59],
        "ctrl_r": [62],
        "alt": [58, 61],
        "alt_l": [58],
        "alt_r": [61],
        "shift": [56, 60],
        "shift_l": [56],
        "shift_r": [60],
        "space": [49],
    }

    def __init__(
        self,
        hotkey_tokens: list[str],
        on_hotkey_change: Callable[[bool], None],
        on_escape: Callable[[], None],
        on_error: Callable[[str], None],
        poll_interval: float = 0.01,
    ):
        self.hotkey_tokens = hotkey_tokens
        self.on_hotkey_change = on_hotkey_change
        self.on_escape = on_escape
        self.on_error = on_error
        self.poll_interval = poll_interval
        self.required_keys: list[list[int]] = []
        for token in hotkey_tokens:
            keycodes = self.TOKEN_KEYCODES.get(token)
            if keycodes is None:
                raise ValueError(f"Unsupported key-state polling token: {token}")
            self.required_keys.append(keycodes)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._active = False
        self._esc_was_down = False

    @classmethod
    def supports_tokens(cls, hotkey_tokens: list[str]) -> bool:
        if CGEventSourceKeyState is None:
            return False
        return all(token in cls.TOKEN_KEYCODES for token in hotkey_tokens)

    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _is_key_down(self, keycode: int) -> bool:
        state = (
            kCGEventSourceStateHIDSystemState
            if kCGEventSourceStateHIDSystemState is not None
            else kCGEventSourceStateCombinedSessionState
        )
        if state is None:
            return False
        return bool(CGEventSourceKeyState(state, keycode))

    def _active_now(self) -> bool:
        for group in self.required_keys:
            if not any(self._is_key_down(keycode) for keycode in group):
                return False
        return True

    def _run(self):
        try:
            while not self._stop_event.is_set():
                active = self._active_now()
                if active != self._active:
                    self._active = active
                    self.on_hotkey_change(active)

                esc_down = self._is_key_down(53)
                if esc_down and (not self._esc_was_down):
                    self.on_escape()
                self._esc_was_down = esc_down
                time.sleep(self.poll_interval)
        except Exception as exc:
            self.on_error(f"Key-state polling listener failed: {exc}")


class BaseBackend:
    name = "unknown"

    def transcribe(self, audio_path: str, language: str | None) -> str:
        raise NotImplementedError


class MLXWhisperBackend(BaseBackend):
    name = "mlx-whisper"

    def __init__(self, model_name: str):
        import mlx_whisper

        self._mlx_whisper = mlx_whisper
        self._model_name = model_name

    def transcribe(self, audio_path: str, language: str | None) -> str:
        kwargs = {"path_or_hf_repo": self._model_name}
        if language:
            kwargs["language"] = language
        result = self._mlx_whisper.transcribe(audio_path, **kwargs)
        return result["text"].strip()


class OpenAIWhisperBackend(BaseBackend):
    name = "openai-whisper"

    def __init__(self, model_name: str):
        import whisper

        self._model = whisper.load_model(model_name)

    def transcribe(self, audio_path: str, language: str | None) -> str:
        kwargs = {"fp16": False}
        if language:
            kwargs["language"] = language
        result = self._model.transcribe(audio_path, **kwargs)
        return result["text"].strip()


class DictationOverlay(QWidget):
    def __init__(self):
        super().__init__(
            flags=(
                Qt.WindowType.Tool
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowDoesNotAcceptFocus
            )
        )
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("overlayFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(20, 12, 20, 12)
        self.status_label = QLabel("Listening...")
        self.status_label.setObjectName("overlayLabel")
        frame_layout.addWidget(self.status_label)
        root.addWidget(frame)
        self.setStyleSheet(
            """
            #overlayFrame {
                background-color: rgba(2, 6, 23, 240);
                border: 1px solid rgba(148, 163, 184, 110);
                border-radius: 14px;
            }
            #overlayLabel {
                color: #f8fafc;
                font-size: 17px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }
            """
        )
        self.resize(340, 70)
        self.hide()

    def _position_top_center(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geometry = screen.availableGeometry()
        x = geometry.x() + (geometry.width() - self.width()) // 2
        y = geometry.y() + 34
        self.move(x, y)

    def show_state(self, message: str):
        self.status_label.setText(message)
        self._position_top_center()
        self.show()
        self.raise_()


class OnboardingDialog(QDialog):
    def __init__(self, hotkey_hint: str, hotkey_scope: str, parent=None):
        super().__init__(parent)
        self.hotkey_scope = hotkey_scope
        self.setWindowTitle("Whisper Dictation Setup")
        self.setModal(True)
        self.resize(660, 330)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #0f172a;
                color: #e2e8f0;
            }
            QLabel#title {
                font-size: 24px;
                font-weight: 800;
                color: #f8fafc;
            }
            QLabel#body {
                font-size: 14px;
                color: #cbd5e1;
            }
            QPushButton {
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 8px 12px;
                background: #111827;
                color: #e2e8f0;
                font-weight: 600;
            }
            QPushButton:hover {
                border-color: #64748b;
            }
            QPushButton#primary {
                background: #0ea5e9;
                color: #06233a;
                border-color: #38bdf8;
            }
            """
        )

        layout = QVBoxLayout(self)
        title = QLabel("Before you start")
        title.setObjectName("title")
        if self.hotkey_scope == "global":
            body_text = (
                "Whisper Dictation needs these macOS permissions:\n"
                "1) Accessibility (global hold-to-talk)\n"
                "2) Input Monitoring (global key capture on newer macOS)\n"
                "3) Microphone (recording)\n\n"
                f"Current push-to-talk key: {hotkey_hint}"
            )
        else:
            body_text = (
                "Whisper Dictation in local mode listens only while this app window is focused.\n"
                "It requires Microphone access for recording.\n\n"
                f"Current push-to-talk key: {hotkey_hint}"
            )
        body = QLabel(body_text)
        body.setObjectName("body")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)

        controls = QHBoxLayout()
        open_microphone = QPushButton("Open Microphone")
        test_mic = QPushButton("Test Microphone")
        if self.hotkey_scope == "global":
            open_accessibility = QPushButton("Open Accessibility")
            open_input_monitoring = QPushButton("Open Input Monitoring")
            controls.addWidget(open_accessibility)
            controls.addWidget(open_input_monitoring)
            open_accessibility.clicked.connect(self.open_accessibility)
            open_input_monitoring.clicked.connect(self.open_input_monitoring)
        controls.addWidget(open_microphone)
        controls.addWidget(test_mic)
        layout.addLayout(controls)

        self.result_label = QLabel("")
        self.result_label.setObjectName("body")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        button_row = QHBoxLayout()
        continue_button = QPushButton("Continue")
        continue_button.setObjectName("primary")
        quit_button = QPushButton("Quit")
        button_row.addStretch(1)
        button_row.addWidget(quit_button)
        button_row.addWidget(continue_button)
        layout.addLayout(button_row)

        open_microphone.clicked.connect(self.open_microphone)
        test_mic.clicked.connect(self.test_microphone)
        continue_button.clicked.connect(self._continue_clicked)
        quit_button.clicked.connect(self.reject)

    def open_accessibility(self):
        QDesktopServices.openUrl(
            QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")
        )

    def open_microphone(self):
        QDesktopServices.openUrl(
            QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")
        )

    def open_input_monitoring(self):
        QDesktopServices.openUrl(
            QUrl("x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent")
        )

    def test_microphone(self):
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="float32"):
                sd.sleep(120)
            self.result_label.setText("Microphone test passed.")
        except Exception as exc:
            self.result_label.setText(f"Microphone test failed: {exc}")

    def _continue_clicked(self):
        if self.hotkey_scope != "global":
            self.accept()
            return
        missing: list[str] = []
        if not _is_accessibility_enabled():
            missing.append("Accessibility")
        if not _is_input_monitoring_enabled():
            if CGRequestListenEventAccess is not None:
                try:
                    CGRequestListenEventAccess()
                except Exception:
                    pass
            missing.append("Input Monitoring")
        if missing:
            self.result_label.setText(
                "Missing permissions: "
                + ", ".join(missing)
                + ". You can continue now, but global hold-to-talk may be limited until these are granted."
            )
        self.accept()


class SignalHandler(QObject):
    transcription_complete = pyqtSignal(str)
    status_update = pyqtSignal(str)
    start_recording_requested = pyqtSignal()
    stop_recording_requested = pyqtSignal()
    hotkey_active_changed = pyqtSignal(bool)


class WhisperDictationApp(QMainWindow):
    QT_KEY_TOKENS = {
        int(Qt.Key.Key_Control): {"ctrl", "ctrl_l", "ctrl_r"},
        int(Qt.Key.Key_Meta): {"cmd", "cmd_l", "cmd_r"},
        int(Qt.Key.Key_Alt): {"alt", "alt_l", "alt_r"},
        int(Qt.Key.Key_Shift): {"shift", "shift_l", "shift_r"},
        int(Qt.Key.Key_Space): {"space"},
        int(Qt.Key.Key_Escape): {"esc"},
    }

    def __init__(self):
        super().__init__()
        self.data_dir = Path.home() / "Library" / "Application Support" / "WhisperDictation"
        self.settings_path = self.data_dir / "settings.json"
        self.history_path = self.data_dir / "history.json"
        self.log_path = self.data_dir / "runtime.log"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.logger = self._setup_logger()

        self.signal_handler = SignalHandler()
        self.recording = False
        self.audio_data: list[np.ndarray] = []
        self.cancel_requested = False
        self.sample_rate = 16000
        self.listener = None
        self.listener_mode = "none"
        self.backend: BaseBackend | None = None
        self.backend_ready = False
        self.history: list[dict[str, str]] = []
        self.pressed_tokens: set[str] = set()
        self.pressed_lock = threading.Lock()
        self.hotkey_active = False
        self.audio_lock = threading.Lock()
        self.record_thread: threading.Thread | None = None
        self.is_quitting = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.background_activity_token = None
        self.language = _env("WHISPER_DICTATION_LANGUAGE", "")
        self.language = self.language or None
        self.hotkey_scope = _env("WHISPER_DICTATION_HOTKEY_SCOPE", "local").lower()
        if self.hotkey_scope not in {"local", "global"}:
            self.logger.warning(
                "Unknown WHISPER_DICTATION_HOTKEY_SCOPE=%s, defaulting to local",
                self.hotkey_scope,
            )
            self.hotkey_scope = "local"
        self.hotkey_tokens = _parse_hotkey(_env("WHISPER_DICTATION_HOTKEY", "ctrl"))
        self.display_hotkey = "+".join(token.upper() for token in self.hotkey_tokens)
        self.min_audio_seconds = 0.15
        self.main_model = _env(
            "WHISPER_DICTATION_MODEL", "mlx-community/whisper-large-v3-turbo"
        )
        self.fallback_model = _env("WHISPER_DICTATION_FALLBACK_MODEL", "base")
        self.overlay = DictationOverlay()
        self.settings = self._load_settings()
        self._load_history()
        self._ensure_ffmpeg_available()
        self.init_ui()
        self._setup_tray_icon()
        self._connect_signals()
        self.init_transcription_backend()
        self.setup_hotkey_capture()
        self.maybe_run_onboarding()

    def _connect_signals(self):
        self.signal_handler.transcription_complete.connect(self.handle_transcription)
        self.signal_handler.status_update.connect(self._set_status)
        self.signal_handler.start_recording_requested.connect(self.start_recording)
        self.signal_handler.stop_recording_requested.connect(self.stop_recording)
        self.signal_handler.hotkey_active_changed.connect(self._set_hotkey_indicator)

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("whisperdictation")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.FileHandler(self.log_path, encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        return logger

    def _ensure_ffmpeg_available(self) -> bool:
        # Whisper backends shell out to a binary literally named "ffmpeg".
        direct = shutil.which("ffmpeg")
        if direct:
            self.logger.info("Using ffmpeg from PATH: %s", direct)
            return True

        common_paths = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
        ]
        for candidate in common_paths:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                os.environ["PATH"] = f"{os.path.dirname(candidate)}:{os.environ.get('PATH', '')}"
                self.logger.info("Using ffmpeg from common path: %s", candidate)
                return True

        # Fallback: use imageio-ffmpeg bundled binary if available.
        try:
            import imageio_ffmpeg

            bundled = imageio_ffmpeg.get_ffmpeg_exe()
            if bundled and os.path.isfile(bundled) and os.access(bundled, os.X_OK):
                shim_dir = self.data_dir / "bin"
                shim_dir.mkdir(parents=True, exist_ok=True)
                shim_path = shim_dir / "ffmpeg"
                if shim_path.exists() or shim_path.is_symlink():
                    try:
                        shim_path.unlink()
                    except Exception:
                        pass
                if not shim_path.exists():
                    try:
                        shim_path.symlink_to(Path(bundled))
                    except Exception:
                        shutil.copy2(bundled, shim_path)
                        shim_path.chmod(0o755)
                os.environ["PATH"] = f"{shim_dir}:{os.environ.get('PATH', '')}"
                self.logger.info("Using bundled ffmpeg shim: %s -> %s", shim_path, bundled)
                return True
        except Exception as exc:
            self.logger.warning("Bundled ffmpeg lookup failed: %s", exc)

        self.logger.error("ffmpeg not found; transcription backends will fail to load")
        return False

    def init_ui(self):
        self.setWindowTitle("Whisper Dictation")
        self.setGeometry(120, 120, 980, 620)
        self.setMinimumSize(820, 520)
        app_icon = self._load_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self._apply_styles()

        central_widget = QWidget()
        central_widget.setObjectName("root")
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Whisper Dictation")
        title.setObjectName("title")
        if self.hotkey_scope == "global":
            subtitle_text = (
                f"Hold {self.display_hotkey} to dictate, release to transcribe. "
                "Transcript is copied to clipboard and saved below."
            )
        else:
            subtitle_text = (
                f"Hold {self.display_hotkey} while this app is focused to dictate, "
                "release to transcribe. Transcript is copied to clipboard and saved below."
            )
        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        status_card = QFrame()
        status_card.setObjectName("statusCard")
        status_layout = QHBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(12)
        self.status_label = QLabel("Loading transcription backend...")
        self.status_label.setObjectName("statusText")
        self.hotkey_indicator = QLabel("HOTKEY IDLE")
        self.hotkey_indicator.setObjectName("hotkeyIdle")
        status_layout.addWidget(self.status_label, stretch=1)
        status_layout.addWidget(self.hotkey_indicator)
        layout.addWidget(status_card)

        self.history_list = QListWidget()
        self.history_list.setObjectName("historyList")
        self.history_list.itemClicked.connect(self.copy_clicked_item)
        layout.addWidget(self.history_list, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.record_button = QPushButton("Stop Recording")
        self.record_button.setEnabled(False)
        self.record_button.clicked.connect(self.stop_recording)
        self.copy_button = QPushButton("Copy Selected")
        self.copy_button.clicked.connect(self.copy_selected_item)
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self.clear_history)
        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.quit_app)
        self.hide_button = QPushButton("Hide Window")
        self.hide_button.clicked.connect(self.hide_to_background)
        controls.addWidget(self.record_button)
        controls.addStretch(1)
        controls.addWidget(self.copy_button)
        controls.addWidget(self.clear_button)
        controls.addWidget(self.hide_button)
        controls.addWidget(self.quit_button)
        layout.addLayout(controls)

        self._refresh_history_list()

    def _apply_styles(self):
        self.setStyleSheet(
            """
            QWidget#root {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0b1020, stop:0.45 #111827, stop:1 #1f2937);
                color: #e5e7eb;
                font-family: "SF Pro Text", "Avenir Next", "Segoe UI", sans-serif;
            }
            QLabel#title {
                font-size: 36px;
                font-weight: 800;
                color: #f8fafc;
                letter-spacing: 0.5px;
            }
            QLabel#subtitle {
                font-size: 15px;
                color: #94a3b8;
                margin-bottom: 4px;
            }
            QFrame#statusCard {
                background: rgba(15, 23, 42, 0.65);
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 12px;
            }
            QLabel#statusText {
                font-size: 14px;
                color: #dbeafe;
                font-weight: 600;
            }
            QLabel#hotkeyIdle {
                background: #1f2937;
                border: 1px solid #334155;
                color: #cbd5e1;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.6px;
            }
            QLabel#hotkeyActive {
                background: #064e3b;
                border: 1px solid #10b981;
                color: #d1fae5;
                border-radius: 999px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.6px;
            }
            QListWidget#historyList {
                background: rgba(2, 6, 23, 0.62);
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 14px;
                padding: 6px;
                font-size: 14px;
                color: #e5e7eb;
            }
            QListWidget#historyList::item {
                padding: 10px 12px;
                border-bottom: 1px solid rgba(148, 163, 184, 0.15);
            }
            QListWidget#historyList::item:selected {
                background: rgba(14, 165, 233, 0.22);
                border-radius: 8px;
            }
            QPushButton {
                background: #111827;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 13px;
                font-weight: 650;
            }
            QPushButton:hover {
                border-color: #60a5fa;
            }
            QPushButton:disabled {
                color: #64748b;
                border-color: #1f2937;
            }
            """
        )

    def _set_status(self, message: str):
        self.status_label.setText(message)

    def _set_hotkey_indicator(self, active: bool):
        if active:
            self.hotkey_indicator.setText("HOTKEY DOWN")
            self.hotkey_indicator.setObjectName("hotkeyActive")
        else:
            self.hotkey_indicator.setText("HOTKEY IDLE")
            self.hotkey_indicator.setObjectName("hotkeyIdle")
        self.hotkey_indicator.style().unpolish(self.hotkey_indicator)
        self.hotkey_indicator.style().polish(self.hotkey_indicator)

    def init_transcription_backend(self):
        def load_backend():
            self.signal_handler.status_update.emit("Loading transcription backend...")
            self.backend_ready = False
            try:
                backend = MLXWhisperBackend(self.main_model)
                self.signal_handler.status_update.emit(
                    "Preparing MLX model (first run can take about a minute)..."
                )
                self._warmup_backend(backend)
                self.backend = backend
                self.backend_ready = True
                self.signal_handler.status_update.emit(
                    f"Ready ({self.backend.name}) - hold {self.display_hotkey}."
                )
                self.logger.info("Loaded backend: %s", self.backend.name)
                return
            except Exception as mlx_error:
                self.logger.exception("MLX backend unavailable: %s", mlx_error)
                print(f"MLX backend unavailable: {mlx_error}")

            try:
                backend = OpenAIWhisperBackend(self.fallback_model)
                self.signal_handler.status_update.emit(
                    "Preparing fallback model (first run can take about a minute)..."
                )
                self._warmup_backend(backend)
                self.backend = backend
                self.backend_ready = True
                self.signal_handler.status_update.emit(
                    f"Ready ({self.backend.name}) - hold {self.display_hotkey}."
                )
                self.logger.info("Loaded backend: %s", self.backend.name)
            except Exception as whisper_error:
                self.signal_handler.status_update.emit(
                    "Failed to load transcription backend. Check installation."
                )
                self.logger.exception("OpenAI Whisper backend unavailable: %s", whisper_error)
                print(f"OpenAI Whisper backend unavailable: {whisper_error}")

        threading.Thread(target=load_backend, daemon=True).start()

    def _warmup_backend(self, backend: BaseBackend):
        warmup_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as warmup_audio:
                warmup_path = warmup_audio.name
            silent = np.zeros(int(self.sample_rate * 0.35), dtype=np.float32)
            wavfile.write(warmup_path, self.sample_rate, (silent * 32767.0).astype(np.int16))
            backend.transcribe(warmup_path, self.language)
        finally:
            if warmup_path and os.path.exists(warmup_path):
                os.unlink(warmup_path)

    def setup_hotkey_capture(self):
        if self.hotkey_scope == "global":
            self.setup_global_hotkey()
            self._begin_background_activity()
            return
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        self.listener_mode = "local-ui"
        self.logger.info("Hotkey listener mode: local-ui")

    def setup_global_hotkey(self):
        try:
            if QuartzHotkeyListener.supports_tokens(self.hotkey_tokens):
                self.listener = QuartzHotkeyListener(
                    hotkey_tokens=self.hotkey_tokens,
                    on_hotkey_change=self._on_quartz_hotkey_change,
                    on_escape=self._on_quartz_escape,
                    on_error=self._on_hotkey_listener_error,
                )
                self.listener_mode = "quartz"
                self.listener.start()
                self.logger.info("Global hotkey listener mode: quartz")
            elif AppKitHotkeyListener.supports_tokens(self.hotkey_tokens):
                self.listener = AppKitHotkeyListener(
                    hotkey_tokens=self.hotkey_tokens,
                    on_hotkey_change=self._on_quartz_hotkey_change,
                    on_escape=self._on_quartz_escape,
                    on_error=self._on_hotkey_listener_error,
                )
                self.listener_mode = "appkit"
                self.listener.start()
                self.logger.info("Global hotkey listener mode: appkit")
            elif KeyStatePollingHotkeyListener.supports_tokens(self.hotkey_tokens):
                self.listener = KeyStatePollingHotkeyListener(
                    hotkey_tokens=self.hotkey_tokens,
                    on_hotkey_change=self._on_quartz_hotkey_change,
                    on_escape=self._on_quartz_escape,
                    on_error=self._on_hotkey_listener_error,
                )
                self.listener_mode = "keystate-polling"
                self.listener.start()
                self.logger.info("Global hotkey listener mode: keystate-polling")
            elif ModifierPollingHotkeyListener.supports_tokens(self.hotkey_tokens):
                self.listener = ModifierPollingHotkeyListener(
                    hotkey_tokens=self.hotkey_tokens,
                    on_hotkey_change=self._on_quartz_hotkey_change,
                    on_error=self._on_hotkey_listener_error,
                )
                self.listener_mode = "polling"
                self.listener.start()
                self.logger.info("Global hotkey listener mode: polling")
            else:
                self.listener = pynput_keyboard.Listener(
                    on_press=self._on_global_press,
                    on_release=self._on_global_release,
                )
                self.listener_mode = "pynput"
                self.listener.start()
                self.logger.info("Global hotkey listener mode: pynput")
        except Exception as exc:
            self._set_status(f"Global hotkey listener failed: {exc}")
            self.logger.exception("Global hotkey listener failed: %s", exc)

    def _on_hotkey_listener_error(self, message: str):
        if self.listener_mode in {"quartz", "appkit", "keystate-polling", "polling"}:
            try:
                if (
                    self.listener_mode == "quartz"
                    and AppKitHotkeyListener.supports_tokens(self.hotkey_tokens)
                ):
                    self.listener = AppKitHotkeyListener(
                        hotkey_tokens=self.hotkey_tokens,
                        on_hotkey_change=self._on_quartz_hotkey_change,
                        on_escape=self._on_quartz_escape,
                        on_error=self._on_hotkey_listener_error,
                    )
                    self.listener_mode = "appkit"
                    self.listener.start()
                    message = f"{message} Falling back to AppKit hotkey listener."
                elif (
                    self.listener_mode in {"quartz", "appkit"}
                    and KeyStatePollingHotkeyListener.supports_tokens(self.hotkey_tokens)
                ):
                    self.listener = KeyStatePollingHotkeyListener(
                        hotkey_tokens=self.hotkey_tokens,
                        on_hotkey_change=self._on_quartz_hotkey_change,
                        on_escape=self._on_quartz_escape,
                        on_error=self._on_hotkey_listener_error,
                    )
                    self.listener_mode = "keystate-polling"
                    self.listener.start()
                    message = f"{message} Falling back to key-state polling listener."
                elif (
                    self.listener_mode in {"quartz", "appkit", "keystate-polling"}
                    and ModifierPollingHotkeyListener.supports_tokens(self.hotkey_tokens)
                ):
                    self.listener = ModifierPollingHotkeyListener(
                        hotkey_tokens=self.hotkey_tokens,
                        on_hotkey_change=self._on_quartz_hotkey_change,
                        on_error=self._on_hotkey_listener_error,
                    )
                    self.listener_mode = "polling"
                    self.listener.start()
                    message = f"{message} Falling back to modifier polling listener."
                else:
                    self.listener = pynput_keyboard.Listener(
                        on_press=self._on_global_press,
                        on_release=self._on_global_release,
                    )
                    self.listener_mode = "pynput"
                    self.listener.start()
                    message = (
                        f"{message} Falling back to pynput listener (may only work while focused)."
                    )
            except Exception as exc:
                message = f"{message} Fallback listener failed: {exc}"
        self.logger.error(message)
        self.signal_handler.status_update.emit(message)

    def _begin_background_activity(self):
        if (
            NSProcessInfo is None
            or NSActivityUserInitiatedAllowingIdleSystemSleep is None
            or NSActivityLatencyCritical is None
        ):
            return
        if self.background_activity_token is not None:
            return
        try:
            options = (
                int(NSActivityUserInitiatedAllowingIdleSystemSleep)
                | int(NSActivityLatencyCritical)
            )
            self.background_activity_token = (
                NSProcessInfo.processInfo().beginActivityWithOptions_reason_(
                    options,
                    "Whisper Dictation global hold-to-talk",
                )
            )
            self.logger.info("Background activity assertion enabled")
        except Exception as exc:
            self.logger.warning("Failed to enable background activity assertion: %s", exc)

    def _end_background_activity(self):
        if NSProcessInfo is None:
            return
        if self.background_activity_token is None:
            return
        try:
            NSProcessInfo.processInfo().endActivity_(self.background_activity_token)
        except Exception:
            pass
        self.background_activity_token = None

    def _on_quartz_hotkey_change(self, active: bool):
        should_start = False
        should_stop = False
        with self.pressed_lock:
            was_active = self.hotkey_active
            self.hotkey_active = active
            if (not was_active) and active and (not self.recording):
                should_start = True
            if self.recording and was_active and (not active):
                should_stop = True
        self.signal_handler.hotkey_active_changed.emit(active)
        if should_start:
            self.signal_handler.start_recording_requested.emit()
        if should_stop:
            self.signal_handler.stop_recording_requested.emit()

    def _on_quartz_escape(self):
        if self.recording:
            self.cancel_requested = True
            self.signal_handler.stop_recording_requested.emit()

    def _hotkey_active_locked(self) -> bool:
        for token in self.hotkey_tokens:
            if token not in self.pressed_tokens:
                return False
        return True

    def eventFilter(self, watched, event):
        if self.hotkey_scope != "local":
            return super().eventFilter(watched, event)

        event_type = event.type()
        if event_type not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return super().eventFilter(watched, event)

        if event.isAutoRepeat():
            return super().eventFilter(watched, event)

        keycode = int(event.key())
        if event_type == QEvent.Type.KeyPress:
            self._on_ui_key_press(keycode)
        else:
            self._on_ui_key_release(keycode)
        return super().eventFilter(watched, event)

    def _qt_tokens_for_key(self, keycode: int) -> set[str]:
        return set(self.QT_KEY_TOKENS.get(keycode, set()))

    def _on_ui_key_press(self, keycode: int):
        key_names = self._qt_tokens_for_key(keycode)
        if not key_names:
            return
        should_start = False
        hotkey_active = False
        with self.pressed_lock:
            was_active = self._hotkey_active_locked()
            self.pressed_tokens.update(key_names)
            hotkey_active = self._hotkey_active_locked()
            self.hotkey_active = hotkey_active
            if (not was_active) and hotkey_active and (not self.recording):
                should_start = True

        self.signal_handler.hotkey_active_changed.emit(hotkey_active)

        if "esc" in key_names and self.recording:
            self.cancel_requested = True
            self.signal_handler.stop_recording_requested.emit()
            return
        if should_start:
            self.signal_handler.start_recording_requested.emit()

    def _on_ui_key_release(self, keycode: int):
        key_names = self._qt_tokens_for_key(keycode)
        if not key_names:
            return
        should_stop = False
        hotkey_active = False
        with self.pressed_lock:
            was_active = self._hotkey_active_locked()
            self.pressed_tokens.difference_update(key_names)
            hotkey_active = self._hotkey_active_locked()
            self.hotkey_active = hotkey_active
            if self.recording and was_active and (not hotkey_active):
                should_stop = True

        self.signal_handler.hotkey_active_changed.emit(hotkey_active)
        if should_stop:
            self.signal_handler.stop_recording_requested.emit()

    def _on_global_press(self, key):
        key_names = _key_names(key)
        if not key_names:
            return

        should_start = False
        hotkey_active = False
        with self.pressed_lock:
            was_active = self._hotkey_active_locked()
            self.pressed_tokens.update(key_names)
            hotkey_active = self._hotkey_active_locked()
            self.hotkey_active = hotkey_active
            if (not was_active) and hotkey_active and (not self.recording):
                should_start = True

        self.signal_handler.hotkey_active_changed.emit(hotkey_active)

        if "esc" in key_names and self.recording:
            self.cancel_requested = True
            self.signal_handler.stop_recording_requested.emit()
            return
        if should_start:
            self.signal_handler.start_recording_requested.emit()

    def _on_global_release(self, key):
        key_names = _key_names(key)
        if not key_names:
            return

        should_stop = False
        hotkey_active = False
        with self.pressed_lock:
            was_active = self._hotkey_active_locked()
            self.pressed_tokens.difference_update(key_names)
            hotkey_active = self._hotkey_active_locked()
            self.hotkey_active = hotkey_active
            if self.recording and was_active and (not hotkey_active):
                should_stop = True

        self.signal_handler.hotkey_active_changed.emit(hotkey_active)
        if should_stop:
            self.signal_handler.stop_recording_requested.emit()

    def start_recording(self):
        if self.recording:
            return
        if self.backend is None or not self.backend_ready:
            self._set_status("Model still preparing... please wait.")
            return
        self.recording = True
        with self.audio_lock:
            self.audio_data = []
        self.cancel_requested = False
        self.logger.info("Recording started")
        self.record_button.setEnabled(True)
        self._set_status("Recording... release to transcribe to clipboard, Esc to cancel.")
        self.overlay.show_state("Listening...")
        self.record_thread = threading.Thread(target=self._record_audio, daemon=True)
        self.record_thread.start()

    def _record_audio(self):
        def callback(indata, frames, time_info, status):
            del frames, time_info
            if status:
                print(f"Audio callback status: {status}")
            with self.audio_lock:
                self.audio_data.append(indata.copy())

        try:
            with sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
            ):
                while self.recording:
                    sd.sleep(60)
        except Exception as exc:
            self.cancel_requested = True
            self.signal_handler.stop_recording_requested.emit()
            self.signal_handler.status_update.emit(f"Microphone error: {exc}")
            self.logger.exception("Microphone error: %s", exc)

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        if self.record_thread and self.record_thread.is_alive():
            self.record_thread.join(timeout=1.2)
        self.record_thread = None
        self.record_button.setEnabled(False)
        with self.audio_lock:
            chunk_count = len(self.audio_data)
        self.logger.info("Stop requested with %d audio chunks buffered", chunk_count)
        if self.cancel_requested:
            with self.audio_lock:
                self.audio_data = []
            self.overlay.hide()
            self._set_status(f"Cancelled. Ready (hold {self.display_hotkey}).")
            self.logger.info("Recording cancelled")
            return
        with self.audio_lock:
            chunks = [chunk.copy() for chunk in self.audio_data]
            self.audio_data = []
        self.overlay.show_state("Transcribing...")
        self._set_status("Transcribing...")
        self.logger.info("Recording stopped, starting transcription")
        threading.Thread(target=self._process_audio, args=(chunks,), daemon=True).start()

    def _process_audio(self, chunks: list[np.ndarray]):
        if not chunks:
            self.logger.info("No audio captured; skipping transcription")
            self.signal_handler.transcription_complete.emit("")
            return
        audio = np.concatenate(chunks, axis=0).flatten().astype(np.float32)
        duration_s = len(audio) / float(self.sample_rate)
        peak = float(np.max(np.abs(audio))) if audio.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
        self.logger.info(
            "Captured audio duration: %.2fs (chunks=%d, rms=%.6f, peak=%.6f)",
            duration_s,
            len(chunks),
            rms,
            peak,
        )
        if duration_s < self.min_audio_seconds:
            self.logger.info("Audio too short; skipping transcription")
            self.signal_handler.transcription_complete.emit("")
            return
        if peak > 0.0:
            gain = min(20.0, 0.92 / peak)
            if gain > 1.0:
                audio = np.clip(audio * gain, -1.0, 1.0)
                self.logger.info("Applied automatic input gain: %.2fx", gain)
        if self.backend is None:
            self.signal_handler.status_update.emit("Backend unavailable.")
            self.logger.error("Backend unavailable during transcription")
            return

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                temp_path = temp_audio.name
            pcm16 = np.clip(audio, -1.0, 1.0)
            wavfile.write(temp_path, self.sample_rate, (pcm16 * 32767.0).astype(np.int16))
            text = self.backend.transcribe(temp_path, self.language)
            self.logger.info("Transcription produced %d chars", len(text))
            self.signal_handler.transcription_complete.emit(text)
        except Exception as exc:
            print(f"Transcription failed: {exc}")
            self.signal_handler.status_update.emit(f"Transcription failed: {exc}")
            self.logger.exception("Transcription failed: %s", exc)
            self.signal_handler.transcription_complete.emit("")
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    def _copy_to_clipboard(self, text: str):
        if not text:
            return
        pyperclip.copy(text)

    def handle_transcription(self, text):
        if text:
            self._append_history(text)
            try:
                self._copy_to_clipboard(text)
                self.logger.info("Copied transcript to clipboard")
            except Exception as exc:
                self.logger.exception("Clipboard copy failed: %s", exc)
                self._set_status(
                    "Transcript captured, but clipboard copy failed."
                )
                self.overlay.hide()
                return
        else:
            self.logger.info("No transcript text to insert")
            self._set_status(f"No speech detected. Ready ({self.display_hotkey}).")
            self.overlay.hide()
            return
        self.overlay.hide()
        self._set_status(f"Copied to clipboard. Ready (hold {self.display_hotkey}).")

    def copy_selected_item(self):
        item = self.history_list.currentItem()
        if item is None:
            return
        text = item.data(Qt.ItemDataRole.UserRole) or ""
        if not text:
            return
        pyperclip.copy(text)
        self._set_status("Copied selected transcript.")

    def copy_clicked_item(self, item: QListWidgetItem):
        text = item.data(Qt.ItemDataRole.UserRole) or ""
        if not text:
            return
        pyperclip.copy(text)
        self._set_status("Copied transcript.")

    def clear_history(self):
        confirm = QMessageBox.question(
            self,
            "Clear history",
            "Delete all saved transcripts?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.history = []
        self._save_history()
        self._refresh_history_list()
        self._set_status("History cleared.")

    def _append_history(self, text: str):
        entry = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "text": text,
        }
        self.history.append(entry)
        if len(self.history) > 1000:
            self.history = self.history[-1000:]
        self._save_history()
        self._insert_history_item(entry, at_top=True)

    def _insert_history_item(self, entry: dict[str, str], at_top: bool):
        timestamp = entry.get("timestamp", "")
        text = entry.get("text", "")
        preview = " ".join(text.split())
        if len(preview) > 220:
            preview = preview[:217] + "..."
        item = QListWidgetItem(f"[{timestamp}] {preview}")
        item.setData(Qt.ItemDataRole.UserRole, text)
        if at_top:
            self.history_list.insertItem(0, item)
        else:
            self.history_list.addItem(item)

    def _refresh_history_list(self):
        self.history_list.clear()
        for entry in reversed(self.history):
            self._insert_history_item(entry, at_top=False)

    def _load_settings(self) -> dict:
        if not self.settings_path.exists():
            return {"onboarding_complete": False}
        try:
            with self.settings_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {"onboarding_complete": False}

    def _save_settings(self):
        with self.settings_path.open("w", encoding="utf-8") as handle:
            json.dump(self.settings, handle, indent=2)

    def _load_history(self):
        if not self.history_path.exists():
            self.history = []
            return
        try:
            with self.history_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, list):
                    self.history = [
                        item
                        for item in loaded
                        if isinstance(item, dict) and "text" in item and "timestamp" in item
                    ]
                else:
                    self.history = []
        except Exception:
            self.history = []

    def _save_history(self):
        with self.history_path.open("w", encoding="utf-8") as handle:
            json.dump(self.history, handle, indent=2)

    def maybe_run_onboarding(self):
        if self.settings.get("onboarding_complete"):
            return
        dialog = OnboardingDialog(self.display_hotkey, self.hotkey_scope, self)
        result = dialog.exec()
        if result == QDialog.DialogCode.Accepted:
            self.settings["onboarding_complete"] = True
            self._save_settings()
            return
        self.quit_app()

    def _setup_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.logger.warning("System tray is not available; background menu icon disabled")
            return
        self.tray_icon = QSystemTrayIcon(self)
        tray_icon = self._load_app_icon()
        if tray_icon.isNull():
            tray_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(tray_icon)
        self.setWindowIcon(tray_icon)
        self.tray_icon.setToolTip("Whisper Dictation")

        menu = QMenu(self)
        show_action = QAction("Show Window", self)
        hide_action = QAction("Hide Window", self)
        quit_action = QAction("Quit", self)
        show_action.triggered.connect(self.show_main_window)
        hide_action.triggered.connect(self.hide_to_background)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(show_action)
        menu.addAction(hide_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _icon_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        try:
            base = Path(__file__).resolve().parents[2]
            candidates.append(base / "assets" / "AppIcon.png")
        except Exception:
            pass

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass) / "assets" / "AppIcon.png")

        try:
            bundle_resources = Path(sys.executable).resolve().parents[1] / "Resources"
            candidates.append(bundle_resources / "assets" / "AppIcon.png")
        except Exception:
            pass

        return candidates

    def _load_app_icon(self) -> QIcon:
        for candidate in self._icon_candidates():
            if candidate.exists():
                return QIcon(str(candidate))
        return QIcon()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_main_window()

    def show_main_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def hide_to_background(self):
        self.hide()

    def quit_app(self):
        self.is_quitting = True
        app = QApplication.instance()
        if self.hotkey_scope == "local" and app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        if self.listener:
            try:
                self.listener.stop()
                if hasattr(self.listener, "join"):
                    self.listener.join(timeout=1.0)
            except Exception:
                pass
            self.listener = None
        self._end_background_activity()
        if self.tray_icon:
            self.tray_icon.hide()
        self.overlay.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.is_quitting:
            event.accept()
            return
        self.hide_to_background()
        event.ignore()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = WhisperDictationApp()
    window.show()
    sys.exit(app.exec())

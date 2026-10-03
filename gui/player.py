"""
gui/player.py
==============
Built-in audiobook player widget (PyQt6).

Features
--------
  - Play / Pause / Resume
  - Seek slider
  - Skip ±30 seconds
  - Speed selector
  - Time display (elapsed / total)

Uses QMediaPlayer (built into PyQt6 via Qt Multimedia).
No external audio library required for playback.
"""

from __future__ import annotations

import os
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QSlider, QLabel, QComboBox, QSizePolicy,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon


# --------------------------------------------------------------------------- #
# Player Widget
# --------------------------------------------------------------------------- #
class AudiobookPlayer(QWidget):
    """
    Embeddable player widget.

    Signals
    -------
    playback_started(path: str)
    playback_finished()
    """

    playback_started = pyqtSignal(str)
    playback_finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_path: str = ""
        self._setup_media()
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------ #
    # Media backend
    # ------------------------------------------------------------------ #
    def _setup_media(self):
        self._player = QMediaPlayer()
        self._audio_out = QAudioOutput()
        self._player.setAudioOutput(self._audio_out)
        self._audio_out.setVolume(0.9)

        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        self.setObjectName("AudiobookPlayer")
        self.setStyleSheet("""
            #AudiobookPlayer {
                background: #131624;
                border: 1px solid #2a2e42;
                border-radius: 12px;
                padding: 8px;
            }
            QPushButton {
                background: #1e2233;
                border: 1px solid #2a2e42;
                border-radius: 8px;
                color: #e8eaf0;
                padding: 6px 14px;
                font-size: 13px;
            }
            QPushButton:hover { background: #f0722e; border-color: #f0722e; }
            QPushButton:pressed { background: #c85a22; }
            QPushButton:disabled { color: #444; border-color: #2a2e42; }
            QSlider::groove:horizontal {
                height: 6px;
                background: #2a2e42;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #f0722e;
                width: 14px; height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #f0722e;
                border-radius: 3px;
            }
            QLabel { color: #8a8fa8; font-size: 12px; }
            QComboBox {
                background: #1e2233;
                border: 1px solid #2a2e42;
                border-radius: 6px;
                color: #e8eaf0;
                padding: 3px 8px;
                font-size: 12px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #1e2233;
                border: 1px solid #2a2e42;
                color: #e8eaf0;
                selection-background-color: #f0722e;
            }
        """)

        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 10, 12, 10)

        # Title label
        self._title_lbl = QLabel("No audiobook loaded")
        self._title_lbl.setStyleSheet("color: #e8eaf0; font-size: 13px; font-weight: 600;")
        self._title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title_lbl)

        # Seek slider
        self._seek_slider = QSlider(Qt.Orientation.Horizontal)
        self._seek_slider.setRange(0, 1000)
        self._seek_slider.setValue(0)
        self._seek_slider.setEnabled(False)
        root.addWidget(self._seek_slider)

        # Time labels
        time_row = QHBoxLayout()
        self._elapsed_lbl = QLabel("0:00")
        self._total_lbl = QLabel("0:00")
        time_row.addWidget(self._elapsed_lbl)
        time_row.addStretch()
        time_row.addWidget(self._total_lbl)
        root.addLayout(time_row)

        # Control buttons
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._skip_back_btn = QPushButton("⏮ 30s")
        self._play_pause_btn = QPushButton("▶  Play")
        self._skip_fwd_btn = QPushButton("30s ⏭")

        self._play_pause_btn.setFixedWidth(100)
        for btn in (self._skip_back_btn, self._play_pause_btn, self._skip_fwd_btn):
            btn.setEnabled(False)
            ctrl_row.addWidget(btn)

        # Speed selector
        ctrl_row.addStretch()
        speed_lbl = QLabel("Speed:")
        speed_lbl.setStyleSheet("color: #8a8fa8; font-size: 12px;")
        ctrl_row.addWidget(speed_lbl)
        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.5×", "0.75×", "1.0×", "1.25×", "1.5×", "2.0×"])
        self._speed_combo.setCurrentIndex(2)
        self._speed_combo.setFixedWidth(70)
        ctrl_row.addWidget(self._speed_combo)

        root.addLayout(ctrl_row)

    # ------------------------------------------------------------------ #
    # Signal connections
    # ------------------------------------------------------------------ #
    def _connect_signals(self):
        self._play_pause_btn.clicked.connect(self._toggle_play_pause)
        self._skip_back_btn.clicked.connect(lambda: self._skip(-30_000))
        self._skip_fwd_btn.clicked.connect(lambda: self._skip(30_000))
        self._seek_slider.sliderMoved.connect(self._on_seek)
        self._speed_combo.currentIndexChanged.connect(self._on_speed_change)
        self._player.playbackStateChanged.connect(self._on_state_change)
        self._player.durationChanged.connect(self._on_duration_change)
        self._player.mediaStatusChanged.connect(self._on_media_status)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def load(self, file_path: str, title: str = ""):
        """Load an audio file into the player."""
        if not os.path.isfile(file_path):
            return
        self._file_path = file_path
        self._player.setSource(QUrl.fromLocalFile(file_path))
        self._title_lbl.setText(title or os.path.basename(file_path))
        self._play_pause_btn.setEnabled(True)
        self._skip_back_btn.setEnabled(True)
        self._skip_fwd_btn.setEnabled(True)
        self._seek_slider.setEnabled(True)

    def stop(self):
        self._player.stop()
        self._timer.stop()

    # ------------------------------------------------------------------ #
    # Slots
    # ------------------------------------------------------------------ #
    def _toggle_play_pause(self):
        state = self._player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self._timer.stop()
            self._play_pause_btn.setText("▶  Play")
        else:
            self._player.play()
            self._timer.start()
            self._play_pause_btn.setText("⏸  Pause")
            self.playback_started.emit(self._file_path)

    def _skip(self, ms: int):
        pos = self._player.position() + ms
        pos = max(0, min(pos, self._player.duration()))
        self._player.setPosition(pos)

    def _on_seek(self, value: int):
        if self._player.duration() > 0:
            pos = int(value / 1000 * self._player.duration())
            self._player.setPosition(pos)

    def _on_speed_change(self, idx: int):
        speeds = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
        self._player.setPlaybackRate(speeds[idx])

    def _on_state_change(self, state):
        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._play_pause_btn.setText("▶  Play")
            self._timer.stop()

    def _on_duration_change(self, duration_ms: int):
        self._total_lbl.setText(_ms_to_str(duration_ms))

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_pause_btn.setText("▶  Play")
            self._seek_slider.setValue(0)
            self._elapsed_lbl.setText("0:00")
            self.playback_finished.emit()

    def _tick(self):
        pos = self._player.position()
        dur = self._player.duration()
        self._elapsed_lbl.setText(_ms_to_str(pos))
        if dur > 0:
            self._seek_slider.setValue(int(pos / dur * 1000))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _ms_to_str(ms: int) -> str:
    s = ms // 1000
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"

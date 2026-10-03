"""
gui/interface.py
================
Main application window for the PDF Audiobook Converter.

Layout (left panel + right panel):
  Left  │  Right
  ──────┼──────────────────────────────
  PDF   │  Voice Settings
  Info  │  Conversion Controls
  ──────┤  Progress Bar
  Library│  Built-in Player

All heavy work runs in QThread workers to keep the UI responsive.
"""

from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFileDialog, QSlider,
    QComboBox, QProgressBar, QFrame, QScrollArea,
    QGridLayout, QSizePolicy, QMessageBox, QLineEdit,
    QSplitter, QListWidget, QListWidgetItem, QAbstractItemView,
    QGroupBox, QDoubleSpinBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer, QMimeData, QUrl
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent, QColor

from gui.player import AudiobookPlayer
from pdf_processing.pdf_reader import PDFReader, PDFDocument
from tts.voice_manager import VoiceManager, VoiceInfo
from tts.tts_engine import TTSEngine
from audio.audio_generator import AudioGenerator
from audio.audio_merger import AudioMerger
from library.audiobook_manager import AudiobookManager, AudiobookEntry


# --------------------------------------------------------------------------- #
# Stylesheet
# --------------------------------------------------------------------------- #
STYLE = """
/* ── Base ─────────────────────────────────────────────── */
QWidget { background: #0d0f14; color: #e8eaf0; font-family: 'Segoe UI', Ubuntu, sans-serif; }

/* ── Groups ───────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #1e2233;
    border-radius: 10px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-size: 11px;
    font-weight: 600;
    color: #5c6280;
    letter-spacing: 1px;
    text-transform: uppercase;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    top: -2px;
    padding: 0 6px;
    background: #0d0f14;
}

/* ── Buttons ──────────────────────────────────────────── */
QPushButton {
    background: #1a1d2b;
    border: 1px solid #2a2e42;
    border-radius: 8px;
    color: #c8cad8;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 500;
}
QPushButton:hover { background: #1e2238; border-color: #f0722e; color: #fff; }
QPushButton:pressed { background: #f0722e; color: #fff; border-color: #f0722e; }
QPushButton:disabled { color: #3a3f56; border-color: #1e2130; }

QPushButton#convertBtn {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #f0722e, stop:1 #e04820);
    border: none;
    color: #fff;
    font-size: 15px;
    font-weight: 700;
    padding: 12px 24px;
    border-radius: 10px;
    letter-spacing: 0.5px;
}
QPushButton#convertBtn:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #ff8c4a, stop:1 #f05030);
}
QPushButton#convertBtn:disabled {
    background: #2a2e42;
    color: #3a3f56;
}

QPushButton#uploadBtn {
    background: #131624;
    border: 2px dashed #2a2e42;
    border-radius: 12px;
    color: #5c6280;
    font-size: 14px;
    padding: 20px;
    min-height: 80px;
}
QPushButton#uploadBtn:hover {
    border-color: #f0722e;
    color: #f0722e;
    background: #16192a;
}

/* ── ComboBox ─────────────────────────────────────────── */
QComboBox {
    background: #131624;
    border: 1px solid #2a2e42;
    border-radius: 7px;
    color: #e8eaf0;
    padding: 6px 10px;
    font-size: 13px;
    min-height: 28px;
}
QComboBox:hover { border-color: #f0722e; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: #131624;
    border: 1px solid #2a2e42;
    color: #e8eaf0;
    selection-background-color: #f0722e;
    selection-color: #fff;
    outline: none;
}

/* ── Sliders ──────────────────────────────────────────── */
QSlider::groove:horizontal {
    height: 5px; background: #1e2233; border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #f0722e; width: 14px; height: 14px;
    margin: -5px 0; border-radius: 7px;
}
QSlider::sub-page:horizontal { background: #f0722e; border-radius: 3px; }

/* ── Progress Bar ─────────────────────────────────────── */
QProgressBar {
    background: #1a1d2b;
    border: 1px solid #2a2e42;
    border-radius: 7px;
    height: 14px;
    text-align: center;
    font-size: 11px;
    color: #8a8fa8;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #f0722e, stop:1 #e05030);
    border-radius: 6px;
}

/* ── List Widget ──────────────────────────────────────── */
QListWidget {
    background: #0d0f14;
    border: 1px solid #1e2233;
    border-radius: 10px;
    outline: none;
}
QListWidget::item {
    padding: 10px;
    border-bottom: 1px solid #1a1d2b;
    border-radius: 0px;
}
QListWidget::item:selected {
    background: #1a1d2b;
    color: #f0722e;
}
QListWidget::item:hover { background: #131624; }

/* ── Labels ───────────────────────────────────────────── */
QLabel#sectionHeader {
    font-size: 18px; font-weight: 700; color: #e8eaf0; letter-spacing: -0.3px;
}
QLabel#subLabel { font-size: 12px; color: #5c6280; }
QLabel#fieldLabel { font-size: 12px; color: #8a8fa8; }
QLabel#valueLabel { font-size: 13px; color: #e8eaf0; }
QLabel#statusLabel { font-size: 12px; color: #f0722e; }

/* ── Line Edit ────────────────────────────────────────── */
QLineEdit {
    background: #131624;
    border: 1px solid #2a2e42;
    border-radius: 7px;
    color: #e8eaf0;
    padding: 6px 10px;
    font-size: 13px;
}
QLineEdit:focus { border-color: #f0722e; }

/* ── Spin boxes ───────────────────────────────────────── */
QDoubleSpinBox, QSpinBox {
    background: #131624;
    border: 1px solid #2a2e42;
    border-radius: 7px;
    color: #e8eaf0;
    padding: 5px 8px;
    font-size: 13px;
}
QDoubleSpinBox:focus, QSpinBox:focus { border-color: #f0722e; }

/* ── Scrollbars ───────────────────────────────────────── */
QScrollBar:vertical { background: #0d0f14; width: 7px; }
QScrollBar::handle:vertical { background: #2a2e42; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #f0722e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

/* ── Splitter ─────────────────────────────────────────── */
QSplitter::handle { background: #1e2233; width: 2px; }
"""


# --------------------------------------------------------------------------- #
# Background worker signals
# --------------------------------------------------------------------------- #
class WorkerSignals(QObject):
    progress = pyqtSignal(int, int, str)   # done, total, message
    finished = pyqtSignal(str)             # output_path
    error = pyqtSignal(str)


class ConversionWorker(QThread):
    """Runs the full PDF → Audiobook pipeline in a background thread."""

    def __init__(
        self, doc: PDFDocument, voice: VoiceInfo,
        speed: float, pitch: float,
        output_format: str, title: str,
        parent=None,
    ):
        super().__init__(parent)
        self.doc = doc
        self.voice = voice
        self.speed = speed
        self.pitch = pitch
        self.output_format = output_format
        self.title = title
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            from audio.audio_generator import AudioGenerator
            from audio.audio_merger import AudioMerger
            import tempfile

            gen = AudioGenerator(
                voice=self.voice,
                speed=self.speed,
                pitch=self.pitch,
            )

            total_chunks_done = [0]
            merge_stage_size = 20  # pseudo-steps for merge phase

            def on_progress(done, total, msg):
                if self._cancelled:
                    gen.cancel()
                    return
                # TTS phase = 0..80% of progress bar
                pct = int(done / max(total, 1) * 80)
                self.signals.progress.emit(pct, 100, msg)
                total_chunks_done[0] = done

            gen.on_progress = on_progress

            result = gen.generate(self.doc.full_text)

            if self._cancelled:
                self.signals.error.emit("Conversion cancelled.")
                return
            if not result.success:
                self.signals.error.emit(result.error or "Unknown TTS error")
                return

            self.signals.progress.emit(82, 100, "Merging audio segments…")

            merger = AudioMerger(output_format=self.output_format)

            # Final output path
            out_dir = Path(__file__).parent.parent / "output" / "audiobooks"
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_title = "".join(
                c if c.isalnum() or c in " _-" else "_"
                for c in self.title
            ).strip()[:60] or "audiobook"
            out_path = str(out_dir / f"{safe_title}.{self.output_format}")

            def merge_progress(done, total):
                pct = 82 + int(done / max(total, 1) * 16)
                self.signals.progress.emit(pct, 100, f"Merging {done}/{total}…")

            merger.merge(result.wav_chunks, out_path, progress_callback=merge_progress)

            # Cleanup temp WAV chunks
            for wav in result.wav_chunks:
                try:
                    os.remove(wav)
                except OSError:
                    pass

            self.signals.progress.emit(100, 100, "Done!")
            self.signals.finished.emit(out_path)

        except Exception as exc:
            self.signals.error.emit(str(exc))


# --------------------------------------------------------------------------- #
# Main Window
# --------------------------------------------------------------------------- #
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF Audiobook Converter")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)
        self.setAcceptDrops(True)

        self._doc: PDFDocument | None = None
        self._voices: list[VoiceInfo] = []
        self._worker: ConversionWorker | None = None
        self._lib = AudiobookManager()
        self._vm = VoiceManager()

        self.setStyleSheet(STYLE)
        self._build_ui()
        self._load_voices()
        self._refresh_library()

    # ================================================================== #
    # UI Construction
    # ================================================================== #
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setSpacing(0)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # ── Top bar ────────────────────────────────────────────────────
        root_layout.addWidget(self._make_topbar())

        # ── Content splitter ──────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setContentsMargins(16, 12, 16, 16)
        splitter.addWidget(self._make_left_panel())
        splitter.addWidget(self._make_right_panel())
        splitter.setSizes([460, 620])
        root_layout.addWidget(splitter)

    def _make_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(56)
        bar.setStyleSheet("""
            QWidget {
                background: #090b10;
                border-bottom: 1px solid #1a1d2b;
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)

        # App name
        name = QLabel("📚  PDF  <span style='color:#f0722e;'>Audiobook</span>  Converter")
        name.setStyleSheet("font-size:17px; font-weight:700; color:#e8eaf0; border:none; background:transparent;")
        name.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(name)
        lay.addStretch()

        status = QLabel("Offline · All processing is local")
        status.setStyleSheet("font-size:11px; color:#3a3f56; border:none; background:transparent;")
        lay.addWidget(status)
        return bar

    # ──────────────────────────────────────────────────────────────────
    # Left Panel
    # ──────────────────────────────────────────────────────────────────
    def _make_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 4, 8, 0)

        # ── PDF Upload ─────────────────────────────────────────────────
        pdf_group = QGroupBox("PDF Document")
        pg_lay = QVBoxLayout(pdf_group)
        pg_lay.setSpacing(8)

        self._upload_btn = QPushButton("⬆   Drop a PDF here or click to browse")
        self._upload_btn.setObjectName("uploadBtn")
        self._upload_btn.clicked.connect(self._browse_pdf)
        pg_lay.addWidget(self._upload_btn)

        # PDF info grid
        self._pdf_info = QWidget()
        self._pdf_info.setVisible(False)
        info_grid = QGridLayout(self._pdf_info)
        info_grid.setSpacing(6)
        info_grid.setContentsMargins(0, 4, 0, 0)

        def _info_row(row, label, attr):
            lbl = QLabel(label)
            lbl.setObjectName("fieldLabel")
            val = QLabel("—")
            val.setObjectName("valueLabel")
            info_grid.addWidget(lbl, row, 0)
            info_grid.addWidget(val, row, 1)
            setattr(self, attr, val)

        _info_row(0, "File:", "_pdf_name_lbl")
        _info_row(1, "Pages:", "_pdf_pages_lbl")
        _info_row(2, "Size:", "_pdf_size_lbl")
        _info_row(3, "Words:", "_pdf_words_lbl")

        pg_lay.addWidget(self._pdf_info)
        layout.addWidget(pdf_group)

        # ── Voice Settings ─────────────────────────────────────────────
        voice_group = QGroupBox("Voice Settings")
        vg_lay = QVBoxLayout(voice_group)
        vg_lay.setSpacing(10)

        # Voice selector
        v_row1 = QHBoxLayout()
        vl1 = QLabel("Voice:")
        vl1.setObjectName("fieldLabel")
        vl1.setFixedWidth(52)
        self._voice_combo = QComboBox()
        self._voice_combo.setPlaceholderText("Scanning for voices…")
        v_row1.addWidget(vl1)
        v_row1.addWidget(self._voice_combo)
        vg_lay.addLayout(v_row1)

        # Engine + Language info
        v_row2 = QHBoxLayout()
        self._engine_lbl = QLabel("Engine: —")
        self._engine_lbl.setObjectName("subLabel")
        self._lang_lbl = QLabel("Lang: —")
        self._lang_lbl.setObjectName("subLabel")
        v_row2.addWidget(self._engine_lbl)
        v_row2.addStretch()
        v_row2.addWidget(self._lang_lbl)
        vg_lay.addLayout(v_row2)

        # Speed
        spd_row = QHBoxLayout()
        sl = QLabel("Speed:")
        sl.setObjectName("fieldLabel")
        sl.setFixedWidth(52)
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setRange(50, 200)
        self._speed_slider.setValue(100)
        self._speed_lbl = QLabel("1.0×")
        self._speed_lbl.setObjectName("valueLabel")
        self._speed_lbl.setFixedWidth(36)
        self._speed_slider.valueChanged.connect(
            lambda v: self._speed_lbl.setText(f"{v/100:.1f}×")
        )
        spd_row.addWidget(sl)
        spd_row.addWidget(self._speed_slider)
        spd_row.addWidget(self._speed_lbl)
        vg_lay.addLayout(spd_row)

        # Pitch
        pitch_row = QHBoxLayout()
        pl = QLabel("Pitch:")
        pl.setObjectName("fieldLabel")
        pl.setFixedWidth(52)
        self._pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self._pitch_slider.setRange(50, 200)
        self._pitch_slider.setValue(100)
        self._pitch_lbl = QLabel("1.0×")
        self._pitch_lbl.setObjectName("valueLabel")
        self._pitch_lbl.setFixedWidth(36)
        self._pitch_slider.valueChanged.connect(
            lambda v: self._pitch_lbl.setText(f"{v/100:.1f}×")
        )
        pitch_row.addWidget(pl)
        pitch_row.addWidget(self._pitch_slider)
        pitch_row.addWidget(self._pitch_lbl)
        vg_lay.addLayout(pitch_row)

        # Format
        fmt_row = QHBoxLayout()
        fl = QLabel("Format:")
        fl.setObjectName("fieldLabel")
        fl.setFixedWidth(52)
        self._format_combo = QComboBox()
        self._format_combo.addItems(["MP3", "WAV", "M4A"])
        fmt_row.addWidget(fl)
        fmt_row.addWidget(self._format_combo)
        vg_lay.addLayout(fmt_row)

        # Preview button
        self._preview_btn = QPushButton("🔊  Preview Voice")
        self._preview_btn.clicked.connect(self._preview_voice)
        vg_lay.addWidget(self._preview_btn)

        self._voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        layout.addWidget(voice_group)

        layout.addStretch()
        return panel

    # ──────────────────────────────────────────────────────────────────
    # Right Panel
    # ──────────────────────────────────────────────────────────────────
    def _make_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setSpacing(12)
        layout.setContentsMargins(8, 4, 0, 0)

        # ── Title + Convert button ─────────────────────────────────────
        conv_group = QGroupBox("Convert")
        cg_lay = QVBoxLayout(conv_group)
        cg_lay.setSpacing(10)

        title_row = QHBoxLayout()
        tl = QLabel("Title:")
        tl.setObjectName("fieldLabel")
        tl.setFixedWidth(40)
        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Audiobook title (auto-filled from PDF name)")
        title_row.addWidget(tl)
        title_row.addWidget(self._title_edit)
        cg_lay.addLayout(title_row)

        self._convert_btn = QPushButton("▶  Convert to Audiobook")
        self._convert_btn.setObjectName("convertBtn")
        self._convert_btn.clicked.connect(self._start_conversion)
        self._convert_btn.setEnabled(False)
        cg_lay.addWidget(self._convert_btn)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFormat("%p%")
        cg_lay.addWidget(self._progress_bar)

        self._status_lbl = QLabel("Load a PDF to get started.")
        self._status_lbl.setObjectName("statusLabel")
        self._status_lbl.setStyleSheet("color: #5c6280; font-size: 12px;")
        cg_lay.addWidget(self._status_lbl)

        # Cancel button (hidden by default)
        self._cancel_btn = QPushButton("✕  Cancel")
        self._cancel_btn.setVisible(False)
        self._cancel_btn.clicked.connect(self._cancel_conversion)
        cg_lay.addWidget(self._cancel_btn)

        layout.addWidget(conv_group)

        # ── Built-in Player ────────────────────────────────────────────
        player_group = QGroupBox("Player")
        pg_lay = QVBoxLayout(player_group)
        self._player = AudiobookPlayer()
        pg_lay.addWidget(self._player)
        layout.addWidget(player_group)

        # ── Library ────────────────────────────────────────────────────
        lib_group = QGroupBox("Audiobook Library")
        lg_lay = QVBoxLayout(lib_group)
        lg_lay.setSpacing(8)

        self._lib_list = QListWidget()
        self._lib_list.setMinimumHeight(180)
        self._lib_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._lib_list.itemDoubleClicked.connect(self._play_selected)
        lg_lay.addWidget(self._lib_list)

        lib_btn_row = QHBoxLayout()
        self._play_lib_btn = QPushButton("▶ Play")
        self._delete_lib_btn = QPushButton("🗑 Delete")
        self._export_lib_btn = QPushButton("📤 Export")
        for btn in (self._play_lib_btn, self._delete_lib_btn, self._export_lib_btn):
            lib_btn_row.addWidget(btn)
        self._play_lib_btn.clicked.connect(self._play_selected)
        self._delete_lib_btn.clicked.connect(self._delete_selected)
        self._export_lib_btn.clicked.connect(self._export_selected)
        lg_lay.addLayout(lib_btn_row)

        layout.addWidget(lib_group)
        return panel

    # ================================================================== #
    # Voice Loading
    # ================================================================== #
    def _load_voices(self):
        voices = self._vm.scan()
        self._voices = voices
        self._voice_combo.clear()
        if voices:
            for v in voices:
                label = f"{v.name}  [{v.engine.upper()}]"
                self._voice_combo.addItem(label, userData=v)
            self._on_voice_changed(0)
        else:
            self._voice_combo.addItem("No voices found – see README")
            self._set_status("⚠ No TTS voices found. Install Piper TTS or eSpeak.", error=True)

    def _on_voice_changed(self, idx: int):
        voice = self._voice_combo.itemData(idx)
        if isinstance(voice, VoiceInfo):
            self._engine_lbl.setText(f"Engine: {voice.engine.upper()}")
            self._lang_lbl.setText(f"Lang: {voice.language}")

    # ================================================================== #
    # PDF Loading
    # ================================================================== #
    def _browse_pdf(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open PDF", "", "PDF Files (*.pdf);;All Files (*)"
        )
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        self._set_status("Reading PDF…")
        reader = PDFReader(ocr_fallback=True)
        try:
            doc = reader.load(path)
            self._doc = doc
            self._upload_btn.setText(f"📄  {doc.file_name}")
            self._pdf_name_lbl.setText(doc.file_name)
            self._pdf_pages_lbl.setText(str(doc.page_count))
            self._pdf_size_lbl.setText(f"{doc.file_size_kb:.1f} KB")
            total_words = sum(p.word_count for p in doc.pages)
            self._pdf_words_lbl.setText(f"{total_words:,}")
            self._pdf_info.setVisible(True)
            # Auto-fill title
            stem = Path(path).stem
            self._title_edit.setText(stem)
            self._convert_btn.setEnabled(bool(self._voices))
            self._set_status(
                f"✓ Loaded {doc.page_count} pages · {total_words:,} words"
                + (" (OCR used)" if doc.has_ocr_pages else ""),
                success=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "PDF Error", str(exc))
            self._set_status(f"Error: {exc}", error=True)

    # ================================================================== #
    # Drag and Drop
    # ================================================================== #
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(".pdf") for u in urls):
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                self._load_pdf(path)
                break

    # ================================================================== #
    # Voice Preview
    # ================================================================== #
    def _preview_voice(self):
        voice = self._voice_combo.currentData()
        if not isinstance(voice, VoiceInfo):
            return
        self._set_status("Generating voice preview…")
        try:
            engine = TTSEngine(voice)
            wav = engine.preview("Hello! This is a preview of the selected voice. I hope you enjoy listening.")
            self._player.load(wav, "Voice Preview")
            self._set_status("Preview ready – press Play in the player.", success=True)
        except Exception as exc:
            QMessageBox.warning(self, "Preview Error", str(exc))
            self._set_status(f"Preview error: {exc}", error=True)

    # ================================================================== #
    # Conversion
    # ================================================================== #
    def _start_conversion(self):
        if not self._doc:
            QMessageBox.warning(self, "No PDF", "Please load a PDF first.")
            return
        voice = self._voice_combo.currentData()
        if not isinstance(voice, VoiceInfo):
            QMessageBox.warning(self, "No Voice", "Please select a TTS voice.")
            return

        title = self._title_edit.text().strip() or self._doc.file_name
        speed = self._speed_slider.value() / 100.0
        pitch = self._pitch_slider.value() / 100.0
        fmt = self._format_combo.currentText().lower()

        self._convert_btn.setEnabled(False)
        self._cancel_btn.setVisible(True)
        self._progress_bar.setValue(0)

        self._worker = ConversionWorker(
            doc=self._doc,
            voice=voice,
            speed=speed,
            pitch=pitch,
            output_format=fmt,
            title=title,
        )
        self._worker.signals.progress.connect(self._on_progress)
        self._worker.signals.finished.connect(self._on_finished)
        self._worker.signals.error.connect(self._on_error)
        self._worker.start()
        self._set_status("Starting conversion…")

    def _cancel_conversion(self):
        if self._worker:
            self._worker.cancel()
        self._cancel_btn.setVisible(False)
        self._convert_btn.setEnabled(True)
        self._set_status("Cancelling…")

    def _on_progress(self, done: int, total: int, msg: str):
        self._progress_bar.setValue(done)
        self._set_status(msg)

    def _on_finished(self, output_path: str):
        self._cancel_btn.setVisible(False)
        self._convert_btn.setEnabled(True)
        self._progress_bar.setValue(100)

        # Estimate duration from file
        duration_s = 0.0
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_file(output_path)
            duration_s = len(seg) / 1000
        except Exception:
            pass

        voice = self._voice_combo.currentData()
        voice_id = voice.id if isinstance(voice, VoiceInfo) else ""
        voice_name = voice.name if isinstance(voice, VoiceInfo) else ""
        title = self._title_edit.text().strip() or "Untitled"
        fmt = output_path.rsplit(".", 1)[-1]

        entry = self._lib.add(
            title=title,
            pdf_name=self._doc.file_name if self._doc else "",
            audio_file=output_path,
            voice_id=voice_id,
            voice_name=voice_name,
            duration_s=duration_s,
            page_count=self._doc.page_count if self._doc else 0,
            output_format=fmt,
            move_file=False,
        )

        self._refresh_library()
        self._set_status(f"✓ Audiobook saved: {os.path.basename(output_path)}", success=True)

        # Auto-load in player
        self._player.load(output_path, title)

        QMessageBox.information(
            self, "Conversion Complete",
            f"Audiobook created successfully!\n\n"
            f"Title: {title}\n"
            f"Format: {fmt.upper()}\n"
            f"File: {output_path}"
        )

    def _on_error(self, msg: str):
        self._cancel_btn.setVisible(False)
        self._convert_btn.setEnabled(True)
        self._progress_bar.setValue(0)
        self._set_status(f"Error: {msg}", error=True)
        QMessageBox.critical(self, "Conversion Error", msg)

    # ================================================================== #
    # Library
    # ================================================================== #
    def _refresh_library(self):
        self._lib_list.clear()
        for entry in self._lib.list_all():
            label = (
                f"📖 {entry.title}\n"
                f"   {entry.pdf_name}  ·  {entry.duration_str}  ·  {entry.size_str}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry.id)
            if not entry.file_exists:
                item.setForeground(QColor("#3a3f56"))
            self._lib_list.addItem(item)

    def _selected_entry_id(self) -> str | None:
        item = self._lib_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def _play_selected(self, *_):
        eid = self._selected_entry_id()
        if not eid:
            return
        entry = self._lib.get(eid)
        if not entry or not entry.file_exists:
            QMessageBox.warning(self, "File Missing", "The audio file could not be found.")
            return
        self._player.load(entry.audio_file, entry.title)

    def _delete_selected(self):
        eid = self._selected_entry_id()
        if not eid:
            return
        entry = self._lib.get(eid)
        if not entry:
            return
        reply = QMessageBox.question(
            self, "Delete Audiobook",
            f"Delete '{entry.title}'?\nThis will also remove the audio file.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._lib.delete(eid, delete_file=True)
            self._refresh_library()

    def _export_selected(self):
        eid = self._selected_entry_id()
        if not eid:
            return
        entry = self._lib.get(eid)
        if not entry or not entry.file_exists:
            QMessageBox.warning(self, "File Missing", "No audio file found.")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Audiobook", entry.title + "." + entry.format,
            f"Audio Files (*.{entry.format});;All Files (*)"
        )
        if dest:
            try:
                self._lib.export_copy(eid, dest)
                QMessageBox.information(self, "Exported", f"Saved to:\n{dest}")
            except Exception as exc:
                QMessageBox.critical(self, "Export Error", str(exc))

    # ================================================================== #
    # Status helper
    # ================================================================== #
    def _set_status(self, msg: str, error: bool = False, success: bool = False):
        color = "#e05030" if error else ("#4caf7d" if success else "#5c6280")
        self._status_lbl.setStyleSheet(f"font-size:12px; color:{color};")
        self._status_lbl.setText(msg)

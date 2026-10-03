# 📚 PDF Audiobook Converter

> **100% offline** · PDF → Audiobook · PyQt6 desktop app

Convert any PDF document into a high-quality audiobook using local
text-to-speech models — no internet connection, no cloud API, no data leaving
your machine.

---

## ✨ Features

| Feature | Details |
|---|---|
| PDF Upload | Browse or drag-and-drop, multi-page support |
| Text Extraction | PyMuPDF with Tesseract OCR fallback for scanned pages |
| Offline TTS | Piper TTS (recommended), Coqui TTS, eSpeak NG |
| Voice Selection | Speed, pitch, language controls + live preview |
| Audiobook Output | MP3, WAV, M4A |
| Built-in Player | Play, pause, seek, skip ±30s, speed control |
| Local Library | Metadata database, export, delete |
| Fully Offline | Zero network calls — all models stored locally |

---

## 🗂 Project Structure

```
pdf_audiobook_converter/
├── main.py                     ← Application entry point
│
├── gui/
│   ├── interface.py            ← Main window (PyQt6)
│   └── player.py               ← Built-in audio player widget
│
├── pdf_processing/
│   ├── pdf_reader.py           ← PDF loading + text extraction
│   └── ocr_engine.py           ← Tesseract OCR wrapper
│
├── tts/
│   ├── voice_manager.py        ← Voice discovery across all engines
│   └── tts_engine.py           ← TTS synthesis (Piper / Coqui / eSpeak)
│
├── audio/
│   ├── audio_generator.py      ← Text chunking + TTS orchestration
│   └── audio_merger.py         ← WAV merging + MP3/M4A export
│
├── library/
│   └── audiobook_manager.py    ← Local audiobook database (JSON)
│
├── models/
│   └── voices/
│       └── piper/              ← Place .onnx + .onnx.json models here
│
├── output/
│   ├── library.json            ← Auto-generated metadata DB
│   └── audiobooks/             ← Generated audiobook files
│
└── requirements.txt
```

---

## ⚡ Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Install system dependencies

**Ubuntu / Debian**
```bash
sudo apt update
sudo apt install tesseract-ocr ffmpeg
```

**macOS**
```bash
brew install tesseract ffmpeg
```

**Windows**
- Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
- FFmpeg: https://ffmpeg.org/download.html (add to PATH)

### 3. Install a TTS engine (pick one)

#### Option A — Piper TTS (Recommended: fast + high quality)

1. Download the `piper` binary for your platform:
   https://github.com/rhasspy/piper/releases

2. Add it to your PATH (or place next to `main.py`).

3. Download voice models from:
   https://huggingface.co/rhasspy/piper-voices/tree/main

   Example (US English, medium quality):
   ```
   models/voices/piper/en_US-lessac-medium.onnx
   models/voices/piper/en_US-lessac-medium.onnx.json
   ```

#### Option B — eSpeak NG (Always-available lightweight fallback)

```bash
# Ubuntu/Debian
sudo apt install espeak-ng

# macOS
brew install espeak

# Windows: https://github.com/espeak-ng/espeak-ng/releases
```

#### Option C — Coqui TTS (Pure Python, heavier)

```bash
pip install TTS
```
Models download on first use and are cached locally.

---

### 4. Run the application

```bash
python main.py
```

---

## 🎯 Usage Guide

1. **Load a PDF** — Click the upload area or drag a PDF file onto the window.
2. **Choose a voice** — Select from the Voice Settings panel. Use the preview
   button to hear it before converting.
3. **Adjust settings** — Set speed, pitch, and output format.
4. **Convert** — Click the big orange "Convert to Audiobook" button.
5. **Listen** — Use the built-in player, or find the file in `output/audiobooks/`.
6. **Library** — All generated audiobooks are stored in the Library panel.
   Double-click to play, or use Export to save elsewhere.

---

## 🔧 Configuration

### Adding Piper voices

Voice models live in `models/voices/piper/`. Download `.onnx` + `.onnx.json`
pairs from https://huggingface.co/rhasspy/piper-voices and place them in that
folder. The app auto-discovers them on startup.

### Supported Piper voice languages

| Code | Language |
|------|----------|
| en_US | English (US) |
| en_GB | English (UK) |
| de_DE | German |
| fr_FR | French |
| es_ES | Spanish |
| it_IT | Italian |
| … | Many more at HuggingFace |

---

## 🛠 Troubleshooting

| Problem | Fix |
|---|---|
| "No voices found" | Install Piper binary + models, or install eSpeak |
| OCR not working | `sudo apt install tesseract-ocr` + `pip install pytesseract pillow` |
| MP3 export fails | Install FFmpeg and ensure it's on PATH |
| Piper not found | Download piper binary and add to system PATH |
| App won't start | `pip install PyQt6 PyMuPDF pydub` |

---

## 📦 Tech Stack

| Layer | Library |
|---|---|
| GUI | PyQt6 |
| PDF reading | PyMuPDF (fitz) |
| OCR | Tesseract + pytesseract |
| TTS | Piper TTS / Coqui TTS / eSpeak NG |
| Audio merging | pydub + FFmpeg |
| Playback | Qt Multimedia (built into PyQt6) |
| Storage | JSON flat-file library |

---

## 📄 License

MIT License — free to use, modify, and distribute.

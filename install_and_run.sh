#!/usr/bin/env bash
# install_and_run.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-shot setup script for the PDF Audiobook Converter.
# Works on Ubuntu/Debian. Adapt paths for macOS / Windows.
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════════════════"
echo "  PDF Audiobook Converter – Setup"
echo "═══════════════════════════════════════════════════════"

# ── 1. System packages ────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
    echo "[1/4] Installing system packages via apt…"
    sudo apt-get update -q
    sudo apt-get install -y -q tesseract-ocr ffmpeg espeak-ng python3-pip python3-venv
elif command -v brew &>/dev/null; then
    echo "[1/4] Installing system packages via Homebrew…"
    brew install tesseract ffmpeg espeak
else
    echo "[1/4] ⚠  Could not detect package manager."
    echo "     Install manually: tesseract-ocr, ffmpeg, espeak-ng"
fi

# ── 2. Python virtual environment ─────────────────────────────────────────────
echo "[2/4] Creating Python virtual environment…"
python3 -m venv .venv
source .venv/bin/activate

# ── 3. Python dependencies ────────────────────────────────────────────────────
echo "[3/4] Installing Python packages…"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── 4. Piper TTS binary (optional) ───────────────────────────────────────────
echo "[4/4] Checking for Piper TTS binary…"
if command -v piper &>/dev/null; then
    echo "      ✓ piper found: $(which piper)"
else
    echo "      ⚠  piper not found on PATH."
    echo "      Download from: https://github.com/rhasspy/piper/releases"
    echo "      Then place it on your PATH or in this directory."
    echo "      eSpeak NG will be used as fallback."
fi

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  Setup complete! Launching application…"
echo "═══════════════════════════════════════════════════════"
echo ""
python main.py

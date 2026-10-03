@echo off
:: install_and_run.bat
:: ─────────────────────────────────────────────────────────────────────────────
:: One-shot setup for Windows. Run as a normal user (no admin needed for pip).
:: ─────────────────────────────────────────────────────────────────────────────

setlocal
cd /d "%~dp0"

echo ═══════════════════════════════════════════════════════
echo   PDF Audiobook Converter - Windows Setup
echo ═══════════════════════════════════════════════════════

:: ── 1. Check Python ───────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause & exit /b 1
)

:: ── 2. Virtual environment ────────────────────────────────────────────────────
echo [1/3] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

:: ── 3. Install packages ───────────────────────────────────────────────────────
echo [2/3] Installing Python packages...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

:: ── 4. Reminders ─────────────────────────────────────────────────────────────
echo [3/3] Manual steps required:
echo.
echo   Tesseract OCR (for scanned PDFs):
echo     https://github.com/UB-Mannheim/tesseract/wiki
echo.
echo   FFmpeg (for MP3/M4A output):
echo     https://ffmpeg.org/download.html
echo     Add ffmpeg\bin to your system PATH.
echo.
echo   Piper TTS binary (recommended voice engine):
echo     https://github.com/rhasspy/piper/releases
echo     Add piper.exe folder to your system PATH.
echo.
echo ═══════════════════════════════════════════════════════
echo   Launching application...
echo ═══════════════════════════════════════════════════════
python main.py

pause

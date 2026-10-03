"""
tts/tts_engine.py
==================
Offline Text-to-Speech synthesis.

Supports three backends (auto-selected based on VoiceInfo.engine):
  1. Piper TTS  – subprocess call to `piper` binary
  2. Coqui TTS  – Python API via TTS library
  3. eSpeak NG  – subprocess fallback

All backends output WAV files. Caller can then convert to MP3/M4A
via audio/audio_generator.py.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional, Callable

from tts.voice_manager import VoiceInfo


# --------------------------------------------------------------------------- #
# Base class
# --------------------------------------------------------------------------- #
class TTSBackend:
    def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        raise NotImplementedError

    def is_available(self) -> bool:
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Piper TTS Backend
# --------------------------------------------------------------------------- #
class PiperBackend(TTSBackend):
    """
    Uses the `piper` command-line binary.
    https://github.com/rhasspy/piper

    Install:
      Download piper binary from GitHub releases and put it on PATH.
      Model files go into models/voices/piper/
    """

    PIPER_BIN = "piper"  # or absolute path

    def __init__(self, voice: VoiceInfo):
        self.voice = voice

    def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        if not self.voice.model_path:
            raise ValueError("Piper voice has no model_path")

        cmd = [
            self.PIPER_BIN,
            "--model", self.voice.model_path,
            "--output_file", output_path,
        ]
        if self.voice.config_path:
            cmd += ["--config", self.voice.config_path]
        if speed != 1.0:
            # Piper uses length_scale: smaller = faster
            length_scale = round(1.0 / speed, 3)
            cmd += ["--length_scale", str(length_scale)]
        if pitch != 1.0:
            cmd += ["--noise_scale", "0.667", "--noise_w", str(pitch)]

        proc = subprocess.run(
            cmd,
            input=text.encode("utf8"),
            capture_output=True,
            #text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Piper error: {proc.stderr.strip()}")
        return output_path

    def is_available(self) -> bool:
        try:
            subprocess.run([self.PIPER_BIN, "--help"],
                           capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# --------------------------------------------------------------------------- #
# Coqui TTS Backend
# --------------------------------------------------------------------------- #
class CoquiBackend(TTSBackend):
    """Uses the Coqui TTS Python library."""

    def __init__(self, voice: VoiceInfo):
        self.voice = voice
        self._tts = None  # lazy init

    def _get_tts(self):
        if self._tts is None:
            from TTS.api import TTS as CoquiTTS  # type: ignore
            self._tts = CoquiTTS(model_name=self.voice.name, progress_bar=False)
        return self._tts

    def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        tts = self._get_tts()
        tts.tts_to_file(text=text, file_path=output_path, speed=speed)
        return output_path

    def is_available(self) -> bool:
        try:
            import TTS  # noqa
            return True
        except ImportError:
            return False


# --------------------------------------------------------------------------- #
# eSpeak NG Backend
# --------------------------------------------------------------------------- #
class ESpeakBackend(TTSBackend):
    """eSpeak NG subprocess fallback."""

    def __init__(self, voice: VoiceInfo):
        self.voice = voice
        # Extract language code from voice id: "espeak:{lang}:{name}"
        parts = voice.id.split(":")
        self.lang = parts[1] if len(parts) > 1 else "en"
        self.voice_name = parts[2] if len(parts) > 2 else self.lang

    def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        # eSpeak speed is words-per-minute; default 175
        wpm = int(175 * speed)
        pitch_val = int(50 * pitch)  # 0-99, default 50

        cmd = [
            "espeak-ng",
            "-v", self.voice_name,
            "-s", str(wpm),
            "-p", str(min(99, max(0, pitch_val))),
            "-w", output_path,
        ]
        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
            #text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"eSpeak error: {proc.stderr.strip()}")
        return output_path

    def is_available(self) -> bool:
        try:
            subprocess.run(["espeak-ng", "--version"],
                           capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# --------------------------------------------------------------------------- #
# Main TTS Engine
# --------------------------------------------------------------------------- #
class TTSEngine:
    """
    High-level TTS engine.  Selects the right backend based on VoiceInfo.

    Usage
    -----
    engine = TTSEngine(voice)
    wav_path = engine.synthesize_chunk("Hello world", "/tmp/chunk_001.wav")
    """

    def __init__(self, voice: VoiceInfo):
        self.voice = voice
        self.backend = self._create_backend(voice)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def synthesize_chunk(
        self,
        text: str,
        output_path: str,
        speed: float = 1.0,
        pitch: float = 1.0,
    ) -> str:
        """Synthesise text → WAV file at output_path. Returns the path."""
        if not text.strip():
            # Return a short silent WAV for empty chunks
            return self._write_silence(output_path)
        text = self._sanitize(text)
        return self.backend.synthesize(text, output_path, speed=speed, pitch=pitch)

    def preview(self, sample_text: str = "This is a preview of the selected voice.") -> str:
        """Synthesise a short preview and return the WAV path."""
        tmp = tempfile.mktemp(suffix=".wav", prefix="preview_")
        return self.synthesize_chunk(sample_text, tmp)

    def is_ready(self) -> bool:
        return self.backend.is_available()

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #
    @staticmethod
    def _create_backend(voice: VoiceInfo) -> TTSBackend:
        if voice.engine == "piper":
            return PiperBackend(voice)
        if voice.engine == "coqui":
            return CoquiBackend(voice)
        if voice.engine == "espeak":
            return ESpeakBackend(voice)
        raise ValueError(f"Unknown TTS engine: {voice.engine}")

    # @staticmethod
    # def _sanitize(text: str) -> str:
    #     """Remove characters TTS engines dislike."""
    #     # Remove excessive whitespace
    #     import re
    #     text = re.sub(r"[ \t]+", " ", text)
    #     text = re.sub(r"\n{3,}", "\n\n", text)
    #     # Strip URLs
    #     text = re.sub(r"https?://\S+", "", text)
    #     # Strip markdown-style headers
    #     text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    #     return text.strip()
    @staticmethod
    def _sanitize(text: str) -> str:
        """Remove characters TTS engines dislike."""
        import re
        text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
        text = re.sub(r"[\t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        text = text.encode("utf-8", "ignore").decode("utf-8")
        return text.strip()
    
    @staticmethod
    def _write_silence(output_path: str, duration_ms: int = 500) -> str:
        """Write a minimal silent WAV file."""
        import struct, wave
        n_frames = int(22050 * duration_ms / 1000)
        with wave.open(output_path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(struct.pack("<" + "h" * n_frames, *([0] * n_frames)))
        return output_path

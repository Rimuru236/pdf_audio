"""
audio/audio_generator.py
=========================
Orchestrates the full PDF → Audiobook conversion pipeline:

  1. Split full text into manageable chunks
  2. Synthesise each chunk via TTSEngine → WAV
  3. Track progress via callback
  4. Hand chunks to AudioMerger

Designed to run in a background thread. All heavy work is done here;
the GUI simply connects to progress/finished signals.
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import List, Optional, Callable

from tts.tts_engine import TTSEngine
from tts.voice_manager import VoiceInfo


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
DEFAULT_CHUNK_SIZE = 1500   # characters per chunk
MAX_CHUNK_SIZE = 3000
TEMP_DIR_PREFIX = "pdfaudio_"


# --------------------------------------------------------------------------- #
# Data class
# --------------------------------------------------------------------------- #
class GenerationResult:
    def __init__(self):
        self.success: bool = False
        self.wav_chunks: List[str] = []
        self.error: Optional[str] = None
        self.total_chars: int = 0
        self.duration_s: float = 0.0


# --------------------------------------------------------------------------- #
# Audio Generator
# --------------------------------------------------------------------------- #
class AudioGenerator:
    """
    Converts a block of text into a series of WAV audio chunks.

    Parameters
    ----------
    voice       : VoiceInfo – the selected TTS voice
    speed       : float     – narration speed multiplier (0.5–2.0)
    pitch       : float     – pitch multiplier (0.5–2.0)
    chunk_size  : int       – target characters per chunk
    temp_dir    : str       – directory for temporary WAV files

    Callbacks
    ---------
    on_progress(done, total, message)   – called after each chunk
    on_finished(result: GenerationResult)
    on_error(message: str)
    """

    def __init__(
        self,
        voice: VoiceInfo,
        speed: float = 1.0,
        pitch: float = 1.0,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        temp_dir: Optional[str] = None,
    ):
        self.voice = voice
        self.speed = speed
        self.pitch = pitch
        self.chunk_size = min(chunk_size, MAX_CHUNK_SIZE)
        self.temp_dir = temp_dir or _make_temp_dir()
        self._engine = TTSEngine(voice)
        self._cancel_flag = threading.Event()

        # Callbacks
        self.on_progress: Optional[Callable[[int, int, str], None]] = None
        self.on_finished: Optional[Callable[[GenerationResult], None]] = None
        self.on_error: Optional[Callable[[str], None]] = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def generate(self, text: str) -> GenerationResult:
        """
        Synchronous conversion. Returns GenerationResult.
        Call from a background thread to avoid blocking the GUI.
        """
        result = GenerationResult()
        t0 = time.time()
        self._cancel_flag.clear()
        result.total_chars = len(text)

        chunks = self._split_text(text)
        total = len(chunks)
        wav_files: List[str] = []

        for idx, chunk in enumerate(chunks):
            if self._cancel_flag.is_set():
                result.error = "Cancelled by user"
                return result

            out_path = os.path.join(
                self.temp_dir, f"chunk_{idx:04d}.wav"
            )
            try:
                self._engine.synthesize_chunk(
                    chunk, out_path,
                    speed=self.speed,
                    pitch=self.pitch,
                )
                wav_files.append(out_path)
                if self.on_progress:
                    pct_done = idx + 1
                    self.on_progress(
                        pct_done, total,
                        f"Synthesising chunk {pct_done}/{total}…"
                    )
            except Exception as exc:
                err_msg = f"TTS error on chunk {idx + 1}: {exc}"
                result.error = err_msg
                if self.on_error:
                    self.on_error(err_msg)
                return result

        result.wav_chunks = wav_files
        result.success = True
        result.duration_s = time.time() - t0

        if self.on_finished:
            self.on_finished(result)
        return result

    def generate_async(self, text: str) -> threading.Thread:
        """Launch generate() in a daemon thread and return it."""
        t = threading.Thread(target=self.generate, args=(text,), daemon=True)
        t.start()
        return t

    def cancel(self):
        """Signal the generator to stop after the current chunk."""
        self._cancel_flag.set()

    # ------------------------------------------------------------------ #
    # Text splitting
    # ------------------------------------------------------------------ #
    def _split_text(self, text: str) -> List[str]:
        """
        Split text into sentence-aware chunks.
        Tries to break at sentence boundaries first, then at word boundaries.
        """
        # Normalise line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Split into paragraphs first
        paragraphs = re.split(r"\n{2,}", text)
        chunks: List[str] = []
        current = ""

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If the paragraph itself is too long, split by sentences
            if len(para) > self.chunk_size:
                sentences = _split_sentences(para)
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= self.chunk_size:
                        current = (current + " " + sent).strip()
                    else:
                        if current:
                            chunks.append(current)
                        # Handle very long single sentence
                        if len(sent) > self.chunk_size:
                            for sub in _split_by_words(sent, self.chunk_size):
                                chunks.append(sub)
                            current = ""
                        else:
                            current = sent
            else:
                if len(current) + len(para) + 2 <= self.chunk_size:
                    current = (current + "\n\n" + para).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = para

        if current:
            chunks.append(current)

        return [c for c in chunks if c.strip()]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _split_sentences(text: str) -> List[str]:
    """Naive sentence splitter (no NLTK required)."""
    # Split on '. ', '! ', '? ' followed by uppercase or end of string
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'])', text)
    return [p.strip() for p in parts if p.strip()]


def _split_by_words(text: str, max_chars: int) -> List[str]:
    """Last-resort split: break by words."""
    words = text.split()
    chunks, current = [], ""
    for word in words:
        if len(current) + len(word) + 1 <= max_chars:
            current = (current + " " + word).strip()
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks


def _make_temp_dir() -> str:
    import tempfile
    path = tempfile.mkdtemp(prefix=TEMP_DIR_PREFIX)
    return path

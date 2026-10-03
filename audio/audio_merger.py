"""
audio/audio_merger.py
======================
Merges a list of WAV chunk files into a single output file.

Supported output formats: WAV, MP3, M4A
Uses pydub for merging + format conversion.

Install:
  pip install pydub
  sudo apt install ffmpeg   (or brew install ffmpeg on macOS)
"""

from __future__ import annotations

import os
import shutil
import tempfile
import wave
from pathlib import Path
from typing import List, Optional, Callable

try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False


# --------------------------------------------------------------------------- #
# AudioMerger
# --------------------------------------------------------------------------- #
class AudioMerger:
    """
    Merges WAV chunks produced by AudioGenerator into a single audiobook file.

    Parameters
    ----------
    output_format : str   – "mp3" | "wav" | "m4a"
    bitrate       : str   – MP3 bitrate, e.g. "128k", "192k"
    silence_ms    : int   – milliseconds of silence between chunks
    """

    SUPPORTED_FORMATS = {"mp3", "wav", "m4a", "ogg"}

    def __init__(
        self,
        output_format: str = "mp3",
        bitrate: str = "128k",
        silence_ms: int = 400,
    ):
        fmt = output_format.lower().lstrip(".")
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported format '{fmt}'. "
                f"Choose from: {', '.join(self.SUPPORTED_FORMATS)}"
            )
        self.output_format = fmt
        self.bitrate = bitrate
        self.silence_ms = silence_ms

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def merge(
        self,
        wav_files: List[str],
        output_path: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """
        Merge wav_files into output_path.

        Parameters
        ----------
        wav_files        : list of paths to WAV chunks (in order)
        output_path      : desired output file path
        progress_callback: callable(done, total) for progress reporting

        Returns
        -------
        str – path to the merged file
        """
        if not wav_files:
            raise ValueError("No WAV files provided for merging")

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        if PYDUB_AVAILABLE:
            return self._merge_pydub(wav_files, output_path, progress_callback)
        else:
            # Pure-Python WAV-only fallback
            if self.output_format != "wav":
                raise RuntimeError(
                    "pydub is required for MP3/M4A output.\n"
                    "  pip install pydub\n"
                    "  sudo apt install ffmpeg"
                )
            return self._merge_wave_module(wav_files, output_path, progress_callback)

    def estimate_duration(self, wav_files: List[str]) -> float:
        """Estimate total duration in seconds from a list of WAV files."""
        total = 0.0
        for p in wav_files:
            try:
                with wave.open(p, "r") as wf:
                    total += wf.getnframes() / wf.getframerate()
            except Exception:
                pass
        # Add silence gaps
        total += (len(wav_files) - 1) * self.silence_ms / 1000
        return total

    # ------------------------------------------------------------------ #
    # Private – pydub implementation
    # ------------------------------------------------------------------ #
    def _merge_pydub(
        self,
        wav_files: List[str],
        output_path: str,
        progress_callback,
    ) -> str:
        silence = AudioSegment.silent(duration=self.silence_ms)
        combined: Optional[AudioSegment] = None
        total = len(wav_files)

        for idx, wav_path in enumerate(wav_files):
            try:
                segment = AudioSegment.from_wav(wav_path)
            except Exception as exc:
                print(f"[AudioMerger] Skipping corrupt chunk {wav_path}: {exc}")
                continue

            if combined is None:
                combined = segment
            else:
                combined = combined + silence + segment

            if progress_callback:
                progress_callback(idx + 1, total)

        if combined is None:
            raise RuntimeError("All audio chunks were unreadable")

        export_kwargs = {}
        if self.output_format == "mp3":
            export_kwargs["bitrate"] = self.bitrate
        elif self.output_format == "m4a":
            export_kwargs["codec"] = "aac"

        combined.export(output_path, format=self.output_format, **export_kwargs)
        return output_path

    # ------------------------------------------------------------------ #
    # Private – stdlib WAV-only fallback
    # ------------------------------------------------------------------ #
    def _merge_wave_module(
        self,
        wav_files: List[str],
        output_path: str,
        progress_callback,
    ) -> str:
        """Merge WAV files using Python's built-in wave module."""
        # Read params from first file
        with wave.open(wav_files[0], "r") as first:
            params = first.getparams()
            n_channels = params.nchannels
            sampwidth = params.sampwidth
            framerate = params.framerate

        # Silence frames
        silence_frames = int(framerate * self.silence_ms / 1000)
        silence_data = b"\x00" * silence_frames * n_channels * sampwidth

        total = len(wav_files)
        with wave.open(output_path, "w") as out_wav:
            out_wav.setparams(params)
            for idx, wav_path in enumerate(wav_files):
                try:
                    with wave.open(wav_path, "r") as wf:
                        out_wav.writeframes(wf.readframes(wf.getnframes()))
                except Exception as exc:
                    print(f"[AudioMerger] Skipping {wav_path}: {exc}")
                    continue
                if idx < total - 1:
                    out_wav.writeframes(silence_data)
                if progress_callback:
                    progress_callback(idx + 1, total)

        return output_path

"""
tts/voice_manager.py
=====================
Discovers and manages offline TTS voices across multiple engines:
  - Piper TTS  (recommended – fast, high quality)
  - Coqui TTS
  - eSpeak NG  (always-available fallback)

Each voice is represented by a VoiceInfo dataclass.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Project root / models directory
MODELS_DIR = Path(__file__).parent.parent / "models" / "voices"


# --------------------------------------------------------------------------- #
# Data Classes
# --------------------------------------------------------------------------- #
@dataclass
class VoiceInfo:
    id: str                       # Unique identifier used internally
    name: str                     # Human-readable name, e.g. "en_US-lessac-medium"
    language: str                 # BCP-47 tag, e.g. "en-US"
    engine: str                   # "piper" | "coqui" | "espeak"
    model_path: Optional[str] = None   # Absolute path to model file (if applicable)
    config_path: Optional[str] = None  # Piper: path to .onnx.json config
    quality: str = "medium"       # low / medium / high
    gender: str = "neutral"       # male / female / neutral
    description: str = ""

    def is_available(self) -> bool:
        if self.engine == "espeak":
            return _espeak_available()
        if self.model_path:
            return os.path.isfile(self.model_path)
        return False


# --------------------------------------------------------------------------- #
# Voice Manager
# --------------------------------------------------------------------------- #
class VoiceManager:
    """
    Scans for available offline TTS voices and presents a unified list.

    Usage
    -----
    vm = VoiceManager()
    voices = vm.get_all_voices()
    default = vm.get_default_voice()
    """

    def __init__(self):
        self._voices: List[VoiceInfo] = []
        self._scanned = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def scan(self) -> List[VoiceInfo]:
        """Scan all engines and return available voices."""
        self._voices = []
        self._voices.extend(self._scan_piper())
        self._voices.extend(self._scan_coqui())
        self._voices.extend(self._scan_espeak())
        self._scanned = True
        return self._voices

    def get_all_voices(self) -> List[VoiceInfo]:
        if not self._scanned:
            self.scan()
        return self._voices

    def get_voices_for_language(self, lang_prefix: str) -> List[VoiceInfo]:
        """Filter voices by language prefix, e.g. 'en'."""
        return [v for v in self.get_all_voices()
                if v.language.lower().startswith(lang_prefix.lower())]

    def get_default_voice(self) -> Optional[VoiceInfo]:
        """Return the first available English voice, or any voice."""
        voices = self.get_all_voices()
        eng = [v for v in voices if v.language.startswith("en")]
        return eng[0] if eng else (voices[0] if voices else None)

    def get_voice_by_id(self, voice_id: str) -> Optional[VoiceInfo]:
        return next((v for v in self.get_all_voices() if v.id == voice_id), None)

    # ------------------------------------------------------------------ #
    # Piper TTS scanner
    # ------------------------------------------------------------------ #
    def _scan_piper(self) -> List[VoiceInfo]:
        voices = []
        piper_dir = MODELS_DIR / "piper"
        if not piper_dir.is_dir():
            return voices

        # Piper models: <name>.onnx + <name>.onnx.json
        for onnx_file in piper_dir.glob("**/*.onnx"):
            config_file = Path(str(onnx_file) + ".json")
            if not config_file.is_file():
                continue
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                lang = cfg.get("language", {})
                lang_code = lang.get("code", "en-US").replace("_", "-")
                name = onnx_file.stem  # e.g. "en_US-lessac-medium"
                quality = name.split("-")[-1] if "-" in name else "medium"
                voices.append(VoiceInfo(
                    id=f"piper:{name}",
                    name=name,
                    language=lang_code,
                    engine="piper",
                    model_path=str(onnx_file),
                    config_path=str(config_file),
                    quality=quality,
                    description=f"Piper TTS – {lang_code}",
                ))
            except Exception as exc:
                print(f"[VoiceManager] Could not load Piper model {onnx_file}: {exc}")

        # Also check voices.json manifest if present
        manifest = piper_dir / "voices.json"
        if manifest.is_file():
            try:
                with open(manifest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for key, info in data.items():
                    vid = f"piper:{key}"
                    if any(v.id == vid for v in voices):
                        continue  # already discovered
                    files = info.get("files", {})
                    onnx_rel = next((k for k in files if k.endswith(".onnx")), None)
                    json_rel = next((k for k in files if k.endswith(".onnx.json")), None)
                    if onnx_rel:
                        onnx_path = piper_dir / onnx_rel
                        json_path = piper_dir / json_rel if json_rel else None
                        lang_tag = info.get("language", "en-US")
                        voices.append(VoiceInfo(
                            id=vid,
                            name=key,
                            language=lang_tag,
                            engine="piper",
                            model_path=str(onnx_path),
                            config_path=str(json_path) if json_path else None,
                            quality=info.get("quality", "medium"),
                            gender=info.get("gender", "neutral"),
                            description=info.get("description", ""),
                        ))
            except Exception as exc:
                print(f"[VoiceManager] voices.json parse error: {exc}")

        return voices

    # ------------------------------------------------------------------ #
    # Coqui TTS scanner
    # ------------------------------------------------------------------ #
    def _scan_coqui(self) -> List[VoiceInfo]:
        voices = []
        try:
            from TTS.api import TTS as CoquiTTS
            model_list = CoquiTTS.list_models()
            for model_name in model_list:
                if "tts_models" not in model_name:
                    continue
                parts = model_name.split("/")
                lang = parts[1] if len(parts) > 1 else "en"
                voices.append(VoiceInfo(
                    id=f"coqui:{model_name}",
                    name=model_name,
                    language=lang,
                    engine="coqui",
                    description=f"Coqui TTS – {model_name}",
                ))
        except ImportError:
            pass
        except Exception as exc:
            print(f"[VoiceManager] Coqui scan error: {exc}")
        return voices

    # ------------------------------------------------------------------ #
    # eSpeak NG scanner
    # ------------------------------------------------------------------ #
    def _scan_espeak(self) -> List[VoiceInfo]:
        voices = []
        if not _espeak_available():
            return voices
        try:
            result = subprocess.run(
                ["espeak-ng", "--voices"],
                capture_output=True, text=True, timeout=10
            )
            for line in result.stdout.splitlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) < 4:
                    continue
                lang = parts[1]
                name = parts[3]
                voices.append(VoiceInfo(
                    id=f"espeak:{lang}:{name}",
                    name=f"{name} ({lang})",
                    language=lang,
                    engine="espeak",
                    quality="low",
                    description="eSpeak NG – lightweight fallback",
                ))
        except Exception as exc:
            print(f"[VoiceManager] eSpeak scan error: {exc}")
        return voices


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _espeak_available() -> bool:
    try:
        subprocess.run(["espeak-ng", "--version"],
                       capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

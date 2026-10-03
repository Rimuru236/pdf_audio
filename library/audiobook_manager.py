"""
library/audiobook_manager.py
=============================
Manages the local audiobook library.

  - Stores metadata in a JSON database (library.json)
  - Audiobook audio files live in output/audiobooks/
  - Supports CRUD: add, list, get, delete, export

Metadata schema
---------------
{
  "id": "uuid4",
  "title": "My Book",
  "pdf_name": "mybook.pdf",
  "audio_file": "/abs/path/to/audio.mp3",
  "format": "mp3",
  "duration_s": 3600.0,
  "voice_id": "piper:en_US-lessac-medium",
  "voice_name": "en_US-lessac-medium",
  "date_created": "2024-01-15T10:30:00",
  "file_size_kb": 45000.0,
  "page_count": 120
}
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# Output directory for audiobook files
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "audiobooks"
DB_PATH = Path(__file__).parent.parent / "output" / "library.json"


# --------------------------------------------------------------------------- #
# Audiobook Entry
# --------------------------------------------------------------------------- #
class AudiobookEntry:
    def __init__(self, data: Dict[str, Any]):
        self.id: str = data.get("id", str(uuid.uuid4()))
        self.title: str = data.get("title", "Untitled")
        self.pdf_name: str = data.get("pdf_name", "")
        self.audio_file: str = data.get("audio_file", "")
        self.format: str = data.get("format", "mp3")
        self.duration_s: float = data.get("duration_s", 0.0)
        self.voice_id: str = data.get("voice_id", "")
        self.voice_name: str = data.get("voice_name", "")
        self.date_created: str = data.get("date_created", _now_iso())
        self.file_size_kb: float = data.get("file_size_kb", 0.0)
        self.page_count: int = data.get("page_count", 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "pdf_name": self.pdf_name,
            "audio_file": self.audio_file,
            "format": self.format,
            "duration_s": self.duration_s,
            "voice_id": self.voice_id,
            "voice_name": self.voice_name,
            "date_created": self.date_created,
            "file_size_kb": self.file_size_kb,
            "page_count": self.page_count,
        }

    @property
    def duration_str(self) -> str:
        s = int(self.duration_s)
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        if h:
            return f"{h}h {m:02d}m {sec:02d}s"
        return f"{m}m {sec:02d}s"

    @property
    def size_str(self) -> str:
        kb = self.file_size_kb
        if kb > 1024:
            return f"{kb / 1024:.1f} MB"
        return f"{kb:.0f} KB"

    @property
    def file_exists(self) -> bool:
        return bool(self.audio_file) and os.path.isfile(self.audio_file)


# --------------------------------------------------------------------------- #
# Audiobook Manager
# --------------------------------------------------------------------------- #
class AudiobookManager:
    """
    CRUD manager for the local audiobook library.

    Usage
    -----
    mgr = AudiobookManager()
    entry = mgr.add(title="My Book", pdf_name="book.pdf", audio_file="/tmp/book.mp3", ...)
    books = mgr.list_all()
    mgr.delete(entry.id)
    """

    def __init__(self, output_dir: Optional[str] = None, db_path: Optional[str] = None):
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.db_path = Path(db_path) if db_path else DB_PATH
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: Dict[str, Dict] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def add(
        self,
        title: str,
        pdf_name: str,
        audio_file: str,
        voice_id: str = "",
        voice_name: str = "",
        duration_s: float = 0.0,
        page_count: int = 0,
        output_format: str = "mp3",
        move_file: bool = True,
    ) -> AudiobookEntry:
        """
        Register a new audiobook.

        If move_file=True the audio file is moved into the library's output_dir.
        """
        entry_id = str(uuid.uuid4())
        dest_filename = f"{entry_id}.{output_format}"
        dest_path = str(self.output_dir / dest_filename)

        if move_file and os.path.isfile(audio_file) and audio_file != dest_path:
            shutil.move(audio_file, dest_path)
            final_path = dest_path
        else:
            final_path = audio_file

        # File size
        try:
            size_kb = os.path.getsize(final_path) / 1024
        except OSError:
            size_kb = 0.0

        entry = AudiobookEntry({
            "id": entry_id,
            "title": title,
            "pdf_name": pdf_name,
            "audio_file": final_path,
            "format": output_format,
            "duration_s": duration_s,
            "voice_id": voice_id,
            "voice_name": voice_name,
            "date_created": _now_iso(),
            "file_size_kb": size_kb,
            "page_count": page_count,
        })
        self._db[entry_id] = entry.to_dict()
        self._save()
        return entry

    def list_all(self) -> List[AudiobookEntry]:
        """Return all library entries, sorted newest first."""
        entries = [AudiobookEntry(d) for d in self._db.values()]
        entries.sort(key=lambda e: e.date_created, reverse=True)
        return entries

    def get(self, entry_id: str) -> Optional[AudiobookEntry]:
        data = self._db.get(entry_id)
        return AudiobookEntry(data) if data else None

    def delete(self, entry_id: str, delete_file: bool = True) -> bool:
        """
        Remove entry from library. If delete_file=True also deletes the audio.
        Returns True if removed, False if not found.
        """
        data = self._db.pop(entry_id, None)
        if data is None:
            return False
        if delete_file:
            audio = data.get("audio_file", "")
            if audio and os.path.isfile(audio):
                try:
                    os.remove(audio)
                except OSError:
                    pass
        self._save()
        return True

    def update_duration(self, entry_id: str, duration_s: float):
        if entry_id in self._db:
            self._db[entry_id]["duration_s"] = duration_s
            self._save()

    def export_copy(self, entry_id: str, destination: str) -> str:
        """Copy the audio file to destination. Returns final path."""
        entry = self.get(entry_id)
        if not entry:
            raise KeyError(f"No entry with id={entry_id}")
        if not entry.file_exists:
            raise FileNotFoundError(f"Audio file missing: {entry.audio_file}")
        shutil.copy2(entry.audio_file, destination)
        return destination

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def _load(self):
        if self.db_path.is_file():
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self._db = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._db = {}
        else:
            self._db = {}

    def _save(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self._db, f, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

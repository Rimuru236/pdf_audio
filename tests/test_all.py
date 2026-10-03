"""
tests/test_all.py
==================
Unit + integration tests for the PDF Audiobook Converter.

Run:  python -m pytest tests/ -v
"""

import io
import json
import os
import struct
import tempfile
import wave
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

# ── make sure project root is on path ────────────────────────────────────────
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════════════ #
# Helpers
# ═══════════════════════════════════════════════════════════════════════════ #
def _make_wav(path: str, duration_s: float = 1.0, rate: int = 22050):
    """Write a minimal silent WAV to disk."""
    n = int(rate * duration_s)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(struct.pack("<" + "h" * n, *([0] * n)))


def _make_pdf_bytes() -> bytes:
    """Return the bytes of a trivially valid single-page PDF."""
    content = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    content += b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    content += b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
    content += b"/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n"
    content += b"4 0 obj<</Length 44>>stream\nBT /F1 12 Tf 100 700 Td (Hello PDF) Tj ET\nendstream\nendobj\n"
    content += b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
    xref_offset = len(content)
    content += b"xref\n0 6\n0000000000 65535 f \n"
    content += b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n"
    content += str(xref_offset).encode() + b"\n%%EOF\n"
    return content


# ═══════════════════════════════════════════════════════════════════════════ #
# PDF Reader Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestPDFReaderClean(unittest.TestCase):
    """Tests for PDFReader._clean_text (no PDF library needed)."""

    def setUp(self):
        from pdf_processing.pdf_reader import PDFReader
        self.reader = PDFReader.__new__(PDFReader)

    def test_ligature_replacement(self):
        from pdf_processing.pdf_reader import PDFReader
        text = "fi\ufb01nd the \ufb02ow"
        result = PDFReader._clean_text(text)
        self.assertIn("find", result)
        self.assertIn("flow", result)

    def test_removes_null_bytes(self):
        from pdf_processing.pdf_reader import PDFReader
        result = PDFReader._clean_text("hello\x00world")
        self.assertEqual(result, "hello world")

    def test_collapses_blank_lines(self):
        from pdf_processing.pdf_reader import PDFReader
        result = PDFReader._clean_text("a\n\n\n\n\nb")
        self.assertNotIn("\n\n\n", result)

    def test_empty_string(self):
        from pdf_processing.pdf_reader import PDFReader
        self.assertEqual(PDFReader._clean_text(""), "")

    def test_curly_quotes(self):
        from pdf_processing.pdf_reader import PDFReader
        result = PDFReader._clean_text("\u201chello\u201d")
        self.assertEqual(result, '"hello"')


class TestPDFReaderLoad(unittest.TestCase):
    """Test PDFReader.load() with a real minimal PDF (requires PyMuPDF)."""

    def test_load_missing_file(self):
        from pdf_processing.pdf_reader import PDFReader
        reader = PDFReader()
        with self.assertRaises(FileNotFoundError):
            reader.load("/nonexistent/path/file.pdf")

    @unittest.skipUnless(
        __import__("importlib").util.find_spec("fitz") is not None,
        "PyMuPDF not installed"
    )
    def test_load_minimal_pdf(self):
        from pdf_processing.pdf_reader import PDFReader
        pdf_bytes = _make_pdf_bytes()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        try:
            reader = PDFReader(ocr_fallback=False)
            doc = reader.load(tmp)
            self.assertEqual(doc.page_count, 1)
            self.assertIsInstance(doc.full_text, str)
            self.assertGreater(len(doc.file_name), 0)
        finally:
            os.unlink(tmp)


# ═══════════════════════════════════════════════════════════════════════════ #
# Audio Generator Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestTextSplitter(unittest.TestCase):
    """Test AudioGenerator's text chunking logic."""

    def _make_generator(self, chunk_size=500):
        from audio.audio_generator import AudioGenerator
        from tts.voice_manager import VoiceInfo
        voice = VoiceInfo(
            id="espeak:en:en", name="en", language="en",
            engine="espeak",
        )
        gen = AudioGenerator.__new__(AudioGenerator)
        gen.chunk_size = chunk_size
        gen.speed = 1.0
        gen.pitch = 1.0
        gen._cancel_flag = __import__("threading").Event()
        gen.on_progress = None
        gen.on_finished = None
        gen.on_error = None
        return gen

    def test_short_text_single_chunk(self):
        gen = self._make_generator(chunk_size=1000)
        chunks = gen._split_text("Hello world. This is a short paragraph.")
        self.assertEqual(len(chunks), 1)
        self.assertIn("Hello world", chunks[0])

    def test_long_text_multiple_chunks(self):
        gen = self._make_generator(chunk_size=100)
        long_text = "This is sentence number one. " * 30
        chunks = gen._split_text(long_text)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(len(c), 200)  # allow some overflow for sentence integrity

    def test_empty_text(self):
        gen = self._make_generator()
        chunks = gen._split_text("")
        self.assertEqual(chunks, [])

    def test_paragraph_preservation(self):
        gen = self._make_generator(chunk_size=2000)
        text = "First paragraph here.\n\nSecond paragraph here."
        chunks = gen._split_text(text)
        joined = " ".join(chunks)
        self.assertIn("First paragraph", joined)
        self.assertIn("Second paragraph", joined)

    def test_no_empty_chunks(self):
        gen = self._make_generator(chunk_size=200)
        text = "\n\n".join(["Sentence " + str(i) + "." for i in range(20)])
        chunks = gen._split_text(text)
        for c in chunks:
            self.assertTrue(c.strip(), "Empty chunk found")


class TestSentenceSplitter(unittest.TestCase):
    def test_basic_split(self):
        from audio.audio_generator import _split_sentences
        parts = _split_sentences("Hello world. How are you? I am fine!")
        self.assertGreaterEqual(len(parts), 1)

    def test_single_sentence(self):
        from audio.audio_generator import _split_sentences
        parts = _split_sentences("Just one sentence here")
        self.assertEqual(len(parts), 1)


# ═══════════════════════════════════════════════════════════════════════════ #
# Audio Merger Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestAudioMerger(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _wav(self, name, duration=0.5):
        path = os.path.join(self.tmp_dir, name)
        _make_wav(path, duration)
        return path

    def test_merge_wav_fallback(self):
        from audio.audio_merger import AudioMerger
        chunks = [self._wav(f"c{i}.wav") for i in range(3)]
        out = os.path.join(self.tmp_dir, "merged.wav")
        merger = AudioMerger(output_format="wav", silence_ms=100)
        result = merger.merge(chunks, out)
        self.assertTrue(os.path.isfile(result))
        self.assertGreater(os.path.getsize(result), 0)

    def test_merge_empty_raises(self):
        from audio.audio_merger import AudioMerger
        merger = AudioMerger(output_format="wav")
        with self.assertRaises(ValueError):
            merger.merge([], "/tmp/out.wav")

    def test_invalid_format_raises(self):
        from audio.audio_merger import AudioMerger
        with self.assertRaises(ValueError):
            AudioMerger(output_format="xyz")

    def test_estimate_duration(self):
        from audio.audio_merger import AudioMerger
        chunks = [self._wav(f"d{i}.wav", duration=1.0) for i in range(3)]
        merger = AudioMerger(silence_ms=0)
        dur = merger.estimate_duration(chunks)
        self.assertAlmostEqual(dur, 3.0, delta=0.2)

    def test_progress_callback_called(self):
        from audio.audio_merger import AudioMerger
        chunks = [self._wav(f"p{i}.wav") for i in range(3)]
        out = os.path.join(self.tmp_dir, "prog.wav")
        calls = []
        merger = AudioMerger(output_format="wav", silence_ms=0)
        merger.merge(chunks, out, progress_callback=lambda d, t: calls.append((d, t)))
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[-1], (3, 3))


# ═══════════════════════════════════════════════════════════════════════════ #
# Audiobook Manager Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestAudiobookManager(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.out_dir = os.path.join(self.tmp_dir, "audiobooks")
        self.db_path = os.path.join(self.tmp_dir, "library.json")
        # Create a fake audio file
        self.audio_file = os.path.join(self.tmp_dir, "test.wav")
        _make_wav(self.audio_file)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _mgr(self):
        from library.audiobook_manager import AudiobookManager
        return AudiobookManager(output_dir=self.out_dir, db_path=self.db_path)

    def test_add_and_list(self):
        mgr = self._mgr()
        entry = mgr.add(
            title="Test Book",
            pdf_name="test.pdf",
            audio_file=self.audio_file,
            output_format="wav",
            move_file=False,
        )
        self.assertEqual(entry.title, "Test Book")
        books = mgr.list_all()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0].id, entry.id)

    def test_get_by_id(self):
        mgr = self._mgr()
        entry = mgr.add("Book A", "a.pdf", self.audio_file, move_file=False, output_format="wav")
        found = mgr.get(entry.id)
        self.assertIsNotNone(found)
        self.assertEqual(found.title, "Book A")

    def test_get_nonexistent(self):
        mgr = self._mgr()
        self.assertIsNone(mgr.get("nonexistent-uuid"))

    def test_delete(self):
        mgr = self._mgr()
        entry = mgr.add("Del Book", "d.pdf", self.audio_file, move_file=False, output_format="wav")
        result = mgr.delete(entry.id, delete_file=False)
        self.assertTrue(result)
        self.assertEqual(len(mgr.list_all()), 0)

    def test_delete_nonexistent(self):
        mgr = self._mgr()
        self.assertFalse(mgr.delete("bad-id"))

    def test_persistence(self):
        """Data survives creating a new manager instance with the same db path."""
        mgr1 = self._mgr()
        mgr1.add("Persist Book", "p.pdf", self.audio_file, move_file=False, output_format="wav")
        mgr2 = self._mgr()
        books = mgr2.list_all()
        self.assertEqual(len(books), 1)
        self.assertEqual(books[0].title, "Persist Book")

    def test_duration_str(self):
        from library.audiobook_manager import AudiobookEntry
        e = AudiobookEntry({"id": "x", "title": "T", "duration_s": 3665})
        self.assertEqual(e.duration_str, "1h 01m 05s")

    def test_size_str_mb(self):
        from library.audiobook_manager import AudiobookEntry
        e = AudiobookEntry({"id": "x", "title": "T", "file_size_kb": 2048})
        self.assertIn("MB", e.size_str)

    def test_export_copy(self):
        mgr = self._mgr()
        entry = mgr.add("Export Book", "e.pdf", self.audio_file, move_file=False, output_format="wav")
        dest = os.path.join(self.tmp_dir, "exported.wav")
        mgr.export_copy(entry.id, dest)
        self.assertTrue(os.path.isfile(dest))

    def test_sorted_newest_first(self):
        import time
        mgr = self._mgr()
        mgr.add("Old", "o.pdf", self.audio_file, move_file=False, output_format="wav")
        time.sleep(0.01)
        mgr.add("New", "n.pdf", self.audio_file, move_file=False, output_format="wav")
        books = mgr.list_all()
        self.assertEqual(books[0].title, "New")


# ═══════════════════════════════════════════════════════════════════════════ #
# Voice Manager Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestVoiceInfo(unittest.TestCase):

    def test_espeak_voice_id_parsing(self):
        from tts.voice_manager import VoiceInfo
        v = VoiceInfo(id="espeak:en:en-us", name="en-us", language="en", engine="espeak")
        self.assertEqual(v.engine, "espeak")
        self.assertEqual(v.language, "en")

    def test_piper_voice_needs_model_path(self):
        from tts.voice_manager import VoiceInfo
        v = VoiceInfo(id="piper:en_US-lessac-medium", name="en_US-lessac-medium",
                      language="en-US", engine="piper")
        self.assertFalse(v.is_available())  # no model_path set

    def test_scan_returns_list(self):
        from tts.voice_manager import VoiceManager
        vm = VoiceManager()
        voices = vm.scan()
        self.assertIsInstance(voices, list)


# ═══════════════════════════════════════════════════════════════════════════ #
# TTS Engine Tests
# ═══════════════════════════════════════════════════════════════════════════ #
class TestTTSEngine(unittest.TestCase):

    def _espeak_voice(self):
        from tts.voice_manager import VoiceInfo
        return VoiceInfo(
            id="espeak:en:en",
            name="en",
            language="en",
            engine="espeak",
        )

    def test_sanitize_removes_urls(self):
        from tts.tts_engine import TTSEngine
        v = self._espeak_voice()
        engine = TTSEngine.__new__(TTSEngine)
        result = TTSEngine._sanitize("Visit https://example.com for info.")
        self.assertNotIn("https", result)

    def test_sanitize_strips_headers(self):
        from tts.tts_engine import TTSEngine
        result = TTSEngine._sanitize("## Introduction\nSome text here.")
        self.assertNotIn("##", result)

    def test_write_silence(self):
        from tts.tts_engine import TTSEngine
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            TTSEngine._write_silence(path, duration_ms=200)
            self.assertTrue(os.path.isfile(path))
            self.assertGreater(os.path.getsize(path), 0)
            with wave.open(path) as wf:
                self.assertEqual(wf.getnchannels(), 1)
        finally:
            os.unlink(path)

    @unittest.skipUnless(
        __import__("subprocess").run(
            ["espeak-ng", "--version"], capture_output=True
        ).returncode == 0,
        "eSpeak NG not installed"
    )
    def test_espeak_synthesis(self):
        from tts.tts_engine import TTSEngine
        voice = self._espeak_voice()
        engine = TTSEngine(voice)
        self.assertTrue(engine.is_ready())
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        try:
            result = engine.synthesize_chunk("Hello test.", out)
            self.assertTrue(os.path.isfile(result))
            self.assertGreater(os.path.getsize(result), 44)  # more than WAV header
        finally:
            if os.path.isfile(out):
                os.unlink(out)


# ═══════════════════════════════════════════════════════════════════════════ #
# Integration Test
# ═══════════════════════════════════════════════════════════════════════════ #
class TestFullPipelineIntegration(unittest.TestCase):
    """
    Lightweight end-to-end test using eSpeak if available.
    Skipped if no TTS engine is installed.
    """

    @unittest.skipUnless(
        __import__("subprocess").run(
            ["espeak-ng", "--version"], capture_output=True
        ).returncode == 0,
        "eSpeak NG not installed"
    )
    def test_text_to_wav_merge(self):
        from tts.voice_manager import VoiceInfo
        from audio.audio_generator import AudioGenerator
        from audio.audio_merger import AudioMerger

        voice = VoiceInfo(
            id="espeak:en:en", name="en", language="en", engine="espeak"
        )

        with tempfile.TemporaryDirectory() as tmp:
            gen = AudioGenerator(voice=voice, speed=1.0, pitch=1.0,
                                  chunk_size=200, temp_dir=tmp)
            result = gen.generate(
                "This is a short integration test. "
                "It checks that the audio generator produces output."
            )
            self.assertTrue(result.success, result.error)
            self.assertGreater(len(result.wav_chunks), 0)

            out = os.path.join(tmp, "integrated.wav")
            merger = AudioMerger(output_format="wav", silence_ms=100)
            merger.merge(result.wav_chunks, out)
            self.assertTrue(os.path.isfile(out))
            self.assertGreater(os.path.getsize(out), 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)

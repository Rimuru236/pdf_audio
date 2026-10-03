"""
pdf_processing/pdf_reader.py
============================
Handles PDF loading, metadata extraction, and text extraction.
Uses PyMuPDF (fitz) as the primary engine.
Falls back to pdfminer if PyMuPDF is unavailable.
Delegates to ocr_engine.py for image-only pages.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# --------------------------------------------------------------------------- #
# Optional imports – graceful degradation
# --------------------------------------------------------------------------- #
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract
    PDFMINER_AVAILABLE = True
except ImportError:
    PDFMINER_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Data Classes
# --------------------------------------------------------------------------- #
@dataclass
class PageResult:
    page_number: int          # 1-based
    text: str
    used_ocr: bool = False
    word_count: int = 0

    def __post_init__(self):
        self.word_count = len(self.text.split())


@dataclass
class PDFDocument:
    file_path: str
    file_name: str = ""
    file_size_kb: float = 0.0
    page_count: int = 0
    pages: List[PageResult] = field(default_factory=list)
    full_text: str = ""
    has_ocr_pages: bool = False

    def __post_init__(self):
        if not self.file_name:
            self.file_name = os.path.basename(self.file_path)
        if not self.file_size_kb:
            try:
                self.file_size_kb = os.path.getsize(self.file_path) / 1024
            except OSError:
                self.file_size_kb = 0.0


# --------------------------------------------------------------------------- #
# Main Reader Class
# --------------------------------------------------------------------------- #
class PDFReader:
    """
    High-level PDF reader.

    Usage
    -----
    reader = PDFReader()
    doc = reader.load(path_to_pdf, ocr_fallback=True)
    print(doc.full_text[:500])
    """

    # Minimum characters on a page before we consider it text-bearing
    TEXT_THRESHOLD = 30

    def __init__(self, ocr_fallback: bool = True):
        self.ocr_fallback = ocr_fallback
        self._ocr_engine = None  # lazy-load

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def load(self, file_path: str, progress_callback=None) -> PDFDocument:
        """
        Load and extract text from a PDF file.

        Parameters
        ----------
        file_path : str
            Absolute path to the PDF file.
        progress_callback : callable(page_index, total_pages), optional
            Called after each page is processed.

        Returns
        -------
        PDFDocument
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"PDF not found: {file_path}")

        doc = PDFDocument(file_path=file_path)

        if PYMUPDF_AVAILABLE:
            self._extract_with_pymupdf(doc, progress_callback)
        elif PDFMINER_AVAILABLE:
            self._extract_with_pdfminer(doc, progress_callback)
        else:
            raise RuntimeError(
                "No PDF library found. Install PyMuPDF: pip install pymupdf"
            )

        # Build full text
        doc.full_text = self._assemble_full_text(doc.pages)
        return doc

    def get_metadata(self, file_path: str) -> dict:
        """Return basic metadata without full text extraction."""
        meta = {
            "file_name": os.path.basename(file_path),
            "file_size_kb": 0.0,
            "page_count": 0,
        }
        try:
            meta["file_size_kb"] = os.path.getsize(file_path) / 1024
        except OSError:
            pass

        if PYMUPDF_AVAILABLE:
            try:
                with fitz.open(file_path) as pdf:
                    meta["page_count"] = len(pdf)
                    meta.update(pdf.metadata or {})
            except Exception:
                pass
        return meta

    # ------------------------------------------------------------------ #
    # Private – PyMuPDF extraction
    # ------------------------------------------------------------------ #
    def _extract_with_pymupdf(self, doc: PDFDocument, progress_callback):
        with fitz.open(doc.file_path) as pdf:
            doc.page_count = len(pdf)
            for i, page in enumerate(pdf):
                text = page.get_text("text")  # type: ignore[attr-defined]
                used_ocr = False

                if len(text.strip()) < self.TEXT_THRESHOLD and self.ocr_fallback:
                    text = self._ocr_page_pymupdf(page)
                    used_ocr = bool(text.strip())
                    if used_ocr:
                        doc.has_ocr_pages = True

                text = self._clean_text(text)
                doc.pages.append(
                    PageResult(page_number=i + 1, text=text, used_ocr=used_ocr)
                )
                if progress_callback:
                    progress_callback(i + 1, doc.page_count)

    def _ocr_page_pymupdf(self, page) -> str:
        """Render page to image and run OCR."""
        try:
            ocr = self._get_ocr_engine()
            pix = page.get_pixmap(dpi=200)  # type: ignore[attr-defined]
            img_bytes = pix.tobytes("png")
            return ocr.ocr_image_bytes(img_bytes)
        except Exception as exc:
            print(f"[PDFReader] OCR failed on page: {exc}")
            return ""

    # ------------------------------------------------------------------ #
    # Private – pdfminer fallback
    # ------------------------------------------------------------------ #
    def _extract_with_pdfminer(self, doc: PDFDocument, progress_callback):
        """Single-pass extraction via pdfminer (no per-page OCR support)."""
        try:
            raw = pdfminer_extract(doc.file_path)
            # pdfminer returns one big string; split naively by form-feed
            raw_pages = raw.split("\x0c")
            doc.page_count = len(raw_pages)
            for i, raw_text in enumerate(raw_pages):
                text = self._clean_text(raw_text)
                doc.pages.append(PageResult(page_number=i + 1, text=text))
                if progress_callback:
                    progress_callback(i + 1, doc.page_count)
        except Exception as exc:
            raise RuntimeError(f"pdfminer extraction failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Private – helpers
    # ------------------------------------------------------------------ #
    def _get_ocr_engine(self):
        if self._ocr_engine is None:
            from pdf_processing.ocr_engine import OCREngine
            self._ocr_engine = OCREngine()
        return self._ocr_engine

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalise whitespace, remove null bytes, fix common ligatures."""
        if not text:
            return ""
        # Remove null bytes and non-printable control chars (except newlines/tabs)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Common ligature replacements
        replacements = {
            "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi",
            "\ufb04": "ffl", "\u2019": "'", "\u2018": "'",
            "\u201c": '"', "\u201d": '"', "\u2013": "-", "\u2014": "--",
        }
        for lig, rep in replacements.items():
            text = text.replace(lig, rep)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse multiple spaces (but preserve single newlines)
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def _assemble_full_text(pages: List[PageResult]) -> str:
        parts = []
        for page in pages:
            if page.text.strip():
                parts.append(page.text)
        return "\n\n".join(parts)

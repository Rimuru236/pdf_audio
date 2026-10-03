"""
pdf_processing/ocr_engine.py
=============================
Offline OCR via Tesseract.  Works on both raw image files and in-memory
PNG/JPEG bytes (for PyMuPDF page renders).

Dependencies
------------
  pip install pytesseract pillow
  System: tesseract-ocr must be installed and on PATH
    - macOS:    brew install tesseract
    - Ubuntu:   sudo apt install tesseract-ocr
    - Windows:  https://github.com/UB-Mannheim/tesseract/wiki
"""

from __future__ import annotations

import io
import os
from typing import Optional

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


class OCREngine:
    """
    Thin wrapper around pytesseract for offline OCR.

    Parameters
    ----------
    lang : str
        Tesseract language code, e.g. "eng", "fra", "deu+eng".
    tesseract_cmd : str, optional
        Override path to the tesseract binary.
    """

    def __init__(self, lang: str = "eng", tesseract_cmd: Optional[str] = None):
        if not TESSERACT_AVAILABLE:
            raise RuntimeError(
                "OCR requires pytesseract and Pillow.\n"
                "  pip install pytesseract pillow\n"
                "  sudo apt install tesseract-ocr   (or brew / winget)"
            )
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        elif os.name == "nt":
            # Common Windows install location
            default_win = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.isfile(default_win):
                pytesseract.pytesseract.tesseract_cmd = default_win

        self.lang = lang
        self._verify_installation()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def ocr_image_file(self, image_path: str) -> str:
        """OCR a saved image file. Returns extracted text."""
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        img = Image.open(image_path)
        return self._run(img)

    def ocr_image_bytes(self, data: bytes, fmt: str = "PNG") -> str:
        """OCR raw image bytes (e.g. from PyMuPDF Pixmap.tobytes())."""
        img = Image.open(io.BytesIO(data))
        return self._run(img)

    def ocr_pil_image(self, img: "Image.Image") -> str:  # noqa: F821
        """OCR a PIL Image object directly."""
        return self._run(img)

    # ------------------------------------------------------------------ #
    # Private
    # ------------------------------------------------------------------ #
    def _run(self, img: "Image.Image") -> str:
        """Core OCR call with pre-processing."""
        img = self._preprocess(img)
        config = "--oem 3 --psm 3"  # LSTM engine, fully automatic segmentation
        text = pytesseract.image_to_string(img, lang=self.lang, config=config)
        return text.strip()

    @staticmethod
    def _preprocess(img: "Image.Image") -> "Image.Image":
        """
        Basic pre-processing to improve OCR accuracy:
        - Convert to greyscale
        - Upscale small images
        """
        img = img.convert("L")  # greyscale
        w, h = img.size
        if w < 1000:
            scale = 1000 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)  # type: ignore
        return img

    @staticmethod
    def _verify_installation():
        """Quick sanity-check that Tesseract binary is reachable."""
        try:
            pytesseract.get_tesseract_version()
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(
                "Tesseract binary not found. Install it:\n"
                "  Ubuntu/Debian: sudo apt install tesseract-ocr\n"
                "  macOS:         brew install tesseract\n"
                "  Windows:       https://github.com/UB-Mannheim/tesseract/wiki"
            ) from exc

    # ------------------------------------------------------------------ #
    # Utility
    # ------------------------------------------------------------------ #
    @staticmethod
    def available_languages() -> list[str]:
        """Return languages installed in Tesseract."""
        if not TESSERACT_AVAILABLE:
            return []
        try:
            return pytesseract.get_languages(config="")
        except Exception:
            return []

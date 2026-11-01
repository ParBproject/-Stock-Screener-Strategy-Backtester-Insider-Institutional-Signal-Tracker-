"""OCR backends.

``glyph`` reads the built-in 5x7 font and is what tests use.
``tesseract`` shells out to the Tesseract binary when it is installed.
``easyocr`` is optional and is never loaded unless selected, because the
package downloads weights.
``auto`` uses Tesseract when the binary is on PATH, otherwise the glyph reader.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from autoqc.vision.font import GLYPH_H, GLYPH_INDEX, GLYPH_W, PITCH

Box = tuple[int, int, int, int]


def binarize(crop: np.ndarray, polarity: str = "auto") -> np.ndarray:
    if crop.size == 0:
        return np.zeros((0, 0), dtype=bool)
    luminance = crop.astype(np.int16).mean(axis=2)
    mode = polarity
    if mode == "auto":
        mode = "dark_on_light" if float(np.median(luminance)) > 140 else "light_on_dark"
    if mode == "light_on_dark":
        return luminance >= 180
    return luminance <= 90


def _row_bits(row: np.ndarray) -> int:
    bits = 0
    for index, on in enumerate(row.tolist()):
        if on:
            bits |= 1 << (GLYPH_W - 1 - index)
    return bits


def _decode(band: np.ndarray, offset: int) -> tuple[str, int, bool]:
    width = band.shape[1]
    x = offset
    chars: list[str] = []
    matched = 0
    while x + GLYPH_W <= width:
        cell = band[:, x : x + GLYPH_W]
        if not cell.any():
            if not band[:, x:].any():
                break
            if chars:
                chars.append(" ")
            x += PITCH
            continue
        key = tuple(_row_bits(cell[row]) for row in range(GLYPH_H))
        char = GLYPH_INDEX.get(key)
        if char is None:
            return "", 0, False
        chars.append(char)
        matched += 1
        x += PITCH
    if matched == 0:
        return "", 0, False
    return "".join(chars), matched, True


def read_band(band: np.ndarray) -> tuple[str, int]:
    if band.shape[0] != GLYPH_H:
        return "", 0
    best_text = ""
    best_score = 0
    for offset in range(PITCH):
        text, score, ok = _decode(band, offset)
        if ok and score > best_score:
            best_text = text
            best_score = score
    return best_text, best_score


def read_binary(binary: np.ndarray) -> str:
    height = binary.shape[0] if binary.ndim == 2 else 0
    if height < GLYPH_H or binary.shape[1] < GLYPH_W:
        return ""
    best = ""
    best_score = 0
    for y in range(height - GLYPH_H + 1):
        text, score = read_band(binary[y : y + GLYPH_H])
        if score > best_score:
            best = text
            best_score = score
    return best


def _crop(image: np.ndarray, box: Box | None) -> np.ndarray:
    if box is None:
        return image
    x0, y0, x1, y1 = box
    height, width = image.shape[:2]
    x0 = max(0, min(width, x0))
    x1 = max(0, min(width, x1))
    y0 = max(0, min(height, y0))
    y1 = max(0, min(height, y1))
    if x1 <= x0 or y1 <= y0:
        return image[0:0, 0:0]
    return image[y0:y1, x0:x1]


class GlyphOcr:
    name = "glyph"

    def read(self, image: np.ndarray, box: Box | None = None, polarity: str = "auto") -> str:
        crop = _crop(image, box)
        if crop.size == 0:
            return ""
        return read_binary(binarize(crop, polarity)).strip()


class TesseractOcr:
    name = "tesseract"

    def read(self, image: np.ndarray, box: Box | None = None, polarity: str = "auto") -> str:
        del polarity
        if shutil.which("tesseract") is None:
            return ""
        crop = _crop(image, box)
        if crop.size == 0:
            return ""
        with tempfile.TemporaryDirectory(prefix="autoqc-ocr-") as tmp:
            path = Path(tmp) / "crop.png"
            Image.fromarray(np.ascontiguousarray(crop), mode="RGB").save(path)
            try:
                proc = subprocess.run(
                    ["tesseract", str(path), "stdout", "--psm", "6"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return ""
        if proc.returncode != 0:
            return ""
        return " ".join(proc.stdout.split())


class EasyOcrEngine:
    """Optional EasyOCR backend. Constructing the reader may download weights."""

    name = "easyocr"

    def __init__(self) -> None:
        self._reader = None

    def read(self, image: np.ndarray, box: Box | None = None, polarity: str = "auto") -> str:
        del polarity
        try:
            import easyocr
        except ImportError:
            return ""
        crop = _crop(image, box)
        if crop.size == 0:
            return ""
        try:
            if self._reader is None:
                self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            pieces = self._reader.readtext(np.ascontiguousarray(crop), detail=0)
        except Exception:
            return ""
        return " ".join(str(piece) for piece in pieces).strip()


class AutoOcr:
    """Tesseract when installed, otherwise the glyph reader. Never downloads weights."""

    name = "auto"

    def __init__(self) -> None:
        self.glyph = GlyphOcr()
        self.tesseract = TesseractOcr()

    def read(self, image: np.ndarray, box: Box | None = None, polarity: str = "auto") -> str:
        if shutil.which("tesseract") is not None:
            text = self.tesseract.read(image, box, polarity)
            if text:
                return text
        return self.glyph.read(image, box, polarity)


def build_ocr(engine: str):
    name = (engine or "auto").strip().lower()
    if name == "glyph":
        return GlyphOcr()
    if name == "tesseract":
        return TesseractOcr()
    if name == "easyocr":
        return EasyOcrEngine()
    return AutoOcr()


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def easyocr_available() -> bool:
    try:
        import easyocr  # noqa: F401
    except ImportError:
        return False
    return True

"""
tools/vision/ocr.py
~~~~~~~~~~~~~~~~~~~~~
Optical character recognition for keyframes / document pages, behind an
availability check so it is fully optional (degrade-not-fail).

Backend order (first available wins):
  1. ``pytesseract`` (Tesseract) — light, no GPU.
  2. ``easyocr`` — heavier, better on stylized text.
Both are imported lazily; if neither is installed :func:`ocr_image` returns ``[]``
and the ingestion ``ocr`` node simply produces no ``TextBlock`` nodes.

Each result is a dict ``{"text", "bbox", "confidence"}`` — ``bbox`` is
``[x, y, w, h]`` when the backend provides it, else ``None``.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _backend() -> Optional[str]:
    """Return the OCR backend name to use, or None if OCR is unavailable."""
    forced = os.getenv("OCR_BACKEND", "").strip().lower()
    if forced in ("tesseract", "easyocr", "none"):
        return None if forced == "none" else forced
    try:
        import pytesseract  # noqa: F401
        return "tesseract"
    except Exception:  # noqa: BLE001
        pass
    try:
        import easyocr  # noqa: F401
        return "easyocr"
    except Exception:  # noqa: BLE001
        pass
    return None


def ocr_available() -> bool:
    return _backend() is not None


@lru_cache(maxsize=1)
def _easyocr_reader():
    import easyocr

    langs = os.getenv("OCR_LANGS", "en").split(",")
    return easyocr.Reader([lang.strip() for lang in langs if lang.strip()], gpu=False)


def _min_conf() -> float:
    try:
        return float(os.getenv("OCR_MIN_CONFIDENCE", "0.3"))
    except ValueError:
        return 0.3


def ocr_image(image_path: str) -> List[Dict[str, Any]]:
    """Return detected text blocks for *image_path* (``[]`` if OCR unavailable)."""
    backend = _backend()
    if backend is None:
        return []
    try:
        if backend == "tesseract":
            return _ocr_tesseract(image_path)
        return _ocr_easyocr(image_path)
    except Exception as exc:  # noqa: BLE001 — never fail ingestion on OCR
        logger.info("OCR failed for %s (%s); skipping.", image_path, exc)
        return []


def _ocr_tesseract(image_path: str) -> List[Dict[str, Any]]:
    import pytesseract
    from PIL import Image

    data = pytesseract.image_to_data(
        Image.open(image_path), output_type=pytesseract.Output.DICT
    )
    blocks: List[Dict[str, Any]] = []
    n = len(data.get("text", []))
    for i in range(n):
        text = (data["text"][i] or "").strip()
        try:
            conf = float(data["conf"][i]) / 100.0
        except (ValueError, TypeError):
            conf = 0.0
        if text and conf >= _min_conf():
            blocks.append({
                "text": text,
                "bbox": [data["left"][i], data["top"][i], data["width"][i], data["height"][i]],
                "confidence": round(conf, 3),
            })
    return blocks


def _ocr_easyocr(image_path: str) -> List[Dict[str, Any]]:
    reader = _easyocr_reader()
    results = reader.readtext(image_path)
    blocks: List[Dict[str, Any]] = []
    for bbox, text, conf in results:
        text = (text or "").strip()
        if text and float(conf) >= _min_conf():
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            blocks.append({
                "text": text,
                "bbox": [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)],
                "confidence": round(float(conf), 3),
            })
    return blocks


__all__ = ["ocr_image", "ocr_available"]

"""Strict, local-only visual selectors built from OpenAdapt Flow primitives.

Bytes never leave the calling process. Coordinates returned here are relative
to the freshly captured, verified window, not the desktop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class VisualSelectorError(ValueError):
    """Insufficient or ambiguous evidence; no input should be delivered."""


@dataclass(frozen=True)
class VisualMatch:
    method: str
    point: tuple[int, int]
    region: tuple[int, int, int, int]
    confidence: float
    text: str | None = None


def checked_threshold(value: float) -> float:
    if not 0.8 <= value <= 1.0:
        raise VisualSelectorError("Visual confidence must be between 0.8 and 1.0")
    return value


def template_path(root: Path, name: str) -> Path:
    """Allow PNG templates only beneath an explicitly configured local root."""
    root = root.resolve(strict=True)
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root) or path.suffix.lower() != ".png":
        raise VisualSelectorError("Template must be a PNG inside the calibration root")
    if path.stat().st_size > 5_000_000:
        raise VisualSelectorError("Template exceeds the 5 MB limit")
    return path


def match_template(
    window_png: bytes, template_png: bytes, *, threshold: float = 0.95
) -> VisualMatch | None:
    """Reuse upstream matching, with strict uniqueness at calibrated 1:1 scale."""
    import cv2
    from openadapt_flow.vision.match import (
        _decode_gray,
        _peaks_above,
        find_template,
    )

    checked_threshold(threshold)
    template = _decode_gray(template_png)
    if min(template.shape) < 4 or float(template.std()) < 2.0:
        raise VisualSelectorError("Template has too little distinguishing structure")
    candidate = find_template(
        window_png, template_png, scales=(1.0,), threshold=threshold
    )
    if candidate is None:
        return None
    frame = _decode_gray(window_png)
    scores = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    height, width = template.shape
    peaks = _peaks_above(scores, threshold, width, height)
    if len(peaks) != 1:
        raise VisualSelectorError(
            "Template matches multiple locations; recalibrate a unique anchor"
        )
    return VisualMatch(
        method="template",
        point=candidate.point,
        region=candidate.region,
        confidence=candidate.confidence,
    )


def match_text(
    window_png: bytes, text: str, *, threshold: float = 0.95
) -> VisualMatch | None:
    """Read local RapidOCR results; require one exact normalized line."""
    from openadapt_flow.vision.ocr import normalize_text, ocr

    checked_threshold(threshold)
    if not text.strip():
        raise VisualSelectorError("OCR anchor text cannot be empty")
    lines = [
        line
        for line in ocr(window_png)
        if normalize_text(line.text) == normalize_text(text)
    ]
    if len(lines) > 1:
        raise VisualSelectorError("OCR text is ambiguous inside the verified window")
    if not lines or lines[0].confidence < threshold:
        return None
    line = lines[0]
    x, y, width, height = line.region
    return VisualMatch(
        "ocr",
        (x + width // 2, y + height // 2),
        line.region,
        line.confidence,
        line.text,
    )

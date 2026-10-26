"""Local image OCR. No document leaves the machine and no LLM is called."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 20_000_000


@dataclass(frozen=True)
class Token:
    text: str
    confidence: float
    bbox: tuple[float, float, float, float]

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


class OCREngine(Protocol):
    name: str

    def read(self, image: Image.Image) -> list[Token]: ...


def load_image(path: str | Path) -> tuple[bytes, Image.Image]:
    path = Path(path)
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Image exceeds 20 MiB.")
    try:
        with Image.open(BytesIO(raw)) as original:
            if original.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("Use a single PNG, JPEG, or WEBP image.")
            if original.width * original.height > MAX_PIXELS:
                raise ValueError("Image exceeds 20 million pixels.")
            if getattr(original, "n_frames", 1) != 1:
                raise ValueError("Use one document copy per image.")
            return raw, ImageOps.exif_transpose(original).convert("RGB")
    except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError("Image cannot be decoded safely.") from exc


class RapidOCREngine:
    name = "rapidocr-onnxruntime/1.4.4"

    def __init__(self) -> None:
        import onnxruntime
        onnxruntime.disable_telemetry_events()
        from rapidocr_onnxruntime import RapidOCR

        # Avoid multiplying CPU thread pools when LangGraph fans out documents.
        self._engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1)

    def read(self, image: Image.Image) -> list[Token]:
        # The OCR package accepts BGR numpy arrays.
        rows, _ = self._engine(np.asarray(image)[:, :, ::-1].copy())
        return [Token(text, float(score), (
            min(p[0] for p in quad), min(p[1] for p in quad),
            max(p[0] for p in quad), max(p[1] for p in quad),
        )) for quad, text, score in (rows or [])]

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from manim_cli.jsonio import write_json


Pixel = Tuple[int, int, int]


def analyze_pixels(width: int, height: int, pixels: Sequence[Pixel], background: Pixel = (30, 30, 30)) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    if width <= 0 or height <= 0 or not pixels:
        return [{"type": "visual_empty_frame", "reason": "no pixels"}]
    active = [
        (index % width, index // width)
        for index, pixel in enumerate(pixels)
        if color_distance(pixel, background) > 24
    ]
    active_ratio = len(active) / float(width * height)
    if active_ratio < 0.01:
        warnings.append({"type": "visual_empty_frame", "active_ratio": round(active_ratio, 4)})
        return warnings
    left = min(x for x, _ in active)
    right = max(x for x, _ in active)
    top = min(y for _, y in active)
    bottom = max(y for _, y in active)
    margin = min(width, height) * 0.03
    if left < margin or top < margin or width - right < margin or height - bottom < margin:
        warnings.append({"type": "visual_edge_pressure", "bbox": {"left": left, "top": top, "right": right, "bottom": bottom}})
    bbox_ratio = ((right - left + 1) * (bottom - top + 1)) / float(width * height)
    if bbox_ratio > 0.88:
        warnings.append({"type": "visual_overfull_frame", "bbox_ratio": round(bbox_ratio, 4)})
    active_set = set(active)
    active_pixels = [pixels[index] for index in range(len(pixels)) if (index % width, index // width) in active_set]
    if average_contrast(active_pixels, background) < 35:
        warnings.append({"type": "visual_low_contrast"})
    return warnings


def analyze_keyframe(frame_id: str, width: int, height: int, pixels: Sequence[Pixel], background: Pixel = (30, 30, 30)) -> Dict[str, Any]:
    return {
        "frame_id": frame_id,
        "width": width,
        "height": height,
        "pixel_hash": pixel_hash(pixels),
        "warnings": analyze_pixels(width, height, pixels, background=background),
    }


def pixel_hash(pixels: Sequence[Pixel]) -> str:
    digest = hashlib.sha256()
    for red, green, blue in pixels:
        digest.update(bytes((red & 0xFF, green & 0xFF, blue & 0xFF)))
    return digest.hexdigest()


def color_distance(left: Pixel, right: Pixel) -> float:
    return sum(abs(left[index] - right[index]) for index in range(3)) / 3.0


def average_contrast(pixels: Iterable[Pixel], background: Pixel) -> float:
    values = [color_distance(pixel, background) for pixel in pixels]
    return sum(values) / len(values) if values else 0.0


def write_feedback(out_dir: Path, warnings: List[Dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "latest.json", {"warnings": warnings})
    lines = ["# Render Feedback", ""]
    if warnings:
        lines.extend(["## Blocking", ""])
        lines.extend(f"- `{item.get('type')}`: {item}" for item in warnings)
    else:
        lines.extend(["No blocking visual QA findings."])
    (out_dir / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

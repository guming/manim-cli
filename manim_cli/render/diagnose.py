from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

from manim_cli.jsonio import Diagnostic, error_result, load_json, ok_result
from manim_cli.source_map import lookup_source_map


TRACE_RE = re.compile(r'File "([^"]+scene\.py)", line (\d+)')


def classify_output(stdout: str = "", stderr: str = "") -> str:
    text = f"{stdout}\n{stderr}"
    lowered = text.lower()
    if "latex error" in lowered or "latex" in lowered and "failed" in lowered:
        return "latex_error"
    missing_runtime_names = ("'latex'", '"latex"', "'dvisvgm'", '"dvisvgm"', "'ffmpeg'", '"ffmpeg"')
    if "modulenotfounderror" in lowered or any(name in lowered for name in missing_runtime_names):
        return "missing_dependency"
    if "syntaxerror" in lowered:
        return "python_syntax_error"
    return "manim_runtime_error"


def diagnose_payload(payload: Dict[str, Any], source_map_path: Optional[Path] = None) -> Diagnostic:
    stdout = payload.get("stdout", "")
    stderr = payload.get("stderr", "")
    error_type = payload.get("error_type") or classify_output(stdout, stderr)
    location: Dict[str, Any] = {}
    text = f"{stdout}\n{stderr}"
    match = TRACE_RE.search(text)
    if match:
        line_no = int(match.group(2))
        location["line_in_generated_code"] = line_no
        mapped = map_line(source_map_path, line_no) if source_map_path else None
        if mapped:
            location.update(mapped)
    suggestions = suggestions_for(error_type)
    return error_result("diagnose", error_type, payload.get("message", error_type), location=location, suggestions=suggestions)


def map_line(source_map_path: Optional[Path], line_no: int) -> Optional[Dict[str, Any]]:
    if not source_map_path or not source_map_path.exists():
        return None
    matches = lookup_source_map(source_map_path, line_no=line_no)
    if not matches:
        return None
    item = matches[0]
    mapped = {"path": item.get("json_path"), "source_map": str(source_map_path), "symbol": item.get("symbol")}
    for key in ("step_id", "step_index", "action_index", "object_ids", "narration_cue_id", "storyboard_event_id"):
        if key in item:
            mapped[key] = item[key]
    return mapped


def suggestions_for(error_type: str) -> list[str]:
    return {
        "latex_error": ["Simplify the Tex string.", "Check whether LaTeX is installed."],
        "missing_dependency": ["Install the missing runtime dependency.", "Check manim, LaTeX, ffmpeg, and rendering backend availability."],
        "python_syntax_error": ["Treat this as a compiler bug and inspect source map context."],
        "render_timeout": ["Lower render quality or simplify the scene."],
    }.get(error_type, ["Inspect the mapped DSL path and simplify the nearest scene artifact."])

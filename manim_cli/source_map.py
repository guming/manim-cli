from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from manim_cli.jsonio import load_json


def load_source_map(path: Path) -> Dict[str, Any]:
    return load_json(path)


def find_by_line(source_map: Dict[str, Any], line_no: int) -> Optional[Dict[str, Any]]:
    for item in source_map.get("mappings", []):
        start, end = item.get("python_lines", [None, None])
        if start is not None and start <= line_no <= end:
            return dict(item)
    return None


def find_by_dsl_path(source_map: Dict[str, Any], dsl_path: str) -> List[Dict[str, Any]]:
    return [dict(item) for item in source_map.get("mappings", []) if item.get("json_path") == dsl_path]


def find_by_object_id(source_map: Dict[str, Any], object_id: str) -> List[Dict[str, Any]]:
    return [dict(item) for item in source_map.get("mappings", []) if object_id in item.get("object_ids", [])]


def find_by_step_id(source_map: Dict[str, Any], step_id: str) -> List[Dict[str, Any]]:
    return [dict(item) for item in source_map.get("mappings", []) if item.get("step_id") == step_id]


def lookup_source_map(source_map_path: Path, *, line_no: int | None = None, dsl_path: str | None = None, object_id: str | None = None, step_id: str | None = None) -> List[Dict[str, Any]]:
    if not source_map_path.exists():
        return []
    source_map = load_source_map(source_map_path)
    if line_no is not None:
        match = find_by_line(source_map, line_no)
        return [] if match is None else [match]
    if dsl_path is not None:
        return find_by_dsl_path(source_map, dsl_path)
    if object_id is not None:
        return find_by_object_id(source_map, object_id)
    if step_id is not None:
        return find_by_step_id(source_map, step_id)
    return []

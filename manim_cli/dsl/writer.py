from __future__ import annotations

from typing import Any, Dict, List, Optional


class CodeWriter:
    def __init__(self) -> None:
        self.lines: List[str] = []
        self.mappings: List[Dict[str, Any]] = []

    def add(self, line: str = "", path: Optional[str] = None, symbol: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
        line_no = len(self.lines) + 1
        self.lines.append(line)
        if path:
            mapping = {
                "json_path": path,
                "python_lines": [line_no, line_no],
                "symbol": symbol or line.strip(),
            }
            if metadata:
                mapping.update({key: value for key, value in metadata.items() if value is not None})
            self.mappings.append(mapping)

    def render(self) -> str:
        return "\n".join(self.lines) + "\n"

    def source_map(self, generated_file: str, scene_name: str = "GeneratedScene") -> Dict[str, Any]:
        return {
            "generated_file": generated_file,
            "scene_name": scene_name,
            "mappings": self.mappings,
        }

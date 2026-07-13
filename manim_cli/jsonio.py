from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


Diagnostic = Dict[str, Any]


def ok_result(phase: str, **fields: Any) -> Diagnostic:
    result: Diagnostic = {"ok": True, "phase": phase}
    result.update(fields)
    return result


def error_result(
    phase: str,
    error_type: str,
    message: str,
    *,
    location: Optional[Dict[str, Any]] = None,
    suggestions: Optional[Iterable[str]] = None,
    details: Optional[Any] = None,
) -> Diagnostic:
    result: Diagnostic = {
        "ok": False,
        "phase": phase,
        "error_type": error_type,
        "message": message,
        "location": location or {},
        "suggestions": list(suggestions or []),
    }
    if details is not None:
        result["details"] = details
    return result


def print_json(data: Diagnostic) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True))


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


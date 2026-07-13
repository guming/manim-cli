from __future__ import annotations

import keyword
import re
from typing import Set


def safe_var_name(dsl_id: str, used: Set[str]) -> str:
    base = re.sub(r"[^0-9a-zA-Z_]", "_", dsl_id).strip("_") or "object"
    if base[0].isdigit():
        base = f"_{base}"
    base = f"mobj_{base}"
    if keyword.iskeyword(base):
        base = f"{base}_obj"

    name = base
    index = 2
    while name in used:
        name = f"{base}_{index}"
        index += 1
    used.add(name)
    return name


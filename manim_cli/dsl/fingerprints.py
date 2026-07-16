from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import shutil
from typing import Any, Dict, Optional

from manim_cli.build import content_hash
from manim_cli.dsl.knowledge import load_local_documents, memory_document_id
from manim_cli.dsl.models import SceneDef


LAYOUT_CACHE_SCHEMA_VERSION = 1


def source_fingerprint(scene: SceneDef) -> str:
    return hash_json(scene.model_dump(mode="json", by_alias=True))


def layout_fingerprint(scene: SceneDef) -> str:
    config = scene.config.model_dump(mode="json", exclude_none=True)
    payload = {
        "version": scene.version,
        "layout_template": scene.layout_template,
        "config": {
            "resolution": config.get("resolution"),
            "frame_height": config.get("frame_height"),
        },
        "mobjects": [
            {
                "id": mob.id,
                "type": mob.type,
                "args": mob.args,
                "style": mob.style.model_dump(mode="json", exclude_none=True) if mob.style else None,
                "position": mob.position.model_dump(mode="json", exclude_none=True) if mob.position else None,
                "layout": mob.layout.model_dump(mode="json", exclude_none=True) if mob.layout else None,
                "layout_role": mob.layout_role,
                "render_role": mob.render_role,
            }
            for mob in scene.mobjects
        ],
        "visible_steps": [
            {
                "actions": [
                    {
                        key: value
                        for key, value in action.model_dump(mode="json", exclude_none=True).items()
                        if key in {"type", "target", "to", "slot", "region", "color", "match_by"}
                    }
                    for action in step.actions
                ]
            }
            for step in scene.steps
        ],
    }
    return hash_json(payload)


def memory_revision(base_dir: Optional[Path]) -> str:
    documents = []
    for document in load_local_documents(base_dir):
        doc_type = str(document["document_type"])
        if doc_type not in ("knowledge", "policy"):
            continue
        if doc_type == "policy" and document.get("status", "active") != "active":
            continue
        normalized = {key: value for key, value in document.items() if not key.startswith("_")}
        documents.append(
            {
                "document_type": doc_type,
                "id": memory_document_id(document, doc_type),
                "source_scope": document.get("_scope", "project"),
                "content": normalized,
            }
        )
    documents.sort(key=lambda item: (item["document_type"], item["id"], item["source_scope"]))
    return hash_json(documents)


def bbox_environment_version() -> str:
    payload: Dict[str, Any] = {"manim_version": package_version("manim")}
    for executable in ("latex", "dvisvgm"):
        path = shutil.which(executable)
        payload[executable] = executable_identity(path)
    return hash_json(payload)


def executable_identity(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    resolved = Path(path).resolve()
    try:
        stat = resolved.stat()
    except OSError:
        return {"path": str(resolved), "unreadable": True}
    return {"path": str(resolved), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def package_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unavailable"


def layout_cache_identity(scene: SceneDef, base_dir: Optional[Path]) -> Dict[str, Any]:
    return {
        "schema_version": LAYOUT_CACHE_SCHEMA_VERSION,
        "source_fingerprint": source_fingerprint(scene),
        "layout_fingerprint": layout_fingerprint(scene),
        "memory_revision": memory_revision(base_dir),
        "bbox_environment_version": bbox_environment_version(),
    }


def layout_cache_key(identity: Dict[str, Any]) -> str:
    return hash_json(
        {
            key: identity[key]
            for key in ("schema_version", "layout_fingerprint", "memory_revision", "bbox_environment_version")
        }
    )


def hash_json(value: Any) -> str:
    return content_hash(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))

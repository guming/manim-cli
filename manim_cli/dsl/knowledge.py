from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, List, Optional

try:
    import yaml
except ModuleNotFoundError:  # JSON-only commands should remain available without optional YAML support.
    yaml = None

from manim_cli.build import content_hash
from manim_cli.dsl.models import SceneDef


_RETRIEVAL_CACHE: dict[str, List[Dict[str, Any]]] = {}
_MEMORY_SUFFIXES = (".json", ".yaml", ".yml")
_POLICY_LIMIT = 20
_COMPATIBILITY_SCAN_LIMIT = 200
_MEMORY_INDEX_VERSION = 1
_POLICY_SAFETY_RANK = {"block": 0, "enforce": 1, "fallback": 2, "diagnostic": 3, "allow": 4}


class MemoryDocumentError(ValueError):
    """Raised when a local layout-memory document is invalid or ambiguous."""


def load_local_documents(base_dir: Optional[Path]) -> List[Dict[str, Any]]:
    if base_dir is None:
        return []
    return load_scoped_documents(memory_scope_roots(base_dir))


def memory_scope_roots(base_dir: Path) -> List[tuple[str, Path]]:
    package_root = Path(__file__).resolve().parents[1] / "builtin_layout_memory"
    user_root = Path(os.environ.get("MANIM_CLI_USER_MEMORY_DIR", Path.home() / ".manim-cli" / "layout_memory"))
    configured_project_root = base_dir / ".manim-cli" / "layout_memory"
    roots = [("built_in", package_root), ("user", user_root), ("project", base_dir)]
    if configured_project_root != base_dir:
        roots.append(("project", configured_project_root))
    return roots


def load_scoped_documents(scope_roots: List[tuple[str, Path]]) -> List[Dict[str, Any]]:
    resolved: dict[tuple[str, str], Dict[str, Any]] = {}
    source_scope_rank = {"built_in": 0, "user": 1, "project": 2, "scene_inline": 3}
    ordered_roots = sorted(enumerate(scope_roots), key=lambda item: (source_scope_rank.get(item[1][0], 99), item[0]))
    seen_per_scope: dict[tuple[str, str, str], Path] = {}
    for _, (scope, root) in ordered_roots:
        if not root.exists():
            continue
        for doc in load_documents_from_root(root, scope, seen_per_scope):
            doc_type = str(doc["document_type"])
            document_id = memory_document_id(doc, doc_type)
            resolved[(doc_type, document_id)] = doc
    return sorted(
        resolved.values(),
        key=lambda doc: (str(doc.get("document_type", "")), memory_document_id(doc, str(doc["document_type"]))),
    )


def load_documents_from_root(root: Path, scope: str, seen_per_scope: dict[tuple[str, str, str], Path]) -> List[Dict[str, Any]]:
    index_path = root / "index.json"
    if index_path.exists():
        return load_documents_from_index(root, scope, seen_per_scope, index_path)
    return scan_documents_from_root(root, scope, seen_per_scope, limit=_COMPATIBILITY_SCAN_LIMIT)


def scan_documents_from_root(
    root: Path,
    scope: str,
    seen_per_scope: dict[tuple[str, str, str], Path],
    limit: int,
) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    paths: List[tuple[Path, str]] = []
    for folder, doc_type in (("knowledge", "knowledge"), ("policies", "policy"), ("failures/reviewed", "failure_memory")):
        folder_root = root / folder
        if not folder_root.exists():
            continue
        for path in memory_document_paths(folder_root):
            paths.append((path, doc_type))
    if len(paths) > limit:
        raise MemoryDocumentError(f"memory compatibility scan at {root} found {len(paths)} documents; rebuild index.json (limit {limit})")
    for path, doc_type in paths:
        loaded = load_document(path, doc_type)
        if loaded:
            register_scoped_document(loaded, path, doc_type, scope, seen_per_scope)
            loaded["_index_mode"] = "compatibility_scan"
            docs.append(loaded)
    return docs


def load_documents_from_index(
    root: Path,
    scope: str,
    seen_per_scope: dict[tuple[str, str, str], Path],
    index_path: Path,
) -> List[Dict[str, Any]]:
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryDocumentError(f"invalid memory index {index_path}: {exc}") from exc
    if not isinstance(index, dict) or index.get("version") != _MEMORY_INDEX_VERSION or not isinstance(index.get("items"), list):
        raise MemoryDocumentError(f"invalid memory index {index_path}: expected version {_MEMORY_INDEX_VERSION} with items list")
    docs: List[Dict[str, Any]] = []
    for item in index["items"]:
        if not isinstance(item, dict):
            raise MemoryDocumentError(f"invalid memory index item in {index_path}: item must be an object")
        relative_path = item.get("path")
        doc_type = item.get("document_type")
        if not isinstance(relative_path, str) or doc_type not in ("knowledge", "policy", "failure_memory"):
            raise MemoryDocumentError(f"invalid memory index item in {index_path}: path/document_type is invalid")
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise MemoryDocumentError(f"memory index path escapes root: {relative_path}") from exc
        if not path.exists() or path.suffix.lower() not in _MEMORY_SUFFIXES:
            raise MemoryDocumentError(f"memory index references missing or unsupported document: {path}")
        source_hash = content_hash(path.read_bytes())
        if item.get("source_hash") != source_hash:
            raise MemoryDocumentError(f"stale memory index entry for {path}; run rebuild-index")
        loaded = load_document(path, str(doc_type))
        if memory_document_id(loaded, str(doc_type)) != item.get("id"):
            raise MemoryDocumentError(f"memory index ID mismatch for {path}; run rebuild-index")
        register_scoped_document(loaded, path, str(doc_type), scope, seen_per_scope)
        loaded["_index_mode"] = "index"
        docs.append(loaded)
    return docs


def register_scoped_document(
    loaded: Dict[str, Any],
    path: Path,
    doc_type: str,
    scope: str,
    seen_per_scope: dict[tuple[str, str, str], Path],
) -> None:
    document_id = memory_document_id(loaded, doc_type)
    seen_key = (scope, doc_type, document_id)
    previous = seen_per_scope.get(seen_key)
    if previous is not None:
        raise MemoryDocumentError(f"duplicate {doc_type} id {document_id!r} in {scope} scope: {previous} and {path}")
    seen_per_scope[seen_key] = path
    loaded["_scope"] = scope


def rebuild_memory_index(root: Path) -> Path:
    documents = scan_documents_from_root(root, "project", {}, limit=100_000)
    items = []
    for document in documents:
        path = Path(str(document["_path"]))
        doc_type = str(document["document_type"])
        items.append(
            {
                "id": memory_document_id(document, doc_type),
                "document_type": doc_type,
                "path": path.relative_to(root).as_posix(),
                "source_hash": content_hash(path.read_bytes()),
                "metadata": memory_index_metadata(document, doc_type),
            }
        )
    items.sort(key=lambda item: (item["document_type"], item["id"]))
    index_path = root / "index.json"
    write_memory_document(index_path, {"version": _MEMORY_INDEX_VERSION, "items": items})
    return index_path


def memory_index_metadata(document: Dict[str, Any], doc_type: str) -> Dict[str, Any]:
    keys_by_type = {
        "knowledge": ("match", "required_roles", "priority"),
        "policy": ("status", "type", "priority", "when", "supersedes"),
        "failure_memory": ("scene_type", "trigger", "evidence", "severity", "confidence"),
    }
    return {key: document[key] for key in keys_by_type[doc_type] if key in document}


def scoped_retrieval_candidates(base_dir: Optional[Path]) -> List[Dict[str, Any]]:
    if base_dir is None:
        return []
    resolved: dict[tuple[str, str], Dict[str, Any]] = {}
    scope_rank = {"built_in": 0, "user": 1, "project": 2, "scene_inline": 3}
    roots = memory_scope_roots(base_dir)
    for order, (scope, root) in sorted(enumerate(roots), key=lambda item: (scope_rank.get(item[1][0], 99), item[0])):
        if not root.exists():
            continue
        index_path = root / "index.json"
        if index_path.exists():
            entries = read_retrieval_index_entries(root, index_path, scope)
        else:
            documents = scan_documents_from_root(root, scope, {}, limit=_COMPATIBILITY_SCAN_LIMIT)
            entries = [retrieval_candidate_from_loaded_document(document, root) for document in documents]
        for entry in entries:
            if entry["document_type"] not in ("knowledge", "failure_memory"):
                continue
            resolved[(entry["document_type"], entry["id"])] = entry
    return list(resolved.values())


def read_retrieval_index_entries(root: Path, index_path: Path, scope: str) -> List[Dict[str, Any]]:
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MemoryDocumentError(f"invalid memory index {index_path}: {exc}") from exc
    if not isinstance(index, dict) or index.get("version") != _MEMORY_INDEX_VERSION or not isinstance(index.get("items"), list):
        raise MemoryDocumentError(f"invalid memory index {index_path}: expected version {_MEMORY_INDEX_VERSION} with items list")
    entries: List[Dict[str, Any]] = []
    for item in index["items"]:
        if not isinstance(item, dict) or not isinstance(item.get("metadata"), dict):
            raise MemoryDocumentError(f"memory index {index_path} lacks retrieval metadata; run rebuild-index")
        if item.get("document_type") not in ("knowledge", "policy", "failure_memory") or not isinstance(item.get("id"), str):
            raise MemoryDocumentError(f"invalid memory index item in {index_path}")
        entries.append({**item, "root": root, "source_scope": scope, "index_mode": "index"})
    return entries


def retrieval_candidate_from_loaded_document(document: Dict[str, Any], root: Path) -> Dict[str, Any]:
    doc_type = str(document["document_type"])
    return {
        "id": memory_document_id(document, doc_type),
        "document_type": doc_type,
        "path": Path(str(document["_path"])).relative_to(root).as_posix(),
        "source_hash": content_hash(Path(str(document["_path"])).read_bytes()),
        "metadata": memory_index_metadata(document, doc_type),
        "root": root,
        "source_scope": document.get("_scope", "project"),
        "index_mode": "compatibility_scan",
        "loaded_document": document,
    }


def load_retrieval_candidate(entry: Dict[str, Any]) -> Dict[str, Any]:
    loaded = entry.get("loaded_document")
    if isinstance(loaded, dict):
        return loaded
    root = Path(entry["root"])
    path = (root / str(entry["path"])).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise MemoryDocumentError(f"memory index path escapes root: {entry['path']}") from exc
    if not path.exists() or content_hash(path.read_bytes()) != entry.get("source_hash"):
        raise MemoryDocumentError(f"stale memory index entry for {path}; run rebuild-index")
    document = load_document(path, str(entry["document_type"]))
    if memory_document_id(document, str(entry["document_type"])) != entry["id"]:
        raise MemoryDocumentError(f"memory index ID mismatch for {path}; run rebuild-index")
    document["_scope"] = entry["source_scope"]
    document["_index_mode"] = entry["index_mode"]
    return document


def memory_document_paths(root: Path) -> List[Path]:
    return sorted(path for path in root.iterdir() if path.is_file() and path.suffix.lower() in _MEMORY_SUFFIXES)


def load_document(path: Path, doc_type: str) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        elif path.suffix.lower() in (".yaml", ".yml"):
            require_yaml()
            data = yaml.safe_load(text)
        else:
            raise MemoryDocumentError(f"unsupported memory document format: {path}")
    except (OSError, json.JSONDecodeError, MemoryDocumentError) as exc:
        raise MemoryDocumentError(f"invalid {doc_type} document {path}: {exc}") from exc
    except Exception as exc:
        if yaml is not None and isinstance(exc, yaml.YAMLError):
            raise MemoryDocumentError(f"invalid {doc_type} document {path}: {exc}") from exc
        raise
    if not isinstance(data, dict):
        raise MemoryDocumentError(f"invalid {doc_type} document {path}: root must be an object/mapping")
    data = dict(data)
    data.setdefault("document_type", doc_type)
    if data["document_type"] != doc_type:
        raise MemoryDocumentError(f"invalid {doc_type} document {path}: document_type must be {doc_type!r}")
    memory_document_id(data, doc_type, path=path)
    data["_path"] = str(path)
    return data


def memory_document_id(data: Dict[str, Any], doc_type: str, path: Optional[Path] = None) -> str:
    key = {"knowledge": "id", "policy": "policy_id", "failure_memory": "failure_id"}[doc_type]
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        location = f" {path}" if path else ""
        raise MemoryDocumentError(f"invalid {doc_type} document{location}: {key} must be a non-empty string")
    return value


def write_memory_document(path: Path, data: Dict[str, Any]) -> None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        content = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    elif suffix in (".yaml", ".yml"):
        require_yaml()
        content = yaml.safe_dump(data, allow_unicode=True, sort_keys=True)
    else:
        raise MemoryDocumentError(f"unsupported memory document format: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    _RETRIEVAL_CACHE.clear()


def scene_features(scene: SceneDef) -> Dict[str, Any]:
    formulas = [str(mob.args.get("tex", "")) for mob in scene.mobjects if mob.type == "Tex"]
    roles = sorted({mob.layout_role for mob in scene.mobjects if mob.layout_role})
    mobject_types = sorted({mob.type for mob in scene.mobjects})
    text = " ".join([scene.name or "", scene.description or "", " ".join(formulas)]).lower()
    formula_features = sorted(set(feature for formula in formulas for feature in formula_features_for(formula)))
    return {
        "layout_template": scene.layout_template,
        "roles": roles,
        "mobject_types": mobject_types,
        "formula_features": formula_features,
        "text": text,
    }


def formula_features_for(formula: str) -> List[str]:
    features: List[str] = []
    if r"\frac" in formula:
        features.append("fraction")
    if r"\lim" in formula:
        features.append("limit")
    if "f'" in formula or r"\frac{d" in formula:
        features.append("derivative_notation")
    if r"\lim" in formula and r"\frac" in formula:
        features.append("limit_difference_quotient")
    return features


def retrieve_top_k(scene: SceneDef, base_dir: Optional[Path], top_k: int = 3) -> List[Dict[str, Any]]:
    features = scene_features(scene)
    cache_key = retrieval_cache_key(scene, base_dir, top_k, features)
    if cache_key in _RETRIEVAL_CACHE:
        return _RETRIEVAL_CACHE[cache_key]
    ranked: List[tuple[int, str, Dict[str, Any]]] = []
    for candidate in scoped_retrieval_candidates(base_dir):
        doc_type = str(candidate["document_type"])
        metadata = {**candidate["metadata"], "document_type": doc_type}
        metadata[{"knowledge": "id", "failure_memory": "failure_id"}[doc_type]] = candidate["id"]
        score = score_document(metadata, features)
        if score <= 0:
            continue
        ranked.append((-score, candidate["id"], candidate))
    ranked.sort(key=lambda item: (item[0], item[1]))
    result = [
        {"score": -negative_score, "document": compact_document(load_retrieval_candidate(candidate))}
        for negative_score, _, candidate in ranked[: max(0, top_k)]
    ]
    _RETRIEVAL_CACHE[cache_key] = result
    return result


def retrieve_typed_top_k(
    scene: SceneDef,
    base_dir: Optional[Path],
    issue_types: Optional[Iterable[str]] = None,
    max_knowledge: int = 2,
    max_reviewed_failures: int = 3,
    min_knowledge_score: int = 12,
    min_failure_score: int = 10,
) -> Dict[str, Any]:
    features = scene_features(scene)
    features["scene_type"] = infer_scene_type(features)
    features["issue_types"] = sorted({str(issue_type) for issue_type in (issue_types or [])})
    knowledge_ranked: List[tuple[int, str, List[str], Dict[str, Any]]] = []
    failures_ranked: List[tuple[int, str, List[str], Dict[str, Any]]] = []
    for candidate in scoped_retrieval_candidates(base_dir):
        doc_type = candidate["document_type"]
        metadata = {**candidate["metadata"]}
        id_key = "id" if doc_type == "knowledge" else "failure_id"
        metadata[id_key] = candidate["id"]
        if doc_type == "knowledge":
            score, matches = score_knowledge_document(metadata, features)
            if score >= min_knowledge_score:
                knowledge_ranked.append((-score, candidate["id"], matches, candidate))
        elif doc_type == "failure_memory":
            score, matches = score_failure_document(metadata, features)
            if score >= min_failure_score:
                failures_ranked.append((-score, candidate["id"], matches, candidate))
    knowledge_ranked.sort(key=lambda item: (item[0], item[1]))
    failures_ranked.sort(key=lambda item: (item[0], item[1]))
    knowledge = [
        retrieval_result(load_retrieval_candidate(candidate), -negative_score, matches)
        for negative_score, _, matches, candidate in knowledge_ranked[: max(0, max_knowledge)]
    ]
    failures = [
        retrieval_result(load_retrieval_candidate(candidate), -negative_score, matches)
        for negative_score, _, matches, candidate in failures_ranked[: max(0, max_reviewed_failures)]
    ]
    return {
        "knowledge": knowledge,
        "reviewed_failures": failures,
        "budget": {
            "max_knowledge_files": max_knowledge,
            "max_reviewed_failures": max_reviewed_failures,
            "min_knowledge_score": min_knowledge_score,
            "min_failure_score": min_failure_score,
        },
    }


def build_repair_memory_context(
    scene: SceneDef,
    base_dir: Optional[Path],
    issue_types: Optional[Iterable[str]] = None,
    max_prompt_tokens: int = 500,
) -> Dict[str, Any]:
    retrieval = retrieve_typed_top_k(scene, base_dir, issue_types=issue_types)
    candidates = [
        repair_memory_candidate(item, "knowledge") for item in retrieval["knowledge"]
    ] + [
        repair_memory_candidate(item, "failure_memory") for item in retrieval["reviewed_failures"]
    ]
    selected: List[Dict[str, Any]] = []
    skipped_budget_ids: List[str] = []
    seen_summaries: set[str] = set()
    for candidate in candidates:
        summary = candidate["prompt_summary"]
        if not summary or summary in seen_summaries:
            continue
        trial = selected + [candidate]
        if estimate_prompt_tokens(render_repair_memory_section_items(trial)) > max_prompt_tokens:
            skipped_budget_ids.append(candidate["id"])
            continue
        selected.append(candidate)
        seen_summaries.add(summary)
    rendered = render_repair_memory_section_items(selected)
    return {
        "selected": selected,
        "selected_ids": [item["id"] for item in selected],
        "skipped_budget_ids": skipped_budget_ids,
        "estimated_prompt_tokens": estimate_prompt_tokens(rendered),
        "max_prompt_tokens": max_prompt_tokens,
        "token_estimator": "ceil(unicode_codepoints/4)",
        "retrieval_budget": retrieval["budget"],
    }


def repair_memory_candidate(item: Dict[str, Any], document_type: str) -> Dict[str, Any]:
    stable_id = item.get("id") or item.get("failure_id")
    summary = " ".join(str(item.get("prompt_summary", "")).split())
    return {
        "id": str(stable_id),
        "document_type": document_type,
        "score": int(item["score"]),
        "prompt_summary": summary,
        "matched_features": list(item.get("matched_features", [])),
        "source_scope": item.get("source_scope", "project"),
    }


def render_repair_memory_section(context: Dict[str, Any]) -> str:
    selected = context.get("selected") if isinstance(context.get("selected"), list) else []
    return render_repair_memory_section_items(selected)


def render_repair_memory_section_items(selected: List[Dict[str, Any]]) -> str:
    if not selected:
        return ""
    lines = ["## Known layout risks", ""]
    for item in selected:
        kind = "Knowledge" if item.get("document_type") == "knowledge" else "Reviewed failure"
        lines.append(f"- {kind} `{item.get('id')}`: {item.get('prompt_summary')}")
    return "\n".join(lines) + "\n"


def estimate_prompt_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def score_knowledge_document(doc: Dict[str, Any], features: Dict[str, Any]) -> tuple[int, List[str]]:
    match = doc.get("match") if isinstance(doc.get("match"), dict) else {}
    matched: List[str] = []
    score = 0
    score += scored_overlap(match.get("mobject_types"), features["mobject_types"], 2, "mobject_type", matched)
    score += scored_overlap(match.get("formula_features"), features["formula_features"], 3, "formula", matched)
    score += scored_overlap(doc.get("required_roles"), features["roles"], 3, "role", matched)
    score += scored_tokens(match.get("topic_keywords"), features["text"], 1, "keyword", matched)
    priority = doc.get("priority", 0)
    if isinstance(priority, (int, float)) and priority:
        priority_score = int(priority) // 10
        score += priority_score
        if priority_score:
            matched.append(f"priority:{int(priority)}")
    return score, sorted(set(matched))


def score_failure_document(doc: Dict[str, Any], features: Dict[str, Any]) -> tuple[int, List[str]]:
    trigger = doc.get("trigger") if isinstance(doc.get("trigger"), dict) else {}
    evidence = doc.get("evidence") if isinstance(doc.get("evidence"), dict) else {}
    matched: List[str] = []
    score = 0
    if doc.get("scene_type") and doc.get("scene_type") == features.get("scene_type"):
        score += 5
        matched.append(f"scene_type:{doc['scene_type']}")
    if trigger.get("layout_template") and trigger.get("layout_template") == features.get("layout_template"):
        score += 4
        matched.append(f"layout_template:{trigger['layout_template']}")
    score += scored_overlap(trigger.get("visible_roles"), features["roles"], 2, "role", matched)
    score += scored_overlap(trigger.get("formula_features"), features["formula_features"], 3, "formula", matched)
    score += scored_overlap(evidence.get("issue_types"), features["issue_types"], 4, "issue", matched)
    if doc.get("severity") == "blocking":
        score += 2
        matched.append("severity:blocking")
    if doc.get("confidence") == "high":
        score += 2
        matched.append("confidence:high")
    return score, sorted(set(matched))


def scored_overlap(expected: Any, actual: Iterable[str], weight: int, label: str, matched: List[str]) -> int:
    if not isinstance(expected, list):
        return 0
    actual_set = set(actual)
    hits = [str(item) for item in expected if item in actual_set]
    matched.extend(f"{label}:{item}" for item in hits)
    return len(hits) * weight


def scored_tokens(tokens: Any, text: str, weight: int, label: str, matched: List[str]) -> int:
    if not isinstance(tokens, list):
        return 0
    hits = [token for token in tokens if isinstance(token, str) and token.lower() in text]
    matched.extend(f"{label}:{token}" for token in hits)
    return len(hits) * weight


def retrieval_result(doc: Dict[str, Any], score: int, matched_features: List[str]) -> Dict[str, Any]:
    result = compact_document(doc)
    result.pop("_path", None)
    result["score"] = score
    result["matched_features"] = matched_features
    result["source_scope"] = doc.get("_scope", "project")
    result["source_path"] = doc.get("_path")
    result["index_mode"] = doc.get("_index_mode", "compatibility_scan")
    return result


def retrieval_cache_key(scene: SceneDef, base_dir: Optional[Path], top_k: int, features: Dict[str, Any]) -> str:
    payload = {
        "base_dir": str(base_dir.resolve()) if base_dir else None,
        "top_k": top_k,
        "features": features,
    }
    return content_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def score_document(doc: Dict[str, Any], features: Dict[str, Any]) -> int:
    score = 0
    match = doc.get("match") if isinstance(doc.get("match"), dict) else {}
    when = doc.get("when") if isinstance(doc.get("when"), dict) else {}
    trigger = doc.get("trigger") if isinstance(doc.get("trigger"), dict) else {}
    score += overlap_score(match.get("mobject_types"), features["mobject_types"], 2)
    score += overlap_score(match.get("formula_features"), features["formula_features"], 3)
    score += overlap_score(doc.get("required_roles"), features["roles"], 3)
    score += overlap_score(trigger.get("visible_roles"), features["roles"], 3)
    score += overlap_score(when.get("visible_roles"), features["roles"], 3)
    if doc.get("layout_template") == features.get("layout_template"):
        score += 4
    if trigger.get("layout_template") == features.get("layout_template"):
        score += 4
    if when.get("layout_template") == features.get("layout_template"):
        score += 4
    score += formula_token_score(match.get("topic_keywords"), features["text"], 1)
    score += formula_token_score(trigger.get("formula_contains"), features["text"], 3)
    score += formula_token_score(when.get("formula_contains_any"), features["text"], 3)
    return score


def overlap_score(expected: Any, actual: Iterable[str], weight: int) -> int:
    if not isinstance(expected, list):
        return 0
    actual_set = set(actual)
    return sum(weight for item in expected if item in actual_set)


def formula_token_score(tokens: Any, text: str, weight: int) -> int:
    if not isinstance(tokens, list):
        return 0
    return sum(weight for token in tokens if isinstance(token, str) and token.lower() in text)


def compact_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    keys = ("document_type", "id", "policy_id", "failure_id", "type", "description", "prompt_summary", "risk_tags", "_path")
    return {key: doc[key] for key in keys if key in doc}


def policy_warnings(scene: SceneDef, base_dir: Optional[Path], profile: str = "relaxed") -> List[Dict[str, Any]]:
    return matched_policy_warnings(scene, base_dir, profile=profile)


def matched_policy_warnings(scene: SceneDef, base_dir: Optional[Path], profile: str = "relaxed") -> List[Dict[str, Any]]:
    features = scene_features(scene)
    matched: List[Dict[str, Any]] = []
    for doc in load_local_documents(base_dir):
        if doc.get("document_type") != "policy":
            continue
        status = doc.get("status", "active")
        if status not in ("candidate", "active", "disabled"):
            raise MemoryDocumentError(f"invalid policy status {status!r} in {doc.get('_path')}")
        if status != "active":
            continue
        when = doc.get("when")
        if not isinstance(when, dict) or not policy_matches(when, features):
            continue
        policy_type = doc.get("type", "diagnostic")
        if policy_type not in _POLICY_SAFETY_RANK:
            raise MemoryDocumentError(f"invalid policy type {policy_type!r} in {doc.get('_path')}")
        matched.append(doc)

    matched = apply_supersedes(matched)
    matched.sort(key=policy_sort_key)
    warnings: List[Dict[str, Any]] = []
    if len(matched) > _POLICY_LIMIT:
        warnings.append(
            {
                "type": "layout_policy_budget_exceeded",
                "policy_count": len(matched),
                "max_policies_loaded": _POLICY_LIMIT,
                "message": f"{len(matched)} active policies matched; the limit is {_POLICY_LIMIT}.",
                "source": "local_policy",
            }
        )
        if profile in ("strict", "final"):
            return warnings
        matched = matched[:_POLICY_LIMIT]

    conflict_ids = policy_conflict_ids(matched)
    if conflict_ids:
        warnings.append(
            {
                "type": "layout_policy_conflict",
                "policy_ids": sorted(conflict_ids),
                "message": "Active layout policies declare incompatible effects for the same condition.",
                "source": "local_policy",
            }
        )
    allowed_ids = allowed_policy_ids(matched)
    for doc in matched:
        policy_id = memory_document_id(doc, "policy")
        policy_type = str(doc.get("type", "diagnostic"))
        if policy_id in conflict_ids or policy_id in allowed_ids:
            continue
        warnings.append(policy_applied_warning(doc, policy_type))
    return warnings


def policy_sort_key(doc: Dict[str, Any]) -> tuple[int, int, str]:
    policy_type = str(doc.get("type", "diagnostic"))
    return (_POLICY_SAFETY_RANK[policy_type], -int(doc.get("priority", 0)), memory_document_id(doc, "policy"))


def apply_supersedes(policies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    superseded = {
        str(policy_id)
        for policy in policies
        for policy_id in (policy.get("supersedes") if isinstance(policy.get("supersedes"), list) else [])
    }
    return [policy for policy in policies if memory_document_id(policy, "policy") not in superseded]


def policy_conflict_ids(policies: List[Dict[str, Any]]) -> set[str]:
    conflicts: set[str] = set()
    grouped: dict[tuple[str, str], List[Dict[str, Any]]] = {}
    for policy in policies:
        policy_type = str(policy.get("type", "diagnostic"))
        if policy_type not in ("enforce", "fallback"):
            continue
        when_key = json.dumps(policy.get("when", {}), ensure_ascii=False, sort_keys=True)
        grouped.setdefault((policy_type, when_key), []).append(policy)
    for (policy_type, _), group in grouped.items():
        effect_key = "enforce" if policy_type == "enforce" else "fallback"
        effects = {json.dumps(policy.get(effect_key), ensure_ascii=False, sort_keys=True) for policy in group}
        if len(effects) > 1:
            conflicts.update(memory_document_id(policy, "policy") for policy in group)
    return conflicts


def allowed_policy_ids(policies: List[Dict[str, Any]]) -> set[str]:
    by_id = {memory_document_id(policy, "policy"): policy for policy in policies}
    allowed: set[str] = set()
    for policy in policies:
        if policy.get("type") != "allow":
            continue
        targets = policy.get("allows") if isinstance(policy.get("allows"), list) else []
        for target_id in targets:
            target = by_id.get(str(target_id))
            if target and target.get("type") in ("diagnostic", "enforce"):
                allowed.add(str(target_id))
    return allowed


def policy_applied_warning(doc: Dict[str, Any], policy_type: str) -> Dict[str, Any]:
    return {
        "type": "layout_memory_policy_applied",
        "policy_id": memory_document_id(doc, "policy"),
        "policy_type": policy_type,
        "policy_status": "active",
        "priority": int(doc.get("priority", 0)),
        "message": doc.get("message") or doc.get("prompt_summary") or "Local layout policy matched this scene.",
        "source": "local_policy",
        "source_scope": doc.get("_scope", "project"),
    }


def compile_policy_changes(scene: SceneDef, base_dir: Optional[Path], profile: str = "relaxed") -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    for warning in matched_policy_warnings(scene, base_dir, profile=profile):
        if warning["type"] != "layout_memory_policy_applied":
            changes.append({"change": warning["type"], **{key: value for key, value in warning.items() if key != "type"}})
            continue
        changes.append(
            {
                "change": "layout_memory_policy_applied",
                "policy_id": warning["policy_id"],
                "policy_type": warning["policy_type"],
                "policy_status": warning["policy_status"],
                "priority": warning["priority"],
                "source": warning["source"],
                "source_scope": warning["source_scope"],
                "effect": "diagnostic" if warning["policy_type"] == "diagnostic" else warning["policy_type"],
            }
        )
    return changes


def policy_matches(when: Dict[str, Any], features: Dict[str, Any]) -> bool:
    if when.get("layout_template") and when.get("layout_template") != features.get("layout_template"):
        return False
    if when.get("role") and when.get("role") not in features["roles"]:
        return False
    if isinstance(when.get("visible_roles"), list) and not set(when["visible_roles"]).issubset(set(features["roles"])):
        return False
    if isinstance(when.get("formula_contains_any"), list):
        text = features["text"]
        if not any(isinstance(token, str) and token.lower() in text for token in when["formula_contains_any"]):
            return False
    if isinstance(when.get("formula_features_any"), list):
        formula_features = set(features["formula_features"])
        if not any(feature in formula_features for feature in when["formula_features_any"]):
            return False
    return True


def failure_memory_from_issues(scene: SceneDef, issues: List[Dict[str, Any]], symptom: Optional[str] = None) -> Dict[str, Any]:
    features = scene_features(scene)
    blocking = [issue for issue in issues if issue.get("severity") == "error"]
    selected = blocking or issues
    issue_types = sorted({str(issue.get("type")) for issue in selected if issue.get("type")})
    fingerprints = sorted({str(issue.get("fingerprint")) for issue in selected if issue.get("fingerprint")})
    failure_id = "failure_" + content_hash(json.dumps({"scene": scene.name, "issue_types": issue_types, "fingerprints": fingerprints}, sort_keys=True).encode("utf-8"))[:16]
    return {
        "failure_id": failure_id,
        "version": 1,
        "scene_name": scene.name,
        "scene_type": infer_scene_type(features),
        "symptom": symptom or "; ".join(issue_types) or "qa_failure",
        "trigger": {
            "layout_template": features.get("layout_template"),
            "visible_roles": features.get("roles", []),
            "mobject_types": features.get("mobject_types", []),
            "formula_features": features.get("formula_features", []),
        },
        "evidence": {
            "issue_types": issue_types,
            "issue_fingerprints": fingerprints,
            "issue_count": len(selected),
        },
        "root_cause": [],
        "avoidance": [],
        "severity": "blocking" if blocking else "warning",
        "confidence": "medium",
        "prompt_summary": build_failure_prompt_summary(scene, issue_types, features),
    }


def infer_scene_type(features: Dict[str, Any]) -> str:
    if "limit_difference_quotient" in features.get("formula_features", []):
        return "derivative_geometry"
    return "unknown"


def build_failure_prompt_summary(scene: SceneDef, issue_types: List[str], features: Dict[str, Any]) -> str:
    template = features.get("layout_template") or "no_template"
    issues = ", ".join(issue_types) if issue_types else "qa warnings"
    return f"{scene.name} produced {issues} under {template}; review layout roles, formula size, and split/fallback policy."


def write_failure_memory(
    base_dir: Path,
    scene: SceneDef,
    issues: List[Dict[str, Any]],
    symptom: Optional[str] = None,
    output_format: str = "json",
) -> Path:
    memory = failure_memory_from_issues(scene, issues, symptom=symptom)
    inbox = base_dir / "failures" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    suffix = memory_format_suffix(output_format)
    path = inbox / f"{memory['failure_id']}{suffix}"
    write_memory_document(path, memory)
    return path


def policy_candidate_from_reviewed_failure(failure: Dict[str, Any], policy_type: str = "diagnostic") -> Dict[str, Any]:
    failure_id = str(failure.get("failure_id") or "reviewed_failure")
    trigger = failure.get("trigger") if isinstance(failure.get("trigger"), dict) else {}
    evidence = failure.get("evidence") if isinstance(failure.get("evidence"), dict) else {}
    policy_id = "policy_" + sanitize_policy_id(failure_id)
    when: Dict[str, Any] = {}
    if trigger.get("layout_template"):
        when["layout_template"] = trigger["layout_template"]
    visible_roles = trigger.get("visible_roles")
    if isinstance(visible_roles, list) and visible_roles:
        when["visible_roles"] = visible_roles
    formula_features = trigger.get("formula_features")
    if isinstance(formula_features, list) and formula_features:
        when["formula_features_any"] = formula_features
    policy: Dict[str, Any] = {
        "policy_id": policy_id,
        "version": 1,
        "status": "candidate",
        "type": policy_type,
        "priority": 0,
        "supersedes": [],
        "source_failure_id": failure_id,
        "when": when,
        "message": failure.get("prompt_summary") or failure.get("symptom") or "Reviewed failure policy matched this scene.",
        "evidence": {
            "issue_types": evidence.get("issue_types", []),
            "confidence": failure.get("confidence", "medium"),
            "severity": failure.get("severity", "warning"),
        },
        "tests": [],
    }
    if failure.get("avoidance"):
        policy["avoidance"] = failure["avoidance"]
    return policy


def sanitize_policy_id(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def write_policy_candidate_from_reviewed_failure(
    reviewed_failure_path: Path,
    policies_dir: Path,
    policy_type: str = "diagnostic",
    output_format: str = "json",
) -> Path:
    failure = load_document(reviewed_failure_path, "failure_memory")
    if failure is None:  # pragma: no cover - load_document raises for invalid data.
        raise MemoryDocumentError("reviewed failure could not be loaded")
    failure.pop("_path", None)
    policy = policy_candidate_from_reviewed_failure(failure, policy_type=policy_type)
    suffix = memory_format_suffix(output_format)
    path = policies_dir / f"{policy['policy_id']}{suffix}"
    write_memory_document(path, policy)
    if (policies_dir.parent / "index.json").exists():
        rebuild_memory_index(policies_dir.parent)
    return path


def memory_format_suffix(output_format: str) -> str:
    normalized = output_format.lower()
    if normalized == "json":
        return ".json"
    if normalized == "yaml":
        return ".yaml"
    raise MemoryDocumentError(f"unsupported memory output format: {output_format}")


def require_yaml() -> None:
    if yaml is None:
        raise MemoryDocumentError("PyYAML is required for YAML layout-memory documents; install PyYAML>=6 or use JSON")

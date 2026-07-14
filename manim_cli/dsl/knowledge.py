from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from manim_cli.build import content_hash
from manim_cli.dsl.models import SceneDef


_RETRIEVAL_CACHE: dict[str, List[Dict[str, Any]]] = {}


def load_local_documents(base_dir: Optional[Path]) -> List[Dict[str, Any]]:
    if base_dir is None:
        return []
    docs: List[Dict[str, Any]] = []
    for folder, doc_type in (("knowledge", "knowledge"), ("policies", "policy"), ("failures/reviewed", "failure_memory")):
        root = base_dir / folder
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            loaded = load_document(path, doc_type)
            if loaded:
                docs.append(loaded)
    return docs


def load_document(path: Path, doc_type: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    data = dict(data)
    data.setdefault("document_type", doc_type)
    data["_path"] = str(path)
    return data


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
    scored: List[Dict[str, Any]] = []
    for doc in load_local_documents(base_dir):
        score = score_document(doc, features)
        if score <= 0:
            continue
        scored.append({"score": score, "document": compact_document(doc)})
    scored.sort(key=lambda item: (-item["score"], item["document"].get("id") or item["document"].get("policy_id") or item["document"].get("failure_id") or ""))
    result = scored[: max(0, top_k)]
    _RETRIEVAL_CACHE[cache_key] = result
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


def policy_warnings(scene: SceneDef, base_dir: Optional[Path]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []
    features = scene_features(scene)
    for doc in load_local_documents(base_dir):
        if doc.get("document_type") != "policy":
            continue
        when = doc.get("when")
        if not isinstance(when, dict) or not policy_matches(when, features):
            continue
        policy_type = doc.get("type", "diagnostic")
        warnings.append(
            {
                "type": "layout_memory_policy_applied",
                "policy_id": doc.get("policy_id") or doc.get("id"),
                "policy_type": policy_type,
                "message": doc.get("message") or doc.get("prompt_summary") or "Local layout policy matched this scene.",
                "source": "local_policy",
            }
        )
    return warnings


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


def write_failure_memory(base_dir: Path, scene: SceneDef, issues: List[Dict[str, Any]], symptom: Optional[str] = None) -> Path:
    memory = failure_memory_from_issues(scene, issues, symptom=symptom)
    inbox = base_dir / "failures" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / f"{memory['failure_id']}.json"
    path.write_text(json.dumps(memory, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
        "type": policy_type,
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


def write_policy_candidate_from_reviewed_failure(reviewed_failure_path: Path, policies_dir: Path, policy_type: str = "diagnostic") -> Path:
    failure = json.loads(reviewed_failure_path.read_text(encoding="utf-8"))
    if not isinstance(failure, dict):
        raise ValueError("reviewed failure must be a JSON object")
    policy = policy_candidate_from_reviewed_failure(failure, policy_type=policy_type)
    policies_dir.mkdir(parents=True, exist_ok=True)
    path = policies_dir / f"{policy['policy_id']}.json"
    path.write_text(json.dumps(policy, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path

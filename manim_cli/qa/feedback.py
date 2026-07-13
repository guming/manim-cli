from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from manim_cli.jsonio import write_json


def write_feedback(out_dir: Path, report: Dict[str, Any]) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_json = out_dir / "latest.json"
    agent_prompt = out_dir / "agent_prompt.md"
    write_json(latest_json, report)
    agent_prompt.write_text(render_agent_prompt(report), encoding="utf-8")
    return {"latest_json": str(latest_json), "agent_prompt": str(agent_prompt)}


def render_agent_prompt(report: Dict[str, Any]) -> str:
    issues: List[Dict[str, Any]] = report.get("issues", [])
    high_priority = sorted(issues, key=issue_sort_key)[:5]
    lines = ["# QA repair summary", ""]
    if not high_priority:
        lines.append("No QA issues found.")
        return "\n".join(lines) + "\n"
    for index, issue in enumerate(high_priority, start=1):
        location = issue.get("location", {})
        path = location.get("dsl_path") or location.get("step_id") or ",".join(location.get("object_ids", [])) or "scene"
        scope = issue.get("repair_scope", "scene")
        identity = issue.get("issue_id", issue.get("fingerprint", "qa-issue"))
        lines.append(f"{index}. {issue.get('severity', 'warning').upper()} `{issue.get('type')}` at `{path}`: {issue.get('message')}")
        lines.append(f"   ID: `{identity}` Scope: `{scope}`")
        hints = issue.get("repair_hints") or []
        if hints:
            lines.append(f"   Repair: {hints[0].get('message')}")
    return "\n".join(lines) + "\n"


def issue_sort_key(issue: Dict[str, Any]) -> tuple[int, int, str]:
    severity_rank = {"error": 0, "warning": 1, "info": 2}.get(issue.get("severity", "warning"), 1)
    confidence_rank = {"high": 0, "medium": 1, "unknown_static": 2, "low": 3}.get(issue.get("confidence", "medium"), 1)
    return (severity_rank, confidence_rank, issue.get("type", ""))

from __future__ import annotations

from pathlib import Path

import click

from manim_cli.dsl.knowledge import retrieve_top_k, write_failure_memory, write_policy_candidate_from_reviewed_failure
from manim_cli.dsl.validators import parse_and_validate_scene_data
from manim_cli.jsonio import load_json, print_json
from manim_cli.qa.engine import run_qa


@click.group("knowledge")
def knowledge_group() -> None:
    """Inspect local knowledge, policy, and reviewed failure memory."""


@knowledge_group.command("retrieve")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--base-dir", type=click.Path(exists=True, file_okay=False, path_type=Path), default=None, help="Directory containing knowledge/, policies/, and failures/reviewed/.")
@click.option("--top-k", type=int, default=3, show_default=True)
def knowledge_retrieve_cmd(scene_json: Path, base_dir: Path | None, top_k: int) -> None:
    data = load_json(scene_json)
    parsed = parse_and_validate_scene_data(data, file=str(scene_json), base_dir=scene_json.parent, quality_gate="off")
    if not parsed.diagnostic.get("ok") or parsed.scene is None:
        print_json(parsed.diagnostic)
        raise SystemExit(1)
    root = base_dir or scene_json.parent
    print_json({"ok": True, "phase": "knowledge_retrieve", "scene": str(scene_json), "base_dir": str(root), "matches": retrieve_top_k(parsed.scene, root, top_k=top_k)})


@knowledge_group.command("record-failure")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None, help="Directory where failures/inbox/ should be written.")
@click.option("--profile", type=click.Choice(["relaxed", "strict", "final"]), default="strict", show_default=True)
@click.option("--symptom", type=str, default=None, help="Short human-readable symptom summary.")
def knowledge_record_failure_cmd(scene_json: Path, base_dir: Path | None, profile: str, symptom: str | None) -> None:
    data = load_json(scene_json)
    parsed = parse_and_validate_scene_data(data, file=str(scene_json), base_dir=scene_json.parent, quality_gate="off")
    if not parsed.diagnostic.get("ok") or parsed.scene is None:
        print_json(parsed.diagnostic)
        raise SystemExit(1)
    qa = run_qa(scene_json, profile=profile)
    issues = qa.get("issues", [])
    if not issues:
        print_json({"ok": False, "phase": "knowledge_record_failure", "error_type": "no_qa_issues", "message": "QA produced no issues to record."})
        raise SystemExit(1)
    root = base_dir or scene_json.parent
    path = write_failure_memory(root, parsed.scene, issues, symptom=symptom)
    print_json({"ok": True, "phase": "knowledge_record_failure", "scene": str(scene_json), "base_dir": str(root), "failure_memory": str(path), "issue_count": len(issues)})


@knowledge_group.command("promote-policy")
@click.argument("reviewed_failure_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None, help="Directory where policies/ should be written.")
@click.option("--policy-type", type=click.Choice(["diagnostic", "enforce", "fallback", "block", "allow"]), default="diagnostic", show_default=True)
def knowledge_promote_policy_cmd(reviewed_failure_json: Path, base_dir: Path | None, policy_type: str) -> None:
    if "reviewed" not in reviewed_failure_json.parts or "failures" not in reviewed_failure_json.parts:
        print_json(
            {
                "ok": False,
                "phase": "knowledge_promote_policy",
                "error_type": "unreviewed_failure",
                "message": "Only failures/reviewed/*.json can be promoted to policy.",
                "location": {"file": str(reviewed_failure_json)},
            }
        )
        raise SystemExit(1)
    root = base_dir or reviewed_failure_json.parents[2]
    path = write_policy_candidate_from_reviewed_failure(reviewed_failure_json, root / "policies", policy_type=policy_type)
    print_json({"ok": True, "phase": "knowledge_promote_policy", "reviewed_failure": str(reviewed_failure_json), "policy": str(path), "policy_type": policy_type})

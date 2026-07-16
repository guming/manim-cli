from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional

import click

from manim_cli.commands.knowledge_cmd import knowledge_promote_policy_cmd, knowledge_record_failure_cmd
from manim_cli.dsl.knowledge import (
    load_document,
    memory_document_id,
    memory_document_paths,
    rebuild_memory_index,
    scan_documents_from_root,
    write_memory_document,
)
from manim_cli.jsonio import print_json


@click.group("memory")
def memory_group() -> None:
    """Manage project or user layout memory explicitly."""


def resolve_memory_root(scope: str, base_dir: Optional[Path]) -> Path:
    if scope == "user":
        if base_dir is not None:
            raise click.UsageError("--base-dir cannot be combined with --scope user")
        return Path.home() / ".manim-cli" / "layout_memory"
    return base_dir or Path.cwd() / ".manim-cli" / "layout_memory"


def source_documents(root: Path, include_inbox: bool = True) -> List[Dict[str, Any]]:
    documents = scan_documents_from_root(root, "project", {}, limit=100_000) if root.exists() else []
    if include_inbox:
        inbox = root / "failures" / "inbox"
        if inbox.exists():
            for path in memory_document_paths(inbox):
                document = load_document(path, "failure_memory")
                document["_scope"] = "project"
                document["_state"] = "inbox"
                documents.append(document)
    for document in documents:
        if document["document_type"] == "failure_memory" and "_state" not in document:
            document["_state"] = "reviewed"
    return documents


def kind_matches(document: Dict[str, Any], kind: str) -> bool:
    expected = {"all": None, "knowledge": "knowledge", "policies": "policy", "failures": "failure_memory"}[kind]
    return expected is None or document.get("document_type") == expected


def public_document_summary(document: Dict[str, Any]) -> Dict[str, Any]:
    doc_type = str(document["document_type"])
    summary = {
        "id": memory_document_id(document, doc_type),
        "document_type": doc_type,
        "path": document.get("_path"),
    }
    for key in ("status", "type", "priority", "severity", "confidence", "_state"):
        if key in document:
            summary["state" if key == "_state" else key] = document[key]
    return summary


@memory_group.command("list")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--kind", type=click.Choice(["all", "knowledge", "policies", "failures"]), default="all", show_default=True)
def memory_list_cmd(scope: str, base_dir: Optional[Path], kind: str) -> None:
    root = resolve_memory_root(scope, base_dir)
    items = [public_document_summary(document) for document in source_documents(root) if kind_matches(document, kind)]
    items.sort(key=lambda item: (item["document_type"], item["id"]))
    print_json({"ok": True, "phase": "memory_list", "scope": scope, "base_dir": str(root), "items": items, "count": len(items)})


@memory_group.command("inspect")
@click.argument("document_id")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
def memory_inspect_cmd(document_id: str, scope: str, base_dir: Optional[Path]) -> None:
    root = resolve_memory_root(scope, base_dir)
    matches = [document for document in source_documents(root) if memory_document_id(document, str(document["document_type"])) == document_id]
    if not matches:
        memory_command_error("memory_inspect", "memory_not_found", f"Memory document {document_id!r} was not found.", root)
    if len(matches) > 1:
        memory_command_error("memory_inspect", "ambiguous_memory_id", f"Memory ID {document_id!r} exists in multiple document kinds.", root)
    document = {key: value for key, value in matches[0].items() if not key.startswith("_")}
    print_json({"ok": True, "phase": "memory_inspect", "scope": scope, "base_dir": str(root), "document": document, "path": matches[0]["_path"]})


@memory_group.command("review")
@click.argument("failure_id")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
def memory_review_cmd(failure_id: str, scope: str, base_dir: Optional[Path]) -> None:
    root = resolve_memory_root(scope, base_dir)
    inbox = root / "failures" / "inbox"
    matches = find_documents(inbox, "failure_memory", failure_id)
    if not matches:
        memory_command_error("memory_review", "failure_not_found", f"Inbox failure {failure_id!r} was not found.", root)
    if len(matches) > 1:
        memory_command_error("memory_review", "ambiguous_failure_id", f"Inbox failure ID {failure_id!r} is duplicated.", root)
    source, _ = matches[0]
    reviewed = root / "failures" / "reviewed"
    reviewed.mkdir(parents=True, exist_ok=True)
    destination = reviewed / source.name
    if destination.exists():
        memory_command_error("memory_review", "reviewed_failure_exists", f"Reviewed failure already exists at {destination}.", root)
    os.replace(source, destination)
    rebuild_memory_index(root)
    print_json({"ok": True, "phase": "memory_review", "scope": scope, "failure_id": failure_id, "from": str(source), "reviewed_failure": str(destination)})


def find_documents(folder: Path, doc_type: str, document_id: str) -> List[tuple[Path, Dict[str, Any]]]:
    if not folder.exists():
        return []
    matches = []
    for path in memory_document_paths(folder):
        document = load_document(path, doc_type)
        if memory_document_id(document, doc_type) == document_id:
            matches.append((path, document))
    return matches


def update_policy_status(policy_id: str, status: str, scope: str, base_dir: Optional[Path]) -> None:
    root = resolve_memory_root(scope, base_dir)
    matches = find_documents(root / "policies", "policy", policy_id)
    if not matches:
        memory_command_error("memory_policy_status", "policy_not_found", f"Policy {policy_id!r} was not found.", root)
    if len(matches) > 1:
        memory_command_error("memory_policy_status", "ambiguous_policy_id", f"Policy ID {policy_id!r} is duplicated.", root)
    path, document = matches[0]
    document = {key: value for key, value in document.items() if not key.startswith("_")}
    previous = document.get("status", "active")
    document["status"] = status
    write_memory_document(path, document)
    rebuild_memory_index(root)
    print_json({"ok": True, "phase": "memory_policy_status", "scope": scope, "policy_id": policy_id, "previous_status": previous, "status": status, "path": str(path)})


@memory_group.command("activate")
@click.argument("policy_id")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
def memory_activate_cmd(policy_id: str, scope: str, base_dir: Optional[Path]) -> None:
    update_policy_status(policy_id, "active", scope, base_dir)


@memory_group.command("disable")
@click.argument("policy_id")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
def memory_disable_cmd(policy_id: str, scope: str, base_dir: Optional[Path]) -> None:
    update_policy_status(policy_id, "disabled", scope, base_dir)


@memory_group.command("rebuild-index")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
def memory_rebuild_index_cmd(scope: str, base_dir: Optional[Path]) -> None:
    root = resolve_memory_root(scope, base_dir)
    path = rebuild_memory_index(root)
    print_json({"ok": True, "phase": "memory_rebuild_index", "scope": scope, "base_dir": str(root), "index": str(path)})


@memory_group.command("clean")
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--inbox", is_flag=True, required=True, help="Limit cleanup to failures/inbox.")
@click.option("--older-than", type=click.IntRange(min=0), required=True, metavar="DAYS")
@click.option("--apply", "apply_changes", is_flag=True, help="Delete matched files. Without this flag the command is a dry run.")
def memory_clean_cmd(scope: str, base_dir: Optional[Path], inbox: bool, older_than: int, apply_changes: bool) -> None:
    root = resolve_memory_root(scope, base_dir)
    folder = root / "failures" / "inbox"
    cutoff = time.time() - older_than * 86400
    candidates = [path for path in memory_document_paths(folder) if path.stat().st_mtime <= cutoff] if folder.exists() else []
    if apply_changes:
        for path in candidates:
            path.unlink()
    print_json(
        {
            "ok": True,
            "phase": "memory_clean",
            "scope": scope,
            "base_dir": str(root),
            "dry_run": not apply_changes,
            "older_than_days": older_than,
            "matched": [str(path) for path in candidates],
            "deleted_count": len(candidates) if apply_changes else 0,
        }
    )


def memory_command_error(phase: str, error_type: str, message: str, root: Path) -> None:
    print_json({"ok": False, "phase": phase, "error_type": error_type, "message": message, "base_dir": str(root)})
    raise SystemExit(1)


@memory_group.command("record")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--profile", type=click.Choice(["relaxed", "strict", "final"]), default="strict", show_default=True)
@click.option("--symptom", type=str, default=None)
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="json", show_default=True)
def memory_record_cmd(
    scene_json: Path,
    scope: str,
    base_dir: Optional[Path],
    profile: str,
    symptom: Optional[str],
    output_format: str,
) -> None:
    root = resolve_memory_root(scope, base_dir)
    knowledge_record_failure_cmd.callback(scene_json, root, profile, symptom, output_format)  # type: ignore[misc]


@memory_group.command("promote")
@click.argument("reviewed_failure", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scope", type=click.Choice(["project", "user"]), required=True)
@click.option("--base-dir", type=click.Path(file_okay=False, path_type=Path), default=None)
@click.option("--policy-type", type=click.Choice(["diagnostic", "enforce", "fallback", "block", "allow"]), default="diagnostic", show_default=True)
@click.option("--format", "output_format", type=click.Choice(["json", "yaml"]), default="json", show_default=True)
def memory_promote_cmd(
    reviewed_failure: Path,
    scope: str,
    base_dir: Optional[Path],
    policy_type: str,
    output_format: str,
) -> None:
    root = resolve_memory_root(scope, base_dir)
    knowledge_promote_policy_cmd.callback(reviewed_failure, root, policy_type, output_format)  # type: ignore[misc]

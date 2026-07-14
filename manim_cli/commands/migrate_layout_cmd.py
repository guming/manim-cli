from __future__ import annotations

import os
from pathlib import Path

import click

from manim_cli.dsl.templates import migrate_scene_layout_data
from manim_cli.dsl.validators import validate_scene_data
from manim_cli.jsonio import error_result, load_json, print_json, write_json


@click.command("migrate-layout")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--to-version", type=click.Choice(["1.1"]), default="1.1", show_default=True)
@click.option("--out", "out_path", type=click.Path(path_type=Path), default=None, help="Write migrated scene JSON to this path. Omit to print JSON.")
def migrate_layout_cmd(scene_json: Path, to_version: str, out_path: Path | None) -> None:
    data = load_json(scene_json)
    if not isinstance(data, dict):
        print_json(error_result("migrate-layout", "invalid_type", "scene JSON must be an object", location={"file": str(scene_json)}))
        raise SystemExit(1)
    if data.get("version") != "1.0":
        print_json(
            error_result(
                "migrate-layout",
                "unsupported_version",
                "migrate-layout currently accepts only version 1.0 source scenes",
                location={"file": str(scene_json), "path": "$.version"},
                details={"version": data.get("version")},
            )
        )
        raise SystemExit(1)
    migrated = migrate_scene_layout_data(data, to_version=to_version)
    if out_path:
        migrated = rewrite_relative_refs(migrated, source_base=scene_json.parent, out_base=out_path.parent)
    validation_base = out_path.parent if out_path else scene_json.parent
    validation = validate_scene_data(migrated, file=str(out_path or scene_json), base_dir=validation_base)
    if not validation.get("ok"):
        print_json(validation)
        raise SystemExit(1)
    if out_path:
        write_json(out_path, migrated)
        print_json({"ok": True, "phase": "migrate-layout", "source": str(scene_json), "out": str(out_path), "version": to_version})
        return
    print_json(migrated)


def rewrite_relative_refs(data: dict, source_base: Path, out_base: Path) -> dict:
    rewritten = dict(data)
    for key in ("plan_ref", "storyboard_ref"):
        value = rewritten.get(key)
        if not value:
            continue
        ref_path = Path(value)
        if ref_path.is_absolute():
            continue
        absolute_ref = (source_base / ref_path).resolve()
        rewritten[key] = os.path.relpath(absolute_ref, out_base.resolve())
    return rewritten

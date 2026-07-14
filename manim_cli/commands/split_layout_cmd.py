from __future__ import annotations

from pathlib import Path

import click

from manim_cli.dsl.splitting import apply_first_storyboard_split, storyboard_split_plans
from manim_cli.dsl.validators import parse_and_validate_scene_data, validate_scene_data
from manim_cli.jsonio import error_result, load_json, print_json, write_json


@click.command("split-layout")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "out_path", type=click.Path(path_type=Path), required=True, help="Write split scene JSON to this path.")
def split_layout_cmd(scene_json: Path, out_path: Path) -> None:
    data = load_json(scene_json)
    if not isinstance(data, dict):
        print_json(error_result("split-layout", "invalid_type", "scene JSON must be an object", location={"file": str(scene_json)}))
        raise SystemExit(1)
    parsed = parse_and_validate_scene_data(data, file=str(scene_json), base_dir=scene_json.parent, quality_gate="off")
    if not parsed.diagnostic.get("ok") or parsed.scene is None:
        print_json(parsed.diagnostic)
        raise SystemExit(1)
    plans = storyboard_split_plans(parsed.scene)
    split_data = apply_first_storyboard_split(data, plans)
    if split_data is None:
        print_json(
            error_result(
                "split-layout",
                "no_applicable_split",
                "No applicable storyboard split plan was found for this scene.",
                location={"file": str(scene_json)},
                details={"plans": plans},
            )
        )
        raise SystemExit(1)
    validation = validate_scene_data(split_data, file=str(out_path), base_dir=scene_json.parent)
    if not validation.get("ok"):
        print_json(validation)
        raise SystemExit(1)
    write_json(out_path, split_data)
    print_json({"ok": True, "phase": "split-layout", "source": str(scene_json), "out": str(out_path), "applied_plan": plans[0]})

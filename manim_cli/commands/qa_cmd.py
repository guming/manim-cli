from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import load_json, print_json
from manim_cli.qa.engine import run_qa


@click.command("qa")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--profile", type=click.Choice(["relaxed", "strict", "final"]), default="relaxed", show_default=True)
@click.option("--plan", "plan_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--storyboard", "storyboard_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=None)
@click.option("--repair-context", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
def qa_cmd(scene_json: Path, profile: str, plan_path: Path | None, storyboard_path: Path | None, out_dir: Path | None, repair_context: Path | None) -> None:
    context = load_json(repair_context) if repair_context else None
    print_json(run_qa(scene_json, profile=profile, plan_path=plan_path, storyboard_path=storyboard_path, out_dir=out_dir, repair_context=context))

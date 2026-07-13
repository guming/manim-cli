from __future__ import annotations

from pathlib import Path

import click

from manim_cli.dsl.validators import validate_scene_file
from manim_cli.jsonio import print_json


@click.command("validate")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--quality-gate", type=click.Choice(["off", "relaxed", "strict", "final"]), default="off", show_default=True)
def validate_cmd(scene_json: Path, quality_gate: str) -> None:
    print_json(validate_scene_file(scene_json, quality_gate=quality_gate))

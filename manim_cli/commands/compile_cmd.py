from __future__ import annotations

from pathlib import Path

import click

from manim_cli.dsl.compiler import compile_scene_file
from manim_cli.jsonio import print_json


@click.command("compile")
@click.argument("scene_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("generated"), show_default=True)
@click.option("--profile", type=click.Choice(["strict", "fast", "preview", "final", "debug"]), default="strict", show_default=True)
@click.option("--no-cache", is_flag=True, help="Disable compile cache reuse.")
def compile_cmd(scene_json: Path, out_dir: Path, profile: str, no_cache: bool) -> None:
    print_json(compile_scene_file(scene_json, out_dir, profile=profile, use_cache=not no_cache))

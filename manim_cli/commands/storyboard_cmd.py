from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import print_json
from manim_cli.planning.validators import validate_storyboard_file


@click.group("storyboard")
def storyboard_group() -> None:
    """Storyboard commands."""


@storyboard_group.command("validate")
@click.argument("storyboard_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def storyboard_validate(storyboard_json: Path) -> None:
    print_json(validate_storyboard_file(storyboard_json))


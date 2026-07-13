from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import print_json
from manim_cli.regression.manifest import run_regression_dir


@click.group("regression")
def regression_group() -> None:
    """Run regression scene suites."""


@regression_group.command("run")
@click.argument("fixtures_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--out", "out_dir", type=click.Path(path_type=Path), default=Path("regression-out"), show_default=True)
@click.option("--render", "render", is_flag=True, help="Reserve render-enabled runs; current regression remains no-render by default.")
def regression_run_cmd(fixtures_dir: Path, out_dir: Path, render: bool) -> None:
    print_json(run_regression_dir(fixtures_dir, out_dir, render=render))

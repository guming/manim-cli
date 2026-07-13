from __future__ import annotations

from pathlib import Path
from typing import Optional

import click

from manim_cli.jsonio import load_json, print_json
from manim_cli.render.diagnose import diagnose_payload


@click.command("diagnose")
@click.argument("diagnostic_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--source-map", "source_map", type=click.Path(path_type=Path), default=None)
def diagnose_cmd(diagnostic_json: Path, source_map: Optional[Path]) -> None:
    print_json(diagnose_payload(load_json(diagnostic_json), source_map))

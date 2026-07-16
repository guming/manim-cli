from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import print_json
from manim_cli.render.runner import render_target


@click.command("render")
@click.argument("target", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--quality", type=click.Choice(["draft", "preview", "final", "low", "high"]), default="low", show_default=True)
@click.option("--output", type=click.Path(path_type=Path), default=Path("renders/preview.mp4"), show_default=True)
@click.option("--qa", "qa_gate", is_flag=True, help="Run static QA before rendering scene.json inputs.")
@click.option("--qa-profile", type=click.Choice(["relaxed", "strict", "final"]), default="strict", show_default=True)
@click.option("--pacing", "pacing_profile", type=click.Choice(["preserve", "teaching", "accelerated"]), default="teaching", show_default=True)
@click.option("--pacing-qa/--no-pacing-qa", default=None, help="Enforce post-render pacing QA (enabled by default for final/high).")
def render_cmd(target: Path, quality: str, output: Path, qa_gate: bool, qa_profile: str, pacing_profile: str, pacing_qa: bool | None) -> None:
    print_json(
        render_target(
            target,
            quality,
            output,
            qa_gate=qa_gate,
            qa_profile=qa_profile,
            pacing_profile=pacing_profile,
            pacing_qa=pacing_qa,
        )
    )

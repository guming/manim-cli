from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import print_json
from manim_cli.qa.eval import run_qa_eval


@click.command("qa-eval")
@click.argument("eval_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--allow-false-positives", is_flag=True, default=False, help="Don't fail on unexpected issues (FP).")
def qa_eval_cmd(eval_dir: Path, allow_false_positives: bool) -> None:
    print_json(run_qa_eval(eval_dir, fail_on_false_positive=not allow_false_positives))

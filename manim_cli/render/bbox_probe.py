from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

from manim_cli.dsl.layout import BBox
from manim_cli.dsl.models import SceneDef

ProbeStatus = Literal["measured", "unavailable"]

_PT_TO_MANIM = 0.0015


@dataclass(frozen=True)
class BBoxProbeResult:
    status: ProbeStatus
    bbox: BBox | None
    method: str
    message: str = ""


def latex_available() -> bool:
    return shutil.which("latex") is not None


def dvisvgm_available() -> bool:
    return shutil.which("dvisvgm") is not None


def probe_available() -> bool:
    return latex_available() and dvisvgm_available() and _probe_smoke_available()


def probe_diagnostic() -> Dict[str, object]:
    missing: List[str] = []
    if not latex_available():
        missing.append("latex")
    if not dvisvgm_available():
        missing.append("dvisvgm")
    if missing:
        return {"ready": False, "method": "dependency_missing", "message": f"LaTeX bbox probe requires: {', '.join(missing)}"}
    try:
        width, height = _compile_and_measure("x")
    except Exception as exc:
        return {"ready": False, "method": "compilation_failed", "message": str(exc)}
    return {"ready": width > 0 and height > 0, "method": "latex_dvisvgm", "message": f"probe measured {width:.1f}pt x {height:.1f}pt"}


@lru_cache(maxsize=1)
def _probe_smoke_available() -> bool:
    if not latex_available() or not dvisvgm_available():
        return False
    try:
        width, height = _compile_and_measure("x")
    except Exception:
        return False
    return width > 0 and height > 0


def probe_tex_bbox(tex: str, font_size: int = 48) -> BBoxProbeResult:
    if not probe_available():
        missing: List[str] = []
        if not latex_available():
            missing.append("latex")
        if not dvisvgm_available():
            missing.append("dvisvgm")
        if missing:
            return BBoxProbeResult(status="unavailable", bbox=None, method="dependency_missing", message=f"LaTeX bbox probe requires: {', '.join(missing)}")
        return BBoxProbeResult(status="unavailable", bbox=None, method="compilation_failed", message="LaTeX bbox probe smoke test failed.")
    try:
        pt_width, pt_height = _compile_and_measure(tex)
    except subprocess.TimeoutExpired:
        return BBoxProbeResult(status="unavailable", bbox=None, method="timeout", message="LaTeX compilation timed out (>30s).")
    except Exception as exc:
        return BBoxProbeResult(status="unavailable", bbox=None, method="compilation_failed", message=str(exc))
    manim_w = pt_width * font_size * _PT_TO_MANIM
    manim_h = pt_height * font_size * _PT_TO_MANIM
    return BBoxProbeResult(
        status="measured",
        bbox=BBox(-manim_w / 2, -manim_h / 2, manim_w / 2, manim_h / 2),
        method="latex_dvisvgm",
        message=f"Measured via latex+dvisvgm: {pt_width:.1f}pt x {pt_height:.1f}pt",
    )


def probe_scene_tex_bboxes(scene: SceneDef, font_size: int = 48) -> Dict[str, BBoxProbeResult]:
    results: Dict[str, BBoxProbeResult] = {}
    for mob in scene.mobjects:
        if mob.type in ("Tex", "MathTex"):
            tex = str(mob.args.get("tex", ""))
            if tex:
                results[mob.id] = probe_tex_bbox(tex, font_size=int(mob.args.get("font_size", font_size)))
    return results


def _compile_and_measure(tex: str) -> Tuple[float, float]:
    with tempfile.TemporaryDirectory(prefix="manim_cli_bbox_") as tmpdir:
        work = Path(tmpdir)
        tex_file = work / "probe.tex"
        tex_file.write_text("\\documentclass{standalone}\n\\begin{document}\n$" + tex + "$\n\\end{document}\n", encoding="utf-8")
        compile_result = subprocess.run(
            ["latex", "-interaction=batchmode", "-halt-on-error", "-output-directory", str(work), str(tex_file)],
            capture_output=True,
            timeout=30,
            cwd=str(work),
        )
        dvi_file = work / "probe.dvi"
        if compile_result.returncode != 0 or not dvi_file.exists():
            raise RuntimeError("LaTeX compilation failed or produced no DVI")
        svg_result = subprocess.run(
            ["dvisvgm", "--no-fonts", "--exact-bbox", "-o-", str(dvi_file)],
            capture_output=True,
            timeout=15,
            cwd=str(work),
        )
        if svg_result.returncode != 0:
            stderr = svg_result.stderr.decode("utf-8", errors="replace").strip()
            lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            relevant = [
                line
                for line in lines
                if "error" in line.lower() or "none of the default map files" in line.lower() or "not found" in line.lower()
            ]
            detail = "; ".join((relevant or lines)[-6:]) if lines else "no stderr"
            raise RuntimeError(f"dvisvgm conversion failed: {detail}")
        svg_content = svg_result.stdout.decode("utf-8", errors="replace")
        return _parse_svg_dimensions(svg_content)


def _parse_svg_dimensions(svg: str) -> Tuple[float, float]:
    width_match = re.search(r'width="([\d.]+)', svg)
    height_match = re.search(r'height="([\d.]+)', svg)
    width_pt = float(width_match.group(1)) if width_match else 0.0
    height_pt = float(height_match.group(1)) if height_match else 0.0
    return (width_pt, height_pt)

from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
from typing import Any, Dict, List, Literal

from manim_cli.dsl.layout import BBoxEstimate, estimate_bboxes
from manim_cli.dsl.models import SceneDef
from manim_cli.dsl.validators import parse_scene_file
from manim_cli.jsonio import Diagnostic, error_result, ok_result
from manim_cli.render.bbox_probe import BBoxProbeResult, probe_available, probe_diagnostic, probe_scene_tex_bboxes
from manim_cli.render.runner import render_target


SmokeExpectation = Literal["measured_safe", "measured_contradiction"]


def render_toolchain_status() -> Dict[str, Any]:
    components = {
        "manim_executable": shutil.which("manim"),
        "manim_python": importlib.util.find_spec("manim") is not None,
        "latex_executable": shutil.which("latex"),
        "dvisvgm_executable": shutil.which("dvisvgm"),
    }
    reasons: List[str] = []
    if not components["manim_executable"]:
        reasons.append("manim executable is missing")
    if not components["manim_python"]:
        reasons.append("manim Python package is missing")
    if not components["latex_executable"]:
        reasons.append("latex executable is missing")
    if not components["dvisvgm_executable"]:
        reasons.append("dvisvgm executable is missing")
    probe = None
    if not reasons and not probe_available():
        probe = probe_diagnostic()
        reasons.append(f"TeX bbox probe is unavailable: {probe['method']}: {probe['message']}")
    return {
        "ready": not reasons,
        "components": components,
        "skip_reasons": reasons,
        "probe": probe,
    }


def measured_formula_caption_findings(
    scene: SceneDef,
    tex_probe_results: Dict[str, BBoxProbeResult],
    min_gap: float = 0.35,
) -> List[Dict[str, Any]]:
    boxes = estimate_bboxes(scene, tex_probe_results=tex_probe_results)
    formulas = [mob for mob in scene.mobjects if (mob.layout_role or "").startswith("formula.") and mob.id in boxes]
    captions = [mob for mob in scene.mobjects if (mob.layout_role or "").startswith("caption.") and mob.id in boxes]
    findings: List[Dict[str, Any]] = []
    for formula in formulas:
        for caption in captions:
            formula_box = boxes[formula.id]
            caption_box = boxes[caption.id]
            if not horizontal_ranges_overlap(formula_box, caption_box):
                continue
            gap = vertical_gap(formula_box, caption_box)
            if gap >= min_gap:
                continue
            findings.append(
                {
                    "type": "layout_formula_caption_overlap",
                    "objects": [formula.id, caption.id],
                    "measured_gap": round(gap, 4),
                    "min_gap": min_gap,
                    "bbox_sources": {formula.id: formula_box.method, caption.id: caption_box.method},
                    "message": f"Measured formula-caption gap {gap:.3f} is below {min_gap:.3f}.",
                }
            )
    return findings


def run_measured_layout_render_smoke(
    scene_path: Path,
    output: Path,
    expectation: SmokeExpectation,
) -> Diagnostic:
    status = render_toolchain_status()
    if not status["ready"]:
        return ok_result(
            "render_smoke",
            render_skipped=True,
            skip_reason="; ".join(status["skip_reasons"]),
            toolchain=status,
            expectation=expectation,
        )
    scene = parse_scene_file(scene_path)
    static_findings = measured_formula_caption_findings(scene, {})
    probe_results = probe_scene_tex_bboxes(scene)
    findings = measured_formula_caption_findings(scene, probe_results)
    if expectation == "measured_contradiction":
        if static_findings:
            return error_result(
                "render_smoke",
                "contradiction_fixture_not_static_safe",
                "Contradiction fixture is already unsafe under static layout analysis.",
                details={"static_findings": static_findings, "toolchain": status},
            )
        if not findings:
            return error_result(
                "render_smoke",
                "expected_measured_contradiction_missing",
                "Measured layout did not contradict the static-safe fixture.",
                details={"findings": findings, "toolchain": status},
            )
        return ok_result(
            "render_smoke",
            render_skipped=True,
            skip_reason="measured contradiction blocked before render",
            expectation=expectation,
            findings=findings,
            static_findings=static_findings,
            toolchain=status,
        )
    if findings:
        return error_result(
            "render_smoke",
            "measured_safe_fixture_failed",
            "Measured-safe fixture produced a formula-caption finding.",
            details={"findings": findings, "toolchain": status},
        )
    rendered = render_target(scene_path, quality="draft", output=output, qa_gate=False)
    if not rendered.get("ok"):
        rendered["phase"] = "render_smoke"
        rendered["expectation"] = expectation
        rendered["toolchain"] = status
        return rendered
    return ok_result(
        "render_smoke",
        render_skipped=False,
        expectation=expectation,
        findings=[],
        static_findings=static_findings,
        output=rendered.get("output"),
        render=rendered,
        toolchain=status,
    )


def horizontal_ranges_overlap(left: BBoxEstimate, right: BBoxEstimate) -> bool:
    return left.bbox.left < right.bbox.right and left.bbox.right > right.bbox.left


def vertical_gap(left: BBoxEstimate, right: BBoxEstimate) -> float:
    left_box = left.bbox
    right_box = right.bbox
    if left_box.bottom >= right_box.top:
        return left_box.bottom - right_box.top
    if right_box.bottom >= left_box.top:
        return right_box.bottom - left_box.top
    return -min(left_box.top, right_box.top) + max(left_box.bottom, right_box.bottom)

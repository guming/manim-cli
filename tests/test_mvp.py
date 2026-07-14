import json
import math
from pathlib import Path

from click.testing import CliRunner

from manim_cli.cli import main
from manim_cli.dsl.analysis import analyze_scene
from manim_cli.dsl.compiler import compile_scene_file
from manim_cli.dsl.layout import BBox, estimate_bbox, layout_warnings, overlaps, slot_region
from manim_cli.dsl.models import RESERVED_FUTURE_MOBJECT_FIELDS, RESERVED_FUTURE_SCENE_FIELDS, SCENE_SCHEMA_VERSION, SUPPORTED_SCENE_VERSIONS
from manim_cli.dsl.names import safe_var_name
from manim_cli.dsl.timeline import build_timeline
from manim_cli.dsl.validators import parse_scene_file, validate_scene_data, validate_scene_file
from manim_cli.jsonio import load_json
from manim_cli.qa.eval import run_qa_eval
from manim_cli.qa.engine import run_qa
from manim_cli.regression.manifest import run_regression_dir
from manim_cli.render.diagnose import map_line
from manim_cli.render.visual_qa import analyze_keyframe, analyze_pixels
from manim_cli.source_map import lookup_source_map


FIXTURES = Path(__file__).parent / "fixtures"


def test_fixtures_validate():
    for fixture in FIXTURES.glob("*.json"):
        result = validate_scene_file(fixture)
        assert result["ok"], result


def test_unknown_field_rejected():
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"][0]["args"]["unknown"] = True
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "unknown_field"


def test_layout_fields_remain_rejected_in_schema_v1():
    assert SCENE_SCHEMA_VERSION == "1.1"
    assert SUPPORTED_SCENE_VERSIONS == ("1.0", "1.1")
    assert "layout_template" in RESERVED_FUTURE_SCENE_FIELDS
    assert "layout_role" in RESERVED_FUTURE_MOBJECT_FIELDS
    data = load_json(FIXTURES / "simple_transform.json")
    data["layout_template"] = "plot_with_bottom_formula"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "unknown_field"
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"][0]["layout_role"] = "plot.primary"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "unknown_field"


def test_schema_v11_accepts_explicit_layout_template_and_role():
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    data["mobjects"][0]["layout_role"] = "formula.primary"
    data["mobjects"][0]["type"] = "Tex"
    data["mobjects"][0]["args"] = {"tex": "x^2", "font_size": 48}
    result = validate_scene_data(data)
    assert result["ok"], result


def test_schema_v11_accepts_plot_full_template():
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_full"
    data["mobjects"][0]["layout_role"] = "plot.primary"
    result = validate_scene_data(data)
    assert result["ok"], result


def test_schema_v11_accepts_fallback_templates():
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    for template in ("plot_with_side_formula", "plot_then_formula", "formula_then_caption"):
        data["layout_template"] = template
        result = validate_scene_data(data)
        assert result["ok"], result


def test_schema_v11_rejects_invalid_layout_template_and_role():
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "unknown_template"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "invalid_enum"

    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["mobjects"][0]["layout_role"] = "plot.fake"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "invalid_enum"


def test_unsupported_scene_version_rejected():
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "2.0"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "invalid_enum"


def test_graph_rejected():
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"][0]["type"] = "Graph"
    result = validate_scene_data(data)
    assert not result["ok"]
    assert result["error_type"] == "unsupported_type"


def test_multi_target_rejected():
    data = load_json(FIXTURES / "simple_transform.json")
    data["steps"][0]["actions"][0]["target"] = ["circle", "square"]
    result = validate_scene_data(data)
    assert not result["ok"]


def test_safe_var_name_stable():
    used = set()
    assert safe_var_name("main-title", used) == "mobj_main_title"
    assert safe_var_name("main title", used) == "mobj_main_title_2"


def test_compile_fixtures(tmp_path):
    for fixture in FIXTURES.glob("*.json"):
        out = tmp_path / fixture.stem
        result = compile_scene_file(fixture, out)
        assert result["ok"], result
        assert (out / "scene.py").exists()
        assert (out / "scene.py.map.json").exists()


def test_axes_emit_uses_manim_community_length_args(tmp_path):
    out = tmp_path / "vector"
    result = compile_scene_file(FIXTURES / "vector_intro.json", out)
    assert result["ok"], result
    source = (out / "scene.py").read_text(encoding="utf-8")
    axes_line = next(line for line in source.splitlines() if " = Axes(" in line)
    assert "x_length=" in axes_line
    assert "y_length=" in axes_line
    assert "width=" not in axes_line
    assert "height=" not in axes_line


def test_compile_layout_fits_tex_to_slot_height(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": r"f'(a)=\lim_{h\to0}\frac{f(a+h)-f(a)}{h}", "font_size": 120},
            "layout": {"slot": "bottom_formula"},
        }
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    changes = result["layout_changes"]
    fit_change = next(change for change in changes if change["object"] == "formula" and change["change"] == "fit_to_region")
    assert fit_change["to"]["height"] > 0
    assert "height" in fit_change["fit_dimensions"]
    assert fit_change["height_scale"] < 1
    assert fit_change["region"]["top"] > fit_change["region"]["bottom"]
    assert any(warning["type"] == "layout_material_scale_down" and warning["object"] == "formula" for warning in result["warnings"])
    source = (tmp_path / "out" / "scene.py").read_text(encoding="utf-8")
    assert ".scale(" in source


def test_compile_v11_role_derives_layout_slot(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": "x^2", "font_size": 48},
            "layout_role": "formula.primary",
        }
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    assert any(change["change"] == "layout_template_selected" and change["layout_template"] == "plot_with_bottom_formula" for change in result["layout_changes"])
    placement = next(change for change in result["layout_changes"] if change.get("object") == "formula" and change["change"] == "layout_role_placement")
    assert placement["layout_role"] == "formula.primary"
    assert placement["actual_slot"] == "bottom_formula"
    source = (tmp_path / "out" / "scene.py").read_text(encoding="utf-8")
    assert "mobj_formula.move_to(np.array([0.0, -2.28, 0.0]))" in source


def test_compile_plot_full_role_maps_to_main(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_full"
    data["mobjects"] = [
        {
            "id": "plot_marker",
            "type": "Dot",
            "args": {"point": [0, 0, 0]},
            "layout_role": "plot.primary",
        }
    ]
    data["steps"] = [{"id": "s1", "name": "plot", "actions": [{"type": "add", "target": "plot_marker"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    placement = next(change for change in result["layout_changes"] if change.get("object") == "plot_marker" and change["change"] == "layout_role_placement")
    assert placement["layout_template"] == "plot_full"
    assert placement["actual_slot"] == "main"


def test_formula_overflow_selects_fallback_template(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": r"\frac{x}{y}", "font_size": 50},
            "layout_role": "formula.primary",
        },
        {
            "id": "caption",
            "type": "Text",
            "args": {"text": "caption", "font_size": 32},
            "layout_role": "caption.conclusion",
        },
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}, {"type": "write", "target": "caption"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)

    validation = validate_scene_data(data, quality_gate="relaxed")
    assert validation["ok"], validation
    assert any(warning["type"] == "layout_fallback_selected" and warning["to"] == "formula_then_caption" for warning in validation["warnings"])

    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    assert any(change["change"] == "layout_fallback_selected" and change["from"] == "plot_with_bottom_formula" and change["to"] == "formula_then_caption" for change in result["layout_changes"])
    placement = next(change for change in result["layout_changes"] if change.get("object") == "formula" and change["change"] == "layout_role_placement")
    assert placement["layout_template"] == "formula_then_caption"
    assert placement["actual_slot"] == "main"


def test_formula_overflow_all_fallbacks_emit_split_plan(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    very_long_formula = " + ".join([r"\frac{x_i}{y_i}"] * 30)
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": very_long_formula, "font_size": 90},
            "layout_role": "formula.primary",
        },
        {
            "id": "caption",
            "type": "Text",
            "args": {"text": "caption", "font_size": 32},
            "layout_role": "caption.conclusion",
        },
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}, {"type": "write", "target": "caption"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)

    validation = validate_scene_data(data, quality_gate="relaxed")
    assert validation["ok"], validation
    assert any(warning["type"] == "layout_template_fit_failed" and warning["object"] == "formula" for warning in validation["warnings"])
    split_warning = next(warning for warning in validation["warnings"] if warning["type"] == "storyboard_split_required")
    assert split_warning["step"] == "s1"
    assert split_warning["moved_object_ids"] == ["caption", "formula"]

    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    assert any(change["change"] == "layout_template_fit_failed" and change["object"] == "formula" for change in result["layout_changes"])
    split_change = next(change for change in result["layout_changes"] if change["change"] == "storyboard_split_plan")
    assert split_change["step"] == "s1"
    assert split_change["timing_policy"] == "preserve_original_step_duration_until_explicit_split"


def test_split_layout_cli_writes_split_scene_without_overwriting_source(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    very_long_formula = " + ".join([r"\frac{x_i}{y_i}"] * 30)
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": very_long_formula, "font_size": 90},
            "layout_role": "formula.primary",
        },
        {
            "id": "caption",
            "type": "Text",
            "args": {"text": "caption", "font_size": 32},
            "layout_role": "caption.conclusion",
        },
    ]
    data["steps"] = [
        {
            "id": "s1",
            "name": "formula",
            "actions": [{"type": "write", "target": "formula"}, {"type": "write", "target": "caption"}],
            "wait_after": 0.5,
        }
    ]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    original = scene_path.read_text(encoding="utf-8")
    out_path = tmp_path / "scene.split.json"

    result = CliRunner().invoke(main, ["split-layout", str(scene_path), "--out", str(out_path)])
    assert result.exit_code == 0, result.output
    assert scene_path.read_text(encoding="utf-8") == original
    split_data = load_json(out_path)
    assert len(split_data["steps"]) == 2
    assert [action["target"] for action in split_data["steps"][0]["actions"]] == ["formula"]
    assert [action["target"] for action in split_data["steps"][1]["actions"]] == ["caption"]
    assert split_data["steps"][1]["wait_after"] == 0.5
    validation = validate_scene_file(out_path)
    assert validation["ok"], validation
    compile_result = compile_scene_file(out_path, tmp_path / "compiled", use_cache=False)
    assert compile_result["ok"], compile_result


def test_local_policy_warning_and_knowledge_retrieval(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": r"f'(a)=\lim_{h\to0}\frac{f(a+h)-f(a)}{h}", "font_size": 48},
            "layout_role": "formula.primary",
        }
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}]}]
    write_json_text(tmp_path / "scene.json", data)
    (tmp_path / "policies").mkdir()
    write_json_text(
        tmp_path / "policies" / "tall_formula.json",
        {
            "policy_id": "tall_formula_bottom_region_safety",
            "type": "diagnostic",
            "when": {
                "layout_template": "plot_with_bottom_formula",
                "role": "formula.primary",
                "formula_contains_any": [r"\lim", r"\frac"],
            },
            "prompt_summary": "Tall formula in bottom region needs extra care.",
        },
    )
    (tmp_path / "knowledge").mkdir()
    write_json_text(
        tmp_path / "knowledge" / "derivative_geometry.json",
        {
            "id": "derivative_geometry",
            "description": "Derivative geometry scenes.",
            "match": {"formula_features": ["limit_difference_quotient"], "mobject_types": ["Tex"]},
            "required_roles": ["formula.primary"],
            "prompt_summary": "Prefer separated formula layout for derivative limits.",
        },
    )

    result = validate_scene_file(tmp_path / "scene.json", quality_gate="relaxed")
    assert result["ok"], result
    policy_warning = next(warning for warning in result["warnings"] if warning["type"] == "layout_memory_policy_applied")
    assert policy_warning["policy_id"] == "tall_formula_bottom_region_safety"
    qa = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert qa["ok"], qa
    assert any(issue["type"] == "layout_memory_policy_applied" for issue in qa["issues"])

    cli = CliRunner().invoke(main, ["knowledge", "retrieve", str(tmp_path / "scene.json"), "--base-dir", str(tmp_path), "--top-k", "2"])
    assert cli.exit_code == 0, cli.output
    payload = json.loads(cli.output)
    assert payload["ok"]
    assert any(match["document"].get("id") == "derivative_geometry" for match in payload["matches"])


def test_knowledge_record_failure_writes_inbox_without_retrieval(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)

    result = CliRunner().invoke(main, ["knowledge", "record-failure", str(scene_path), "--base-dir", str(tmp_path), "--profile", "strict", "--symptom", "overlapping circles"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    failure_path = Path(payload["failure_memory"])
    assert failure_path.exists()
    assert failure_path.parent == tmp_path / "failures" / "inbox"
    memory = load_json(failure_path)
    assert memory["symptom"] == "overlapping circles"
    assert memory["severity"] == "blocking"
    assert "layout_overlap" in memory["evidence"]["issue_types"]

    retrieve = CliRunner().invoke(main, ["knowledge", "retrieve", str(scene_path), "--base-dir", str(tmp_path), "--top-k", "5"])
    assert retrieve.exit_code == 0, retrieve.output
    retrieved = json.loads(retrieve.output)
    assert not any(match["document"].get("failure_id") == memory["failure_id"] for match in retrieved["matches"])


def test_knowledge_promote_reviewed_failure_to_policy(tmp_path):
    reviewed_dir = tmp_path / "failures" / "reviewed"
    inbox_dir = tmp_path / "failures" / "inbox"
    reviewed_dir.mkdir(parents=True)
    inbox_dir.mkdir(parents=True)
    failure = {
        "failure_id": "derivative_formula_caption_overlap_2026_07",
        "scene_type": "derivative_geometry",
        "symptom": "formula overlaps caption",
        "trigger": {
            "layout_template": "plot_with_bottom_formula",
            "visible_roles": ["formula.primary", "caption.conclusion"],
            "formula_features": ["limit_difference_quotient"],
        },
        "evidence": {"issue_types": ["layout_overlap"]},
        "severity": "blocking",
        "confidence": "high",
        "prompt_summary": "Tall derivative formula should avoid crowded bottom layout.",
    }
    reviewed_path = reviewed_dir / "failure.json"
    inbox_path = inbox_dir / "failure.json"
    write_json_text(reviewed_path, failure)
    write_json_text(inbox_path, failure)

    rejected = CliRunner().invoke(main, ["knowledge", "promote-policy", str(inbox_path), "--base-dir", str(tmp_path)])
    assert rejected.exit_code != 0
    assert "unreviewed_failure" in rejected.output

    promoted = CliRunner().invoke(main, ["knowledge", "promote-policy", str(reviewed_path), "--base-dir", str(tmp_path)])
    assert promoted.exit_code == 0, promoted.output
    payload = json.loads(promoted.output)
    policy_path = Path(payload["policy"])
    policy = load_json(policy_path)
    assert policy["policy_id"] == "policy_derivative_formula_caption_overlap_2026_07"
    assert policy["source_failure_id"] == failure["failure_id"]
    assert policy["when"]["formula_features_any"] == ["limit_difference_quotient"]

    scene = load_json(FIXTURES / "simple_transform.json")
    scene["version"] = "1.1"
    scene["layout_template"] = "plot_with_bottom_formula"
    scene["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": r"f'(a)=\lim_{h\to0}\frac{f(a+h)-f(a)}{h}", "font_size": 48},
            "layout_role": "formula.primary",
        },
        {
            "id": "caption",
            "type": "Text",
            "args": {"text": "caption", "font_size": 32},
            "layout_role": "caption.conclusion",
        },
    ]
    scene["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}, {"type": "write", "target": "caption"}]}]
    write_json_text(tmp_path / "scene.json", scene)
    qa = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert any(issue["type"] == "layout_memory_policy_applied" and issue["details"]["policy_id"] == policy["policy_id"] for issue in qa["issues"])


def test_compile_explicit_layout_overrides_v11_role(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["layout_template"] = "plot_with_bottom_formula"
    data["mobjects"] = [
        {
            "id": "formula",
            "type": "Tex",
            "args": {"tex": "x^2", "font_size": 48},
            "layout_role": "formula.primary",
            "layout": {"slot": "title"},
        }
    ]
    data["steps"] = [{"id": "s1", "name": "formula", "actions": [{"type": "write", "target": "formula"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "out", use_cache=False)
    assert result["ok"], result
    source = (tmp_path / "out" / "scene.py").read_text(encoding="utf-8")
    assert "mobj_formula.move_to(np.array([0.0, 3.36, 0.0]))" in source


def test_unmapped_v11_role_warns_without_moving(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["version"] = "1.1"
    data["mobjects"][0]["layout_role"] = "diagram.primary"
    result = validate_scene_data(data, quality_gate="relaxed")
    assert result["ok"], result
    assert any(warning["type"] == "layout_role_unmapped" and warning["object"] == "circle" for warning in result["warnings"])


def test_compile_cache_key_includes_generator_hash(tmp_path):
    out = tmp_path / "generated"
    first = compile_scene_file(FIXTURES / "simple_transform.json", out, use_cache=True)
    assert first["ok"], first
    assert not first["cached"]
    assert first["manifest"]["generator_hash"]
    cache = load_json(out / ".compile-cache.json")
    assert cache["generator_hash"] == first["manifest"]["generator_hash"]
    assert "compile_warnings" in cache
    second = compile_scene_file(FIXTURES / "simple_transform.json", out, use_cache=True)
    assert second["ok"], second
    assert second["cached"]
    assert second["cache_key"] == first["cache_key"]
    assert second["manifest"]["generator_hash"] == first["manifest"]["generator_hash"]


def test_compile_collects_precise_manim_imports(tmp_path):
    out = tmp_path / "imports"
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"][0]["style"] = {"color": "BLUE"}
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, out, use_cache=False)
    assert result["ok"], result
    source = (out / "scene.py").read_text(encoding="utf-8")
    assert "from manim import BLUE" in source
    assert "GOLD" not in source
    assert "ORIGIN" not in source


def test_compile_cache_hit(tmp_path):
    out = tmp_path / "cache"
    first = compile_scene_file(FIXTURES / "simple_transform.json", out)
    second = compile_scene_file(FIXTURES / "simple_transform.json", out)
    assert first["ok"], first
    assert second["ok"], second
    assert first["cached"] is False
    assert second["cached"] is True
    assert "cost" in second
    cache = load_json(out / ".compile-cache.json")
    assert cache["manim_cli_version"]
    assert "manim_version" in cache


def test_compile_source_map_contains_metadata(tmp_path):
    out = tmp_path / "metadata"
    result = compile_scene_file(FIXTURES / "simple_transform.json", out, use_cache=False)
    assert result["ok"], result
    source_map = load_json(out / "scene.py.map.json")
    action_mapping = next(item for item in source_map["mappings"] if item["json_path"].startswith("$.steps["))
    assert action_mapping["step_index"] == 0
    assert action_mapping["action_index"] == 0
    assert action_mapping["object_ids"]


def test_multi_error_validation_reports_all_errors():
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"][0]["type"] = "Graph"
    data["steps"][0]["actions"][0]["target"] = "missing_object"
    result = validate_scene_data(data)
    assert not result["ok"]
    errors = result["details"]["errors"]
    error_types = {error["error_type"] for error in errors}
    assert "unsupported_type" in error_types
    assert "undefined_target" in error_types


def test_fast_profile_skips_py_compile_and_records_profile(tmp_path):
    out = tmp_path / "fast"
    result = compile_scene_file(FIXTURES / "simple_transform.json", out, profile="fast", use_cache=False)
    assert result["ok"], result
    assert result["profile"] == "fast"
    assert result["cached"] is False
    assert (out / "build_manifest.json").exists()


def test_timeline_transform_target_template_not_visible():
    scene = validate_and_parse_fixture("simple_transform.json")
    timeline = build_timeline(scene)
    assert "circle" in timeline[0].visible_after
    assert "circle" in timeline[1].visible_after
    assert "square" not in timeline[1].visible_after


def test_scene_analysis_duration_and_bbox_confidence():
    scene = validate_and_parse_fixture("simple_transform.json")
    analysis = analyze_scene(scene)
    assert analysis.timeline[0].duration_seconds == 1.0
    assert analysis.object_lifetimes["circle"].first_step == 0
    circle = next(mob for mob in scene.mobjects if mob.type == "Circle")
    estimate = estimate_bbox(scene, circle)
    assert estimate.confidence == "high"


def test_strict_quality_gate_blocks_overlap():
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    relaxed = validate_scene_data(data, quality_gate="relaxed")
    strict = validate_scene_data(data, quality_gate="strict")
    assert relaxed["ok"], relaxed
    assert any(item["type"] == "layout_overlap" for item in relaxed["warnings"])
    assert not strict["ok"]
    assert strict["error_type"] == "layout_overlap"


def test_validate_default_skips_quality_warnings():
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    result = validate_scene_data(data)
    assert result["ok"], result
    assert "warnings" not in result


def test_qa_strict_blocks_text_solid_overlap(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "circle", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "label", "type": "Text", "args": {"text": "label", "font_size": 48}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "show both", "actions": [{"type": "add", "target": "circle"}, {"type": "write", "target": "label"}]}]
    write_json_text(tmp_path / "scene.json", data)
    relaxed = run_qa(tmp_path / "scene.json")
    strict = run_qa(tmp_path / "scene.json", profile="strict")
    assert relaxed["ok"], relaxed
    issue = next(issue for issue in relaxed["issues"] if issue["type"] == "layout_overlap")
    assert issue["issue_id"].startswith("qa-")
    assert issue["fingerprint"]
    assert issue["confidence"] == "medium"
    assert issue["source"] == "layout_static"
    assert not strict["ok"]


def test_qa_tex_overlap_unknown_static_fails_strict(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Tex", "args": {"tex": "\\frac{a}{b}", "font_size": 48}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Tex", "args": {"tex": "a + b", "font_size": 48}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "show tex", "actions": [{"type": "write", "target": "a"}, {"type": "write", "target": "b"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="strict")
    assert not result["ok"], result
    assert any(issue["type"] == "layout_overlap" and issue["severity"] == "error" for issue in result["issues"])


def test_qa_timing_drift_and_feedback(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["storyboard_ref"] = "storyboard.json"
    data["mobjects"] = [{"id": "title", "type": "Text", "args": {"text": "Timing", "font_size": 40}}]
    data["steps"] = [{"id": "s1", "name": "slow", "storyboard_event_id": "event1", "actions": [{"type": "write", "target": "title", "run_time": 5.0}]}]
    storyboard = {"id": "sb", "plan_id": "p", "frames": [{"id": "frame1", "duration_seconds": 1.0, "visual_events": [{"id": "event1", "intent": "show title", "focus": ["title"]}]}]}
    write_json_text(tmp_path / "scene.json", data)
    write_json_text(tmp_path / "storyboard.json", storyboard)
    result = run_qa(tmp_path / "scene.json", profile="strict", out_dir=tmp_path / "feedback")
    assert not result["ok"]
    assert any(issue["type"] == "step_frame_timing_drift" for issue in result["issues"])
    assert (tmp_path / "feedback" / "latest.json").exists()
    prompt = (tmp_path / "feedback" / "agent_prompt.md").read_text(encoding="utf-8")
    assert "Scope:" in prompt
    assert "Repair:" in prompt


def test_qa_cue_event_timing_drift(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["plan_ref"] = "plan.json"
    data["storyboard_ref"] = "storyboard.json"
    data["mobjects"] = [{"id": "title", "type": "Text", "args": {"text": "Timing", "font_size": 40}}]
    data["steps"] = [{"id": "s1", "name": "slow", "narration_cue_id": "cue1", "storyboard_event_id": "event1", "actions": [{"type": "write", "target": "title", "run_time": 5.0}]}]
    plan = {"id": "p", "topic": "t", "audience_level": "beginner", "duration_seconds": 60, "learning_goals": ["g1"], "teaching_sequence": [{"id": "ts1", "goal": "g1"}], "narration_cues": [{"id": "cue1", "text": "hello", "duration_seconds": 1.0}]}
    storyboard = {"id": "sb", "plan_id": "p", "frames": [{"id": "frame1", "duration_seconds": 1.0, "visual_events": [{"id": "event1", "intent": "show title", "focus": ["title"], "duration_seconds": 1.0}]}]}
    write_json_text(tmp_path / "scene.json", data)
    write_json_text(tmp_path / "plan.json", plan)
    write_json_text(tmp_path / "storyboard.json", storyboard)
    result = run_qa(tmp_path / "scene.json", profile="strict")
    assert not result["ok"]
    drift_types = {i["type"] for i in result["issues"] if "timing_drift" in i["type"]}
    assert "step_frame_timing_drift" in drift_types
    assert "cue_event_timing_drift" in drift_types
    cue_issue = next(i for i in result["issues"] if i["type"] == "cue_event_timing_drift")
    assert cue_issue["repair_scope"] == "cross_track_alignment"
    assert cue_issue["source"] == "timing_static"


def test_repair_context_uses_fingerprints(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    write_json_text(tmp_path / "scene.json", data)
    first = run_qa(tmp_path / "scene.json", profile="strict")
    fp = first["issues"][0]["fingerprint"]
    second = run_qa(tmp_path / "scene.json", profile="strict", repair_context={"previous_issues": first["issues"], "repaired_issue_fingerprints": [fp]})
    assert fp in second["regression_reintroduced"]
    assert second["repair_loop_risk"] == "high"


def test_qa_math_denominator_zero(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "eq", "type": "Tex", "args": {"tex": "\\frac{1}{x-1}", "font_size": 48}},
        {"id": "assign", "type": "Text", "args": {"text": "x=1", "font_size": 36}},
    ]
    data["steps"] = [{"id": "s1", "name": "bad math", "actions": [{"type": "write", "target": "eq"}, {"type": "write", "target": "assign"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="strict")
    assert not result["ok"]
    assert any(issue["type"] == "math_denominator_zero" for issue in result["issues"])


def test_qa_math_transform_without_relation(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "eq1", "type": "Tex", "args": {"tex": "a + b", "font_size": 48}},
        {"id": "eq2", "type": "Tex", "args": {"tex": "c + d", "font_size": 48}},
    ]
    data["steps"] = [{"id": "s1", "name": "unexplained transform", "actions": [{"type": "write", "target": "eq1"}, {"type": "transform", "target": "eq1", "to": "eq2"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="relaxed")
    issue = next(i for i in result["issues"] if i["type"] == "math_transform_without_relation")
    assert issue["repair_scope"] == "single_action"
    assert issue["source"] == "math_lint"
    # Supplied relation suppresses the warning.
    data["steps"][0]["actions"][1]["semantic_relation"] = "apply_distributive_law"
    write_json_text(tmp_path / "scene.json", data)
    relaxed = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert not any(i["type"] == "math_transform_without_relation" for i in relaxed["issues"])


def test_qa_layout_font_too_small(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [{"id": "tiny", "type": "Text", "args": {"text": "x", "font_size": 12}}]
    data["steps"] = [{"id": "s1", "name": "tiny", "actions": [{"type": "write", "target": "tiny"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert any(i["type"] == "layout_font_too_small" for i in result["issues"])


def test_bottom_formula_and_caption_slots_do_not_overlap():
    scene = parse_scene_file(FIXTURES / "simple_transform.json")
    bottom_formula = slot_region(scene, "bottom_formula")
    caption = slot_region(scene, "caption")
    assert not overlaps(bottom_formula, caption)


def test_tex_conservative_height_for_limit_fraction():
    scene = parse_scene_file(FIXTURES / "simple_transform.json")
    simple = {"id": "simple", "type": "Tex", "args": {"tex": "x^2", "font_size": 48}}
    tall = {"id": "tall", "type": "Tex", "args": {"tex": r"f'(a)=\lim_{h\to0}\frac{f(a+h)-f(a)}{h}", "font_size": 48}}
    simple_scene = scene.__class__.model_validate({**scene.model_dump(), "mobjects": [simple]})
    tall_scene = scene.__class__.model_validate({**scene.model_dump(), "mobjects": [tall]})
    simple_box = estimate_bbox(simple_scene, simple_scene.mobjects[0])
    tall_box = estimate_bbox(tall_scene, tall_scene.mobjects[0])
    assert simple_box is not None
    assert tall_box is not None
    assert tall_box.height > simple_box.height * 2


def test_measured_tex_bbox_overrides_heuristic():
    from manim_cli.render.bbox_probe import BBoxProbeResult

    scene = parse_scene_file(FIXTURES / "simple_transform.json")
    scene = scene.__class__.model_validate(
        {
            **scene.model_dump(),
            "mobjects": [
                {"id": "eq", "type": "Tex", "args": {"tex": "x^2", "font_size": 48}, "position": {"mode": "absolute", "point": [1, 2, 0]}}
            ],
        }
    )
    box = estimate_bbox(scene, scene.mobjects[0], tex_probe_results={"eq": BBoxProbeResult(status="measured", bbox=BBox(-2, -0.75, 2, 0.75), method="latex_dvisvgm")})
    assert box is not None
    assert box.confidence == "high"
    assert box.method == "latex_dvisvgm"
    assert box.width == 4
    assert box.height == 1.5


def test_qa_layout_confidence_gated_overlap(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    # Two Text objects (medium confidence) slightly overlapping → no warning (small overlap).
    data["mobjects"] = [
        {"id": "t1", "type": "Text", "args": {"text": "hello", "font_size": 48}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "t2", "type": "Text", "args": {"text": "world", "font_size": 48}, "position": {"mode": "absolute", "point": [2.5, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "both", "actions": [{"type": "add", "target": "t1"}, {"type": "add", "target": "t2"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert not any(i["type"] == "layout_overlap" for i in result["issues"])
    # Now heavily overlapping (same position) → should warn.
    data["mobjects"][1]["position"]["point"] = [0.1, 0, 0]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="relaxed")
    assert any(i["type"] == "layout_overlap" for i in result["issues"])


def test_qa_allows_plot_geometry_overlay(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "axes", "type": "Axes", "args": {"x_range": [-1, 2, 1], "y_range": [-1, 2, 1], "width": 4.0, "height": 4.0}},
        {"id": "curve", "type": "Line", "args": {"start": [0, 0, 0], "end": [1, 1, 0], "coordinate_space": "plane", "axes": "axes"}},
        {"id": "point", "type": "Dot", "args": {"point": [0.5, 0.5, 0], "coordinate_space": "plane", "axes": "axes"}},
    ]
    data["steps"] = [{"id": "s1", "name": "plot", "actions": [{"type": "add", "target": "axes"}, {"type": "add", "target": "curve"}, {"type": "add", "target": "point"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="strict")
    assert result["ok"], result
    assert not any(issue["type"] == "layout_overlap" for issue in result["issues"])


def test_qa_blocks_tex_inside_plot_area(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "axes", "type": "Axes", "args": {"x_range": [-1, 2, 1], "y_range": [-1, 2, 1], "width": 4.0, "height": 4.0}},
        {"id": "formula", "type": "Tex", "args": {"tex": "f'(a)", "font_size": 48}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    data["steps"] = [{"id": "s1", "name": "bad formula", "actions": [{"type": "add", "target": "axes"}, {"type": "write", "target": "formula"}]}]
    write_json_text(tmp_path / "scene.json", data)
    result = run_qa(tmp_path / "scene.json", profile="strict")
    assert not result["ok"], result
    assert any(issue["type"] == "layout_overlap" for issue in result["issues"])


def test_derivative_example_layout_and_geometry():
    scene_path = Path(__file__).parents[1] / "examples" / "derivative_geometric_meaning" / "scene.json"
    result = run_qa(scene_path, profile="strict")
    assert result["ok"], result
    blocking_overlaps = [issue for issue in result["issues"] if issue["type"] == "layout_overlap"]
    assert blocking_overlaps == []

    data = load_json(scene_path)
    objects = {mob["id"]: mob for mob in data["mobjects"]}
    curve_segments = sorted(
        [mob for mob in objects.values() if mob["id"].startswith("curve_")],
        key=lambda mob: mob["args"]["start"][0],
    )
    assert len(curve_segments) == 67
    assert curve_segments[0]["args"]["start"][:2] == [-1.5, 2.25]
    assert curve_segments[-1]["args"]["end"][:2] == [1.8, 3.24]
    for segment in curve_segments:
        for point_key in ("start", "end"):
            x, y, _ = segment["args"][point_key]
            assert y == round(x * x, 4)

    before_p = objects["curve_50"]["args"]
    after_p = objects["curve_66"]["args"]
    left_slope = slope(before_p["start"], before_p["end"])
    right_slope = slope(after_p["start"], after_p["end"])
    angle_change = abs(math.degrees(math.atan(right_slope) - math.atan(left_slope)))
    assert angle_change < 1.0

    tangent = objects["tangent_line"]["args"]
    assert slope(tangent["start"], tangent["end"]) == 2.0
    assert objects["limit_formula"]["layout"]["slot"] == "bottom_formula"
    assert "position" not in objects["limit_formula"]


def test_qa_layout_custom_region_max_dims(tmp_path):
    from manim_cli.dsl.layout import bbox_from_region
    box = bbox_from_region({"left": -5, "bottom": -2, "max_width": 10, "max_height": 4})
    assert box is not None
    assert box.right == 5.0
    assert box.top == 2.0


def slope(start, end):
    return round((end[1] - start[1]) / (end[0] - start[0]), 10)


def test_qa_cli_command(tmp_path):
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, load_json(FIXTURES / "simple_transform.json"))
    result = CliRunner().invoke(main, ["qa", str(scene_path), "--profile", "relaxed"])
    assert result.exit_code == 0, result.output
    assert '"phase": "qa"' in result.output


def test_migrate_layout_cli_outputs_v11_template_and_roles(tmp_path):
    source_path = Path("examples/derivative_geometric_meaning/scene.json")
    original = source_path.read_text(encoding="utf-8")
    out_path = tmp_path / "scene.v1_1.json"
    result = CliRunner().invoke(main, ["migrate-layout", str(source_path), "--to-version", "1.1", "--out", str(out_path)])
    assert result.exit_code == 0, result.output
    assert source_path.read_text(encoding="utf-8") == original
    migrated = load_json(out_path)
    assert migrated["version"] == "1.1"
    assert migrated["layout_template"] == "plot_with_bottom_formula"
    objects = {mobject["id"]: mobject for mobject in migrated["mobjects"]}
    assert objects["title"]["layout_role"] == "title.primary"
    assert objects["axes"]["layout_role"] == "plot.axes"
    assert objects["limit_formula"]["layout_role"] == "formula.primary"
    assert objects["conclusion"]["layout_role"] == "caption.conclusion"
    validation = validate_scene_file(out_path)
    assert validation["ok"], validation
    qa = run_qa(out_path, profile="strict")
    assert qa["ok"], qa
    compile_result = compile_scene_file(out_path, tmp_path / "compiled", use_cache=False)
    assert compile_result["ok"], compile_result


def test_render_qa_gate_blocks_before_manim(tmp_path):
    scene = load_json(FIXTURES / "simple_transform.json")
    scene["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    scene["steps"] = [{"id": "s1", "name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, scene)
    result = CliRunner().invoke(main, ["render", str(scene_path), "--qa", "--output", str(tmp_path / "preview.mp4")])
    assert result.exit_code == 0, result.output
    assert '"phase": "render_qa_gate"' in result.output
    assert "layout_overlap" in result.output


def test_source_map_lookup_and_diagnose_mapping(tmp_path):
    out = tmp_path / "generated"
    result = compile_scene_file(FIXTURES / "simple_transform.json", out, use_cache=False)
    assert result["ok"], result
    source_map_path = out / "scene.py.map.json"
    by_object = lookup_source_map(source_map_path, object_id="circle")
    assert by_object
    action_line = next(item["python_lines"][0] for item in by_object if item["json_path"].startswith("$.steps["))
    mapped = map_line(source_map_path, action_line)
    assert mapped["object_ids"]
    assert mapped["step_id"]
    cli = CliRunner().invoke(main, ["source-map", "lookup", str(source_map_path), "--object-id", "circle"])
    assert cli.exit_code == 0, cli.output
    assert '"matches"' in cli.output


def test_layout_slot_compiles_scale_to_fit_width(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {
            "id": "long_caption",
            "type": "Text",
            "args": {"text": "This is a very long caption that should fit inside the caption slot safely", "font_size": 48},
            "layout": {"slot": "caption"},
        }
    ]
    data["steps"] = [{"name": "show", "actions": [{"type": "write", "target": "long_caption"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "generated", use_cache=False)
    assert result["ok"], result
    source = (tmp_path / "generated" / "scene.py").read_text(encoding="utf-8")
    assert "move_to(np.array" in source
    assert "scale_to_fit_width" in source or ".scale(" in source
    assert any(change["object"] == "long_caption" and change["change"] == "fit_to_region" for change in result["layout_changes"])


def test_step_level_layout_action_compiles(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [{"id": "label", "type": "Text", "args": {"text": "Move me", "font_size": 36}, "layout": {"slot": "main"}}]
    data["steps"] = [
        {"id": "s1", "name": "show", "actions": [{"type": "write", "target": "label"}]},
        {"id": "s2", "name": "move", "actions": [{"type": "layout", "target": "label", "slot": "caption", "run_time": 0.5}]},
    ]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "generated", use_cache=False)
    assert result["ok"], result
    source = (tmp_path / "generated" / "scene.py").read_text(encoding="utf-8")
    assert ".animate.move_to" in source
    assert any(change["change"] == "step_layout" for change in result["layout_changes"])


def test_duplicate_mobject_uses_copy_template(tmp_path):
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [
        {"id": "a", "type": "Text", "args": {"text": "x", "font_size": 40}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Text", "args": {"text": "x", "font_size": 40}, "position": {"mode": "absolute", "point": [1, 0, 0]}},
    ]
    data["steps"] = [{"name": "show", "actions": [{"type": "write", "target": "a"}, {"type": "write", "target": "b"}]}]
    scene_path = tmp_path / "scene.json"
    write_json_text(scene_path, data)
    result = compile_scene_file(scene_path, tmp_path / "generated", use_cache=False)
    assert result["ok"], result
    source = (tmp_path / "generated" / "scene.py").read_text(encoding="utf-8")
    assert ".copy()" in source
    assert any(change["change"] == "copy_from_template" for change in result["layout_changes"])


def test_pedagogy_and_alignment_warnings(tmp_path):
    plan = {
        "id": "p",
        "topic": "Vectors",
        "audience_level": "intro",
        "duration_seconds": 30,
        "learning_goals": ["Understand vector magnitude"],
        "teaching_sequence": [{"id": "s1", "goal": "Magnitude"}],
        "symbol_ledger": [{"symbol": "v", "meaning": "velocity", "canonical_tex": "\\vec{v}", "color_role": "BLUE"}],
        "narration_cues": [{"id": "cue_missing", "text": "Velocity v appears."}],
    }
    storyboard = {"id": "sb", "plan_id": "p", "frames": [{"id": "f1", "visual_events": [{"id": "event_missing", "intent": "show vector", "focus": ["vector_arrow"]}]}]}
    scene = load_json(FIXTURES / "simple_transform.json")
    scene["plan_ref"] = "plan.json"
    scene["storyboard_ref"] = "storyboard.json"
    scene["mobjects"] = [{"id": "label", "type": "Text", "args": {"text": "v", "font_size": 40}, "style": {"color": "RED"}}]
    scene["steps"] = [{"id": "step", "name": "show", "actions": [{"type": "write", "target": "label"}]}]
    write_json_text(tmp_path / "plan.json", plan)
    write_json_text(tmp_path / "storyboard.json", storyboard)
    write_json_text(tmp_path / "scene.json", scene)
    result = validate_scene_file(tmp_path / "scene.json", quality_gate="relaxed")
    assert result["ok"], result
    warning_types = {item["type"] for item in result["warnings"]}
    assert "symbol_not_in_ledger" in warning_types or "symbol_canonical_tex_mismatch" in warning_types
    assert "cue_without_scene_step" in warning_types
    assert "event_without_scene_step" in warning_types


def test_visual_qa_pixel_analysis():
    warnings = analyze_pixels(10, 10, [(30, 30, 30)] * 100, background=(30, 30, 30))
    assert warnings[0]["type"] == "visual_empty_frame"
    full = analyze_pixels(10, 10, [(255, 255, 255)] * 100, background=(30, 30, 30))
    assert any(item["type"] == "visual_edge_pressure" for item in full)
    keyframe = analyze_keyframe("frame1", 10, 10, [(255, 255, 255)] * 100)
    assert keyframe["pixel_hash"]
    assert keyframe["frame_id"] == "frame1"


def test_visual_qa_cli_keyframe_and_bbox_probe(tmp_path):
    pixels_path = tmp_path / "pixels.json"
    write_json_text(pixels_path, {"frame_id": "f", "width": 2, "height": 2, "pixels": [[30, 30, 30], [30, 30, 30], [30, 30, 30], [30, 30, 30]]})
    keyframe = CliRunner().invoke(main, ["visual-qa", "keyframe", str(pixels_path)])
    assert keyframe.exit_code == 0, keyframe.output
    assert '"frame_id": "f"' in keyframe.output
    probe = CliRunner().invoke(main, ["visual-qa", "bbox-probe", "\\frac{a}{b}"])
    assert probe.exit_code == 0, probe.output
    assert '"phase": "bbox_probe"' in probe.output


def test_regression_runner_without_render(tmp_path):
    fixture_dir = tmp_path / "regression" / "case"
    fixture_dir.mkdir(parents=True)
    write_json_text(fixture_dir / "scene.json", load_json(FIXTURES / "simple_transform.json"))
    result = run_regression_dir(tmp_path / "regression", tmp_path / "out")
    assert result["ok"], result
    assert result["results"][0]["render_skipped"] is True
    assert result["results"][0]["qa"] is not None
    assert result["results"][0]["render_cost"]["scene_py_bytes"] > 0


def test_regression_expected_qa_baseline_and_eval(tmp_path):
    fixture_dir = tmp_path / "regression" / "case"
    fixture_dir.mkdir(parents=True)
    scene = load_json(FIXTURES / "simple_transform.json")
    scene["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    scene["steps"] = [{"id": "s1", "name": "show both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    write_json_text(fixture_dir / "scene.json", scene)
    write_json_text(fixture_dir / "expected_qa.json", {"issue_types": ["layout_overlap"]})
    result = run_regression_dir(tmp_path / "regression", tmp_path / "out")
    assert result["results"][0]["qa_baseline"]["ok"]
    eval_result = run_qa_eval(tmp_path / "regression")
    assert eval_result["metrics"]["true_positive"] >= 1
    regression_cli = CliRunner().invoke(main, ["regression", "run", str(tmp_path / "regression"), "--out", str(tmp_path / "cli-out")])
    assert regression_cli.exit_code == 0, regression_cli.output
    assert '"phase": "qa"' in regression_cli.output
    eval_cli = CliRunner().invoke(main, ["qa-eval", str(tmp_path / "regression")])
    assert eval_cli.exit_code == 0, eval_cli.output
    assert '"precision"' in eval_cli.output


def test_regression_manifest_baseline(tmp_path):
    fixture_dir = tmp_path / "regression" / "case"
    fixture_dir.mkdir(parents=True)
    scene = load_json(FIXTURES / "simple_transform.json")
    write_json_text(fixture_dir / "scene.json", scene)
    # First run to capture the actual manifest, then write it as expected.
    first = run_regression_dir(tmp_path / "regression", tmp_path / "out")
    manifest = first["results"][0]["manifest"]
    assert manifest is not None
    assert "scene_hash" in manifest
    write_json_text(fixture_dir / "expected_manifest.json", manifest)
    # Matching manifest → ok.
    second = run_regression_dir(tmp_path / "regression", tmp_path / "out")
    assert second["results"][0]["manifest_baseline"]["ok"]
    # Tampered manifest → not ok with a changed entry.
    tampered = dict(manifest)
    tampered["action_count"] = manifest["action_count"] + 999
    write_json_text(fixture_dir / "expected_manifest.json", tampered)
    third = run_regression_dir(tmp_path / "regression", tmp_path / "out")
    baseline = third["results"][0]["manifest_baseline"]
    assert not baseline["ok"]
    assert any(c["key"] == "action_count" for c in baseline["changed"])


def test_deterministic_python_output(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    first = compile_scene_file(FIXTURES / "vector_intro.json", out_a, use_cache=False)
    second = compile_scene_file(FIXTURES / "vector_intro.json", out_b, use_cache=False)
    assert first["ok"] and second["ok"]
    py_a = (out_a / "scene.py").read_bytes()
    py_b = (out_b / "scene.py").read_bytes()
    assert py_a == py_b, "generated scene.py must be byte-identical across compiles"


def test_deterministic_source_map(tmp_path):
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    compile_scene_file(FIXTURES / "vector_intro.json", out_a, use_cache=False)
    compile_scene_file(FIXTURES / "vector_intro.json", out_b, use_cache=False)
    map_a = json.loads((out_a / "scene.py.map.json").read_text(encoding="utf-8"))
    map_b = json.loads((out_b / "scene.py.map.json").read_text(encoding="utf-8"))
    assert map_a == map_b, "source map must be structurally identical across compiles"
    canonical_a = json.dumps(map_a, sort_keys=True)
    canonical_b = json.dumps(map_b, sort_keys=True)
    assert canonical_a == canonical_b, "source map must serialize byte-identically when sorted"


def test_deterministic_scene_serialization(tmp_path):
    # Lock the canonical serialization used for the scene_hash fallback
    # (compile_scene computes scene_hash from scene_canonical_json when no raw-file
    # hash is passed). Pydantic v2's model_dump_json has no sort_keys option, so the
    # compiler dumps to a json-mode dict and sorts every key via stdlib. This pins
    # determinism and insertion-order independence.
    from manim_cli.dsl.compiler import scene_canonical_json
    from manim_cli.dsl.models import SceneDef

    raw = load_json(FIXTURES / "vector_intro.json")
    scene = SceneDef.model_validate(raw)

    once = scene_canonical_json(scene)
    twice = scene_canonical_json(scene)
    assert once == twice, "scene_canonical_json must be deterministic"

    # Reconstructing the model from a dict with reversed key order must yield
    # identical canonical bytes — proves sorted output is dict-order independent.
    reversed_raw = dict(reversed(list(raw.items())))
    scene_rev = SceneDef.model_validate(reversed_raw)
    assert scene_canonical_json(scene_rev) == once, "dict insertion order must not affect canonical output"

    # The fallback scene_hash computed by compile_scene must be stable for the
    # same logical scene regardless of how it was built.
    from manim_cli.build import content_hash

    assert content_hash(once.encode("utf-8")) == content_hash(twice.encode("utf-8"))


def validate_and_parse_fixture(name):
    from manim_cli.dsl.validators import parse_scene_file

    result = validate_scene_file(FIXTURES / name)
    assert result["ok"], result
    return parse_scene_file(FIXTURES / name)


def write_json_text(path, data):
    import json

    path.write_text(json.dumps(data), encoding="utf-8")


REGRESSION_DIR = Path(__file__).parent / "regression"


def test_qa_eval_persistent_corpus():
    result = run_qa_eval(REGRESSION_DIR)
    assert result["ok"], result
    assert result["metrics"]["false_negative"] == 0
    assert result["metrics"]["false_positive"] == 0
    assert result["metrics"]["true_positive"] >= 5
    case_names = {c["name"] for c in result["cases"]}
    assert {"clean", "overlap", "out_of_bounds", "math_denominator", "font_too_small"} <= case_names


def test_qa_eval_empty_corpus_guard(tmp_path):
    result = run_qa_eval(tmp_path)
    assert not result["ok"]
    assert result.get("error") == "no_eval_cases"


def test_qa_eval_false_positive_gating(tmp_path):
    case_dir = tmp_path / "extra_issue"
    case_dir.mkdir()
    scene = load_json(FIXTURES / "simple_transform.json")
    scene["mobjects"] = [
        {"id": "a", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
        {"id": "b", "type": "Circle", "args": {"radius": 1.0}, "position": {"mode": "absolute", "point": [0, 0, 0]}},
    ]
    scene["steps"] = [{"id": "s1", "name": "both", "actions": [{"type": "add", "target": "a"}, {"type": "add", "target": "b"}]}]
    write_json_text(case_dir / "scene.json", scene)
    write_json_text(case_dir / "expected_qa.json", {"issue_types": []})
    strict = run_qa_eval(tmp_path, fail_on_false_positive=True)
    assert not strict["ok"]
    assert strict["metrics"]["false_positive"] >= 1
    relaxed = run_qa_eval(tmp_path, fail_on_false_positive=False)
    assert relaxed["ok"]


def test_video_frame_extraction(tmp_path):
    import shutil

    from manim_cli.render.frames import analyze_video_keyframes, compare_keyframe_hashes, extract_keyframes, ffmpeg_available

    if not ffmpeg_available():
        return
    content_video = tmp_path / "content.mp4"
    subprocess_result = __import__("subprocess")
    subprocess_result.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=2:size=320x180:rate=15", "-pix_fmt", "yuv420p", str(content_video)],
        capture_output=True,
        timeout=15,
    )
    assert content_video.exists()
    frames = extract_keyframes(content_video, num_frames=3, scale_width=80)
    assert len(frames) == 3
    assert all(f["width"] == 80 for f in frames)
    assert all(len(f["pixels"]) > 0 for f in frames)
    result = analyze_video_keyframes(content_video, num_frames=3, scale_width=80)
    assert result["ok"] is True or len(result["all_warnings"]) > 0
    hashes1 = [f["pixel_hash"] for f in result["frames"]]
    result2 = analyze_video_keyframes(content_video, num_frames=3, scale_width=80)
    hashes2 = [f["pixel_hash"] for f in result2["frames"]]
    assert hashes1 == hashes2
    baseline = compare_keyframe_hashes(hashes1, hashes1)
    assert baseline["ok"]
    mismatch = compare_keyframe_hashes(hashes1, ["deadbeef"])
    assert not mismatch["ok"]


def test_video_frame_empty_detection(tmp_path):
    import subprocess

    from manim_cli.render.frames import analyze_video_keyframes, ffmpeg_available

    if not ffmpeg_available():
        return
    empty_video = tmp_path / "empty.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x1e1e1e:s=320x180:d=2:r=15", "-pix_fmt", "yuv420p", str(empty_video)],
        capture_output=True,
        timeout=15,
    )
    assert empty_video.exists()
    result = analyze_video_keyframes(empty_video, num_frames=3, scale_width=80)
    assert any(w["type"] == "visual_empty_frame" for w in result["all_warnings"])


def test_latex_bbox_probe_availability():
    from manim_cli.render.bbox_probe import probe_available, probe_tex_bbox

    result = probe_tex_bbox(r"\frac{a}{b}", font_size=48)
    if probe_available():
        assert result.status == "measured"
        assert result.bbox is not None
        assert result.bbox.width > 0
        assert result.method == "latex_dvisvgm"
    else:
        assert result.status == "unavailable"
        assert result.bbox is None
        assert "dependency_missing" in result.method or "compilation" in result.method


def test_latex_bbox_probe_unavailable_message():
    from manim_cli.render.bbox_probe import latex_available, probe_available, probe_tex_bbox

    if probe_available():
        return
    result = probe_tex_bbox("x^2", font_size=48)
    assert result.status == "unavailable"
    assert result.bbox is None
    assert result.message
    if not latex_available():
        assert "latex" in result.message


def test_latex_bbox_probe_scene():
    from manim_cli.render.bbox_probe import probe_available, probe_scene_tex_bboxes

    parsed = parse_scene_file(FIXTURES / "simple_transform.json")
    results = probe_scene_tex_bboxes(parsed)
    assert len(results) == 0
    data = load_json(FIXTURES / "simple_transform.json")
    data["mobjects"] = [{"id": "eq", "type": "Tex", "args": {"tex": "x^2 + y^2", "font_size": 48}}]
    tmp_scene = FIXTURES.parent / "tmp_tex_scene.json"
    write_json_text(tmp_scene, data)
    parsed2 = parse_scene_file(tmp_scene)
    results2 = probe_scene_tex_bboxes(parsed2)
    assert "eq" in results2
    if probe_available():
        assert results2["eq"].status == "measured"
    else:
        assert results2["eq"].status == "unavailable"
    tmp_scene.unlink(missing_ok=True)

from __future__ import annotations

from pathlib import Path

import click

from manim_cli.jsonio import load_json, print_json
from manim_cli.render.bbox_probe import probe_tex_bbox
from manim_cli.render.frames import analyze_video_keyframes
from manim_cli.render.visual_qa import analyze_keyframe


@click.group("visual-qa")
def visual_qa_group() -> None:
    """Run dependency-light visual QA helpers."""


@visual_qa_group.command("keyframe")
@click.argument("pixels_json", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def visual_qa_keyframe_cmd(pixels_json: Path) -> None:
    data = load_json(pixels_json)
    frame_id = data.get("frame_id", pixels_json.stem)
    print_json(analyze_keyframe(frame_id, int(data["width"]), int(data["height"]), [tuple(pixel) for pixel in data["pixels"]], background=tuple(data.get("background", [30, 30, 30]))))


@visual_qa_group.command("video")
@click.argument("video_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--num-frames", type=int, default=5, show_default=True, help="Number of keyframes to extract.")
@click.option("--scale-width", type=int, default=160, show_default=True, help="Downscale width for pixel analysis.")
def visual_qa_video_cmd(video_path: Path, num_frames: int, scale_width: int) -> None:
    """Extract keyframes from a rendered video and run pixel-level visual QA."""
    print_json(analyze_video_keyframes(video_path, num_frames=num_frames, scale_width=scale_width))


@visual_qa_group.command("bbox-probe")
@click.argument("tex")
@click.option("--font-size", type=int, default=48, show_default=True)
def bbox_probe_cmd(tex: str, font_size: int) -> None:
    result = probe_tex_bbox(tex, font_size=font_size)
    bbox = None if result.bbox is None else {"left": result.bbox.left, "bottom": result.bbox.bottom, "right": result.bbox.right, "top": result.bbox.top}
    print_json({"ok": result.status == "measured", "phase": "bbox_probe", "status": result.status, "bbox": bbox, "method": result.method, "message": result.message})

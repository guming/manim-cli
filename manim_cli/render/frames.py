from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from manim_cli.render.visual_qa import Pixel, analyze_keyframe


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def probe_video(video_path: Path) -> Dict[str, Any]:
    if not shutil.which("ffprobe"):
        return {"ok": False, "error": "ffprobe_not_found"}
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(video_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return {"ok": False, "error": "ffprobe_failed", "stderr": result.stderr.strip()}
        import json

        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        if not video_stream:
            return {"ok": False, "error": "no_video_stream"}
        fmt = data.get("format", {})
        duration = float(fmt.get("duration", 0) or video_stream.get("duration", 0))
        return {
            "ok": True,
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "duration": duration,
            "nb_frames": int(video_stream.get("nb_frames", 0)),
            "fps": _parse_fps(video_stream.get("avg_frame_rate", "0/1")),
        }
    except (subprocess.TimeoutExpired, ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc)}


def extract_keyframes(video_path: Path, num_frames: int = 5, scale_width: int = 160) -> List[Dict[str, Any]]:
    if not ffmpeg_available():
        return []
    info = probe_video(video_path)
    if not info.get("ok") or info.get("duration", 0) <= 0:
        return []
    duration = info["duration"]
    if num_frames == 1:
        timestamps = [duration / 2.0]
    else:
        step = duration / num_frames
        timestamps = [step * (i + 0.5) for i in range(num_frames)]
    frames: List[Dict[str, Any]] = []
    for index, ts in enumerate(timestamps):
        frame = extract_frame(video_path, ts, scale_width)
        if frame:
            frames.append({"frame_id": f"frame_{index:03d}", "timestamp": round(ts, 3), "width": frame[0], "height": frame[1], "pixels": frame[2]})
    return frames


def extract_frame(video_path: Path, timestamp: float, scale_width: int = 160) -> Tuple[int, int, List[Pixel]] | None:
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={scale_width}:-1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            timeout=15,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        raw = result.stdout
        height = len(raw) // (scale_width * 3)
        if height == 0:
            return None
        pixels: List[Pixel] = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
        return (scale_width, height, pixels)
    except (subprocess.TimeoutExpired, OSError):
        return None


def analyze_video_keyframes(video_path: Path, num_frames: int = 5, scale_width: int = 160, background: Pixel = (30, 30, 30)) -> Dict[str, Any]:
    info = probe_video(video_path)
    if not info.get("ok"):
        return {"ok": False, "error": info.get("error", "probe_failed"), "frames": [], "all_warnings": []}
    frames = extract_keyframes(video_path, num_frames=num_frames, scale_width=scale_width)
    if not frames:
        return {"ok": False, "error": "extraction_failed", "frames": [], "all_warnings": []}
    analyses = [analyze_keyframe(f["frame_id"], f["width"], f["height"], f["pixels"], background=background) for f in frames]
    all_warnings = [w for a in analyses for w in a["warnings"]]
    return {"ok": len(all_warnings) == 0, "video_info": info, "frames": analyses, "all_warnings": all_warnings}


def compare_keyframe_hashes(actual_hashes: List[str], expected_hashes: List[str]) -> Dict[str, Any]:
    actual_set = set(actual_hashes)
    expected_set = set(expected_hashes)
    matched = actual_set & expected_set
    missing = expected_set - actual_set
    unexpected = actual_set - expected_set
    return {
        "ok": not missing and not unexpected,
        "matched": sorted(matched),
        "missing": sorted(missing),
        "unexpected": sorted(unexpected),
        "match_ratio": round(len(matched) / max(1, len(expected_set)), 4),
    }


def _parse_fps(fraction: str) -> float:
    try:
        num, den = fraction.split("/")
        den_val = float(den)
        return float(num) / den_val if den_val else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0

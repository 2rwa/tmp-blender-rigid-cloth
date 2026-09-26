from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "softbody-jelly-cube-ball-drop-eevee"


def validate_preview(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"preview missing: {path}")
    if path.stat().st_size < 10_000:
        raise SystemExit(f"preview suspiciously small: {path.stat().st_size}")

    with Image.open(path) as image:
        image.load()
        if image.size != (480, 360):
            raise SystemExit(f"unexpected preview size: {image.size}")
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        extrema = gray.getextrema()
        mean = float(stat.mean[0])
        stddev = float(stat.stddev[0])
        if extrema[1] - extrema[0] < 75:
            raise SystemExit(f"insufficient luminance range: {extrema}")
        if stddev < 16.0:
            raise SystemExit(f"preview too uniform: {stddev:.2f}")
        if not (7.0 <= mean <= 210.0):
            raise SystemExit(f"unexpected luminance mean: {mean:.2f}")

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "width": 480,
        "height": 360,
        "luminance_min": extrema[0],
        "luminance_max": extrema[1],
        "luminance_mean": round(mean, 3),
        "luminance_stddev": round(stddev, 3),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_video(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"video missing: {path}")
    if path.stat().st_size < 40_000:
        raise SystemExit(f"video suspiciously small: {path.stat().st_size}")

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,duration,nb_frames",
            "-show_entries", "format=size,duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(proc.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    duration = float(stream.get("duration") or fmt.get("duration") or 0.0)

    if (width, height) != (480, 360):
        raise SystemExit(f"unexpected video size: {(width, height)}")
    if not (7.5 <= duration <= 8.5):
        raise SystemExit(f"unexpected video duration: {duration:.3f}")

    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": round(duration, 3),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "nb_frames": stream.get("nb_frames"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_report(report_path: Path, blend_path: Path) -> dict:
    if not report_path.exists():
        raise SystemExit(f"report missing: {report_path}")
    if not blend_path.exists():
        raise SystemExit(f"blend missing: {blend_path}")
    if blend_path.stat().st_size < 500_000:
        raise SystemExit(f"blend suspiciously small: {blend_path.stat().st_size}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    expected = {
        "frame_start": 1,
        "frame_end": 192,
        "fps": 24,
        "resolution_x": 480,
        "resolution_y": 360,
    }
    for key, value in expected.items():
        if report.get(key) != value:
            raise SystemExit(f"unexpected {key}: {report.get(key)}")

    jelly = report.get("jelly") or {}
    if jelly.get("name") != "JellyCube":
        raise SystemExit(f"unexpected jelly name: {jelly.get('name')}")
    if int(jelly.get("vertex_count", 0)) < 100:
        raise SystemExit(f"jelly mesh too small: {jelly.get('vertex_count')}")
    if int(jelly.get("baked_shape_keys", 0)) != 192:
        raise SystemExit(f"unexpected baked frames: {jelly.get('baked_shape_keys')}")
    if int(jelly.get("shape_key_count", 0)) < 193:
        raise SystemExit(f"shape keys missing: {jelly.get('shape_key_count')}")

    max_displacement = float(jelly.get("max_displacement", 0.0))
    if not (0.005 <= max_displacement <= 12.0):
        raise SystemExit(f"unexpected jelly deformation: {max_displacement}")

    rigid = report.get("rigid_bodies") or {}
    if int(rigid.get("count", 0)) != 3:
        raise SystemExit(f"unexpected rigid body count: {rigid.get('count')}")
    if rigid.get("proxy") != "JellyRigidProxy":
        raise SystemExit(f"unexpected proxy: {rigid.get('proxy')}")
    balls = rigid.get("balls") or []
    if len(balls) != 3:
        raise SystemExit(f"ball diagnostics missing: {len(balls)}")
    for ball in balls:
        if not ball.get("name"):
            raise SystemExit("ball name missing")
        if len(ball.get("final_location") or []) != 3:
            raise SystemExit(f"ball final location missing: {ball.get('name')}")

    return {
        "engine": report.get("engine"),
        "jelly_vertex_count": jelly.get("vertex_count"),
        "jelly_face_count": jelly.get("face_count"),
        "baked_shape_keys": jelly.get("baked_shape_keys"),
        "shape_key_count": jelly.get("shape_key_count"),
        "simulation_seconds": jelly.get("simulation_seconds"),
        "max_displacement": jelly.get("max_displacement"),
        "max_displacement_frame": jelly.get("max_displacement_frame"),
        "rigid_body_count": rigid.get("count"),
        "rigid_body_bake_seconds": rigid.get("bake_seconds"),
        "rigid_body_proxy": rigid.get("proxy"),
        "substeps_per_frame": rigid.get("world_substeps_per_frame"),
        "solver_iterations": rigid.get("world_solver_iterations"),
        "possible_proxy_tunneling": [
            ball.get("name") for ball in balls if ball.get("possible_proxy_tunneling")
        ],
        "blend_size_bytes": blend_path.stat().st_size,
    }


def main() -> None:
    preview = Path(sys.argv[1] if len(sys.argv) > 1 else "output/preview.png")
    base = preview.parent
    result = {
        "video": f"{EXPERIMENT}.mp4",
        "preview": validate_preview(preview),
        "movie": validate_video(base / f"{EXPERIMENT}.mp4"),
        "report": validate_report(
            base / f"{EXPERIMENT}-report.json",
            base / f"{EXPERIMENT}.blend",
        ),
    }
    out = base / "validation.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

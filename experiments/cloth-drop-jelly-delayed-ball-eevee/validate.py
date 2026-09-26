from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "cloth-drop-jelly-delayed-ball-eevee"


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
        "path": str(path), "size_bytes": path.stat().st_size,
        "width": 480, "height": 360,
        "luminance_min": extrema[0], "luminance_max": extrema[1],
        "luminance_mean": round(mean, 3), "luminance_stddev": round(stddev, 3),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_video(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"video missing: {path}")
    if path.stat().st_size < 40_000:
        raise SystemExit(f"video suspiciously small: {path.stat().st_size}")
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,avg_frame_rate,duration,nb_frames",
         "-show_entries", "format=size,duration", "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(proc.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
    duration = float(stream.get("duration") or fmt.get("duration") or 0.0)
    if (width, height) != (480, 360):
        raise SystemExit(f"unexpected video size: {(width, height)}")
    if not (7.5 <= duration <= 8.5):
        raise SystemExit(f"unexpected video duration: {duration:.3f}")
    return {
        "path": str(path), "size_bytes": path.stat().st_size,
        "width": width, "height": height, "duration_seconds": round(duration, 3),
        "avg_frame_rate": stream.get("avg_frame_rate"), "nb_frames": stream.get("nb_frames"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_report(report_path: Path, blend_path: Path) -> dict:
    if not report_path.exists():
        raise SystemExit(f"report missing: {report_path}")
    if not blend_path.exists():
        raise SystemExit(f"blend missing: {blend_path}")
    if blend_path.stat().st_size < 700_000:
        raise SystemExit(f"blend suspiciously small: {blend_path.stat().st_size}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key, value in {
        "frame_start": 1, "frame_end": 192, "fps": 24,
        "resolution_x": 480, "resolution_y": 360,
    }.items():
        if report.get(key) != value:
            raise SystemExit(f"unexpected {key}: {report.get(key)}")

    coupling = report.get("coupling") or {}
    if coupling.get("cloth_reads_jelly_collision") is not True:
        raise SystemExit("cloth-to-jelly collision coupling missing")
    if coupling.get("jelly_reads_cloth_collision") is not False:
        raise SystemExit("unexpected two-way cloth/jelly dependency")

    jelly = report.get("jelly") or {}
    if jelly.get("name") != "JellyCube" or int(jelly.get("vertex_count", 0)) < 100:
        raise SystemExit("invalid jelly mesh")
    if int(jelly.get("baked_shape_keys", 0)) != 192 or int(jelly.get("shape_key_count", 0)) < 193:
        raise SystemExit("jelly shape-key bake incomplete")
    jelly_disp = float(jelly.get("max_displacement", 0.0))
    if not (0.005 <= jelly_disp <= 12.0):
        raise SystemExit(f"unexpected jelly deformation: {jelly_disp}")

    cloth = report.get("cloth") or {}
    if cloth.get("name") != "DropCloth" or int(cloth.get("vertex_count", 0)) < 900:
        raise SystemExit("invalid cloth mesh")
    if cloth.get("self_collision") is not True:
        raise SystemExit("cloth self collision disabled")
    if int(cloth.get("baked_shape_keys", 0)) != 192 or int(cloth.get("shape_key_count", 0)) < 193:
        raise SystemExit("cloth shape-key bake incomplete")
    cloth_disp = float(cloth.get("max_displacement", 0.0))
    if not (0.50 <= cloth_disp <= 16.0):
        raise SystemExit(f"cloth did not fall/deform as expected: {cloth_disp}")

    ball = report.get("ball") or {}
    if ball.get("name") != "DropBall_00":
        raise SystemExit(f"unexpected ball name: {ball.get('name')}")
    if int(ball.get("release_frame", 0)) != 49:
        raise SystemExit(f"unexpected ball release frame: {ball.get('release_frame')}")
    if abs(float(ball.get("release_seconds", 0.0)) - 2.0) > 0.01:
        raise SystemExit(f"unexpected ball release time: {ball.get('release_seconds')}")
    if len(ball.get("final_location") or []) != 3:
        raise SystemExit("ball final location missing")

    rigid = report.get("rigid_body") or {}
    if rigid.get("proxy") != "JellyRigidProxy":
        raise SystemExit(f"unexpected rigid proxy: {rigid.get('proxy')}")

    return {
        "engine": report.get("engine"),
        "jelly_vertex_count": jelly.get("vertex_count"),
        "jelly_max_displacement": jelly.get("max_displacement"),
        "jelly_max_displacement_frame": jelly.get("max_displacement_frame"),
        "cloth_vertex_count": cloth.get("vertex_count"),
        "cloth_max_displacement": cloth.get("max_displacement"),
        "cloth_max_displacement_frame": cloth.get("max_displacement_frame"),
        "cloth_min_vertex_z": cloth.get("min_vertex_z"),
        "cloth_min_vertex_z_frame": cloth.get("min_vertex_z_frame"),
        "ball_release_frame": ball.get("release_frame"),
        "ball_release_seconds": ball.get("release_seconds"),
        "ball_final_location": ball.get("final_location"),
        "possible_proxy_tunneling": ball.get("possible_proxy_tunneling"),
        "substeps_per_frame": rigid.get("world_substeps_per_frame"),
        "solver_iterations": rigid.get("world_solver_iterations"),
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
    (base / "validation.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

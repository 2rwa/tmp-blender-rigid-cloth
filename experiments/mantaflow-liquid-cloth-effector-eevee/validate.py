from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "mantaflow-liquid-cloth-effector-eevee"
OUTPUT = Path("output")


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

    if extrema[1] - extrema[0] < 60:
        raise SystemExit(f"insufficient preview contrast: {extrema}")
    if stddev < 12.0:
        raise SystemExit(f"preview too uniform: {stddev:.2f}")

    return {
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
    if path.stat().st_size < 30_000:
        raise SystemExit(f"video suspiciously small: {path.stat().st_size}")

    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,avg_frame_rate,nb_frames",
            "-show_entries", "format=duration,size",
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
    duration = float(fmt.get("duration") or 0.0)

    if (width, height) != (480, 360):
        raise SystemExit(f"unexpected video size: {(width, height)}")
    if not (3.7 <= duration <= 4.3):
        raise SystemExit(f"unexpected video duration: {duration:.3f}")

    return {
        "size_bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": round(duration, 3),
        "avg_frame_rate": stream.get("avg_frame_rate"),
        "nb_frames": stream.get("nb_frames"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_report(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"report missing: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))

    if report.get("true_fluid") is not True:
        raise SystemExit("experiment is not marked as a true fluid simulation")

    coupling = report.get("coupling") or {}
    if coupling.get("liquid_reads_cloth_effector") is not True:
        raise SystemExit("liquid/cloth effector coupling missing")
    if coupling.get("cloth_reads_liquid_force") is not False:
        raise SystemExit("first Mantaflow test must remain explicitly one-way")

    domain = report.get("domain") or {}
    if int(domain.get("resolution_max", 0)) != 48:
        raise SystemExit(f"unexpected domain resolution: {domain.get('resolution_max')}")
    if int(domain.get("cache_file_count", 0)) < 5:
        raise SystemExit(
            f"Mantaflow cache too small: files={domain.get('cache_file_count')}"
        )
    if int(domain.get("cache_bytes", 0)) < 50_000:
        raise SystemExit(
            f"Mantaflow cache bytes suspiciously low: {domain.get('cache_bytes')}"
        )

    samples = report.get("fluid_mesh_samples") or {}
    later = []
    lateral_spans = []
    min_z_values = []

    for frame in ("24", "48", "72", "96"):
        stat = samples.get(frame) or {}
        vertices = int(stat.get("vertex_count", 0))
        if vertices > 8:
            later.append(vertices)
        bounds = stat.get("bounds")
        if bounds:
            span = bounds.get("span") or [0, 0, 0]
            mn = bounds.get("min") or [0, 0, 99]
            lateral_spans.append(max(float(span[0]), float(span[1])))
            min_z_values.append(float(mn[2]))

    if not later or max(later) < 50:
        raise SystemExit(
            f"no meaningful liquid mesh found in sampled frames: {samples}"
        )
    if not lateral_spans or max(lateral_spans) < 1.45:
        raise SystemExit(
            f"liquid did not spread laterally enough to show interaction: {lateral_spans}"
        )
    if not min_z_values or min(min_z_values) > 2.0:
        raise SystemExit(
            f"liquid never descended to Cloth height: min_z={min_z_values}"
        )

    return {
        "fluid_solver": report.get("fluid_solver"),
        "bake_seconds": domain.get("bake_seconds"),
        "cache_file_count": domain.get("cache_file_count"),
        "cache_bytes": domain.get("cache_bytes"),
        "sample_vertex_counts": {
            frame: (samples.get(frame) or {}).get("vertex_count")
            for frame in ("1", "24", "48", "72", "96")
        },
        "max_lateral_span": round(max(lateral_spans), 6),
        "min_fluid_z": round(min(min_z_values), 6),
        "cloth_vertex_count": (report.get("cloth_effector") or {}).get(
            "vertex_count"
        ),
    }


def main():
    preview = validate_preview(OUTPUT / "preview.png")
    video_path = OUTPUT / f"{EXPERIMENT}.mp4"
    video = validate_video(video_path)
    report = validate_report(OUTPUT / f"{EXPERIMENT}-report.json")

    blend = OUTPUT / f"{EXPERIMENT}.blend"
    if not blend.exists() or blend.stat().st_size < 500_000:
        raise SystemExit("prepared Mantaflow blend missing or suspiciously small")

    result = {
        "video": video_path.name,
        "preview": preview,
        "movie": video,
        "report": report,
        "blend_size_bytes": blend.stat().st_size,
    }
    (OUTPUT / "validation.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

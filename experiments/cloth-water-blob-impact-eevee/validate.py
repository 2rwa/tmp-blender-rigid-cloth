from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "cloth-water-blob-impact-eevee"


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
        if extrema[1] - extrema[0] < 70:
            raise SystemExit(f"insufficient luminance range: {extrema}")
        if stddev < 15.0:
            raise SystemExit(f"preview too uniform: {stddev:.2f}")
        if not (6.0 <= mean <= 215.0):
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
    if path.stat().st_size < 35_000:
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
    if blend_path.stat().st_size < 700_000:
        raise SystemExit(f"blend suspiciously small: {blend_path.stat().st_size}")

    report = json.loads(report_path.read_text(encoding="utf-8"))

    for key, value in {
        "frame_start": 1,
        "frame_end": 192,
        "fps": 24,
        "resolution_x": 480,
        "resolution_y": 360,
    }.items():
        if report.get(key) != value:
            raise SystemExit(f"unexpected {key}: {report.get(key)}")

    coupling = report.get("coupling") or {}
    if coupling.get("true_fluid") is not False:
        raise SystemExit("water-like blob must be explicitly marked as non-fluid")
    if coupling.get("cloth_reads_blob_collision") is not True:
        raise SystemExit("cloth does not read blob collision")
    if coupling.get("blob_reads_cloth_collision") is not True:
        raise SystemExit("blob does not read cloth collision")

    blob = report.get("blob") or {}
    if blob.get("name") != "WaterBlob":
        raise SystemExit(f"unexpected blob name: {blob.get('name')}")
    if int(blob.get("vertex_count", 0)) < 400:
        raise SystemExit(f"blob mesh too small: {blob.get('vertex_count')}")
    if int(blob.get("baked_shape_keys", 0)) != 192:
        raise SystemExit(f"blob bake incomplete: {blob.get('baked_shape_keys')}")
    if int(blob.get("shape_key_count", 0)) < 193:
        raise SystemExit(f"blob shape keys missing: {blob.get('shape_key_count')}")

    blob_disp = float(blob.get("max_displacement", 0.0))
    if not (0.03 <= blob_disp <= 8.0):
        raise SystemExit(
            f"water-like blob did not deform plausibly: max_displacement={blob_disp:.6f}"
        )

    cloth = report.get("cloth") or {}
    if cloth.get("name") != "WaterDropCloth":
        raise SystemExit(f"unexpected cloth name: {cloth.get('name')}")
    if int(cloth.get("vertex_count", 0)) < 1000:
        raise SystemExit(f"cloth mesh too small: {cloth.get('vertex_count')}")
    if cloth.get("self_collision") is not True:
        raise SystemExit("cloth self collision disabled")
    if int(cloth.get("baked_shape_keys", 0)) != 192:
        raise SystemExit(f"cloth bake incomplete: {cloth.get('baked_shape_keys')}")
    if int(cloth.get("shape_key_count", 0)) < 193:
        raise SystemExit(f"cloth shape keys missing: {cloth.get('shape_key_count')}")

    interaction = report.get("interaction") or {}
    contact_frame = interaction.get("first_contact_frame")
    if contact_frame is None:
        raise SystemExit("no cloth/blob contact detected")
    if not (2 <= int(contact_frame) <= 160):
        raise SystemExit(f"unexpected first contact frame: {contact_frame}")

    coverage = float(interaction.get("coverage_at_blob_peak", 0.0))
    if coverage < 0.45:
        raise SystemExit(
            f"cloth not sufficiently over blob at deformation peak: coverage={coverage:.3f}"
        )

    gap = interaction.get("center_gap_at_blob_peak")
    if gap is None:
        raise SystemExit("center gap metric unavailable")
    gap = float(gap)
    if gap > 0.20:
        raise SystemExit(
            f"cloth center not in contact with blob at deformation peak: gap={gap:.3f}"
        )

    return {
        "engine": report.get("engine"),
        "blob_vertex_count": blob.get("vertex_count"),
        "blob_max_displacement": blob.get("max_displacement"),
        "blob_peak_frame": blob.get("max_displacement_frame"),
        "cloth_vertex_count": cloth.get("vertex_count"),
        "cloth_max_displacement": cloth.get("max_displacement"),
        "cloth_min_vertex_z": cloth.get("min_vertex_z"),
        "first_contact_frame": contact_frame,
        "coverage_at_blob_peak": coverage,
        "center_gap_at_blob_peak": gap,
        "simulation_seconds": interaction.get("simulation_seconds"),
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
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "mantaflow-liquid-baked-cloth-effector-eevee"
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
    size = path.stat().st_size
    if size < 30_000:
        raise SystemExit(f"video suspiciously small: {size}")
    return {
        "size_bytes": size,
        "expected_width": 480,
        "expected_height": 360,
        "expected_duration_seconds": 4.0,
        "expected_fps": 24,
        "expected_frames": 96,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def validate_report(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"report missing: {path}")
    report = json.loads(path.read_text(encoding="utf-8"))

    if report.get("true_fluid") is not True:
        raise SystemExit("experiment is not marked as true fluid")

    coupling = report.get("coupling") or {}
    if coupling.get("liquid_reads_deforming_cloth") is not True:
        raise SystemExit("liquid does not read deforming Cloth effector")
    if coupling.get("cloth_reads_liquid_force") is not False:
        raise SystemExit("experiment unexpectedly claims liquid -> Cloth force")
    if coupling.get("cloth_is_dynamic_before_bake") is not True:
        raise SystemExit("Cloth was not dynamically generated before bake")

    cloth = report.get("cloth") or {}
    if int(cloth.get("vertex_count", 0)) < 1000:
        raise SystemExit(f"cloth mesh too small: {cloth.get('vertex_count')}")
    if int(cloth.get("baked_frames", 0)) != 96:
        raise SystemExit(f"cloth bake incomplete: {cloth.get('baked_frames')}")
    if int(cloth.get("shape_key_count", 0)) < 97:
        raise SystemExit(f"cloth shape keys missing: {cloth.get('shape_key_count')}")

    displacement = float(cloth.get("max_displacement", 0.0))
    if not (0.15 <= displacement <= 8.0):
        raise SystemExit(
            f"Cloth did not deform meaningfully: max displacement={displacement:.6f}"
        )

    center = cloth.get("center_z_samples") or {}
    z1 = center.get("1")
    z24 = center.get("24")
    z48 = center.get("48")
    if z1 is None or z24 is None or z48 is None:
        raise SystemExit(f"missing Cloth center samples: {center}")
    z1, z24, z48 = float(z1), float(z24), float(z48)
    if max(z1 - z24, z1 - z48) < 0.18:
        raise SystemExit(
            f"Cloth center did not sag enough: z1={z1:.3f}, "
            f"z24={z24:.3f}, z48={z48:.3f}"
        )

    domain = report.get("domain") or {}
    if int(domain.get("resolution_max", 0)) != 48:
        raise SystemExit(f"unexpected domain resolution: {domain.get('resolution_max')}")
    if int(domain.get("cache_file_count", 0)) < 5:
        raise SystemExit(
            f"Mantaflow cache too small: {domain.get('cache_file_count')}"
        )
    if int(domain.get("cache_bytes", 0)) < 50_000:
        raise SystemExit(
            f"Mantaflow cache bytes suspiciously low: {domain.get('cache_bytes')}"
        )

    samples = report.get("fluid_mesh_samples") or {}
    later_vertices = []
    lateral_spans = []
    min_z_values = []

    for frame in ("12", "24", "48", "72", "96"):
        stat = samples.get(frame) or {}
        vertices = int(stat.get("vertex_count", 0))
        if vertices > 8:
            later_vertices.append(vertices)
        bounds = stat.get("bounds")
        if bounds:
            span = bounds.get("span") or [0, 0, 0]
            mn = bounds.get("min") or [0, 0, 99]
            lateral_spans.append(max(float(span[0]), float(span[1])))
            min_z_values.append(float(mn[2]))

    if not later_vertices or max(later_vertices) < 50:
        raise SystemExit(f"no meaningful liquid mesh: {samples}")
    if not lateral_spans or max(lateral_spans) < 1.45:
        raise SystemExit(
            f"liquid did not spread laterally enough: {lateral_spans}"
        )
    if not min_z_values or min(min_z_values) > 2.0:
        raise SystemExit(
            f"liquid never descended to deforming Cloth region: {min_z_values}"
        )

    return {
        "fluid_solver": report.get("fluid_solver"),
        "cloth_simulation_seconds": cloth.get("simulation_seconds"),
        "cloth_max_displacement": displacement,
        "cloth_center_z_samples": center,
        "fluid_bake_seconds": domain.get("bake_seconds"),
        "cache_file_count": domain.get("cache_file_count"),
        "cache_bytes": domain.get("cache_bytes"),
        "sample_vertex_counts": {
            frame: (samples.get(frame) or {}).get("vertex_count")
            for frame in ("1", "12", "24", "48", "72", "96")
        },
        "max_lateral_span": round(max(lateral_spans), 6),
        "min_fluid_z": round(min(min_z_values), 6),
    }


def main():
    preview = validate_preview(OUTPUT / "preview.png")
    video_path = OUTPUT / f"{EXPERIMENT}.mp4"
    video = validate_video(video_path)
    report = validate_report(OUTPUT / f"{EXPERIMENT}-report.json")

    blend = OUTPUT / f"{EXPERIMENT}.blend"
    if not blend.exists() or blend.stat().st_size < 500_000:
        raise SystemExit("Mantaflow blend missing or suspiciously small")

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

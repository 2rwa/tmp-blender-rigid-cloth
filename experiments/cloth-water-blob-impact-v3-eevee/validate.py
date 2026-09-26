from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "cloth-water-blob-impact-v3-eevee"


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
            "-show_entries", "format=size,duration", "-of", "json", str(path),
        ],
        check=True, capture_output=True, text=True,
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
    coupling = report.get("coupling") or {}

    if coupling.get("mode") != (
        "three-pass staged coupling with expanded final collision shell"
    ):
        raise SystemExit(f"unexpected coupling mode: {coupling.get('mode')}")
    if coupling.get("true_fluid") is not False:
        raise SystemExit("V3 must remain explicitly non-fluid")

    shell = report.get("collision_shell") or {}
    if shell.get("shares_blob_shape_keys") is not True:
        raise SystemExit("animated collision shell is not tied to baked blob")

    blob = report.get("blob") or {}
    if int(blob.get("baked_shape_keys", 0)) != 192:
        raise SystemExit("blob bake incomplete")
    blob_disp = float(blob.get("max_displacement", 0.0))
    if not (0.03 <= blob_disp <= 6.0):
        raise SystemExit(f"implausible blob deformation: {blob_disp:.6f}")

    cloth = report.get("final_cloth") or {}
    if cloth.get("name") != "WaterDropClothV3":
        raise SystemExit(f"unexpected final cloth: {cloth.get('name')}")
    if int(cloth.get("baked_shape_keys", 0)) != 192:
        raise SystemExit("final cloth bake incomplete")
    if cloth.get("first_contact_frame") is None:
        raise SystemExit("V3 final Cloth never contacted blob shell")

    coverage = float(cloth.get("coverage_at_blob_peak", 0.0))
    if coverage < 0.40:
        raise SystemExit(f"V3 coverage too low at blob peak: {coverage:.3f}")

    peak_gap = cloth.get("center_gap_at_blob_peak")
    min_gap = cloth.get("min_center_gap_after_contact")
    max_gap = cloth.get("max_center_gap_after_contact")
    if peak_gap is None or min_gap is None or max_gap is None:
        raise SystemExit("V3 gap metrics missing")

    peak_gap = float(peak_gap)
    min_gap = float(min_gap)
    max_gap = float(max_gap)

    # V2 fixed floating but looked as if the blob was swallowing the cloth.
    # V3 should keep the visible Cloth slightly outside the visible surface.
    if not (-0.05 <= peak_gap <= 0.30):
        raise SystemExit(
            f"V3 peak gap outside useful surface band: {peak_gap:.3f}"
        )
    if min_gap < -0.12:
        raise SystemExit(
            f"V3 still shows excessive center ingestion: min_gap={min_gap:.3f}"
        )
    if max_gap > 0.35:
        raise SystemExit(
            f"V3 reintroduced visible floating: max_gap={max_gap:.3f}"
        )

    return {
        "engine": report.get("engine"),
        "blob_max_displacement": blob.get("max_displacement"),
        "blob_peak_frame": blob.get("max_displacement_frame"),
        "v2_peak_gap": (report.get("comparison") or {}).get(
            "v2_gap_at_blob_peak"
        ),
        "v3_peak_gap": peak_gap,
        "v3_min_gap_after_contact": min_gap,
        "v3_max_gap_after_contact": max_gap,
        "v3_coverage_at_blob_peak": coverage,
        "final_cloth_simulation_seconds": cloth.get("simulation_seconds"),
        "blend_size_bytes": blend_path.stat().st_size,
    }


def main():
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

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat

EXPERIMENT = "cloth-water-blob-impact-v2-eevee"


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
    if coupling.get("mode") != "three-pass staged coupling with cloth reconciliation":
        raise SystemExit(f"unexpected coupling mode: {coupling.get('mode')}")
    if coupling.get("true_fluid") is not False:
        raise SystemExit("V2 must remain explicitly non-fluid")
    if coupling.get("bidirectional_feedback") is not False:
        raise SystemExit("V2 unexpectedly claims bidirectional feedback")

    blob = report.get("blob") or {}
    if int(blob.get("baked_shape_keys", 0)) != 192:
        raise SystemExit("blob bake incomplete")
    blob_disp = float(blob.get("max_displacement", 0.0))
    if not (0.03 <= blob_disp <= 6.0):
        raise SystemExit(f"implausible blob deformation: {blob_disp:.6f}")

    final_cloth = report.get("final_cloth") or {}
    if final_cloth.get("name") != "WaterDropClothV2":
        raise SystemExit(f"unexpected final cloth: {final_cloth.get('name')}")
    if int(final_cloth.get("baked_shape_keys", 0)) != 192:
        raise SystemExit("final cloth bake incomplete")
    if int(final_cloth.get("shape_key_count", 0)) < 193:
        raise SystemExit("final cloth shape keys missing")
    if final_cloth.get("first_contact_frame") is None:
        raise SystemExit("final Cloth never contacted the baked blob")

    coverage = float(final_cloth.get("coverage_at_blob_peak", 0.0))
    if coverage < 0.40:
        raise SystemExit(
            f"final Cloth not over blob at peak deformation: {coverage:.3f}"
        )

    final_gap = final_cloth.get("center_gap_at_blob_peak")
    if final_gap is None:
        raise SystemExit("final Cloth/blob peak gap unavailable")
    final_gap = float(final_gap)
    if final_gap > 0.35:
        raise SystemExit(
            f"V2 still visibly floats at blob peak: gap={final_gap:.3f}"
        )

    comparison = report.get("comparison") or {}
    guide_gap = comparison.get("guide_gap_at_blob_peak")
    improvement = comparison.get("gap_improvement_from_guide")
    if guide_gap is None or improvement is None:
        raise SystemExit("V2 comparison metrics missing")
    guide_gap = float(guide_gap)
    improvement = float(improvement)

    if guide_gap > 0.35 and improvement < 0.30:
        raise SystemExit(
            f"third pass did not materially reduce separation: "
            f"guide={guide_gap:.3f}, improvement={improvement:.3f}"
        )

    return {
        "engine": report.get("engine"),
        "blob_max_displacement": blob.get("max_displacement"),
        "blob_peak_frame": blob.get("max_displacement_frame"),
        "guide_gap_at_blob_peak": guide_gap,
        "final_gap_at_blob_peak": final_gap,
        "gap_improvement_from_guide": improvement,
        "final_coverage_at_blob_peak": coverage,
        "max_positive_gap_after_contact": final_cloth.get(
            "max_positive_center_gap_after_contact"
        ),
        "guide_simulation_seconds": (report.get("guide_cloth") or {}).get(
            "simulation_seconds"
        ),
        "blob_simulation_seconds": blob.get("simulation_seconds"),
        "final_cloth_simulation_seconds": final_cloth.get("simulation_seconds"),
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

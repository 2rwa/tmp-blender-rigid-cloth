from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageStat

OUT = Path("output52")
EXPERIMENT = "cloth-tearing-minimal-gn52"


def main():
    report_path = OUT / f"{EXPERIMENT}-report.json"
    preview_path = OUT / "preview.png"
    video_path = OUT / f"{EXPERIMENT}.mp4"
    blend_path = OUT / f"{EXPERIMENT}.blend"
    version_path = OUT / "blender-version.txt"

    for path in (report_path, preview_path, video_path, blend_path, version_path):
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"missing or empty output: {path}")

    version_text = version_path.read_text(encoding="utf-8", errors="replace")
    if "Blender 5.2.2" not in version_text:
        raise SystemExit(f"unexpected Blender version: {version_text[:120]!r}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not str(report.get("blender_version", "")).startswith("5.2.2"):
        raise SystemExit(
            f"report Blender mismatch: {report.get('blender_version')}"
        )

    tearing = report.get("tearing") or {}
    if tearing.get("enabled") is not True:
        raise SystemExit("tearing was not enabled")
    if tearing.get("topology_changed") is not True:
        raise SystemExit(
            "no tearing topology change detected; "
            f"first_tear={tearing.get('first_tear_frame')}"
        )

    first_tear = int(tearing["first_tear_frame"])
    if not (2 <= first_tear <= 65):
        raise SystemExit(f"tear frame outside useful range: {first_tear}")

    cloth = report.get("cloth") or {}
    base = cloth.get("base_topology") or {}
    base_vertices = int(base.get("vertices", 0))
    max_vertices = int(tearing.get("max_vertices", 0))
    if max_vertices <= base_vertices:
        raise SystemExit(
            f"tear did not split vertices: base={base_vertices}, max={max_vertices}"
        )

    samples = report.get("samples") or []
    if len(samples) != 72:
        raise SystemExit(f"unexpected sample count: {len(samples)}")

    with Image.open(preview_path) as image:
        image.load()
        if image.size != (480, 360):
            raise SystemExit(f"unexpected preview size: {image.size}")
        gray = image.convert("L")
        stat = ImageStat.Stat(gray)
        extrema = gray.getextrema()
        stddev = float(stat.stddev[0])

    if extrema[1] - extrema[0] < 55:
        raise SystemExit(f"preview contrast too low: {extrema}")
    if stddev < 10.0:
        raise SystemExit(f"preview too uniform: {stddev:.2f}")
    if video_path.stat().st_size < 35_000:
        raise SystemExit(
            f"video suspiciously small: {video_path.stat().st_size}"
        )
    if blend_path.stat().st_size < 500_000:
        raise SystemExit(
            f"blend suspiciously small: {blend_path.stat().st_size}"
        )

    result = {
        "experiment": EXPERIMENT,
        "blender_version": report.get("blender_version"),
        "asset_source": (report.get("asset") or {}).get("source"),
        "first_tear_frame": first_tear,
        "base_vertices": base_vertices,
        "max_vertices": max_vertices,
        "max_components": tearing.get("max_components"),
        "preview_frame": tearing.get("preview_frame"),
        "preview_sha256": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
        "video_size_bytes": video_path.stat().st_size,
        "blend_size_bytes": blend_path.stat().st_size,
    }

    (OUT / "validation.json").write_text(
        json.dumps(result, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

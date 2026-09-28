from __future__ import annotations
import hashlib,json
from pathlib import Path
from PIL import Image,ImageStat
OUT=Path("output52")
def validate(experiment):
    report_path=OUT/f"{experiment}-report.json"; preview=OUT/"preview.png"; video=OUT/f"{experiment}.mp4"; blend=OUT/f"{experiment}.blend"; version=OUT/"blender-version.txt"
    for p in (report_path,preview,video,blend,version):
        if not p.is_file() or p.stat().st_size==0: raise SystemExit(f"missing or empty output: {p}")
    report=json.loads(report_path.read_text(encoding="utf-8"))
    if not str(report.get("blender_version","")).startswith("5.2.2"): raise SystemExit(f"unexpected Blender version: {report.get('blender_version')}")
    samples=report.get("samples") or []
    expected_samples=int(report.get("frame_end",72))-int(report.get("frame_start",1))+1
    if len(samples)!=expected_samples: raise SystemExit(f"expected {expected_samples} samples, got {len(samples)}")
    with Image.open(preview) as im:
        im.load()
        if im.size!=(480,360): raise SystemExit(f"unexpected preview size: {im.size}")
        gray=im.convert("L"); ext=gray.getextrema(); std=float(ImageStat.Stat(gray).stddev[0])
    if ext[1]-ext[0]<45 or std<8: raise SystemExit(f"preview lacks contrast: {ext}, {std}")
    if video.stat().st_size<10000: raise SystemExit(f"video too small: {video.stat().st_size}")
    if blend.stat().st_size<150000: raise SystemExit(f"blend too small: {blend.stat().st_size}")
    t=report.get("tearing") or {}; ball=report.get("ball") or {}; cloth=report.get("cloth") or {}
    result={"experiment":experiment,"pattern":report.get("pattern"),"blender_version":report.get("blender_version"),"impact_frame":ball.get("impact_frame"),"frame_end":report.get("frame_end"),"duration_seconds":round(len(samples)/float(report.get("fps") or 24),3),"tear_observed":bool(t.get("topology_changed")),"first_tear_frame":t.get("first_tear_frame"),"tear_after_planned_contact":t.get("tear_after_planned_contact"),"base_vertices":cloth.get("base_topology",{}).get("vertices"),"max_vertices":t.get("max_vertices"),"max_components":t.get("max_components"),"tear_edge_count":cloth.get("tear_edge_count"),"custom_mode_applied":(report.get("asset") or {}).get("applied",{}).get("tearing_mode_custom_applied"),"preview_frame":t.get("preview_frame"),"preview_sha256":hashlib.sha256(preview.read_bytes()).hexdigest(),"video_size_bytes":video.stat().st_size,"blend_size_bytes":blend.stat().st_size}
    (OUT/"validation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8"); print(json.dumps(result,indent=2))

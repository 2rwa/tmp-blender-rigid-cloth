from __future__ import annotations

import importlib.util
import json
import math
import time
from pathlib import Path

import bpy

ROOT = Path.cwd()
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT = "cloth-water-blob-impact-v2-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START, FRAME_END, FPS = 1, 192, 24
RES_X, RES_Y = 480, 360


def load_v1():
    path = ROOT / "experiments/cloth-water-blob-impact-eevee/scene.py"
    spec = importlib.util.spec_from_file_location("water_blob_v1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load v1 experiment: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bake_final_cloth(scene, v1, cloth, cloth_mod, blob):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in cloth.data.vertices]
    frames = {}
    metrics = {}

    max_displacement = 0.0
    max_frame = FRAME_START
    min_z = float("inf")
    min_z_frame = FRAME_START
    first_contact = None
    started = time.perf_counter()

    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()

        cloth_coords = v1.eval_coords(cloth, depsgraph)
        blob_coords = v1.eval_coords(blob, depsgraph)
        if len(cloth_coords) != len(basis):
            raise RuntimeError(f"final cloth topology changed at frame {frame}")

        frames[frame] = cloth_coords
        cloth_world = v1.to_world_coords(cloth, cloth_coords)
        blob_world = v1.to_world_coords(blob, blob_coords)
        metric = v1.cloth_metrics(cloth_world, blob_world)
        metrics[frame] = metric

        frame_max = 0.0
        for base_co, co in zip(basis, cloth_coords):
            dx = co[0] - base_co[0]
            dy = co[1] - base_co[1]
            dz = co[2] - base_co[2]
            frame_max = max(frame_max, math.sqrt(dx*dx + dy*dy + dz*dz))

        if frame_max > max_displacement:
            max_displacement = frame_max
            max_frame = frame

        frame_min_z = min(co[2] for co in cloth_coords)
        if frame_min_z < min_z:
            min_z = frame_min_z
            min_z_frame = frame

        gap = metric["center_gap"]
        if (
            first_contact is None
            and gap is not None
            and gap <= 0.20
            and metric["coverage"] >= 0.40
        ):
            first_contact = frame

        if not math.isfinite(frame_max) or frame_max > 16.0:
            raise RuntimeError(
                f"final cloth numerical instability at frame {frame}: {frame_max}"
            )

        if frame % 12 == 0:
            print(f"WATER_V2_FINAL_CLOTH_FRAME={frame}")
            print(f"WATER_V2_FINAL_CLOTH_GAP={gap}")
            print(f"WATER_V2_FINAL_CLOTH_COVERAGE={metric['coverage']:.6f}")

    seconds = time.perf_counter() - started

    cloth.modifiers.remove(cloth_mod)
    v1.bake_shape_keys(cloth, frames)
    scene.frame_set(FRAME_START)

    return {
        "frames": frames,
        "metrics": metrics,
        "seconds": round(seconds, 3),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_z": round(min_z, 6),
        "min_z_frame": min_z_frame,
        "first_contact_frame": first_contact,
    }


def metric_at(scene, depsgraph, v1, cloth, blob, frame):
    scene.frame_set(frame)
    depsgraph.update()
    cloth_world = v1.to_world_coords(cloth, v1.eval_coords(cloth, depsgraph))
    blob_world = v1.to_world_coords(blob, v1.eval_coords(blob, depsgraph))
    return v1.cloth_metrics(cloth_world, blob_world)


def build_scene():
    v1 = load_v1()
    base = v1.load_base()
    base.clear_scene()

    scene = bpy.context.scene
    engine = base.choose_engine(scene)
    samples = base.configure_render(scene)

    scene.frame_start, scene.frame_end = FRAME_START, FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x, scene.render.resolution_y = RES_X, RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.gravity = (0.0, 0.0, -9.81)

    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.003, 0.006, 0.014, 1.0)
    bg.inputs["Strength"].default_value = 0.10

    ground = base.make_floor()
    base.add_collision(ground, thickness=0.025, damping=0.20)
    if hasattr(ground.collision, "cloth_friction"):
        ground.collision.cloth_friction = 10.0

    blob = v1.make_blob(
        base,
        "WaterBlobV2",
        (v1.BLOB_HALF_X, v1.BLOB_HALF_Y, v1.BLOB_HALF_Z),
        v1.BLOB_Z,
        render=True,
    )
    initial_blob_local = [tuple(v.co) for v in blob.data.vertices]
    initial_blob_world = v1.to_world_coords(blob, initial_blob_local)

    proxy = v1.make_blob(
        base,
        "WaterBlobGuideProxy",
        (v1.PROXY_HALF_X, v1.PROXY_HALF_Y, v1.PROXY_HALF_Z),
        v1.PROXY_Z,
        render=False,
    )
    base.add_collision(proxy, thickness=0.012, damping=0.18)
    if hasattr(proxy.collision, "cloth_friction"):
        proxy.collision.cloth_friction = 18.0

    # Pass 1: provisional Cloth path against a hidden approximation.
    guide_cloth = v1.make_cloth(base)
    guide_cloth.name = "WaterGuideCloth"
    guide_cloth.hide_render = True
    guide_mod = v1.add_cloth_physics(guide_cloth)

    base.setup_camera_and_lights(scene)

    guide_bake = v1.bake_cloth_pass(
        scene,
        guide_cloth,
        guide_mod,
        initial_blob_world,
    )

    bpy.data.objects.remove(proxy, do_unlink=True)

    # Pass 2: baked provisional Cloth drives the live Soft Body blob.
    base.add_collision(guide_cloth, thickness=0.010, damping=0.14)
    if hasattr(guide_cloth.collision, "cloth_friction"):
        guide_cloth.collision.cloth_friction = 14.0

    soft_mod = v1.add_water_softbody(blob)
    blob_bake = v1.bake_blob_pass(
        scene,
        blob,
        soft_mod,
        guide_cloth,
        guide_bake["frames"],
        initial_blob_local,
    )
    v1.remove_collision_modifier(guide_cloth)

    # Pass 3: solve a fresh visible Cloth against the now-baked animated blob.
    # This is the correction for V1's visible floating/separation artifact.
    base.add_collision(blob, thickness=0.012, damping=0.18)
    if hasattr(blob.collision, "cloth_friction"):
        blob.collision.cloth_friction = 18.0

    final_cloth = v1.make_cloth(base)
    final_cloth.name = "WaterDropClothV2"
    final_mod = v1.add_cloth_physics(final_cloth)
    final_bake = bake_final_cloth(scene, v1, final_cloth, final_mod, blob)

    v1.remove_collision_modifier(blob)
    v1.add_render_modifiers(blob, final_cloth)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    peak_frame = int(blob_bake["peak_frame"])

    guide_peak = metric_at(
        scene, depsgraph, v1, guide_cloth, blob, peak_frame
    )
    final_peak = final_bake["metrics"][peak_frame]

    guide_gap = guide_peak["center_gap"]
    final_gap = final_peak["center_gap"]
    gap_improvement = (
        guide_gap - final_gap
        if guide_gap is not None and final_gap is not None
        else None
    )

    post_contact_gaps = [
        m["center_gap"]
        for frame, m in final_bake["metrics"].items()
        if final_bake["first_contact_frame"] is not None
        and frame >= final_bake["first_contact_frame"]
        and m["center_gap"] is not None
    ]
    max_positive_gap_after_contact = (
        max([g for g in post_contact_gaps if g > 0.0], default=0.0)
        if post_contact_gaps else None
    )

    report = {
        "experiment": EXPERIMENT,
        "engine": engine,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "fps": FPS,
        "resolution_x": RES_X,
        "resolution_y": RES_Y,
        "effective_render_samples": samples,
        "coupling": {
            "mode": "three-pass staged coupling with cloth reconciliation",
            "pass_1": "guide cloth -> hidden initial-blob proxy",
            "pass_2": "baked guide cloth -> live soft-body water blob",
            "pass_3": "fresh final cloth -> baked animated water blob",
            "bidirectional_feedback": False,
            "true_fluid": False,
            "goal": "reduce V1 floating/separation without reintroducing a dependency cycle",
        },
        "blob": {
            "name": blob.name,
            "vertex_count": len(blob.data.vertices),
            "face_count": len(blob.data.polygons),
            "baked_shape_keys": FRAME_END - FRAME_START + 1,
            "shape_key_count": len(blob.data.shape_keys.key_blocks),
            "simulation_seconds": blob_bake["seconds"],
            "max_displacement": blob_bake["max_displacement"],
            "max_displacement_frame": peak_frame,
            "initial_center_top_z": blob_bake["initial_center_top_z"],
            "center_top_z_at_peak": blob_bake["center_top_z_at_peak"],
            "center_top_drop": blob_bake["center_top_drop"],
        },
        "guide_cloth": {
            "name": guide_cloth.name,
            "hidden_render": True,
            "simulation_seconds": guide_bake["seconds"],
            "max_displacement": guide_bake["max_displacement"],
            "first_contact_frame": guide_bake["first_contact_frame"],
            "center_gap_at_blob_peak": (
                round(float(guide_gap), 6) if guide_gap is not None else None
            ),
            "coverage_at_blob_peak": round(float(guide_peak["coverage"]), 6),
        },
        "final_cloth": {
            "name": final_cloth.name,
            "vertex_count": len(final_cloth.data.vertices),
            "face_count": len(final_cloth.data.polygons),
            "self_collision": True,
            "baked_shape_keys": FRAME_END - FRAME_START + 1,
            "shape_key_count": len(final_cloth.data.shape_keys.key_blocks),
            "simulation_seconds": final_bake["seconds"],
            "max_displacement": final_bake["max_displacement"],
            "max_displacement_frame": final_bake["max_displacement_frame"],
            "min_vertex_z": final_bake["min_z"],
            "min_vertex_z_frame": final_bake["min_z_frame"],
            "first_contact_frame": final_bake["first_contact_frame"],
            "center_gap_at_blob_peak": (
                round(float(final_gap), 6) if final_gap is not None else None
            ),
            "coverage_at_blob_peak": round(float(final_peak["coverage"]), 6),
            "max_positive_center_gap_after_contact": (
                round(float(max_positive_gap_after_contact), 6)
                if max_positive_gap_after_contact is not None else None
            ),
        },
        "comparison": {
            "v1_observed_gap_at_blob_peak": 1.264967,
            "guide_gap_at_blob_peak": (
                round(float(guide_gap), 6) if guide_gap is not None else None
            ),
            "final_gap_at_blob_peak": (
                round(float(final_gap), 6) if final_gap is not None else None
            ),
            "gap_improvement_from_guide": (
                round(float(gap_improvement), 6)
                if gap_improvement is not None else None
            ),
        },
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"WATER_V2_BLOB_PEAK_FRAME={peak_frame}")
    print(f"WATER_V2_GUIDE_GAP_AT_PEAK={guide_gap}")
    print(f"WATER_V2_FINAL_GAP_AT_PEAK={final_gap}")
    print(f"WATER_V2_GAP_IMPROVEMENT={gap_improvement}")
    print(f"WATER_V2_MAX_POSITIVE_GAP_AFTER_CONTACT={max_positive_gap_after_contact}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

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

EXPERIMENT = "cloth-water-blob-impact-v3-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START, FRAME_END, FPS = 1, 192, 24
RES_X, RES_Y = 480, 360

SHELL_SCALE = (1.045, 1.045, 1.070)
SHELL_COLLISION_THICKNESS = 0.014


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_animated_collision_shell(base, blob):
    shell = blob.copy()
    # Deliberately share the baked Mesh/Key datablock: the shell receives
    # exactly the same shape-key animation as the visible blob, but an object
    # scale expands it into a thin collision envelope.
    shell.data = blob.data
    shell.name = "WaterBlobCollisionShell"
    shell.hide_render = True
    shell.display_type = "WIRE"
    shell.scale = SHELL_SCALE
    bpy.context.collection.objects.link(shell)

    base.add_collision(
        shell,
        thickness=SHELL_COLLISION_THICKNESS,
        damping=0.20,
    )
    if hasattr(shell.collision, "cloth_friction"):
        shell.collision.cloth_friction = 18.0
    return shell


def bake_final_cloth(scene, v1, cloth, cloth_mod, visible_blob):
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
        blob_coords = v1.eval_coords(visible_blob, depsgraph)
        if len(cloth_coords) != len(basis):
            raise RuntimeError(f"V3 final cloth topology changed at frame {frame}")

        frames[frame] = cloth_coords
        cloth_world = v1.to_world_coords(cloth, cloth_coords)
        blob_world = v1.to_world_coords(visible_blob, blob_coords)
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
            and gap <= 0.30
            and metric["coverage"] >= 0.40
        ):
            first_contact = frame

        if not math.isfinite(frame_max) or frame_max > 16.0:
            raise RuntimeError(
                f"V3 final cloth numerical instability at frame {frame}: {frame_max}"
            )

        if frame % 12 == 0:
            print(f"WATER_V3_FINAL_CLOTH_FRAME={frame}")
            print(f"WATER_V3_VISIBLE_GAP={gap}")
            print(f"WATER_V3_COVERAGE={metric['coverage']:.6f}")

    seconds = time.perf_counter() - started
    cloth.modifiers.remove(cloth_mod)
    v1.bake_shape_keys(cloth, frames)
    scene.frame_set(FRAME_START)

    post_contact_metrics = [
        m for frame, m in metrics.items()
        if first_contact is not None and frame >= first_contact
        and m["center_gap"] is not None
    ]
    post_gaps = [float(m["center_gap"]) for m in post_contact_metrics]

    return {
        "frames": frames,
        "metrics": metrics,
        "seconds": round(seconds, 3),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_z": round(min_z, 6),
        "min_z_frame": min_z_frame,
        "first_contact_frame": first_contact,
        "min_center_gap_after_contact": (
            round(min(post_gaps), 6) if post_gaps else None
        ),
        "max_center_gap_after_contact": (
            round(max(post_gaps), 6) if post_gaps else None
        ),
    }


def metric_at(scene, depsgraph, v1, cloth, blob, frame):
    scene.frame_set(frame)
    depsgraph.update()
    cloth_world = v1.to_world_coords(cloth, v1.eval_coords(cloth, depsgraph))
    blob_world = v1.to_world_coords(blob, v1.eval_coords(blob, depsgraph))
    return v1.cloth_metrics(cloth_world, blob_world)


def build_scene():
    v1 = load_module(
        "water_blob_v1",
        "experiments/cloth-water-blob-impact-eevee/scene.py",
    )
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
        "WaterBlobV3",
        (v1.BLOB_HALF_X, v1.BLOB_HALF_Y, v1.BLOB_HALF_Z),
        v1.BLOB_Z,
        render=True,
    )
    initial_blob_local = [tuple(v.co) for v in blob.data.vertices]
    initial_blob_world = v1.to_world_coords(blob, initial_blob_local)

    proxy = v1.make_blob(
        base,
        "WaterBlobGuideProxyV3",
        (v1.PROXY_HALF_X, v1.PROXY_HALF_Y, v1.PROXY_HALF_Z),
        v1.PROXY_Z,
        render=False,
    )
    base.add_collision(proxy, thickness=0.012, damping=0.18)
    if hasattr(proxy.collision, "cloth_friction"):
        proxy.collision.cloth_friction = 18.0

    # Pass 1: provisional path.
    guide_cloth = v1.make_cloth(base)
    guide_cloth.name = "WaterGuideClothV3"
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

    # Pass 2: provisional Cloth drives the Soft Body.
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

    # Pass 3: fresh visible Cloth follows a slightly expanded, invisible
    # collision shell that shares the blob's baked shape-key animation.
    shell = make_animated_collision_shell(base, blob)

    final_cloth = v1.make_cloth(base)
    final_cloth.name = "WaterDropClothV3"
    final_mod = v1.add_cloth_physics(final_cloth)

    final_bake = bake_final_cloth(
        scene,
        v1,
        final_cloth,
        final_mod,
        blob,
    )

    bpy.data.objects.remove(shell, do_unlink=True)
    v1.add_render_modifiers(blob, final_cloth)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    peak_frame = int(blob_bake["peak_frame"])
    guide_peak = metric_at(scene, depsgraph, v1, guide_cloth, blob, peak_frame)
    final_peak = final_bake["metrics"][peak_frame]

    guide_gap = guide_peak["center_gap"]
    final_gap = final_peak["center_gap"]
    gap_improvement = (
        guide_gap - final_gap
        if guide_gap is not None and final_gap is not None
        else None
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
            "mode": "three-pass staged coupling with expanded final collision shell",
            "pass_1": "guide cloth -> hidden initial-blob proxy",
            "pass_2": "baked guide cloth -> live soft-body water blob",
            "pass_3": "fresh visible cloth -> expanded shell sharing baked blob animation",
            "bidirectional_feedback": False,
            "true_fluid": False,
            "goal": "reduce V2 cloth-ingestion/interpenetration appearance without reintroducing dependency cycles",
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
            "center_top_drop": blob_bake["center_top_drop"],
        },
        "collision_shell": {
            "name": "WaterBlobCollisionShell",
            "scale": list(SHELL_SCALE),
            "collision_thickness": SHELL_COLLISION_THICKNESS,
            "shares_blob_shape_keys": True,
            "hidden_render": True,
            "removed_after_final_cloth_bake": True,
        },
        "guide_cloth": {
            "simulation_seconds": guide_bake["seconds"],
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
            "min_center_gap_after_contact": final_bake[
                "min_center_gap_after_contact"
            ],
            "max_center_gap_after_contact": final_bake[
                "max_center_gap_after_contact"
            ],
        },
        "comparison": {
            "v1_gap_at_blob_peak": 1.264967,
            "v2_gap_at_blob_peak": 0.059224,
            "v2_max_positive_gap_after_contact": 0.161919,
            "v3_guide_gap_at_blob_peak": (
                round(float(guide_gap), 6) if guide_gap is not None else None
            ),
            "v3_final_gap_at_blob_peak": (
                round(float(final_gap), 6) if final_gap is not None else None
            ),
            "v3_gap_improvement_from_guide": (
                round(float(gap_improvement), 6)
                if gap_improvement is not None else None
            ),
        },
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"WATER_V3_BLOB_PEAK_FRAME={peak_frame}")
    print(f"WATER_V3_GUIDE_GAP_AT_PEAK={guide_gap}")
    print(f"WATER_V3_FINAL_GAP_AT_PEAK={final_gap}")
    print(f"WATER_V3_MIN_GAP_AFTER_CONTACT={final_bake['min_center_gap_after_contact']}")
    print(f"WATER_V3_MAX_GAP_AFTER_CONTACT={final_bake['max_center_gap_after_contact']}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

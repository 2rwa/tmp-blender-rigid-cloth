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

EXPERIMENT = "mantaflow-liquid-baked-cloth-effector-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"
PREVIEW_PATH = OUTPUT_DIR / "preview.png"
VIDEO_STEM = OUTPUT_DIR / EXPERIMENT
VIDEO_PATH = OUTPUT_DIR / f"{EXPERIMENT}.mp4"
CACHE_DIR = OUTPUT_DIR / "mantaflow-baked-cloth-cache"

FRAME_START = 1
FRAME_END = 96
FPS = 24
PREVIEW_FRAME = 48
RES_X = 480
RES_Y = 360
DOMAIN_RESOLUTION = 48

CLOTH_W = 3.75
CLOTH_D = 3.15
CLOTH_NX = 41
CLOTH_NY = 35
CLOTH_Z = 1.72


def load_baseline():
    path = ROOT / "experiments/mantaflow-liquid-cloth-effector-eevee/scene.py"
    spec = importlib.util.spec_from_file_location("mantaflow_static_baseline", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load baseline experiment: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.EXPERIMENT = EXPERIMENT
    module.BLEND_PATH = BLEND_PATH
    module.REPORT_PATH = REPORT_PATH
    module.PREVIEW_PATH = PREVIEW_PATH
    module.VIDEO_STEM = VIDEO_STEM
    module.VIDEO_PATH = VIDEO_PATH
    module.CACHE_DIR = CACHE_DIR
    module.FRAME_START = FRAME_START
    module.FRAME_END = FRAME_END
    module.FPS = FPS
    module.PREVIEW_FRAME = PREVIEW_FRAME
    module.RES_X = RES_X
    module.RES_Y = RES_Y
    module.DOMAIN_RESOLUTION = DOMAIN_RESOLUTION
    return module


def make_dynamic_cloth(base):
    verts = []
    faces = []
    pin_indices = []

    for j in range(CLOTH_NY):
        y = -CLOTH_D * 0.5 + CLOTH_D * j / (CLOTH_NY - 1)
        for i in range(CLOTH_NX):
            x = -CLOTH_W * 0.5 + CLOTH_W * i / (CLOTH_NX - 1)
            z = CLOTH_Z + 0.008 * math.sin(i * 0.51) * math.sin(j * 0.47)
            idx = len(verts)
            verts.append((x, y, z))
            if i in (0, CLOTH_NX - 1) or j in (0, CLOTH_NY - 1):
                pin_indices.append(idx)

    for j in range(CLOTH_NY - 1):
        for i in range(CLOTH_NX - 1):
            a = j * CLOTH_NX + i
            faces.append((a, a + 1, a + CLOTH_NX + 1, a + CLOTH_NX))

    mesh = bpy.data.meshes.new("BakedFluidClothMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    cloth = bpy.data.objects.new("BakedDynamicClothEffector", mesh)
    bpy.context.collection.objects.link(cloth)
    cloth.data.materials.append(
        base.make_material(
            "BakedFluidClothMaterial",
            (0.72, 0.052, 0.032, 1.0),
            roughness=0.74,
        )
    )

    pin = cloth.vertex_groups.new(name="PinnedBorder")
    pin.add(pin_indices, 1.0, "REPLACE")

    mod = cloth.modifiers.new("ClothPhysics", type="CLOTH")
    s = mod.settings
    s.quality = 9
    s.mass = 0.28
    s.air_damping = 1.4
    s.tension_stiffness = 28.0
    s.compression_stiffness = 28.0
    s.shear_stiffness = 20.0
    s.bending_stiffness = 0.24
    s.tension_damping = 7.0
    s.compression_damping = 7.0
    s.shear_damping = 7.0
    s.bending_damping = 3.0
    s.vertex_group_mass = "PinnedBorder"
    s.pin_stiffness = 1.0

    c = mod.collision_settings
    c.use_collision = True
    c.collision_quality = 5
    c.distance_min = 0.012
    c.friction = 8.0
    c.use_self_collision = True
    c.self_distance_min = 0.010
    c.self_friction = 4.0

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1

    return cloth, mod, len(pin_indices)


def evaluated_coords(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    coords = [tuple(v.co) for v in mesh.vertices]
    eval_obj.to_mesh_clear()
    return coords


def center_mean_z(coords):
    region = [
        co for co in coords
        if abs(co[0]) <= 0.60 and abs(co[1]) <= 0.50
    ]
    if not region:
        return None
    return sum(co[2] for co in region) / len(region)


def bake_cloth(scene, cloth, mod):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in cloth.data.vertices]
    frames = {}
    sample_frames = {1, 12, 24, 48, 72, 96}
    center_samples = {}

    max_displacement = 0.0
    max_frame = FRAME_START
    min_z = float("inf")
    min_z_frame = FRAME_START

    started = time.perf_counter()
    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()
        coords = evaluated_coords(cloth, depsgraph)
        if len(coords) != len(basis):
            raise RuntimeError(
                f"cloth topology changed at frame {frame}: "
                f"{len(coords)} != {len(basis)}"
            )
        frames[frame] = coords

        frame_max = 0.0
        for base_co, co in zip(basis, coords):
            dx = co[0] - base_co[0]
            dy = co[1] - base_co[1]
            dz = co[2] - base_co[2]
            frame_max = max(
                frame_max,
                math.sqrt(dx * dx + dy * dy + dz * dz),
            )

        if frame_max > max_displacement:
            max_displacement = frame_max
            max_frame = frame

        frame_min = min(co[2] for co in coords)
        if frame_min < min_z:
            min_z = frame_min
            min_z_frame = frame

        if frame in sample_frames:
            center_samples[str(frame)] = center_mean_z(coords)

        if not math.isfinite(frame_max) or frame_max > 8.0:
            raise RuntimeError(
                f"cloth numerical instability at frame {frame}: {frame_max}"
            )

        if frame % 12 == 0:
            print(f"MANTAFLOW_BAKED_CLOTH_FRAME={frame}")
            print(f"MANTAFLOW_BAKED_CLOTH_MAX_DISPLACEMENT={frame_max:.6f}")
            print(
                f"MANTAFLOW_BAKED_CLOTH_CENTER_Z="
                f"{center_samples.get(str(frame))}"
            )

    seconds = time.perf_counter() - started

    cloth.modifiers.remove(mod)
    cloth.shape_key_add(name="Basis", from_mix=False)

    for frame in range(FRAME_START, FRAME_END + 1):
        key = cloth.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
        for idx, co in enumerate(frames[frame]):
            key.data[idx].co = co

        for key_frame, value in (
            (frame - 1, 0.0),
            (frame, 1.0),
            (frame + 1, 0.0),
        ):
            if FRAME_START <= key_frame <= FRAME_END:
                key.value = value
                key.keyframe_insert(data_path="value", frame=key_frame)

    if cloth.data.shape_keys and cloth.data.shape_keys.animation_data:
        action = cloth.data.shape_keys.animation_data.action
        if action:
            for fc in action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

    scene.frame_set(FRAME_START)

    return {
        "simulation_seconds": round(seconds, 3),
        "baked_frames": len(frames),
        "shape_key_count": len(cloth.data.shape_keys.key_blocks),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_z": round(min_z, 6),
        "min_z_frame": min_z_frame,
        "center_z_samples": {
            k: (round(float(v), 6) if v is not None else None)
            for k, v in center_samples.items()
        },
    }


def add_fluid_effector_and_render_modifiers(cloth):
    fluid = cloth.modifiers.new("FluidEffector", type="FLUID")
    fluid.fluid_type = "EFFECTOR"
    bpy.context.view_layer.objects.active = cloth
    cloth.select_set(True)
    bpy.context.view_layer.update()

    eff = fluid.effector_settings
    if eff is None:
        raise RuntimeError("Fluid effector settings were not created")
    eff.effector_type = "COLLISION"
    eff.use_effector = True
    eff.use_plane_init = True
    eff.surface_distance = 1.0
    eff.subframes = 3
    eff.velocity_factor = 1.0

    solid = cloth.modifiers.new("RenderThickness", type="SOLIDIFY")
    solid.thickness = 0.026
    solid.offset = 0.0

    sub = cloth.modifiers.new("RenderSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1

    return fluid


def build_scene():
    base = load_baseline()
    base.clear_scene()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.gravity = (0.0, 0.0, -9.81)

    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.004, 0.007, 0.015, 1.0)
    bg.inputs["Strength"].default_value = 0.16

    base.make_floor_visual()
    cloth, cloth_mod, pin_count = make_dynamic_cloth(base)
    base.setup_camera_lights(scene)

    # Phase 1: solve Cloth independently of the liquid and bake it to shape keys.
    cloth_bake = bake_cloth(scene, cloth, cloth_mod)

    # Phase 2: turn that already-baked deforming surface into a Mantaflow
    # effector. The fluid sees the animated Cloth geometry, but the Cloth
    # never reads fluid pressure/force in this experiment.
    add_fluid_effector_and_render_modifiers(cloth)

    source = base.make_flow_source()
    # Lift the initial volume slightly so it meets the Cloth while the
    # hammock is still settling.
    source.location.z = 3.86

    domain, domain_mod = base.make_domain()

    scene.frame_set(FRAME_START)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    bpy.ops.object.select_all(action="DESELECT")
    domain.select_set(True)
    bpy.context.view_layer.objects.active = domain
    bpy.context.view_layer.update()

    settings = domain_mod.domain_settings
    started = time.perf_counter()
    result = bpy.ops.fluid.bake_all()
    bake_seconds = time.perf_counter() - started
    if "FINISHED" not in result:
        raise RuntimeError(f"Mantaflow bake_all failed: {result}")

    bpy.context.view_layer.update()

    cache_files = [p for p in CACHE_DIR.rglob("*") if p.is_file()]
    cache_bytes = sum(p.stat().st_size for p in cache_files)

    fluid_samples = base.fluid_mesh_stats(
        scene,
        domain,
        [1, 12, 24, 48, 72, 96],
    )

    report = {
        "experiment": EXPERIMENT,
        "engine": scene.render.engine,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "fps": FPS,
        "resolution": [RES_X, RES_Y],
        "true_fluid": True,
        "fluid_solver": "Mantaflow liquid / FLIP",
        "coupling": {
            "mode": "two-phase one-way deforming Cloth -> Mantaflow liquid",
            "phase_1": "live Cloth -> baked shape-key animation",
            "phase_2": "baked deforming Cloth -> Mantaflow Fluid Effector",
            "liquid_reads_deforming_cloth": True,
            "cloth_reads_liquid_force": False,
            "cloth_is_dynamic_before_bake": True,
            "true_two_way_fsi": False,
        },
        "cloth": {
            "name": cloth.name,
            "vertex_count": len(cloth.data.vertices),
            "face_count": len(cloth.data.polygons),
            "pin_vertex_count": pin_count,
            "baked_frames": cloth_bake["baked_frames"],
            "shape_key_count": cloth_bake["shape_key_count"],
            "simulation_seconds": cloth_bake["simulation_seconds"],
            "max_displacement": cloth_bake["max_displacement"],
            "max_displacement_frame": cloth_bake["max_displacement_frame"],
            "min_z": cloth_bake["min_z"],
            "min_z_frame": cloth_bake["min_z_frame"],
            "center_z_samples": cloth_bake["center_z_samples"],
            "fluid_effector_planar": True,
            "fluid_effector_subframes": 3,
        },
        "domain": {
            "name": domain.name,
            "resolution_max": DOMAIN_RESOLUTION,
            "cache_type": settings.cache_type,
            "cache_directory": str(CACHE_DIR.relative_to(ROOT)),
            "cache_baked_any": bool(settings.has_cache_baked_any),
            "cache_baked_data": bool(settings.has_cache_baked_data),
            "cache_baked_mesh": bool(settings.has_cache_baked_mesh),
            "bake_seconds": round(bake_seconds, 3),
            "cache_file_count": len(cache_files),
            "cache_bytes": cache_bytes,
        },
        "flow": {
            "name": source.name,
            "behavior": "GEOMETRY",
            "type": "LIQUID",
            "initial_center": list(source.location),
        },
        "fluid_mesh_samples": fluid_samples,
        "blend": BLEND_PATH.name,
        "video": VIDEO_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    base.render_outputs(scene)

    print(f"MANTAFLOW_DYNAMIC_CLOTH_SIM_SECONDS={cloth_bake['simulation_seconds']}")
    print(f"MANTAFLOW_DYNAMIC_CLOTH_MAX_DISPLACEMENT={cloth_bake['max_displacement']}")
    print(f"MANTAFLOW_DYNAMIC_BAKE_SECONDS={bake_seconds:.3f}")
    print(f"MANTAFLOW_DYNAMIC_CACHE_FILES={len(cache_files)}")
    print(f"MANTAFLOW_DYNAMIC_CACHE_BYTES={cache_bytes}")
    for frame, stat in fluid_samples.items():
        print(
            f"MANTAFLOW_DYNAMIC_SAMPLE_{frame}_VERTICES="
            f"{stat['vertex_count']}"
        )
    print(f"VIDEO_PATH={VIDEO_PATH}")
    print(f"PREVIEW_PATH={PREVIEW_PATH}")


if __name__ == "__main__":
    build_scene()

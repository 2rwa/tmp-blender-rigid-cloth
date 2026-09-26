from __future__ import annotations

import importlib.util
import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT = "cloth-water-blob-impact-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START, FRAME_END, FPS = 1, 192, 24
RES_X, RES_Y = 480, 360

CLOTH_GRID_X, CLOTH_GRID_Y = 35, 31
CLOTH_WIDTH, CLOTH_DEPTH, CLOTH_Z = 3.80, 3.20, 3.35

BLOB_HALF_X, BLOB_HALF_Y, BLOB_HALF_Z = 1.55, 1.30, 0.75
BLOB_Z = 0.88

# The Cloth is solved against a smaller hidden support first. Replaying that
# baked Cloth against the full-size live blob creates a controlled overlap
# that can deform the Soft Body without a live dependency cycle.
PROXY_HALF_X, PROXY_HALF_Y, PROXY_HALF_Z = 1.46, 1.22, 0.62
PROXY_Z = 0.82

CENTER_HALF_X, CENTER_HALF_Y = 0.60, 0.50


def load_base():
    path = ROOT / "experiments/softbody-jelly-cube-ball-drop-eevee/scene.py"
    spec = importlib.util.spec_from_file_location("water_blob_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load base experiment: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FRAME_START = FRAME_START
    module.FRAME_END = FRAME_END
    module.FPS = FPS
    module.RES_X = RES_X
    module.RES_Y = RES_Y
    return module


def make_water_material(base):
    mat = bpy.data.materials.new("WaterBlobMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    bsdf.inputs["Base Color"].default_value = (0.018, 0.24, 0.62, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.12
    bsdf.inputs["Metallic"].default_value = 0.0
    base.set_bsdf_input(bsdf, ("IOR",), 1.333)
    base.set_bsdf_input(bsdf, ("Transmission Weight", "Transmission"), 0.52)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.3
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.45

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.01, 0.08, 0.28, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (0.05, 0.72, 0.98, 1.0)

    tex = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.85, 0.85, 1.25)

    links.new(tex.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def make_blob(base, name, half_extents, z, render=True):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=18,
        radius=1.0,
        location=(0.0, 0.0, z),
        scale=half_extents,
    )
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.hide_render = not render
    if render:
        obj.data.materials.append(make_water_material(base))
    return obj


def add_water_softbody(blob):
    mod = blob.modifiers.new(name="WaterBlobSoftBody", type="SOFT_BODY")
    s = mod.settings
    s.use_edges = True
    s.use_stiff_quads = False
    s.pull = 0.26
    s.push = 0.26
    s.shear = 0.15
    s.bend = 0.18
    s.damping = 10.0
    s.friction = 5.0
    s.mass = 1.35
    s.speed = 0.55
    s.gravity = 0.0
    s.plastic = 0

    s.use_goal = True
    s.goal_default = 0.38
    s.goal_spring = 0.40
    s.goal_friction = 10.0
    s.goal_min = 0.0
    s.goal_max = 1.0

    s.use_edge_collision = False
    s.use_face_collision = False
    s.use_self_collision = False
    s.use_auto_step = True
    s.step_min = 2
    s.step_max = 16
    s.error_threshold = 0.04

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1
    return mod


def make_cloth(base):
    verts, faces = [], []
    for j in range(CLOTH_GRID_Y):
        y = -CLOTH_DEPTH * 0.5 + CLOTH_DEPTH * j / (CLOTH_GRID_Y - 1)
        for i in range(CLOTH_GRID_X):
            x = -CLOTH_WIDTH * 0.5 + CLOTH_WIDTH * i / (CLOTH_GRID_X - 1)
            z = CLOTH_Z + 0.012 * math.sin(i * 0.49) * math.sin(j * 0.43)
            verts.append((x, y, z))

    for j in range(CLOTH_GRID_Y - 1):
        for i in range(CLOTH_GRID_X - 1):
            a = j * CLOTH_GRID_X + i
            faces.append((a, a + 1, a + CLOTH_GRID_X + 1, a + CLOTH_GRID_X))

    mesh = bpy.data.meshes.new("WaterDropClothMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    cloth = bpy.data.objects.new("WaterDropCloth", mesh)
    bpy.context.collection.objects.link(cloth)
    cloth.data.materials.append(
        base.make_material(
            "WaterDropClothMaterial",
            (0.82, 0.11, 0.08),
            roughness=0.72,
            metallic=0.02,
        )
    )
    return cloth


def add_cloth_physics(cloth):
    mod = cloth.modifiers.new(name="ClothPhysics", type="CLOTH")
    s = mod.settings
    s.quality = 8
    s.mass = 0.30
    s.air_damping = 1.6
    s.tension_stiffness = 24.0
    s.compression_stiffness = 24.0
    s.shear_stiffness = 18.0
    s.bending_stiffness = 0.20
    s.tension_damping = 7.0
    s.compression_damping = 7.0
    s.shear_damping = 7.0
    s.bending_damping = 3.0

    c = mod.collision_settings
    c.use_collision = True
    c.collision_quality = 6
    c.distance_min = 0.010
    c.friction = 12.0
    c.use_self_collision = True
    c.self_distance_min = 0.010
    c.self_friction = 6.0

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1
    return mod


def eval_coords(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    coords = [tuple(v.co) for v in mesh.vertices]
    eval_obj.to_mesh_clear()
    return coords


def to_world_coords(obj, coords):
    matrix = obj.matrix_world.copy()
    return [tuple(matrix @ Vector(co)) for co in coords]


def center_top(coords):
    region = [
        co for co in coords
        if abs(co[0]) <= CENTER_HALF_X and abs(co[1]) <= CENTER_HALF_Y
    ]
    return max((co[2] for co in region), default=None)


def cloth_metrics(cloth_coords, blob_coords):
    coverage = (
        sum(
            1 for co in cloth_coords
            if abs(co[0]) <= BLOB_HALF_X and abs(co[1]) <= BLOB_HALF_Y
        )
        / len(cloth_coords)
    )
    center = [
        co for co in cloth_coords
        if abs(co[0]) <= CENTER_HALF_X and abs(co[1]) <= CENTER_HALF_Y
    ]
    cloth_center_z = (
        sum(co[2] for co in center) / len(center)
        if center else None
    )
    blob_top = center_top(blob_coords)
    gap = (
        cloth_center_z - blob_top
        if cloth_center_z is not None and blob_top is not None
        else None
    )
    return {
        "coverage": coverage,
        "cloth_center_z": cloth_center_z,
        "blob_center_top_z": blob_top,
        "center_gap": gap,
    }


def bake_shape_keys(obj, frames):
    obj.shape_key_add(name="Basis", from_mix=False)
    for frame in range(FRAME_START, FRAME_END + 1):
        key = obj.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
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

    if obj.data.shape_keys and obj.data.shape_keys.animation_data:
        action = obj.data.shape_keys.animation_data.action
        if action:
            for fc in action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"


def bake_cloth_pass(scene, cloth, cloth_mod, live_blob_coords):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in cloth.data.vertices]
    frames = {}
    metrics = {}

    max_displacement = 0.0
    max_frame = FRAME_START
    min_z = float("inf")
    min_z_frame = FRAME_START
    first_contact_frame = None
    started = time.perf_counter()

    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()
        coords = eval_coords(cloth, depsgraph)
        if len(coords) != len(basis):
            raise RuntimeError(f"cloth topology changed at frame {frame}")

        frames[frame] = coords
        cloth_world = to_world_coords(cloth, coords)
        metric = cloth_metrics(cloth_world, live_blob_coords)
        metrics[frame] = metric

        frame_max = 0.0
        for base, co in zip(basis, coords):
            dx, dy, dz = co[0]-base[0], co[1]-base[1], co[2]-base[2]
            frame_max = max(frame_max, math.sqrt(dx*dx + dy*dy + dz*dz))

        if frame_max > max_displacement:
            max_displacement, max_frame = frame_max, frame

        frame_min_z = min(co[2] for co in coords)
        if frame_min_z < min_z:
            min_z, min_z_frame = frame_min_z, frame

        gap = metric["center_gap"]
        if (
            first_contact_frame is None
            and gap is not None
            and gap <= 0.12
            and metric["coverage"] >= 0.40
        ):
            first_contact_frame = frame

        if not math.isfinite(frame_max) or frame_max > 16.0:
            raise RuntimeError(
                f"cloth numerical instability at frame {frame}: {frame_max}"
            )

        if frame % 12 == 0:
            print(f"WATER_CLOTH_PASS_FRAME={frame}")
            print(f"WATER_CLOTH_MAX_DISPLACEMENT={frame_max:.6f}")
            print(f"WATER_CLOTH_COVERAGE={metric['coverage']:.6f}")
            print(f"WATER_CLOTH_LIVE_BLOB_GAP={gap}")

    seconds = time.perf_counter() - started
    cloth.modifiers.remove(cloth_mod)
    bake_shape_keys(cloth, frames)
    scene.frame_set(FRAME_START)

    return {
        "frames": frames,
        "metrics": metrics,
        "seconds": round(seconds, 3),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_z": round(min_z, 6),
        "min_z_frame": min_z_frame,
        "first_contact_frame": first_contact_frame,
    }


def bake_blob_pass(scene, blob, soft_mod, cloth, cloth_frames, initial_blob_coords):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in blob.data.vertices]
    frames = {}
    metrics = {}

    max_displacement = 0.0
    peak_frame = FRAME_START
    started = time.perf_counter()

    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()
        coords = eval_coords(blob, depsgraph)
        if len(coords) != len(basis):
            raise RuntimeError(f"blob topology changed at frame {frame}")

        frames[frame] = coords
        cloth_world = to_world_coords(cloth, cloth_frames[frame])
        blob_world = to_world_coords(blob, coords)
        metrics[frame] = cloth_metrics(cloth_world, blob_world)

        frame_max = 0.0
        for base, co in zip(basis, coords):
            dx, dy, dz = co[0]-base[0], co[1]-base[1], co[2]-base[2]
            frame_max = max(frame_max, math.sqrt(dx*dx + dy*dy + dz*dz))

        if frame_max > max_displacement:
            max_displacement, peak_frame = frame_max, frame

        if not math.isfinite(frame_max) or frame_max > 6.0:
            raise RuntimeError(
                f"water blob numerical instability at frame {frame}: {frame_max}"
            )

        if frame % 12 == 0:
            metric = metrics[frame]
            print(f"WATER_BLOB_PASS_FRAME={frame}")
            print(f"WATER_BLOB_MAX_DISPLACEMENT={frame_max:.6f}")
            print(f"WATER_BLOB_CENTER_GAP={metric['center_gap']}")

    seconds = time.perf_counter() - started
    peak_metric = metrics[peak_frame]

    initial_top = center_top(to_world_coords(blob, initial_blob_coords))
    peak_top = center_top(to_world_coords(blob, frames[peak_frame]))
    center_top_drop = (
        initial_top - peak_top
        if initial_top is not None and peak_top is not None
        else None
    )

    min_gap_frame = min(
        (
            (frame, m["center_gap"])
            for frame, m in metrics.items()
            if m["center_gap"] is not None
        ),
        key=lambda item: abs(item[1]),
        default=(None, None),
    )

    blob.modifiers.remove(soft_mod)
    bake_shape_keys(blob, frames)
    scene.frame_set(FRAME_START)

    return {
        "seconds": round(seconds, 3),
        "max_displacement": round(max_displacement, 6),
        "peak_frame": peak_frame,
        "coverage_at_peak": round(float(peak_metric["coverage"]), 6),
        "center_gap_at_peak": (
            round(float(peak_metric["center_gap"]), 6)
            if peak_metric["center_gap"] is not None else None
        ),
        "initial_center_top_z": (
            round(float(initial_top), 6) if initial_top is not None else None
        ),
        "center_top_z_at_peak": (
            round(float(peak_top), 6) if peak_top is not None else None
        ),
        "center_top_drop": (
            round(float(center_top_drop), 6)
            if center_top_drop is not None else None
        ),
        "min_abs_center_gap_frame": min_gap_frame[0],
        "min_abs_center_gap": (
            round(float(min_gap_frame[1]), 6)
            if min_gap_frame[1] is not None else None
        ),
    }


def remove_collision_modifier(obj):
    for mod in list(obj.modifiers):
        if mod.type == "COLLISION":
            obj.modifiers.remove(mod)


def add_render_modifiers(blob, cloth):
    blob_sub = blob.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    blob_sub.subdivision_type = "CATMULL_CLARK"
    blob_sub.levels = blob_sub.render_levels = 1

    solid = cloth.modifiers.new(name="FabricThickness", type="SOLIDIFY")
    solid.thickness = 0.022
    solid.offset = 0.0

    cloth_sub = cloth.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    cloth_sub.subdivision_type = "CATMULL_CLARK"
    cloth_sub.levels = cloth_sub.render_levels = 1


def build_scene():
    base = load_base()
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

    blob = make_blob(
        base,
        "WaterBlob",
        (BLOB_HALF_X, BLOB_HALF_Y, BLOB_HALF_Z),
        BLOB_Z,
        render=True,
    )
    initial_blob_coords = [tuple(v.co) for v in blob.data.vertices]
    initial_blob_world_coords = to_world_coords(blob, initial_blob_coords)

    proxy = make_blob(
        base,
        "WaterBlobClothProxy",
        (PROXY_HALF_X, PROXY_HALF_Y, PROXY_HALF_Z),
        PROXY_Z,
        render=False,
    )
    base.add_collision(proxy, thickness=0.012, damping=0.18)
    if hasattr(proxy.collision, "cloth_friction"):
        proxy.collision.cloth_friction = 18.0

    cloth = make_cloth(base)
    cloth_mod = add_cloth_physics(cloth)

    base.setup_camera_and_lights(scene)

    # Pass 1: Cloth falls against a smaller hidden proxy. The full WaterBlob
    # is not a Collision object, so there is no Cloth/Soft Body cycle.
    cloth_bake = bake_cloth_pass(
        scene,
        cloth,
        cloth_mod,
        initial_blob_world_coords,
    )

    # The proxy has served its purpose. Remove it before the live Soft Body
    # pass so it cannot constrain or overlap the WaterBlob.
    bpy.data.objects.remove(proxy, do_unlink=True)

    # The baked Cloth now becomes a deterministic animated collider.
    base.add_collision(cloth, thickness=0.010, damping=0.14)
    if hasattr(cloth.collision, "cloth_friction"):
        cloth.collision.cloth_friction = 14.0

    soft_mod = add_water_softbody(blob)

    # Pass 2: live Soft Body reads the baked Cloth. This preserves a
    # Cloth->blob response without a dependency cycle.
    blob_bake = bake_blob_pass(
        scene,
        blob,
        soft_mod,
        cloth,
        cloth_bake["frames"],
        initial_blob_coords,
    )

    remove_collision_modifier(cloth)
    add_render_modifiers(blob, cloth)

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
            "mode": "two-pass staged cloth-to-softbody coupling",
            "pass_1": "cloth -> smaller hidden initial-blob proxy",
            "pass_2": "baked cloth -> live soft-body water blob",
            "cloth_reads_initial_blob_proxy": True,
            "blob_reads_baked_cloth_collision": True,
            "bidirectional_feedback": False,
            "true_fluid": False,
            "direct_live_mutual_collision_attempt": "failed with Blender dependency cycle in run 5",
        },
        "blob": {
            "name": blob.name,
            "half_extents": [BLOB_HALF_X, BLOB_HALF_Y, BLOB_HALF_Z],
            "vertex_count": len(blob.data.vertices),
            "face_count": len(blob.data.polygons),
            "baked_shape_keys": FRAME_END - FRAME_START + 1,
            "shape_key_count": len(blob.data.shape_keys.key_blocks),
            "simulation_seconds": blob_bake["seconds"],
            "max_displacement": blob_bake["max_displacement"],
            "max_displacement_frame": blob_bake["peak_frame"],
            "initial_center_top_z": blob_bake["initial_center_top_z"],
            "center_top_z_at_peak": blob_bake["center_top_z_at_peak"],
            "center_top_drop": blob_bake["center_top_drop"],
        },
        "cloth": {
            "name": cloth.name,
            "grid_x": CLOTH_GRID_X,
            "grid_y": CLOTH_GRID_Y,
            "vertex_count": len(cloth.data.vertices),
            "face_count": len(cloth.data.polygons),
            "self_collision": True,
            "baked_shape_keys": FRAME_END - FRAME_START + 1,
            "shape_key_count": len(cloth.data.shape_keys.key_blocks),
            "simulation_seconds": cloth_bake["seconds"],
            "max_displacement": cloth_bake["max_displacement"],
            "max_displacement_frame": cloth_bake["max_displacement_frame"],
            "min_vertex_z": cloth_bake["min_z"],
            "min_vertex_z_frame": cloth_bake["min_z_frame"],
            "first_live_blob_contact_frame": cloth_bake["first_contact_frame"],
        },
        "interaction": {
            "coverage_at_blob_peak": blob_bake["coverage_at_peak"],
            "center_gap_at_blob_peak": blob_bake["center_gap_at_peak"],
            "min_abs_center_gap": blob_bake["min_abs_center_gap"],
            "min_abs_center_gap_frame": blob_bake["min_abs_center_gap_frame"],
        },
        "proxy": {
            "name": "WaterBlobClothProxy",
            "half_extents": [PROXY_HALF_X, PROXY_HALF_Y, PROXY_HALF_Z],
            "z": PROXY_Z,
            "removed_before_blob_pass": True,
        },
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"WATER_FIRST_CONTACT_FRAME={cloth_bake['first_contact_frame']}")
    print(f"WATER_BLOB_MAX_DISPLACEMENT={blob_bake['max_displacement']:.6f}")
    print(f"WATER_BLOB_PEAK_FRAME={blob_bake['peak_frame']}")
    print(f"WATER_BLOB_CENTER_TOP_DROP={blob_bake['center_top_drop']}")
    print(f"WATER_COVERAGE_AT_BLOB_PEAK={blob_bake['coverage_at_peak']:.6f}")
    print(f"WATER_MIN_ABS_CENTER_GAP={blob_bake['min_abs_center_gap']}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

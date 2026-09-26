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

EXPERIMENT = "cloth-water-blob-impact-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START = 1
FRAME_END = 192
FPS = 24
RES_X = 480
RES_Y = 360

CLOTH_GRID_X = 35
CLOTH_GRID_Y = 31
CLOTH_WIDTH = 3.80
CLOTH_DEPTH = 3.20
CLOTH_Z = 3.35

BLOB_HALF_X = 1.55
BLOB_HALF_Y = 1.30
BLOB_HALF_Z = 0.75
BLOB_Z = 0.88

CENTER_HALF_X = 0.60
CENTER_HALF_Y = 0.50


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


def make_water_blob(base):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=18,
        radius=1.0,
        location=(0.0, 0.0, BLOB_Z),
        scale=(BLOB_HALF_X, BLOB_HALF_Y, BLOB_HALF_Z),
    )
    blob = bpy.context.object
    blob.name = "WaterBlob"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    for poly in blob.data.polygons:
        poly.use_smooth = True

    blob.data.materials.append(make_water_material(base))
    return blob


def add_water_softbody(blob):
    mod = blob.modifiers.new(name="WaterBlobSoftBody", type="SOFT_BODY")
    s = mod.settings
    s.use_edges = True
    s.use_stiff_quads = False
    s.pull = 0.22
    s.push = 0.22
    s.shear = 0.13
    s.bend = 0.14
    s.damping = 9.0
    s.friction = 5.0
    s.mass = 1.35
    s.speed = 0.58
    s.gravity = 0.0
    s.plastic = 0

    s.use_goal = True
    s.goal_default = 0.30
    s.goal_spring = 0.34
    s.goal_friction = 9.0
    s.goal_min = 0.0
    s.goal_max = 1.0

    s.use_edge_collision = False
    s.use_face_collision = False
    s.use_self_collision = False
    s.use_auto_step = True
    s.step_min = 2
    s.step_max = 18
    s.error_threshold = 0.035

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1
    return mod


def make_cloth(base):
    verts = []
    faces = []

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


def region_metrics(blob_coords, cloth_coords):
    coverage = (
        sum(
            1
            for co in cloth_coords
            if abs(co[0]) <= BLOB_HALF_X and abs(co[1]) <= BLOB_HALF_Y
        )
        / len(cloth_coords)
    )

    cloth_center = [
        co for co in cloth_coords
        if abs(co[0]) <= CENTER_HALF_X and abs(co[1]) <= CENTER_HALF_Y
    ]
    blob_center = [
        co for co in blob_coords
        if abs(co[0]) <= CENTER_HALF_X and abs(co[1]) <= CENTER_HALF_Y
    ]

    cloth_center_z = (
        sum(co[2] for co in cloth_center) / len(cloth_center)
        if cloth_center else None
    )
    blob_center_top_z = (
        max(co[2] for co in blob_center)
        if blob_center else None
    )
    center_gap = (
        cloth_center_z - blob_center_top_z
        if cloth_center_z is not None and blob_center_top_z is not None
        else None
    )

    return {
        "coverage": coverage,
        "cloth_center_z": cloth_center_z,
        "blob_center_top_z": blob_center_top_z,
        "center_gap": center_gap,
        "cloth_center_count": len(cloth_center),
        "blob_center_count": len(blob_center),
    }


def bake_coupled(scene, blob, soft_mod, cloth, cloth_mod):
    depsgraph = bpy.context.evaluated_depsgraph_get()

    blob_basis = [tuple(v.co) for v in blob.data.vertices]
    cloth_basis = [tuple(v.co) for v in cloth.data.vertices]

    blob_frames = {}
    cloth_frames = {}
    metrics_by_frame = {}

    blob_max_displacement = 0.0
    blob_peak_frame = FRAME_START
    cloth_max_displacement = 0.0
    cloth_peak_frame = FRAME_START
    cloth_min_z = float("inf")
    cloth_min_z_frame = FRAME_START

    started = time.perf_counter()
    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()

        eval_blob = blob.evaluated_get(depsgraph)
        blob_mesh = eval_blob.to_mesh()
        if len(blob_mesh.vertices) != len(blob_basis):
            raise RuntimeError(
                f"blob topology changed at frame {frame}: "
                f"{len(blob_mesh.vertices)} != {len(blob_basis)}"
            )
        blob_coords = [tuple(v.co) for v in blob_mesh.vertices]
        blob_frames[frame] = blob_coords
        eval_blob.to_mesh_clear()

        eval_cloth = cloth.evaluated_get(depsgraph)
        cloth_mesh = eval_cloth.to_mesh()
        if len(cloth_mesh.vertices) != len(cloth_basis):
            raise RuntimeError(
                f"cloth topology changed at frame {frame}: "
                f"{len(cloth_mesh.vertices)} != {len(cloth_basis)}"
            )
        cloth_coords = [tuple(v.co) for v in cloth_mesh.vertices]
        cloth_frames[frame] = cloth_coords
        eval_cloth.to_mesh_clear()

        blob_frame_max = 0.0
        for base_co, co in zip(blob_basis, blob_coords):
            dx = co[0] - base_co[0]
            dy = co[1] - base_co[1]
            dz = co[2] - base_co[2]
            blob_frame_max = max(
                blob_frame_max,
                math.sqrt(dx * dx + dy * dy + dz * dz),
            )

        cloth_frame_max = 0.0
        for base_co, co in zip(cloth_basis, cloth_coords):
            dx = co[0] - base_co[0]
            dy = co[1] - base_co[1]
            dz = co[2] - base_co[2]
            cloth_frame_max = max(
                cloth_frame_max,
                math.sqrt(dx * dx + dy * dy + dz * dz),
            )

        frame_cloth_min_z = min(co[2] for co in cloth_coords)
        metrics_by_frame[frame] = region_metrics(blob_coords, cloth_coords)

        if blob_frame_max > blob_max_displacement:
            blob_max_displacement = blob_frame_max
            blob_peak_frame = frame
        if cloth_frame_max > cloth_max_displacement:
            cloth_max_displacement = cloth_frame_max
            cloth_peak_frame = frame
        if frame_cloth_min_z < cloth_min_z:
            cloth_min_z = frame_cloth_min_z
            cloth_min_z_frame = frame

        if not math.isfinite(blob_frame_max) or blob_frame_max > 8.0:
            raise RuntimeError(
                f"water blob numerical instability at frame {frame}: "
                f"max displacement={blob_frame_max}"
            )
        if not math.isfinite(cloth_frame_max) or cloth_frame_max > 16.0:
            raise RuntimeError(
                f"cloth numerical instability at frame {frame}: "
                f"max displacement={cloth_frame_max}"
            )

        if frame % 12 == 0:
            m = metrics_by_frame[frame]
            print(f"WATER_CLOTH_SIM_FRAME={frame}")
            print(f"WATER_BLOB_MAX_DISPLACEMENT={blob_frame_max:.6f}")
            print(f"WATER_CLOTH_MAX_DISPLACEMENT={cloth_frame_max:.6f}")
            print(f"WATER_CLOTH_COVERAGE={m['coverage']:.6f}")
            print(f"WATER_CENTER_GAP={m['center_gap']}")

    simulation_seconds = time.perf_counter() - started

    peak_metrics = metrics_by_frame[blob_peak_frame]
    contact_candidates = [
        (frame, values)
        for frame, values in metrics_by_frame.items()
        if values["center_gap"] is not None
        and values["center_gap"] <= 0.12
        and values["coverage"] >= 0.40
    ]
    first_contact_frame = contact_candidates[0][0] if contact_candidates else None

    blob.modifiers.remove(soft_mod)
    cloth.modifiers.remove(cloth_mod)

    blob.shape_key_add(name="Basis", from_mix=False)
    cloth.shape_key_add(name="Basis", from_mix=False)

    for frame in range(FRAME_START, FRAME_END + 1):
        blob_key = blob.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
        for idx, co in enumerate(blob_frames[frame]):
            blob_key.data[idx].co = co

        cloth_key = cloth.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
        for idx, co in enumerate(cloth_frames[frame]):
            cloth_key.data[idx].co = co

        for key_frame, value in (
            (frame - 1, 0.0),
            (frame, 1.0),
            (frame + 1, 0.0),
        ):
            if FRAME_START <= key_frame <= FRAME_END:
                blob_key.value = value
                blob_key.keyframe_insert(data_path="value", frame=key_frame)
                cloth_key.value = value
                cloth_key.keyframe_insert(data_path="value", frame=key_frame)

    for obj in (blob, cloth):
        if obj.data.shape_keys and obj.data.shape_keys.animation_data:
            action = obj.data.shape_keys.animation_data.action
            if action:
                for fc in action.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"

    blob_sub = blob.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    blob_sub.subdivision_type = "CATMULL_CLARK"
    blob_sub.levels = 1
    blob_sub.render_levels = 1

    solid = cloth.modifiers.new(name="FabricThickness", type="SOLIDIFY")
    solid.thickness = 0.022
    solid.offset = 0.0

    cloth_sub = cloth.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    cloth_sub.subdivision_type = "CATMULL_CLARK"
    cloth_sub.levels = 1
    cloth_sub.render_levels = 1

    scene.frame_set(FRAME_START)

    return {
        "simulation_seconds": round(simulation_seconds, 3),
        "blob_baked_frames": len(blob_frames),
        "cloth_baked_frames": len(cloth_frames),
        "blob_max_displacement": round(blob_max_displacement, 6),
        "blob_peak_frame": blob_peak_frame,
        "cloth_max_displacement": round(cloth_max_displacement, 6),
        "cloth_peak_frame": cloth_peak_frame,
        "cloth_min_z": round(cloth_min_z, 6),
        "cloth_min_z_frame": cloth_min_z_frame,
        "first_contact_frame": first_contact_frame,
        "coverage_at_blob_peak": round(float(peak_metrics["coverage"]), 6),
        "cloth_center_z_at_blob_peak": (
            round(float(peak_metrics["cloth_center_z"]), 6)
            if peak_metrics["cloth_center_z"] is not None else None
        ),
        "blob_center_top_z_at_peak": (
            round(float(peak_metrics["blob_center_top_z"]), 6)
            if peak_metrics["blob_center_top_z"] is not None else None
        ),
        "center_gap_at_blob_peak": (
            round(float(peak_metrics["center_gap"]), 6)
            if peak_metrics["center_gap"] is not None else None
        ),
    }


def build_scene():
    base = load_base()
    base.clear_scene()

    scene = bpy.context.scene
    engine = base.choose_engine(scene)
    samples = base.configure_render(scene)

    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
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

    blob = make_water_blob(base)
    soft_mod = add_water_softbody(blob)
    base.add_collision(blob, thickness=0.014, damping=0.20)
    if hasattr(blob.collision, "cloth_friction"):
        blob.collision.cloth_friction = 18.0

    cloth = make_cloth(base)
    cloth_mod = add_cloth_physics(cloth)

    # Deliberately expose the deforming Cloth as a Collision object too.
    # This is the experiment: can Soft Body and Cloth coexist in one
    # sequential headless solve without an explicit two-pass approximation?
    base.add_collision(cloth, thickness=0.010, damping=0.12)
    if hasattr(cloth.collision, "cloth_friction"):
        cloth.collision.cloth_friction = 14.0

    base.setup_camera_and_lights(scene)

    baked = bake_coupled(scene, blob, soft_mod, cloth, cloth_mod)

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
            "mode": "single-pass live cloth-softbody collision experiment",
            "cloth_reads_blob_collision": True,
            "blob_reads_cloth_collision": True,
            "true_fluid": False,
            "intent": "test a water-like deformable blob directly against Cloth before trying Mantaflow",
        },
        "blob": {
            "name": blob.name,
            "half_extents": [BLOB_HALF_X, BLOB_HALF_Y, BLOB_HALF_Z],
            "vertex_count": len(blob.data.vertices),
            "face_count": len(blob.data.polygons),
            "baked_shape_keys": baked["blob_baked_frames"],
            "shape_key_count": len(blob.data.shape_keys.key_blocks),
            "max_displacement": baked["blob_max_displacement"],
            "max_displacement_frame": baked["blob_peak_frame"],
            "center_top_z_at_peak": baked["blob_center_top_z_at_peak"],
            "softbody": {
                "pull": 0.22,
                "push": 0.22,
                "shear": 0.13,
                "bend": 0.14,
                "damping": 9.0,
                "goal_default": 0.30,
                "goal_spring": 0.34,
            },
        },
        "cloth": {
            "name": cloth.name,
            "grid_x": CLOTH_GRID_X,
            "grid_y": CLOTH_GRID_Y,
            "width": CLOTH_WIDTH,
            "depth": CLOTH_DEPTH,
            "start_z": CLOTH_Z,
            "vertex_count": len(cloth.data.vertices),
            "face_count": len(cloth.data.polygons),
            "self_collision": True,
            "baked_shape_keys": baked["cloth_baked_frames"],
            "shape_key_count": len(cloth.data.shape_keys.key_blocks),
            "max_displacement": baked["cloth_max_displacement"],
            "max_displacement_frame": baked["cloth_peak_frame"],
            "min_vertex_z": baked["cloth_min_z"],
            "min_vertex_z_frame": baked["cloth_min_z_frame"],
            "coverage_at_blob_peak": baked["coverage_at_blob_peak"],
            "center_z_at_blob_peak": baked["cloth_center_z_at_blob_peak"],
        },
        "interaction": {
            "simulation_seconds": baked["simulation_seconds"],
            "first_contact_frame": baked["first_contact_frame"],
            "blob_peak_frame": baked["blob_peak_frame"],
            "coverage_at_blob_peak": baked["coverage_at_blob_peak"],
            "center_gap_at_blob_peak": baked["center_gap_at_blob_peak"],
        },
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"WATER_BLOB_MAX_DISPLACEMENT={baked['blob_max_displacement']:.6f}")
    print(f"WATER_BLOB_PEAK_FRAME={baked['blob_peak_frame']}")
    print(f"WATER_FIRST_CONTACT_FRAME={baked['first_contact_frame']}")
    print(f"WATER_COVERAGE_AT_BLOB_PEAK={baked['coverage_at_blob_peak']:.6f}")
    print(f"WATER_CENTER_GAP_AT_BLOB_PEAK={baked['center_gap_at_blob_peak']}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

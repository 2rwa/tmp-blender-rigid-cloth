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

EXPERIMENT = "cloth-wrap-jelly-delayed-ball-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START, FRAME_END, FPS = 1, 192, 24
RES_X, RES_Y = 480, 360

BALL_RELEASE_FRAME = 49
BALL_RADIUS = 0.50
BALL_START = (0.0, 0.0, 6.8)

CLOTH_GRID_X, CLOTH_GRID_Y = 35, 31
CLOTH_WIDTH, CLOTH_DEPTH, CLOTH_Z = 3.50, 3.00, 3.45
JELLY_HALF_X, JELLY_HALF_Y = 1.55, 1.32
CENTER_HALF_X, CENTER_HALF_Y = 0.58, 0.48


def load_previous():
    path = ROOT / "experiments/cloth-drop-jelly-delayed-ball-eevee/scene.py"
    spec = importlib.util.spec_from_file_location("cloth_jelly_previous", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load previous experiment: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.EXPERIMENT = EXPERIMENT
    module.BLEND_PATH = BLEND_PATH
    module.REPORT_PATH = REPORT_PATH
    module.FRAME_START = FRAME_START
    module.FRAME_END = FRAME_END
    module.FPS = FPS
    module.RES_X = RES_X
    module.RES_Y = RES_Y
    module.BALL_RELEASE_FRAME = BALL_RELEASE_FRAME
    module.BALL_RADIUS = BALL_RADIUS
    module.BALL_START = BALL_START
    module.CLOTH_GRID_X = CLOTH_GRID_X
    module.CLOTH_GRID_Y = CLOTH_GRID_Y
    module.CLOTH_WIDTH = CLOTH_WIDTH
    module.CLOTH_DEPTH = CLOTH_DEPTH
    module.CLOTH_Z = CLOTH_Z
    return module


def make_delayed_ball(base):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=36,
        ring_count=20,
        radius=BALL_RADIUS,
        location=BALL_START,
    )
    ball = bpy.context.object
    ball.name = "DropBall_00"
    ball.data.materials.append(
        base.make_material(
            "DelayedPressBallMat",
            (0.98, 0.55, 0.06),
            roughness=0.18,
            metallic=0.45,
        )
    )
    for poly in ball.data.polygons:
        poly.use_smooth = True

    base.add_collision(ball, thickness=0.022, damping=0.10)
    if hasattr(ball.collision, "cloth_friction"):
        ball.collision.cloth_friction = 18.0

    bpy.ops.rigidbody.object_add()
    rb = ball.rigid_body
    rb.type = "ACTIVE"
    rb.mass = 2.6
    rb.friction = 0.66
    rb.restitution = 0.12
    rb.linear_damping = 0.04
    rb.angular_damping = 0.08
    rb.collision_shape = "SPHERE"
    rb.use_deactivation = False

    rb.kinematic = True
    rb.keyframe_insert(data_path="kinematic", frame=FRAME_START)
    rb.keyframe_insert(data_path="kinematic", frame=BALL_RELEASE_FRAME - 1)
    rb.kinematic = False
    rb.keyframe_insert(data_path="kinematic", frame=BALL_RELEASE_FRAME)
    rb.keyframe_insert(data_path="kinematic", frame=FRAME_END)
    return ball


def add_grippy_cloth_modifier(cloth):
    mod = cloth.modifiers.new(name="ClothPhysics", type="CLOTH")
    s = mod.settings
    s.quality = 9
    s.mass = 0.18
    s.air_damping = 1.8
    s.tension_stiffness = 26.0
    s.compression_stiffness = 26.0
    s.shear_stiffness = 19.0
    s.bending_stiffness = 0.24
    s.tension_damping = 7.0
    s.compression_damping = 7.0
    s.shear_damping = 7.0
    s.bending_damping = 3.0

    c = mod.collision_settings
    c.use_collision = True
    c.collision_quality = 7
    c.distance_min = 0.010
    c.friction = 14.0
    c.use_self_collision = True
    c.self_distance_min = 0.010
    c.self_friction = 8.0

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1
    return mod


def sample_metrics(coords):
    footprint = [
        co for co in coords
        if abs(co[0]) <= JELLY_HALF_X and abs(co[1]) <= JELLY_HALF_Y
    ]
    center = [
        co for co in coords
        if abs(co[0]) <= CENTER_HALF_X and abs(co[1]) <= CENTER_HALF_Y
    ]
    coverage = len(footprint) / len(coords) if coords else 0.0
    center_mean_z = (
        sum(co[2] for co in center) / len(center)
        if center else None
    )
    return coverage, center_mean_z, len(center)


def bake_cloth(scene, cloth, cloth_mod, impact_frame):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in cloth.data.vertices]
    frames = {}

    max_displacement = 0.0
    max_frame = FRAME_START
    min_z = float("inf")
    min_z_frame = FRAME_START
    diagnostics = {}

    release_probe_frame = BALL_RELEASE_FRAME - 1
    impact_probe_frame = max(FRAME_START, min(FRAME_END, int(impact_frame)))

    started = time.perf_counter()
    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()

        eval_obj = cloth.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if len(mesh.vertices) != len(basis):
            raise RuntimeError(
                f"cloth topology changed at frame {frame}: "
                f"{len(mesh.vertices)} != {len(basis)}"
            )
        coords = [tuple(v.co) for v in mesh.vertices]
        frames[frame] = coords
        eval_obj.to_mesh_clear()

        frame_max = 0.0
        frame_min_z = min(co[2] for co in coords)
        for base_co, co in zip(basis, coords):
            dx = co[0] - base_co[0]
            dy = co[1] - base_co[1]
            dz = co[2] - base_co[2]
            frame_max = max(frame_max, math.sqrt(dx*dx + dy*dy + dz*dz))

        if frame_max > max_displacement:
            max_displacement = frame_max
            max_frame = frame
        if frame_min_z < min_z:
            min_z = frame_min_z
            min_z_frame = frame

        if not math.isfinite(frame_max) or frame_max > 16.0:
            raise RuntimeError(
                f"cloth numerical instability at frame {frame}: "
                f"max displacement={frame_max}"
            )

        if frame in {release_probe_frame, impact_probe_frame}:
            coverage, center_mean_z, center_count = sample_metrics(coords)
            diagnostics[frame] = {
                "coverage": coverage,
                "center_mean_z": center_mean_z,
                "center_vertex_count": center_count,
            }

        if frame % 12 == 0:
            print(f"WRAP_CLOTH_SIM_FRAME={frame}")
            print(f"WRAP_CLOTH_FRAME_MAX_DISPLACEMENT={frame_max:.6f}")

    seconds = time.perf_counter() - started

    cloth.modifiers.remove(cloth_mod)
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

    action = (
        cloth.data.shape_keys.animation_data.action
        if cloth.data.shape_keys and cloth.data.shape_keys.animation_data
        else None
    )
    if action:
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

    solid = cloth.modifiers.new(name="FabricThickness", type="SOLIDIFY")
    solid.thickness = 0.024
    solid.offset = 0.0

    sub = cloth.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1

    release_diag = diagnostics.get(release_probe_frame) or {}
    impact_diag = diagnostics.get(impact_probe_frame) or {}
    release_z = release_diag.get("center_mean_z")
    impact_z = impact_diag.get("center_mean_z")
    press_depth = (
        release_z - impact_z
        if release_z is not None and impact_z is not None
        else None
    )

    scene.frame_set(FRAME_START)
    return {
        "seconds": round(seconds, 3),
        "baked_frames": len(frames),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_vertex_z": round(min_z, 6),
        "min_vertex_z_frame": min_z_frame,
        "release_probe_frame": release_probe_frame,
        "impact_probe_frame": impact_probe_frame,
        "coverage_at_release": round(float(release_diag.get("coverage", 0.0)), 6),
        "coverage_at_impact": round(float(impact_diag.get("coverage", 0.0)), 6),
        "center_mean_z_at_release": (
            round(float(release_z), 6) if release_z is not None else None
        ),
        "center_mean_z_at_impact": (
            round(float(impact_z), 6) if impact_z is not None else None
        ),
        "center_press_depth": (
            round(float(press_depth), 6) if press_depth is not None else None
        ),
        "center_vertices_at_release": int(release_diag.get("center_vertex_count", 0)),
        "center_vertices_at_impact": int(impact_diag.get("center_vertex_count", 0)),
    }


def build_scene() -> None:
    previous = load_previous()
    base = previous.load_base()

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
    bg.inputs["Color"].default_value = (0.004, 0.006, 0.010, 1.0)
    bg.inputs["Strength"].default_value = 0.12

    ground = base.make_floor()
    base.add_collision(ground, thickness=0.025, damping=0.20)
    if hasattr(ground.collision, "cloth_friction"):
        ground.collision.cloth_friction = 10.0

    jelly = base.make_rounded_jelly()
    soft_mod = base.add_softbody(jelly)
    base.add_collision(jelly, thickness=0.018, damping=0.18)
    if hasattr(jelly.collision, "cloth_friction"):
        jelly.collision.cloth_friction = 28.0

    base.ensure_rigidbody_world(scene)
    scene.rigidbody_world.substeps_per_frame = 10
    scene.rigidbody_world.solver_iterations = 35

    proxy = base.make_rigid_proxy()
    ball = make_delayed_ball(base)
    base.setup_camera_and_lights(scene)

    # Pass 1: the delayed rigid ball deforms the live Jelly.
    jelly_bake = base.bake_hybrid_to_keys(scene, jelly, soft_mod, [ball])
    previous.remove_rigidbody_release_curve(ball)
    base.add_render_modifiers(jelly)

    # Pass 2: the smaller, grippier Cloth settles on the baked Jelly first,
    # then is squeezed by the already-baked ball trajectory.
    cloth = previous.make_cloth(base)
    cloth_mod = add_grippy_cloth_modifier(cloth)
    ball_info = jelly_bake["balls"][0]
    impact_frame = ball_info.get("min_center_z_frame") or 74
    cloth_bake = bake_cloth(scene, cloth, cloth_mod, impact_frame)

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
            "mode": "two-pass one-way coupling",
            "pass_1": "delayed rigid ball -> soft-body jelly",
            "pass_2": "baked jelly + baked ball -> grippy cloth",
            "cloth_reads_jelly_collision": True,
            "jelly_reads_cloth_collision": False,
            "ball_feels_cloth": False,
            "intent": "keep cloth on jelly long enough for ball to press cloth into deformed jelly",
        },
        "jelly": {
            "name": jelly.name,
            "vertex_count": len(jelly.data.vertices),
            "face_count": len(jelly.data.polygons),
            "baked_shape_keys": jelly_bake["baked_frames"],
            "shape_key_count": len(jelly.data.shape_keys.key_blocks),
            "simulation_seconds": jelly_bake["simulation_seconds"],
            "max_displacement": jelly_bake["max_displacement"],
            "max_displacement_frame": jelly_bake["max_displacement_frame"],
            "cloth_friction": getattr(jelly.collision, "cloth_friction", None),
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
            "baked_shape_keys": cloth_bake["baked_frames"],
            "shape_key_count": len(cloth.data.shape_keys.key_blocks),
            "simulation_seconds": cloth_bake["seconds"],
            "max_displacement": cloth_bake["max_displacement"],
            "max_displacement_frame": cloth_bake["max_displacement_frame"],
            "min_vertex_z": cloth_bake["min_vertex_z"],
            "min_vertex_z_frame": cloth_bake["min_vertex_z_frame"],
            "release_probe_frame": cloth_bake["release_probe_frame"],
            "impact_probe_frame": cloth_bake["impact_probe_frame"],
            "coverage_at_release": cloth_bake["coverage_at_release"],
            "coverage_at_impact": cloth_bake["coverage_at_impact"],
            "center_mean_z_at_release": cloth_bake["center_mean_z_at_release"],
            "center_mean_z_at_impact": cloth_bake["center_mean_z_at_impact"],
            "center_press_depth": cloth_bake["center_press_depth"],
            "center_vertices_at_release": cloth_bake["center_vertices_at_release"],
            "center_vertices_at_impact": cloth_bake["center_vertices_at_impact"],
        },
        "ball": {
            "name": ball.name,
            "radius": BALL_RADIUS,
            "mass": ball.rigid_body.mass,
            "release_frame": BALL_RELEASE_FRAME,
            "release_seconds": (BALL_RELEASE_FRAME - FRAME_START) / FPS,
            "start_location": list(BALL_START),
            "final_location": ball_info["final_location"],
            "min_center_z_in_proxy_footprint": ball_info["min_center_z_in_proxy_footprint"],
            "min_center_z_frame": ball_info["min_center_z_frame"],
            "possible_proxy_tunneling": ball_info["possible_proxy_tunneling"],
        },
        "rigid_body": {
            "proxy": proxy.name,
            "world_substeps_per_frame": scene.rigidbody_world.substeps_per_frame,
            "world_solver_iterations": scene.rigidbody_world.solver_iterations,
            "bake_seconds": jelly_bake["rigid_bake_seconds"],
        },
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"BALL_RELEASE_FRAME={BALL_RELEASE_FRAME}")
    print(f"CLOTH_COVERAGE_AT_RELEASE={cloth_bake['coverage_at_release']:.6f}")
    print(f"CLOTH_COVERAGE_AT_IMPACT={cloth_bake['coverage_at_impact']:.6f}")
    print(f"CLOTH_CENTER_PRESS_DEPTH={cloth_bake['center_press_depth']}")
    print(f"JELLY_MAX_DISPLACEMENT={jelly_bake['max_displacement']:.6f}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

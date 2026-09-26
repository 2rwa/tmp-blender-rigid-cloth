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

EXPERIMENT = "cloth-drop-jelly-delayed-ball-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"
FRAME_START, FRAME_END, FPS = 1, 192, 24
RES_X, RES_Y = 480, 360
BALL_RELEASE_FRAME = 49
BALL_RADIUS = 0.42
BALL_START = (0.28, -0.08, 7.2)
CLOTH_GRID_X, CLOTH_GRID_Y = 35, 29
CLOTH_WIDTH, CLOTH_DEPTH, CLOTH_Z = 4.5, 3.7, 4.35


def load_base():
    path = ROOT / "experiments/softbody-jelly-cube-ball-drop-eevee/scene.py"
    spec = importlib.util.spec_from_file_location("jelly_ball_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load base experiment: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.FRAME_START = FRAME_START
    module.FRAME_END = FRAME_END
    module.FPS = FPS
    module.RES_X = RES_X
    module.RES_Y = RES_Y
    module.BALL_RADIUS = (BALL_RADIUS,)
    module.BALL_POSITIONS = (BALL_START,)
    return module


def make_delayed_ball(base):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32, ring_count=18, radius=BALL_RADIUS, location=BALL_START
    )
    ball = bpy.context.object
    ball.name = "DropBall_00"
    ball.data.materials.append(
        base.make_material("DelayedBallMat", (0.96, 0.62, 0.08), roughness=0.20, metallic=0.42)
    )
    for poly in ball.data.polygons:
        poly.use_smooth = True
    base.add_collision(ball, thickness=0.045, damping=0.08)

    bpy.ops.rigidbody.object_add()
    rb = ball.rigid_body
    rb.type = "ACTIVE"
    rb.mass = 2.0
    rb.friction = 0.58
    rb.restitution = 0.20
    rb.linear_damping = 0.035
    rb.angular_damping = 0.07
    rb.collision_shape = "SPHERE"
    rb.use_deactivation = False

    rb.kinematic = True
    rb.keyframe_insert(data_path="kinematic", frame=FRAME_START)
    rb.keyframe_insert(data_path="kinematic", frame=BALL_RELEASE_FRAME - 1)
    rb.kinematic = False
    rb.keyframe_insert(data_path="kinematic", frame=BALL_RELEASE_FRAME)
    rb.keyframe_insert(data_path="kinematic", frame=FRAME_END)
    return ball


def remove_rigidbody_release_curve(ball) -> None:
    if ball.animation_data and ball.animation_data.action:
        action = ball.animation_data.action
        for fc in list(action.fcurves):
            if fc.data_path == "rigid_body.kinematic":
                action.fcurves.remove(fc)
    if ball.rigid_body:
        ball.rigid_body.kinematic = True


def make_cloth(base):
    verts, faces = [], []
    for j in range(CLOTH_GRID_Y):
        y = -CLOTH_DEPTH * 0.5 + CLOTH_DEPTH * j / (CLOTH_GRID_Y - 1)
        for i in range(CLOTH_GRID_X):
            x = -CLOTH_WIDTH * 0.5 + CLOTH_WIDTH * i / (CLOTH_GRID_X - 1)
            z = CLOTH_Z + 0.015 * math.sin(i * 0.53) * math.sin(j * 0.41)
            verts.append((x, y, z))
    for j in range(CLOTH_GRID_Y - 1):
        for i in range(CLOTH_GRID_X - 1):
            a = j * CLOTH_GRID_X + i
            faces.append((a, a + 1, a + CLOTH_GRID_X + 1, a + CLOTH_GRID_X))

    mesh = bpy.data.meshes.new("DropClothMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    cloth = bpy.data.objects.new("DropCloth", mesh)
    bpy.context.collection.objects.link(cloth)
    cloth.data.materials.append(
        base.make_material("DropClothMaterial", (0.08, 0.18, 0.78), roughness=0.68, metallic=0.03)
    )
    return cloth


def add_cloth_modifier(cloth):
    mod = cloth.modifiers.new(name="ClothPhysics", type="CLOTH")
    s = mod.settings
    s.quality = 7
    s.mass = 0.22
    s.air_damping = 1.2
    s.tension_stiffness = 30.0
    s.compression_stiffness = 30.0
    s.shear_stiffness = 22.0
    s.bending_stiffness = 0.45
    s.tension_damping = 6.0
    s.compression_damping = 6.0
    s.shear_damping = 6.0
    s.bending_damping = 2.0

    c = mod.collision_settings
    c.use_collision = True
    c.collision_quality = 5
    c.distance_min = 0.018
    c.friction = 7.0
    c.use_self_collision = True
    c.self_distance_min = 0.015
    c.self_friction = 4.0

    mod.point_cache.frame_start = FRAME_START
    mod.point_cache.frame_end = FRAME_END
    mod.point_cache.frame_step = 1
    return mod


def bake_cloth(scene, cloth, cloth_mod):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis = [tuple(v.co) for v in cloth.data.vertices]
    frames = {}
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
        eval_obj = cloth.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        if len(mesh.vertices) != len(basis):
            raise RuntimeError(f"cloth topology changed at frame {frame}")
        coords = [tuple(v.co) for v in mesh.vertices]
        frames[frame] = coords
        eval_obj.to_mesh_clear()

        frame_max = 0.0
        frame_min_z = min(co[2] for co in coords)
        for base_co, co in zip(basis, coords):
            dx, dy, dz = co[0]-base_co[0], co[1]-base_co[1], co[2]-base_co[2]
            frame_max = max(frame_max, math.sqrt(dx*dx + dy*dy + dz*dz))
        if frame_max > max_displacement:
            max_displacement, max_frame = frame_max, frame
        if frame_min_z < min_z:
            min_z, min_z_frame = frame_min_z, frame
        if not math.isfinite(frame_max) or frame_max > 16.0:
            raise RuntimeError(f"cloth instability at frame {frame}: {frame_max}")
        if frame % 12 == 0:
            print(f"CLOTH_SIM_FRAME={frame}")
            print(f"CLOTH_FRAME_MAX_DISPLACEMENT={frame_max:.6f}")

    seconds = time.perf_counter() - started
    cloth.modifiers.remove(cloth_mod)
    cloth.shape_key_add(name="Basis", from_mix=False)
    for frame in range(FRAME_START, FRAME_END + 1):
        key = cloth.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
        for idx, co in enumerate(frames[frame]):
            key.data[idx].co = co
        for key_frame, value in ((frame-1, 0.0), (frame, 1.0), (frame+1, 0.0)):
            if FRAME_START <= key_frame <= FRAME_END:
                key.value = value
                key.keyframe_insert(data_path="value", frame=key_frame)

    action = cloth.data.shape_keys.animation_data.action if cloth.data.shape_keys and cloth.data.shape_keys.animation_data else None
    if action:
        for fc in action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"

    solid = cloth.modifiers.new(name="FabricThickness", type="SOLIDIFY")
    solid.thickness = 0.025
    solid.offset = 0.0
    sub = cloth.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = sub.render_levels = 1
    scene.frame_set(FRAME_START)
    return {
        "seconds": round(seconds, 3),
        "baked_frames": len(frames),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_frame,
        "min_vertex_z": round(min_z, 6),
        "min_vertex_z_frame": min_z_frame,
    }


def build_scene() -> None:
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
    scene.world.node_tree.nodes.get("Background").inputs["Strength"].default_value = 0.12

    ground = base.make_floor()
    base.add_collision(ground, thickness=0.03, damping=0.18)
    jelly = base.make_rounded_jelly()
    soft_mod = base.add_softbody(jelly)
    base.add_collision(jelly, thickness=0.045, damping=0.12)
    base.ensure_rigidbody_world(scene)
    proxy = base.make_rigid_proxy()
    ball = make_delayed_ball(base)
    base.setup_camera_and_lights(scene)

    # Pass 1: delayed ball + live Jelly. Avoid a Cloth/Soft Body dependency cycle.
    jelly_bake = base.bake_hybrid_to_keys(scene, jelly, soft_mod, [ball])
    remove_rigidbody_release_curve(ball)
    base.add_render_modifiers(jelly)

    # Pass 2: Cloth falls against the baked Jelly surface and baked ball motion.
    cloth = make_cloth(base)
    cloth_mod = add_cloth_modifier(cloth)
    cloth_bake = bake_cloth(scene, cloth, cloth_mod)

    ball_info = jelly_bake["balls"][0]
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
            "pass_2": "baked jelly + baked ball -> cloth",
            "cloth_reads_jelly_collision": True,
            "jelly_reads_cloth_collision": False,
            "ball_feels_cloth": False,
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
        },
        "cloth": {
            "name": cloth.name,
            "grid_x": CLOTH_GRID_X,
            "grid_y": CLOTH_GRID_Y,
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
    print(f"JELLY_MAX_DISPLACEMENT={jelly_bake['max_displacement']:.6f}")
    print(f"CLOTH_MAX_DISPLACEMENT={cloth_bake['max_displacement']:.6f}")
    print(f"BLEND_PATH={BLEND_PATH}")


if __name__ == "__main__":
    build_scene()

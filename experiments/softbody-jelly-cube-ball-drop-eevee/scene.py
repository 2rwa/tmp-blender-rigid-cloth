from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT = "softbody-jelly-cube-ball-drop-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"

FRAME_START = 1
FRAME_END = 192
FPS = 24
RES_X = 480
RES_Y = 360
PREPARE_ONLY = os.environ.get("BLENDER_PREPARE_ONLY") == "1"

BALL_COUNT = 3
BALL_RADIUS = (0.38, 0.34, 0.42)
BALL_POSITIONS = (
    (-0.72, -0.28, 4.9),
    (0.18, 0.34, 6.35),
    (0.74, -0.16, 7.85),
)
PROXY_HALF_EXTENTS = (1.18, 1.02, 0.72)
PROXY_Z = 1.34


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def choose_engine(scene) -> str:
    for candidate in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = candidate
            return candidate
        except TypeError:
            continue
    scene.render.engine = "BLENDER_WORKBENCH"
    return "BLENDER_WORKBENCH"


def configure_render(scene) -> int | None:
    eevee = getattr(scene, "eevee", None)
    if eevee is not None and hasattr(eevee, "taa_render_samples"):
        eevee.taa_render_samples = 16
        if hasattr(eevee, "use_gtao"):
            eevee.use_gtao = True
        if hasattr(eevee, "gtao_distance"):
            eevee.gtao_distance = 3.0
        if hasattr(eevee, "gtao_factor"):
            eevee.gtao_factor = 1.3
        return int(eevee.taa_render_samples)
    return None


def look_at(obj, target) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def set_bsdf_input(bsdf, names, value) -> bool:
    for name in names:
        socket = bsdf.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return True
    return False


def make_material(name: str, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def make_jelly_material():
    mat = bpy.data.materials.new("JellyMaterial")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.08, 0.70, 0.32, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.18
    bsdf.inputs["Metallic"].default_value = 0.0
    set_bsdf_input(bsdf, ("IOR",), 1.36)
    set_bsdf_input(bsdf, ("Transmission Weight", "Transmission"), 0.30)
    set_bsdf_input(bsdf, ("Subsurface Weight", "Subsurface"), 0.10)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.2
    noise.inputs["Detail"].default_value = 2.0
    noise.inputs["Roughness"].default_value = 0.58

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.25
    ramp.color_ramp.elements[0].color = (0.025, 0.20, 0.08, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (0.26, 0.95, 0.52, 1.0)

    texcoord = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (0.8, 0.8, 1.15)

    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def active(obj) -> None:
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)


def make_rounded_jelly():
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, 1.62))
    jelly = bpy.context.object
    jelly.name = "JellyCube"
    jelly.scale = (1.55, 1.32, 1.38)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    bevel = jelly.modifiers.new(name="RoundedCorners", type="BEVEL")
    bevel.width = 0.28
    bevel.segments = 5
    bevel.limit_method = "ANGLE"
    active(jelly)
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    sub = jelly.modifiers.new(name="PhysicsSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1
    bpy.ops.object.modifier_apply(modifier=sub.name)

    for poly in jelly.data.polygons:
        poly.use_smooth = True

    jelly.data.materials.append(make_jelly_material())
    return jelly


def add_softbody(jelly):
    mod = jelly.modifiers.new(name="JellySoftBody", type="SOFT_BODY")
    settings = mod.settings
    settings.use_edges = True
    settings.use_stiff_quads = False
    settings.pull = 0.32
    settings.push = 0.32
    settings.shear = 0.18
    settings.bend = 0.34
    settings.damping = 7.0
    settings.friction = 4.0
    settings.mass = 1.0
    settings.speed = 0.65
    settings.gravity = 0.0
    settings.plastic = 0

    settings.use_goal = True
    settings.goal_default = 0.48
    settings.goal_spring = 0.46
    settings.goal_friction = 7.0
    settings.goal_min = 0.0
    settings.goal_max = 1.0

    settings.use_edge_collision = False
    settings.use_face_collision = False
    settings.use_self_collision = False
    settings.use_auto_step = True
    settings.step_min = 2
    settings.step_max = 16
    settings.error_threshold = 0.04

    cache = mod.point_cache
    cache.frame_start = FRAME_START
    cache.frame_end = FRAME_END
    cache.frame_step = 1
    return mod


def add_collision(obj, thickness=0.04, damping=0.12) -> None:
    obj.modifiers.new(name="Collision", type="COLLISION")
    obj.collision.use = True
    if hasattr(obj.collision, "thickness_outer"):
        obj.collision.thickness_outer = thickness
    if hasattr(obj.collision, "damping"):
        obj.collision.damping = damping


def ensure_rigidbody_world(scene):
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    world.point_cache.frame_start = FRAME_START
    world.point_cache.frame_end = FRAME_END
    world.substeps_per_frame = 8
    world.solver_iterations = 30
    return world


def make_floor():
    floor_mat = make_material("Floor", (0.018, 0.022, 0.028), roughness=0.82, metallic=0.05)
    bpy.ops.mesh.primitive_plane_add(size=18.0, location=(0.0, 0.0, 0.0))
    floor = bpy.context.object
    floor.name = "Ground"
    floor.data.materials.append(floor_mat)
    bpy.context.view_layer.objects.active = floor
    bpy.ops.rigidbody.object_add()
    floor.rigid_body.type = "PASSIVE"
    floor.rigid_body.friction = 0.82
    floor.rigid_body.restitution = 0.04
    return floor


def make_rigid_proxy():
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0.0, 0.0, PROXY_Z))
    proxy = bpy.context.object
    proxy.name = "JellyRigidProxy"
    proxy.scale = PROXY_HALF_EXTENTS
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = proxy.modifiers.new(name="ProxyBevel", type="BEVEL")
    bevel.width = 0.22
    bevel.segments = 3
    active(proxy)
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    proxy.hide_render = True
    bpy.ops.rigidbody.object_add()
    proxy.rigid_body.type = "PASSIVE"
    proxy.rigid_body.collision_shape = "MESH"
    proxy.rigid_body.friction = 0.66
    proxy.rigid_body.restitution = 0.18
    return proxy


def make_rigid_balls():
    palette = (
        (0.88, 0.16, 0.12),
        (0.10, 0.45, 0.92),
        (0.96, 0.68, 0.10),
    )
    balls = []
    for idx, (radius, location) in enumerate(zip(BALL_RADIUS, BALL_POSITIONS)):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32,
            ring_count=18,
            radius=radius,
            location=location,
        )
        ball = bpy.context.object
        ball.name = f"DropBall_{idx:02d}"
        ball.data.materials.append(
            make_material(
                f"DropBallMat_{idx:02d}",
                palette[idx],
                roughness=0.22,
                metallic=0.38,
            )
        )
        for poly in ball.data.polygons:
            poly.use_smooth = True

        # The Collision modifier drives the Soft Body response, while the
        # Rigid Body system handles the gravity-driven ball motion.
        add_collision(ball, thickness=0.045, damping=0.08)
        bpy.ops.rigidbody.object_add()
        rb = ball.rigid_body
        rb.type = "ACTIVE"
        rb.mass = 1.2 + idx * 0.55
        rb.friction = 0.58
        rb.restitution = 0.22
        rb.linear_damping = 0.035
        rb.angular_damping = 0.07
        rb.collision_shape = "SPHERE"
        rb.use_deactivation = False
        balls.append(ball)
    return balls


def bake_hybrid_to_keys(scene, jelly, soft_mod, rigid_objects):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    basis_coords = [tuple(v.co) for v in jelly.data.vertices]
    jelly_frames = {}
    rigid_frames = {obj.name: {} for obj in rigid_objects}
    max_displacement = 0.0
    max_displacement_frame = FRAME_START
    started = time.perf_counter()

    scene.frame_set(FRAME_START)
    depsgraph.update()

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()

        eval_jelly = jelly.evaluated_get(depsgraph)
        eval_mesh = eval_jelly.to_mesh()
        if len(eval_mesh.vertices) != len(basis_coords):
            raise RuntimeError(
                f"soft-body topology changed at frame {frame}: "
                f"{len(eval_mesh.vertices)} != {len(basis_coords)}"
            )

        coords = [tuple(v.co) for v in eval_mesh.vertices]
        jelly_frames[frame] = coords

        frame_max = 0.0
        for base, co in zip(basis_coords, coords):
            dx = co[0] - base[0]
            dy = co[1] - base[1]
            dz = co[2] - base[2]
            disp = math.sqrt(dx * dx + dy * dy + dz * dz)
            if disp > frame_max:
                frame_max = disp
        eval_jelly.to_mesh_clear()

        if frame_max > max_displacement:
            max_displacement = frame_max
            max_displacement_frame = frame
        if not math.isfinite(frame_max) or frame_max > 12.0:
            raise RuntimeError(
                f"soft-body numerical instability at frame {frame}: "
                f"max displacement={frame_max}"
            )

        for obj in rigid_objects:
            eval_obj = obj.evaluated_get(depsgraph)
            loc, rot, scale = eval_obj.matrix_world.decompose()
            rigid_frames[obj.name][frame] = (tuple(loc), tuple(rot), tuple(scale))

        if frame % 12 == 0:
            print(f"JELLY_RIGID_SIM_FRAME={frame}")
            print(f"JELLY_FRAME_MAX_DISPLACEMENT={frame_max:.6f}")

    simulation_seconds = time.perf_counter() - started

    jelly.modifiers.remove(soft_mod)
    basis = jelly.shape_key_add(name="Basis", from_mix=False)
    assert len(basis.data) == len(basis_coords)

    for frame in range(FRAME_START, FRAME_END + 1):
        key = jelly.shape_key_add(name=f"Sim_{frame:03d}", from_mix=False)
        for idx, co in enumerate(jelly_frames[frame]):
            key.data[idx].co = co
        for key_frame, value in ((frame - 1, 0.0), (frame, 1.0), (frame + 1, 0.0)):
            if FRAME_START <= key_frame <= FRAME_END:
                key.value = value
                key.keyframe_insert(data_path="value", frame=key_frame)

    if jelly.data.shape_keys and jelly.data.shape_keys.animation_data:
        action = jelly.data.shape_keys.animation_data.action
        if action:
            for fc in action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

    rigid_bake_started = time.perf_counter()
    for obj in rigid_objects:
        obj.rotation_mode = "QUATERNION"
        if obj.rigid_body:
            obj.rigid_body.kinematic = True

        for frame in range(FRAME_START, FRAME_END + 1):
            loc, rot, scale = rigid_frames[obj.name][frame]
            obj.location = loc
            obj.rotation_quaternion = rot
            obj.scale = scale
            obj.keyframe_insert(data_path="location", frame=frame)
            obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)
            obj.keyframe_insert(data_path="scale", frame=frame)

        if obj.animation_data and obj.animation_data.action:
            for fc in obj.animation_data.action.fcurves:
                if fc.data_path in {"location", "rotation_quaternion", "scale"}:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"

    rigid_bake_seconds = time.perf_counter() - rigid_bake_started
    scene.frame_set(FRAME_START)

    per_ball = []
    proxy_top = PROXY_Z + PROXY_HALF_EXTENTS[2]
    for obj in rigid_objects:
        samples = rigid_frames[obj.name]
        footprint_z = []
        for frame, (loc, _rot, _scale) in samples.items():
            if abs(loc[0]) <= PROXY_HALF_EXTENTS[0] and abs(loc[1]) <= PROXY_HALF_EXTENTS[1]:
                footprint_z.append((frame, loc[2]))
        min_frame, min_z = min(footprint_z, key=lambda item: item[1]) if footprint_z else (None, None)
        final_loc = samples[FRAME_END][0]
        radius = BALL_RADIUS[int(obj.name.rsplit("_", 1)[1])]
        possible_tunneling = bool(min_z is not None and min_z < (proxy_top - radius * 0.25))
        per_ball.append({
            "name": obj.name,
            "radius": radius,
            "mass": obj.rigid_body.mass if obj.rigid_body else None,
            "start_location": list(BALL_POSITIONS[int(obj.name.rsplit("_", 1)[1])]),
            "min_center_z_in_proxy_footprint": round(min_z, 6) if min_z is not None else None,
            "min_center_z_frame": min_frame,
            "final_location": [round(v, 6) for v in final_loc],
            "possible_proxy_tunneling": possible_tunneling,
        })

    return {
        "simulation_seconds": round(simulation_seconds, 3),
        "baked_frames": len(jelly_frames),
        "max_displacement": round(max_displacement, 6),
        "max_displacement_frame": max_displacement_frame,
        "rigid_bake_seconds": round(rigid_bake_seconds, 3),
        "balls": per_ball,
    }


def add_render_modifiers(jelly):
    sub = jelly.modifiers.new(name="RenderSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1


def setup_camera_and_lights(scene):
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    scene.camera = camera

    shots = [
        (1, (8.2, -10.5, 6.8), (0.0, 0.0, 2.65), 52.0),
        (56, (7.4, -9.4, 5.7), (0.0, 0.0, 2.10), 56.0),
        (116, (6.8, -8.3, 5.0), (0.15, 0.0, 1.85), 59.0),
        (192, (7.5, -9.1, 5.6), (0.0, 0.0, 1.95), 55.0),
    ]
    for frame, location, target, lens in shots:
        camera.location = location
        camera_data.lens = lens
        look_at(camera, target)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera_data.keyframe_insert(data_path="lens", frame=frame)

    def area(name, location, energy, size, color):
        data = bpy.data.lights.new(name=name, type="AREA")
        data.energy = energy
        data.shape = "DISK"
        data.size = size
        data.color = color
        obj = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(obj)
        obj.location = location
        look_at(obj, (0.0, 0.0, 1.8))

    area("Key", (-3.0, -4.0, 7.5), 980.0, 5.0, (0.82, 1.0, 0.88))
    area("Fill", (4.5, -2.0, 4.8), 520.0, 4.0, (0.40, 0.58, 1.0))
    area("Rim", (2.0, 4.0, 6.4), 760.0, 3.0, (0.95, 0.36, 0.16))

    bpy.ops.object.light_add(type="AREA", location=(-0.5, 1.8, 1.9))
    back = bpy.context.object
    back.name = "GelBacklight"
    back.data.energy = 480.0
    back.data.shape = "RECTANGLE"
    back.data.size = 2.8
    back.data.size_y = 2.8
    back.data.color = (0.38, 1.0, 0.58)
    look_at(back, (0.0, 0.0, 1.7))


def build_scene() -> None:
    clear_scene()
    scene = bpy.context.scene
    engine = choose_engine(scene)
    samples = configure_render(scene)

    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.frame_current = FRAME_START
    scene.render.fps = FPS
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.gravity = (0.0, 0.0, -9.81)

    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.004, 0.006, 0.010, 1.0)
    bg.inputs["Strength"].default_value = 0.12

    make_floor()
    jelly = make_rounded_jelly()
    soft_mod = add_softbody(jelly)
    ensure_rigidbody_world(scene)
    proxy = make_rigid_proxy()
    balls = make_rigid_balls()
    setup_camera_and_lights(scene)

    bake = bake_hybrid_to_keys(scene, jelly, soft_mod, balls)
    add_render_modifiers(jelly)

    report = {
        "experiment": EXPERIMENT,
        "engine": engine,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "fps": FPS,
        "resolution_x": RES_X,
        "resolution_y": RES_Y,
        "requested_render_samples": 16,
        "effective_render_samples": samples,
        "prepare_only": PREPARE_ONLY,
        "jelly": {
            "name": jelly.name,
            "vertex_count": len(jelly.data.vertices),
            "face_count": len(jelly.data.polygons),
            "baked_shape_keys": bake["baked_frames"],
            "shape_key_count": len(jelly.data.shape_keys.key_blocks) if jelly.data.shape_keys else 0,
            "simulation_seconds": bake["simulation_seconds"],
            "max_displacement": bake["max_displacement"],
            "max_displacement_frame": bake["max_displacement_frame"],
            "goal_default": 0.48,
            "goal_spring": 0.46,
            "goal_friction": 7.0,
            "pull": 0.32,
            "push": 0.32,
            "bend": 0.34,
            "stability_limit": 12.0,
        },
        "rigid_bodies": {
            "count": len(balls),
            "bake_seconds": bake["rigid_bake_seconds"],
            "world_substeps_per_frame": scene.rigidbody_world.substeps_per_frame,
            "world_solver_iterations": scene.rigidbody_world.solver_iterations,
            "proxy": proxy.name,
            "proxy_half_extents": list(PROXY_HALF_EXTENTS),
            "balls": bake["balls"],
        },
        "render_modifiers": [m.type for m in jelly.modifiers],
        "blend": BLEND_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    print(f"BLENDER_ENGINE={engine}")
    print(f"JELLY_VERTICES={len(jelly.data.vertices)}")
    print(f"JELLY_BAKED_FRAMES={bake['baked_frames']}")
    print(f"JELLY_MAX_DISPLACEMENT={bake['max_displacement']:.6f}")
    print(f"JELLY_SIM_SECONDS={bake['simulation_seconds']:.3f}")
    print(f"RIGID_BODY_COUNT={len(balls)}")
    print(f"RIGID_BODY_BAKE_SECONDS={bake['rigid_bake_seconds']:.3f}")
    print(f"BLEND_PATH={BLEND_PATH}")
    print(f"REPORT_PATH={REPORT_PATH}")


if __name__ == "__main__":
    build_scene()

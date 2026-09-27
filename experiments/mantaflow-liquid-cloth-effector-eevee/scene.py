from __future__ import annotations

import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EXPERIMENT = "mantaflow-liquid-cloth-effector-eevee"
BLEND_PATH = OUTPUT_DIR / f"{EXPERIMENT}.blend"
REPORT_PATH = OUTPUT_DIR / f"{EXPERIMENT}-report.json"
PREVIEW_PATH = OUTPUT_DIR / "preview.png"
VIDEO_STEM = OUTPUT_DIR / EXPERIMENT
VIDEO_PATH = OUTPUT_DIR / f"{EXPERIMENT}.mp4"
CACHE_DIR = OUTPUT_DIR / "mantaflow-cache"

FRAME_START = 1
FRAME_END = 96
FPS = 24
PREVIEW_FRAME = 48
RES_X = 480
RES_Y = 360
DOMAIN_RESOLUTION = 48

CLOTH_W = 3.7
CLOTH_D = 3.1
CLOTH_NX = 41
CLOTH_NY = 35


def clear_scene():
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


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_material(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def make_water_material():
    mat = bpy.data.materials.new("MantaflowWaterMaterial")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (0.025, 0.24, 0.68, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.16
    bsdf.inputs["Metallic"].default_value = 0.02

    for name in ("IOR",):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = 1.333

    for name in ("Transmission Weight", "Transmission"):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = 0.28
            break
    return mat


def make_cloth_mesh():
    verts = []
    faces = []

    for j in range(CLOTH_NY):
        v = j / (CLOTH_NY - 1)
        y = -CLOTH_D * 0.5 + CLOTH_D * v
        yn = y / (CLOTH_D * 0.5)

        for i in range(CLOTH_NX):
            u = i / (CLOTH_NX - 1)
            x = -CLOTH_W * 0.5 + CLOTH_W * u
            xn = x / (CLOTH_W * 0.5)

            # A cloth-like shallow hammock/basin: low in the center and
            # rising toward the perimeter. This is intentionally a static
            # Cloth-shaped effector for the first Mantaflow test.
            r2 = xn * xn + yn * yn
            z = 1.23 + 0.47 * min(1.0, r2)
            z += 0.018 * math.sin(i * 0.48) * math.sin(j * 0.43)
            verts.append((x, y, z))

    for j in range(CLOTH_NY - 1):
        for i in range(CLOTH_NX - 1):
            a = j * CLOTH_NX + i
            faces.append((a, a + 1, a + CLOTH_NX + 1, a + CLOTH_NX))

    mesh = bpy.data.meshes.new("MantaflowClothMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    cloth = bpy.data.objects.new("MantaflowClothEffector", mesh)
    bpy.context.collection.objects.link(cloth)
    cloth.data.materials.append(
        make_material(
            "MantaflowClothMaterial",
            (0.72, 0.055, 0.035, 1.0),
            roughness=0.74,
        )
    )

    # Fluid modifier must see the open cloth surface, while render thickness
    # may be added after it in the modifier stack.
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
    eff.subframes = 2
    eff.velocity_factor = 1.0

    solid = cloth.modifiers.new("RenderThickness", type="SOLIDIFY")
    solid.thickness = 0.028
    solid.offset = 0.0

    sub = cloth.modifiers.new("RenderSubdivision", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 1
    sub.render_levels = 1

    return cloth


def make_flow_source():
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 3.72))
    source = bpy.context.object
    source.name = "LiquidInitialBlock"
    source.scale = (0.68, 0.58, 0.46)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    source.hide_render = True

    fluid = source.modifiers.new("FluidFlow", type="FLUID")
    fluid.fluid_type = "FLOW"
    bpy.context.view_layer.objects.active = source
    bpy.context.view_layer.update()

    flow = fluid.flow_settings
    if flow is None:
        raise RuntimeError("Fluid flow settings were not created")
    flow.flow_type = "LIQUID"
    flow.flow_behavior = "GEOMETRY"
    flow.use_plane_init = False
    flow.surface_distance = 1.5

    return source


def make_domain():
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 2.45))
    domain = bpy.context.object
    domain.name = "LiquidDomain"
    domain.scale = (2.55, 2.20, 2.45)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    domain.data.materials.append(make_water_material())

    fluid = domain.modifiers.new("FluidDomain", type="FLUID")
    fluid.fluid_type = "DOMAIN"
    bpy.context.view_layer.objects.active = domain
    bpy.context.view_layer.update()

    settings = fluid.domain_settings
    if settings is None:
        raise RuntimeError("Fluid domain settings were not created")

    settings.domain_type = "LIQUID"
    settings.cache_type = "ALL"
    settings.cache_directory = str(CACHE_DIR.resolve())
    settings.cache_frame_start = FRAME_START
    settings.cache_frame_end = FRAME_END
    settings.resolution_max = DOMAIN_RESOLUTION
    settings.time_scale = 1.0
    settings.timesteps_min = 1
    settings.timesteps_max = 4
    settings.cfl_condition = 2.0
    settings.simulation_method = "FLIP"

    settings.use_mesh = True
    settings.mesh_scale = 1
    settings.mesh_particle_radius = 1.6
    settings.mesh_smoothen_pos = 2
    settings.mesh_smoothen_neg = 2
    settings.use_fractions = True
    settings.use_flip_particles = True

    return domain, fluid


def make_floor_visual():
    bpy.ops.mesh.primitive_plane_add(size=10.0, location=(0.0, 0.0, 0.015))
    floor = bpy.context.object
    floor.name = "FloorVisual"
    floor.data.materials.append(
        make_material("FloorMaterial", (0.018, 0.022, 0.032, 1.0), roughness=0.88)
    )
    return floor


def setup_camera_lights(scene):
    bpy.ops.object.camera_add(location=(6.3, -7.4, 4.7))
    camera = bpy.context.object
    camera.name = "Camera"
    camera.data.lens = 48
    look_at(camera, (0.0, 0.0, 1.75))
    scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(3.5, -2.2, 6.4))
    key = bpy.context.object
    key.name = "KeyLight"
    key.data.energy = 1050
    key.data.shape = "DISK"
    key.data.size = 4.5
    look_at(key, (0.0, 0.0, 1.6))

    bpy.ops.object.light_add(type="AREA", location=(-4.2, 1.8, 4.3))
    fill = bpy.context.object
    fill.name = "FillLight"
    fill.data.energy = 720
    fill.data.size = 3.5
    look_at(fill, (0.0, 0.0, 1.5))

    bpy.ops.object.light_add(type="AREA", location=(0.0, 4.2, 5.2))
    rim = bpy.context.object
    rim.name = "RimLight"
    rim.data.energy = 820
    rim.data.size = 3.0
    look_at(rim, (0.0, 0.0, 1.7))


def fluid_mesh_stats(scene, domain, frames):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    out = {}

    for frame in frames:
        scene.frame_set(frame)
        depsgraph.update()
        eval_obj = domain.evaluated_get(depsgraph)
        mesh = eval_obj.to_mesh()
        coords = [eval_obj.matrix_world @ v.co for v in mesh.vertices]

        if coords:
            xs = [p.x for p in coords]
            ys = [p.y for p in coords]
            zs = [p.z for p in coords]
            bounds = {
                "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
                "span": [max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)],
            }
        else:
            bounds = None

        out[str(frame)] = {
            "vertex_count": len(mesh.vertices),
            "face_count": len(mesh.polygons),
            "bounds": bounds,
        }
        eval_obj.to_mesh_clear()

    return out


def render_outputs(scene):
    # MP4 animation rendered by Blender on the same runner that owns the
    # Mantaflow cache.
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "REALTIME"
    scene.render.filepath = str(VIDEO_STEM)
    scene.render.use_file_extension = True
    bpy.ops.render.render(animation=True)

    if not VIDEO_PATH.exists():
        candidates = sorted(OUTPUT_DIR.glob(f"{EXPERIMENT}*.mp4"))
        if candidates:
            candidates[0].replace(VIDEO_PATH)

    scene.frame_set(PREVIEW_FRAME)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_PATH)
    bpy.ops.render.render(write_still=True)


def build_scene():
    clear_scene()
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

    if hasattr(scene, "eevee"):
        pass

    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.004, 0.007, 0.015, 1.0)
    bg.inputs["Strength"].default_value = 0.16

    make_floor_visual()
    cloth = make_cloth_mesh()
    source = make_flow_source()
    domain, domain_mod = make_domain()
    setup_camera_lights(scene)

    # Save once before baking: Mantaflow expects a saved scene/cache context.
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

    sampled = fluid_mesh_stats(
        scene,
        domain,
        [1, 24, 48, 72, 96],
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
            "mode": "one-way Mantaflow liquid -> static Cloth-shaped effector obstacle",
            "liquid_reads_cloth_effector": True,
            "cloth_reads_liquid_force": False,
            "cloth_is_dynamic": False,
            "goal": "prove Blender 4.0.2 headless Mantaflow liquid can collide with a Cloth-like planar effector in Actions",
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
        "cloth_effector": {
            "name": cloth.name,
            "vertex_count": len(cloth.data.vertices),
            "face_count": len(cloth.data.polygons),
            "planar_effector": True,
            "surface_distance": 1.0,
        },
        "flow": {
            "name": source.name,
            "behavior": "GEOMETRY",
            "type": "LIQUID",
            "initial_center": [0.0, 0.0, 3.72],
            "initial_half_extents": [0.68, 0.58, 0.46],
        },
        "fluid_mesh_samples": sampled,
        "blend": BLEND_PATH.name,
        "video": VIDEO_PATH.name,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    # Preserve the baked-domain settings/cache references in the blend.
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    render_outputs(scene)

    print(f"MANTAFLOW_BAKE_SECONDS={bake_seconds:.3f}")
    print(f"MANTAFLOW_CACHE_FILES={len(cache_files)}")
    print(f"MANTAFLOW_CACHE_BYTES={cache_bytes}")
    for frame, stat in sampled.items():
        print(
            f"MANTAFLOW_SAMPLE_{frame}_VERTICES="
            f"{stat['vertex_count']}"
        )
    print(f"VIDEO_PATH={VIDEO_PATH}")
    print(f"PREVIEW_PATH={PREVIEW_PATH}")


if __name__ == "__main__":
    build_scene()

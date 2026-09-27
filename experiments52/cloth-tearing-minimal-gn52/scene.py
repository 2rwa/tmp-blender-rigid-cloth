from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path.cwd()
OUT = ROOT / "output52"
FRAMES = OUT / "frames"
OUT.mkdir(parents=True, exist_ok=True)
FRAMES.mkdir(parents=True, exist_ok=True)

EXPERIMENT = "cloth-tearing-minimal-gn52"
FRAME_START = 1
FRAME_END = 72
FPS = 24
RES_X = 480
RES_Y = 360
NX = 37
NZ = 29
WIDTH = 3.7
HEIGHT = 2.9


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def material(name, color, roughness=0.5):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def make_cloth():
    verts = []
    faces = []
    pin_indices = []

    for j in range(NZ):
        z = 3.55 - HEIGHT * j / (NZ - 1)
        for i in range(NX):
            x = -WIDTH * 0.5 + WIDTH * i / (NX - 1)
            # Tiny deterministic perturbation breaks perfect symmetry and
            # encourages a visible local tear instead of one uniform stretch.
            y = 0.012 * math.sin(i * 0.71) * math.sin(j * 0.53)
            idx = len(verts)
            verts.append((x, y, z))
            if j == 0:
                pin_indices.append(idx)

    for j in range(NZ - 1):
        for i in range(NX - 1):
            a = j * NX + i
            faces.append((a, a + 1, a + NX + 1, a + NX))

    mesh = bpy.data.meshes.new("TearingClothMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new("TearingCloth", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material("TearingClothMaterial", (0.72, 0.035, 0.025, 1.0), 0.68))

    vg = obj.vertex_groups.new(name="PinnedTop")
    vg.add(pin_indices, 1.0, "REPLACE")
    return obj, len(pin_indices)


def add_backdrop():
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.50, 2.05), scale=(2.45, 0.08, 2.05))
    board = bpy.context.object
    board.name = "Backdrop"
    board.data.materials.append(material("BackdropMaterial", (0.055, 0.065, 0.085, 1.0), 0.8))

    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 3.72), scale=(2.2, 0.10, 0.10))
    bar = bpy.context.object
    bar.name = "SupportBar"
    bar.data.materials.append(material("SupportMaterial", (0.12, 0.13, 0.15, 1.0), 0.35))


def setup_camera(scene):
    bpy.ops.object.camera_add(location=(0.0, -7.4, 2.25))
    cam = bpy.context.object
    cam.data.lens = 54
    look_at(cam, (0.0, 0.0, 2.15))
    scene.camera = cam

    bpy.ops.object.light_add(type="AREA", location=(-3.5, -3.0, 5.7))
    key = bpy.context.object
    key.data.energy = 900
    key.data.size = 4.0
    look_at(key, (0.0, 0.0, 2.0))

    bpy.ops.object.light_add(type="AREA", location=(3.0, -1.8, 3.0))
    fill = bpy.context.object
    fill.data.energy = 560
    fill.data.size = 3.0
    look_at(fill, (0.0, 0.0, 2.0))


def interface_inputs(group):
    result = []
    for item in group.interface.items_tree:
        if getattr(item, "item_type", None) != "SOCKET":
            continue
        if getattr(item, "in_out", None) != "INPUT":
            continue
        result.append(
            {
                "name": item.name,
                "identifier": item.identifier,
                "socket_type": getattr(item, "socket_type", None),
            }
        )
    return result


def load_cloth_asset_directly():
    asset_name = "Cloth Dynamics (Experimental)"
    roots = []
    for kind in ("LOCAL", "SYSTEM"):
        try:
            roots.append(Path(bpy.utils.resource_path(kind)) / "datafiles" / "assets")
        except Exception:
            pass

    scanned = []
    for root in roots:
        if not root.exists():
            continue
        for blend in root.rglob("*.blend"):
            scanned.append(str(blend))
            try:
                with bpy.data.libraries.load(str(blend), assets_only=True) as (src, dst):
                    if asset_name in src.node_groups:
                        dst.node_groups = [asset_name]
                group = bpy.data.node_groups.get(asset_name)
                if group is not None:
                    return group, str(blend), scanned
            except Exception:
                continue

    raise RuntimeError(
        "Cloth Dynamics asset not found in bundled essentials. "
        f"roots={roots}, scanned={len(scanned)}"
    )


def add_cloth_dynamics(obj):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    asset_name = "Cloth Dynamics (Experimental)"
    rel_candidates = [
        "nodes/geometry_nodes_essentials.blend/NodeTree/Cloth Dynamics (Experimental)",
        "geometry_nodes/geometry_nodes_essentials.blend/NodeTree/Cloth Dynamics (Experimental)",
    ]

    source = None
    modifier = None
    operator_errors = []

    for rel in rel_candidates:
        try:
            before = len(obj.modifiers)
            result = bpy.ops.object.modifier_add_node_group(
                asset_library_type="ESSENTIALS",
                asset_library_identifier="",
                relative_asset_identifier=rel,
                use_selected_objects=False,
            )
            if "FINISHED" in result and len(obj.modifiers) > before:
                modifier = obj.modifiers[-1]
                source = f"operator:{rel}"
                break
        except Exception as exc:
            operator_errors.append(f"{rel}: {exc!r}")

    scanned = []
    if modifier is None:
        group, path, scanned = load_cloth_asset_directly()
        modifier = obj.modifiers.new(name=asset_name, type="NODES")
        modifier.node_group = group
        source = f"direct:{path}"

    if modifier.node_group is None:
        raise RuntimeError(
            f"Cloth Dynamics modifier has no node group; errors={operator_errors}"
        )

    inputs = interface_inputs(modifier.node_group)
    applied = {}

    def matching(name):
        return [item for item in inputs if item["name"].strip().lower() == name.lower()]

    def runtime_input(item):
        props = modifier.properties
        if props is None:
            raise RuntimeError("Geometry Nodes modifier has no runtime properties")
        try:
            return getattr(props.inputs, item["identifier"])
        except AttributeError as exc:
            raise RuntimeError(
                f"runtime input missing for {item['name']} / {item['identifier']}"
            ) from exc

    def set_scalar(name, value, socket_hint=None):
        matches = matching(name)
        if socket_hint:
            matches = [
                item for item in matches
                if socket_hint.lower() in str(item["socket_type"]).lower()
            ]
        if not matches:
            return False
        item = matches[0]
        prop = runtime_input(item)
        prop.value = value
        applied[f"{name}:{item['identifier']}"] = value
        return True

    # Blender 5.2 moved Geometry Nodes modifier inputs from ID properties
    # to proper RNA objects under modifier.properties.inputs.
    pins = matching("Pin Group")
    if not pins:
        raise RuntimeError(f"Pin Group input missing: {inputs}")
    pin = pins[0]
    pin_prop = runtime_input(pin)
    pin_prop.type = "ATTRIBUTE"
    pin_prop.attribute_name = "PinnedTop"
    applied[f"Pin Group:{pin['identifier']}"] = "attribute:PinnedTop"

    # Conservative solver settings, but intentionally tear-friendly material.
    set_scalar("Substeps", 8)
    set_scalar("Constraint Iterations", 24)
    set_scalar("Stretchiness", 0.08)
    set_scalar("Bendiness", 0.22)
    set_scalar("Mass", 1.0)
    set_scalar("Linear", 0.035)

    if not set_scalar("Tearing", True, "Bool"):
        # Some asset revisions expose the panel toggle as a generic boolean
        # socket without preserving NodeSocketBool in the interface string.
        if not set_scalar("Tearing", True):
            raise RuntimeError(f"Tearing input missing: {inputs}")

    if not set_scalar("Threshold", 1.012):
        raise RuntimeError(f"Tearing Threshold input missing: {inputs}")

    # Strong gravity makes the hanging curtain exceed the low tearing strain.
    gravity_matches = matching("Gravity")
    for item in gravity_matches:
        st = str(item["socket_type"])
        if "Vector" in st:
            runtime_input(item).value = (0.0, 0.0, -32.0)
            applied[f"Gravity:{item['identifier']}"] = [0.0, 0.0, -32.0]
        elif "Bool" in st:
            runtime_input(item).value = True
            applied[f"Gravity:{item['identifier']}"] = True

    try:
        modifier.node_group.interface_update(bpy.context)
    except Exception:
        pass

    return modifier, {
        "source": source,
        "operator_errors": operator_errors,
        "direct_scan_count": len(scanned),
        "inputs": inputs,
        "applied": applied,
    }


def connected_components(mesh):
    parent = list(range(len(mesh.vertices)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for edge in mesh.edges:
        union(edge.vertices[0], edge.vertices[1])

    return len({find(i) for i in range(len(parent))}) if parent else 0


def eval_topology(obj, depsgraph):
    eval_obj = obj.evaluated_get(depsgraph)
    mesh = eval_obj.to_mesh()
    coords = [eval_obj.matrix_world @ v.co for v in mesh.vertices]

    if coords:
        xs = [p.x for p in coords]
        ys = [p.y for p in coords]
        zs = [p.z for p in coords]
        bounds = {
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        }
    else:
        bounds = None

    stat = {
        "vertices": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "components": connected_components(mesh),
        "bounds": bounds,
    }
    eval_obj.to_mesh_clear()
    return stat


def choose_engine(scene):
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            scene.render.engine = engine
            return engine
        except Exception:
            continue
    raise RuntimeError("No EEVEE render engine available")


def main():
    clear_scene()

    scene = bpy.context.scene
    scene.frame_start = FRAME_START
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    engine = choose_engine(scene)

    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.006, 0.008, 0.014, 1.0)
    bg.inputs["Strength"].default_value = 0.16

    cloth, pin_count = make_cloth()
    add_backdrop()
    setup_camera(scene)
    modifier, asset_info = add_cloth_dynamics(cloth)

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()

    base = {
        "vertices": len(cloth.data.vertices),
        "edges": len(cloth.data.edges),
        "faces": len(cloth.data.polygons),
    }

    samples = []
    first_tear = None
    max_vertices = base["vertices"]
    max_components = 1

    for frame in range(FRAME_START, FRAME_END + 1):
        scene.frame_set(frame)
        depsgraph.update()
        stat = eval_topology(cloth, depsgraph)
        stat["frame"] = frame
        samples.append(stat)

        max_vertices = max(max_vertices, stat["vertices"])
        max_components = max(max_components, stat["components"])

        changed = (
            stat["vertices"] != base["vertices"]
            or stat["edges"] != base["edges"]
            or stat["faces"] != base["faces"]
        )
        if first_tear is None and changed:
            first_tear = frame
            print(
                "TEAR_FIRST_FRAME="
                f"{frame} vertices={stat['vertices']} edges={stat['edges']} "
                f"faces={stat['faces']} components={stat['components']}"
            )

        if frame % 6 == 0 or frame == 1:
            print(
                f"TEAR_FRAME={frame} "
                f"vertices={stat['vertices']} edges={stat['edges']} "
                f"faces={stat['faces']} components={stat['components']}"
            )

        scene.render.filepath = str(FRAMES / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)

    preview_frame = min(
        FRAME_END,
        (first_tear + 6) if first_tear is not None else FRAME_END,
    )
    shutil.copy2(
        FRAMES / f"frame_{preview_frame:04d}.png",
        OUT / "preview.png",
    )

    report = {
        "experiment": EXPERIMENT,
        "blender_version": bpy.app.version_string,
        "engine": engine,
        "frame_start": FRAME_START,
        "frame_end": FRAME_END,
        "fps": FPS,
        "resolution": [RES_X, RES_Y],
        "solver": "Geometry Nodes Cloth Dynamics / XPBD",
        "experimental": True,
        "cloth": {
            "grid": [NX, NZ],
            "pin_vertex_count": pin_count,
            "base_topology": base,
        },
        "asset": asset_info,
        "tearing": {
            "enabled": True,
            "threshold_requested": 1.012,
            "first_tear_frame": first_tear,
            "max_vertices": max_vertices,
            "max_components": max_components,
            "topology_changed": first_tear is not None,
            "preview_frame": preview_frame,
        },
        "samples": samples,
    }

    (OUT / f"{EXPERIMENT}-report.json").write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    bpy.ops.wm.save_as_mainfile(
        filepath=str(OUT / f"{EXPERIMENT}.blend")
    )

    print(f"BLENDER52_VERSION={bpy.app.version_string}")
    print(f"TEAR_ASSET_SOURCE={asset_info['source']}")
    print(f"TEAR_FIRST_FRAME={first_tear}")
    print(f"TEAR_MAX_VERTICES={max_vertices}")
    print(f"TEAR_MAX_COMPONENTS={max_components}")
    print(f"TEAR_PREVIEW_FRAME={preview_frame}")


if __name__ == "__main__":
    main()

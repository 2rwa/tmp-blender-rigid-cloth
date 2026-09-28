from __future__ import annotations
import json, math, shutil
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path.cwd(); OUT=ROOT/"output52"; FRAMES=OUT/"frames"
FRAME_START=1; FRAME_END=72; FPS=24; RES_X=480; RES_Y=360

def clear_scene():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)

def look_at(obj,target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat("-Z","Y").to_euler()

def material(name,color,roughness=.5,metallic=0.0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    b=m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value=color; b.inputs["Roughness"].default_value=roughness; b.inputs["Metallic"].default_value=metallic
    return m

def choose_engine(scene):
    for engine in ("BLENDER_EEVEE_NEXT","BLENDER_EEVEE"):
        try: scene.render.engine=engine; return engine
        except Exception: pass
    raise RuntimeError("No EEVEE render engine")

def interface_inputs(group):
    out=[]
    for item in group.interface.items_tree:
        if getattr(item,"item_type",None)=="SOCKET" and getattr(item,"in_out",None)=="INPUT":
            out.append({"name":item.name,"identifier":item.identifier,"socket_type":getattr(item,"socket_type",None)})
    return out

def load_asset(name):
    roots=[]
    for kind in ("LOCAL","SYSTEM"):
        try: roots.append(Path(bpy.utils.resource_path(kind))/"datafiles"/"assets")
        except Exception: pass
    scanned=0
    for root in roots:
        if not root.exists(): continue
        for blend in root.rglob("*.blend"):
            scanned+=1
            try:
                with bpy.data.libraries.load(str(blend),assets_only=True) as (src,dst):
                    if name in src.node_groups: dst.node_groups=[name]
                group=bpy.data.node_groups.get(name)
                if group is not None: return group,str(blend),scanned
            except Exception: pass
    raise RuntimeError(f"asset not found: {name}; scanned={scanned}")

def add_asset_modifier(obj,name):
    bpy.context.view_layer.objects.active=obj; obj.select_set(True)
    errors=[]
    for rel in (f"nodes/geometry_nodes_essentials.blend/NodeTree/{name}",f"geometry_nodes/geometry_nodes_essentials.blend/NodeTree/{name}"):
        try:
            before=len(obj.modifiers)
            result=bpy.ops.object.modifier_add_node_group(asset_library_type="ESSENTIALS",asset_library_identifier="",relative_asset_identifier=rel,use_selected_objects=False)
            if "FINISHED" in result and len(obj.modifiers)>before and obj.modifiers[-1].node_group:
                return obj.modifiers[-1],f"operator:{rel}",errors
        except Exception as exc: errors.append(repr(exc))
    group,path,count=load_asset(name)
    mod=obj.modifiers.new(name=name,type="NODES"); mod.node_group=group
    return mod,f"direct:{path}",errors+[f"direct_scan_count={count}"]

def access(mod):
    inputs=interface_inputs(mod.node_group)
    def matching(name): return [i for i in inputs if i["name"].strip().lower()==name.lower()]
    def prop(item): return getattr(mod.properties.inputs,item["identifier"])
    def set_value(name,value,hint=None,required=False):
        items=matching(name)
        if hint: items=[i for i in items if hint.lower() in str(i["socket_type"]).lower()]
        if not items:
            if required: raise RuntimeError(f"missing input {name}: {inputs}")
            return False
        prop(items[0]).value=value; return True
    def set_attr(name,attr,required=False):
        items=matching(name)
        if not items:
            if required: raise RuntimeError(f"missing field input {name}: {inputs}")
            return False
        p=prop(items[0]); p.type="ATTRIBUTE"; p.attribute_name=attr; return True
    def set_menu(name,wanted):
        items=matching(name)
        if not items: return False
        p=prop(items[0])
        for candidate in (wanted,wanted.upper(),wanted.lower()):
            try: p.value=candidate; return True
            except Exception: pass
        try:
            ep=p.bl_rna.properties.get("value")
            for item in ep.enum_items:
                if item.name.lower()==wanted.lower() or item.identifier.lower()==wanted.lower():
                    p.value=item.identifier; return True
        except Exception: pass
        return False
    return inputs,prop,matching,set_value,set_attr,set_menu

def tear_allowed(pattern,mid,cfg):
    x,y,z=mid
    if pattern=="centerline": return abs(x)<=cfg.get("tear_half_width",.20)
    if pattern=="local-zone": return math.hypot(x,z-cfg.get("impact_z",2.1))<=cfg.get("tear_radius",.68)
    if pattern=="notch": return abs(x)<=cfg.get("tear_half_width",.22) and 1.25<=z<=3.05
    if pattern=="hammock": return math.hypot(x,y)<=cfg.get("tear_radius",.95)
    if pattern=="swing":
        dz=z-(cfg.get("impact_z",2.1)+cfg.get("tear_slope",.34)*x)
        return abs(dz)<=cfg.get("tear_half_width",.22) and abs(x)<=1.35
    return True

def make_cloth(cfg):
    nx=cfg.get("nx",45); nz=cfg.get("nz",35); width=cfg.get("width",3.9); height=cfg.get("height",3.0)
    pattern=cfg["pattern"]; horizontal=pattern=="hammock"; verts=[]; faces=[]; pins=[]
    for j in range(nz):
        for i in range(nx):
            u=i/(nx-1); v=j/(nz-1); x=-width*.5+width*u
            if horizontal:
                y=-height*.5+height*v; z=2.15-.06*math.sin(math.pi*u)*math.sin(math.pi*v)
                idx=len(verts); verts.append((x,y,z))
                if (i<=1 or i>=nx-2) and (j<=1 or j>=nz-2): pins.append(idx)
            else:
                z=3.55-height*v; y=.010*math.sin(i*.71)*math.sin(j*.53)
                idx=len(verts); verts.append((x,y,z))
                if j==0: pins.append(idx)
    ci=(nx-1)//2; notch_rows=set(range((nz-1)//2-2,(nz-1)//2+2))
    for j in range(nz-1):
        for i in range(nx-1):
            if pattern=="notch" and i==ci-1 and j in notch_rows: continue
            a=j*nx+i; faces.append((a,a+1,a+nx+1,a+nx))
    mesh=bpy.data.meshes.new("ImpactTearingClothMesh"); mesh.from_pydata(verts,[],faces); mesh.update()
    attr=mesh.attributes.new(name="TearEdges",type="FLOAT",domain="EDGE"); tear_count=0
    for edge,datum in zip(mesh.edges,attr.data):
        a=verts[edge.vertices[0]]; b=verts[edge.vertices[1]]
        mid=((a[0]+b[0])*.5,(a[1]+b[1])*.5,(a[2]+b[2])*.5)
        ok=tear_allowed(pattern,mid,cfg); datum.value=1.0 if ok else 0.0; tear_count+=int(ok)
    obj=bpy.data.objects.new("ImpactTearingCloth",mesh); bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material("ImpactClothMaterial",(0.72,0.035,0.025,1),.62))
    vg=obj.vertex_groups.new(name="Pinned"); vg.add(pins,1.0,"REPLACE")
    return obj,{"grid":[nx,nz],"pin_vertex_count":len(pins),"tear_edge_count":tear_count,"notch_face_count":4 if pattern=="notch" else 0}

def add_collider(ball,cfg):
    mod,source,errors=add_asset_modifier(ball,"Collider")
    inputs,prop,matching,set_value,set_attr,set_menu=access(mod)
    set_value("Deforming",False); set_value("Boundary",False); set_value("Margin",cfg.get("collision_margin",.025)); set_value("Friction",.20); set_value("Softness",0.0)
    return {"source":source,"operator_errors":errors,"inputs":inputs}

def add_ball(cfg,effectors):
    r=cfg.get("ball_radius",.34); start=tuple(cfg["ball_start"]); impact=tuple(cfg["ball_impact"]); end=tuple(cfg["ball_end"])
    impact_frame=int(cfg.get("impact_frame",28)); end_frame=int(cfg.get("end_frame",44)); render_end=int(cfg.get("render_end_frame",FRAME_END))
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3,radius=r,location=start)
    ball=bpy.context.object; ball.name="ImpactBall"; ball.data.materials.append(material("ImpactBallMaterial",tuple(cfg.get("ball_color",(0.05,0.28,0.86,1))),.24,.15))
    effectors.objects.link(ball)
    for frame,loc in ((1,start),(impact_frame,impact),(end_frame,end),(render_end,end)):
        ball.location=loc; ball.keyframe_insert(data_path="location",frame=frame)
    try:
        for curve in ball.animation_data.action.fcurves:
            for key in curve.keyframe_points: key.interpolation="LINEAR"
    except Exception: pass
    return ball,{"radius":r,"start":start,"impact":impact,"end":end,"impact_frame":impact_frame,"end_frame":end_frame,"render_end_frame":render_end,"collider":add_collider(ball,cfg)}

def add_cloth_dynamics(obj,effectors,cfg):
    mod,source,errors=add_asset_modifier(obj,"Cloth Dynamics (Experimental)")
    inputs,prop,matching,set_value,set_attr,set_menu=access(mod)
    set_attr("Pin Group","Pinned",True)
    set_value("Substeps",cfg.get("substeps",14),required=True)
    if not set_value("Constraint Steps",cfg.get("constraint_steps",30)): set_value("Constraint Iterations",cfg.get("constraint_steps",30),required=True)
    set_value("Stretchiness",cfg.get("stretchiness",.05),required=True); set_value("Bendiness",cfg.get("bendiness",.18),required=True)
    set_value("Mass",cfg.get("mass",.65),required=True)
    if not set_value("Linear Damping",.035): set_value("Linear",.035)
    set_value("Tearing",True,"Bool",True); custom=set_menu("Tearing Mode","Custom")
    set_attr("Tearing Edge Group","TearEdges",True); set_value("Tearing Threshold",cfg.get("threshold",1.11),required=True)
    coll=matching("Effectors Collection") or matching("Collection")
    if not coll: raise RuntimeError(f"Effectors Collection input missing: {inputs}")
    prop(coll[0]).value=effectors
    for item in matching("Gravity"):
        st=str(item["socket_type"])
        if "Vector" in st: prop(item).value=tuple(cfg.get("gravity",(0,0,-9.81)))
        elif "Bool" in st: prop(item).value=True
    return {"source":source,"operator_errors":errors,"inputs":inputs,"applied":{"tearing_mode_custom_applied":custom,"tear_edge_attribute":"TearEdges","effectors_collection":effectors.name}}

def setup_stage(scene,cfg):
    if cfg["pattern"]=="hammock":
        bpy.ops.mesh.primitive_cube_add(location=(0,0,.08),scale=(2.6,2.1,.08)); bpy.context.object.data.materials.append(material("Floor",(0.04,.05,.065,1),.82))
        camera_location=tuple(cfg.get("camera_location",(5.6,-6.5,4.8)))
        camera_target=tuple(cfg.get("camera_target",(0,0,1.95)))
        bpy.ops.object.camera_add(location=camera_location); scene.camera=bpy.context.object; scene.camera.data.lens=cfg.get("camera_lens",52); look_at(scene.camera,camera_target)
    else:
        bpy.ops.mesh.primitive_cube_add(location=(0,.58,2.05),scale=(2.55,.07,2.05)); bpy.context.object.data.materials.append(material("Backdrop",(0.04,.05,.07,1),.82))
        bpy.ops.mesh.primitive_cube_add(location=(0,0,3.72),scale=(2.25,.10,.10)); bpy.context.object.data.materials.append(material("Support",(0.13,.14,.16,1),.38))
        camera_location=tuple(cfg.get("camera_location",(0,-7.4,2.25)))
        camera_target=tuple(cfg.get("camera_target",(0,0,2.15)))
        bpy.ops.object.camera_add(location=camera_location); scene.camera=bpy.context.object; scene.camera.data.lens=cfg.get("camera_lens",54); look_at(scene.camera,camera_target)
    bpy.ops.object.light_add(type="AREA",location=(-3.5,-3,5.7)); key=bpy.context.object; key.data.energy=950; key.data.size=4; look_at(key,(0,0,2))
    bpy.ops.object.light_add(type="AREA",location=(3.2,-1.5,3.2)); fill=bpy.context.object; fill.data.energy=520; fill.data.size=3; look_at(fill,(0,0,2))

def connected_components(mesh):
    parent=list(range(len(mesh.vertices)))
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def union(a,b):
        a=find(a); b=find(b)
        if a!=b: parent[b]=a
    for e in mesh.edges: union(e.vertices[0],e.vertices[1])
    return len({find(i) for i in range(len(parent))}) if parent else 0

def eval_topology(obj,deps):
    eo=obj.evaluated_get(deps); mesh=eo.to_mesh(); pts=[eo.matrix_world@v.co for v in mesh.vertices]
    s={"vertices":len(mesh.vertices),"edges":len(mesh.edges),"faces":len(mesh.polygons),"components":connected_components(mesh)}
    if pts: s["bounds"]={"min":[min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)],"max":[max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)]}
    eo.to_mesh_clear(); return s

def run(cfg):
    OUT.mkdir(parents=True,exist_ok=True)
    if FRAMES.exists(): shutil.rmtree(FRAMES)
    FRAMES.mkdir(parents=True); clear_scene()
    render_end=int(cfg.get("render_end_frame",FRAME_END))
    scene=bpy.context.scene; scene.frame_start=FRAME_START; scene.frame_end=render_end; scene.render.fps=FPS; scene.render.resolution_x=RES_X; scene.render.resolution_y=RES_Y; scene.render.resolution_percentage=100; scene.render.image_settings.file_format="PNG"
    engine=choose_engine(scene); scene.world.use_nodes=True; bg=scene.world.node_tree.nodes.get("Background"); bg.inputs["Color"].default_value=(.006,.008,.014,1); bg.inputs["Strength"].default_value=.16
    setup_stage(scene,cfg); effectors=bpy.data.collections.new("ImpactEffectors"); scene.collection.children.link(effectors)
    cloth,cloth_info=make_cloth(cfg); ball,ball_info=add_ball(cfg,effectors); asset_info=add_cloth_dynamics(cloth,effectors,cfg)
    bpy.context.view_layer.update(); deps=bpy.context.evaluated_depsgraph_get()
    base={"vertices":len(cloth.data.vertices),"edges":len(cloth.data.edges),"faces":len(cloth.data.polygons)}
    first=None; maxv=base["vertices"]; maxc=1; samples=[]
    for frame in range(FRAME_START,render_end+1):
        scene.frame_set(frame); deps.update(); s=eval_topology(cloth,deps); s["frame"]=frame; s["ball_location"]=list(ball.matrix_world.translation); samples.append(s)
        maxv=max(maxv,s["vertices"]); maxc=max(maxc,s["components"])
        changed=s["vertices"]!=base["vertices"] or s["edges"]!=base["edges"] or s["faces"]!=base["faces"]
        if first is None and changed: first=frame; print(f"IMPACT_TEAR_FIRST={frame} vertices={s['vertices']} edges={s['edges']} components={s['components']}")
        if frame%6==0 or frame in (1,ball_info["impact_frame"]): print(f"IMPACT_TEAR_FRAME={frame} vertices={s['vertices']} components={s['components']} ball={tuple(round(v,3) for v in ball.matrix_world.translation)}")
        scene.render.filepath=str(FRAMES/f"frame_{frame:04d}.png"); bpy.ops.render.render(write_still=True)
    preview=min(render_end,max(ball_info["impact_frame"]+3,(first+4) if first else ball_info["impact_frame"]+8)); shutil.copy2(FRAMES/f"frame_{preview:04d}.png",OUT/"preview.png")
    exp=cfg["experiment"]; report={"experiment":exp,"pattern":cfg["pattern"],"blender_version":bpy.app.version_string,"engine":engine,"frame_start":FRAME_START,"frame_end":render_end,"fps":FPS,"resolution":[RES_X,RES_Y],"solver":"Geometry Nodes Cloth Dynamics / XPBD","experimental":True,"coupling":"prescribed closed collider ball -> Cloth Dynamics","cloth":{**cloth_info,"base_topology":base},"ball":ball_info,"asset":asset_info,"tearing":{"enabled":True,"threshold_requested":cfg.get("threshold",1.11),"first_tear_frame":first,"max_vertices":maxv,"max_components":maxc,"topology_changed":first is not None,"tear_after_planned_contact":first is not None and first>=ball_info["impact_frame"]-2,"preview_frame":preview},"samples":samples,"config":cfg}
    (OUT/f"{exp}-report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8"); bpy.ops.wm.save_as_mainfile(filepath=str(OUT/f"{exp}.blend"))
    print(f"IMPACT_PATTERN={cfg['pattern']}"); print(f"IMPACT_PLANNED_FRAME={ball_info['impact_frame']}"); print(f"IMPACT_TEAR_FIRST_FRAME={first}"); print(f"IMPACT_TEAR_MAX_VERTICES={maxv}"); print(f"IMPACT_TEAR_MAX_COMPONENTS={maxc}")

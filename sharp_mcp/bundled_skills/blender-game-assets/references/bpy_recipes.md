# bpy Modeling Recipes for Game Assets

Tested procedural modeling snippets for use with `execute_blender_code`.

---

## 1. Clean Object & Mesh Initialization

```python
import bpy
import bmesh
from mathutils import Vector, Matrix

def create_mesh_object(name: str):
    # Remove existing object with the same name if present
    existing = bpy.data.objects.get(name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj, mesh
```

---

## 2. Recipe: Procedural Roman Gladius (Melee Weapon)

```python
import bpy, bmesh
from mathutils import Vector

obj, mesh = create_mesh_object("Gladius_V1")
bm = bmesh.new()

# 1. Hilt / Pommel (Sphere or flattened cylinder at Z = 0)
pommel = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.045)
bmesh.ops.scale(bm, vec=Vector((1.0, 0.8, 0.8)), verts=pommel['verts'])
bmesh.ops.translate(bm, vec=Vector((0, 0, -0.05)), verts=pommel['verts'])

# 2. Grip (Octagonal cylinder)
grip = bmesh.ops.create_cone(
    bm, cap_ends=True, cap_tris=False, segments=8,
    radius1=0.022, radius2=0.022, depth=0.12
)
bmesh.ops.translate(bm, vec=Vector((0, 0, 0.03)), verts=grip['verts'])

# 3. Guard (Elliptical wooden guard)
guard = bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.scale(bm, vec=Vector((0.14, 0.045, 0.035)), verts=guard['verts'])
bmesh.ops.translate(bm, vec=Vector((0, 0, 0.105)), verts=guard['verts'])

# 4. Blade Base & Diamond Cross-Section Extrusion
# Mainz style: waist in middle, long point
blade_verts = [
    bm.verts.new(Vector((-0.035, 0.0, 0.12))),
    bm.verts.new(Vector((0.0, 0.008, 0.12))),
    bm.verts.new(Vector((0.035, 0.0, 0.12))),
    bm.verts.new(Vector((0.0, -0.008, 0.12))),
]
f_base = bm.faces.new(blade_verts)

# Extrude through blade sections (waist at 0.35m, widening at 0.50m, point at 0.65m)
sections = [
    (0.35, Vector((0.85, 0.9, 1.0))),  # Waist
    (0.50, Vector((1.05, 1.0, 1.0))),  # Swell
    (0.65, Vector((0.05, 0.1, 1.0))),  # Point
]

curr_face = f_base
prev_z = 0.12
for z_pos, scale_vec in sections:
    res = bmesh.ops.extrude_face_region(bm, geom=[curr_face])
    new_verts = [v for v in res['geom'] if isinstance(v, bmesh.types.BMVert)]
    dz = z_pos - prev_z
    bmesh.ops.translate(bm, vec=Vector((0, 0, dz)), verts=new_verts)
    center = sum((v.co for v in new_verts), Vector()) / len(new_verts)
    for v in new_verts:
        v.co = center + Vector(((v.co.x - center.x) * scale_vec.x,
                                (v.co.y - center.y) * scale_vec.y,
                                (v.co.z - center.z) * scale_vec.z))
    prev_z = z_pos
    curr_face = [f for f in res['geom'] if isinstance(f, bmesh.types.BMFace)][0]

# Weld the tip vertices
tip_verts = curr_face.verts
tip_center = sum((v.co for v in tip_verts), Vector()) / len(tip_verts)
tip_vert = bm.verts.new(tip_center + Vector((0, 0, 0.02)))
for i in range(len(tip_verts)):
    bm.faces.new([tip_verts[i], tip_verts[(i+1)%len(tip_verts)], tip_vert])
bm.faces.remove(curr_face)

# Recalculate outside normals & remove duplicates
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

bm.to_mesh(mesh)
bm.free()

# Origin is already at grip center (0, 0, 0)!
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
```

---

## 3. Recipe: Robust Principled BSDF PBR Setup

```python
def setup_pbr_material(obj, mat_name: str, base_color=(0.8, 0.8, 0.8, 1.0), roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    
    # Always lookup by node type to avoid localization crashes
    bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = base_color
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    
    if len(obj.data.materials) == 0:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat
    return mat
```

---

## 4. Recipe: Export to glTF & FBX

```python
def export_game_asset(obj, export_dir: str, base_name: str):
    import os
    os.makedirs(export_dir, exist_ok=True)
    
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    
    # 1. glTF / GLB (Binary)
    glb_path = os.path.join(export_dir, base_name + ".glb")
    bpy.ops.export_scene.gltf(
        filepath=glb_path,
        export_format='GLB',
        use_selection=True,
        export_apply=True,
        export_normals=True
    )
    
    # 2. FBX (Engine ready)
    fbx_path = os.path.join(export_dir, base_name + ".fbx")
    bpy.ops.export_scene.fbx(
        filepath=fbx_path,
        use_selection=True,
        apply_scale_options='FBX_SCALE_ALL',
        axis_forward='-Z',
        axis_up='Y'
    )
    return {"glb": glb_path, "fbx": fbx_path}
```

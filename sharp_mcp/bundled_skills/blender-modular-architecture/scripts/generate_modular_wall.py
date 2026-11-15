"""Procedural Modular Roman Arch Wall Generator for Blender.
Run via execute_blender_code to generate a clean 4m x 4m snap module.
"""
import bpy
import bmesh
import math
from mathutils import Vector

def create_arch_wall(name="Modular_Roman_Arch_4m"):
    existing = bpy.data.objects.get(name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)

    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    bm = bmesh.new()

    # Dimensions
    w_half = 2.0  # 4m total width
    d_half = 0.35 # 0.7m wall thickness
    h_total = 4.0
    r_arch = 1.15 # 2.3m arch diameter
    h_spring = 2.2 # arch springline elevation

    # 1. Left Pier
    p_left = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((w_half - r_arch, d_half * 2, h_spring)), verts=p_left['verts'])
    bmesh.ops.translate(bm, vec=Vector((- (r_arch + (w_half - r_arch)/2), 0, h_spring / 2)), verts=p_left['verts'])

    # 2. Right Pier
    p_right = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((w_half - r_arch, d_half * 2, h_spring)), verts=p_right['verts'])
    bmesh.ops.translate(bm, vec=Vector((r_arch + (w_half - r_arch)/2, 0, h_spring / 2)), verts=p_right['verts'])

    # 3. Top Lintel / Attic Block
    lintel_h = h_total - (h_spring + r_arch)
    top_block = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((w_half * 2, d_half * 2, lintel_h)), verts=top_block['verts'])
    bmesh.ops.translate(bm, vec=Vector((0, 0, h_spring + r_arch + lintel_h / 2)), verts=top_block['verts'])

    # 4. Cornice Projection (decorative rim)
    cornice = bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector((w_half * 2 + 0.15, d_half * 2 + 0.15, 0.25)), verts=cornice['verts'])
    bmesh.ops.translate(bm, vec=Vector((0, 0, h_total - 0.125)), verts=cornice['verts'])

    # 5. Semi-circular Arch Voussoir ring
    segments = 12
    for i in range(segments):
        a1 = math.pi * i / segments
        a2 = math.pi * (i + 1) / segments
        x1_in = math.cos(a1) * r_arch
        z1_in = h_spring + math.sin(a1) * r_arch
        x2_in = math.cos(a2) * r_arch
        z2_in = h_spring + math.sin(a2) * r_arch

        r_outer = r_arch + 0.22
        x1_out = math.cos(a1) * r_outer
        z1_out = h_spring + math.sin(a1) * r_outer
        x2_out = math.cos(a2) * r_outer
        z2_out = h_spring + math.sin(a2) * r_outer

        # Front quad
        v1 = bm.verts.new(Vector((x1_in, d_half + 0.03, z1_in)))
        v2 = bm.verts.new(Vector((x2_in, d_half + 0.03, z2_in)))
        v3 = bm.verts.new(Vector((x2_out, d_half + 0.03, z2_out)))
        v4 = bm.verts.new(Vector((x1_out, d_half + 0.03, z1_out)))
        bm.faces.new([v1, v2, v3, v4])

        # Back quad
        b1 = bm.verts.new(Vector((x1_in, -d_half - 0.03, z1_in)))
        b2 = bm.verts.new(Vector((x2_in, -d_half - 0.03, z2_in)))
        b3 = bm.verts.new(Vector((x2_out, -d_half - 0.03, z2_out)))
        b4 = bm.verts.new(Vector((x1_out, -d_half - 0.03, z1_out)))
        bm.faces.new([b4, b3, b2, b1])

        # Inner soffit face
        bm.faces.new([v2, v1, b1, b2])

    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)

    bm.to_mesh(mesh)
    bm.free()

    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj

if __name__ == "__main__":
    arch = create_arch_wall()
    print("Created modular arch wall:", arch.name)

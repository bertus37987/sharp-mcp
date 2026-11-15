"""Game Asset Topology & Quality Auditor for Blender.
Run directly inside Blender via execute_blender_code or from a script.
"""
import bpy
import bmesh
from mathutils import Vector

def audit_object(obj: bpy.types.Object) -> dict:
    if obj.type != 'MESH':
        return {"error": f"Object {obj.name} is not a mesh ({obj.type})"}

    mesh = obj.data
    bm = bmesh.new()
    bm.from_mesh(mesh)

    tri_count = sum(len(f.verts) - 2 for f in bm.faces)
    face_count = len(bm.faces)
    vert_count = len(bm.verts)
    edge_count = len(bm.edges)

    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    tris = sum(1 for f in bm.faces if len(f.verts) == 3)
    ngons = sum(1 for f in bm.faces if len(f.verts) > 4)

    non_manifold_edges = sum(1 for e in bm.edges if not e.is_manifold)
    zero_area_faces = sum(1 for f in bm.faces if f.calc_area() < 1e-6)

    # Check unapplied scale / rotation
    scale_applied = all(abs(s - 1.0) < 1e-4 for s in obj.scale)
    rotation_applied = all(abs(r) < 1e-4 for r in obj.rotation_euler)

    # Bounding box dimensions
    dims = [obj.dimensions.x, obj.dimensions.y, obj.dimensions.z]

    bm.free()

    result = {
        "name": obj.name,
        "triangles": tri_count,
        "faces": face_count,
        "verts": vert_count,
        "quads": quads,
        "tris": tris,
        "ngons": ngons,
        "non_manifold_edges": non_manifold_edges,
        "zero_area_faces": zero_area_faces,
        "scale_applied": scale_applied,
        "rotation_applied": rotation_applied,
        "dimensions": dims,
        "passed": (non_manifold_edges == 0 and ngons == 0 and scale_applied and rotation_applied)
    }
    return result

if __name__ == "__main__":
    active = bpy.context.active_object
    if active:
        res = audit_object(active)
        print("AUDIT RESULT:", res)
    else:
        print("No active object selected for audit.")

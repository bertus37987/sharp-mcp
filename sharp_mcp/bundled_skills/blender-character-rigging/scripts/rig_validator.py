"""Humanoid / R15 Rig & Skinning Validator.
Inspects active mesh and armature for game engine compliance.
"""
import bpy

def validate_rig(mesh_obj: bpy.types.Object, arm_obj: bpy.types.Object) -> dict:
    issues = []
    
    if mesh_obj.type != 'MESH':
        return {"passed": False, "error": f"{mesh_obj.name} is not a mesh"}
    if arm_obj.type != 'ARMATURE':
        return {"passed": False, "error": f"{arm_obj.name} is not an armature"}

    arm_bones = set(arm_obj.data.bones.keys())
    vgroups = {vg.index: vg.name for vg in mesh_obj.vertex_groups}

    # 1. Check for unassigned vertex groups
    orphaned_groups = [name for name in vgroups.values() if name not in arm_bones]
    if orphaned_groups:
        issues.append(f"Vertex groups not in armature: {orphaned_groups[:5]}")

    # 2. Check for vertices with 0 weight or > 4 weights
    mesh = mesh_obj.data
    unweighted_verts = 0
    over_limit_verts = 0

    for v in mesh.vertices:
        deform_weights = [g for g in v.groups if vgroups.get(g.group) in arm_bones and g.weight > 1e-4]
        if len(deform_weights) == 0:
            unweighted_verts += 1
        elif len(deform_weights) > 4:
            over_limit_verts += 1

    if unweighted_verts > 0:
        issues.append(f"{unweighted_verts} vertices have 0 weight (will cause spiking/stretching)")
    if over_limit_verts > 0:
        issues.append(f"{over_limit_verts} vertices have >4 bone weights (exceeds game engine limits)")

    # 3. Check transforms
    if any(abs(s - 1.0) > 1e-4 for s in mesh_obj.scale) or any(abs(s - 1.0) > 1e-4 for s in arm_obj.scale):
        issues.append("Unapplied scale detected on mesh or armature. Run transform_apply!")

    return {
        "passed": len(issues) == 0,
        "mesh": mesh_obj.name,
        "armature": arm_obj.name,
        "bone_count": len(arm_bones),
        "issues": issues,
    }

if __name__ == "__main__":
    sel = bpy.context.selected_objects
    mesh = next((o for o in sel if o.type == 'MESH'), None)
    arm = next((o for o in sel if o.type == 'ARMATURE'), None)
    if mesh and arm:
        res = validate_rig(mesh, arm)
        print("RIG VALIDATION:", res)
    else:
        print("Select both a Mesh and an Armature to validate.")

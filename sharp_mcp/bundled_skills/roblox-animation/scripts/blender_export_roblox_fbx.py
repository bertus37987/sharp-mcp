"""Export Blender 5.2+ rigs and animations to Roblox Studio-compliant FBX files.

Applies officially verified Roblox FBX settings:
- apply_scale_options='FBX_SCALE_UNITS' (1 Blender Unit = 1 Stud)
- axis_forward='-Z', axis_up='Y'
- primary_bone_axis='Y', secondary_bone_axis='X'
- add_leaf_bones=False, use_armature_deform_only=True
- bake_anim_simplify_factor=0.0, bake_anim_use_nla_strips=False, bake_anim_use_all_actions=False
"""
from __future__ import annotations

from pathlib import Path

import bpy


def export_roblox_fbx(
    filepath: str | Path,
    armature_obj: bpy.types.Object,
    mode: str = "animation",
    mesh_objects: list[bpy.types.Object] | None = None,
    unit_scale: float | None = None,
) -> Path:
    """Export an Armature-only animation FBX or a Skinned Rigged Mesh FBX for Roblox Studio.

    Args:
        filepath: Output .fbx file path.
        armature_obj: Target Blender Armature object.
        mode:
            - "animation": Armature-only FBX for Studio Animation Editor / Import FBX Animation.
            - "rigged_mesh": Skinned Mesh + Armature static rig (with embedded textures).
            - "rigged_with_anim": Skinned Mesh + Armature + baked active Action.
        mesh_objects: Optional list of Mesh objects for rigged_mesh / rigged_with_anim.
            If omitted, uses all MESH children of armature_obj.
        unit_scale: Override Blender-units-per-stud (defaults to armature's roblox_unit_scale or 1.0).
    """
    out_path = Path(filepath)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if unit_scale is None:
        unit_scale = float(armature_obj.get("roblox_unit_scale", 1.0))
    global_scale = 1.0 / unit_scale if unit_scale else 1.0

    if mesh_objects is None and mode in {"rigged_mesh", "rigged_with_anim"}:
        mesh_objects = [ch for ch in armature_obj.children if ch.type == "MESH"]

    prev_mode = bpy.context.mode
    if prev_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    bpy.ops.object.select_all(action="DESELECT")
    armature_obj.select_set(True)
    bpy.context.view_layer.objects.active = armature_obj

    if mode == "animation":
        object_types = {"ARMATURE"}
        bake_anim = True
        path_mode = "AUTO"
        embed_textures = False
    elif mode == "rigged_mesh":
        for m in (mesh_objects or []):
            m.select_set(True)
        object_types = {"ARMATURE", "MESH"}
        bake_anim = False
        path_mode = "COPY"
        embed_textures = True
    elif mode == "rigged_with_anim":
        for m in (mesh_objects or []):
            m.select_set(True)
        object_types = {"ARMATURE", "MESH"}
        bake_anim = True
        path_mode = "COPY"
        embed_textures = True
    else:
        raise ValueError(f"Unsupported mode '{mode}'. Use 'animation', 'rigged_mesh', or 'rigged_with_anim'.")

    bpy.ops.export_scene.fbx(
        filepath=str(out_path),
        use_selection=True,
        object_types=object_types,
        global_scale=global_scale,
        apply_scale_options="FBX_SCALE_UNITS",
        axis_forward="-Z",
        axis_up="Y",
        primary_bone_axis="Y",
        secondary_bone_axis="X",
        use_armature_deform_only=True,
        add_leaf_bones=False,
        bake_anim=bake_anim,
        bake_anim_use_all_bones=True,
        bake_anim_use_nla_strips=False,
        bake_anim_use_all_actions=False,
        bake_anim_force_startend_keying=False,
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        path_mode=path_mode,
        embed_textures=embed_textures,
        use_custom_props=True,
    )
    return out_path

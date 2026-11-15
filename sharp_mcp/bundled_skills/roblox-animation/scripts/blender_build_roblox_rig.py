"""Build an exact 1:1 Roblox Armature (+ optional proxy meshes & IK controls) in Blender 5.2+.

Supports:
- Any live rig dumped by `probe_rig.luau` (`rig_spec.json` or Python dict):
  R15 (AnimationConstraint or Motor6D), R6, Skinned MeshPart+Bone, Weapons, Shields,
  Non-Humanoid Vehicles / Doors / Creatures.
- Built-in calibrated Blocky R15 and Blocky R6 templates when no rig_spec is supplied.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

try:
    from blender_anim_helpers import (
        ROBLOX_TO_BLENDER,
        ROBLOX_TO_BLENDER_INV,
        roblox_cf_to_matrix,
    )
except ImportError:
    import sys
    here = str(Path(__file__).resolve().parent)
    if here not in sys.path:
        sys.path.insert(0, here)
    from blender_anim_helpers import (
        ROBLOX_TO_BLENDER,
        ROBLOX_TO_BLENDER_INV,
        roblox_cf_to_matrix,
    )


def builtin_r15_spec() -> dict[str, Any]:
    """Calibrated standard Classic Blocky R15 (1.0) rig specification in Roblox studs."""
    # Exact classic blocky R15 measurements (HumanoidRootPart center at Y = 3.0 studs)
    parts = {
        "HumanoidRootPart": {"size": [2.0, 2.0, 1.0], "cf": [0, 3.0, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LowerTorso":       {"size": [2.0, 0.4, 1.0], "cf": [0, 2.2, 0, 1,0,0, 0,1,0, 0,0,1]},
        "UpperTorso":       {"size": [2.0, 1.6, 1.0], "cf": [0, 3.2, 0, 1,0,0, 0,1,0, 0,0,1]},
        "Head":             {"size": [1.2, 1.2, 1.2], "cf": [0, 4.6, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftUpperArm":     {"size": [1.0, 1.2, 1.0], "cf": [-1.5, 3.4, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftLowerArm":     {"size": [1.0, 0.7, 1.0], "cf": [-1.5, 2.55, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftHand":         {"size": [1.0, 0.3, 1.0], "cf": [-1.5, 2.05, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightUpperArm":    {"size": [1.0, 1.2, 1.0], "cf": [ 1.5, 3.4, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightLowerArm":    {"size": [1.0, 0.7, 1.0], "cf": [ 1.5, 2.55, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightHand":        {"size": [1.0, 0.3, 1.0], "cf": [ 1.5, 2.05, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftUpperLeg":     {"size": [1.0, 1.1, 1.0], "cf": [-0.5, 1.45, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftLowerLeg":     {"size": [1.0, 0.7, 1.0], "cf": [-0.5, 0.65, 0, 1,0,0, 0,1,0, 0,0,1]},
        "LeftFoot":         {"size": [1.0, 0.3, 1.0], "cf": [-0.5, 0.15, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightUpperLeg":    {"size": [1.0, 1.1, 1.0], "cf": [ 0.5, 1.45, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightLowerLeg":    {"size": [1.0, 0.7, 1.0], "cf": [ 0.5, 0.65, 0, 1,0,0, 0,1,0, 0,0,1]},
        "RightFoot":        {"size": [1.0, 0.3, 1.0], "cf": [ 0.5, 0.15, 0, 1,0,0, 0,1,0, 0,0,1]},
    }
    def id_cf(x, y, z):
        return [x, y, z, 1,0,0, 0,1,0, 0,0,1]

    joints = [
        {"name": "Root",          "kind": "Motor6D", "p0": "HumanoidRootPart", "p1": "LowerTorso",    "c0": id_cf(0, -1.0, 0),    "c1": id_cf(0, -0.2, 0)},
        {"name": "Waist",         "kind": "Motor6D", "p0": "LowerTorso",       "p1": "UpperTorso",    "c0": id_cf(0, 0.2, 0),     "c1": id_cf(0, -0.8, 0)},
        {"name": "Neck",          "kind": "Motor6D", "p0": "UpperTorso",       "p1": "Head",          "c0": id_cf(0, 0.8, 0),     "c1": id_cf(0, -0.6, 0)},
        {"name": "LeftShoulder",  "kind": "Motor6D", "p0": "UpperTorso",       "p1": "LeftUpperArm",  "c0": id_cf(-1.0, 0.6, 0),  "c1": id_cf(0.5, 0.4, 0)},
        {"name": "LeftElbow",     "kind": "Motor6D", "p0": "LeftUpperArm",     "p1": "LeftLowerArm",  "c0": id_cf(0, -0.5, 0),    "c1": id_cf(0, 0.35, 0)},
        {"name": "LeftWrist",     "kind": "Motor6D", "p0": "LeftLowerArm",     "p1": "LeftHand",      "c0": id_cf(0, -0.35, 0),   "c1": id_cf(0, 0.15, 0)},
        {"name": "RightShoulder", "kind": "Motor6D", "p0": "UpperTorso",       "p1": "RightUpperArm", "c0": id_cf(1.0, 0.6, 0),   "c1": id_cf(-0.5, 0.4, 0)},
        {"name": "RightElbow",    "kind": "Motor6D", "p0": "RightUpperArm",    "p1": "RightLowerArm", "c0": id_cf(0, -0.5, 0),    "c1": id_cf(0, 0.35, 0)},
        {"name": "RightWrist",    "kind": "Motor6D", "p0": "RightLowerArm",    "p1": "RightHand",     "c0": id_cf(0, -0.35, 0),   "c1": id_cf(0, 0.15, 0)},
        {"name": "LeftHip",       "kind": "Motor6D", "p0": "LowerTorso",       "p1": "LeftUpperLeg",  "c0": id_cf(-0.5, -0.2, 0), "c1": id_cf(0, 0.55, 0)},
        {"name": "LeftKnee",      "kind": "Motor6D", "p0": "LeftUpperLeg",     "p1": "LeftLowerLeg",  "c0": id_cf(0, -0.55, 0),   "c1": id_cf(0, 0.35, 0)},
        {"name": "LeftAnkle",     "kind": "Motor6D", "p0": "LeftLowerLeg",     "p1": "LeftFoot",      "c0": id_cf(0, -0.35, 0),   "c1": id_cf(0, 0.15, 0)},
        {"name": "RightHip",      "kind": "Motor6D", "p0": "LowerTorso",       "p1": "RightUpperLeg", "c0": id_cf(0.5, -0.2, 0),  "c1": id_cf(0, 0.55, 0)},
        {"name": "RightKnee",     "kind": "Motor6D", "p0": "RightUpperLeg",    "p1": "RightLowerLeg", "c0": id_cf(0, -0.55, 0),   "c1": id_cf(0, 0.35, 0)},
        {"name": "RightAnkle",    "kind": "Motor6D", "p0": "RightLowerLeg",    "p1": "RightFoot",     "c0": id_cf(0, -0.35, 0),   "c1": id_cf(0, 0.15, 0)},
    ]
    grips = {
        "RightHand.RightGripAttachment": {"name": "RightGripAttachment", "parent": "RightHand", "cf": [0, -0.15, 0, 1,0,0, 0,0,1, 0,-1,0]},
        "LeftHand.LeftGripAttachment":   {"name": "LeftGripAttachment",  "parent": "LeftHand",  "cf": [0, -0.15, 0, 1,0,0, 0,0,1, 0,-1,0]},
    }
    return {
        "modelName": "BlockyR15",
        "rigKind": "R15",
        "hasHumanoid": True,
        "hasAnimationController": False,
        "rootName": "HumanoidRootPart",
        "parts": parts,
        "joints": joints,
        "bones": [],
        "grips": grips,
    }


def builtin_r6_spec() -> dict[str, Any]:
    """Calibrated standard Classic Blocky R6 rig specification in Roblox studs."""
    def id_cf(x, y, z):
        return [x, y, z, 1,0,0, 0,1,0, 0,0,1]

    parts = {
        "HumanoidRootPart": {"size": [2.0, 2.0, 1.0], "cf": id_cf(0, 3.0, 0)},
        "Torso":            {"size": [2.0, 2.0, 1.0], "cf": id_cf(0, 3.0, 0)},
        "Head":             {"size": [2.0, 1.0, 1.0], "cf": id_cf(0, 4.5, 0)},
        "Left Arm":         {"size": [1.0, 2.0, 1.0], "cf": id_cf(-1.5, 3.0, 0)},
        "Right Arm":        {"size": [1.0, 2.0, 1.0], "cf": id_cf( 1.5, 3.0, 0)},
        "Left Leg":         {"size": [1.0, 2.0, 1.0], "cf": id_cf(-0.5, 1.0, 0)},
        "Right Leg":        {"size": [1.0, 2.0, 1.0], "cf": id_cf( 0.5, 1.0, 0)},
    }
    joints = [
        {"name": "RootJoint",      "kind": "Motor6D", "p0": "HumanoidRootPart", "p1": "Torso",     "c0": id_cf(0, 0, 0),    "c1": id_cf(0, 0, 0)},
        {"name": "Neck",           "kind": "Motor6D", "p0": "Torso",            "p1": "Head",      "c0": id_cf(0, 1.0, 0),  "c1": id_cf(0, -0.5, 0)},
        {"name": "Left Shoulder",  "kind": "Motor6D", "p0": "Torso",            "p1": "Left Arm",  "c0": id_cf(-1.0, 0.5, 0), "c1": id_cf(0.5, 0.5, 0)},
        {"name": "Right Shoulder", "kind": "Motor6D", "p0": "Torso",            "p1": "Right Arm", "c0": id_cf(1.0, 0.5, 0),  "c1": id_cf(-0.5, 0.5, 0)},
        {"name": "Left Hip",       "kind": "Motor6D", "p0": "Torso",            "p1": "Left Leg",  "c0": id_cf(-0.5, -1.0, 0), "c1": id_cf(0, 1.0, 0)},
        {"name": "Right Hip",      "kind": "Motor6D", "p0": "Torso",            "p1": "Right Leg", "c0": id_cf(0.5, -1.0, 0),  "c1": id_cf(0, 1.0, 0)},
    ]
    return {
        "modelName": "BlockyR6",
        "rigKind": "R6",
        "hasHumanoid": True,
        "hasAnimationController": False,
        "rootName": "HumanoidRootPart",
        "parts": parts,
        "joints": joints,
        "bones": [],
        "grips": {},
    }


def _create_box_proxy(
    name: str,
    size_studs: list[float],
    world_mat_blender: Matrix,
    rig_obj: bpy.types.Object,
    bone_name: str,
    unit_scale: float,
    color: tuple[float, float, float, float] = (0.55, 0.62, 0.72, 1.0),
) -> bpy.types.Object:
    """Create a lightweight visual box proxy parented cleanly to an armature bone."""
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    # Roblox (sx, sy, sz) -> Blender (sx, sz, sy)
    sx, sy, sz = size_studs
    scale_mat = Matrix.Diagonal((sx * unit_scale, sz * unit_scale, sy * unit_scale, 1.0))
    bmesh.ops.transform(bm, matrix=scale_mat, verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    mat_name = f"M_Proxy_{name}"
    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = 0.65
    mesh.materials.append(mat)

    bone = rig_obj.data.bones[bone_name]
    obj.parent = rig_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    # Blender bone-parenting anchors relative to bone TAIL! Offset by -bone.length along +Y.
    tail_offset = Matrix.Translation((0.0, -bone.length, 0.0))
    obj.matrix_parent_inverse = tail_offset @ bone.matrix_local.inverted()
    obj.matrix_basis = world_mat_blender
    return obj


def _orient_edit_bone(eb: bpy.types.EditBone, frame_blender: Matrix, length: float) -> None:
    """Place an EditBone so its rest matrix_local matches frame_blender exactly."""
    head = frame_blender.translation
    rot = frame_blender.to_3x3()
    eb.head = head
    eb.tail = head + (rot @ Vector((0.0, 1.0, 0.0))) * length
    eb.align_roll(rot @ Vector((0.0, 0.0, 1.0)))


def build_rig_from_spec(
    spec: dict[str, Any] | str | Path = "R15",
    name: str | None = None,
    unit_scale: float = 1.0,
    create_proxies: bool = True,
    add_ik_controls: bool = False,
) -> bpy.types.Object:
    """Build a 1:1 Roblox armature in Blender from a rig_spec JSON/dict or 'R15'/'R6' preset."""
    if isinstance(spec, (str, Path)):
        key = str(spec).upper()
        if key == "R15":
            data = builtin_r15_spec()
        elif key == "R6":
            data = builtin_r6_spec()
        else:
            data = json.loads(Path(spec).read_text(encoding="utf-8"))
    else:
        data = spec

    rig_name = name or f"{data.get('modelName', 'RobloxRig')}_Rig"
    arm_data = bpy.data.armatures.new(f"{rig_name}_Data")
    rig_obj = bpy.data.objects.new(rig_name, arm_data)
    bpy.context.collection.objects.link(rig_obj)
    bpy.context.view_layer.objects.active = rig_obj

    parts = data.get("parts", {})
    joints = data.get("joints", [])
    bones_list = data.get("bones", [])
    root_name = data.get("rootName") or ("HumanoidRootPart" if "HumanoidRootPart" in parts else next(iter(parts), "Root"))

    # Compute Roblox-space rest frames for parts & joint pivots
    part_mats: dict[str, Matrix] = {
        p_name: roblox_cf_to_matrix(p_info["cf"], unit_scale=unit_scale)
        for p_name, p_info in parts.items()
    }
    bone_frames: dict[str, Matrix] = {}
    parents: dict[str, str | None] = {}

    if root_name in part_mats:
        bone_frames[root_name] = part_mats[root_name]
        parents[root_name] = None

    for j in joints:
        p0, p1 = j["p0"], j["p1"]
        if p0 in part_mats:
            c0_b = roblox_cf_to_matrix(j["c0"], unit_scale=unit_scale)
            # Notice conjugation distributes over multiplication:
            # S (P0 * C0) S^-1 = (S P0 S^-1) * (S C0 S^-1)
            bone_frames[p1] = part_mats[p0] @ c0_b
            parents[p1] = p0

    # Also support Skinned Mesh Bone entries
    for b in bones_list:
        bname = b["name"]
        bone_frames[bname] = roblox_cf_to_matrix(b["worldCf"], unit_scale=unit_scale)
        parents[bname] = b["parent"] if b.get("parentIsBone") else b.get("hostPart")

    # Sort topologically so parents are created before children
    ordered: list[str] = []
    remaining = list(bone_frames.keys())
    while remaining:
        progressed = False
        for bname in list(remaining):
            par = parents.get(bname)
            if par is None or par in ordered or par not in bone_frames:
                ordered.append(bname)
                remaining.remove(bname)
                progressed = True
        if not progressed:
            ordered.extend(remaining)
            break

    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones: dict[str, bpy.types.EditBone] = {}
    bone_len = 0.25 * unit_scale

    for bname in ordered:
        eb = arm_data.edit_bones.new(bname)
        _orient_edit_bone(eb, bone_frames[bname], bone_len)
        eb.use_deform = True
        edit_bones[bname] = eb

    for bname in ordered:
        par = parents.get(bname)
        if par and par in edit_bones:
            edit_bones[bname].parent = edit_bones[par]

    bpy.ops.object.mode_set(mode="OBJECT")

    # Store metadata on the armature for downstream baking & export
    rig_obj["roblox_unit_scale"] = float(unit_scale)
    rig_obj["roblox_rig_meta"] = json.dumps({
        "rigKind": data.get("rigKind", "Custom"),
        "rootName": root_name,
        "bones": ordered,
        "parents": {b: parents.get(b) for b in ordered},
        "grips": data.get("grips", {}),
    })

    if create_proxies and parts:
        palette = {
            "Head": (0.95, 0.80, 0.55, 1.0),
            "UpperTorso": (0.25, 0.42, 0.72, 1.0),
            "Torso": (0.25, 0.42, 0.72, 1.0),
            "LowerTorso": (0.20, 0.34, 0.60, 1.0),
            "HumanoidRootPart": (0.4, 0.4, 0.4, 0.2),
        }
        for p_name, p_info in parts.items():
            if p_name == "HumanoidRootPart":
                continue  # skip invisible HRP proxy unless no other torso exists
            target_bone = p_name if p_name in edit_bones or p_name in rig_obj.data.bones else root_name
            if target_bone not in rig_obj.data.bones:
                continue
            col = palette.get(p_name, (0.35, 0.65, 0.45, 1.0) if "Leg" in p_name or "Foot" in p_name else (0.85, 0.72, 0.48, 1.0))
            _create_box_proxy(
                name=f"Proxy_{p_name}",
                size_studs=p_info["size"],
                world_mat_blender=part_mats[p_name],
                rig_obj=rig_obj,
                bone_name=target_bone,
                unit_scale=unit_scale,
                color=col,
            )

    if add_ik_controls and data.get("rigKind") == "R15":
        _setup_r15_leg_ik(rig_obj, unit_scale)

    return rig_obj


def _setup_r15_leg_ik(rig_obj: bpy.types.Object, unit_scale: float) -> None:
    """Add non-deforming IK_LeftFoot and IK_RightFoot controls for grounded walk cycles."""
    bpy.context.view_layer.objects.active = rig_obj
    bpy.ops.object.mode_set(mode="EDIT")
    arm = rig_obj.data
    for side in ("Left", "Right"):
        foot_eb = arm.edit_bones.get(f"{side}Foot")
        if not foot_eb:
            continue
        ik_eb = arm.edit_bones.new(f"IK_{side}Foot")
        ik_eb.head = foot_eb.head.copy()
        ik_eb.tail = ik_eb.head + Vector((0.0, -0.4 * unit_scale, 0.0))
        ik_eb.use_deform = False

    bpy.ops.object.mode_set(mode="POSE")
    for side in ("Left", "Right"):
        lower_leg = rig_obj.pose.bones.get(f"{side}LowerLeg")
        if lower_leg:
            ik = lower_leg.constraints.new("IK")
            ik.target = rig_obj
            ik.subtarget = f"IK_{side}Foot"
            ik.chain_count = 2
    bpy.ops.object.mode_set(mode="OBJECT")


def attach_prop_proxy(
    rig_obj: bpy.types.Object,
    prop_name: str,
    size_studs: tuple[float, float, float],
    parent_bone: str = "RightHand",
    local_offset_studs: tuple[float, float, float] = (0.0, -0.2, -1.2),
    local_rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    color: tuple[float, float, float, float] = (0.75, 0.22, 0.18, 1.0),
) -> bpy.types.Object:
    """Attach a rigid weapon/shield proxy to a bone for visual collision/facing checks in Blender."""
    unit_scale = float(rig_obj.get("roblox_unit_scale", 1.0))
    bone = rig_obj.data.bones[parent_bone]
    rx, ry, rz = (math.radians(a) for a in local_rot_deg)
    off_rbx = (
        Matrix.Translation(Vector(local_offset_studs) * unit_scale)
        @ Matrix.Rotation(rx, 4, "X")
        @ Matrix.Rotation(ry, 4, "Y")
        @ Matrix.Rotation(rz, 4, "Z")
    )
    off_bl = ROBLOX_TO_BLENDER @ off_rbx @ ROBLOX_TO_BLENDER_INV
    world_mat = rig_obj.matrix_world @ bone.matrix_local @ off_bl
    return _create_box_proxy(prop_name, list(size_studs), world_mat, rig_obj, parent_bone, unit_scale, color=color)

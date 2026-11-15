"""Blender 5.2+ & legacy-compatible animation helpers for Roblox rigs.

Provides:
- Coordinate system conjugation between Roblox (+X right, +Y up, -Z forward, studs)
  and Blender (+X right, +Z up, -Y forward, BU).
- Blender 5.2 slotted-action / channelbag F-curve abstraction.
- Pose authoring, seamless cyclic looping, timeline animation markers,
  world-locked shield hand solver, 2-handed IK setup, and rest-delta retargeting.
"""
from __future__ import annotations

import json
import math
from typing import Iterable

import bpy
from mathutils import Euler, Matrix, Quaternion, Vector

# Roblox (x, y, z) -> Blender (x, -z, y)
ROBLOX_TO_BLENDER = Matrix((
    (1.0,  0.0,  0.0, 0.0),
    (0.0,  0.0, -1.0, 0.0),
    (0.0,  1.0,  0.0, 0.0),
    (0.0,  0.0,  0.0, 1.0),
))
ROBLOX_TO_BLENDER_INV = ROBLOX_TO_BLENDER.transposed()
S_3X3 = ROBLOX_TO_BLENDER.to_3x3()
S_3X3_INV = ROBLOX_TO_BLENDER_INV.to_3x3()

DEFAULT_RETARGET_PATTERNS: dict[str, list[str]] = {
    "LowerTorso": [r"^hips?$", r"pelvis", r"^root$", r"^bip01$"],
    "UpperTorso": [r"^spine[123]?$", r"chest", r"upperchest", r"torso"],
    "Head": [r"^head$"],
    "LeftUpperArm": [r"left.*(upper)?arm$", r"l_?(upper)?arm$"],
    "LeftLowerArm": [r"left.*(forearm|lowerarm|elbow)", r"l_?(forearm|lowerarm)"],
    "LeftHand": [r"left.*hand$", r"l_?hand$"],
    "RightUpperArm": [r"right.*(upper)?arm$", r"r_?(upper)?arm$"],
    "RightLowerArm": [r"right.*(forearm|lowerarm|elbow)", r"r_?(forearm|lowerarm)"],
    "RightHand": [r"right.*hand$", r"r_?hand$"],
    "LeftUpperLeg": [r"left.*(upleg|thigh|upperleg)", r"l_?(upleg|thigh|upperleg)"],
    "LeftLowerLeg": [r"left.*(leg|shin|calf|lowerleg)$", r"l_?(leg|shin|calf|lowerleg)$"],
    "LeftFoot": [r"left.*foot$", r"l_?foot$"],
    "RightUpperLeg": [r"right.*(upleg|thigh|upperleg)", r"r_?(upleg|thigh|upperleg)"],
    "RightLowerLeg": [r"right.*(leg|shin|calf|lowerleg)$", r"r_?(leg|shin|calf|lowerleg)$"],
    "RightFoot": [r"right.*foot$", r"r_?foot$"],
}


def roblox_cf_to_matrix(values: Iterable[float], unit_scale: float = 1.0) -> Matrix:
    """Convert Roblox 12-float CFrame [x, y, z, r00..r22] to Blender space Matrix."""
    x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = values
    m_rbx = Matrix((
        (r00, r01, r02, x * unit_scale),
        (r10, r11, r12, y * unit_scale),
        (r20, r21, r22, z * unit_scale),
        (0.0, 0.0, 0.0, 1.0),
    ))
    return ROBLOX_TO_BLENDER @ m_rbx @ ROBLOX_TO_BLENDER_INV


def matrix_to_roblox_cf(mat_blender: Matrix, unit_scale: float = 1.0) -> tuple[list[float], list[float]]:
    """Convert a Blender-space 4x4 Matrix to Roblox (pos_studs[3], rot3x3[9])."""
    m_rbx = ROBLOX_TO_BLENDER_INV @ mat_blender @ ROBLOX_TO_BLENDER
    inv_scale = 1.0 / unit_scale if unit_scale else 1.0
    pos = [round(m_rbx.translation[i] * inv_scale, 6) for i in range(3)]
    r = m_rbx.to_3x3()
    rot = [round(r[i][j], 6) for i in range(3) for j in range(3)]
    return pos, rot


def euler_xyz_roblox(rx_deg: float, ry_deg: float, rz_deg: float) -> Matrix:
    """Equivalent to Roblox CFrame.Angles(rad(rx), rad(ry), rad(rz)) in Blender space."""
    rx, ry, rz = math.radians(rx_deg), math.radians(ry_deg), math.radians(rz_deg)
    r_rbx = Matrix.Rotation(rx, 3, "X") @ Matrix.Rotation(ry, 3, "Y") @ Matrix.Rotation(rz, 3, "Z")
    return (S_3X3 @ r_rbx @ S_3X3_INV).to_4x4()


def ensure_action(obj: bpy.types.Object, action_name: str) -> bpy.types.Action:
    """Assign or create an Action and bind a Blender 5.2 slot/layer/strip if supported."""
    anim_data = obj.animation_data or obj.animation_data_create()
    act = bpy.data.actions.get(action_name) or bpy.data.actions.new(name=action_name)
    anim_data.action = act

    if hasattr(act, "slots"):
        slot = next(
            (s for s in act.slots if s.target_id_type == 'OBJECT' and getattr(s, "name_display", "") == obj.name),
            None,
        )
        if slot is None:
            slot = next((s for s in act.slots if s.target_id_type == 'OBJECT'), None)
        if slot is None:
            slot = act.slots.new(id_type='OBJECT', name=obj.name)
        anim_data.action_slot = slot
        if len(act.layers) == 0:
            layer = act.layers.new(name="Layer")
            layer.strips.new(type='KEYFRAME')
    return act


def get_action_fcurves(obj: bpy.types.Object):
    """Return the active F-curves collection for Blender 5.2+ channelbags or legacy <=4.x."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return []
    act = ad.action
    if hasattr(act, "fcurves"):
        return act.fcurves
    slot = ad.action_slot
    if not slot or not act.layers:
        return []
    strip = act.layers[0].strips[0]
    bag = strip.channelbag(slot, ensure=True)
    return bag.fcurves


def set_bone_pose(
    rig_obj: bpy.types.Object,
    bone_name: str,
    rot_deg: tuple[float, float, float] = (0.0, 0.0, 0.0),
    loc_studs: tuple[float, float, float] | None = None,
    frame: int | None = None,
    interp: str = "BEZIER",
    unit_scale: float | None = None,
) -> None:
    """Pose a bone using Roblox XYZ degrees & optional stud translation, optionally keying a frame."""
    pb = rig_obj.pose.bones.get(bone_name)
    if pb is None:
        raise KeyError(f"PoseBone '{bone_name}' not found on armature '{rig_obj.name}'")
    if unit_scale is None:
        unit_scale = float(rig_obj.get("roblox_unit_scale", 1.0))

    pb.rotation_mode = "QUATERNION"
    pb.rotation_quaternion = euler_xyz_roblox(*rot_deg).to_quaternion()

    if loc_studs is not None:
        v_rbx = Vector(loc_studs) * unit_scale
        pb.location = S_3X3 @ v_rbx

    if frame is not None:
        if rig_obj.animation_data and rig_obj.animation_data.action:
            ensure_action(rig_obj, rig_obj.animation_data.action.name)
        pb.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        if loc_studs is not None:
            pb.keyframe_insert(data_path="location", frame=frame)

        # Apply interpolation on newly inserted keys at this frame
        dp_rot = f'pose.bones["{bone_name}"].rotation_quaternion'
        dp_loc = f'pose.bones["{bone_name}"].location'
        for fc in get_action_fcurves(rig_obj):
            if fc.data_path == dp_rot or (loc_studs is not None and fc.data_path == dp_loc):
                for kp in fc.keyframe_points:
                    if abs(kp.co[0] - frame) < 1e-4:
                        kp.interpolation = interp


def clear_pose(rig_obj: bpy.types.Object) -> None:
    """Reset all pose bones on an armature to identity transforms."""
    for pb in rig_obj.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def make_seamless_loop(rig_obj: bpy.types.Object, start_frame: int, end_frame: int, add_cycles: bool = True) -> int:
    """Match end_frame keys to start_frame and configure cyclic smooth tangents."""
    fcurves = get_action_fcurves(rig_obj)
    updated = 0
    for fc in fcurves:
        start_kp = next((kp for kp in fc.keyframe_points if abs(kp.co[0] - start_frame) < 1e-4), None)
        if start_kp is None:
            continue
        end_kp = next((kp for kp in fc.keyframe_points if abs(kp.co[0] - end_frame) < 1e-4), None)
        if end_kp is None:
            end_kp = fc.keyframe_points.insert(float(end_frame), start_kp.co[1], options={'FAST'})
        else:
            end_kp.co[1] = start_kp.co[1]
        start_kp.interpolation = "BEZIER"
        end_kp.interpolation = "BEZIER"
        start_kp.handle_left_type = "AUTO_CLAMPED"
        start_kp.handle_right_type = "AUTO_CLAMPED"
        end_kp.handle_left_type = "AUTO_CLAMPED"
        end_kp.handle_right_type = "AUTO_CLAMPED"
        fc.update()
        if add_cycles and not any(m.type == 'CYCLES' for m in fc.modifiers):
            mod = fc.modifiers.new(type='CYCLES')
            mod.mode_before = 'REPEAT'
            mod.mode_after = 'REPEAT'
        updated += 1
    return updated


def add_animation_marker(rig_obj: bpy.types.Object, frame: int, name: str, value: str = "") -> None:
    """Register an animation event marker (exported as KeyframeMarker / MarkerCurve)."""
    act = rig_obj.animation_data.action if rig_obj.animation_data else None
    act_name = act.name if act else "__default__"
    raw = rig_obj.get("roblox_anim_markers", "{}")
    store = json.loads(raw) if isinstance(raw, str) else {}
    entries = store.setdefault(act_name, [])
    entries = [e for e in entries if not (e["frame"] == frame and e["name"] == name)]
    entries.append({"frame": int(frame), "name": str(name), "value": str(value)})
    store[act_name] = sorted(entries, key=lambda e: e["frame"])
    rig_obj["roblox_anim_markers"] = json.dumps(store)

    if act is not None and hasattr(act, "pose_markers"):
        pm = act.pose_markers.get(name) or act.pose_markers.new(name)
        pm.frame = int(frame)


def solve_world_locked_hand(
    rig_obj: bpy.types.Object,
    hand_bone_name: str = "LeftHand",
    desired_world_rot_roblox: Matrix | Quaternion | Euler | tuple[float, float, float] | None = None,
    frame: int | None = None,
) -> Quaternion:
    """Set hand_bone rotation so a held shield/banner keeps a target world orientation.

    `desired_world_rot_roblox` may be None (keep rest orientation), a 3-tuple of XYZ
    Euler degrees in Roblox world space, or a Blender Euler/Quaternion/Matrix representing
    the target orientation in Roblox world space. If `frame` is provided, ancestor bones
    should already be keyed at `frame` before calling this helper.
    """
    if frame is not None:
        bpy.context.scene.frame_set(int(frame))
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    eval_arm = rig_obj.evaluated_get(deps)
    pb_eval = eval_arm.pose.bones[hand_bone_name]
    pb_raw = rig_obj.pose.bones[hand_bone_name]

    if desired_world_rot_roblox is None:
        target_world_rot = (rig_obj.matrix_world @ pb_eval.bone.matrix_local).to_3x3()
    elif isinstance(desired_world_rot_roblox, (tuple, list)):
        rx, ry, rz = (float(desired_world_rot_roblox[0]), float(desired_world_rot_roblox[1]), float(desired_world_rot_roblox[2]))
        target_world_rot = euler_xyz_roblox(rx, ry, rz).to_3x3()
    elif isinstance(desired_world_rot_roblox, Euler):
        r_rbx = desired_world_rot_roblox.to_matrix()
        target_world_rot = S_3X3 @ r_rbx @ S_3X3_INV
    elif isinstance(desired_world_rot_roblox, Quaternion):
        r_rbx = desired_world_rot_roblox.to_matrix()
        target_world_rot = S_3X3 @ r_rbx @ S_3X3_INV
    else:
        target_world_rot = S_3X3 @ desired_world_rot_roblox.to_3x3() @ S_3X3_INV

    if pb_eval.parent is not None:
        rest_rel = (pb_eval.parent.bone.matrix_local.inverted() @ pb_eval.bone.matrix_local).to_3x3()
        parent_world = (rig_obj.matrix_world @ pb_eval.parent.matrix).to_3x3()
        local_rot = (parent_world @ rest_rel).inverted() @ target_world_rot
    else:
        local_rot = (rig_obj.matrix_world.to_3x3() @ pb_eval.bone.matrix_local.to_3x3()).inverted() @ target_world_rot

    quat = local_rot.to_quaternion()
    pb_raw.rotation_mode = "QUATERNION"
    pb_raw.rotation_quaternion = quat
    if frame is not None:
        pb_raw.keyframe_insert(data_path="rotation_quaternion", frame=frame)
    return quat


def attach_two_handed_ik(
    rig_obj: bpy.types.Object,
    effector_bone: str = "LeftLowerArm",
    chain_count: int = 2,
    target_parent_bone: str = "RightHand",
    offset_studs: tuple[float, float, float] = (0.0, -0.45, 0.0),
    target_bone_name: str = "IK_OffHandGrip",
) -> str:
    """Create a non-deforming IK bone parented to the main hand and bind an IK constraint."""
    unit_scale = float(rig_obj.get("roblox_unit_scale", 1.0))
    prev_active = bpy.context.view_layer.objects.active
    prev_mode = rig_obj.mode
    bpy.context.view_layer.objects.active = rig_obj
    bpy.ops.object.mode_set(mode="EDIT")

    arm = rig_obj.data
    parent_eb = arm.edit_bones[target_parent_bone]
    parent_mat = parent_eb.matrix.copy()
    local_off = ROBLOX_TO_BLENDER @ Matrix.Translation(Vector(offset_studs) * unit_scale) @ ROBLOX_TO_BLENDER_INV
    target_mat = parent_mat @ local_off

    eb = arm.edit_bones.get(target_bone_name) or arm.edit_bones.new(target_bone_name)
    eb.head = target_mat.translation
    eb.tail = eb.head + (target_mat.to_3x3() @ Vector((0.0, 0.25 * unit_scale, 0.0)))
    eb.align_roll(target_mat.to_3x3() @ Vector((0.0, 0.0, 1.0)))
    eb.parent = parent_eb
    eb.use_deform = False

    bpy.ops.object.mode_set(mode="POSE")
    pb = rig_obj.pose.bones[effector_bone]
    for c in list(pb.constraints):
        if c.type == "IK" and c.subtarget == target_bone_name:
            pb.constraints.remove(c)
    ik = pb.constraints.new("IK")
    ik.target = rig_obj
    ik.subtarget = target_bone_name
    ik.chain_count = chain_count

    bpy.ops.object.mode_set(mode=prev_mode if prev_mode in {"OBJECT", "POSE", "EDIT"} else "OBJECT")
    bpy.context.view_layer.objects.active = prev_active
    return target_bone_name


def retarget_armature_action(
    source_arm: bpy.types.Object,
    target_arm: bpy.types.Object,
    start_frame: int,
    end_frame: int,
    action_name: str = "RetargetedClip",
    bone_map: dict[str, str] | None = None,
    copy_hip_translation: bool = True,
) -> dict[str, str]:
    """Retarget animation from Mixamo/CMU/Tripo/BVH source armature onto a Roblox armature."""
    import re

    if bone_map is None:
        src_bones = [b.name for b in source_arm.data.bones]
        bone_map = {}
        used: set[str] = set()
        for rbx_name, patterns in DEFAULT_RETARGET_PATTERNS.items():
            if rbx_name not in target_arm.data.bones:
                continue
            for pat in patterns:
                rx = re.compile(pat, re.IGNORECASE)
                hit = next((sb for sb in src_bones if sb not in used and rx.search(sb)), None)
                if hit:
                    bone_map[rbx_name] = hit
                    used.add(hit)
                    break

    ensure_action(target_arm, action_name)
    src_rest = {n: (source_arm.matrix_world @ source_arm.data.bones[n].matrix_local).to_3x3() for n in bone_map.values()}
    tgt_rest = {n: (target_arm.matrix_world @ target_arm.data.bones[n].matrix_local).to_3x3() for n in bone_map.keys()}

    src_hip_name = bone_map.get("LowerTorso")
    src_hip_rest_z = (source_arm.matrix_world @ source_arm.data.bones[src_hip_name].matrix_local).translation.z if src_hip_name else 0.0
    tgt_hip_rest_z = (target_arm.matrix_world @ target_arm.data.bones["LowerTorso"].matrix_local).translation.z if "LowerTorso" in bone_map else 0.0
    height_ratio = (tgt_hip_rest_z / src_hip_rest_z) if (src_hip_rest_z and abs(src_hip_rest_z) > 1e-4) else 1.0

    scene = bpy.context.scene
    for frame in range(start_frame, end_frame + 1):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        src_eval = source_arm.evaluated_get(deps)

        # Solve parent-to-child in topological order so world-space matching propagates cleanly
        for pb_tgt in target_arm.pose.bones:
            if pb_tgt.name not in bone_map:
                continue
            src_name = bone_map[pb_tgt.name]
            pb_src = src_eval.pose.bones[src_name]
            src_pose_w = (src_eval.matrix_world @ pb_src.matrix).to_3x3()
            delta_w = src_pose_w @ src_rest[src_name].inverted()
            desired_w = delta_w @ tgt_rest[pb_tgt.name]

            if pb_tgt.parent:
                bpy.context.view_layer.update()
                deps_t = bpy.context.evaluated_depsgraph_get()
                tgt_eval = target_arm.evaluated_get(deps_t)
                parent_eval = tgt_eval.pose.bones[pb_tgt.parent.name]
                rest_rel = (pb_tgt.parent.bone.matrix_local.inverted() @ pb_tgt.bone.matrix_local).to_3x3()
                parent_w = (tgt_eval.matrix_world @ parent_eval.matrix).to_3x3()
                local_r = (parent_w @ rest_rel).inverted() @ desired_w
            else:
                local_r = (target_arm.matrix_world.to_3x3() @ pb_tgt.bone.matrix_local.to_3x3()).inverted() @ desired_w

            pb_tgt.rotation_mode = "QUATERNION"
            pb_tgt.rotation_quaternion = local_r.to_quaternion()
            pb_tgt.keyframe_insert(data_path="rotation_quaternion", frame=frame)

            if copy_hip_translation and pb_tgt.name == "LowerTorso":
                src_hip_pos = (src_eval.matrix_world @ pb_src.matrix).translation
                src_hip_rest_pos = (source_arm.matrix_world @ source_arm.data.bones[src_name].matrix_local).translation
                delta_hip = (src_hip_pos - src_hip_rest_pos) * height_ratio
                # Project delta into LowerTorso local rest space
                parent_w = (target_arm.matrix_world @ pb_tgt.bone.matrix_local).to_3x3()
                pb_tgt.location = parent_w.inverted() @ delta_hip
                pb_tgt.keyframe_insert(data_path="location", frame=frame)

    return bone_map

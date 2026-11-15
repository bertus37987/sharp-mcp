"""Bake evaluated Blender 5.2+ animations into Roblox clips (.json, .rbxmx, Luau KeyframeSequence, Luau CurveAnimation).

Reads the evaluated depsgraph per sampled frame so keyframes, IK constraints,
world-locked shields, 2-handed grips, and NLA strips all bake accurately into
Roblox joint transforms with zero Euler-order ambiguity.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

try:
    import bpy
    from mathutils import Matrix

    try:
        from blender_anim_helpers import ROBLOX_TO_BLENDER, ROBLOX_TO_BLENDER_INV, matrix_to_roblox_cf
    except ImportError:
        import sys
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        from blender_anim_helpers import ROBLOX_TO_BLENDER, ROBLOX_TO_BLENDER_INV, matrix_to_roblox_cf
except ImportError:
    bpy = None  # type: ignore[assignment]
    Matrix = None  # type: ignore[assignment]

# Verified Enum.AnimationPriority XML Token values from create.roblox.com/docs
PRIORITY_XML_TOKEN: dict[str, int] = {
    "Idle": 0,
    "Movement": 1,
    "Action": 2,
    "Action2": 3,
    "Action3": 4,
    "Action4": 5,
    "Core": 1000,
}

PRIORITY_LUAU_ENUM: dict[str, str] = {
    name: f"Enum.AnimationPriority.{name}" for name in PRIORITY_XML_TOKEN
}

EASING_XML_TOKEN: dict[str, int] = {
    "Linear": 0,
    "Constant": 1,
    "Elastic": 2,
    "Cubic": 3,
    "Bounce": 4,
    "CubicV2": 5,
}

DIRECTION_XML_TOKEN: dict[str, int] = {
    "In": 0,
    "Out": 1,
    "InOut": 2,
}


def _extract_rig_hierarchy(rig_obj: bpy.types.Object) -> tuple[str, dict[str, str | None], list[str]]:
    """Read Roblox joint hierarchy from rig custom property or infer from deform bones."""
    raw = rig_obj.get("roblox_rig_meta")
    if isinstance(raw, str):
        meta = json.loads(raw)
        bones = [b for b in meta["bones"] if b in rig_obj.data.bones]
        parents = {b: meta["parents"].get(b) for b in bones}
        return meta.get("rootName", bones[0]), parents, bones

    deform_bones = [b for b in rig_obj.data.bones if b.use_deform]
    if not deform_bones:
        deform_bones = list(rig_obj.data.bones)
    bones = [b.name for b in deform_bones]
    parents = {
        b.name: (b.parent.name if b.parent and b.parent.name in bones else None)
        for b in deform_bones
    }
    root = next((b for b, p in parents.items() if p is None), bones[0])
    return root, parents, bones


def _collect_markers(rig_obj: bpy.types.Object, action_name: str, start_frame: int, end_frame: int, fps: float) -> list[dict[str, Any]]:
    """Collect markers registered via add_animation_marker or Blender pose_markers."""
    out: list[dict[str, Any]] = []
    raw = rig_obj.get("roblox_anim_markers")
    if isinstance(raw, str):
        store = json.loads(raw)
        for m in store.get(action_name, []):
            f = int(m["frame"])
            if start_frame <= f <= end_frame:
                out.append({
                    "t": round((f - start_frame) / fps, 6),
                    "name": str(m["name"]),
                    "value": str(m.get("value", "")),
                })
    act = rig_obj.animation_data.action if rig_obj.animation_data else None
    if act and hasattr(act, "pose_markers"):
        seen = {(e["t"], e["name"]) for e in out}
        for pm in act.pose_markers:
            if start_frame <= pm.frame <= end_frame:
                t = round((pm.frame - start_frame) / fps, 6)
                if (t, pm.name) not in seen:
                    out.append({"t": t, "name": pm.name, "value": ""})
    return sorted(out, key=lambda e: e["t"])


def bake_clip(
    rig_obj: bpy.types.Object,
    clip_name: str,
    start_frame: int,
    end_frame: int,
    fps: float | None = None,
    step: int = 1,
    loop: bool = False,
    priority: str = "Action",
    bones_mask: set[str] | None = None,
    bake_root_motion: bool = False,
) -> dict[str, Any]:
    """Sample evaluated Blender rig across frames into Roblox joint transforms."""
    scene = bpy.context.scene
    fps = float(fps or (scene.render.fps / scene.render.fps_base))
    unit_scale = float(rig_obj.get("roblox_unit_scale", 1.0))
    root_name, parents, ordered_bones = _extract_rig_hierarchy(rig_obj)

    if bones_mask is not None:
        # Include all structural ancestors up to root_name so the Pose/Folder tree remains connected,
        # while only emitting non-zero-weight poses for bones inside bones_mask.
        tree_set: set[str] = {root_name}
        for b in bones_mask:
            cur: str | None = b
            while cur and cur in parents and cur not in tree_set:
                tree_set.add(cur)
                cur = parents.get(cur)
        tree_bones = [b for b in ordered_bones if b in tree_set]
        pose_bones = [b for b in tree_bones if b in bones_mask]
    else:
        tree_bones = ordered_bones
        pose_bones = ordered_bones

    prev_frame = scene.frame_current
    frames_out: list[dict[str, Any]] = []

    sample_frames = list(range(start_frame, end_frame + 1, max(1, step)))
    if sample_frames[-1] != end_frame:
        sample_frames.append(end_frame)

    for frame in sample_frames:
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        eval_arm = rig_obj.evaluated_get(deps)

        poses: dict[str, dict[str, Any]] = {}
        for bname in pose_bones:
            pb = eval_arm.pose.bones.get(bname)
            if pb is None:
                continue

            if bname == root_name and not bake_root_motion:
                poses[bname] = {"pos": [0.0, 0.0, 0.0], "rot": [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]}
                continue

            if pb.parent is not None:
                rest_rel = pb.parent.bone.matrix_local.inverted() @ pb.bone.matrix_local
                t_blender = (pb.parent.matrix @ rest_rel).inverted() @ pb.matrix
            else:
                t_blender = pb.bone.matrix_local.inverted() @ pb.matrix

            pos, rot = matrix_to_roblox_cf(t_blender, unit_scale=unit_scale)
            poses[bname] = {"pos": pos, "rot": rot}

        frames_out.append({
            "t": round((frame - start_frame) / fps, 6),
            "poses": poses,
        })

    scene.frame_set(prev_frame)
    act_name = rig_obj.animation_data.action.name if (rig_obj.animation_data and rig_obj.animation_data.action) else clip_name
    markers = _collect_markers(rig_obj, act_name, start_frame, end_frame, fps)

    return {
        "name": clip_name,
        "loop": bool(loop),
        "priority": priority if priority in PRIORITY_XML_TOKEN else "Action",
        "fps": fps,
        "rootName": root_name,
        "parents": {b: parents.get(b) for b in tree_bones},
        "frames": frames_out,
        "markers": markers,
    }


def _fmt_num(val: float) -> str:
    if abs(val) < 1e-6:
        return "0"
    s = f"{val:.6f}".rstrip("0").rstrip(".")
    return "0" if s == "-0" else s


def clip_to_rbxmx(clip: dict[str, Any], easing_style: str = "CubicV2", easing_dir: str = "InOut") -> str:
    """Serialize a baked clip dict into a Roblox .rbxmx XML KeyframeSequence file."""
    ref = 0
    def next_ref() -> str:
        nonlocal ref
        ref += 1
        return f"RBX{ref}"

    parents: dict[str, str | None] = clip["parents"]
    root_name: str = clip["rootName"]
    children_map: dict[str, list[str]] = {b: [] for b in parents}
    for b, p in parents.items():
        if p and p in children_map:
            children_map[p].append(b)

    e_style = EASING_XML_TOKEN.get(easing_style, 5)
    e_dir = DIRECTION_XML_TOKEN.get(easing_dir, 2)
    prio_tok = PRIORITY_XML_TOKEN.get(clip["priority"], 2)

    markers_by_time: dict[float, list[dict[str, Any]]] = {}
    for m in clip.get("markers", []):
        # Snap marker to nearest frame timestamp in clip
        nearest = min(clip["frames"], key=lambda fr: abs(fr["t"] - m["t"]))["t"]
        markers_by_time.setdefault(nearest, []).append(m)

    def pose_xml(bone_name: str, poses: dict[str, dict[str, Any]]) -> str:
        data = poses.get(bone_name)
        pos = data["pos"] if data else [0.0, 0.0, 0.0]
        r = data["rot"] if data else [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
        weight = 1.0 if data else 0.0
        parts = [
            f'<Item class="Pose" referent="{next_ref()}"><Properties>',
            f'<string name="Name">{xml_escape(bone_name)}</string>',
            '<CoordinateFrame name="CFrame">',
            f'<X>{_fmt_num(pos[0])}</X><Y>{_fmt_num(pos[1])}</Y><Z>{_fmt_num(pos[2])}</Z>',
            f'<R00>{_fmt_num(r[0])}</R00><R01>{_fmt_num(r[1])}</R01><R02>{_fmt_num(r[2])}</R02>',
            f'<R10>{_fmt_num(r[3])}</R10><R11>{_fmt_num(r[4])}</R11><R12>{_fmt_num(r[5])}</R12>',
            f'<R20>{_fmt_num(r[6])}</R20><R21>{_fmt_num(r[7])}</R21><R22>{_fmt_num(r[8])}</R22>',
            '</CoordinateFrame>',
            f'<float name="Weight">{_fmt_num(weight)}</float>',
            f'<token name="EasingStyle">{e_style}</token>',
            f'<token name="EasingDirection">{e_dir}</token>',
            '</Properties>',
        ]
        for ch in children_map.get(bone_name, []):
            parts.append(pose_xml(ch, poses))
        parts.append('</Item>')
        return "".join(parts)

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">',
        f'  <Item class="KeyframeSequence" referent="{next_ref()}"><Properties>',
        f'    <string name="Name">{xml_escape(clip["name"])}</string>',
        f'    <bool name="Loop">{"true" if clip["loop"] else "false"}</bool>',
        f'    <token name="Priority">{prio_tok}</token>',
        '  </Properties>',
    ]

    for idx, fr in enumerate(clip["frames"]):
        lines.append(f'    <Item class="Keyframe" referent="{next_ref()}"><Properties>')
        lines.append(f'      <string name="Name">KF_{idx}</string>')
        lines.append(f'      <float name="Time">{_fmt_num(fr["t"])}</float>')
        lines.append('    </Properties>')
        for m in markers_by_time.get(fr["t"], []):
            lines.append(f'      <Item class="KeyframeMarker" referent="{next_ref()}"><Properties>')
            lines.append(f'        <string name="Name">{xml_escape(m["name"])}</string>')
            lines.append(f'        <string name="Value">{xml_escape(m.get("value", ""))}</string>')
            lines.append('      </Properties></Item>')
        lines.append('      ' + pose_xml(root_name, fr["poses"]))
        lines.append('    </Item>')

    lines.append('  </Item>')
    lines.append('</roblox>')
    return "\n".join(lines)


def _cframe_luau(pos: list[float], rot: list[float]) -> str:
    return (
        "CFrame.new("
        f"{_fmt_num(pos[0])},{_fmt_num(pos[1])},{_fmt_num(pos[2])},"
        f"{_fmt_num(rot[0])},{_fmt_num(rot[1])},{_fmt_num(rot[2])},"
        f"{_fmt_num(rot[3])},{_fmt_num(rot[4])},{_fmt_num(rot[5])},"
        f"{_fmt_num(rot[6])},{_fmt_num(rot[7])},{_fmt_num(rot[8])})"
    )


def clip_to_luau(
    clip: dict[str, Any],
    mode: str = "KeyframeSequence",
    target_folder_name: str = "Animations",
    register_preview: bool = True,
) -> str:
    """Generate a standalone Luau script creating either a KeyframeSequence or CurveAnimation in ReplicatedStorage."""
    parents: dict[str, str | None] = clip["parents"]
    root_name: str = clip["rootName"]
    prio_enum = PRIORITY_LUAU_ENUM.get(clip["priority"], "Enum.AnimationPriority.Action")
    loop_str = "true" if clip["loop"] else "false"

    parent_entries = ", ".join(
        f'["{b}"] = "{p}"' for b, p in parents.items() if p is not None
    )

    if mode == "CurveAnimation":
        # Build nested Folder hierarchy matching the Roblox rig tree (HumanoidRootPart -> LowerTorso -> ...)
        tracks_lua = []
        for b in parents:
            pos_keys = []
            rot_keys = []
            for fr in clip["frames"]:
                pdata = fr["poses"].get(b)
                if not pdata:
                    continue
                t = _fmt_num(fr["t"])
                p = pdata["pos"]
                r = pdata["rot"]
                pos_keys.append(f"{{{t},{_fmt_num(p[0])},{_fmt_num(p[1])},{_fmt_num(p[2])}}}")
                rot_keys.append(f"{{{t},{_cframe_luau([0.0,0.0,0.0], r)}}}")
            if pos_keys or rot_keys:
                tracks_lua.append(
                    f'\t["{b}"] = {{ pos = {{{",".join(pos_keys)}}}, rot = {{{",".join(rot_keys)}}} }}'
                )

        markers_lua = ", ".join(
            f'{{t={_fmt_num(m["t"])}, name={json.dumps(str(m["name"]))}, value={json.dumps(str(m.get("value", "")))}}}'
            for m in clip.get("markers", [])
        )
        reg_block = (
            'local ACP = game:GetService("AnimationClipProvider")\n'
            'local regId = ACP:RegisterAnimationClip(clip)\n'
            'return clip:GetFullName() .. " | RegisteredId=" .. regId\n'
            if register_preview else
            'return clip:GetFullName()\n'
        )
        return (
            "--!strict\n"
            f"-- Generated CurveAnimation builder for {clip['name']}\n"
            'local ReplicatedStorage = game:GetService("ReplicatedStorage")\n'
            f'local folder = ReplicatedStorage:FindFirstChild("{target_folder_name}") or Instance.new("Folder")\n'
            f'folder.Name = "{target_folder_name}"\n'
            "folder.Parent = ReplicatedStorage\n"
            f'local prev = folder:FindFirstChild("{clip["name"]}")\n'
            "if prev then prev:Destroy() end\n\n"
            'local clip = Instance.new("CurveAnimation")\n'
            f'clip.Name = "{clip["name"]}"\n'
            f"clip.Loop = {loop_str}\n"
            f"clip.Priority = {prio_enum}\n\n"
            f'local ROOT_NAME = "{root_name}"\n'
            f"local PARENTS = {{{parent_entries}}}\n"
            "local TRACKS = {\n" + ",\n".join(tracks_lua) + "\n}\n\n"
            "local folders: { [string]: Folder } = {}\n"
            "local function getOrMakeFolder(name: string): Folder\n"
            "\tif not folders[name] then\n"
            '\t\tlocal f = Instance.new("Folder")\n'
            "\t\tf.Name = name\n"
            "\t\tfolders[name] = f\n"
            "\tend\n"
            "\treturn folders[name]\n"
            "end\n\n"
            "getOrMakeFolder(ROOT_NAME)\n"
            "for childName in pairs(PARENTS) do getOrMakeFolder(childName) end\n\n"
            "for boneName, data in pairs(TRACKS) do\n"
            "\tlocal bf = getOrMakeFolder(boneName)\n"
            '\tlocal v3 = Instance.new("Vector3Curve")\n'
            '\tv3.Name = "Position"\n'
            "\tlocal kx, ky, kz = {}, {}, {}\n"
            "\tfor _, pt in ipairs(data.pos) do\n"
            "\t\ttable.insert(kx, FloatCurveKey.new(pt[1], pt[2], Enum.KeyInterpolationMode.Cubic))\n"
            "\t\ttable.insert(ky, FloatCurveKey.new(pt[1], pt[3], Enum.KeyInterpolationMode.Cubic))\n"
            "\t\ttable.insert(kz, FloatCurveKey.new(pt[1], pt[4], Enum.KeyInterpolationMode.Cubic))\n"
            "\tend\n"
            "\tv3:X():SetKeys(kx); v3:Y():SetKeys(ky); v3:Z():SetKeys(kz)\n"
            "\tv3.Parent = bf\n"
            '\tlocal rc = Instance.new("RotationCurve")\n'
            '\trc.Name = "Rotation"\n'
            "\tfor _, rt in ipairs(data.rot) do\n"
            "\t\trc:InsertKey(RotationCurveKey.new(rt[1], rt[2], Enum.KeyInterpolationMode.Cubic))\n"
            "\tend\n"
            "\trc.Parent = bf\n"
            "end\n\n"
            "for childName, parentName in pairs(PARENTS) do\n"
            "\tfolders[childName].Parent = folders[parentName] or clip\n"
            "end\n"
            "folders[ROOT_NAME].Parent = clip\n\n"
            f"local MARKERS = {{{markers_lua}}}\n"
            "local markerCurves: { [string]: MarkerCurve } = {}\n"
            "for _, m in ipairs(MARKERS) do\n"
            "\tlocal mc = markerCurves[m.name]\n"
            "\tif not mc then\n"
            '\t\tmc = Instance.new("MarkerCurve")\n'
            "\t\tmc.Name = m.name\n"
            "\t\tmc.Parent = clip\n"
            "\t\tmarkerCurves[m.name] = mc\n"
            "\tend\n"
            "\tmc:InsertMarkerAtTime(m.t, m.value)\n"
            "end\n"
            "clip.Parent = folder\n"
            + reg_block
        )

    # Default: KeyframeSequence mode
    frame_lines = []
    markers_by_time: dict[float, list[dict[str, Any]]] = {}
    for m in clip.get("markers", []):
        nearest = min(clip["frames"], key=lambda fr: abs(fr["t"] - m["t"]))["t"]
        markers_by_time.setdefault(nearest, []).append(m)

    for fr in clip["frames"]:
        pose_entries = ", ".join(
            f'["{b}"] = {_cframe_luau(pd["pos"], pd["rot"])}'
            for b, pd in fr["poses"].items()
        )
        m_entries = ", ".join(
            f'{{name="{m["name"]}", value="{m.get("value", "")}"}}'
            for m in markers_by_time.get(fr["t"], [])
        )
        frame_lines.append(f'\t{{t={_fmt_num(fr["t"])}, poses={{{pose_entries}}}, markers={{{m_entries}}}}}')

    reg_block = (
        'local ACP = game:GetService("AnimationClipProvider")\n'
        'local regId = ACP:RegisterAnimationClip(seq)\n'
        'return seq:GetFullName() .. " | RegisteredId=" .. regId\n'
        if register_preview else
        'return seq:GetFullName()\n'
    )
    return (
        "--!strict\n"
        f"-- Generated KeyframeSequence builder for {clip['name']}\n"
        'local ReplicatedStorage = game:GetService("ReplicatedStorage")\n'
        f'local folder = ReplicatedStorage:FindFirstChild("{target_folder_name}") or Instance.new("Folder")\n'
        f'folder.Name = "{target_folder_name}"\n'
        "folder.Parent = ReplicatedStorage\n"
        f'local prev = folder:FindFirstChild("{clip["name"]}")\n'
        "if prev then prev:Destroy() end\n\n"
        f'local ROOT_NAME = "{root_name}"\n'
        f"local PARENTS = {{{parent_entries}}}\n"
        "local FRAMES = {\n" + ",\n".join(frame_lines) + "\n}\n\n"
        'local seq = Instance.new("KeyframeSequence")\n'
        f'seq.Name = "{clip["name"]}"\n'
        f"seq.Loop = {loop_str}\n"
        f"seq.Priority = {prio_enum}\n\n"
        "for idx, fr in ipairs(FRAMES) do\n"
        '\tlocal kf = Instance.new("Keyframe")\n'
        '\tkf.Name = "KF_" .. tostring(idx)\n'
        "\tkf.Time = fr.t\n"
        "\tfor _, m in ipairs(fr.markers) do\n"
        '\t\tlocal km = Instance.new("KeyframeMarker")\n'
        "\t\tkm.Name = m.name\n"
        "\t\tkm.Value = m.value\n"
        "\t\tkm.Parent = kf\n"
        "\tend\n"
        "\tlocal poses: { [string]: Pose } = {}\n"
        '\tlocal rootPose = Instance.new("Pose")\n'
        "\trootPose.Name = ROOT_NAME\n"
        "\trootPose.Weight = 1\n"
        "\trootPose.CFrame = fr.poses[ROOT_NAME] or CFrame.identity\n"
        "\tposes[ROOT_NAME] = rootPose\n"
        "\tfor childName in pairs(PARENTS) do\n"
        '\t\tlocal p = Instance.new("Pose")\n'
        "\t\tp.Name = childName\n"
        "\t\tlocal cf = fr.poses[childName]\n"
        "\t\tif cf then\n"
        "\t\t\tp.CFrame = cf\n"
        "\t\t\tp.Weight = 1\n"
        "\t\telse\n"
        "\t\t\tp.Weight = 0\n"
        "\t\tend\n"
        "\t\tp.EasingStyle = Enum.PoseEasingStyle.CubicV2\n"
        "\t\tp.EasingDirection = Enum.PoseEasingDirection.InOut\n"
        "\t\tposes[childName] = p\n"
        "\tend\n"
        "\tfor childName, parentName in pairs(PARENTS) do\n"
        "\t\tif poses[parentName] then poses[childName].Parent = poses[parentName] end\n"
        "\tend\n"
        "\trootPose.Parent = kf\n"
        "\tkf.Parent = seq\n"
        "end\n"
        "seq.Parent = folder\n"
        + reg_block
    )


def save_outputs(
    clip: dict[str, Any],
    out_dir: str | Path,
    emit_json: bool = True,
    emit_rbxmx: bool = True,
    emit_luau_kfs: bool = True,
    emit_luau_curve: bool = True,
) -> dict[str, str]:
    """Write selected baked outputs for a clip to out_dir and return file paths."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    name = clip["name"]
    written: dict[str, str] = {}

    if emit_json:
        p = out_path / f"{name}.json"
        p.write_text(json.dumps(clip, indent=2), encoding="utf-8")
        written["json"] = str(p)
    if emit_rbxmx:
        p = out_path / f"{name}.rbxmx"
        p.write_text(clip_to_rbxmx(clip), encoding="utf-8")
        written["rbxmx"] = str(p)
    if emit_luau_kfs:
        p = out_path / f"{name}_KeyframeSeq.luau"
        p.write_text(clip_to_luau(clip, mode="KeyframeSequence"), encoding="utf-8")
        written["luau_kfs"] = str(p)
    if emit_luau_curve:
        p = out_path / f"{name}_CurveAnim.luau"
        p.write_text(clip_to_luau(clip, mode="CurveAnimation"), encoding="utf-8")
        written["luau_curve"] = str(p)

    return written

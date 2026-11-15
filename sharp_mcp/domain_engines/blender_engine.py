"""Blender-only 3D Modeling, Rigging, Baking & Animation Engine for Sharp MCP."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from sharp_mcp.blender_installer import (
    detect_blender_installation,
    ensure_blender_installed,
    execute_bpy_over_socket_or_headless,
)


def _strip_future_and_main(src: str) -> str:
    """Strip module-top __future__ imports and __main__ blocks for clean single-script bundling."""
    lines: List[str] = []
    skip_main = False
    for line in src.splitlines():
        if re.match(r"^\s*from\s+__future__\s+import\s+", line):
            continue
        if re.match(r'^if\s+__name__\s*==\s*["\']__main__["\']\s*:', line):
            skip_main = True
            continue
        if skip_main:
            if line and not line[0].isspace():
                skip_main = False
            else:
                continue
        lines.append(line)
    return "\n".join(lines)


class BlenderDomainEngine:
    """Compiles and optionally executes Blender 3D modeling, rigging, animation, and PBR baking scripts."""

    def __init__(
        self,
        skills_dir: Path,
        archive_dir: Optional[Path] = None,
        default_artifacts_dir: Optional[Path] = None,
    ) -> None:
        self.skills_dir = Path(skills_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else None
        self.default_artifacts_dir = Path(default_artifacts_dir) if default_artifacts_dir else None
        self.blender_host = os.environ.get("BLENDER_HOST", "localhost").strip() or "localhost"
        self.blender_port = int(os.environ.get("BLENDER_PORT", "9876"))

    def _resolve_skill_dir(self, skill_name: str, archive_rel: Optional[str] = None) -> Path:
        primary = self.skills_dir / skill_name
        if primary.is_dir():
            return primary
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / skill_name
        if bundled.is_dir():
            return bundled
        if self.archive_dir and archive_rel:
            fallback = self.archive_dir / archive_rel
            if fallback.is_dir():
                return fallback
        return primary

    def _read_skill_script(self, skill_name: str, script_name: str, archive_rel: Optional[str] = None) -> str:
        skill_root = self._resolve_skill_dir(skill_name, archive_rel=archive_rel)
        script_path = skill_root / "scripts" / script_name
        if script_path.is_file():
            return script_path.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Blender skill script missing: {script_path}")

    def _resolve_output_dir(self, output_dir: str, project_library: Optional[Any] = None) -> Path:
        if output_dir and output_dir.strip():
            return Path(output_dir).expanduser().resolve()
        if project_library is not None and getattr(project_library, "project_dir", None):
            out = Path(project_library.project_dir) / "artifacts"
            out.mkdir(parents=True, exist_ok=True)
            return out.resolve()
        if self.default_artifacts_dir is not None:
            self.default_artifacts_dir.mkdir(parents=True, exist_ok=True)
            return self.default_artifacts_dir.resolve()
        fallback = Path.cwd() / "artifacts"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback.resolve()

    def check_blender_socket(self, timeout: float = 0.5) -> Dict[str, Any]:
        """Inspect Blender installation, addon readiness, and live TCP socket availability."""
        info = detect_blender_installation()
        return {
            "online": bool(info.get("socket_reachable")),
            "installed": bool(info.get("installed")),
            "executable": info.get("executable"),
            "version": info.get("version"),
            "addon_installed": bool(info.get("addon_installed")),
            "addon_enabled": bool(info.get("addon_enabled")),
            "host": info.get("socket_host", self.blender_host),
            "port": info.get("socket_port", self.blender_port),
        }

    def ensure_setup(
        self,
        *,
        auto_install: bool = True,
        install_addon: bool = True,
        enable_addon: bool = True,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Verify or install Blender and its `mcp-for-blender` addon."""
        return ensure_blender_installed(
            auto_install=auto_install,
            install_addon=install_addon,
            enable_addon=enable_addon,
            dry_run=dry_run,
        )

    def _register_outputs_if_present(
        self,
        *,
        project_library: Optional[Any],
        asset_name: str,
        category: str,
        paths: List[Path],
        description: str,
        tags: List[str],
    ) -> List[str]:
        if project_library is None:
            return []
        registered: List[str] = []
        for idx, file_path in enumerate(paths):
            if file_path.is_file():
                suffix = file_path.suffix.lstrip(".").lower()
                key_name = asset_name if idx == 0 else f"{asset_name}_{suffix}"
                res = project_library.register_asset(
                    name=key_name,
                    category=category,
                    local_path=str(file_path),
                    description=description,
                    tags=tags + [suffix],
                )
                if res.get("ok"):
                    registered.append(res["asset_key"])
        return registered

    def compile_rig_and_animation_bpy(
        self,
        rig_spec_path: Optional[str] = None,
        output_dir: str = "",
        preset_motion: str = "walk_and_slash",
        fps: int = 30,
        export_fbx: bool = True,
        *,
        execute: bool = False,
        auto_install: bool = False,
        execution_mode: str = "auto",
        timeout_sec: float = 90.0,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Compile a runnable Blender Python rigging & animation script, and optionally execute it."""
        build_rig_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_build_roblox_rig.py", "01_roblox_animation/skill")
        )
        anim_helpers_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_anim_helpers.py", "01_roblox_animation/skill")
        )
        bake_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_bake_to_roblox.py", "01_roblox_animation/skill")
        )
        fbx_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_export_roblox_fbx.py", "01_roblox_animation/skill")
        )

        out_dir = self._resolve_output_dir(output_dir, project_library=project_library)
        spec_arg = json.dumps(str(Path(rig_spec_path).resolve())) if rig_spec_path else '"R15"'
        safe_clip_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", preset_motion or "SharpAnim")

        compiled_py = f'''# ==============================================================================
# Sharp MCP Compiled Blender Rig & Animation Pipeline
# Execution target: Blender 5.2+ headless CLI or mcp-for-blender TCP socket
# ==============================================================================
from __future__ import annotations

import json
import math
from pathlib import Path
import bpy

# ---- [1/4] blender_anim_helpers.py ----
{anim_helpers_src}

import sys as _sharp_sys
_sharp_sys.modules.setdefault("blender_anim_helpers", _sharp_sys.modules[__name__])

# ---- [2/4] blender_build_roblox_rig.py ----
{build_rig_src}

_sharp_sys.modules.setdefault("blender_build_roblox_rig", _sharp_sys.modules[__name__])

# ---- [3/4] blender_bake_to_roblox.py ----
{bake_src}

_sharp_sys.modules.setdefault("blender_bake_to_roblox", _sharp_sys.modules[__name__])

# ---- [4/4] blender_export_roblox_fbx.py ----
{fbx_src}

def _run_sharp_rig_pipeline():
    out_dir = Path({json.dumps(out_dir.as_posix())})
    out_dir.mkdir(parents=True, exist_ok=True)
    fps_val = {int(fps)}
    bpy.context.scene.render.fps = fps_val

    rig_obj = build_rig_from_spec({spec_arg}, create_proxies=True)
    action = bpy.data.actions.new(name={json.dumps(safe_clip_name)})
    if not rig_obj.animation_data:
        rig_obj.animation_data_create()
    rig_obj.animation_data.action = action

    end_frame = max(12, fps_val)
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = end_frame
    bpy.context.view_layer.objects.active = rig_obj
    bpy.ops.object.mode_set(mode="POSE")

    preset = {json.dumps(preset_motion)}.lower()
    pb_right = rig_obj.pose.bones.get("RightUpperArm") or rig_obj.pose.bones.get("Right Arm")
    pb_left = rig_obj.pose.bones.get("LeftUpperArm") or rig_obj.pose.bones.get("Left Arm")
    pb_torso = rig_obj.pose.bones.get("UpperTorso") or rig_obj.pose.bones.get("Torso")

    for frame in (1, max(2, end_frame // 2), end_frame):
        bpy.context.scene.frame_set(frame)
        phase = (frame - 1) / max(1, end_frame - 1)
        if pb_right:
            pb_right.rotation_mode = "XYZ"
            angle = -1.2 * math.sin(phase * math.pi) if "slash" in preset else 0.45 * math.sin(phase * math.pi * 2)
            pb_right.rotation_euler = (angle, 0.0, 0.15 * phase)
            pb_right.keyframe_insert(data_path="rotation_euler", frame=frame)
        if pb_left:
            pb_left.rotation_mode = "XYZ"
            pb_left.rotation_euler = (-0.35 * math.sin(phase * math.pi * 2), 0.0, 0.0)
            pb_left.keyframe_insert(data_path="rotation_euler", frame=frame)
        if pb_torso:
            pb_torso.rotation_mode = "XYZ"
            pb_torso.rotation_euler = (0.08 * math.sin(phase * math.pi), 0.12 * math.sin(phase * math.pi * 2), 0.0)
            pb_torso.keyframe_insert(data_path="rotation_euler", frame=frame)

    bpy.ops.object.mode_set(mode="OBJECT")
    clip = bake_clip(
        rig_obj,
        clip_name={json.dumps(safe_clip_name)},
        start_frame=1,
        end_frame=end_frame,
        fps=float(fps_val),
        loop=("walk" in preset or "idle" in preset),
    )
    written = save_outputs(clip, out_dir, emit_json=True, emit_rbxmx=True, emit_luau_kfs=True, emit_luau_curve=True)
    if {repr(bool(export_fbx))}:
        fbx_out = out_dir / f"{safe_clip_name}.fbx"
        export_roblox_fbx(fbx_out, rig_obj, mode="animation")
        written["fbx"] = str(fbx_out)
    print("SHARP_BLENDER_RIG_OK", json.dumps({{"out_dir": str(out_dir), "outputs": written}}))
    return written

_run_sharp_rig_pipeline()
'''

        result: Dict[str, Any] = {
            "ok": True,
            "pipeline": "blender_rig_and_animation",
            "preset_motion": preset_motion,
            "fps": fps,
            "export_fbx": export_fbx,
            "output_dir": str(out_dir),
            "compiled_bpy_code": compiled_py,
            "executed": False,
        }

        if execute:
            exec_res = execute_bpy_over_socket_or_headless(
                code=compiled_py,
                host=self.blender_host,
                port=self.blender_port,
                mode=execution_mode,
                auto_install=auto_install,
                timeout_sec=timeout_sec,
            )
            result["execution"] = exec_res
            result["executed"] = bool(exec_res.get("ok"))
            result["ok"] = bool(exec_res.get("ok"))
            expected_files = [
                out_dir / f"{safe_clip_name}.fbx",
                out_dir / f"{safe_clip_name}.rbxmx",
                out_dir / f"{safe_clip_name}.json",
            ]
            if result["executed"]:
                result["registered_asset_keys"] = self._register_outputs_if_present(
                    project_library=project_library,
                    asset_name=safe_clip_name,
                    category="animation",
                    paths=expected_files,
                    description=f"Blender compiled rig & animation clip ({preset_motion}, {fps} fps)",
                    tags=["blender", "animation", preset_motion],
                )
        return result

    def compile_asset_and_bake_bpy(
        self,
        asset_kind: str = "modular_roman_arch",
        asset_name: str = "Modular_Roman_Arch_4m",
        output_dir: str = "",
        bake_resolution: int = 1024,
        run_cycles_bake: bool = False,
        *,
        execute: bool = False,
        auto_install: bool = False,
        execution_mode: str = "auto",
        timeout_sec: float = 120.0,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Compile a runnable Blender 3D asset modeling/export/bake script, and optionally execute it."""
        mod_wall_src = _strip_future_and_main(
            self._read_skill_script(
                "blender-modular-architecture",
                "generate_modular_wall.py",
                "05_blender_skills/blender_modular_architecture/skill",
            )
        )
        bake_src = _strip_future_and_main(
            self._read_skill_script(
                "blender-bake-and-materials",
                "bake_high_to_low.py",
                "05_blender_skills/blender_bake_and_materials/skill",
            )
        )

        out_dir = self._resolve_output_dir(output_dir, project_library=project_library)
        safe_asset = re.sub(r"[^a-zA-Z0-9_\-]", "_", asset_name or "SharpAsset")

        compiled_py = f'''# ==============================================================================
# Sharp MCP Compiled Blender 3D Asset & PBR Bake Pipeline
# Target asset: {safe_asset} ({asset_kind}) | Out: {out_dir.as_posix()}
# ==============================================================================
from __future__ import annotations

import json
import os
from pathlib import Path
import bmesh
import bpy

# ---- [1/2] generate_modular_wall.py ----
{mod_wall_src}

# ---- [2/2] bake_high_to_low.py ----
{bake_src}

def _build_stylized_prop(name: str):
    existing = bpy.data.objects.get(name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    mesh = bpy.data.meshes.new(name + "_Mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0)
    bmesh.ops.scale(bm, vec=(1.0, 1.0, 1.35), verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    return obj

def _run_sharp_asset_pipeline():
    out_dir = Path({json.dumps(out_dir.as_posix())})
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = {json.dumps(asset_kind)}
    name = {json.dumps(safe_asset)}

    bpy.ops.object.select_all(action="DESELECT")
    if "arch" in kind.lower() or "wall" in kind.lower() or "modular" in kind.lower():
        obj = create_arch_wall(name=name)
    else:
        obj = _build_stylized_prop(name)

    mat = bpy.data.materials.new(name=f"M_{{name}}_Base")
    mat.use_nodes = True
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    glb_path = out_dir / f"{{name}}.glb"
    bpy.ops.export_scene.gltf(
        filepath=str(glb_path),
        use_selection=True,
        export_format="GLB",
        export_yup=True,
    )

    baked = None
    if {repr(bool(run_cycles_bake))}:
        high_copy = obj.copy()
        high_copy.data = obj.data.copy()
        high_copy.name = name + "_High"
        bpy.context.collection.objects.link(high_copy)
        baked = bake_high_to_low(
            high_obj=high_copy,
            low_obj=obj,
            output_dir=str(out_dir),
            base_name=name,
            resolution={int(bake_resolution)},
        )

    summary = {{"glb": str(glb_path), "baked": bool(baked), "asset_name": name, "asset_kind": kind}}
    print("SHARP_BLENDER_ASSET_OK", json.dumps(summary))
    return summary

_run_sharp_asset_pipeline()
'''

        result: Dict[str, Any] = {
            "ok": True,
            "pipeline": "blender_asset_and_bake",
            "asset_kind": asset_kind,
            "asset_name": safe_asset,
            "output_dir": str(out_dir),
            "bake_resolution": bake_resolution,
            "run_cycles_bake": run_cycles_bake,
            "compiled_bpy_code": compiled_py,
            "executed": False,
        }

        if execute:
            exec_res = execute_bpy_over_socket_or_headless(
                code=compiled_py,
                host=self.blender_host,
                port=self.blender_port,
                mode=execution_mode,
                auto_install=auto_install,
                timeout_sec=timeout_sec,
            )
            result["execution"] = exec_res
            result["executed"] = bool(exec_res.get("ok"))
            result["ok"] = bool(exec_res.get("ok"))
            glb_file = out_dir / f"{safe_asset}.glb"
            fbx_file = out_dir / f"{safe_asset}.fbx"
            if result["executed"]:
                result["registered_asset_keys"] = self._register_outputs_if_present(
                    project_library=project_library,
                    asset_name=safe_asset,
                    category="mesh",
                    paths=[glb_file, fbx_file],
                    description=f"Blender generated 3D asset ({asset_kind})",
                    tags=["blender", "3d", asset_kind],
                )
        return result

    def compile_asset_attach_bpy(
        self,
        prop_kind: str = "sword",
        prop_name: str = "SharpProp",
        attachment_mode: str = "auto",
        slot: Optional[str] = None,
        limb_part: Optional[str] = None,
        limb_attachment: Optional[str] = None,
        item_attachment: Optional[str] = None,
        source_mesh_path: Optional[str] = None,
        output_dir: str = "",
        rig_spec_path: Optional[str] = None,
        target_rig_height_studs: float = 5.0,
        export_fbx: bool = True,
        export_glb: bool = True,
        *,
        execute: bool = False,
        auto_install: bool = False,
        execution_mode: str = "auto",
        timeout_sec: float = 90.0,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Compile a Blender 5.2-compatible prop/armor rigging, socket empty, and sidecar export script.

        Builds or imports a prop/armor mesh, scales it to R15 proportions, adds official Roblox
        socket Empty objects, binds either via ARMATURE_AUTO (with vertex-group fallback + 4-bone
        clamping for skinned armor) or bone parenting (for rigid props), and exports FBX/GLB plus
        a `<prop_name>_attachments.json` sidecar consumable by `AttachmentEngine`.
        """
        anim_helpers_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_anim_helpers.py", "01_roblox_animation/skill")
        )
        build_rig_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_build_roblox_rig.py", "01_roblox_animation/skill")
        )

        out_dir = self._resolve_output_dir(output_dir, project_library=project_library)
        safe_prop = re.sub(r"[^a-zA-Z0-9_\-]", "_", prop_name or "SharpProp")
        kind_key = (prop_kind or "sword").strip().lower()

        # Align defaults with R15 official attachment catalog & AttachmentEngine SOCKET_PRESETS.
        prop_presets: Dict[str, Dict[str, Any]] = {
            "sword": {
                "default_mode": "rigid",
                "default_slot": "right_hand",
                "limb": "RightHand",
                "limb_att": "RightGripAttachment",
                "item_att": "GripAttachment",
                "target_size_studs": (0.35, 3.6, 0.9),
                "secondary_sockets": [
                    ("ForegripAttachment", [0.0, 0.55, 0.0], [0.0, 0.0, 0.0], "LeftHand", "LeftGripAttachment", "foregrip"),
                    ("HolsterBackAttachment", [0.0, 0.25, 0.0], [0.0, 0.0, -32.0], "UpperTorso", "BodyBackAttachment", "holster"),
                ],
            },
            "bow": {
                "default_mode": "rigid",
                "default_slot": "left_hand",
                "limb": "LeftHand",
                "limb_att": "LeftGripAttachment",
                "item_att": "BowGripAttachment",
                "target_size_studs": (0.25, 4.0, 0.95),
                "secondary_sockets": [
                    ("StringNockAttachment", [0.0, 0.0, 0.35], [0.0, 0.0, 0.0], "RightHand", "RightGripAttachment", "foregrip"),
                    ("HolsterBackAttachment", [0.0, 0.0, 0.0], [0.0, 0.0, 35.0], "UpperTorso", "BodyBackAttachment", "holster"),
                ],
            },
            "shield": {
                "default_mode": "rigid",
                "default_slot": "left_hand",
                "limb": "LeftHand",
                "limb_att": "LeftGripAttachment",
                "item_att": "ShieldGripAttachment",
                "target_size_studs": (2.2, 2.6, 0.28),
                "secondary_sockets": [
                    ("ShieldBackAttachment", [0.0, 0.0, 0.14], [0.0, 180.0, 0.0], "UpperTorso", "BodyBackAttachment", "holster"),
                ],
            },
            "staff": {
                "default_mode": "rigid",
                "default_slot": "right_hand",
                "limb": "RightHand",
                "limb_att": "RightGripAttachment",
                "item_att": "StaffGripAttachment",
                "target_size_studs": (0.38, 5.2, 0.38),
                "secondary_sockets": [
                    ("ForegripAttachment", [0.0, 0.9, 0.0], [0.0, 0.0, 0.0], "LeftHand", "LeftGripAttachment", "foregrip"),
                    ("HolsterBackAttachment", [0.0, 0.15, 0.0], [0.0, 0.0, -28.0], "UpperTorso", "BodyBackAttachment", "holster"),
                ],
            },
            "gun": {
                "default_mode": "rigid",
                "default_slot": "right_hand",
                "limb": "RightHand",
                "limb_att": "RightGripAttachment",
                "item_att": "GripAttachment",
                "target_size_studs": (0.28, 0.75, 2.3),
                "secondary_sockets": [
                    ("ForegripAttachment", [0.0, -0.05, -0.85], [0.0, 0.0, 0.0], "LeftHand", "LeftGripAttachment", "foregrip"),
                    ("MuzzleAttachment", [0.0, 0.12, -1.35], [0.0, 0.0, 0.0], None, None, "fx"),
                ],
            },
            "backpack": {
                "default_mode": "rigid",
                "default_slot": "back",
                "limb": "UpperTorso",
                "limb_att": "BodyBackAttachment",
                "item_att": "BodyBackAttachment",
                "target_size_studs": (1.55, 1.85, 0.85),
                "secondary_sockets": [],
            },
            "cape": {
                "default_mode": "rigid",
                "default_slot": "back",
                "limb": "UpperTorso",
                "limb_att": "BodyBackAttachment",
                "item_att": "BodyBackAttachment",
                "target_size_studs": (1.85, 2.75, 0.18),
                "secondary_sockets": [],
            },
            "wings": {
                "default_mode": "rigid",
                "default_slot": "back",
                "limb": "UpperTorso",
                "limb_att": "BodyBackAttachment",
                "item_att": "BodyBackAttachment",
                "target_size_studs": (4.4, 2.4, 0.35),
                "secondary_sockets": [],
            },
            "pet": {
                "default_mode": "rigid",
                "default_slot": "right_collar",
                "limb": "UpperTorso",
                "limb_att": "RightCollarAttachment",
                "item_att": "PetMountAttachment",
                "target_size_studs": (0.75, 0.7, 0.85),
                "secondary_sockets": [],
            },
            "helmet": {
                "default_mode": "rigid",
                "default_slot": "helmet",
                "limb": "Head",
                "limb_att": "HatAttachment",
                "item_att": "HatAttachment",
                "target_size_studs": (1.28, 1.18, 1.28),
                "secondary_sockets": [],
            },
            "chest": {
                "default_mode": "skinned_armor",
                "default_slot": "chest",
                "limb": "UpperTorso",
                "limb_att": "BodyFrontAttachment",
                "item_att": "BodyFrontAttachment",
                "target_size_studs": (2.15, 1.55, 1.22),
                "secondary_sockets": [
                    ("BodyBackAttachment", [0.0, 0.0, 0.58], [0.0, 0.0, 0.0], "UpperTorso", "BodyBackAttachment", "secondary"),
                ],
            },
            "pauldron": {
                "default_mode": "skinned_armor",
                "default_slot": "right_pauldron",
                "limb": "RightUpperArm",
                "limb_att": "RightShoulderAttachment",
                "item_att": "RightShoulderAttachment",
                "target_size_studs": (1.05, 0.95, 1.05),
                "secondary_sockets": [],
            },
            "left_pauldron": {
                "default_mode": "skinned_armor",
                "default_slot": "left_pauldron",
                "limb": "LeftUpperArm",
                "limb_att": "LeftShoulderAttachment",
                "item_att": "LeftShoulderAttachment",
                "target_size_studs": (1.05, 0.95, 1.05),
                "secondary_sockets": [],
            },
            "right_pauldron": {
                "default_mode": "skinned_armor",
                "default_slot": "right_pauldron",
                "limb": "RightUpperArm",
                "limb_att": "RightShoulderAttachment",
                "item_att": "RightShoulderAttachment",
                "target_size_studs": (1.05, 0.95, 1.05),
                "secondary_sockets": [],
            },
            "greave": {
                "default_mode": "skinned_armor",
                "default_slot": "right_greave",
                "limb": "RightLowerLeg",
                "limb_att": "RightKneeRigAttachment",
                "item_att": "RightKneeRigAttachment",
                "target_size_studs": (0.98, 1.25, 0.98),
                "secondary_sockets": [],
            },
            "left_greave": {
                "default_mode": "skinned_armor",
                "default_slot": "left_greave",
                "limb": "LeftLowerLeg",
                "limb_att": "LeftKneeRigAttachment",
                "item_att": "LeftKneeRigAttachment",
                "target_size_studs": (0.98, 1.25, 0.98),
                "secondary_sockets": [],
            },
            "right_greave": {
                "default_mode": "skinned_armor",
                "default_slot": "right_greave",
                "limb": "RightLowerLeg",
                "limb_att": "RightKneeRigAttachment",
                "item_att": "RightKneeRigAttachment",
                "target_size_studs": (0.98, 1.25, 0.98),
                "secondary_sockets": [],
            },
            "boot": {
                "default_mode": "skinned_armor",
                "default_slot": "right_boot",
                "limb": "RightFoot",
                "limb_att": "RightFootAttachment",
                "item_att": "RightFootAttachment",
                "target_size_studs": (1.02, 0.55, 1.15),
                "secondary_sockets": [],
            },
            "gauntlet": {
                "default_mode": "skinned_armor",
                "default_slot": "right_gauntlet",
                "limb": "RightLowerArm",
                "limb_att": "RightWristRigAttachment",
                "item_att": "RightWristRigAttachment",
                "target_size_studs": (0.85, 0.95, 0.85),
                "secondary_sockets": [],
            },
        }
        preset = prop_presets.get(kind_key, prop_presets["sword"])

        mode_norm = (attachment_mode or "auto").strip().lower()
        rigid_attach_aliases = {
            "rigid": "accessory_rigid",
            "bone": "accessory_rigid",
            "accessory": "accessory_rigid",
            "accessory_rigid": "accessory_rigid",
            "tool_grip": "tool_grip",
            "motor6d_weapon": "motor6d_weapon",
            "holster_back": "holster_back",
            "holster_hip": "holster_hip",
            "shield_back": "shield_back",
            "two_hand_ik": "two_hand_ik",
            "two_handed_ik": "two_hand_ik",
        }
        skinned_aliases = {"skinned", "armor", "skinned_armor", "armature"}
        if mode_norm == "auto":
            effective_mode = str(preset["default_mode"])
            recommended_attach_mode = "armor_set" if effective_mode == "skinned_armor" else (
                "motor6d_weapon" if kind_key in ("sword", "bow", "shield", "staff", "gun") else "accessory_rigid"
            )
        elif mode_norm == "armor_set":
            effective_mode = str(preset["default_mode"])
            recommended_attach_mode = "armor_set"
        elif mode_norm in skinned_aliases:
            effective_mode = "skinned_armor"
            recommended_attach_mode = "armor_set"
        elif mode_norm in rigid_attach_aliases:
            effective_mode = "rigid"
            recommended_attach_mode = rigid_attach_aliases[mode_norm]
        else:
            raise ValueError(
                f"Invalid attachment_mode '{attachment_mode}'. Expected 'auto', 'rigid', 'skinned_armor', or AttachmentEngine mode."
            )

        resolved_slot = slot or str(preset["default_slot"])
        resolved_limb = limb_part or str(preset["limb"])
        resolved_limb_att = limb_attachment or str(preset["limb_att"])
        resolved_item_att = item_attachment or str(preset["item_att"])
        spec_arg = json.dumps(str(Path(rig_spec_path).resolve())) if rig_spec_path else '"R15"'
        sidecar_file = out_dir / f"{safe_prop}_attachments.json"
        fbx_file = out_dir / f"{safe_prop}.fbx"
        glb_file = out_dir / f"{safe_prop}.glb"
        src_mesh_arg = json.dumps(str(Path(source_mesh_path).resolve())) if source_mesh_path else "None"

        compiled_py = f'''# ==============================================================================
# Sharp MCP Compiled Blender 5.2+ Prop/Armor Socket & Export Pipeline
# Prop: {safe_prop} ({kind_key}) | Mode: {effective_mode} | Slot: {resolved_slot}
# Blender 5.2 API notes:
#   - Never set deprecated mesh.use_auto_smooth (removed in Blender 4.1+/5.2)
#   - Look up Principled BSDF by node.type == "BSDF_PRINCIPLED"
#   - Use bpy.ops.wm.obj_import when present with fallback to import_scene.obj
# ==============================================================================
from __future__ import annotations

import json
import math
from pathlib import Path
import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

# ---- [1/2] blender_anim_helpers.py ----
{anim_helpers_src}

import sys as _sharp_sys
_sharp_sys.modules.setdefault("blender_anim_helpers", _sharp_sys.modules[__name__])

# ---- [2/2] blender_build_roblox_rig.py ----
{build_rig_src}


def _sharp_ensure_uv_and_material(obj, mat_name: str, rgba=(0.55, 0.58, 0.64, 1.0), metallic: float = 0.45, roughness: float = 0.35):
    mesh = obj.data
    if not mesh.uv_layers:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_data = uv_layer.data
        for poly in mesh.polygons:
            for loop_idx in poly.loop_indices:
                v_co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.z))

    mat = bpy.data.materials.get(mat_name) or bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    bsdf = None
    for node in mat.node_tree.nodes:
        if node.type == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = tuple(rgba)
    if "Metallic" in bsdf.inputs:
        bsdf.inputs["Metallic"].default_value = float(metallic)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = float(roughness)

    if mesh.materials:
        mesh.materials[0] = mat
    else:
        mesh.materials.append(mat)


def _sharp_import_prop_mesh(source_path_str: str, prop_name: str):
    src = Path(source_path_str)
    if not src.is_file():
        raise FileNotFoundError(f"source_mesh_path not found: {{src}}")
    before = set(bpy.data.objects.keys())
    ext = src.suffix.lower()
    if ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(src))
    elif ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(src))
    elif ext == ".obj":
        if hasattr(bpy.ops, "wm") and hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(src))
        else:
            bpy.ops.import_scene.obj(filepath=str(src))
    else:
        raise ValueError(f"Unsupported mesh extension '{{ext}}' for {{src}}")

    imported_meshes = [
        bpy.data.objects[k]
        for k in bpy.data.objects.keys()
        if k not in before and bpy.data.objects[k].type == "MESH"
    ]
    if not imported_meshes:
        raise RuntimeError(f"No MESH objects imported from {{src}}")

    bpy.ops.object.select_all(action="DESELECT")
    for m_obj in imported_meshes:
        m_obj.select_set(True)
    primary = imported_meshes[0]
    bpy.context.view_layer.objects.active = primary
    if len(imported_meshes) > 1:
        bpy.ops.object.join()
        primary = bpy.context.view_layer.objects.active
    primary.name = prop_name
    primary.data.name = prop_name + "_Mesh"
    return primary


def _sharp_add_box(bm, size_xyz, center_xyz=(0.0, 0.0, 0.0)):
    sx, sy, sz = [float(v) for v in size_xyz]
    cx, cy, cz = [float(v) for v in center_xyz]
    ret = bmesh.ops.create_cube(bm, size=1.0)
    verts = ret["verts"]
    bmesh.ops.scale(bm, vec=(sx, sy, sz), verts=verts)
    bmesh.ops.translate(bm, vec=(cx, cy, cz), verts=verts)
    return verts


def _sharp_build_procedural_prop(prop_kind: str, prop_name: str):
    existing = bpy.data.objects.get(prop_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    mesh = bpy.data.meshes.new(prop_name + "_Mesh")
    obj = bpy.data.objects.new(prop_name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()

    k = prop_kind.lower()
    # Blender local convention before Roblox export: X=right, Y=back, Z=up
    if k == "sword":
        # Hilt grip centered at origin, blade extending +Z
        _sharp_add_box(bm, (0.14, 0.14, 0.80), (0.0, 0.0, 0.0))
        _sharp_add_box(bm, (0.24, 0.24, 0.18), (0.0, 0.0, -0.46))
        _sharp_add_box(bm, (0.85, 0.20, 0.14), (0.0, 0.0, 0.44))
        _sharp_add_box(bm, (0.24, 0.08, 2.55), (0.0, 0.0, 1.78))
    elif k == "shield":
        _sharp_add_box(bm, (2.10, 0.18, 2.50), (0.0, 0.0, 0.0))
        _sharp_add_box(bm, (0.55, 0.16, 0.55), (0.0, -0.14, 0.15))
    elif k == "bow":
        _sharp_add_box(bm, (0.14, 0.18, 1.35), (0.0, 0.0, 0.0))
        _sharp_add_box(bm, (0.12, 0.22, 1.30), (0.0, -0.18, 1.25))
        _sharp_add_box(bm, (0.12, 0.22, 1.30), (0.0, -0.18, -1.25))
        _sharp_add_box(bm, (0.04, 0.04, 3.60), (0.0, -0.34, 0.0))
    elif k == "staff":
        _sharp_add_box(bm, (0.16, 0.16, 4.40), (0.0, 0.0, 1.40))
        _sharp_add_box(bm, (0.42, 0.42, 0.62), (0.0, 0.0, 3.85))
    elif k == "gun":
        _sharp_add_box(bm, (0.22, 0.42, 0.65), (0.0, 0.0, -0.25))
        _sharp_add_box(bm, (0.24, 1.95, 0.34), (0.0, -0.72, 0.16))
        _sharp_add_box(bm, (0.14, 0.28, 0.42), (0.0, -0.85, -0.15))
    elif k in ("backpack", "cape", "wings"):
        dims = (1.55, 0.85, 1.85) if k == "backpack" else ((1.85, 0.18, 2.75) if k == "cape" else (4.4, 0.35, 2.4))
        _sharp_add_box(bm, dims, (0.0, 0.0, 0.0))
    elif k == "helmet":
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.64)
        bmesh.ops.scale(bm, vec=(1.0, 1.0, 0.96), verts=bm.verts)
    elif k == "chest":
        _sharp_add_box(bm, (2.15, 1.22, 1.55), (0.0, 0.0, 0.0))
    elif "pauldron" in k:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.52)
        bmesh.ops.scale(bm, vec=(1.05, 1.0, 0.90), verts=bm.verts)
    elif "greave" in k or "boot" in k or "gauntlet" in k:
        dims = (0.98, 0.98, 1.25) if "greave" in k else ((1.02, 1.15, 0.55) if "boot" in k else (0.85, 0.85, 0.95))
        _sharp_add_box(bm, dims, (0.0, 0.0, 0.0))
    else:
        bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.45)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    _sharp_ensure_uv_and_material(obj, f"M_{{prop_name}}_Mat")
    return obj


def _sharp_rig_height_studs(rig_obj) -> float:
    zs = []
    for pbone in rig_obj.pose.bones:
        w_head = rig_obj.matrix_world @ pbone.head
        w_tail = rig_obj.matrix_world @ pbone.tail
        zs.extend([float(w_head.z), float(w_tail.z)])
    if not zs:
        return 5.0
    return max(1.0, max(zs) - min(zs))


def _sharp_scale_and_align_prop(prop_obj, rig_obj, prop_kind: str, target_size_studs, target_rig_height_studs: float, mode: str, limb_name: str):
    rig_h = _sharp_rig_height_studs(rig_obj)
    height_scale = rig_h / 5.0 if rig_h > 0.1 else 1.0

    bpy.context.view_layer.update()
    bbox = [prop_obj.matrix_world @ Vector(corner) for corner in prop_obj.bound_box]
    xs = [c.x for c in bbox]
    ys = [c.y for c in bbox]
    zs = [c.z for c in bbox]
    cur_max_span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1e-4)
    desired_max_span = max(target_size_studs) * (float(target_rig_height_studs) / 5.0) * (height_scale / max(height_scale, 1e-4))
    if abs(cur_max_span - desired_max_span) / max(desired_max_span, 1e-4) > 0.15:
        sf = desired_max_span / cur_max_span
        prop_obj.scale = (prop_obj.scale.x * sf, prop_obj.scale.y * sf, prop_obj.scale.z * sf)

    bpy.ops.object.select_all(action="DESELECT")
    prop_obj.select_set(True)
    bpy.context.view_layer.objects.active = prop_obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # Place armor / prop near its target rig bone before parenting or armature binding
    bone = rig_obj.pose.bones.get(limb_name) or rig_obj.pose.bones.get("UpperTorso")
    if bone is not None:
        bone_mid_world = rig_obj.matrix_world @ ((bone.head + bone.tail) * 0.5)
        if mode == "skinned_armor":
            prop_obj.location = bone_mid_world
        else:
            prop_obj.location = rig_obj.matrix_world @ bone.tail


def _sharp_roblox_offset_to_blender_matrix(pos_rbx, rot_deg_rbx) -> Matrix:
    px, py, pz = [float(v) for v in pos_rbx]
    rx, ry, rz = [math.radians(float(v)) for v in rot_deg_rbx]
    # Roblox CFrame.Angles(rx, ry, rz) multiplies Rx * Ry * Rz
    rbx_rot = Matrix.Rotation(rx, 4, "X") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rz, 4, "Z")
    rbx_mat = Matrix.Translation((px, py, pz)) @ rbx_rot
    return ROBLOX_TO_BLENDER @ rbx_mat @ ROBLOX_TO_BLENDER_INV


def _sharp_rot_mat9_to_euler_deg(m9) -> list:
    r00, r01, r02, r10, r11, _r12, _r20, _r21, r22 = [float(v) for v in m9]
    r12 = float(m9[5])
    if r02 >= 0.99999:
        ry = math.pi * 0.5
        rx = math.atan2(r10, r11)
        rz = 0.0
    elif r02 <= -0.99999:
        ry = -math.pi * 0.5
        rx = math.atan2(-r10, r11)
        rz = 0.0
    else:
        ry = math.asin(max(-1.0, min(1.0, r02)))
        rx = math.atan2(-r12, r22)
        rz = math.atan2(-r01, r00)
    return [round(math.degrees(rx), 4), round(math.degrees(ry), 4), round(math.degrees(rz), 4)]


def _sharp_add_socket_empty(prop_obj, att_name: str, pos_rbx, rot_deg_rbx, target_limb, target_limb_att, role: str):
    existing = bpy.data.objects.get(att_name)
    if existing and existing.type == "EMPTY" and existing.parent == prop_obj:
        bpy.data.objects.remove(existing, do_unlink=True)
    empty = bpy.data.objects.new(att_name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.25
    bpy.context.collection.objects.link(empty)
    empty.parent = prop_obj
    local_mat = _sharp_roblox_offset_to_blender_matrix(pos_rbx, rot_deg_rbx)
    empty.matrix_parent_inverse = Matrix.Identity(4)
    empty.matrix_basis = local_mat
    empty["roblox_attachment_role"] = role
    if target_limb:
        empty["roblox_target_limb"] = target_limb
    if target_limb_att:
        empty["roblox_target_limb_attachment"] = target_limb_att
    return empty


def _sharp_bind_prop_to_rig(prop_obj, rig_obj, mode: str, limb_name: str):
    if mode == "skinned_armor":
        bpy.ops.object.select_all(action="DESELECT")
        prop_obj.select_set(True)
        rig_obj.select_set(True)
        bpy.context.view_layer.objects.active = rig_obj
        auto_ok = False
        try:
            bpy.ops.object.parent_set(type="ARMATURE_AUTO")
            bpy.context.view_layer.update()
            total_w = sum(g.weight for v in prop_obj.data.vertices for g in v.groups)
            if prop_obj.vertex_groups and total_w > 1e-5:
                auto_ok = True
        except RuntimeError:
            auto_ok = False

        if not auto_ok:
            # Deterministic bone-proximity fallback for thin plates in headless mode
            prop_obj.parent = rig_obj
            has_arm_mod = any(m.type == "ARMATURE" and m.object == rig_obj for m in prop_obj.modifiers)
            if not has_arm_mod:
                arm_mod = prop_obj.modifiers.new(name="Armature", type="ARMATURE")
                arm_mod.object = rig_obj
            target_bones = []
            if limb_name in rig_obj.data.bones:
                target_bones.append(rig_obj.data.bones[limb_name])
                if rig_obj.data.bones[limb_name].parent:
                    target_bones.append(rig_obj.data.bones[limb_name].parent)
            if not target_bones and rig_obj.data.bones:
                target_bones = [rig_obj.data.bones[0]]

            for b in target_bones:
                if b.name not in prop_obj.vertex_groups:
                    prop_obj.vertex_groups.new(name=b.name)

            v_indices = [v.index for v in prop_obj.data.vertices]
            primary_vg = prop_obj.vertex_groups[target_bones[0].name]
            if len(target_bones) == 1:
                primary_vg.add(v_indices, 1.0, "REPLACE")
            else:
                sec_vg = prop_obj.vertex_groups[target_bones[1].name]
                b0_mid = rig_obj.matrix_world @ ((target_bones[0].head_local + target_bones[0].tail_local) * 0.5)
                b1_mid = rig_obj.matrix_world @ ((target_bones[1].head_local + target_bones[1].tail_local) * 0.5)
                for v in prop_obj.data.vertices:
                    vw = prop_obj.matrix_world @ v.co
                    d0 = max((vw - b0_mid).length, 1e-4)
                    d1 = max((vw - b1_mid).length, 1e-4)
                    w0 = (1.0 / d0)
                    w1 = (1.0 / d1)
                    s = w0 + w1
                    primary_vg.add([v.index], w0 / s, "REPLACE")
                    sec_vg.add([v.index], w1 / s, "REPLACE")

        # Enforce Roblox 4-bone influence limit & normalize weights cleanly without fragile mode assumptions
        mesh = prop_obj.data
        max_w = 0
        for v in mesh.vertices:
            non_zero = [(g.group, g.weight) for g in v.groups if g.weight > 1e-6]
            non_zero.sort(key=lambda item: item[1], reverse=True)
            kept = non_zero[:4]
            dropped = non_zero[4:]
            for grp_idx, _ in dropped:
                prop_obj.vertex_groups[grp_idx].remove([v.index])
            tot = sum(w for _, w in kept)
            if tot > 1e-6 and kept:
                for grp_idx, w in kept:
                    prop_obj.vertex_groups[grp_idx].add([v.index], w / tot, "REPLACE")
            max_w = max(max_w, len(kept))
        return max_w

    # Rigid prop: parent directly to target bone with Rig tail offset so pose matches Roblox attach
    bone = rig_obj.data.bones.get(limb_name) or rig_obj.data.bones.get("RightHand")
    if bone is not None:
        prop_obj.parent = rig_obj
        prop_obj.parent_type = "BONE"
        prop_obj.parent_bone = bone.name
        tail_offset = Matrix.Translation((0.0, -bone.length, 0.0))
        prop_obj.matrix_parent_inverse = tail_offset @ bone.matrix_local.inverted()
    return 0


def _run_sharp_asset_attach_pipeline():
    out_dir = Path({json.dumps(out_dir.as_posix())})
    out_dir.mkdir(parents=True, exist_ok=True)
    prop_kind = {json.dumps(kind_key)}
    prop_name = {json.dumps(safe_prop)}
    mode = {json.dumps(effective_mode)}
    slot_name = {json.dumps(resolved_slot)}
    primary_limb = {json.dumps(resolved_limb)}
    primary_limb_att = {json.dumps(resolved_limb_att)}
    primary_item_att = {json.dumps(resolved_item_att)}
    src_mesh = {src_mesh_arg}
    target_size = {json.dumps(list(preset["target_size_studs"]))}
    secondary_specs = {json.dumps(preset["secondary_sockets"])}

    rig_obj = build_rig_from_spec({spec_arg}, create_proxies=True)
    if src_mesh:
        prop_obj = _sharp_import_prop_mesh(src_mesh, prop_name)
    else:
        prop_obj = _sharp_build_procedural_prop(prop_kind, prop_name)

    _sharp_scale_and_align_prop(
        prop_obj,
        rig_obj,
        prop_kind,
        target_size,
        {float(target_rig_height_studs)},
        mode,
        primary_limb,
    )
    max_weights = _sharp_bind_prop_to_rig(prop_obj, rig_obj, mode, primary_limb)

    # Create primary & secondary Roblox socket empties parented to prop_obj
    created_empties = []
    primary_empty = _sharp_add_socket_empty(
        prop_obj,
        primary_item_att,
        [0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
        primary_limb,
        primary_limb_att,
        "primary",
    )
    created_empties.append(primary_empty)

    for sec_name, sec_pos, sec_rot, sec_limb, sec_limb_att, sec_role in secondary_specs:
        if sec_name != primary_item_att:
            created_empties.append(
                _sharp_add_socket_empty(prop_obj, sec_name, sec_pos, sec_rot, sec_limb, sec_limb_att, sec_role)
            )

    bpy.context.view_layer.update()
    attachments_json = []
    prop_world_inv = prop_obj.matrix_world.inverted()
    for emp in created_empties:
        rel_mat = prop_world_inv @ emp.matrix_world
        pos_rbx, rot_mat9_rbx = matrix_to_roblox_cf(rel_mat, unit_scale=1.0)
        rot_deg_rbx = _sharp_rot_mat9_to_euler_deg(rot_mat9_rbx)
        attachments_json.append({{
            "name": emp.name,
            "role": str(emp.get("roblox_attachment_role", "secondary")),
            "target_limb": emp.get("roblox_target_limb"),
            "target_limb_attachment": emp.get("roblox_target_limb_attachment"),
            "pos": [round(float(v), 5) for v in pos_rbx],
            "rot_deg": rot_deg_rbx,
            "rot_matrix": [round(float(v), 6) for v in rot_mat9_rbx],
            "cframe": [round(float(v), 5) for v in (list(pos_rbx) + list(rot_mat9_rbx))],
        }})

    bbox_local = [Vector(corner) for corner in prop_obj.bound_box]
    xs = [c.x for c in bbox_local]
    ys = [c.y for c in bbox_local]
    zs = [c.z for c in bbox_local]
    dims_studs = [
        round(max(xs) - min(xs), 4),
        round(max(zs) - min(zs), 4),
        round(max(ys) - min(ys), 4),
    ]

    sidecar_path = Path({json.dumps(sidecar_file.as_posix())})
    fbx_path = Path({json.dumps(fbx_file.as_posix())})
    glb_path = Path({json.dumps(glb_file.as_posix())})

    # Export FBX (include rig when skinned_armor so skin weights survive; prop+empties always included)
    if {repr(bool(export_fbx))}:
        bpy.ops.object.select_all(action="DESELECT")
        prop_obj.select_set(True)
        for emp in created_empties:
            emp.select_set(True)
        if mode == "skinned_armor":
            rig_obj.select_set(True)
            bpy.context.view_layer.objects.active = rig_obj
            obj_types = {{"ARMATURE", "MESH", "EMPTY"}}
        else:
            bpy.context.view_layer.objects.active = prop_obj
            obj_types = {{"MESH", "EMPTY"}}
        bpy.ops.export_scene.fbx(
            filepath=str(fbx_path),
            use_selection=True,
            object_types=obj_types,
            apply_scale_options="FBX_SCALE_ALL",
            axis_forward="-Z",
            axis_up="Y",
            add_leaf_bones=False,
            bake_anim=False,
        )

    if {repr(bool(export_glb))}:
        bpy.ops.object.select_all(action="DESELECT")
        prop_obj.select_set(True)
        for emp in created_empties:
            emp.select_set(True)
        if mode == "skinned_armor":
            rig_obj.select_set(True)
            bpy.context.view_layer.objects.active = rig_obj
        else:
            bpy.context.view_layer.objects.active = prop_obj
        bpy.ops.export_scene.gltf(
            filepath=str(glb_path),
            use_selection=True,
            export_format="GLB",
            export_yup=True,
        )

    sidecar_payload = {{
        "schema": "sharp.attachment_sidecar.v1",
        "prop_name": prop_name,
        "prop_kind": prop_kind,
        "attachment_mode": mode,
        "attach_mode": {json.dumps(recommended_attach_mode)},
        "slot": slot_name,
        "rig_height_studs": round(_sharp_rig_height_studs(rig_obj), 4),
        "prop_dimensions_studs": dims_studs,
        "target_limb": primary_limb,
        "target_limb_attachment": primary_limb_att,
        "parent_bone": primary_limb,
        "vertex_group_count": len(prop_obj.vertex_groups),
        "max_weights_per_vertex": int(max_weights),
        "fbx_path": str(fbx_path) if {repr(bool(export_fbx))} else None,
        "glb_path": str(glb_path) if {repr(bool(export_glb))} else None,
        "attachments": attachments_json,
    }}
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")
    print("SHARP_BLENDER_ASSET_ATTACH_OK", json.dumps({{"sidecar": str(sidecar_path), "attachment_count": len(attachments_json)}}))
    return sidecar_payload


_run_sharp_asset_attach_pipeline()
'''

        result: Dict[str, Any] = {
            "ok": True,
            "pipeline": "blender_asset_attach",
            "prop_kind": kind_key,
            "prop_name": safe_prop,
            "attachment_mode": effective_mode,
            "attach_mode": recommended_attach_mode,
            "slot": resolved_slot,
            "target_limb": resolved_limb,
            "target_limb_attachment": resolved_limb_att,
            "item_attachment": resolved_item_att,
            "output_dir": str(out_dir),
            "sidecar_path": str(sidecar_file),
            "fbx_path": str(fbx_file) if export_fbx else None,
            "glb_path": str(glb_file) if export_glb else None,
            "compiled_bpy_code": compiled_py,
            "executed": False,
        }

        if execute:
            exec_res = execute_bpy_over_socket_or_headless(
                code=compiled_py,
                host=self.blender_host,
                port=self.blender_port,
                mode=execution_mode,
                auto_install=auto_install,
                timeout_sec=timeout_sec,
            )
            result["execution"] = exec_res
            result["executed"] = bool(exec_res.get("ok"))
            result["ok"] = bool(exec_res.get("ok"))
            if result["executed"] and sidecar_file.is_file():
                result["sidecar"] = json.loads(sidecar_file.read_text(encoding="utf-8"))
                reg_paths = [p for p in (fbx_file, glb_file, sidecar_file) if p.is_file()]
                result["registered_asset_keys"] = self._register_outputs_if_present(
                    project_library=project_library,
                    asset_name=safe_prop,
                    category="mesh",
                    paths=reg_paths,
                    description=f"Blender rigged/socketed {kind_key} ({effective_mode})",
                    tags=["blender", "equipment", kind_key, effective_mode],
                )
        return result

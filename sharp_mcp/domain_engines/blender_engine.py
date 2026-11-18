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


BLENDER_ASSET_STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "lowpoly_flat_stylized": {
        "default_primary": "#4B9CD3",
        "default_secondary": "#F59E0B",
        "default_accent": "#34D399",
        "leather_rgba": (0.20, 0.12, 0.08, 1.0),
        "metal_metallic": 0.18,
        "metal_roughness": 0.52,
        "trim_metallic": 0.30,
        "trim_roughness": 0.42,
        "emissive_strength": 0.35,
        "flat_shading": True,
    },
    "handpainted_fantasy_rpg": {
        "default_primary": "#6E7F91",
        "default_secondary": "#D9A441",
        "default_accent": "#38BDF8",
        "leather_rgba": (0.14, 0.08, 0.05, 1.0),
        "metal_metallic": 0.72,
        "metal_roughness": 0.34,
        "trim_metallic": 0.88,
        "trim_roughness": 0.24,
        "emissive_strength": 0.60,
        "flat_shading": False,
    },
    "hard_surface_scifi_mecha": {
        "default_primary": "#334155",
        "default_secondary": "#E2E8F0",
        "default_accent": "#22D3EE",
        "leather_rgba": (0.07, 0.08, 0.10, 1.0),
        "metal_metallic": 0.92,
        "metal_roughness": 0.22,
        "trim_metallic": 0.90,
        "trim_roughness": 0.18,
        "emissive_strength": 0.95,
        "flat_shading": False,
    },
    "chibi_chunky_toon": {
        "default_primary": "#FF5E7E",
        "default_secondary": "#FFD166",
        "default_accent": "#06D6A0",
        "leather_rgba": (0.22, 0.14, 0.10, 1.0),
        "metal_metallic": 0.22,
        "metal_roughness": 0.30,
        "trim_metallic": 0.42,
        "trim_roughness": 0.26,
        "emissive_strength": 0.45,
        "flat_shading": False,
    },
    "dark_gothic_souls": {
        "default_primary": "#2D313A",
        "default_secondary": "#9C7A3C",
        "default_accent": "#E11D48",
        "leather_rgba": (0.08, 0.05, 0.04, 1.0),
        "metal_metallic": 0.84,
        "metal_roughness": 0.42,
        "trim_metallic": 0.86,
        "trim_roughness": 0.36,
        "emissive_strength": 0.70,
        "flat_shading": False,
    },
}

BLENDER_TEXTURE_STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "clean_vector_cel": {"roughness_bias": -0.04, "emissive_mul": 0.90},
    "stylized_gradient_atlas": {"roughness_bias": 0.00, "emissive_mul": 1.00},
    "pbr_metallic_roughness": {"roughness_bias": -0.06, "emissive_mul": 1.05},
    "pixel_retro_crisp": {"roughness_bias": 0.12, "emissive_mul": 0.80},
    "arcane_emissive_runes": {"roughness_bias": -0.02, "emissive_mul": 1.35},
}

_CUSTOM_SLOT_TARGETS: Dict[str, tuple[str, str, str]] = {
    "right_hand": ("RightHand", "RightGripAttachment", "GripAttachment"),
    "left_hand": ("LeftHand", "LeftGripAttachment", "GripAttachment"),
    "back": ("UpperTorso", "BodyBackAttachment", "BodyBackAttachment"),
    "front": ("UpperTorso", "BodyFrontAttachment", "BodyFrontAttachment"),
    "chest": ("UpperTorso", "BodyFrontAttachment", "BodyFrontAttachment"),
    "head": ("Head", "HatAttachment", "HatAttachment"),
    "helmet": ("Head", "HatAttachment", "HatAttachment"),
    "face": ("Head", "FaceFrontAttachment", "FaceFrontAttachment"),
    "waist": ("LowerTorso", "WaistCenterAttachment", "WaistCenterAttachment"),
    "hip_left": ("LowerTorso", "WaistCenterAttachment", "HolsterHipAttachment"),
    "hip_right": ("LowerTorso", "WaistCenterAttachment", "HolsterHipAttachment"),
    "left_shoulder": ("LeftUpperArm", "LeftShoulderAttachment", "LeftShoulderAttachment"),
    "right_shoulder": ("RightUpperArm", "RightShoulderAttachment", "RightShoulderAttachment"),
    "left_pauldron": ("LeftUpperArm", "LeftShoulderAttachment", "LeftShoulderAttachment"),
    "right_pauldron": ("RightUpperArm", "RightShoulderAttachment", "RightShoulderAttachment"),
    "left_foot": ("LeftFoot", "LeftFootAttachment", "LeftFootAttachment"),
    "right_foot": ("RightFoot", "RightFootAttachment", "RightFootAttachment"),
}


def _hex_to_linear_rgba(hex_color: Optional[str], default_rgba=(0.14, 0.62, 0.96, 1.0)) -> tuple[float, float, float, float]:
    """Convert `#RRGGBB` hex string into linearized RGBA 4-tuple for Principled BSDF."""
    raw = (hex_color or "").strip().lstrip("#")
    if len(raw) != 6:
        return tuple(float(v) for v in default_rgba)
    try:
        vals = [int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4)]
    except ValueError:
        return tuple(float(v) for v in default_rgba)

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (round(_lin(vals[0]), 5), round(_lin(vals[1]), 5), round(_lin(vals[2]), 5), 1.0)


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
        accent_hex: Optional[str] = None,
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
        resolved_accent = (accent_hex or "").strip() if accent_hex else ""
        if not resolved_accent and project_library is not None and hasattr(project_library, "get_design_system"):
            ds = project_library.get_design_system() or {}
            resolved_accent = str(((ds.get("palette") or {}).get("accent")) or "")
        accent_rgba_tuple = _hex_to_linear_rgba(resolved_accent or "#38BDF8")

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
            nrm = poly.normal
            ax, ay, az = abs(float(nrm.x)), abs(float(nrm.y)), abs(float(nrm.z))
            for loop_idx in poly.loop_indices:
                v_co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                # Triplanar-aligned box UV projection avoids stretched polar UVs
                if az >= ax and az >= ay:
                    u_v = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.y))
                elif ay >= ax:
                    u_v = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.z))
                else:
                    u_v = (0.5 + 0.25 * float(v_co.y), 0.5 + 0.25 * float(v_co.z))
                uv_data[loop_idx].uv = u_v

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
    return mat


def _sharp_ensure_multi_materials(obj, prop_name: str, accent_rgba=(0.14, 0.62, 0.96, 1.0)):
    mesh = obj.data
    if not mesh.uv_layers:
        uv_layer = mesh.uv_layers.new(name="UVMap")
        uv_data = uv_layer.data
        for poly in mesh.polygons:
            nrm = poly.normal
            ax, ay, az = abs(float(nrm.x)), abs(float(nrm.y)), abs(float(nrm.z))
            for loop_idx in poly.loop_indices:
                v_co = mesh.vertices[mesh.loops[loop_idx].vertex_index].co
                if az >= ax and az >= ay:
                    uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.y))
                elif ay >= ax:
                    uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.z))
                else:
                    uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.y), 0.5 + 0.25 * float(v_co.z))

    specs = [
        ("PrimaryMetal", (0.42, 0.48, 0.56, 1.0), 0.86, 0.28, 0.0),
        ("TrimAccent", (0.82, 0.62, 0.16, 1.0), 0.92, 0.22, 0.0),
        ("LeatherGrip", (0.12, 0.075, 0.05, 1.0), 0.05, 0.68, 0.0),
        ("CoreEmblem", tuple(accent_rgba), 0.18, 0.16, 0.45),
    ]
    mesh.materials.clear()
    for tag, rgba, met, rough, emit_str in specs:
        mat_name = "M_" + prop_name + "_" + tag
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
            bsdf.inputs["Metallic"].default_value = float(met)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(rough)
        if emit_str > 0.0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = tuple(rgba)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = float(emit_str)
        mesh.materials.append(mat)
    max_idx = max(0, len(mesh.materials) - 1)
    for poly in mesh.polygons:
        if poly.material_index < 0 or poly.material_index > max_idx:
            poly.material_index = 0


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
    if not primary.data.materials:
        _sharp_ensure_uv_and_material(primary, "M_" + prop_name + "_Mat")
    return primary


def _sharp_merge_sub_bm(bm, sub_bm, mat_idx: int = 0, rot_deg=(0.0, 0.0, 0.0), loc=(0.0, 0.0, 0.0)):
    sub_bm.verts.index_update()
    rot_mat = Euler(
        (math.radians(float(rot_deg[0])), math.radians(float(rot_deg[1])), math.radians(float(rot_deg[2]))),
        "XYZ",
    ).to_matrix()
    offset = Vector((float(loc[0]), float(loc[1]), float(loc[2])))
    vmap = [bm.verts.new((rot_mat @ v.co) + offset) for v in sub_bm.verts]
    for f in sub_bm.faces:
        try:
            nf = bm.faces.new([vmap[v.index] for v in f.verts])
            nf.material_index = int(mat_idx)
        except ValueError:
            pass
    sub_bm.free()


def _sharp_add_box(bm, size_xyz, center_xyz=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), bevel_ratio: float = 0.08, mat_idx: int = 0):
    sx, sy, sz = [max(1e-4, float(v)) for v in size_xyz]
    sub = bmesh.new()
    bmesh.ops.create_cube(sub, size=1.0)
    bmesh.ops.scale(sub, vec=(sx, sy, sz), verts=sub.verts)
    if bevel_ratio > 0.0:
        bev = min(sx, sy, sz) * min(0.32, float(bevel_ratio))
        if bev > 1e-4:
            bmesh.ops.bevel(sub, geom=list(sub.edges), offset=bev, segments=1, affect="EDGES", clamp_overlap=True)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=center_xyz)


def _sharp_add_cylinder(bm, r1: float, r2: float, depth: float, segs: int = 12, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    bmesh.ops.create_cone(
        sub,
        cap_ends=True,
        cap_tris=False,
        segments=max(4, int(segs)),
        radius1=max(1e-4, float(r1)),
        radius2=max(1e-4, float(r2)),
        depth=max(1e-4, float(depth)),
    )
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_sphere(bm, radius: float, scale_xyz=(1.0, 1.0, 1.0), segs: int = 12, rings: int = 6, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    bmesh.ops.create_uvsphere(sub, u_segments=max(6, int(segs)), v_segments=max(4, int(rings)), radius=max(1e-4, float(radius)))
    bmesh.ops.scale(sub, vec=(float(scale_xyz[0]), float(scale_xyz[1]), float(scale_xyz[2])), verts=sub.verts)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_tapered_blade(bm, width: float, thickness: float, length: float, tip_len: float, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    hw = max(0.01, float(width) * 0.5)
    ht = max(0.008, float(thickness) * 0.5)
    sh_z = max(0.05, float(length) - float(tip_len))
    v0 = sub.verts.new((-hw, 0.0, 0.0))
    v1 = sub.verts.new((0.0, -ht, 0.0))
    v2 = sub.verts.new((hw, 0.0, 0.0))
    v3 = sub.verts.new((0.0, ht, 0.0))
    s0 = sub.verts.new((-hw * 0.72, 0.0, sh_z))
    s1 = sub.verts.new((0.0, -ht * 0.78, sh_z))
    s2 = sub.verts.new((hw * 0.72, 0.0, sh_z))
    s3 = sub.verts.new((0.0, ht * 0.78, sh_z))
    apex = sub.verts.new((0.0, 0.0, float(length)))
    sub.faces.new([v3, v2, v1, v0])
    for a0, a1, b1, b0 in ((v0, v1, s1, s0), (v1, v2, s2, s1), (v2, v3, s3, s2), (v3, v0, s0, s3)):
        sub.faces.new([a0, a1, b1, b0])
    for t0, t1 in ((s0, s1), (s1, s2), (s2, s3), (s3, s0)):
        sub.faces.new([t0, t1, apex])
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_faceted_gem(bm, rx: float, ry: float, rz: float, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 3):
    sub = bmesh.new()
    bmesh.ops.create_icosphere(sub, subdivisions=1, radius=1.0)
    bmesh.ops.scale(sub, vec=(float(rx), float(ry), float(rz)), verts=sub.verts)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_curved_shell(bm, width: float, height: float, curve_depth: float, thickness: float, segs: int = 5, taper_bottom: float = 0.65, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    half_segs = max(1, int(segs) // 2)
    seg_w = float(width) / max(1, int(segs))
    for idx in range(-half_segs, half_segs + 1):
        u = float(idx) / max(1, half_segs)
        px = idx * (seg_w * 0.92)
        py = -float(curve_depth) * (1.0 - u * u * 0.85)
        yaw = u * 26.0
        h_local = float(height) * (1.0 - abs(u) * (1.0 - float(taper_bottom)) * 0.35)
        _sharp_add_box(bm, (seg_w * 1.05, thickness, h_local), (loc[0] + px, loc[1] + py, loc[2]), (rot_deg[0], rot_deg[1], rot_deg[2] + yaw), bevel_ratio=0.14, mat_idx=mat_idx)


def _sharp_build_procedural_prop(prop_kind: str, prop_name: str, accent_rgba=(0.14, 0.62, 0.96, 1.0)):
    existing = bpy.data.objects.get(prop_name)
    if existing:
        bpy.data.objects.remove(existing, do_unlink=True)
    mesh = bpy.data.meshes.new(prop_name + "_Mesh")
    obj = bpy.data.objects.new(prop_name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()

    k = prop_kind.lower()
    # Material slot conventions: 0=PrimaryMetal, 1=TrimAccent, 2=LeatherGrip, 3=CoreEmblem
    # Blender local convention before Roblox export: X=right, Y=back, Z=up
    if k == "sword":
        # Leather wrapped handle + trim rings + swept winged crossguard + diamond blade + faceted pommel gem
        _sharp_add_cylinder(bm, 0.068, 0.062, 0.72, segs=10, loc=(0.0, 0.0, -0.02), mat_idx=2)
        for rz in (-0.24, -0.04, 0.16):
            _sharp_add_cylinder(bm, 0.076, 0.076, 0.04, segs=10, loc=(0.0, 0.0, rz), mat_idx=1)
        _sharp_add_cylinder(bm, 0.11, 0.08, 0.11, segs=8, loc=(0.0, 0.0, -0.42), mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.075, 0.075, 0.09, loc=(0.0, 0.0, -0.51), mat_idx=3)
        _sharp_add_box(bm, (0.24, 0.20, 0.16), (0.0, 0.0, 0.36), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_box(bm, (0.40, 0.13, 0.10), (-0.28, 0.0, 0.42), rot_deg=(0.0, -16.0, 0.0), bevel_ratio=0.16, mat_idx=1)
        _sharp_add_box(bm, (0.40, 0.13, 0.10), (0.28, 0.0, 0.42), rot_deg=(0.0, 16.0, 0.0), bevel_ratio=0.16, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.075, 0.095, 0.075, loc=(0.0, 0.0, 0.36), mat_idx=3)
        _sharp_add_tapered_blade(bm, width=0.28, thickness=0.11, length=2.65, tip_len=0.52, loc=(0.0, 0.0, 0.44), mat_idx=0)
        _sharp_add_box(bm, (0.055, 0.125, 1.78), (0.0, 0.0, 1.38), bevel_ratio=0.12, mat_idx=1)
    elif k == "shield":
        # Arched heater shield + gold outer rim + layered boss medallion + rear handle
        _sharp_add_curved_shell(bm, 2.05, 2.38, curve_depth=0.22, thickness=0.14, segs=5, taper_bottom=0.58, loc=(0.0, 0.0, 0.0), mat_idx=0)
        _sharp_add_curved_shell(bm, 2.16, 0.16, curve_depth=0.24, thickness=0.19, segs=5, taper_bottom=0.95, loc=(0.0, -0.02, 1.15), mat_idx=1)
        _sharp_add_box(bm, (0.14, 0.18, 2.05), (-0.98, 0.06, 0.02), rot_deg=(0.0, -8.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_box(bm, (0.14, 0.18, 2.05), (0.98, 0.06, 0.02), rot_deg=(0.0, 8.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_cylinder(bm, 0.36, 0.24, 0.14, segs=12, loc=(0.0, -0.26, 0.14), rot_deg=(90.0, 0.0, 0.0), mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.18, 0.14, 0.18, loc=(0.0, -0.34, 0.14), mat_idx=3)
        _sharp_add_box(bm, (0.12, 0.26, 0.62), (0.0, 0.20, 0.0), bevel_ratio=0.15, mat_idx=2)
    elif k == "bow":
        # Ergonomic leather riser + swept curved limbs + gilded tips + rune sight + bowstring
        _sharp_add_box(bm, (0.15, 0.21, 0.95), (0.0, 0.0, 0.0), bevel_ratio=0.2, mat_idx=2)
        _sharp_add_box(bm, (0.13, 0.20, 0.78), (0.0, -0.10, 0.78), rot_deg=(14.0, 0.0, 0.0), bevel_ratio=0.18, mat_idx=0)
        _sharp_add_box(bm, (0.10, 0.16, 0.72), (0.0, -0.30, 1.38), rot_deg=(24.0, 0.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_box(bm, (0.13, 0.20, 0.78), (0.0, -0.10, -0.78), rot_deg=(-14.0, 0.0, 0.0), bevel_ratio=0.18, mat_idx=0)
        _sharp_add_box(bm, (0.10, 0.16, 0.72), (0.0, -0.30, -1.38), rot_deg=(-24.0, 0.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.09, 0.10, 0.12, loc=(0.0, -0.09, 0.26), mat_idx=3)
        _sharp_add_cylinder(bm, 0.016, 0.016, 3.36, segs=6, loc=(0.0, -0.45, 0.0), mat_idx=0)
    elif k == "staff":
        # Fluted staff shaft + grip leather + twin cradle horns + glowing hovering crystal orb
        _sharp_add_cylinder(bm, 0.075, 0.095, 4.10, segs=10, loc=(0.0, 0.0, 1.15), mat_idx=2)
        for sz in (-0.35, 0.35, 3.05, 3.22):
            _sharp_add_cylinder(bm, 0.115, 0.115, 0.08, segs=10, loc=(0.0, 0.0, sz), mat_idx=1)
        _sharp_add_box(bm, (0.11, 0.12, 0.64), (-0.22, 0.0, 3.55), rot_deg=(0.0, -24.0, 0.0), bevel_ratio=0.2, mat_idx=1)
        _sharp_add_box(bm, (0.11, 0.12, 0.64), (0.22, 0.0, 3.55), rot_deg=(0.0, 24.0, 0.0), bevel_ratio=0.2, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.24, 0.24, 0.34, loc=(0.0, 0.0, 3.74), mat_idx=3)
    elif k == "gun":
        # Tactical beveled carbine: receiver, shroud, barrel, muzzle brake, stock, grip, curved mag, optic
        _sharp_add_box(bm, (0.24, 1.18, 0.34), (0.0, -0.35, 0.16), bevel_ratio=0.14, mat_idx=0)
        _sharp_add_cylinder(bm, 0.068, 0.065, 1.35, segs=10, loc=(0.0, -1.10, 0.19), rot_deg=(90.0, 0.0, 0.0), mat_idx=0)
        _sharp_add_box(bm, (0.19, 0.72, 0.24), (0.0, -1.06, 0.19), bevel_ratio=0.14, mat_idx=1)
        _sharp_add_cylinder(bm, 0.09, 0.085, 0.18, segs=8, loc=(0.0, -1.82, 0.19), rot_deg=(90.0, 0.0, 0.0), mat_idx=1)
        _sharp_add_box(bm, (0.20, 0.34, 0.66), (0.0, 0.02, -0.22), rot_deg=(16.0, 0.0, 0.0), bevel_ratio=0.14, mat_idx=2)
        _sharp_add_box(bm, (0.18, 0.70, 0.26), (0.0, 0.56, 0.12), bevel_ratio=0.12, mat_idx=2)
        _sharp_add_box(bm, (0.15, 0.28, 0.56), (0.0, -0.58, -0.22), rot_deg=(-12.0, 0.0, 0.0), bevel_ratio=0.1, mat_idx=2)
        _sharp_add_box(bm, (0.14, 0.32, 0.14), (0.0, -0.32, 0.40), bevel_ratio=0.15, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.06, 0.08, 0.06, loc=(0.0, -0.44, 0.40), mat_idx=3)
    elif k == "helmet":
        # Contoured dome + sagittal crest + T-visor bar + cheek plates + ear medallions
        _sharp_add_sphere(bm, 0.60, scale_xyz=(0.98, 1.06, 1.02), segs=14, rings=8, loc=(0.0, 0.0, 0.04), mat_idx=0)
        _sharp_add_box(bm, (0.14, 0.84, 0.34), (0.0, -0.02, 0.56), bevel_ratio=0.18, mat_idx=3)
        _sharp_add_curved_shell(bm, 1.12, 0.18, curve_depth=0.22, thickness=0.12, segs=5, loc=(0.0, -0.54, 0.14), mat_idx=1)
        _sharp_add_box(bm, (0.14, 0.14, 0.58), (0.0, -0.62, -0.10), bevel_ratio=0.15, mat_idx=1)
        _sharp_add_box(bm, (0.22, 0.46, 0.52), (-0.48, -0.28, -0.18), bevel_ratio=0.14, mat_idx=0)
        _sharp_add_box(bm, (0.22, 0.46, 0.52), (0.48, -0.28, -0.18), bevel_ratio=0.14, mat_idx=0)
        _sharp_add_cylinder(bm, 0.16, 0.13, 0.10, segs=10, loc=(-0.60, 0.0, -0.02), rot_deg=(0.0, 90.0, 0.0), mat_idx=1)
        _sharp_add_cylinder(bm, 0.16, 0.13, 0.10, segs=10, loc=(0.60, 0.0, -0.02), rot_deg=(0.0, 90.0, 0.0), mat_idx=1)
    elif k == "chest":
        # Contoured pectoral cuirass + fauld lames + gorget trim + belt/buckle + glowing chest core
        _sharp_add_box(bm, (2.02, 1.12, 0.92), (0.0, 0.0, 0.24), bevel_ratio=0.16, mat_idx=0)
        _sharp_add_box(bm, (1.76, 1.02, 0.52), (0.0, 0.02, -0.44), bevel_ratio=0.14, mat_idx=0)
        _sharp_add_box(bm, (1.38, 0.98, 0.22), (0.0, -0.02, 0.74), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_box(bm, (1.84, 1.08, 0.24), (0.0, 0.0, -0.58), bevel_ratio=0.12, mat_idx=2)
        _sharp_add_box(bm, (0.40, 0.18, 0.30), (0.0, -0.56, -0.58), bevel_ratio=0.15, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.22, 0.14, 0.26, loc=(0.0, -0.58, 0.28), mat_idx=3)
    elif "pauldron" in k:
        # Three overlapping nested curved shoulder plates + trim ridge + emblem + strap
        sx_sign = -1.0 if "left" in k else 1.0
        for layer_idx, (lw, lh, off_z, tilt) in enumerate(((1.12, 0.64, 0.18, 12.0), (1.02, 0.44, -0.12, 22.0), (0.90, 0.36, -0.36, 30.0))):
            _sharp_add_curved_shell(
                bm,
                lw,
                lh,
                curve_depth=0.22,
                thickness=0.14,
                segs=5,
                loc=(sx_sign * layer_idx * 0.06, 0.0, off_z),
                rot_deg=(0.0, sx_sign * tilt, sx_sign * -90.0),
                mat_idx=0,
            )
        _sharp_add_box(bm, (0.20, 0.96, 0.18), (sx_sign * 0.04, 0.0, 0.36), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.14, 0.14, 0.18, loc=(sx_sign * 0.42, 0.0, 0.14), mat_idx=3)
        _sharp_add_box(bm, (0.76, 0.20, 0.16), (0.0, 0.0, -0.32), bevel_ratio=0.12, mat_idx=2)
    elif "greave" in k:
        # Tapered shin plate + sculpted knee cop + dual calf straps + crest gem
        _sharp_add_curved_shell(bm, 0.92, 1.14, curve_depth=0.18, thickness=0.14, segs=5, taper_bottom=0.72, loc=(0.0, -0.05, 0.0), mat_idx=0)
        _sharp_add_sphere(bm, 0.34, scale_xyz=(0.95, 0.65, 1.05), segs=10, rings=6, loc=(0.0, -0.46, 0.42), mat_idx=1)
        _sharp_add_faceted_gem(bm, 0.12, 0.10, 0.16, loc=(0.0, -0.58, 0.42), mat_idx=3)
        _sharp_add_cylinder(bm, 0.48, 0.48, 0.14, segs=10, loc=(0.0, 0.02, 0.22), mat_idx=2)
        _sharp_add_cylinder(bm, 0.42, 0.42, 0.14, segs=10, loc=(0.0, 0.02, -0.32), mat_idx=2)
    elif "boot" in k:
        # Armored cuff + sabaton toe cap + tread sole + ankle buckle
        _sharp_add_box(bm, (0.94, 0.94, 0.46), (0.0, 0.04, 0.12), bevel_ratio=0.16, mat_idx=0)
        _sharp_add_box(bm, (0.92, 0.88, 0.34), (0.0, -0.28, -0.08), bevel_ratio=0.22, mat_idx=1)
        _sharp_add_box(bm, (0.98, 1.22, 0.12), (0.0, -0.10, -0.26), bevel_ratio=0.12, mat_idx=2)
        _sharp_add_box(bm, (0.98, 0.24, 0.14), (0.0, -0.12, 0.18), bevel_ratio=0.15, mat_idx=2)
    elif "gauntlet" in k:
        # Vambrace cuff + articulated knuckle plate + wrist strap + gem
        _sharp_add_cylinder(bm, 0.42, 0.47, 0.84, segs=10, loc=(0.0, 0.0, 0.05), mat_idx=0)
        _sharp_add_box(bm, (0.86, 0.34, 0.28), (0.0, -0.32, -0.24), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_cylinder(bm, 0.46, 0.46, 0.14, segs=10, loc=(0.0, 0.0, 0.22), mat_idx=2)
        _sharp_add_faceted_gem(bm, 0.11, 0.11, 0.14, loc=(0.0, -0.46, 0.06), mat_idx=3)
    elif k == "backpack":
        # Chamfered pack shell + lid flap + twin side pouches + top bedroll + twin straps + buckles + beacon
        _sharp_add_box(bm, (1.36, 0.72, 1.56), (0.0, 0.04, -0.06), bevel_ratio=0.16, mat_idx=2)
        _sharp_add_box(bm, (1.42, 0.78, 0.36), (0.0, 0.04, 0.62), bevel_ratio=0.18, mat_idx=0)
        _sharp_add_box(bm, (0.28, 0.46, 0.82), (-0.78, 0.02, -0.12), bevel_ratio=0.18, mat_idx=2)
        _sharp_add_box(bm, (0.28, 0.46, 0.82), (0.78, 0.02, -0.12), bevel_ratio=0.18, mat_idx=2)
        _sharp_add_cylinder(bm, 0.22, 0.22, 1.28, segs=10, loc=(0.0, 0.12, 0.90), rot_deg=(0.0, 90.0, 0.0), mat_idx=0)
        _sharp_add_box(bm, (0.16, 0.14, 0.26), (-0.36, 0.42, 0.46), bevel_ratio=0.12, mat_idx=1)
        _sharp_add_box(bm, (0.16, 0.14, 0.26), (0.36, 0.42, 0.46), bevel_ratio=0.12, mat_idx=1)
        _sharp_add_box(bm, (0.18, 0.24, 1.32), (-0.42, -0.38, -0.02), bevel_ratio=0.12, mat_idx=2)
        _sharp_add_box(bm, (0.18, 0.24, 1.32), (0.42, -0.38, -0.02), bevel_ratio=0.12, mat_idx=2)
        _sharp_add_faceted_gem(bm, 0.14, 0.12, 0.16, loc=(0.0, 0.44, 0.12), mat_idx=3)
    elif k == "cape":
        # Flared cambered royal mantle + trim border + gilded shoulder clasps
        _sharp_add_curved_shell(bm, 1.88, 2.55, curve_depth=0.28, thickness=0.12, segs=5, taper_bottom=0.82, loc=(0.0, 0.14, 0.0), rot_deg=(-8.0, 0.0, 0.0), mat_idx=3)
        _sharp_add_box(bm, (1.36, 0.24, 0.22), (0.0, 0.02, 1.22), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_cylinder(bm, 0.16, 0.13, 0.10, segs=10, loc=(-0.58, -0.04, 1.18), rot_deg=(90.0, 0.0, 0.0), mat_idx=1)
        _sharp_add_cylinder(bm, 0.16, 0.13, 0.10, segs=10, loc=(0.58, -0.04, 1.18), rot_deg=(90.0, 0.0, 0.0), mat_idx=1)
    elif k == "wings":
        # Dual swept wing spars + fanned tapered primary & secondary pinion blades
        for sx_sign in (-1.0, 1.0):
            _sharp_add_box(bm, (1.65, 0.18, 0.18), (sx_sign * 0.92, 0.12, 0.56), rot_deg=(0.0, sx_sign * 22.0, sx_sign * -14.0), bevel_ratio=0.18, mat_idx=1)
            for idx, (fx, fz, flen, fw, tilt) in enumerate((
                (0.58, 0.30, 1.65, 0.30, 14.0),
                (0.98, 0.36, 1.95, 0.30, 22.0),
                (1.38, 0.44, 2.15, 0.28, 30.0),
                (1.76, 0.52, 1.95, 0.25, 38.0),
                (2.08, 0.58, 1.55, 0.22, 46.0),
            )):
                _sharp_add_tapered_blade(
                    bm,
                    width=fw,
                    thickness=0.09,
                    length=flen,
                    tip_len=flen * 0.28,
                    loc=(sx_sign * fx, 0.18 + idx * 0.03, fz),
                    rot_deg=(-102.0, sx_sign * tilt, 0.0),
                    mat_idx=3 if idx == 4 else 0,
                )
    elif k == "pet":
        # Stylized companion spirit/drone: beveled core cube + glowing visor eye + ear fins + floating halo ring
        _sharp_add_box(bm, (0.76, 0.76, 0.72), (0.0, 0.0, 0.0), bevel_ratio=0.22, mat_idx=0)
        _sharp_add_box(bm, (0.52, 0.16, 0.30), (0.0, -0.36, 0.04), bevel_ratio=0.16, mat_idx=2)
        _sharp_add_faceted_gem(bm, 0.15, 0.10, 0.15, loc=(0.0, -0.43, 0.04), mat_idx=3)
        _sharp_add_box(bm, (0.14, 0.30, 0.46), (-0.44, 0.02, 0.18), rot_deg=(0.0, -18.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_box(bm, (0.14, 0.30, 0.46), (0.44, 0.02, 0.18), rot_deg=(0.0, 18.0, 0.0), bevel_ratio=0.18, mat_idx=1)
        _sharp_add_cylinder(bm, 0.26, 0.16, 0.14, segs=10, loc=(0.0, 0.0, -0.42), mat_idx=2)
        _sharp_add_cylinder(bm, 0.28, 0.28, 0.07, segs=12, loc=(0.0, 0.0, 0.56), mat_idx=1)
    else:
        _sharp_add_faceted_gem(bm, 0.45, 0.45, 0.45, mat_idx=0)

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()

    _sharp_ensure_multi_materials(obj, prop_name, accent_rgba=accent_rgba)
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

    accent_rgba = {repr(accent_rgba_tuple)}

    rig_obj = build_rig_from_spec({spec_arg}, create_proxies=True)
    if src_mesh:
        prop_obj = _sharp_import_prop_mesh(src_mesh, prop_name)
    else:
        prop_obj = _sharp_build_procedural_prop(prop_kind, prop_name, accent_rgba=accent_rgba)

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

    tri_count = sum(max(1, len(p.vertices) - 2) for p in prop_obj.data.polygons)
    vert_count = len(prop_obj.data.vertices)
    mat_slots = [m.name for m in prop_obj.data.materials if m is not None]
    mesh_stats = {{
        "triangle_count": int(tri_count),
        "vertex_count": int(vert_count),
        "polygon_count": len(prop_obj.data.polygons),
        "material_slots": mat_slots,
        "material_count": len(mat_slots),
        "uv_present": bool(prop_obj.data.uv_layers),
        "within_roblox_10k_budget": bool(tri_count <= 10000),
    }}

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
        "mesh_stats": mesh_stats,
        "fbx_path": str(fbx_path) if {repr(bool(export_fbx))} else None,
        "glb_path": str(glb_path) if {repr(bool(export_glb))} else None,
        "attachments": attachments_json,
    }}
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")
    print("SHARP_BLENDER_ASSET_ATTACH_OK", json.dumps({{"sidecar": str(sidecar_path), "attachment_count": len(attachments_json), "triangles": int(tri_count)}}))
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
            "accent_hex": resolved_accent or "#38BDF8",
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
                result["mesh_stats"] = result["sidecar"].get("mesh_stats")
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

    def compile_custom_bmesh_asset_bpy(
        self,
        *,
        asset_name: str = "SharpCustomAsset",
        custom_bpy_code: str = "",
        asset_style: str = "handpainted_fantasy_rpg",
        texture_style: str = "stylized_gradient_atlas",
        attach_mode: str = "motor6d_weapon",
        slot: str = "right_hand",
        primary_hex: Optional[str] = None,
        secondary_hex: Optional[str] = None,
        accent_hex: Optional[str] = None,
        output_dir: str = "",
        export_fbx: bool = True,
        export_glb: bool = True,
        render_preview: bool = True,
        execute: bool = False,
        auto_install: bool = False,
        execution_mode: str = "auto",
        timeout_sec: float = 90.0,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Compile & optionally execute a custom Blender 5.2 bmesh asset builder with 4 PBR slots, UV audit & preview."""
        if custom_bpy_code and custom_bpy_code.strip():
            try:
                compile(custom_bpy_code, "<custom_bpy_code>", "exec")
            except SyntaxError as exc:
                raise ValueError(f"Invalid custom_bpy_code syntax: {exc}") from exc

        anim_helpers_src = _strip_future_and_main(
            self._read_skill_script("roblox-animation", "blender_anim_helpers.py", "01_roblox_animation/skill")
        )

        out_dir = self._resolve_output_dir(output_dir, project_library=project_library)
        safe_asset = re.sub(r"[^a-zA-Z0-9_\-]", "_", asset_name or "SharpCustomAsset") or "SharpCustomAsset"

        style_key = (asset_style or "handpainted_fantasy_rpg").strip().lower().replace("-", "_").replace(" ", "_")
        if style_key not in BLENDER_ASSET_STYLE_PROFILES:
            style_key = "handpainted_fantasy_rpg"
        style_cfg = BLENDER_ASSET_STYLE_PROFILES[style_key]

        tex_key = (texture_style or "stylized_gradient_atlas").strip().lower().replace("-", "_").replace(" ", "_")
        if tex_key not in BLENDER_TEXTURE_STYLE_PROFILES:
            tex_key = "stylized_gradient_atlas"
        tex_cfg = BLENDER_TEXTURE_STYLE_PROFILES[tex_key]

        ds_palette: Dict[str, Any] = {}
        if project_library is not None and hasattr(project_library, "get_design_system"):
            ds = project_library.get_design_system() or {}
            ds_palette = ds.get("palette") or {}

        p_hex = (primary_hex or str(ds_palette.get("primary") or "") or style_cfg["default_primary"]).strip()
        s_hex = (secondary_hex or str(ds_palette.get("secondary") or "") or style_cfg["default_secondary"]).strip()
        a_hex = (accent_hex or str(ds_palette.get("accent") or "") or style_cfg["default_accent"]).strip()

        p_rgba = _hex_to_linear_rgba(p_hex, (0.42, 0.48, 0.56, 1.0))
        s_rgba = _hex_to_linear_rgba(s_hex, (0.82, 0.62, 0.16, 1.0))
        a_rgba = _hex_to_linear_rgba(a_hex, (0.14, 0.62, 0.96, 1.0))
        l_rgba = tuple(float(v) for v in style_cfg["leather_rgba"])

        r_bias = float(tex_cfg["roughness_bias"])
        metal_rough = max(0.08, min(0.95, float(style_cfg["metal_roughness"]) + r_bias))
        trim_rough = max(0.08, min(0.95, float(style_cfg["trim_roughness"]) + r_bias))
        emit_str = round(float(style_cfg["emissive_strength"]) * float(tex_cfg["emissive_mul"]), 4)
        flat_shading = bool(style_cfg.get("flat_shading", False))

        slot_key = (slot or "right_hand").strip().lower().replace("-", "_")
        target_limb, target_limb_att, default_item_att = _CUSTOM_SLOT_TARGETS.get(
            slot_key, ("RightHand", "RightGripAttachment", "GripAttachment")
        )
        norm_attach_mode = (attach_mode or "motor6d_weapon").strip().lower()
        sidecar_att_mode = "skinned_armor" if norm_attach_mode in ("armor_set", "skinned", "skinned_armor") else "rigid"

        sidecar_file = out_dir / f"{safe_asset}_attachments.json"
        fbx_file = out_dir / f"{safe_asset}.fbx"
        glb_file = out_dir / f"{safe_asset}.glb"
        preview_file = out_dir / f"{safe_asset}_preview.png"
        generic_preview_file = out_dir / "preview.png"

        compiled_py = f'''# ==============================================================================
# Sharp MCP Compiled Blender 5.2+ Custom BMesh Asset Pipeline
# Asset: {safe_asset} | Style: {style_key} / {tex_key} | Slot: {slot_key}
# ==============================================================================
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

# ---- blender_anim_helpers.py ----
{anim_helpers_src}


def _sharp_create_styled_materials():
    specs = [
        ("PrimaryMetal", {repr(p_rgba)}, {float(style_cfg["metal_metallic"])}, {metal_rough}, 0.0),
        ("TrimAccent", {repr(s_rgba)}, {float(style_cfg["trim_metallic"])}, {trim_rough}, 0.0),
        ("LeatherGrip", {repr(l_rgba)}, 0.05, 0.72, 0.0),
        ("CoreEmblem", {repr(a_rgba)}, 0.18, 0.18, {emit_str}),
    ]
    mats = {{}}
    mat_list = []
    for slot_name, rgba, met, rough, emit in specs:
        mat = bpy.data.materials.get(slot_name) or bpy.data.materials.new(name=slot_name)
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
            bsdf.inputs["Metallic"].default_value = float(met)
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = float(rough)
        if emit > 0.0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = tuple(rgba)
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = float(emit)
        mats[slot_name] = mat
        mat_list.append(mat)
    return mats, mat_list


def _sharp_merge_sub_bm(bm, sub_bm, mat_idx: int = 0, rot_deg=(0.0, 0.0, 0.0), loc=(0.0, 0.0, 0.0)):
    sub_bm.verts.index_update()
    rot_mat = Euler(
        (math.radians(float(rot_deg[0])), math.radians(float(rot_deg[1])), math.radians(float(rot_deg[2]))),
        "XYZ",
    ).to_matrix()
    offset = Vector((float(loc[0]), float(loc[1]), float(loc[2])))
    vmap = [bm.verts.new((rot_mat @ v.co) + offset) for v in sub_bm.verts]
    for f in sub_bm.faces:
        try:
            nf = bm.faces.new([vmap[v.index] for v in f.verts])
            nf.material_index = int(mat_idx)
        except ValueError:
            pass
    sub_bm.free()


def _sharp_add_box(bm, size_xyz, center_xyz=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), bevel_ratio: float = 0.08, mat_idx: int = 0):
    sx, sy, sz = [max(1e-4, float(v)) for v in size_xyz]
    sub = bmesh.new()
    bmesh.ops.create_cube(sub, size=1.0)
    bmesh.ops.scale(sub, vec=(sx, sy, sz), verts=sub.verts)
    if bevel_ratio > 0.0:
        bev = min(sx, sy, sz) * min(0.32, float(bevel_ratio))
        if bev > 1e-4:
            bmesh.ops.bevel(sub, geom=list(sub.edges), offset=bev, segments=1, affect="EDGES", clamp_overlap=True)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=center_xyz)


def _sharp_add_cylinder(bm, r1: float, r2: float, depth: float, segs: int = 12, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    bmesh.ops.create_cone(
        sub,
        cap_ends=True,
        cap_tris=False,
        segments=max(4, int(segs)),
        radius1=max(1e-4, float(r1)),
        radius2=max(1e-4, float(r2)),
        depth=max(1e-4, float(depth)),
    )
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_sphere(bm, radius: float, scale_xyz=(1.0, 1.0, 1.0), segs: int = 12, rings: int = 6, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    bmesh.ops.create_uvsphere(sub, u_segments=max(6, int(segs)), v_segments=max(4, int(rings)), radius=max(1e-4, float(radius)))
    bmesh.ops.scale(sub, vec=(float(scale_xyz[0]), float(scale_xyz[1]), float(scale_xyz[2])), verts=sub.verts)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_tapered_blade(bm, width: float, thickness: float, length: float, tip_len: float, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    sub = bmesh.new()
    hw = max(0.01, float(width) * 0.5)
    ht = max(0.008, float(thickness) * 0.5)
    sh_z = max(0.05, float(length) - float(tip_len))
    v0 = sub.verts.new((-hw, 0.0, 0.0))
    v1 = sub.verts.new((0.0, -ht, 0.0))
    v2 = sub.verts.new((hw, 0.0, 0.0))
    v3 = sub.verts.new((0.0, ht, 0.0))
    s0 = sub.verts.new((-hw * 0.72, 0.0, sh_z))
    s1 = sub.verts.new((0.0, -ht * 0.78, sh_z))
    s2 = sub.verts.new((hw * 0.72, 0.0, sh_z))
    s3 = sub.verts.new((0.0, ht * 0.78, sh_z))
    apex = sub.verts.new((0.0, 0.0, float(length)))
    sub.faces.new([v3, v2, v1, v0])
    for a0, a1, b1, b0 in ((v0, v1, s1, s0), (v1, v2, s2, s1), (v2, v3, s3, s2), (v3, v0, s0, s3)):
        sub.faces.new([a0, a1, b1, b0])
    for t0, t1 in ((s0, s1), (s1, s2), (s2, s3), (s3, s0)):
        sub.faces.new([t0, t1, apex])
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_faceted_gem(bm, rx: float, ry: float, rz: float, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 3):
    sub = bmesh.new()
    bmesh.ops.create_icosphere(sub, subdivisions=1, radius=1.0)
    bmesh.ops.scale(sub, vec=(float(rx), float(ry), float(rz)), verts=sub.verts)
    _sharp_merge_sub_bm(bm, sub, mat_idx=mat_idx, rot_deg=rot_deg, loc=loc)


def _sharp_add_curved_shell(bm, width: float, height: float, curve_depth: float, thickness: float, segs: int = 5, taper_bottom: float = 0.65, loc=(0.0, 0.0, 0.0), rot_deg=(0.0, 0.0, 0.0), mat_idx: int = 0):
    half_segs = max(1, int(segs) // 2)
    seg_w = float(width) / max(1, int(segs))
    for idx in range(-half_segs, half_segs + 1):
        u = float(idx) / max(1, half_segs)
        px = idx * (seg_w * 0.92)
        py = -float(curve_depth) * (1.0 - u * u * 0.85)
        yaw = u * 26.0
        h_local = float(height) * (1.0 - abs(u) * (1.0 - float(taper_bottom)) * 0.35)
        _sharp_add_box(bm, (seg_w * 1.05, thickness, h_local), (loc[0] + px, loc[1] + py, loc[2]), (rot_deg[0], rot_deg[1], rot_deg[2] + yaw), bevel_ratio=0.14, mat_idx=mat_idx)


def _sharp_rot_mat9_to_euler_deg(m9) -> list:
    r00, r01, r02, r10, r11, r12, _r20, _r21, r22 = [float(v) for v in m9]
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


def _sharp_build_default_custom_bm(bm):
    # Default multi-slot stylized blade/crest artifact when custom_bpy_code is empty
    _sharp_add_cylinder(bm, 0.068, 0.062, 0.72, segs=10, loc=(0.0, 0.0, -0.02), mat_idx=2)
    _sharp_add_cylinder(bm, 0.11, 0.08, 0.11, segs=8, loc=(0.0, 0.0, -0.42), mat_idx=1)
    _sharp_add_faceted_gem(bm, 0.08, 0.08, 0.10, loc=(0.0, 0.0, -0.52), mat_idx=3)
    _sharp_add_box(bm, (0.68, 0.16, 0.14), (0.0, 0.0, 0.36), bevel_ratio=0.18, mat_idx=1)
    _sharp_add_faceted_gem(bm, 0.09, 0.11, 0.09, loc=(0.0, 0.0, 0.36), mat_idx=3)
    _sharp_add_tapered_blade(bm, width=0.28, thickness=0.11, length=2.45, tip_len=0.48, loc=(0.0, 0.0, 0.42), mat_idx=0)


def _sharp_join_meshes(*objs):
    """Deterministically merge MESH objects/meshes via bmesh without bpy.ops UI context."""
    flat_items = []
    for item in objs:
        if item is None:
            continue
        if isinstance(item, (list, tuple, set)):
            flat_items.extend(item)
        else:
            flat_items.append(item)

    candidates = []
    seen_ptrs = set()
    for item in flat_items:
        if item is None:
            continue
        if isinstance(item, bpy.types.Object):
            if item.type != "MESH" or item.data is None:
                continue
            ptr = item.as_pointer()
            if ptr not in seen_ptrs:
                seen_ptrs.add(ptr)
                candidates.append((item, True))
        elif isinstance(item, bpy.types.Mesh):
            ptr = item.as_pointer()
            if ptr not in seen_ptrs:
                seen_ptrs.add(ptr)
                candidates.append((item, False))

    if not candidates:
        return None

    first_item, first_is_obj = candidates[0]
    if first_is_obj:
        target_obj = first_item
    else:
        target_obj = bpy.data.objects.new(first_item.name + "_Obj", first_item)
        bpy.context.collection.objects.link(target_obj)

    if len(candidates) == 1:
        return target_obj

    bpy.context.view_layer.update()
    if target_obj.data.users > 1:
        target_obj.data = target_obj.data.copy()
    target_mesh = target_obj.data
    try:
        target_inv = target_obj.matrix_world.inverted()
    except ValueError:
        target_inv = Matrix.Identity(4)

    mat_to_idx = {{}}
    for idx, mat in enumerate(target_mesh.materials):
        if mat is not None and mat.name not in mat_to_idx:
            mat_to_idx[mat.name] = idx

    target_bm = bmesh.new()
    target_bm.from_mesh(target_mesh)
    target_bm.verts.ensure_lookup_table()
    target_bm.edges.ensure_lookup_table()
    target_bm.faces.ensure_lookup_table()

    objs_to_remove = []
    for src_item, is_obj in candidates[1:]:
        if is_obj:
            src_obj = src_item
            src_mesh = src_obj.data
            rel_mat = target_inv @ src_obj.matrix_world
            objs_to_remove.append(src_obj)
        else:
            src_obj = None
            src_mesh = src_item
            rel_mat = Matrix.Identity(4)

        local_mat_map = {{}}
        for src_idx, src_mat in enumerate(src_mesh.materials):
            if src_mat is None:
                continue
            if src_mat.name not in mat_to_idx:
                target_mesh.materials.append(src_mat)
                mat_to_idx[src_mat.name] = len(target_mesh.materials) - 1
            local_mat_map[src_idx] = mat_to_idx[src_mat.name]

        src_bm = bmesh.new()
        src_bm.from_mesh(src_mesh)
        bmesh.ops.transform(src_bm, matrix=rel_mat, verts=src_bm.verts)
        if rel_mat.determinant() < 0.0:
            bmesh.ops.reverse_faces(src_bm, faces=src_bm.faces)
        src_bm.normal_update()
        src_bm.verts.index_update()

        uv_pairs = []
        for src_uv in src_bm.loops.layers.uv:
            dst_uv = target_bm.loops.layers.uv.get(src_uv.name)
            if dst_uv is None:
                if len(src_bm.loops.layers.uv) == 1 and len(target_bm.loops.layers.uv) == 1:
                    dst_uv = target_bm.loops.layers.uv.active
                else:
                    dst_uv = target_bm.loops.layers.uv.new(src_uv.name)
            uv_pairs.append((src_uv, dst_uv))

        vmap = []
        for v in src_bm.verts:
            nv = target_bm.verts.new(v.co)
            nv.normal = v.normal
            vmap.append(nv)

        for f in src_bm.faces:
            try:
                nf = target_bm.faces.new([vmap[v.index] for v in f.verts])
            except ValueError:
                continue
            nf.material_index = local_mat_map.get(f.material_index, 0)
            nf.smooth = f.smooth
            nf.normal = f.normal
            for src_uv, dst_uv in uv_pairs:
                for src_loop, dst_loop in zip(f.loops, nf.loops):
                    dst_loop[dst_uv].uv = src_loop[src_uv].uv.copy()

        for e in src_bm.edges:
            ev0 = vmap[e.verts[0].index]
            ev1 = vmap[e.verts[1].index]
            ne = target_bm.edges.get((ev0, ev1)) or target_bm.edges.new((ev0, ev1))
            ne.smooth = e.smooth
            ne.seam = e.seam

        src_bm.free()

    target_bm.normal_update()
    target_bm.to_mesh(target_mesh)
    target_bm.free()
    target_mesh.update()

    for m_obj in objs_to_remove:
        for child in list(m_obj.children):
            cw = child.matrix_world.copy()
            child.parent = target_obj
            child.matrix_parent_inverse = Matrix.Identity(4)
            child.matrix_world = cw
        old_mesh = m_obj.data
        bpy.data.objects.remove(m_obj, do_unlink=True)
        if old_mesh is not None and old_mesh.users == 0 and old_mesh != target_mesh:
            bpy.data.meshes.remove(old_mesh)

    bpy.context.view_layer.update()
    try:
        bpy.context.view_layer.objects.active = target_obj
        target_obj.select_set(True)
    except Exception:
        pass
    return target_obj


def _run_sharp_custom_bmesh_pipeline():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "NONE"
    scene.unit_settings.scale_length = 1.0

    out_dir = Path({json.dumps(out_dir.as_posix())})
    out_dir.mkdir(parents=True, exist_ok=True)
    asset_name = {json.dumps(safe_asset)}
    asset_style = {json.dumps(style_key)}
    texture_style = {json.dumps(tex_key)}
    attach_mode_str = {json.dumps(norm_attach_mode)}
    slot_name = {json.dumps(slot_key)}
    target_limb = {json.dumps(target_limb)}
    target_limb_att = {json.dumps(target_limb_att)}
    default_item_att = {json.dumps(default_item_att)}

    mats_by_name, mat_list = _sharp_create_styled_materials()
    user_code = {json.dumps(custom_bpy_code)}

    bm = bmesh.new()
    exec_ns = {{
        "__name__": "__sharp_custom_bmesh__",
        "bpy": bpy,
        "bmesh": bmesh,
        "math": math,
        "Vector": Vector,
        "Matrix": Matrix,
        "Euler": Euler,
        "ASSET_NAME": asset_name,
        "ASSET_STYLE": asset_style,
        "TEXTURE_STYLE": texture_style,
        "ATTACH_MODE": attach_mode_str,
        "SLOT": slot_name,
        "PRIMARY_RGBA": {repr(p_rgba)},
        "SECONDARY_RGBA": {repr(s_rgba)},
        "ACCENT_RGBA": {repr(a_rgba)},
        "SHARP_MATERIALS": mats_by_name,
        "SHARP_MAT_LIST": mat_list,
        "PRIMARY_MAT": mats_by_name["PrimaryMetal"],
        "TRIM_MAT": mats_by_name["TrimAccent"],
        "LEATHER_MAT": mats_by_name["LeatherGrip"],
        "CORE_MAT": mats_by_name["CoreEmblem"],
        "bm": bm,
        "merge_sub_bm": _sharp_merge_sub_bm,
        "add_box": _sharp_add_box,
        "add_cylinder": _sharp_add_cylinder,
        "add_sphere": _sharp_add_sphere,
        "add_tapered_blade": _sharp_add_tapered_blade,
        "add_faceted_gem": _sharp_add_faceted_gem,
        "add_curved_shell": _sharp_add_curved_shell,
        "join_meshes": _sharp_join_meshes,
    }}

    if user_code.strip():
        exec(compile(user_code, "<custom_bpy_code>", "exec"), exec_ns, exec_ns)
    else:
        _sharp_build_default_custom_bm(bm)

    mesh_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not mesh_objs:
        if len(bm.verts) == 0:
            raise RuntimeError("custom_bpy_code produced no MESH objects and bm has 0 vertices.")
        mesh_data = bpy.data.meshes.new(asset_name + "_Mesh")
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(mesh_data)
        asset_obj = bpy.data.objects.new(asset_name, mesh_data)
        bpy.context.collection.objects.link(asset_obj)
        for m in mat_list:
            mesh_data.materials.append(m)
        mesh_objs = [asset_obj]
    bm.free()

    bpy.context.view_layer.update()
    saved_empty_worlds = [(e, e.matrix_world.copy()) for e in bpy.context.scene.objects if e.type == "EMPTY"]
    for m_obj in mesh_objs:
        if not m_obj.data.materials:
            for m in mat_list:
                m_obj.data.materials.append(m)

    asset_obj = mesh_objs[0]
    if len(mesh_objs) > 1:
        asset_obj = _sharp_join_meshes(*mesh_objs)

    asset_obj.name = asset_name
    asset_obj.data.name = asset_name + "_Mesh"
    bpy.ops.object.select_all(action="DESELECT")
    asset_obj.select_set(True)
    bpy.context.view_layer.objects.active = asset_obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.context.view_layer.update()
    for emp_obj, w_mat in saved_empty_worlds:
        if emp_obj.parent != asset_obj:
            emp_obj.parent = asset_obj
            emp_obj.matrix_parent_inverse = Matrix.Identity(4)
        emp_obj.matrix_world = w_mat

    existing_mat_names = {{m.name for m in asset_obj.data.materials if m is not None}}
    for m in mat_list:
        if m.name not in existing_mat_names:
            asset_obj.data.materials.append(m)

    max_mat_idx = max(0, len(asset_obj.data.materials) - 1)
    for poly in asset_obj.data.polygons:
        if poly.material_index < 0 or poly.material_index > max_mat_idx:
            poly.material_index = 0
        if {repr(flat_shading)}:
            poly.use_smooth = False

    # Audit & recalculate normals
    bm_audit = bmesh.new()
    bm_audit.from_mesh(asset_obj.data)
    bmesh.ops.recalc_face_normals(bm_audit, faces=bm_audit.faces)
    non_manifold_edges = sum(1 for e in bm_audit.edges if not e.is_manifold)
    loose_vertices = sum(1 for v in bm_audit.verts if len(v.link_edges) == 0)
    tri_count = sum(max(1, len(f.verts) - 2) for f in bm_audit.faces)
    vert_count = len(bm_audit.verts)
    poly_count = len(bm_audit.faces)
    bm_audit.to_mesh(asset_obj.data)
    bm_audit.free()
    asset_obj.data.update()

    if tri_count <= 0:
        raise RuntimeError("Asset mesh has 0 triangles after compilation.")

    # Smart-UV fallback if UVs missing
    uv_method = "existing"
    if not asset_obj.data.uv_layers:
        asset_obj.data.uv_layers.new(name="UVMap")
        try:
            bpy.ops.object.select_all(action="DESELECT")
            asset_obj.select_set(True)
            bpy.context.view_layer.objects.active = asset_obj
            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
            bpy.ops.object.mode_set(mode="OBJECT")
            uv_method = "smart_project"
        except Exception:
            if bpy.context.mode != "OBJECT":
                bpy.ops.object.mode_set(mode="OBJECT")
            uv_data = asset_obj.data.uv_layers[0].data
            for poly in asset_obj.data.polygons:
                nrm = poly.normal
                ax, ay, az = abs(float(nrm.x)), abs(float(nrm.y)), abs(float(nrm.z))
                for loop_idx in poly.loop_indices:
                    v_co = asset_obj.data.vertices[asset_obj.data.loops[loop_idx].vertex_index].co
                    if az >= ax and az >= ay:
                        uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.y))
                    elif ay >= ax:
                        uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.x), 0.5 + 0.25 * float(v_co.z))
                    else:
                        uv_data[loop_idx].uv = (0.5 + 0.25 * float(v_co.y), 0.5 + 0.25 * float(v_co.z))
            uv_method = "triplanar_fallback"

    # Collect or create socket empties for _attachments.json
    socket_empties = [o for o in bpy.context.scene.objects if o.type == "EMPTY"]
    if not socket_empties:
        emp = bpy.data.objects.new(default_item_att, None)
        emp.empty_display_type = "PLAIN_AXES"
        emp.empty_display_size = 0.25
        bpy.context.collection.objects.link(emp)
        emp.parent = asset_obj
        emp.matrix_parent_inverse = Matrix.Identity(4)
        emp["roblox_attachment_role"] = "primary"
        emp["roblox_target_limb"] = target_limb
        emp["roblox_target_limb_attachment"] = target_limb_att
        socket_empties = [emp]

    bpy.context.view_layer.update()
    prop_world_inv = asset_obj.matrix_world.inverted()
    attachments_json = []
    for idx, emp in enumerate(socket_empties):
        rel_mat = prop_world_inv @ emp.matrix_world
        pos_rbx, rot_mat9_rbx = matrix_to_roblox_cf(rel_mat, unit_scale=1.0)
        rot_deg_rbx = _sharp_rot_mat9_to_euler_deg(rot_mat9_rbx)
        attachments_json.append({{
            "name": emp.name,
            "role": str(emp.get("roblox_attachment_role", "primary" if idx == 0 else "secondary")),
            "target_limb": emp.get("roblox_target_limb") or target_limb,
            "target_limb_attachment": emp.get("roblox_target_limb_attachment") or target_limb_att,
            "pos": [round(float(v), 5) for v in pos_rbx],
            "rot_deg": rot_deg_rbx,
            "rot_matrix": [round(float(v), 6) for v in rot_mat9_rbx],
            "cframe": [round(float(v), 5) for v in (list(pos_rbx) + list(rot_mat9_rbx))],
        }})

    bbox_local = [Vector(corner) for corner in asset_obj.bound_box]
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
    preview_path = Path({json.dumps(preview_file.as_posix())})
    generic_preview_path = Path({json.dumps(generic_preview_file.as_posix())})

    # Export FBX & GLB before adding render Camera/Lights
    if {repr(bool(export_fbx))}:
        bpy.ops.object.select_all(action="DESELECT")
        asset_obj.select_set(True)
        for emp in socket_empties:
            emp.select_set(True)
        bpy.context.view_layer.objects.active = asset_obj
        bpy.ops.export_scene.fbx(
            filepath=str(fbx_path),
            use_selection=True,
            object_types={{"MESH", "EMPTY"}},
            apply_scale_options="FBX_SCALE_ALL",
            axis_forward="-Z",
            axis_up="Y",
            add_leaf_bones=False,
            bake_anim=False,
        )

    if {repr(bool(export_glb))}:
        bpy.ops.object.select_all(action="DESELECT")
        asset_obj.select_set(True)
        for emp in socket_empties:
            emp.select_set(True)
        bpy.context.view_layer.objects.active = asset_obj
        bpy.ops.export_scene.gltf(
            filepath=str(glb_path),
            use_selection=True,
            export_format="GLB",
            export_yup=True,
        )

    # Orthographic preview render
    preview_written = False
    if {repr(bool(render_preview))}:
        world = bpy.data.worlds.new("SharpPreviewWorld")
        world.use_nodes = True
        bg_node = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg_node:
            bg_node.inputs[0].default_value = (0.11, 0.13, 0.18, 1.0)
            bg_node.inputs[1].default_value = 1.1
        scene.world = world

        bbox_world = [asset_obj.matrix_world @ Vector(c) for c in asset_obj.bound_box]
        wxs = [c.x for c in bbox_world]
        wys = [c.y for c in bbox_world]
        wzs = [c.z for c in bbox_world]
        center = Vector(((min(wxs) + max(wxs)) * 0.5, (min(wys) + max(wys)) * 0.5, (min(wzs) + max(wzs)) * 0.5))
        max_span = max(max(wxs) - min(wxs), max(wys) - min(wys), max(wzs) - min(wzs), 0.5)

        cam_data = bpy.data.cameras.new("SharpPreviewCam")
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = max(0.6, max_span * 1.45)
        cam_data.clip_start = 0.05
        cam_data.clip_end = max(100.0, max_span * 20.0)
        cam_obj = bpy.data.objects.new("SharpPreviewCam", cam_data)
        bpy.context.collection.objects.link(cam_obj)
        view_dir = Vector((1.0, -1.25, 0.72)).normalized()
        cam_obj.location = center + view_dir * (max_span * 3.0 + 2.0)
        cam_obj.rotation_euler = (center - cam_obj.location).to_track_quat("-Z", "Y").to_euler()
        scene.camera = cam_obj

        key_light_data = bpy.data.lights.new("SharpKeySun", type="SUN")
        key_light_data.energy = 3.2
        key_light = bpy.data.objects.new("SharpKeySun", key_light_data)
        bpy.context.collection.objects.link(key_light)
        key_light.rotation_euler = (math.radians(42.0), math.radians(15.0), math.radians(-35.0))

        rim_light_data = bpy.data.lights.new("SharpRimSun", type="SUN")
        rim_light_data.energy = 1.6
        rim_light = bpy.data.objects.new("SharpRimSun", rim_light_data)
        bpy.context.collection.objects.link(rim_light)
        rim_light.rotation_euler = (math.radians(55.0), math.radians(-20.0), math.radians(140.0))

        avail_engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
        for eng_cand in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH", "CYCLES"):
            if eng_cand in avail_engines:
                scene.render.engine = eng_cand
                break
        scene.render.resolution_x = 512
        scene.render.resolution_y = 512
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(preview_path)
        bpy.ops.render.render(write_still=True)
        if preview_path.is_file():
            shutil.copy2(preview_path, generic_preview_path)
            preview_written = True

    mat_slots = [m.name for m in asset_obj.data.materials if m is not None]
    within_budget = bool(tri_count <= 10000)
    is_manifold = bool(non_manifold_edges == 0)
    audit_warnings = []
    if not within_budget:
        audit_warnings.append(f"Triangle count {{tri_count}} exceeds 10k Roblox MeshPart budget.")
    if not is_manifold:
        audit_warnings.append(f"Detected {{non_manifold_edges}} non-manifold edge(s).")
    if loose_vertices > 0:
        audit_warnings.append(f"Detected {{loose_vertices}} loose vertex(ices).")

    mesh_stats = {{
        "triangle_count": int(tri_count),
        "vertex_count": int(vert_count),
        "polygon_count": int(poly_count),
        "non_manifold_edges": int(non_manifold_edges),
        "loose_vertices": int(loose_vertices),
        "material_slots": mat_slots,
        "material_count": len(mat_slots),
        "uv_present": bool(asset_obj.data.uv_layers),
        "uv_method": uv_method,
        "within_roblox_10k_budget": within_budget,
        "is_manifold": is_manifold,
        "warnings": audit_warnings,
    }}

    sidecar_payload = {{
        "schema": "sharp.attachment_sidecar.v1",
        "prop_name": asset_name,
        "prop_kind": "custom_bmesh",
        "asset_style": asset_style,
        "texture_style": texture_style,
        "attachment_mode": {json.dumps(sidecar_att_mode)},
        "attach_mode": attach_mode_str,
        "slot": slot_name,
        "rig_height_studs": 5.0,
        "prop_dimensions_studs": dims_studs,
        "target_limb": target_limb,
        "target_limb_attachment": target_limb_att,
        "mesh_stats": mesh_stats,
        "fbx_path": str(fbx_path) if {repr(bool(export_fbx))} else None,
        "glb_path": str(glb_path) if {repr(bool(export_glb))} else None,
        "preview_path": str(preview_path) if preview_written else None,
        "attachments": attachments_json,
    }}
    sidecar_path.write_text(json.dumps(sidecar_payload, indent=2), encoding="utf-8")
    print("SHARP_CUSTOM_BMESH_OK", json.dumps({{
        "sidecar": str(sidecar_path),
        "triangles": int(tri_count),
        "non_manifold_edges": int(non_manifold_edges),
        "preview_written": preview_written,
    }}))
    return sidecar_payload


_run_sharp_custom_bmesh_pipeline()
'''

        result: Dict[str, Any] = {
            "ok": True,
            "pipeline": "blender_custom_bmesh_asset",
            "asset_name": safe_asset,
            "asset_style": style_key,
            "texture_style": tex_key,
            "attach_mode": norm_attach_mode,
            "slot": slot_key,
            "target_limb": target_limb,
            "target_limb_attachment": target_limb_att,
            "primary_hex": p_hex,
            "secondary_hex": s_hex,
            "accent_hex": a_hex,
            "output_dir": str(out_dir),
            "sidecar_path": str(sidecar_file),
            "fbx_path": str(fbx_file) if export_fbx else None,
            "glb_path": str(glb_file) if export_glb else None,
            "preview_path": str(preview_file) if render_preview else None,
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
                sidecar_obj = json.loads(sidecar_file.read_text(encoding="utf-8"))
                ms = sidecar_obj.get("mesh_stats") or {}
                result["sidecar"] = sidecar_obj
                result["mesh_stats"] = ms
                result["audit"] = {
                    "passed": bool(ms.get("within_roblox_10k_budget")) and int(ms.get("triangle_count", 0)) > 0,
                    "within_roblox_10k_budget": bool(ms.get("within_roblox_10k_budget")),
                    "is_manifold": bool(ms.get("is_manifold")),
                    "triangle_count": int(ms.get("triangle_count", 0)),
                    "non_manifold_edges": int(ms.get("non_manifold_edges", 0)),
                    "uv_present": bool(ms.get("uv_present")),
                    "material_slots": ms.get("material_slots", []),
                    "warnings": ms.get("warnings", []),
                }
                reg_paths = [p for p in (fbx_file, glb_file, sidecar_file, preview_file) if p.is_file()]
                result["registered_asset_keys"] = self._register_outputs_if_present(
                    project_library=project_library,
                    asset_name=safe_asset,
                    category="mesh",
                    paths=reg_paths,
                    description=f"Blender custom bmesh {style_key} asset ({slot_key})",
                    tags=["blender", "custom_bmesh", style_key, tex_key, slot_key],
                )
        return result

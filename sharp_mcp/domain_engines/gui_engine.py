"""GUI, 9-Slice, Atlas & StyleSheet Domain Engine (`roblox-gui`).

Embeds:
- `slice_and_atlas_helper.py` (background strip, 1-2px RGB alpha bleed, auto SliceCenter, 4px atlas packing)
- `gui_map_spec.py` (canonical 11-layer DisplayOrder & ScreenInsets specification)
- `generate_rbxmx_gui.py` (offline .rbxmx GUI package serializer)
- `ui_theme_and_components.luau` (StyleSheet / StyleRule token system & responsive rules)
- `build_standard_game_gui.luau` (live 11-layer StarterGui HUD/Modals/Shop/Dialog/Tooltip/Toast builder)
- `audit_gui.luau` (safe-zone, >=44px touch target, CanvasGroup VRAM, and StyleRule auditor)
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from .design_engine import DesignEngine


class GuiDomainEngine:
    def __init__(self, skills_dir: Path, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir
        self.skill_path = self._resolve_skill_path()

    def _resolve_skill_path(self) -> Path:
        p = self.skills_dir / "roblox-gui"
        if p.is_dir():
            return p
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / "roblox-gui"
        if bundled.is_dir():
            return bundled
        if self.archive_dir:
            return self.archive_dir / "02_roblox_gui" / "skill"
        return p

    def _read_script(self, script_name: str) -> str:
        return (self.skill_path / "scripts" / script_name).read_text(encoding="utf-8")

    def _load_py_module(self, script_name: str, mod_alias: str) -> Any:
        py_path = self.skill_path / "scripts" / script_name
        scripts_dir = str(py_path.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location(mod_alias, py_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_alias] = mod
        prev_dwb = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = prev_dwb
        return mod

    def process_slice_and_atlas(
        self,
        output_dir: str,
        panel_source_path: Optional[str] = None,
        button_source_path: Optional[str] = None,
        icon_source_paths: Optional[List[str]] = None,
        alpha_bleed_px: int = 2,
        gutter_px: int = 4,
        export_rbxmx: bool = True,
        grid_rows: Optional[int] = None,
        grid_cols: Optional[int] = None,
        icon_names: Optional[List[str]] = None,
        cell_size: Optional[int] = None,
        max_dim: int = 512,
        skip_empty_cells: bool = False,
    ) -> Dict[str, Any]:
        """Processes 9-slice panels/buttons and packs arbitrary RxC icon atlases with RGB alpha bleed."""
        helper = self._load_py_module("slice_and_atlas_helper.py", "sharp_slice_helper")
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        safe_max_dim = max(16, min(int(max_dim), 1024))

        staged_files: List[Path] = []
        results: Dict[str, Any] = {"ok": True, "output_dir": str(out_path), "assets": {}}

        if panel_source_path and Path(panel_source_path).is_file():
            p_out = out_path / "panel_9slice.png"
            meta = helper.prepare_nine_slice_png(
                input_path=str(Path(panel_source_path).resolve()),
                output_path=str(p_out),
                max_dim=safe_max_dim,
                bleed_px=max(1, alpha_bleed_px),
            )
            results["assets"]["panel_9slice"] = meta
            results["panel_9slice"] = meta
            staged_files.append(p_out)

        if button_source_path and Path(button_source_path).is_file():
            b_out = out_path / "button_9slice.png"
            meta = helper.prepare_nine_slice_png(
                input_path=str(Path(button_source_path).resolve()),
                output_path=str(b_out),
                max_dim=safe_max_dim,
                bleed_px=max(1, alpha_bleed_px),
            )
            results["assets"]["button_9slice"] = meta
            results["button_9slice"] = meta
            staged_files.append(b_out)

        valid_icons = [str(Path(p).resolve()) for p in (icon_source_paths or []) if Path(p).is_file()]
        if valid_icons:
            a_out = out_path / "icons_atlas.png"
            stem_l = Path(valid_icons[0]).stem.lower()
            rxc_match = re.search(r"(\d+)x(\d+)", stem_l)
            is_grid_sheet = len(valid_icons) == 1 and (
                grid_rows is not None
                or grid_cols is not None
                or rxc_match is not None
                or any(tag in stem_l for tag in ("grid", "sheet"))
            )
            if is_grid_sheet:
                det_rows = int(rxc_match.group(1)) if rxc_match else 2
                det_cols = int(rxc_match.group(2)) if rxc_match else 2
                rows = max(1, int(grid_rows if grid_rows is not None else det_rows))
                cols = max(1, int(grid_cols if grid_cols is not None else det_cols))
                if icon_names is not None:
                    resolved_names: Optional[List[str]] = list(icon_names)
                elif rows == 2 and cols == 2:
                    resolved_names = ["coin", "gem", "combat", "chest"]
                else:
                    resolved_names = None
                eff_cell = int(cell_size) if cell_size is not None else 256
                atlas_meta = helper.split_grid_and_pack_atlas(
                    input_path=valid_icons[0],
                    output_path=str(a_out),
                    rows=rows,
                    cols=cols,
                    names=resolved_names,
                    cell_size=eff_cell,
                    gutter=max(4, gutter_px),
                    bleed_px=max(1, alpha_bleed_px),
                    auto_fit_cell_size=True,
                    tight_trim=True,
                    skip_empty_cells=skip_empty_cells,
                )
            else:
                icon_dict: Dict[str, str | Path] = {}
                for idx, p_str in enumerate(valid_icons):
                    if icon_names and idx < len(icon_names) and icon_names[idx]:
                        key = str(icon_names[idx])
                    else:
                        stem = Path(p_str).stem
                        key = f"{stem}_{idx}" if stem in icon_dict else stem
                    icon_dict[key] = p_str
                atlas_meta = helper.pack_icon_atlas(
                    icon_paths=icon_dict,
                    output_path=str(a_out),
                    cell_size=int(cell_size) if cell_size is not None else 128,
                    gutter=max(4, gutter_px),
                    bleed_px=max(1, alpha_bleed_px),
                    key_background=True,
                    auto_fit_cell_size=True,
                )
            results["assets"]["icons_atlas"] = atlas_meta
            results["icon_atlas"] = atlas_meta
            staged_files.append(a_out)

        if export_rbxmx:
            rbxmx_gen = self._load_py_module("generate_rbxmx_gui.py", "sharp_rbxmx_gui")
            rbxmx_file = out_path / "SharpStandardGameGui.rbxmx"
            rbxmx_gen.generate_standard_gui_rbxmx(str(rbxmx_file))
            results["rbxmx_path"] = str(rbxmx_file)

        results["staged_file_paths"] = [str(p) for p in staged_files]
        return results

    def get_gui_map_spec_summary(self) -> Dict[str, Any]:
        spec_mod = self._load_py_module("gui_map_spec.py", "sharp_gui_map_spec")
        raw_layers = getattr(spec_mod, "STANDARD_LAYERS", getattr(spec_mod, "STANDARD_GUI_LAYERS", ()))
        layers = [asdict(item) if is_dataclass(item) else item for item in raw_layers]
        return {
            "layer_count": len(layers),
            "layers": layers,
        }

    def compile_gui_build_luau(
        self,
        panel_asset_id: str = "",
        button_asset_id: str = "",
        atlas_asset_id: str = "",
        run_audit_after: bool = True,
        design_system: Optional[Dict[str, Any] | str] = None,
    ) -> str:
        theme_src = self._read_script("ui_theme_and_components.luau")
        builder_src = self._read_script("build_standard_game_gui.luau")
        audit_src = self._read_script("audit_gui.luau")

        asset_overrides: Dict[str, str] = {}
        luau_override_entries: List[str] = []
        if panel_asset_id:
            asset_overrides["Panel9SliceId"] = panel_asset_id
            luau_override_entries.append(f"\tPanel9SliceId = {json.dumps(panel_asset_id)},")
        if button_asset_id:
            asset_overrides["Button9SliceId"] = button_asset_id
            luau_override_entries.append(f"\tButton9SliceId = {json.dumps(button_asset_id)},")
        if atlas_asset_id:
            asset_overrides["IconAtlasId"] = atlas_asset_id
            luau_override_entries.append(f"\tIconAtlasId = {json.dumps(atlas_asset_id)},")

        if luau_override_entries:
            override_block = "{\n" + "\n".join(luau_override_entries) + "\n}"
            assets_pattern = re.compile(r"UIKit\.Assets\s*=\s*\{\}\s*::\s*AssetOverrides")
            if assets_pattern.search(theme_src):
                theme_src = assets_pattern.sub(
                    lambda _: f"UIKit.Assets = {override_block} :: AssetOverrides",
                    theme_src,
                    count=1,
                )
            else:
                theme_src = theme_src.replace(
                    "return UIKit",
                    f"UIKit.SetAssets({override_block})\nreturn UIKit",
                    1,
                )

        if design_system:
            design_engine = DesignEngine(self.skills_dir, self.archive_dir)
            if isinstance(design_system, str):
                stripped = design_system.strip()
                if stripped.startswith("{"):
                    ds_obj: Dict[str, Any] = json.loads(stripped)
                else:
                    ds_obj = design_engine.generate_design_system(
                        game_title="Custom Experience",
                        genre=stripped,
                    )
            else:
                ds_obj = design_system
            theme_block = design_engine.compile_theme_luau(ds_obj, module_mode=False).replace("]========]", "]=======]")
            idx = theme_src.rfind("return UIKit")
            if idx != -1:
                theme_src = (
                    theme_src[:idx]
                    + f"\n{theme_block}\nUIKit.ApplyDesignSystem(DesignTheme)\n"
                    + theme_src[idx:]
                )
            else:
                theme_src = theme_src + f"\n{theme_block}\nUIKit.ApplyDesignSystem(DesignTheme)\n"

        assets_json = json.dumps(asset_overrides)

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpGuiBuild", "Sharp MCP: Build 11-Layer Game GUI & StyleSheet")
local ok, resOrErr = xpcall(function()
	local oldMod = ReplicatedStorage:FindFirstChild("UIThemeAndComponents")
	if oldMod then oldMod:Destroy() end

	local themeMod = Instance.new("ModuleScript")
	themeMod.Name = "UIThemeAndComponents"
	themeMod.Source = [========[{theme_src}]========]
	themeMod.Parent = ReplicatedStorage

	local customAssets = HttpService:JSONDecode({json.dumps(assets_json)})
	if next(customAssets) ~= nil then
		_G.ROBLOX_GUI_ASSETS = customAssets
	end

	local builderFn = function()
{builder_src}
	end
	local buildRes = builderFn()
	_G.ROBLOX_GUI_ASSETS = nil

	local auditRes = nil
	if {"true" if run_audit_after else "false"} then
		local StarterGui = game:GetService("StarterGui")
		local mainHud = StarterGui:FindFirstChild("MainHudGui")
		local rail = mainHud and mainHud:FindFirstChild("SideRail")
		local t0 = os.clock()
		while rail and rail.AbsoluteSize.X < 10 and (os.clock() - t0) < 1.0 do
			task.wait(0.05)
		end
		task.wait(0.05)
		local auditFn = function()
{audit_src}
		end
		local rawAudit = auditFn()
		if type(rawAudit) == "string" then
			local okDec, decoded = pcall(function() return HttpService:JSONDecode(rawAudit) end)
			auditRes = if okDec then decoded else rawAudit
		else
			auditRes = rawAudit
		end
	end

	return {{
		buildResult = buildRes,
		auditReport = auditRes,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    @staticmethod
    def build_inspect_module_op(
        *,
        root_path: Optional[str] = None,
        root_handle: Optional[str] = None,
        target: Optional[str] = None,
        max_depth: int = 5,
        include_props: bool = False,
        include_style_sheets: bool = True,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.inspect module op payload."""
        args: Dict[str, Any] = {
            "maxDepth": max(0, min(12, int(max_depth))),
            "includeProps": bool(include_props),
            "includeStyleSheets": bool(include_style_sheets),
        }
        if root_path:
            args["rootPath"] = root_path
        if root_handle:
            args["rootHandle"] = root_handle
        if target:
            args["target"] = target
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "inspect",
            "kind": "read",
            "args": args,
        }

    @staticmethod
    def build_patch_module_op(
        *,
        patches: Optional[List[Dict[str, Any]]] = None,
        path: Optional[str] = None,
        sharp_handle: Optional[str] = None,
        set_properties: Optional[Dict[str, Any]] = None,
        reset_properties: Optional[List[str]] = None,
        style_rule_updates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.patch module op payload."""
        args: Dict[str, Any] = {}
        if patches is not None:
            args["patches"] = patches
        if path:
            args["path"] = path
        if sharp_handle:
            args["sharpHandle"] = sharp_handle
        if set_properties is not None:
            args["setProperties"] = set_properties
        if reset_properties is not None:
            args["resetProperties"] = reset_properties
        if style_rule_updates is not None:
            args["styleRuleUpdates"] = style_rule_updates
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "patch",
            "kind": "write",
            "args": args,
        }

    @staticmethod
    def build_device_sim_module_op(
        *,
        action: str = "get_device",
        device_id: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        orientation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.deviceSim module op payload."""
        args: Dict[str, Any] = {"action": action}
        if device_id is not None:
            args["deviceId"] = device_id
        if width is not None:
            args["width"] = int(width)
        if height is not None:
            args["height"] = int(height)
        if orientation is not None:
            args["orientation"] = orientation
        read_actions = {"get_device", "list_devices"}
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "deviceSim",
            "kind": "read" if action in read_actions else "write",
            "args": args,
        }

    @staticmethod
    def compute_visual_diff(
        before_path: str | Path,
        after_path: str | Path,
        diff_out_path: Optional[str | Path] = None,
        threshold: int = 8,
    ) -> Dict[str, Any]:
        """Compare two RGBA screenshots using Pillow + numpy, detect blank frames, and optionally emit a diff image."""
        return compute_visual_diff(
            before_path=before_path,
            after_path=after_path,
            diff_out_path=diff_out_path,
            threshold=threshold,
        )


def compute_visual_diff(
    before_path: str | Path,
    after_path: str | Path,
    diff_out_path: Optional[str | Path] = None,
    threshold: int = 8,
) -> Dict[str, Any]:
    """Compare two images pixel-by-pixel with RGBA alignment, blank detection, and bounding-box delta."""
    p_before = Path(before_path).expanduser()
    p_after = Path(after_path).expanduser()
    if not p_before.is_file():
        return {"ok": False, "error": f"Before image not found: {p_before}"}
    if not p_after.is_file():
        return {"ok": False, "error": f"After image not found: {p_after}"}

    before_bytes = p_before.read_bytes()
    after_bytes = p_after.read_bytes()
    sha_before = hashlib.sha256(before_bytes).hexdigest()
    sha_after = hashlib.sha256(after_bytes).hexdigest()

    img_before = Image.open(p_before).convert("RGBA")
    img_after = Image.open(p_after).convert("RGBA")
    orig_before_size = list(img_before.size)
    orig_after_size = list(img_after.size)
    size_aligned = img_before.size != img_after.size
    if size_aligned:
        img_after = img_after.resize(img_before.size, Image.Resampling.BILINEAR)

    width, height = img_before.size
    arr_before = np.asarray(img_before, dtype=np.int16)
    arr_after = np.asarray(img_after, dtype=np.int16)

    before_is_blank = bool(
        arr_before[:, :, 3].max() == 0
        or float(arr_before[:, :, :3].reshape(-1, 3).std(axis=0).max()) < 1.0
    )
    after_is_blank = bool(
        arr_after[:, :, 3].max() == 0
        or float(arr_after[:, :, :3].reshape(-1, 3).std(axis=0).max()) < 1.0
    )

    abs_diff = np.abs(arr_before - arr_after)
    max_per_pixel = abs_diff.max(axis=2)
    changed_mask = max_per_pixel > int(threshold)

    total_pixels = int(width * height)
    changed_pixels = int(changed_mask.sum())
    changed_ratio = round(changed_pixels / max(1, total_pixels), 6)
    max_channel_delta = int(abs_diff.max()) if total_pixels > 0 else 0
    mean_delta = round(float(abs_diff.mean()), 4) if total_pixels > 0 else 0.0

    diff_bbox: Optional[List[int]] = None
    if changed_pixels > 0:
        ys, xs = np.where(changed_mask)
        diff_bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]

    written_diff_path: Optional[str] = None
    if diff_out_path is not None:
        out_p = Path(diff_out_path).expanduser()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        overlay = (arr_after.astype(np.float32) * 0.35).astype(np.uint8)
        overlay[:, :, 3] = 255
        overlay[changed_mask] = np.array([255, 48, 96, 255], dtype=np.uint8)
        Image.fromarray(overlay, mode="RGBA").save(out_p, format="PNG")
        written_diff_path = str(out_p)

    return {
        "ok": True,
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "width": width,
        "height": height,
        "size_aligned": size_aligned,
        "original_before_size": orig_before_size,
        "original_after_size": orig_after_size,
        "blank_frame_detected": before_is_blank or after_is_blank,
        "before_is_blank": before_is_blank,
        "after_is_blank": after_is_blank,
        "threshold": int(threshold),
        "total_pixels": total_pixels,
        "changed_pixels": changed_pixels,
        "changed_ratio": changed_ratio,
        "max_channel_delta": max_channel_delta,
        "mean_delta": mean_delta,
        "diff_bbox": diff_bbox,
        "diff_image_path": written_diff_path,
    }


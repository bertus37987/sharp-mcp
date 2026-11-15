"""Terrain & Atmosphere Domain Engine (`roblox-terrain-atmosphere`).

Embeds:
- `heightmap_generator.py` (offline heightmap.png + colormap.png with exact Roblox palette RGBs)
- `terrain_chunked_builder.luau` (chunked WriteVoxelChannels / WriteVoxels with 6 biomes + FlattenZones)
- `atmosphere_presets.luau` (11 complete lighting/atmosphere/cloud/postfx mood presets)
- `audit_environment.luau` (comprehensive environment & expanded terrain auditor)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class TerrainEnvironmentEngine:
    def __init__(self, skills_dir: Path, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir
        self.skill_path = self._resolve_skill_path()

    def _resolve_skill_path(self) -> Path:
        p = self.skills_dir / "roblox-terrain-atmosphere"
        if p.is_dir():
            return p
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / "roblox-terrain-atmosphere"
        if bundled.is_dir():
            return bundled
        if self.archive_dir:
            return self.archive_dir / "03_roblox_terrain_atmosphere" / "skill"
        return p

    def _read_script(self, script_name: str) -> str:
        return (self.skill_path / "scripts" / script_name).read_text(encoding="utf-8")

    def _load_heightmap_module(self) -> Any:
        py_path = self.skill_path / "scripts" / "heightmap_generator.py"
        spec = importlib.util.spec_from_file_location("sharp_heightmap_generator", py_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def generate_offline_heightmap(
        self,
        output_dir: str,
        size: int = 256,
        seed: int = 42,
        biome: str = "alpine",
        water_level: float = 0.32,
        plateau_radius: float = 0.12,
        plateau_height: float = 0.48,
        bit_depth: str = "both",
        world_height_studs: int = 192,
        flatten_zones: Optional[List[Dict[str, Any]]] = None,
        **_: Any,
    ) -> Dict[str, Any]:
        hm_mod = self._load_heightmap_module()
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        resolved_biome = biome.lower() if biome.lower() in getattr(hm_mod, "BIOME_PROFILES", {"alpine": 1}) else "alpine"
        manifest = hm_mod.generate_terrain_maps(
            out_dir=out_path,
            size=size,
            seed=seed,
            biome=resolved_biome,
            water_level=water_level if 0.0 <= water_level <= 1.0 else 0.32,
            plateau_radius=plateau_radius,
            plateau_height=plateau_height,
            bit_depth=bit_depth,
            world_height_studs=world_height_studs,
        )
        files = manifest.get("files", {})
        hm_path = files.get("heightmap_16bit") or files.get("heightmap_8bit") or ""
        col_path = files.get("colormap") or ""
        return {
            "ok": bool(manifest.get("palette_valid", True)),
            "output_dir": str(out_path),
            "heightmap_path": hm_path,
            "colormap_path": col_path,
            "manifest": manifest,
            "palette_verification": {"ok": bool(manifest.get("palette_valid", True))},
        }

    def compile_terrain_build_luau(
        self,
        min_corner: List[float],
        max_corner: List[float],
        biome: str = "Alpine",
        seed: int = 42,
        base_height: float = 76.0,
        mountain_height: float = 72.0,
        water_level: Optional[float] = 80.0,
        chunk_voxels: int = 32,
        clear_first: bool = True,
        flatten_zones: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        builder_src = self._read_script("terrain_chunked_builder.luau")
        fz_luau_items: List[str] = []
        for z in flatten_zones or []:
            shape = z.get("shape", "Circle")
            cx = float(z.get("x", (min_corner[0] + max_corner[0]) * 0.5))
            cz = float(z.get("z", (min_corner[2] + max_corner[2]) * 0.5))
            th = float(z.get("h", z.get("target_height", base_height + 8.0)))
            r0 = float(z.get("r0", z.get("radius", 36.0)))
            falloff = float(z.get("falloff", 20.0))
            r1 = float(z.get("r1", r0 + falloff))
            half_x = float(z.get("halfX", r0))
            half_z = float(z.get("halfZ", r0))
            blend = float(z.get("blend", falloff))
            mat_name = z.get("material", "Cobblestone")
            fz_luau_items.append(
                f"{{ x = {cx}, z = {cz}, h = {th}, shape = {json.dumps(shape)}, "
                f"r0 = {r0}, r1 = {r1}, halfX = {half_x}, halfZ = {half_z}, blend = {blend}, "
                f"material = Enum.Material.{mat_name} }}"
            )
        fz_table = "{ " + ", ".join(fz_luau_items) + " }"
        wl_expr = "nil" if water_level is None else str(float(water_level))

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")

local TerrainChunkedBuilder = (function()
{builder_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpTerrainBuild", "Sharp MCP: Build Terrain ({biome})")
local ok, resultOrErr = xpcall(function()
	local minVec = Vector3.new({float(min_corner[0])}, {float(min_corner[1])}, {float(min_corner[2])})
	local maxVec = Vector3.new({float(max_corner[0])}, {float(max_corner[1])}, {float(max_corner[2])})
	if {"true" if clear_first else "false"} then
		TerrainChunkedBuilder.ClearRegion(minVec, maxVec)
	end
	return TerrainChunkedBuilder.BuildRegion({{
		min = minVec,
		max = maxVec,
		biome = {json.dumps(biome)},
		seed = {int(seed)},
		baseHeight = {float(base_height)},
		mountainHeight = {float(mountain_height)},
		waterLevel = {wl_expr},
		chunkCellsXZ = {int(chunk_voxels)},
		yieldPerChunk = false,
		flattenZones = {fz_table},
	}})
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
	error(resultOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	buildResult = resultOrErr,
}})
"""

    def compile_environment_apply_luau(
        self,
        preset_name: str = "GoldenSunset",
        overrides: Optional[Dict[str, Any]] = None,
        run_audit_after: bool = True,
    ) -> str:
        presets_src = self._read_script("atmosphere_presets.luau")
        audit_src = self._read_script("audit_environment.luau")
        overrides_json = json.dumps(overrides or {})

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local Lighting = game:GetService("Lighting")
local Workspace = game:GetService("Workspace")

local AtmospherePresets = (function()
{presets_src}
end)()

local runAuditFn = function()
{audit_src}
end

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpEnvironmentApply", "Sharp MCP: Apply Atmosphere ({preset_name})")
local ok, resOrErr = xpcall(function()
	local overridesTbl = HttpService:JSONDecode({json.dumps(overrides_json)})
	local applied = AtmospherePresets.ApplyPreset({json.dumps(preset_name)}, overridesTbl)

	if type(overridesTbl.lighting) == "table" then
		for k, v in pairs(overridesTbl.lighting) do
			pcall(function() (Lighting :: any)[k] = v end)
		end
	end
	if type(overridesTbl.atmosphere) == "table" then
		local atmo = Lighting:FindFirstChildOfClass("Atmosphere")
		if atmo then
			for k, v in pairs(overridesTbl.atmosphere) do
				pcall(function() (atmo :: any)[k] = v end)
			end
		end
	end
	if type(overridesTbl.clouds) == "table" then
		local clouds = Workspace.Terrain:FindFirstChildOfClass("Clouds")
		if clouds then
			for k, v in pairs(overridesTbl.clouds) do
				pcall(function() (clouds :: any)[k] = v end)
			end
		end
	end

	local auditReport = nil
	if {"true" if run_audit_after else "false"} then
		local rawAudit = runAuditFn()
		if type(rawAudit) == "string" then
			local okDec, decoded = pcall(function() return HttpService:JSONDecode(rawAudit) end)
			auditReport = if okDec then decoded else rawAudit
		else
			auditReport = rawAudit
		end
	end
	return {{
		appliedPreset = applied,
		auditReport = auditReport,
		auditSummary = if type(auditReport) == "table" then {{
			status = auditReport.status,
			passCount = auditReport.passCount,
			warningCount = auditReport.warningCount,
			errorCount = auditReport.errorCount,
		}} else nil,
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

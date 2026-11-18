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
import re
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

    @staticmethod
    def _sanitize_material_name(raw: Any, default: str = "Rock") -> str:
        text = str(raw or default).strip()
        if text.startswith("Enum.Material."):
            text = text[len("Enum.Material.") :]
        cleaned = re.sub(r"[^A-Za-z0-9_]", "", text)
        return cleaned or default

    @classmethod
    def _compile_height_layers_luau(cls, layers: List[Dict[str, Any]]) -> str:
        items: List[str] = []
        for layer in layers:
            if not isinstance(layer, dict):
                continue
            ltype = str(layer.get("type") or "").strip().lower()
            if not ltype:
                continue
            fields: List[str] = [f"type = {json.dumps(ltype)}"]
            num_aliases = (
                ("x", ("x",)),
                ("z", ("z",)),
                ("x1", ("x1",)),
                ("z1", ("z1",)),
                ("x2", ("x2",)),
                ("z2", ("z2",)),
                ("radius", ("radius", "r")),
                ("depth", ("depth",)),
                ("height", ("height", "h")),
                ("rimHeight", ("rimHeight", "rim_height")),
                ("rimWidth", ("rimWidth", "rim_width")),
                ("width", ("width",)),
                ("stepHeight", ("stepHeight", "step_height")),
                ("blend", ("blend", "falloff")),
                ("minY", ("minY", "min_y")),
                ("maxY", ("maxY", "max_y")),
                ("waterLevel", ("waterLevel", "water_level")),
            )
            for luau_k, py_keys in num_aliases:
                for pk in py_keys:
                    if layer.get(pk) is not None:
                        fields.append(f"{luau_k} = {float(layer[pk])}")
                        break
            wf = layer.get("waterFill", layer.get("water_fill"))
            if wf is not None:
                fields.append(f"waterFill = {'true' if bool(wf) else 'false'}")
            if layer.get("material"):
                mat_name = cls._sanitize_material_name(layer["material"])
                fields.append(f"material = Enum.Material.{mat_name}")
            pts = layer.get("points")
            if isinstance(pts, list) and pts:
                pt_strs: List[str] = []
                for pt in pts:
                    if isinstance(pt, dict) and pt.get("x") is not None and pt.get("z") is not None:
                        pt_strs.append(f"{{ x = {float(pt['x'])}, z = {float(pt['z'])} }}")
                    elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
                        pt_strs.append(f"{{ x = {float(pt[0])}, z = {float(pt[1])} }}")
                if pt_strs:
                    fields.append("points = { " + ", ".join(pt_strs) + " }")
            items.append("{ " + ", ".join(fields) + " }")
        return "{ " + ", ".join(items) + " }"

    @classmethod
    def _compile_material_rules_luau(cls, rules: List[Dict[str, Any]]) -> str:
        items: List[str] = []
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            mat_raw = rule.get("material")
            if not mat_raw:
                continue
            mat_name = cls._sanitize_material_name(mat_raw)
            fields: List[str] = [f"material = Enum.Material.{mat_name}"]
            num_aliases = (
                ("minY", ("minY", "min_y")),
                ("maxY", ("maxY", "max_y")),
                ("minSlope", ("minSlope", "min_slope")),
                ("maxSlope", ("maxSlope", "max_slope")),
                ("x", ("x",)),
                ("z", ("z",)),
                ("minRadius", ("minRadius", "min_radius")),
                ("maxRadius", ("maxRadius", "max_radius")),
            )
            for luau_k, py_keys in num_aliases:
                for pk in py_keys:
                    if rule.get(pk) is not None:
                        fields.append(f"{luau_k} = {float(rule[pk])}")
                        break
            items.append("{ " + ", ".join(fields) + " }")
        return "{ " + ", ".join(items) + " }"

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
        custom_terrain_spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        builder_src = self._read_script("terrain_chunked_builder.luau")
        spec = custom_terrain_spec if isinstance(custom_terrain_spec, dict) else {}

        eff_biome = str(spec.get("biome") or biome)
        eff_seed = int(spec.get("seed", seed))
        eff_base_height = float(spec.get("base_height", spec.get("baseHeight", base_height)))
        eff_mountain_height = float(spec.get("mountain_height", spec.get("mountainHeight", mountain_height)))
        eff_water_level = spec["water_level"] if "water_level" in spec else (
            spec["waterLevel"] if "waterLevel" in spec else water_level
        )
        eff_flatten = flatten_zones if flatten_zones is not None else spec.get("flatten_zones", spec.get("flattenZones"))

        fz_luau_items: List[str] = []
        for z in eff_flatten or []:
            shape = z.get("shape", "Circle")
            cx = float(z.get("x", (min_corner[0] + max_corner[0]) * 0.5))
            cz = float(z.get("z", (min_corner[2] + max_corner[2]) * 0.5))
            th = float(z.get("h", z.get("target_height", eff_base_height + 8.0)))
            r0 = float(z.get("r0", z.get("radius", 36.0)))
            falloff = float(z.get("falloff", 20.0))
            r1 = float(z.get("r1", r0 + falloff))
            half_x = float(z.get("halfX", r0))
            half_z = float(z.get("halfZ", r0))
            blend = float(z.get("blend", falloff))
            mat_name = self._sanitize_material_name(z.get("material", "Cobblestone"), "Cobblestone")
            fz_luau_items.append(
                f"{{ x = {cx}, z = {cz}, h = {th}, shape = {json.dumps(shape)}, "
                f"r0 = {r0}, r1 = {r1}, halfX = {half_x}, halfZ = {half_z}, blend = {blend}, "
                f"material = Enum.Material.{mat_name} }}"
            )
        fz_table = "{ " + ", ".join(fz_luau_items) + " }"
        wl_expr = "nil" if eff_water_level is None else str(float(eff_water_level))

        raw_layers = spec.get("height_layers") or spec.get("heightLayers") or []
        raw_rules = spec.get("material_rules") or spec.get("materialRules") or []
        hl_table = self._compile_height_layers_luau(raw_layers) if isinstance(raw_layers, list) and raw_layers else "nil"
        mr_table = self._compile_material_rules_luau(raw_rules) if isinstance(raw_rules, list) and raw_rules else "nil"

        extra_cfg_lines: List[str] = []
        nw = spec.get("noise_weight", spec.get("noiseWeight"))
        if nw is not None:
            extra_cfg_lines.append(f"\t\tnoiseWeight = {float(nw)},")
        ns = spec.get("noise_scale", spec.get("noiseScale"))
        if ns is not None:
            extra_cfg_lines.append(f"\t\tnoiseScale = {float(ns)},")
        oct_v = spec.get("octaves")
        if oct_v is not None:
            extra_cfg_lines.append(f"\t\toctaves = {int(oct_v)},")
        rw = spec.get("ridge_weight", spec.get("ridgeWeight"))
        if rw is not None:
            extra_cfg_lines.append(f"\t\tridgeWeight = {float(rw)},")
        pal = spec.get("palette")
        if isinstance(pal, dict) and all(k in pal for k in ("low", "shore", "underwater", "mid", "cliff", "high")):
            extra_cfg_lines.append(
                "\t\tpalette = { "
                + ", ".join(f"{k} = Enum.Material.{self._sanitize_material_name(pal[k])}" for k in ("low", "shore", "underwater", "mid", "cliff", "high"))
                + " },"
            )
        if hl_table != "nil":
            extra_cfg_lines.append(f"\t\theightLayers = {hl_table},")
        if mr_table != "nil":
            extra_cfg_lines.append(f"\t\tmaterialRules = {mr_table},")
        extra_cfg_block = ("\n" + "\n".join(extra_cfg_lines)) if extra_cfg_lines else ""

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")

local TerrainChunkedBuilder = (function()
{builder_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else (ChangeHistoryService :: any):TryBeginRecording("SharpTerrainBuild", "Sharp MCP: Build Terrain ({eff_biome})")
local ok, resultOrErr = xpcall(function()
	local minVec = Vector3.new({float(min_corner[0])}, {float(min_corner[1])}, {float(min_corner[2])})
	local maxVec = Vector3.new({float(max_corner[0])}, {float(max_corner[1])}, {float(max_corner[2])})
	if {"true" if clear_first else "false"} then
		TerrainChunkedBuilder.ClearRegion(minVec, maxVec)
	end
	return TerrainChunkedBuilder.BuildRegion({{
		min = minVec,
		max = maxVec,
		biome = {json.dumps(eff_biome)} :: any,
		seed = {eff_seed},
		baseHeight = {eff_base_height},
		mountainHeight = {eff_mountain_height},
		waterLevel = {wl_expr},
		chunkCellsXZ = {int(chunk_voxels)},
		yieldPerChunk = false,
		flattenZones = {fz_table},{extra_cfg_block}
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

    @staticmethod
    def _merge_atmosphere_overrides(
        overrides: Optional[Dict[str, Any]],
        custom_atmosphere: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for src in (overrides or {}, custom_atmosphere or {}):
            if not isinstance(src, dict):
                continue
            for sec_key in (
                "lighting", "atmosphere", "clouds", "sky", "water", "grass",
                "postEffects", "post_effects", "bloom", "colorCorrection", "color_correction",
                "colorGrading", "color_grading", "sunRays", "sun_rays", "depthOfField", "depth_of_field",
            ):
                if isinstance(src.get(sec_key), dict):
                    norm_sec = {
                        "post_effects": "postEffects",
                        "color_correction": "colorCorrection",
                        "color_grading": "colorGrading",
                        "sun_rays": "sunRays",
                        "depth_of_field": "depthOfField",
                    }.get(sec_key, sec_key)
                    if norm_sec in ("bloom", "colorCorrection", "colorGrading", "sunRays", "depthOfField"):
                        pe = merged.setdefault("postEffects", {})
                        pe.setdefault(norm_sec, {}).update(src[sec_key])
                    else:
                        merged.setdefault(norm_sec, {}).update(src[sec_key])

            wind_val = src.get("globalWind") or src.get("global_wind") or src.get("wind")
            if wind_val is not None:
                merged["globalWind"] = wind_val

            # Flat convenience keys inside custom_atmosphere / overrides
            lighting_aliases = {
                "clock_time": "ClockTime", "ClockTime": "ClockTime",
                "brightness": "Brightness", "Brightness": "Brightness",
                "ambient": "Ambient", "Ambient": "Ambient",
                "outdoor_ambient": "OutdoorAmbient", "OutdoorAmbient": "OutdoorAmbient",
                "color_shift_top": "ColorShift_Top", "ColorShift_Top": "ColorShift_Top",
                "color_shift_bottom": "ColorShift_Bottom", "ColorShift_Bottom": "ColorShift_Bottom",
                "exposure_compensation": "ExposureCompensation", "ExposureCompensation": "ExposureCompensation",
                "shadow_softness": "ShadowSoftness", "ShadowSoftness": "ShadowSoftness",
                "geographic_latitude": "GeographicLatitude", "GeographicLatitude": "GeographicLatitude",
                "global_shadows": "GlobalShadows", "GlobalShadows": "GlobalShadows",
                "lighting_style": "LightingStyle", "LightingStyle": "LightingStyle",
            }
            atmo_aliases = {
                "density": "Density", "Density": "Density",
                "offset": "Offset", "Offset": "Offset",
                "haze": "Haze", "Haze": "Haze",
                "glare": "Glare", "Glare": "Glare",
                "atmosphere_color": "Color", "fog_color": "Color", "Color": "Color",
                "decay": "Decay", "Decay": "Decay",
            }
            clouds_aliases = {
                "cloud_cover": "Cover", "cloud_density": "Density", "cloud_color": "Color",
                "clouds_enabled": "Enabled",
            }
            water_aliases = {
                "water_color": "WaterColor", "WaterColor": "WaterColor",
                "water_transparency": "WaterTransparency", "WaterTransparency": "WaterTransparency",
                "water_reflectance": "WaterReflectance", "WaterReflectance": "WaterReflectance",
                "water_wave_size": "WaterWaveSize", "WaterWaveSize": "WaterWaveSize",
                "water_wave_speed": "WaterWaveSpeed", "WaterWaveSpeed": "WaterWaveSpeed",
            }
            grass_aliases = {
                "grass_decoration": "Decoration", "decoration": "Decoration",
                "grass_length": "GrassLength", "GrassLength": "GrassLength",
            }
            for k, v in src.items():
                if k in lighting_aliases:
                    merged.setdefault("lighting", {})[lighting_aliases[k]] = v
                elif k in atmo_aliases:
                    merged.setdefault("atmosphere", {})[atmo_aliases[k]] = v
                elif k in clouds_aliases:
                    merged.setdefault("clouds", {})[clouds_aliases[k]] = v
                elif k in water_aliases:
                    merged.setdefault("water", {})[water_aliases[k]] = v
                elif k in grass_aliases:
                    merged.setdefault("grass", {})[grass_aliases[k]] = v
                elif k not in (
                    "lighting", "atmosphere", "clouds", "sky", "water", "grass",
                    "postEffects", "post_effects", "bloom", "colorCorrection", "color_correction",
                    "colorGrading", "color_grading", "sunRays", "sun_rays", "depthOfField", "depth_of_field",
                    "globalWind", "global_wind", "wind", "base_preset", "preset_name", "preset",
                ):
                    merged[k] = v
        return merged

    def compile_environment_apply_luau(
        self,
        preset_name: str = "GoldenSunset",
        overrides: Optional[Dict[str, Any]] = None,
        run_audit_after: bool = True,
        custom_atmosphere: Optional[Dict[str, Any]] = None,
    ) -> str:
        presets_src = self._read_script("atmosphere_presets.luau")
        audit_src = self._read_script("audit_environment.luau")
        eff_preset = preset_name
        if isinstance(custom_atmosphere, dict):
            eff_preset = str(
                custom_atmosphere.get("base_preset")
                or custom_atmosphere.get("preset_name")
                or custom_atmosphere.get("preset")
                or preset_name
            )
        merged_overrides = self._merge_atmosphere_overrides(overrides, custom_atmosphere)
        overrides_json = json.dumps(merged_overrides)

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local Lighting = game:GetService("Lighting")
local Workspace = game:GetService("Workspace")

local AtmospherePresets = (function()
{presets_src}
end)()

local runAuditFn = function()
{audit_src}
end

local function parseHexColor(hex: string): Color3?
	local clean = string.gsub(hex, "^#", "")
	if #clean ~= 6 then
		return nil
	end
	local r = tonumber(string.sub(clean, 1, 2), 16)
	local g = tonumber(string.sub(clean, 3, 4), 16)
	local b = tonumber(string.sub(clean, 5, 6), 16)
	if r and g and b then
		return Color3.fromRGB(r, g, b)
	end
	return nil
end

local function coercePropValue(propName: string, rawVal: any): any
	local lower = string.lower(propName)
	if type(rawVal) == "string" then
		if string.sub(rawVal, 1, 1) == "#" then
			local col = parseHexColor(rawVal)
			if col then
				return col
			end
		elseif propName == "LightingStyle" then
			local okE, enumVal = pcall(function() return (Enum.LightingStyle :: any)[rawVal] end)
			if okE and enumVal ~= nil then return enumVal end
		elseif propName == "TonemapperPreset" then
			local okE, enumVal = pcall(function() return (Enum.TonemapperPreset :: any)[rawVal] end)
			if okE and enumVal ~= nil then return enumVal end
		end
	elseif type(rawVal) == "table" then
		if string.find(lower, "wind", 1, true) ~= nil or string.find(lower, "orientation", 1, true) ~= nil then
			local x = tonumber(rawVal[1] or rawVal.x or rawVal.X) or 0
			local y = tonumber(rawVal[2] or rawVal.y or rawVal.Y) or 0
			local z = tonumber(rawVal[3] or rawVal.z or rawVal.Z) or 0
			return Vector3.new(x, y, z)
		elseif string.find(lower, "color", 1, true) ~= nil or lower == "ambient" or lower == "outdoorambient" or lower == "decay" or lower == "tintcolor" then
			local r = tonumber(rawVal[1] or rawVal.r or rawVal.R)
			local g = tonumber(rawVal[2] or rawVal.g or rawVal.G)
			local b = tonumber(rawVal[3] or rawVal.b or rawVal.B)
			if r and g and b then
				if math.max(r, g, b) > 1 then
					return Color3.fromRGB(r, g, b)
				end
				return Color3.new(r, g, b)
			end
		end
	end
	return rawVal
end

local function applyProps(target: Instance, props: any)
	if type(props) ~= "table" then
		return
	end
	for k, v in pairs(props) do
		local val = coercePropValue(tostring(k), v)
		pcall(function() (target :: any)[k] = val end)
	end
end

local function ensurePostEffect(className: string): Instance
	local existing = Lighting:FindFirstChildOfClass(className)
	if existing then
		return existing
	end
	local created = Instance.new(className)
	created.Parent = Lighting
	return created
end

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else (ChangeHistoryService :: any):TryBeginRecording("SharpEnvironmentApply", "Sharp MCP: Apply Atmosphere ({eff_preset})")
local ok, resOrErr = xpcall(function()
	local overridesTbl = HttpService:JSONDecode({json.dumps(overrides_json)})
	local applied = AtmospherePresets.ApplyPreset({json.dumps(eff_preset)}, overridesTbl)

	if type(overridesTbl.lighting) == "table" then
		applyProps(Lighting, overridesTbl.lighting)
	end
	if type(overridesTbl.atmosphere) == "table" then
		local atmo = Lighting:FindFirstChildOfClass("Atmosphere")
		if atmo then
			applyProps(atmo, overridesTbl.atmosphere)
			if atmo.Glare > 0 and atmo.Haze <= 0 then
				atmo.Haze = 0.25
			end
		end
	end
	if type(overridesTbl.clouds) == "table" then
		local clouds = Workspace.Terrain:FindFirstChildOfClass("Clouds")
		if clouds then
			applyProps(clouds, overridesTbl.clouds)
		end
	end
	if type(overridesTbl.sky) == "table" then
		local sky = Lighting:FindFirstChildOfClass("Sky")
		if sky then
			applyProps(sky, overridesTbl.sky)
		end
	end
	if type(overridesTbl.water) == "table" then
		applyProps(Workspace.Terrain, overridesTbl.water)
	end
	if type(overridesTbl.grass) == "table" then
		applyProps(Workspace.Terrain, overridesTbl.grass)
	end
	if overridesTbl.globalWind ~= nil then
		local w = coercePropValue("GlobalWind", overridesTbl.globalWind)
		if typeof(w) == "Vector3" then
			Workspace.GlobalWind = w
		end
	end
	if type(overridesTbl.postEffects) == "table" then
		local peMap = {{
			bloom = "BloomEffect",
			Bloom = "BloomEffect",
			colorCorrection = "ColorCorrectionEffect",
			ColorCorrection = "ColorCorrectionEffect",
			colorGrading = "ColorGradingEffect",
			ColorGrading = "ColorGradingEffect",
			sunRays = "SunRaysEffect",
			SunRays = "SunRaysEffect",
			depthOfField = "DepthOfFieldEffect",
			DepthOfField = "DepthOfFieldEffect",
		}}
		for key, props in pairs(overridesTbl.postEffects) do
			local clsName = peMap[tostring(key)]
			if clsName and type(props) == "table" then
				local inst = ensurePostEffect(clsName)
				applyProps(inst, props)
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

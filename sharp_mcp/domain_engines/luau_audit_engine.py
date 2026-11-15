"""Luau Scaffolding, Networking, Multi-Domain Auditing & Place Snapshot Engine.

Embeds:
- `project_scaffold.luau` (`roblox-luau-coding`)
- `safe_remote_gateway.luau` (`roblox-luau-coding`)
- `architecture_security_audit.luau` (`roblox-luau-coding`)
- `studio_runtime_smoke_test.luau` (`roblox-luau-coding`)
- `audit_environment.luau` (`roblox-terrain-atmosphere`)
- `audit_gui.luau` (`roblox-gui`)
- Full Place Snapshot / Zero-Diff Restore Engine (`Step A` / `Step D` verified baseline parity)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class LuauAuditSnapshotEngine:
    def __init__(self, skills_dir: Path, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir

    def _resolve_skill_script(self, skill_name: str, archive_folder: str, script_name: str) -> str:
        p = self.skills_dir / skill_name / "scripts" / script_name
        if p.is_file():
            return p.read_text(encoding="utf-8")
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / skill_name / "scripts" / script_name
        if bundled.is_file():
            return bundled.read_text(encoding="utf-8")
        if self.archive_dir:
            return (self.archive_dir / archive_folder / "skill" / "scripts" / script_name).read_text(encoding="utf-8")
        raise FileNotFoundError(f"Skill script not found: {skill_name}/{script_name}")

    def compile_scaffold_luau(
        self,
        action: str = "apply",  # "apply" | "cleanup"
        root_prefix: str = "",
        tag: str = "RobloxLuauCodingScaffold",
        install_safe_remote_gateway: bool = True,
    ) -> str:
        scaffold_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "project_scaffold.luau"
        )
        gateway_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "safe_remote_gateway.luau"
        )

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local ProjectScaffold = (function()
{scaffold_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpLuauScaffold", "Sharp MCP: Project Scaffold ({action})")
local ok, resOrErr = xpcall(function()
	local opts = {{
		rootPrefix = {json.dumps(root_prefix)},
		tag = {json.dumps(tag)},
	}}
	if {json.dumps(action)} == "cleanup" then
		return ProjectScaffold.Cleanup(opts)
	end

	local rep = ProjectScaffold.Apply(opts)
	if {"true" if install_safe_remote_gateway else "false"} then
		local targetRoot = if {json.dumps(root_prefix)} ~= ""
			then ReplicatedStorage:FindFirstChild({json.dumps(root_prefix)}) or ReplicatedStorage
			else ReplicatedStorage
		local sharedFolder = targetRoot:FindFirstChild("Shared") or targetRoot
		local oldGw = sharedFolder:FindFirstChild("SafeRemoteGateway")
		if oldGw then oldGw:Destroy() end
		local gwMod = Instance.new("ModuleScript")
		gwMod.Name = "SafeRemoteGateway"
		gwMod:SetAttribute("LuauSkillScaffoldManaged", true)
		gwMod.Source = [========[{gateway_src}]========]
		gwMod.Parent = sharedFolder
	end
	return rep
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
	report = resOrErr,
}})
"""

    def compile_audit_all_luau(
        self,
        domains: Optional[List[str]] = None,
        run_smoke_test: bool = False,
    ) -> str:
        selected = set(domains or ["gui", "environment", "luau_security"])
        env_audit_src = self._resolve_skill_script(
            "roblox-terrain-atmosphere", "03_roblox_terrain_atmosphere", "audit_environment.luau"
        )
        gui_audit_src = self._resolve_skill_script(
            "roblox-gui", "02_roblox_gui", "audit_gui.luau"
        )
        sec_audit_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "architecture_security_audit.luau"
        )
        scaffold_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "project_scaffold.luau"
        )
        gateway_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "safe_remote_gateway.luau"
        )
        smoke_src = self._resolve_skill_script(
            "roblox-luau-coding", "04_roblox_luau_coding", "studio_runtime_smoke_test.luau"
        )

        run_env = "environment" in selected
        run_gui = "gui" in selected
        run_sec = "luau_security" in selected

        return f"""local HttpService = game:GetService("HttpService")

local combined = {{
	ok = true,
	domainsRun = {{}},
	reports = {{}},
}}

if {"true" if run_env else "false"} then
	local rawEnv = (function()
{env_audit_src}
	end)()
	table.insert(combined.domainsRun, "environment")
	if type(rawEnv) == "string" then
		local okDec, dec = pcall(function() return HttpService:JSONDecode(rawEnv) end)
		combined.reports.environment = if okDec then dec else rawEnv
	elseif type(rawEnv) == "table" and type(rawEnv.Run) == "function" then
		combined.reports.environment = rawEnv.Run()
	else
		combined.reports.environment = rawEnv
	end
end

if {"true" if run_gui else "false"} then
	local rawGui = (function()
{gui_audit_src}
	end)()
	table.insert(combined.domainsRun, "gui")
	if type(rawGui) == "string" then
		local okDec, dec = pcall(function() return HttpService:JSONDecode(rawGui) end)
		combined.reports.gui = if okDec then dec else rawGui
	else
		combined.reports.gui = rawGui
	end
end

local ArchitectureSecurityAudit = (function()
{sec_audit_src}
end)()

if {"true" if run_sec else "false"} then
	table.insert(combined.domainsRun, "luau_security")
	combined.reports.luau_security = ArchitectureSecurityAudit.Run()
end

if {"true" if run_smoke_test else "false"} then
	local ProjectScaffold = (function()
{scaffold_src}
	end)()
	local SafeRemoteGateway = (function()
{gateway_src}
	end)()
	local StudioRuntimeSmokeTest = (function()
{smoke_src}
	end)()
	table.insert(combined.domainsRun, "runtime_smoke")
	combined.reports.runtime_smoke = StudioRuntimeSmokeTest.Run({{
		scaffold = ProjectScaffold,
		gateway = SafeRemoteGateway,
		audit = ArchitectureSecurityAudit,
	}})
end

return HttpService:JSONEncode(combined)
"""

    def get_audit_script_sources(self) -> Dict[str, str]:
        """Return raw Luau sources of built-in domain audit scripts."""
        return {
            "luau_security": self._resolve_skill_script(
                "roblox-luau-coding", "04_roblox_luau_coding", "architecture_security_audit.luau"
            ),
            "gui": self._resolve_skill_script(
                "roblox-gui", "02_roblox_gui", "audit_gui.luau"
            ),
            "environment": self._resolve_skill_script(
                "roblox-terrain-atmosphere", "03_roblox_terrain_atmosphere", "audit_environment.luau"
            ),
        }

    def compile_script_inventory_luau(
        self,
        roots: Optional[List[str]] = None,
        max_scripts: int = 60,
        max_source_chars: int = 12000,
    ) -> str:
        """Compile read-only Luau to collect bounded LuaSourceContainer paths and sources from Studio."""
        target_roots = roots or [
            "ServerScriptService",
            "ServerStorage",
            "ReplicatedStorage",
            "ReplicatedFirst",
            "StarterGui",
            "StarterPack",
            "StarterPlayer",
            "Workspace",
        ]
        return f"""local HttpService = game:GetService("HttpService")

local TARGET_SERVICES = {json.dumps(target_roots)}
local MAX_SCRIPTS = {max(1, int(max_scripts))}
local MAX_SOURCE_CHARS = {max(256, int(max_source_chars))}

local scriptsOut = {{}}
local truncated = false

for _, svcName in ipairs(TARGET_SERVICES) do
	local okSvc, svc = pcall(function()
		return game:GetService(svcName)
	end)
	if okSvc and svc then
		for _, desc in ipairs(svc:GetDescendants()) do
			if desc:IsA("LuaSourceContainer") then
				local fullName = desc:GetFullName()
				if string.find(fullName, "SharpBridgePlugin", 1, true) == nil and desc:GetAttribute("LuauSkillAuditIgnore") ~= true then
					if #scriptsOut >= MAX_SCRIPTS then
						truncated = true
						break
					end
					local okSrc, src = pcall(function()
						return (desc :: any).Source
					end)
					local runCtx = "Legacy"
					if desc:IsA("Script") then
						local okCtx, rc = pcall(function()
							return tostring((desc :: Script).RunContext)
						end)
						if okCtx then
							runCtx = rc
						end
					end
					local text = if okSrc and type(src) == "string" then src else ""
					local isTrunc = false
					if #text > MAX_SOURCE_CHARS then
						text = string.sub(text, 1, MAX_SOURCE_CHARS)
						isTrunc = true
					end
					table.insert(scriptsOut, {{
						path = fullName,
						service = svcName,
						className = desc.ClassName,
						runContext = runCtx,
						source = text,
						sourceTruncated = isTrunc,
					}})
				end
			end
		end
	end
	if truncated then
		break
	end
end

return HttpService:JSONEncode({{
	ok = true,
	count = #scriptsOut,
	truncated = truncated,
	scripts = scriptsOut,
}})
"""

    def compile_critical_audit_luau(
        self,
        domains: Optional[List[str]] = None,
        run_smoke_test: bool = False,
        include_script_sources: bool = True,
        max_scripts: int = 40,
        max_source_chars: int = 8000,
    ) -> str:
        """Compile combined live Studio audit + deep telemetry + bounded script extraction for CriticalAuditEngine."""
        base_audit = self.compile_audit_all_luau(domains=domains, run_smoke_test=run_smoke_test)
        inv_luau = (
            self.compile_script_inventory_luau(max_scripts=max_scripts, max_source_chars=max_source_chars)
            if include_script_sources
            else 'return game:GetService("HttpService"):JSONEncode({ ok = true, count = 0, truncated = false, scripts = {} })'
        )
        return f"""local HttpService = game:GetService("HttpService")
local StarterGui = game:GetService("StarterGui")
local Workspace = game:GetService("Workspace")

local baseRaw = (function()
{base_audit}
end)()

local invRaw = (function()
{inv_luau}
end)()

local okBase, baseDecoded = pcall(function()
	return if type(baseRaw) == "string" then HttpService:JSONDecode(baseRaw) else baseRaw
end)
local okInv, invDecoded = pcall(function()
	return if type(invRaw) == "string" then HttpService:JSONDecode(invRaw) else invRaw
end)

local worldTelemetry = {{
	partCount = 0,
	meshOrUnionCount = 0,
	preciseCollisionCount = 0,
	unanchoredCount = 0,
	spawnLocationCount = 0,
	streamingEnabled = false,
}}
pcall(function()
	worldTelemetry.streamingEnabled = Workspace.StreamingEnabled
end)
for _, desc in ipairs(Workspace:GetDescendants()) do
	if desc:IsA("BasePart") and not desc:IsA("Terrain") then
		worldTelemetry.partCount += 1
		if not desc.Anchored then
			worldTelemetry.unanchoredCount += 1
		end
		if desc:IsA("SpawnLocation") then
			worldTelemetry.spawnLocationCount += 1
		end
		if desc:IsA("MeshPart") or desc:IsA("UnionOperation") then
			worldTelemetry.meshOrUnionCount += 1
			local okF, fid = pcall(function()
				return tostring((desc :: any).CollisionFidelity)
			end)
			if okF and string.find(fid, "PreciseConvexDecomposition", 1, true) ~= nil then
				worldTelemetry.preciseCollisionCount += 1
			end
		end
	end
end

local guiTelemetry = {{
	screenGuiCount = 0,
	canvasGroupCount = 0,
	textScaledWithoutConstraint = 0,
}}
for _, child in ipairs(StarterGui:GetChildren()) do
	if child:IsA("ScreenGui") then
		guiTelemetry.screenGuiCount += 1
	end
end
for _, desc in ipairs(StarterGui:GetDescendants()) do
	if desc:IsA("CanvasGroup") then
		guiTelemetry.canvasGroupCount += 1
	elseif desc:IsA("TextLabel") or desc:IsA("TextButton") or desc:IsA("TextBox") then
		if (desc :: any).TextScaled == true and desc:FindFirstChildWhichIsA("UITextSizeConstraint") == nil then
			guiTelemetry.textScaledWithoutConstraint += 1
		end
	end
end

local payload = if okBase and type(baseDecoded) == "table" then baseDecoded else {{ ok = false, raw = baseRaw }}
payload.telemetry = {{
	world = worldTelemetry,
	gui = guiTelemetry,
}}
if okInv and type(invDecoded) == "table" then
	payload.scriptInventory = invDecoded
end

return HttpService:JSONEncode(payload)
"""

    @staticmethod
    def compile_snapshot_and_undo_luau(
        action: str = "checkpoint",  # "checkpoint" | "restore" | "status" | "undo"
        probe_min: Optional[List[float]] = None,
        probe_max: Optional[List[float]] = None,
    ) -> str:
        p_min = probe_min or [2000, 0, 2000]
        p_max = probe_max or [2256, 160, 2256]

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local Lighting = game:GetService("Lighting")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local ServerStorage = game:GetService("ServerStorage")
local StarterGui = game:GetService("StarterGui")
local Workspace = game:GetService("Workspace")
local terrain = Workspace.Terrain

local ACTION = {json.dumps(action)}
local probeRegion = Region3.new(
	Vector3.new({float(p_min[0])}, {float(p_min[1])}, {float(p_min[2])}),
	Vector3.new({float(p_max[0])}, {float(p_max[1])}, {float(p_max[2])})
):ExpandToGrid(4)

local function countNonAir()
	local mats, occs = terrain:ReadVoxels(probeRegion, 4)
	local sz = mats.Size
	local c = 0
	for x = 1, sz.X do
		for y = 1, sz.Y do
			for z = 1, sz.Z do
				if mats[x][y][z] ~= Enum.Material.Air or occs[x][y][z] > 0 then
					c += 1
				end
			end
		end
	end
	return c
end

if ACTION == "undo" then
	ChangeHistoryService:Undo()
	return HttpService:JSONEncode({{ ok = true, action = "undo" }})
end

if ACTION == "status" then
	return HttpService:JSONEncode({{
		ok = true,
		hasCheckpoint = _G._SharpMcpSnapshot ~= nil,
		probeRegionNonAirVoxels = countNonAir(),
		clockTime = Lighting.ClockTime,
		brightness = Lighting.Brightness,
	}})
end

if ACTION == "checkpoint" then
	local guiStates = {{}}
	for _, ch in ipairs(StarterGui:GetChildren()) do
		if ch:IsA("ScreenGui") then
			guiStates[ch.Name] = ch.Enabled
		end
	end
	local lightingClones = {{}}
	for _, ch in ipairs(Lighting:GetChildren()) do
		table.insert(lightingClones, ch:Clone())
	end
	local terrainClones = {{}}
	for _, ch in ipairs(terrain:GetChildren()) do
		table.insert(terrainClones, ch:Clone())
	end
	_G._SharpMcpSnapshot = {{
		timestamp = os.time(),
		clockTime = Lighting.ClockTime,
		brightness = Lighting.Brightness,
		ambient = Lighting.Ambient,
		outdoorAmbient = Lighting.OutdoorAmbient,
		colorShiftTop = Lighting.ColorShift_Top,
		colorShiftBottom = Lighting.ColorShift_Bottom,
		envDiffuse = Lighting.EnvironmentDiffuseScale,
		envSpecular = Lighting.EnvironmentSpecularScale,
		globalShadows = Lighting.GlobalShadows,
		shadowSoftness = Lighting.ShadowSoftness,
		latitude = Lighting.GeographicLatitude,
		exposure = Lighting.ExposureCompensation,
		globalWind = Workspace.GlobalWind,
		cameraCFrame = if Workspace.CurrentCamera then Workspace.CurrentCamera.CFrame else nil,
		waterColor = terrain.WaterColor,
		waterReflectance = terrain.WaterReflectance,
		waterTransparency = terrain.WaterTransparency,
		waterWaveSize = terrain.WaterWaveSize,
		waterWaveSpeed = terrain.WaterWaveSpeed,
		showDevGui = StarterGui.ShowDevelopmentGui,
		guiStates = guiStates,
		lightingClones = lightingClones,
		terrainClones = terrainClones,
		baselineNonAirVoxels = countNonAir(),
	}}
	return HttpService:JSONEncode({{
		ok = true,
		action = "checkpoint",
		baselineNonAirVoxels = _G._SharpMcpSnapshot.baselineNonAirVoxels,
		clockTime = Lighting.ClockTime,
	}})
end

if ACTION == "restore" then
	local snap = _G._SharpMcpSnapshot
	if not snap then
		return HttpService:JSONEncode({{ ok = false, error = "No active checkpoint in _G._SharpMcpSnapshot" }})
	end
	terrain:FillRegion(probeRegion, 4, Enum.Material.Air)
	for _, ch in ipairs(terrain:GetChildren()) do
		ch:Destroy()
	end
	for _, cl in ipairs(snap.terrainClones) do
		cl:Clone().Parent = terrain
	end
	for _, ch in ipairs(Lighting:GetChildren()) do
		ch:Destroy()
	end
	for _, cl in ipairs(snap.lightingClones) do
		cl:Clone().Parent = Lighting
	end
	Lighting.ClockTime = snap.clockTime
	Lighting.Brightness = snap.brightness
	Lighting.Ambient = snap.ambient
	Lighting.OutdoorAmbient = snap.outdoorAmbient
	Lighting.ColorShift_Top = snap.colorShiftTop
	Lighting.ColorShift_Bottom = snap.colorShiftBottom
	Lighting.EnvironmentDiffuseScale = snap.envDiffuse
	Lighting.EnvironmentSpecularScale = snap.envSpecular
	Lighting.GlobalShadows = snap.globalShadows
	Lighting.ShadowSoftness = snap.shadowSoftness
	Lighting.GeographicLatitude = snap.latitude
	Lighting.ExposureCompensation = snap.exposure
	Workspace.GlobalWind = snap.globalWind
	if Workspace.CurrentCamera and snap.cameraCFrame then
		Workspace.CurrentCamera.CFrame = snap.cameraCFrame
	end
	terrain.WaterColor = snap.waterColor
	terrain.WaterReflectance = snap.waterReflectance
	terrain.WaterTransparency = snap.waterTransparency
	terrain.WaterWaveSize = snap.waterWaveSize
	terrain.WaterWaveSpeed = snap.waterWaveSpeed
	StarterGui.ShowDevelopmentGui = snap.showDevGui
	for name, en in pairs(snap.guiStates) do
		local sg = StarterGui:FindFirstChild(name)
		if sg and sg:IsA("ScreenGui") then
			sg.Enabled = en
		end
	end
	local afterNonAir = countNonAir()
	local diffCount = 0
	if afterNonAir ~= snap.baselineNonAirVoxels then diffCount += 1 end
	if math.abs(Lighting.ClockTime - snap.clockTime) > 1e-4 then diffCount += 1 end
	return HttpService:JSONEncode({{
		ok = true,
		action = "restore",
		restored100Percent = (diffCount == 0),
		diffCount = diffCount,
		probeRegionNonAirVoxels = afterNonAir,
		clockTime = Lighting.ClockTime,
	}})
end

return HttpService:JSONEncode({{ ok = false, error = "Unknown action: " .. tostring(ACTION) }})
"""

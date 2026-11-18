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
import re
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

local TARGET_SERVICES = {{ {", ".join(json.dumps(root, ensure_ascii=False) for root in target_roots)} }}
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
local weaponTelemetry = {{
	rotatedPivotModels = {{}},
	brokenLoadedAmmo = {{}},
	verticalRangedTools = {{}},
	transformArmIKs = {{}},
}}
local assetContainers = {{
	game:GetService("ReplicatedStorage"),
	game:GetService("ServerStorage"),
	game:GetService("StarterPack"),
}}
for _, container in ipairs(assetContainers) do
	for _, desc in ipairs(container:GetDescendants()) do
		if desc:IsA("Model") and desc.PrimaryPart then
			local po = desc.PrimaryPart.PivotOffset
			if po.LookVector:Dot(Vector3.new(0, 0, -1)) < 0.99 or po.UpVector:Dot(Vector3.new(0, 1, 0)) < 0.99 then
				table.insert(weaponTelemetry.rotatedPivotModels, {{
					path = desc:GetFullName(),
					primaryPart = desc.PrimaryPart.Name,
					lookDot = po.LookVector:Dot(Vector3.new(0, 0, -1)),
					upDot = po.UpVector:Dot(Vector3.new(0, 1, 0)),
				}})
			end
		elseif desc:IsA("Tool") then
			local h = desc:FindFirstChild("Handle")
			local muzzle = desc:FindFirstChild("MuzzleAttachment", true)
			if h and h:IsA("BasePart") and muzzle and muzzle:IsA("Attachment") then
				local muzzleDir = h.CFrame:VectorToObjectSpace(muzzle.WorldCFrame.LookVector)
				local barrelAxis = if muzzle.Position.Magnitude > 0.1 then muzzle.Position.Unit else muzzleDir
				if math.abs(desc.Grip.RightVector:Dot(Vector3.new(1, 0, 0))) > 0.99 and desc.Grip.LookVector:Dot(Vector3.new(0, 0, -1)) > 0.99 then
					table.insert(weaponTelemetry.verticalRangedTools, desc:GetFullName())
				end
				for _, child in ipairs(desc:GetChildren()) do
					local ln = string.lower(child.Name)
					if child:IsA("Model") and (string.find(ln, "bolt", 1, true) or string.find(ln, "arrow", 1, true) or string.find(ln, "ammo", 1, true)) then
						for _, bp in ipairs(child:GetDescendants()) do
							if bp:IsA("BasePart") then
								local relLook = h.CFrame:ToObjectSpace(bp.CFrame).LookVector
								if math.abs(relLook:Dot(Vector3.new(0, 0, -1))) < 0.7 then
									table.insert(weaponTelemetry.brokenLoadedAmmo, bp:GetFullName())
									break
								end
							end
						end
					end
				end
			end
		end
	end
end
for _, rootSvc in ipairs({{ Workspace, game:GetService("StarterPlayer") }}) do
	for _, desc in ipairs(rootSvc:GetDescendants()) do
		if desc:IsA("IKControl") and desc.Enabled then
			local okT, isTransform = pcall(function()
				return desc.Type == Enum.IKControlType.Transform
			end)
			if okT and isTransform and desc.EndEffector and (desc.EndEffector.Name == "RightHand" or desc.EndEffector.Name == "LeftHand") then
				table.insert(weaponTelemetry.transformArmIKs, desc:GetFullName())
			end
		end
	end
end

payload.telemetry = {{
	world = worldTelemetry,
	gui = guiTelemetry,
	weapons = weaponTelemetry,
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

    @staticmethod
    def _sanitize_luau_key(raw: str, fallback: str = "Item") -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_]", "_", (raw or "").strip())
        if not cleaned or cleaned[0].isdigit():
            cleaned = f"K_{cleaned}" if cleaned else fallback
        return cleaned

    @staticmethod
    def _normalize_contracts_spec(contracts_spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        raw_spec = contracts_spec if isinstance(contracts_spec, dict) else {}
        spec: Dict[str, Any] = {}
        for sk, sv in raw_spec.items():
            low_k = str(sk).strip().lower()
            if low_k not in spec or spec[low_k] is None:
                spec[low_k] = sv
            spec.setdefault(str(sk), sv)
        root_prefix = str(spec.get("root_prefix") or spec.get("rootprefix") or spec.get("rootPrefix") or "").strip()
        remotes_folder = str(spec.get("remotes_folder") or spec.get("remotesfolder") or spec.get("remotesFolder") or "Remotes").strip() or "Remotes"
        schema_version = str(spec.get("schema_version") or spec.get("schemaversion") or spec.get("schemaVersion") or "1.0.0").strip() or "1.0.0"
        ensure_remotes = bool(spec.get("ensure_remote_instances", True))

        # Remotes normalization
        raw_remotes = spec.get("remotes")
        remotes_out: List[Dict[str, Any]] = []
        if isinstance(raw_remotes, dict):
            for r_key, r_val in raw_remotes.items():
                if isinstance(r_val, dict):
                    r_name = str(r_val.get("name") or r_key)
                    r_kind = str(r_val.get("kind") or r_val.get("className") or "RemoteEvent")
                    r_dir = str(r_val.get("direction") or "ClientToServer")
                    rl_raw = r_val.get("rate_limit") or r_val.get("rateLimit") or r_val.get("rateLimitPerSec") or 10
                    if isinstance(rl_raw, dict):
                        rl_num = float(rl_raw.get("refillPerSecond") or rl_raw.get("capacity") or 10)
                    else:
                        rl_num = float(rl_raw or 10)
                    r_desc = str(r_val.get("description") or "")
                else:
                    r_name = str(r_val or r_key)
                    r_kind = "RemoteEvent"
                    r_dir = "ClientToServer"
                    rl_num = 10.0
                    r_desc = ""
                if r_kind not in ("RemoteEvent", "UnreliableRemoteEvent", "RemoteFunction"):
                    r_kind = "RemoteEvent"
                remotes_out.append(
                    {
                        "key": str(r_key),
                        "name": r_name,
                        "kind": r_kind,
                        "direction": r_dir,
                        "rateLimitPerSec": rl_num,
                        "description": r_desc,
                    }
                )
        elif isinstance(raw_remotes, list):
            for item in raw_remotes:
                if isinstance(item, str) and item.strip():
                    remotes_out.append(
                        {
                            "key": item.strip(),
                            "name": item.strip(),
                            "kind": "RemoteEvent",
                            "direction": "ClientToServer",
                            "rateLimitPerSec": 10.0,
                            "description": "",
                        }
                    )
                elif isinstance(item, dict):
                    r_name = str(item.get("name") or item.get("key") or "").strip()
                    if not r_name:
                        continue
                    r_key = str(item.get("key") or r_name)
                    r_kind = str(item.get("kind") or item.get("className") or "RemoteEvent")
                    if r_kind not in ("RemoteEvent", "UnreliableRemoteEvent", "RemoteFunction"):
                        r_kind = "RemoteEvent"
                    rl_raw = item.get("rate_limit") or item.get("rateLimit") or item.get("rateLimitPerSec") or 10
                    if isinstance(rl_raw, dict):
                        rl_num = float(rl_raw.get("refillPerSecond") or rl_raw.get("capacity") or 10)
                    else:
                        rl_num = float(rl_raw or 10)
                    remotes_out.append(
                        {
                            "key": r_key,
                            "name": r_name,
                            "kind": r_kind,
                            "direction": str(item.get("direction") or "ClientToServer"),
                            "rateLimitPerSec": rl_num,
                            "description": str(item.get("description") or ""),
                        }
                    )

        # Tags normalization
        raw_tags = spec.get("tags")
        tags_out: Dict[str, str] = {}
        if isinstance(raw_tags, dict):
            for tk, tv in raw_tags.items():
                tags_out[str(tk)] = str(tv)
        elif isinstance(raw_tags, list):
            for t in raw_tags:
                if isinstance(t, str) and t.strip():
                    tags_out[t.strip()] = t.strip()
                elif isinstance(t, dict):
                    tk = str(t.get("key") or t.get("name") or "").strip()
                    tv = str(t.get("tag") or t.get("name") or tk).strip()
                    if tk:
                        tags_out[tk] = tv

        # Module contracts normalization
        raw_mods = spec.get("modules") or spec.get("module_contracts") or spec.get("interfaces")
        mods_out: List[Dict[str, Any]] = []
        if isinstance(raw_mods, dict):
            for mk, mv in raw_mods.items():
                if isinstance(mv, dict):
                    mods_out.append(
                        {
                            "key": str(mk),
                            "name": str(mv.get("name") or mk),
                            "path": str(mv.get("path") or f"ReplicatedStorage.Shared.{mk}"),
                            "exports": [str(e) for e in (mv.get("exports") or []) if str(e).strip()],
                            "role": str(mv.get("role") or "shared"),
                        }
                    )
                elif isinstance(mv, list):
                    mods_out.append(
                        {
                            "key": str(mk),
                            "name": str(mk),
                            "path": f"ReplicatedStorage.Shared.{mk}",
                            "exports": [str(e) for e in mv if str(e).strip()],
                            "role": "shared",
                        }
                    )
        elif isinstance(raw_mods, list):
            for mv in raw_mods:
                if isinstance(mv, dict):
                    mname = str(mv.get("name") or mv.get("key") or "").strip()
                    if not mname:
                        continue
                    mods_out.append(
                        {
                            "key": str(mv.get("key") or mname),
                            "name": mname,
                            "path": str(mv.get("path") or f"ReplicatedStorage.Shared.{mname}"),
                            "exports": [str(e) for e in (mv.get("exports") or []) if str(e).strip()],
                            "role": str(mv.get("role") or "shared"),
                        }
                    )

        # Attributes normalization
        raw_attrs = spec.get("attributes")
        attrs_out: Dict[str, str] = {}
        if isinstance(raw_attrs, dict):
            for ak, av in raw_attrs.items():
                attrs_out[str(ak)] = str(av)
        elif isinstance(raw_attrs, list):
            for a in raw_attrs:
                if isinstance(a, str) and a.strip():
                    attrs_out[a.strip()] = a.strip()

        return {
            "root_prefix": root_prefix,
            "remotes_folder": remotes_folder,
            "schema_version": schema_version,
            "ensure_remote_instances": ensure_remotes,
            "remotes": remotes_out,
            "tags": tags_out,
            "modules": mods_out,
            "attributes": attrs_out,
        }

    def compile_system_contracts_luau(self, contracts_spec: Optional[Dict[str, Any]] = None) -> str:
        """Compile --!strict ReplicatedStorage.Shared.SystemContracts ModuleScript installer for Studio."""
        norm = self._normalize_contracts_spec(contracts_spec)
        root_prefix = norm["root_prefix"]
        remotes_folder = norm["remotes_folder"]
        schema_version = norm["schema_version"]
        ensure_remotes = norm["ensure_remote_instances"]

        remote_entries: List[str] = []
        for rem in norm["remotes"]:
            key_lit = json.dumps(rem["key"])
            remote_entries.append(
                f"\t[{key_lit}] = {{\n"
                f"\t\tname = {json.dumps(rem['name'])},\n"
                f"\t\tkind = {json.dumps(rem['kind'])},\n"
                f"\t\tdirection = {json.dumps(rem['direction'])},\n"
                f"\t\trateLimitPerSec = {float(rem['rateLimitPerSec'])},\n"
                f"\t\tdescription = {json.dumps(rem['description'])},\n"
                f"\t}},"
            )
        remotes_block = "{\n" + "\n".join(remote_entries) + "\n}" if remote_entries else "{}"

        tag_entries: List[str] = []
        for tk, tv in norm["tags"].items():
            tag_entries.append(f"\t[{json.dumps(tk)}] = {json.dumps(tv)},")
        tags_block = "{\n" + "\n".join(tag_entries) + "\n}" if tag_entries else "{}"

        mod_entries: List[str] = []
        for mod in norm["modules"]:
            exports_lit = "{ " + ", ".join(json.dumps(e) for e in mod["exports"]) + " }"
            mod_entries.append(
                f"\t[{json.dumps(mod['key'])}] = {{\n"
                f"\t\tname = {json.dumps(mod['name'])},\n"
                f"\t\tpath = {json.dumps(mod['path'])},\n"
                f"\t\texports = table.freeze({exports_lit}),\n"
                f"\t\trole = {json.dumps(mod['role'])},\n"
                f"\t}},"
            )
        mods_block = "{\n" + "\n".join(mod_entries) + "\n}" if mod_entries else "{}"

        attr_entries: List[str] = []
        for ak, av in norm["attributes"].items():
            attr_entries.append(f"\t[{json.dumps(ak)}] = {json.dumps(av)},")
        attrs_block = "{\n" + "\n".join(attr_entries) + "\n}" if attr_entries else "{}"

        contracts_module_src = f"""--!strict
--[[
	SystemContracts
	Centralized --!strict cross-script compatibility contract for Remotes,
	CollectionService Tags, Attributes, and ModuleScript export interfaces.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")

export type RemoteKind = "RemoteEvent" | "UnreliableRemoteEvent" | "RemoteFunction"

export type RemoteContract = {{
	name: string,
	kind: RemoteKind,
	direction: string,
	rateLimitPerSec: number,
	description: string,
}}

export type ModuleContract = {{
	name: string,
	path: string,
	exports: {{ string }},
	role: string,
}}

local ROOT_PREFIX: string = {json.dumps(root_prefix)}

local SystemContracts = {{}}

SystemContracts.SchemaVersion = {json.dumps(schema_version)}
SystemContracts.RemotesFolder = {json.dumps(remotes_folder)}

SystemContracts.Remotes = table.freeze({remotes_block}) :: {{ [string]: RemoteContract }}

SystemContracts.Tags = table.freeze({tags_block}) :: {{ [string]: string }}

SystemContracts.Modules = table.freeze({mods_block}) :: {{ [string]: ModuleContract }}

SystemContracts.Attributes = table.freeze({attrs_block}) :: {{ [string]: string }}

local function resolveContractsRoot(): Instance
	if ROOT_PREFIX ~= "" then
		local prefixed = ReplicatedStorage:FindFirstChild(ROOT_PREFIX)
		if prefixed then
			return prefixed
		end
	end
	return ReplicatedStorage
end

local function ensureRemoteChild(remotesFolder: Folder, contract: RemoteContract): Instance
	local existing = remotesFolder:FindFirstChild(contract.name)
	if existing then
		return existing
	end
	local className = if contract.kind == "RemoteFunction"
		then "RemoteFunction"
		elseif contract.kind == "UnreliableRemoteEvent" then "UnreliableRemoteEvent"
		else "RemoteEvent"
	local remote = Instance.new(className)
	remote.Name = contract.name
	remote:SetAttribute("Direction", contract.direction)
	remote:SetAttribute("LuauSkillContractManaged", true)
	remote.Parent = remotesFolder
	return remote
end

function SystemContracts.GetRemotesFolder(timeoutSeconds: number?): Folder?
	local root = resolveContractsRoot()
	local existing = root:FindFirstChild(SystemContracts.RemotesFolder)
	if existing and existing:IsA("Folder") then
		return existing
	end
	if timeoutSeconds and timeoutSeconds > 0 then
		local waited = root:WaitForChild(SystemContracts.RemotesFolder, timeoutSeconds)
		if waited and waited:IsA("Folder") then
			return waited
		end
	end
	return nil
end

function SystemContracts.EnsureRemotes(parentOverride: Instance?): Folder
	local root: Instance = parentOverride or ReplicatedStorage
	if parentOverride == nil and ROOT_PREFIX ~= "" then
		local prefixed = ReplicatedStorage:FindFirstChild(ROOT_PREFIX)
		if not prefixed then
			local createdPrefix = Instance.new("Folder")
			createdPrefix.Name = ROOT_PREFIX
			createdPrefix:SetAttribute("LuauSkillContractManaged", true)
			createdPrefix.Parent = ReplicatedStorage
			prefixed = createdPrefix
		end
		root = prefixed :: Instance
	end

	local folderInst = root:FindFirstChild(SystemContracts.RemotesFolder)
	local remotesFolder: Folder
	if folderInst and folderInst:IsA("Folder") then
		remotesFolder = folderInst
	else
		local created = Instance.new("Folder")
		created.Name = SystemContracts.RemotesFolder
		created:SetAttribute("LuauSkillContractManaged", true)
		created.Parent = root
		remotesFolder = created
	end

	for _, contract in SystemContracts.Remotes do
		ensureRemoteChild(remotesFolder, contract)
	end

	return remotesFolder
end

function SystemContracts.GetRemote(name: string, timeoutSeconds: number?): Instance?
	local folder = SystemContracts.GetRemotesFolder(timeoutSeconds)
	if not folder then
		return nil
	end
	local direct = folder:FindFirstChild(name)
	if direct then
		return direct
	end
	if timeoutSeconds and timeoutSeconds > 0 then
		return folder:WaitForChild(name, timeoutSeconds)
	end
	return nil
end

function SystemContracts.GetRemoteContract(name: string): RemoteContract?
	for key, contract in SystemContracts.Remotes do
		if key == name or contract.name == name then
			return contract
		end
	end
	return nil
end

function SystemContracts.GetModuleContract(name: string): ModuleContract?
	return SystemContracts.Modules[name]
end

function SystemContracts.HasTagContract(tagName: string): boolean
	for _, value in SystemContracts.Tags do
		if value == tagName then
			return true
		end
	end
	return false
end

return SystemContracts
"""

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local ROOT_PREFIX: string = {json.dumps(root_prefix)}
local ENSURE_REMOTES: boolean = {"true" if ensure_remotes else "false"}

local function ensureFolder(parent: Instance, name: string): Folder
	local found = parent:FindFirstChild(name)
	if found and found:IsA("Folder") then
		return found
	end
	local created = Instance.new("Folder")
	created.Name = name
	created:SetAttribute("LuauSkillContractManaged", true)
	created.Parent = parent
	return created
end

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else (ChangeHistoryService :: any):TryBeginRecording("SharpSystemContracts", "Sharp MCP: Install SystemContracts")
local ok, resOrErr = xpcall(function()
	local targetRoot: Instance = if ROOT_PREFIX ~= "" then ensureFolder(ReplicatedStorage, ROOT_PREFIX) else ReplicatedStorage
	local sharedFolder = ensureFolder(targetRoot, "Shared")
	local oldMod = sharedFolder:FindFirstChild("SystemContracts")
	if oldMod then
		oldMod:Destroy()
	end

	local mod = Instance.new("ModuleScript")
	mod.Name = "SystemContracts"
	mod:SetAttribute("LuauSkillContractManaged", true)
	mod:SetAttribute("LuauSkillScaffoldManaged", true)
	mod.Source = [========[{contracts_module_src}]========]
	mod.Parent = sharedFolder

	local remotesFolderPath = ""
	if ENSURE_REMOTES then
		local okReq, loaded = pcall(require, mod)
		if okReq and type(loaded) == "table" and type((loaded :: any).EnsureRemotes) == "function" then
			local rf = (loaded :: any).EnsureRemotes()
			remotesFolderPath = rf:GetFullName()
		end
	end

	return {{
		modulePath = mod:GetFullName(),
		remotesFolder = remotesFolderPath,
		remotesCount = {len(norm['remotes'])},
		tagsCount = {len(norm['tags'])},
		modulesCount = {len(norm['modules'])},
		attributesCount = {len(norm['attributes'])},
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
	report = resOrErr,
}})
"""

    def compile_smoke_test_luau(self, roots: Optional[List[str]] = None) -> str:
        """Compile read-only Studio Luau smoke test running pcall(require, mod) across ModuleScripts."""
        target_roots = roots or ["ReplicatedStorage", "ServerScriptService", "StarterPlayerScripts"]
        roots_lit = "{ " + ", ".join(json.dumps(r) for r in target_roots) + " }"

        return f"""--!strict
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")
local StarterPlayer = game:GetService("StarterPlayer")

local TARGET_ROOTS: {{ string }} = {roots_lit}

local function resolveContainer(name: string): (string, Instance?)
	if name == "ReplicatedStorage" then
		return name, ReplicatedStorage
	elseif name == "ServerScriptService" then
		return name, ServerScriptService
	elseif name == "StarterPlayerScripts" then
		local sps = StarterPlayer:FindFirstChild("StarterPlayerScripts")
		return name, sps
	end
	local segments = string.split(name, ".")
	local okSvc, root = pcall(function()
		return game:GetService(segments[1])
	end)
	if not (okSvc and root) then
		return name, nil
	end
	local cur: Instance = root
	for idx = 2, #segments do
		local nextInst = cur:FindFirstChild(segments[idx])
		if not nextInst then
			return name, nil
		end
		cur = nextInst
	end
	return name, cur
end

local modulesToTest: {{ {{ mod: ModuleScript, container: string, path: string }} }} = {{}}
local missingContainers: {{ string }} = {{}}

for _, rootName in ipairs(TARGET_ROOTS) do
	local label, container = resolveContainer(rootName)
	if container then
		for _, desc in ipairs(container:GetDescendants()) do
			if desc:IsA("ModuleScript") then
				local fullName = desc:GetFullName()
				if string.find(fullName, "SharpBridgePlugin", 1, true) == nil
					and string.find(fullName, "SharpVisualTools", 1, true) == nil
					and desc:GetAttribute("LuauSkillAuditIgnore") ~= true
				then
					table.insert(modulesToTest, {{
						mod = desc,
						container = label,
						path = fullName,
					}})
				end
			end
		end
	else
		table.insert(missingContainers, label)
	end
end

table.sort(modulesToTest, function(a, b)
	return a.path < b.path
end)

local passed: {{ {{ path: string, container: string, returnType: string }} }} = {{}}
local failed: {{ {{ path: string, container: string, error: string }} }} = {{}}

for _, entry in ipairs(modulesToTest) do
	local okReq, resOrErr = pcall(require, entry.mod)
	if okReq then
		table.insert(passed, {{
			path = entry.path,
			container = entry.container,
			returnType = typeof(resOrErr),
		}})
	else
		table.insert(failed, {{
			path = entry.path,
			container = entry.container,
			error = tostring(resOrErr),
		}})
	end
end

return HttpService:JSONEncode({{
	ok = (#failed == 0),
	allPassed = (#failed == 0),
	totalModules = #modulesToTest,
	passedCount = #passed,
	failedCount = #failed,
	missingContainers = missingContainers,
	passed = passed,
	failed = failed,
}})
"""

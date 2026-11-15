--!strict
--[[
	ArchitectureSecurityAudit
	Read-only DataModel auditor that inspects Roblox Studio places (or scoped roots)
	and returns structured PASS / WARN / FAIL findings for common Explorer placement,
	networking, security, physics authority, and modern Luau hygiene pitfalls.
]]

export type Severity = "PASS" | "WARN" | "FAIL"

export type AuditFinding = {
	id: string,
	severity: Severity,
	path: string,
	message: string,
	recommendation: string,
}

export type AuditSummary = {
	pass: number,
	warn: number,
	fail: number,
	totalFindings: number,
	totalScriptsScanned: number,
}

export type AuditOptions = {
	roots: { Instance }?,
	checkWorkspaceParts: boolean?,
	checkServicesConfig: boolean?,
}

export type AuditReport = {
	summary: AuditSummary,
	findings: { AuditFinding },
}

local DEPRECATED_GLOBALS = {
	{ token = "wa" .. "it", replacement = "task.wait" },
	{ token = "sp" .. "awn", replacement = "task.spawn" },
	{ token = "de" .. "lay", replacement = "task.delay" },
}

local SECRET_NAME_PATTERNS = {
	"secret",
	"apikey",
	"api_key",
	"admin",
	"webhook",
	"privatekey",
	"serverconfig",
	"datastore",
	"loottable",
}

local REPLICATED_SERVICE_NAMES = {
	"Workspace",
	"ReplicatedFirst",
	"ReplicatedStorage",
	"StarterGui",
	"StarterPack",
	"StarterPlayer",
	"Teams",
	"SoundService",
}

local DEFAULT_SCAN_SERVICES = {
	"Workspace",
	"Lighting",
	"MaterialService",
	"ReplicatedFirst",
	"ReplicatedStorage",
	"ServerScriptService",
	"ServerStorage",
	"StarterGui",
	"StarterPack",
	"StarterPlayer",
	"Teams",
	"SoundService",
	"TextChatService",
}

local ArchitectureSecurityAudit = {}

local function safeGetService(name: string): Instance?
	local ok, svc = pcall(function()
		return game:GetService(name)
	end)
	if ok then
		return svc
	end
	return nil
end

local function safeReadSource(inst: Instance): string?
	if not inst:IsA("LuaSourceContainer") then
		return nil
	end
	local ok, src = pcall(function()
		return (inst :: any).Source :: string
	end)
	if ok and type(src) == "string" then
		return src
	end
	return nil
end

local function stripCommentsForScan(src: string): string
	-- Strip block comments first, then single-line comments
	local noBlocks = string.gsub(src, "%-%-%[%[.-%]%]", "")
	local noLines = string.gsub(noBlocks, "%-%-[^\r\n]*", "")
	return noLines
end

local function hasBareCall(cleanSrc: string, token: string): boolean
	local idx = 1
	while true do
		local s, e = string.find(cleanSrc, token, idx, true)
		if not s or not e then
			break
		end
		local before = if s > 1 then string.sub(cleanSrc, s - 1, s - 1) else ""
		local after = string.sub(cleanSrc, e + 1)
		local validPrev = (before == "" or string.match(before, "[%w_.:]") == nil)
		local validNext = (string.match(after, "^%s*%(") ~= nil)
		if validPrev and validNext then
			return true
		end
		idx = e + 1
	end
	return false
end

local function isInsideService(inst: Instance, serviceName: string): boolean
	local svc = safeGetService(serviceName)
	return svc ~= nil and inst:IsDescendantOf(svc)
end

local function isInAnyReplicatedContainer(inst: Instance): boolean
	for _, svcName in REPLICATED_SERVICE_NAMES do
		if isInsideService(inst, svcName) then
			return true
		end
	end
	return false
end

local function modelHasPhysicsRigOrVehicle(model: Instance): boolean
	for _, child in model:GetDescendants() do
		if
			child:IsA("Humanoid")
			or child:IsA("VehicleSeat")
			or child:IsA("Seat")
			or child:IsA("AnimationController")
			or child:IsA("Constraint")
			or child:IsA("JointInstance")
		then
			return true
		end
	end
	return false
end

local function matchesSecretKeyword(name: string): string?
	local lower = string.lower(name)
	for _, kw in SECRET_NAME_PATTERNS do
		if string.find(lower, kw, 1, true) ~= nil then
			return kw
		end
	end
	return nil
end

local function addFinding(report: AuditReport, finding: AuditFinding)
	table.insert(report.findings, finding)
	if finding.severity == "PASS" then
		report.summary.pass += 1
	elseif finding.severity == "WARN" then
		report.summary.warn += 1
	else
		report.summary.fail += 1
	end
	report.summary.totalFindings += 1
end

local function inspectScriptInstance(report: AuditReport, inst: Instance, checkWorkspaceParts: boolean)
	if inst:GetAttribute("LuauSkillAuditIgnore") == true then
		return
	end

	-- SEC-01: Scripts inside ServerStorage never execute
	if inst:IsA("Script") and isInsideService(inst, "ServerStorage") then
		addFinding(report, {
			id = "SEC-01",
			severity = "FAIL",
			path = inst:GetFullName(),
			message = "Executable Script placed inside ServerStorage (Scripts inside ServerStorage do not run).",
			recommendation = "Move server Script to ServerScriptService or convert into a ModuleScript required by ServerScriptService.",
		})
	end

	-- SEC-03: Replicated container exposure checks
	if isInAnyReplicatedContainer(inst) then
		if inst:IsA("Script") and inst.RunContext == Enum.RunContext.Server then
			addFinding(report, {
				id = "SEC-03",
				severity = "WARN",
				path = inst:GetFullName(),
				message = "Script with RunContext.Server located inside a replicated container instead of ServerScriptService.",
				recommendation = "Keep all server Scripts in ServerScriptService to isolate server architecture from clients.",
			})
		end

		local kw = matchesSecretKeyword(inst.Name)
		if kw then
			addFinding(report, {
				id = "SEC-03",
				severity = "WARN",
				path = inst:GetFullName(),
				message = `Replicated script/module name matches sensitive keyword '{kw}'; all replicated bytecode can be decompiled.`,
				recommendation = "Verify no secrets, admin keys, or server-only reward/drop formulas exist here; move server logic to ServerScriptService/ServerStorage.",
			})
		end

		-- ARCH-02: Scattered legacy scripts directly under BaseParts/Models in Workspace
		if checkWorkspaceParts and isInsideService(inst, "Workspace") and (inst:IsA("Script") or inst:IsA("LocalScript")) then
			if inst.Parent and (inst.Parent:IsA("BasePart") or inst.Parent:IsA("Model")) then
				addFinding(report, {
					id = "ARCH-02",
					severity = "WARN",
					path = inst:GetFullName(),
					message = `Legacy per-object {inst.ClassName} attached inside Workspace {inst.Parent.ClassName}.`,
					recommendation = "Tag the object with CollectionService and drive behavior from one modular service in ServerScriptService or StarterPlayerScripts.",
				})
			end
		end
	end

	local src = safeReadSource(inst)
	if src == nil then
		return
	end

	report.summary.totalScriptsScanned += 1

	-- ARCH-01: Missing --!strict directive (ignoring tiny 1-line comments if intentional)
	local firstLine = string.match(src, "^([^\r\n]*)") or ""
	if string.find(firstLine, "--!strict", 1, true) == nil then
		local sev: Severity = "WARN"
		local msg = "Missing '--!strict' type-checking directive on line 1."
		if string.find(firstLine, "--!nocheck", 1, true) ~= nil then
			msg = "Script explicitly disables type checking with '--!nocheck'."
		end
		addFinding(report, {
			id = "ARCH-01",
			severity = sev,
			path = inst:GetFullName(),
			message = msg,
			recommendation = "Add '--!strict' on line 1 to catch nil/type bugs before runtime.",
		})
	end

	local cleanSrc = stripCommentsForScan(src)

	-- SEC-04: Deprecated blocking scheduler calls
	for _, dep in DEPRECATED_GLOBALS do
		if hasBareCall(cleanSrc, dep.token) then
			addFinding(report, {
				id = "SEC-04",
				severity = "FAIL",
				path = inst:GetFullName(),
				message = `Deprecated scheduler call '{dep.token}(...)' detected.`,
				recommendation = `Replace with '{dep.replacement}(...)' to avoid 30Hz throttling.`,
			})
		end
	end

	-- SEC-05: RemoteFunction:InvokeClient hang/crash hazard
	if string.find(cleanSrc, ":InvokeClient", 1, true) ~= nil then
		addFinding(report, {
			id = "SEC-05",
			severity = "FAIL",
			path = inst:GetFullName(),
			message = "RemoteFunction:InvokeClient(...) usage detected.",
			recommendation = "Replace InvokeClient with one-way RemoteEvent:FireClient + server timeout validation; clients can hang or throw errors.",
		})
	end
end

function ArchitectureSecurityAudit.Run(options: AuditOptions?): AuditReport
	local opts: AuditOptions = options or {}
	local checkWorkspaceParts = if opts.checkWorkspaceParts == nil then true else opts.checkWorkspaceParts
	local checkServicesConfig = if opts.checkServicesConfig == nil then (opts.roots == nil) else opts.checkServicesConfig

	local report: AuditReport = {
		summary = {
			pass = 0,
			warn = 0,
			fail = 0,
			totalFindings = 0,
			totalScriptsScanned = 0,
		},
		findings = {},
	}

	-- Global Service Security & StarterGui Checks
	if checkServicesConfig then
		local sss = safeGetService("ServerScriptService") :: ServerScriptService?
		if sss then
			local okLoad, loadEnabled = pcall(function()
				return (sss :: any).LoadStringEnabled
			end)
			if not okLoad then
				addFinding(report, {
					id = "SEC-02",
					severity = "PASS",
					path = "ServerScriptService.LoadStringEnabled",
					message = "ServerScriptService.LoadStringEnabled is restricted/NotScriptable in this identity.",
					recommendation = "Verify LoadStringEnabled remains unchecked in Studio Explorer Properties.",
				})
			elseif loadEnabled then
				addFinding(report, {
					id = "SEC-02",
					severity = "FAIL",
					path = "ServerScriptService.LoadStringEnabled",
					message = "ServerScriptService.LoadStringEnabled is enabled (RCE risk).",
					recommendation = "Set ServerScriptService.LoadStringEnabled = false.",
				})
			else
				addFinding(report, {
					id = "SEC-02",
					severity = "PASS",
					path = "ServerScriptService.LoadStringEnabled",
					message = "ServerScriptService.LoadStringEnabled is disabled (false).",
					recommendation = "Keep false in production.",
				})
			end
		end

		local soundSvc = safeGetService("SoundService") :: SoundService?
		if soundSvc then
			local okRespect, respectEnabled = pcall(function()
				return (soundSvc :: any).RespectFilteringEnabled
			end)
			if not okRespect then
				addFinding(report, {
					id = "SEC-06",
					severity = "WARN",
					path = "SoundService.RespectFilteringEnabled",
					message = "SoundService.RespectFilteringEnabled could not be read in this execution context.",
					recommendation = "Verify SoundService.RespectFilteringEnabled = true in Studio Properties.",
				})
			elseif not respectEnabled then
				addFinding(report, {
					id = "SEC-06",
					severity = "FAIL",
					path = "SoundService.RespectFilteringEnabled",
					message = "SoundService.RespectFilteringEnabled is false (clients can globally play sounds).",
					recommendation = "Set SoundService.RespectFilteringEnabled = true.",
				})
			else
				addFinding(report, {
					id = "SEC-06",
					severity = "PASS",
					path = "SoundService.RespectFilteringEnabled",
					message = "SoundService.RespectFilteringEnabled is true.",
					recommendation = "Keep true.",
				})
			end
		end

		-- ARCH-04: ResetOnSpawn = false nested inside Folder under StarterGui
		local starterGui = safeGetService("StarterGui")
		if starterGui then
			for _, desc in starterGui:GetDescendants() do
				if desc:IsA("ScreenGui") then
					if not desc.ResetOnSpawn and desc.Parent ~= starterGui then
						addFinding(report, {
							id = "ARCH-04",
							severity = "WARN",
							path = desc:GetFullName(),
							message = "ScreenGui with ResetOnSpawn = false is nested inside a non-root container.",
							recommendation = "Make ScreenGui a direct child of StarterGui so ResetOnSpawn = false persists across respawns.",
						})
					end
				end
			end
		end
	end

	-- Collect scan roots
	local roots: { Instance } = {}
	if opts.roots then
		roots = opts.roots
	else
		for _, svcName in DEFAULT_SCAN_SERVICES do
			local svc = safeGetService(svcName)
			if svc then
				table.insert(roots, svc)
			end
		end
	end

	local serverStorageScriptFails = 0
	for _, root in roots do
		local candidates: { Instance } = { root }
		for _, d in root:GetDescendants() do
			table.insert(candidates, d)
		end

		for _, inst in candidates do
			if inst:IsA("LuaSourceContainer") then
				local beforeFails = report.summary.fail
				inspectScriptInstance(report, inst, checkWorkspaceParts)
				if inst:IsA("Script") and isInsideService(inst, "ServerStorage") and report.summary.fail > beforeFails then
					serverStorageScriptFails += 1
				end
			elseif checkWorkspaceParts and inst:IsA("BasePart") and not inst:IsA("Terrain") then
				if isInsideService(inst, "Workspace") and not inst.Anchored then
					local modelAncestor = inst:FindFirstAncestorOfClass("Model")
					local inRigOrVehicle = modelAncestor ~= nil and modelHasPhysicsRigOrVehicle(modelAncestor)
					local okConn, connected = pcall(function()
						return inst:GetConnectedParts(true)
					end)
					local hasAnchoredWeld = false
					if okConn and type(connected) == "table" then
						for _, other in connected :: { Instance } do
							if other:IsA("BasePart") and other.Anchored then
								hasAnchoredWeld = true
								break
							end
						end
					end
					if not inRigOrVehicle and not hasAnchoredWeld then
						addFinding(report, {
							id = "ARCH-03",
							severity = "WARN",
							path = inst:GetFullName(),
							message = "Unanchored BasePart in Workspace with no Humanoid/Vehicle/Constraint rig or anchored weld.",
							recommendation = "Anchor static props/architecture (Anchored = true), or lock ownership server-side via SetNetworkOwner(nil) if dynamic.",
						})
					end
				end
			end
		end
	end

	if checkServicesConfig and serverStorageScriptFails == 0 then
		addFinding(report, {
			id = "SEC-01",
			severity = "PASS",
			path = "ServerStorage",
			message = "Zero executable Scripts misplaced inside ServerStorage.",
			recommendation = "Continue placing executable server Scripts in ServerScriptService only.",
		})
	end

	return report
end

return ArchitectureSecurityAudit

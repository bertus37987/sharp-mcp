--!strict
--[[
	StudioRuntimeSmokeTest
	Self-contained, isolated verification suite for Studio Edit/Run testing.
	Tests:
	  1. ProjectScaffold idempotent apply + cleanup (when module injected or found as sibling).
	  2. SafeRemoteGateway valid payload pass, bad-type/NaN/Inf/mixed-table reject, and token-bucket rate limiting.
	  3. ArchitectureSecurityAudit detection of intentionally planted insecure fixtures (SEC-01, ARCH-01).
	  4. CollectionService tag add/remove signals + Instance Attribute sync.
	  5. Parallel Luau Actor ownership, SharedTable atomic increment, SharedTableRegistry cleanup,
	     Actor:SendMessage, and live task.desynchronize/synchronize when invoked inside an Actor context.
	  6. Complete cleanup verification leaving zero temporary instances or connections.
]]

local CollectionService = game:GetService("CollectionService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local SharedTableRegistry = game:GetService("SharedTableRegistry")
local Workspace = game:GetService("Workspace")

export type SmokeDependencies = {
	scaffold: any?,
	gateway: any?,
	audit: any?,
}

export type SmokeResult = {
	allPassed: boolean,
	passed: { string },
	failed: { string },
	skipped: { string },
	details: { [string]: any },
	cleanupVerified: boolean,
}

local StudioRuntimeSmokeTest = {}

local function resolveModule(provided: any, siblingName: string): any
	if provided ~= nil then
		return provided
	end
	if typeof(script) == "Instance" and script.Parent then
		local sibling = script.Parent:FindFirstChild(siblingName)
		if sibling and sibling:IsA("ModuleScript") then
			local ok, mod = pcall(require, sibling)
			if ok then
				return mod
			end
		end
	end
	return nil
end

local function recordPass(res: SmokeResult, name: string, detail: any?)
	table.insert(res.passed, name)
	if detail ~= nil then
		res.details[name] = detail
	end
end

local function recordFail(res: SmokeResult, name: string, errMsg: string)
	table.insert(res.failed, `{name}: {errMsg}`)
	res.allPassed = false
	res.details[name] = { error = errMsg }
end

local function recordSkip(res: SmokeResult, name: string, reason: string)
	table.insert(res.skipped, `{name}: {reason}`)
	res.details[name] = { skipped = reason }
end

function StudioRuntimeSmokeTest.Run(deps: SmokeDependencies?): SmokeResult
	local passedDeps: SmokeDependencies = deps or {}
	local scaffoldMod = resolveModule(passedDeps.scaffold, "project_scaffold")
	local gatewayMod = resolveModule(passedDeps.gateway, "safe_remote_gateway")
	local auditMod = resolveModule(passedDeps.audit, "architecture_security_audit")

	local nonce = `{math.floor(os.clock() * 1000)}_{math.random(1000, 9999)}`
	local tmpPrefix = `_LuauSkillSmoke_{nonce}`
	local sharedTableKey = `_LuauSkillSmokeST_{nonce}`

	local result: SmokeResult = {
		allPassed = true,
		passed = {},
		failed = {},
		skipped = {},
		details = {},
		cleanupVerified = false,
	}

	local tempWorkspaceFolder = Instance.new("Folder")
	tempWorkspaceFolder.Name = tmpPrefix
	tempWorkspaceFolder.Parent = Workspace

	local tempRemotesFolder = Instance.new("Folder")
	tempRemotesFolder.Name = tmpPrefix
	tempRemotesFolder.Parent = ReplicatedStorage

	local tempServerStorageFolder = Instance.new("Folder")
	tempServerStorageFolder.Name = tmpPrefix
	tempServerStorageFolder.Parent = ServerStorage

	local connections: { RBXScriptConnection } = {}
	local gatewayInstance: any = nil

	local function track(conn: RBXScriptConnection)
		table.insert(connections, conn)
	end

	-- Wrap test suite in pcall so cleanup ALWAYS executes cleanly
	local suiteOk, suiteErr = pcall(function()
		-- 1. ProjectScaffold idempotency & cleanup
		if scaffoldMod then
			local firstReport = scaffoldMod.Apply({
				rootPrefix = `{tmpPrefix}_Scaffold`,
				tag = `Tag_{tmpPrefix}`,
			})
			local secondReport = scaffoldMod.Apply({
				rootPrefix = `{tmpPrefix}_Scaffold`,
				tag = `Tag_{tmpPrefix}`,
			})
			local cleanupReport = scaffoldMod.Cleanup({
				rootPrefix = `{tmpPrefix}_Scaffold`,
				tag = `Tag_{tmpPrefix}`,
			})
			if #firstReport.created > 0 and #secondReport.created == 0 and cleanupReport.remainingCount == 0 then
				recordPass(result, "ProjectScaffold_Idempotency_And_Cleanup", {
					createdFirst = #firstReport.created,
					createdSecond = #secondReport.created,
					removed = #cleanupReport.removed,
				})
			else
				recordFail(
					result,
					"ProjectScaffold_Idempotency_And_Cleanup",
					`first={#firstReport.created}, second={#secondReport.created}, rem={cleanupReport.remainingCount}`
				)
			end
		else
			recordSkip(result, "ProjectScaffold_Idempotency_And_Cleanup", "project_scaffold module not provided")
		end

		-- 2. SafeRemoteGateway schema validation + token bucket rate limit
		if gatewayMod then
			local nowClock = 100.0
			local drops: { string } = {}
			local acceptedCount = 0

			local gw = gatewayMod.Create(tempRemotesFolder, {
				clock = function(): number
					return nowClock
				end,
				onDrop = function(_player: Player?, _route: string, reason: string)
					table.insert(drops, reason)
				end,
			})
			gatewayInstance = gw

			gw:RegisterReliable(
				"EquipSlot",
				{
					args = {
						{ kind = "integer", min = 1, max = 9 },
						{
							kind = "table",
							maxDepth = 2,
							keys = {
								tag = { kind = "string", maxLength = 16 },
							},
						},
					},
				},
				{ capacity = 2, refillPerSecond = 1 },
				function(_player: Player, _slot: number, _meta: { tag: string })
					acceptedCount += 1
				end
			)

			gw:RegisterUnreliable(
				"LookTelemetry",
				{ args = { { kind = "Vector3" } } },
				{ capacity = 1, refillPerSecond = 2 },
				function(_player: Player, _dir: Vector3) end
			)

			local mockPlayer = { UserId = 424242, Name = "SmokeTester" }

			local okValid = gw:SimulateIncoming("EquipSlot", mockPlayer, 3, { tag = "sword" })
			local okBadType, errBadType = gw:SimulateIncoming("EquipSlot", mockPlayer, "not_int", { tag = "sword" })
			-- Consume remaining token with bad-schema? No, rate limit runs first, so replenish time cleanly:
			nowClock += 5.0
			local okMixedTable, errMixed = gw:SimulateIncoming("EquipSlot", mockPlayer, 2, { tag = "ok", [1] = "mixed" } :: any)
			nowClock += 5.0
			local okNaN, errNaN = gw:SimulateIncoming("LookTelemetry", mockPlayer, Vector3.new(0 / 0, 1, 0))
			local okSparse, errSparse = gatewayMod.ValidateArgs({ args = { { kind = "table" } } }, { [1] = "a", [3] = "c" })

			-- Test burst rate limit: capacity = 2, zero time elapsed -> 2 pass, 3rd drops
			nowClock += 5.0
			local b1 = gw:SimulateIncoming("EquipSlot", mockPlayer, 1, { tag = "a" })
			local b2 = gw:SimulateIncoming("EquipSlot", mockPlayer, 2, { tag = "b" })
			local b3, errB3 = gw:SimulateIncoming("EquipSlot", mockPlayer, 3, { tag = "c" })

			gw:Destroy()
			gatewayInstance = nil

			local checksOk = okValid == true
				and not okBadType and errBadType ~= nil
				and not okMixedTable and errMixed ~= nil
				and not okNaN and errNaN ~= nil
				and not okSparse and errSparse ~= nil
				and b1 == true and b2 == true and b3 == false and errB3 == "rate limit exceeded"
				and acceptedCount == 3

			if checksOk then
				recordPass(result, "SafeRemoteGateway_Schema_And_RateLimit", {
					accepted = acceptedCount,
					dropsCaptured = #drops,
					mixedReason = errMixed,
					nanReason = errNaN,
				})
			else
				recordFail(
					result,
					"SafeRemoteGateway_Schema_And_RateLimit",
					`okValid={okValid}, okBad={okBadType}, okMix={okMixedTable}, okNaN={okNaN}, burst=({b1},{b2},{b3})`
				)
			end
		else
			recordSkip(result, "SafeRemoteGateway_Schema_And_RateLimit", "safe_remote_gateway module not provided")
		end

		-- 3. ArchitectureSecurityAudit on controlled isolated bad fixtures
		if auditMod then
			local badScript = Instance.new("Script")
			badScript.Name = "BrokenInServerStorage"
			badScript.Disabled = true
			badScript.Source = "local x = 1\n" -- intentionally missing --!strict
			badScript.Parent = tempServerStorageFolder

			local loosePart = Instance.new("Part")
			loosePart.Name = "StrayUnanchoredPart"
			loosePart.Anchored = false
			loosePart.Parent = tempWorkspaceFolder

			local auditReport = auditMod.Run({
				roots = { tempServerStorageFolder, tempWorkspaceFolder },
				checkWorkspaceParts = true,
				checkServicesConfig = false,
			})

			local hasSec01 = false
			local hasArch01 = false
			local hasArch03 = false
			for _, f in auditReport.findings do
				if f.id == "SEC-01" and f.severity == "FAIL" then
					hasSec01 = true
				elseif f.id == "ARCH-01" and f.severity == "WARN" then
					hasArch01 = true
				elseif f.id == "ARCH-03" and f.severity == "WARN" then
					hasArch03 = true
				end
			end

			if hasSec01 and hasArch01 and hasArch03 then
				recordPass(result, "ArchitectureSecurityAudit_FixtureDetection", {
					sec01 = hasSec01,
					arch01 = hasArch01,
					arch03 = hasArch03,
					summary = auditReport.summary,
				})
			else
				recordFail(
					result,
					"ArchitectureSecurityAudit_FixtureDetection",
					`Expected SEC-01/ARCH-01/ARCH-03 got sec01={hasSec01}, arch01={hasArch01}, arch03={hasArch03}`
				)
			end
		else
			recordSkip(result, "ArchitectureSecurityAudit_FixtureDetection", "architecture_security_audit module not provided")
		end

		-- 4. CollectionService + Attribute lifecycle
		local testTag = `SmokeTag_{nonce}`
		local addedCount = 0
		local removedCount = 0
		local attrValueSeen: any = nil

		local taggedPart = Instance.new("Part")
		taggedPart.Name = "TaggedLifecyclePart"
		taggedPart.Anchored = true
		taggedPart.Parent = tempWorkspaceFolder

		track(CollectionService:GetInstanceAddedSignal(testTag):Connect(function(inst: Instance)
			if inst == taggedPart then
				addedCount += 1
			end
		end))
		track(CollectionService:GetInstanceRemovedSignal(testTag):Connect(function(inst: Instance)
			if inst == taggedPart then
				removedCount += 1
			end
		end))
		track(taggedPart:GetAttributeChangedSignal("Health"):Connect(function()
			attrValueSeen = taggedPart:GetAttribute("Health")
		end))

		CollectionService:AddTag(taggedPart, testTag)
		taggedPart:SetAttribute("Health", 75)
		task.wait()
		CollectionService:RemoveTag(taggedPart, testTag)
		task.wait()

		if addedCount == 1 and removedCount == 1 and attrValueSeen == 75 then
			recordPass(result, "CollectionService_And_Attribute_Lifecycle", {
				added = addedCount,
				removed = removedCount,
				attr = attrValueSeen,
			})
		else
			recordFail(
				result,
				"CollectionService_And_Attribute_Lifecycle",
				`added={addedCount}, removed={removedCount}, attr={tostring(attrValueSeen)}`
			)
		end

		-- 5. Parallel Luau: Actor + SharedTable + SendMessage + desynchronize/synchronize
		local actor = Instance.new("Actor")
		actor.Name = "SmokeParallelActor"
		actor.Parent = tempWorkspaceFolder

		local workerNode = Instance.new("Folder")
		workerNode.Name = "WorkerChild"
		workerNode.Parent = actor

		local sharedTbl = SharedTable.new({ count = 10 })
		SharedTableRegistry:SetSharedTable(sharedTableKey, sharedTbl)
		local fetched = SharedTableRegistry:GetSharedTable(sharedTableKey)
		local prevVal = SharedTable.increment(fetched, "count", 5)

		local callerActor = if typeof(script) == "Instance" then script:GetActor() else nil
		local parallelModeUsed = "edit-caller-contract-verified"
		local messageReceived = false

		if callerActor ~= nil then
			-- Invoked directly inside an Actor VM: exercise live BindToMessage + desynchronize/synchronize
			local bindOk = pcall(function()
				callerActor:BindToMessage("SmokePing", function(payload: number)
					if payload == 99 then
						messageReceived = true
					end
				end)
				callerActor:SendMessage("SmokePing", 99)
				task.desynchronize()
				SharedTable.increment(fetched, "count", 1)
				task.synchronize()
			end)
			parallelModeUsed = if bindOk then "actor-vm-live-parallel" else "actor-vm-error"
		else
			-- Caller is outside an Actor (e.g., Studio Edit CommandBar / MCP execute_luau):
			-- verify SendMessage enqueue from non-Actor works without calling forbidden non-Actor BindToMessage/desynchronize
			actor:SendMessage("SmokePing", 99)
		end

		local finalCount = fetched["count"]
		local actorOwnerOk = workerNode:GetActor() == actor
		local sendMessageOk = callerActor == nil or messageReceived
		SharedTableRegistry:SetSharedTable(sharedTableKey, nil)

		if actorOwnerOk and prevVal == 10 and finalCount >= 15 and sendMessageOk then
			recordPass(result, "ParallelLuau_Actor_And_SharedTable", {
				actorOwnerOk = actorOwnerOk,
				prevCount = prevVal,
				finalCount = finalCount,
				mode = parallelModeUsed,
				isRunning = RunService:IsRunning(),
			})
		else
			recordFail(
				result,
				"ParallelLuau_Actor_And_SharedTable",
				`actorOwner={actorOwnerOk}, prev={prevVal}, final={finalCount}, msg={sendMessageOk}`
			)
		end
	end)

	-- Guaranteed cleanup
	if gatewayInstance then
		pcall(function()
			gatewayInstance:Destroy()
		end)
	end
	for _, conn in connections do
		if conn.Connected then
			conn:Disconnect()
		end
	end
	pcall(function()
		SharedTableRegistry:SetSharedTable(sharedTableKey, nil)
	end)
	tempWorkspaceFolder:Destroy()
	tempRemotesFolder:Destroy()
	tempServerStorageFolder:Destroy()

	result.cleanupVerified = Workspace:FindFirstChild(tmpPrefix) == nil
		and ReplicatedStorage:FindFirstChild(tmpPrefix) == nil
		and ServerStorage:FindFirstChild(tmpPrefix) == nil

	if not suiteOk then
		recordFail(result, "SmokeSuiteUnhandledError", tostring(suiteErr))
	end
	if not result.cleanupVerified then
		recordFail(result, "CleanupVerification", "Temporary smoke test folders remained in DataModel")
	end

	return result
end

return StudioRuntimeSmokeTest

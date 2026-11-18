--!strict
--[[
	SharpBridgePlugin (init.server.luau)
	Connects Roblox Studio Edit mode to Sharp MCP Server on 127.0.0.1:<port> (default 58421).
	Features:
	- Boots strictly in RunService:IsEdit() (never runs inside Playtest Server/Client VMs)
	- Cleans up leaked ChangeHistoryService recordings on reload
	- Auto-opens DockWidget on boot ONLY if HttpService.HttpEnabled == false
	- Enforces 3-tier Safety Mode (Read-Only / Safe Mutate / Full + Upload)
	- Executes incoming jobs via task.spawn with 5s /v1/heartbeat loop until completion
	- Supports direct module_op dispatch (SharpGuiTools, SharpTreeTools, & embedded skill modules)
	  AND compiledLuau inside SharpUndo.withRecording(..., verifyFn)
	- Single-encode UTF-8 boundary-safe chunking for large responses (> 900 KB)
	- Stops cleanly on plugin.Unloading
]]

local HttpService = game:GetService("HttpService")
local RunService = game:GetService("RunService")

if not plugin then
	return
end

local okEdit, isEdit = pcall(function()
	return RunService:IsEdit()
end)
if not okEdit or not isEdit then
	return
end

local SharpUndo = require(script:WaitForChild("SharpUndo"))
local DockWidget = require(script:WaitForChild("DockWidget"))
local SharpGuiTools = require(script:WaitForChild("SharpGuiTools"))
local SharpTreeTools = require(script:WaitForChild("SharpTreeTools"))

SharpUndo.cleanupLeakedRecording()

local rawPort = tonumber(plugin:GetSetting("SharpBridgePort"))
local BRIDGE_PORT = if rawPort and rawPort >= 1 and rawPort <= 65535
	then math.floor(rawPort)
	else 58421
local BRIDGE_BASE = string.format("http://127.0.0.1:%d", BRIDGE_PORT)

local ui = DockWidget.new(plugin, BRIDGE_PORT)
local isShuttingDown = false
local sessionToken = ""
local serverEpoch = ""
local studioSessionId = HttpService:GenerateGUID(false)

-- Auto-open DockWidget on boot ONLY when HttpService.HttpEnabled == false
local initialHttpEnabled = HttpService.HttpEnabled
ui:setHttpOnboarding(initialHttpEnabled)
ui:showIfNeeded(not initialHttpEnabled)

plugin.Unloading:Connect(function()
	isShuttingDown = true
	SharpUndo.cleanupLeakedRecording()
	ui:destroy()
end)

local function splitUtf8Chunks(str: string, maxBytes: number): { string }
	local chunks: { string } = {}
	local n = #str
	local pos = 1
	while pos <= n do
		local stopIdx = math.min(n, pos + maxBytes - 1)
		if stopIdx < n then
			-- Walk backward if next byte is a UTF-8 continuation byte (10xxxxxx = 0x80..0xBF)
			while stopIdx > pos do
				local nextByte = string.byte(str, stopIdx + 1)
				if nextByte and bit32.band(nextByte, 0xC0) == 0x80 then
					stopIdx -= 1
				else
					break
				end
			end
		end
		table.insert(chunks, string.sub(str, pos, stopIdx))
		pos = stopIdx + 1
	end
	return chunks
end

local function makeAuthHeaders(includeContentType: boolean): { [string]: string }
	local hdrs: { [string]: string } = {
		["Authorization"] = "Bearer " .. sessionToken,
		["X-Sharp-Server-Epoch"] = serverEpoch,
	}
	if includeContentType then
		hdrs["Content-Type"] = "application/json"
	end
	return hdrs
end

local function sendResult(requestId: string, envelope: { [string]: any })
	envelope.requestId = requestId
	envelope.placeId = game.PlaceId
	envelope.studioSessionId = studioSessionId
	local encoded = HttpService:JSONEncode(envelope)

	if #encoded <= 900000 then
		pcall(function()
			HttpService:RequestAsync({
				Url = BRIDGE_BASE .. "/v1/result",
				Method = "POST",
				Headers = makeAuthHeaders(true),
				Body = encoded,
			})
		end)
	else
		local parts = splitUtf8Chunks(encoded, 800000)
		for idx, part in ipairs(parts) do
			pcall(function()
				HttpService:RequestAsync({
					Url = BRIDGE_BASE .. "/v1/result_chunk",
					Method = "POST",
					Headers = makeAuthHeaders(true),
					Body = HttpService:JSONEncode({
						requestId = requestId,
						chunkIndex = idx,
						chunkData = part,
					}),
				})
			end)
		end
		pcall(function()
			HttpService:RequestAsync({
				Url = BRIDGE_BASE .. "/v1/result_commit",
				Method = "POST",
				Headers = makeAuthHeaders(true),
				Body = HttpService:JSONEncode({ requestId = requestId }),
			})
		end)
	end
end

local function isDestructiveRequest(toolName: string, args: { [string]: any }, compiledLuau: string?): boolean
	local opArgs = if typeof(args.args) == "table" then args.args :: { [string]: any } else {}
	if args.allowDestructive == true or args.destructive == true or opArgs.allowDestructive == true then
		return true
	end
	local lowerTool = string.lower(toolName)
	if string.find(lowerTool, "open_cloud", 1, true)
		or string.find(lowerTool, "publish", 1, true)
		or string.find(lowerTool, "wipe", 1, true)
	then
		return true
	end
	if typeof(compiledLuau) == "string" and #compiledLuau > 0 then
		if string.find(compiledLuau, "Workspace:ClearAllChildren()", 1, true)
			or string.find(compiledLuau, "StarterGui:ClearAllChildren()", 1, true)
			or string.find(compiledLuau, "ReplicatedStorage:ClearAllChildren()", 1, true)
			or string.find(compiledLuau, "ServerScriptService:ClearAllChildren()", 1, true)
		then
			return true
		end
	end
	return false
end

local function verifyMutationResult(res: any): (boolean, string?)
	if typeof(res) == "table" then
		if res.verified == false then
			local errList = res.errors
			local msg = if typeof(errList) == "table" and #errList > 0
				then table.concat(errList, "; ")
				else tostring(res.message or "Post-write readback verification failed.")
			return false, msg
		end
		if res.ok == false then
			return false, tostring(res.message or res.code or "Mutation reported ok=false.")
		end
	end
	return true, nil
end

local function dispatchModuleOpInternal(moduleName: string, opName: string, opArgs: { [string]: any }): (boolean, any)
	if moduleName == "SharpGuiTools" then
		if opName == "inspect" then
			local out = SharpGuiTools.inspect(opArgs)
			return out.ok ~= false, out
		elseif opName == "patch" then
			return SharpGuiTools.patch(opArgs)
		elseif opName == "deviceSim" then
			local out = SharpGuiTools.deviceSim(opArgs)
			return out.ok ~= false, out
		else
			return false, { code = "UNKNOWN_MODULE_OP", message = "Unknown SharpGuiTools op: " .. opName }
		end
	elseif moduleName == "SharpTreeTools" then
		if opName == "searchTree" then
			local out = SharpTreeTools.searchTree(opArgs)
			return out.ok ~= false, out
		elseif opName == "inspectInstance" then
			local out = SharpTreeTools.inspectInstance(opArgs)
			return out.ok ~= false, out
		elseif opName == "readScript" then
			local out = SharpTreeTools.readScript(opArgs)
			return out.ok ~= false, out
		elseif opName == "updateScript" then
			return SharpTreeTools.updateScript(opArgs)
		elseif opName == "readConsoleLogs" then
			local out = SharpTreeTools.readConsoleLogs(opArgs)
			return out.ok ~= false, out
		else
			return false, { code = "UNKNOWN_MODULE_OP", message = "Unknown SharpTreeTools op: " .. opName }
		end
	end

	return SharpTreeTools.dispatchModuleOp(script, moduleName, opName, opArgs)
end

local function executeJobAsync(job: { [string]: any })
	local reqId = tostring(job.requestId or "")
	local kind = tostring(job.kind or "read")
	local toolName = tostring(job.tool or "unknown")
	local args = (job.args or {}) :: { [string]: any }
	local compiledLuau = if typeof(args.compiledLuau) == "string" then args.compiledLuau else nil

	if kind == "write" and ui.safetyMode == "Read-Only" then
		ui:appendLog("[BLOCKED Read-Only] " .. toolName)
		sendResult(reqId, {
			ok = false,
			code = "SAFETY_READ_ONLY",
			message = "SharpBridgePlugin DockWidget is set to Read-Only mode.",
			recordingStatus = "Rejected",
		})
		return
	end

	if kind == "write" and ui.safetyMode == "Safe Mutate" and isDestructiveRequest(toolName, args, compiledLuau) then
		ui:appendLog("[BLOCKED Safe Mutate] " .. toolName)
		sendResult(reqId, {
			ok = false,
			code = "SAFETY_REQUIRES_FULL_UPLOAD",
			message = "Destructive or upload operations require SharpSafetyMode = 'Full + Upload'.",
			recordingStatus = "Rejected",
		})
		return
	end

	-- Start 5s heartbeat loop while job runs so lease never expires on long operations
	local jobFinished = false
	local heartbeatThread = task.spawn(function()
		while not jobFinished and not isShuttingDown do
			task.wait(5.0)
			if jobFinished or isShuttingDown or sessionToken == "" then
				break
			end
			pcall(function()
				HttpService:RequestAsync({
					Url = BRIDGE_BASE .. "/v1/heartbeat",
					Method = "POST",
					Headers = makeAuthHeaders(true),
					Body = HttpService:JSONEncode({
						requestId = reqId,
						placeId = game.PlaceId,
						studioSessionId = studioSessionId,
					}),
				})
			end)
		end
	end)

	local function finishHeartbeat()
		jobFinished = true
		pcall(task.cancel, heartbeatThread)
	end

	-- Mode A: Direct module_op dispatch (no loadstring)
	if args.mode == "module_op" then
		local moduleName = tostring(args.module or "")
		local opName = tostring(args.op or "")
		local opArgs = (if typeof(args.args) == "table" then args.args else {}) :: { [string]: any }

		local okRun: boolean = false
		local runOut: any = nil
		local recStatus: string = "None"

		local execCallOk, execErr = pcall(function()
			if kind == "write" then
				local recOk, recRes, recState = SharpUndo.withRecording(
					"Sharp_" .. moduleName .. "_" .. opName,
					"Sharp MCP: " .. moduleName .. "." .. opName,
					function()
						local opOk, opRes = dispatchModuleOpInternal(moduleName, opName, opArgs)
						if not opOk and typeof(opRes) ~= "table" then
							return { ok = false, message = tostring(opRes) }
						end
						if not opOk and typeof(opRes) == "table" and opRes.ok == nil then
							opRes.ok = false
						end
						return opRes
					end,
					verifyMutationResult
				)
				okRun = recOk
				runOut = recRes
				recStatus = recState
			else
				local opOk, opRes = dispatchModuleOpInternal(moduleName, opName, opArgs)
				okRun = opOk
				runOut = opRes
				recStatus = "None"
			end
		end)

		finishHeartbeat()

		if not execCallOk then
			okRun = false
			runOut = { code = "PLUGIN_EXEC_ERROR", message = tostring(execErr) }
			recStatus = "Cancelled"
		end

		ui:appendLog((if okRun then "[OK] " else "[ERR] ") .. moduleName .. "." .. opName)
		sendResult(reqId, {
			ok = okRun,
			result = runOut,
			recordingStatus = recStatus,
		})
		return
	end

	-- Mode B: Compiled Luau payload inside SharpUndo.withRecording(..., verifyFn)
	if compiledLuau and #compiledLuau > 0 then
		local fn, loadErr = loadstring(compiledLuau)
		if not fn then
			finishHeartbeat()
			ui:appendLog("[SYNTAX ERR] " .. toolName)
			sendResult(reqId, {
				ok = false,
				code = "LOADSTRING_SYNTAX_ERROR",
				message = tostring(loadErr),
				recordingStatus = "Rejected",
			})
			return
		end

		local okRun: boolean = false
		local runOut: any = nil
		local recStatus: string = "None"

		local execCallOk, execErr = pcall(function()
			if kind == "write" and toolName ~= "sharp_snapshot_and_undo" then
				okRun, runOut, recStatus = SharpUndo.withRecording(
					"Sharp_" .. toolName,
					"Sharp MCP: " .. toolName,
					fn :: () -> any,
					verifyMutationResult
				)
			else
				okRun, runOut = xpcall(fn :: () -> any, debug.traceback)
				recStatus = if okRun then "Committed" else "Cancelled"
			end
		end)

		finishHeartbeat()

		if not execCallOk then
			okRun = false
			runOut = { code = "PLUGIN_EXEC_ERROR", message = tostring(execErr) }
			recStatus = "Cancelled"
		end

		ui:appendLog((if okRun then "[OK] " else "[ERR] ") .. toolName)
		sendResult(reqId, {
			ok = okRun,
			result = runOut,
			recordingStatus = recStatus,
		})
		return
	end

	-- Mode C: Ping / status probe
	finishHeartbeat()
	ui:appendLog("[PING] " .. toolName)
	sendResult(reqId, {
		ok = true,
		result = {
			pong = true,
			safetyMode = ui.safetyMode,
			placeId = game.PlaceId,
			studioSessionId = studioSessionId,
		},
		recordingStatus = "None",
	})
end

task.spawn(function()
	while not isShuttingDown do
		local httpEnabled = HttpService.HttpEnabled
		ui:setHttpOnboarding(httpEnabled)

		if not httpEnabled then
			ui:setStatus("HttpService.HttpEnabled = OFF")
			task.wait(3.0)
			continue
		end

		if sessionToken == "" then
			local okHello, resp = pcall(function()
				return HttpService:RequestAsync({
					Url = BRIDGE_BASE .. "/v1/hello",
					Method = "POST",
					Headers = { ["Content-Type"] = "application/json" },
					Body = HttpService:JSONEncode({
						studioSessionId = studioSessionId,
						placeId = game.PlaceId,
						universeId = game.GameId,
						placeName = game.Name,
						pluginVersion = "0.5.0",
						safetyMode = ui.safetyMode,
						httpEnabled = httpEnabled,
						capabilities = {
							moduleOp = true,
							sharpGuiTools = true,
							sharpTreeTools = true,
							heartbeat = true,
						},
					}),
				})
			end)
			if okHello and resp and resp.StatusCode == 200 then
				local decoded = HttpService:JSONDecode(resp.Body)
				sessionToken = tostring(decoded.sessionToken or "")
				serverEpoch = tostring(decoded.serverEpoch or "")
				ui:setStatus(string.format("Connected • 127.0.0.1:%d", BRIDGE_PORT))
				ui:appendLog("Handshake OK (" .. serverEpoch .. ")")
			else
				ui:setStatus("Standby (Waiting for Sharp MCP)")
				task.wait(3.0)
				continue
			end
		end

		local okPoll, pollResp = pcall(function()
			return HttpService:RequestAsync({
				Url = BRIDGE_BASE .. "/v1/poll?timeoutMs=8000",
				Method = "GET",
				Headers = makeAuthHeaders(false),
			})
		end)

		if not okPoll or not pollResp then
			sessionToken = ""
			ui:setStatus("Disconnected • Retrying...")
			task.wait(2.0)
		elseif pollResp.StatusCode == 200 and #pollResp.Body > 0 then
			local okDec, job = pcall(function()
				return HttpService:JSONDecode(pollResp.Body)
			end)
			if okDec and type(job) == "table" then
				task.spawn(executeJobAsync, job)
			end
		elseif pollResp.StatusCode == 401 or pollResp.StatusCode == 409 then
			sessionToken = ""
			task.wait(0.5)
		else
			task.wait(0.1)
		end
	end
end)

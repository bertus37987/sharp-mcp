--!strict
--[[
	SharpUndo
	Atomic ChangeHistoryService recording engine for SharpBridgePlugin.
	1. Never sets a permanent sticky disable flag if TryBeginRecording returns nil.
	2. Supports optional post-write verifyFn(result) -> (boolean, string?) BEFORE Commit;
	   if verifyFn fails or returns false, cancels the recording cleanly.
	3. Cleans up any leaked __SharpActiveRecordingId attribute on plugin reload/startup.
]]

local ChangeHistoryService = game:GetService("ChangeHistoryService")

local REC_ID_ATTR = "__SharpActiveRecordingId"
local REC_TS_ATTR = "__SharpActiveRecordingTs"

export type VerifyFn = (any) -> (boolean, string?)

local SharpUndo = {}

function SharpUndo.cleanupLeakedRecording(): number
	local staleId = ChangeHistoryService:GetAttribute(REC_ID_ATTR)
	if typeof(staleId) == "string" and #staleId > 0 then
		pcall(function()
			ChangeHistoryService:FinishRecording(staleId, Enum.FinishRecordingOperation.Cancel)
		end)
		ChangeHistoryService:SetAttribute(REC_ID_ATTR, nil)
		ChangeHistoryService:SetAttribute(REC_TS_ATTR, nil)
		return 1
	end
	return 0
end

local function runVerify(verifyFn: VerifyFn?, res: any): (boolean, string?)
	if not verifyFn then
		return true, nil
	end
	local callOk, passOrErr, msg = pcall(verifyFn, res)
	if not callOk then
		return false, "Readback verifier threw error: " .. tostring(passOrErr)
	end
	if passOrErr == false then
		return false, msg or "Post-write readback verification failed."
	end
	return true, nil
end

function SharpUndo.withRecording(
	actionName: string,
	displayName: string,
	fn: () -> any,
	verifyFn: VerifyFn?
): (boolean, any, string)
	local existingId = ChangeHistoryService:GetAttribute(REC_ID_ATTR)
	if typeof(existingId) == "string" and #existingId > 0 then
		local okNested, resNested = xpcall(fn, debug.traceback)
		if not okNested then
			return false, { code = "EXECUTION_ERROR", message = tostring(resNested) }, "Cancelled"
		end
		local vOk, vMsg = runVerify(verifyFn, resNested)
		if not vOk then
			return false, { code = "READBACK_VERIFICATION_FAILED", message = vMsg }, "Cancelled"
		end
		return true, resNested, "Committed"
	end

	local recId = ChangeHistoryService:TryBeginRecording(actionName, displayName)
	if not recId then
		local okFallback, resFallback = xpcall(fn, debug.traceback)
		if not okFallback then
			return false, { code = "EXECUTION_ERROR", message = tostring(resFallback) }, "Cancelled"
		end
		local vOk, vMsg = runVerify(verifyFn, resFallback)
		if not vOk then
			return false, { code = "READBACK_VERIFICATION_FAILED", message = vMsg }, "Cancelled"
		end
		return true, resFallback, "NoRecording"
	end

	ChangeHistoryService:SetAttribute(REC_ID_ATTR, recId)
	ChangeHistoryService:SetAttribute(REC_TS_ATTR, os.time())

	local ok, res = xpcall(fn, debug.traceback)

	ChangeHistoryService:SetAttribute(REC_ID_ATTR, nil)
	ChangeHistoryService:SetAttribute(REC_TS_ATTR, nil)

	if not ok then
		pcall(function()
			ChangeHistoryService:FinishRecording(recId, Enum.FinishRecordingOperation.Cancel)
		end)
		return false, { code = "EXECUTION_ERROR", message = tostring(res) }, "Cancelled"
	end

	local vOk, vMsg = runVerify(verifyFn, res)
	if not vOk then
		pcall(function()
			ChangeHistoryService:FinishRecording(recId, Enum.FinishRecordingOperation.Cancel)
		end)
		return false, { code = "READBACK_VERIFICATION_FAILED", message = vMsg }, "Cancelled"
	end

	local finOk, finErr = pcall(function()
		ChangeHistoryService:FinishRecording(recId, Enum.FinishRecordingOperation.Commit)
	end)
	if not finOk then
		return false, { code = "RECORDING_COMMIT_FAILED", message = tostring(finErr) }, "CommitError"
	end
	return true, res, "Committed"
end

return SharpUndo

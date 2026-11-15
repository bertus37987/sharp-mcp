--!strict
--[[
	SharpTreeTools
	Standalone Place tree browsing, GUID SharpHandle resolution, surgical script
	reading/editing via ScriptEditorService, bounded console logs, and embedded
	ModuleScript operation dispatch for SharpBridgePlugin.
]]

local CollectionService = game:GetService("CollectionService")
local HttpService = game:GetService("HttpService")
local LogService = game:GetService("LogService")
local ScriptEditorService = game:GetService("ScriptEditorService")

local HANDLE_ATTR = "SharpHandle"

local SAFE_DATAMODEL_SERVICES: { string } = {
	"Workspace",
	"ReplicatedStorage",
	"ReplicatedFirst",
	"ServerScriptService",
	"ServerStorage",
	"StarterGui",
	"StarterPack",
	"StarterPlayer",
	"Lighting",
	"SoundService",
	"TextChatService",
	"Teams",
	"Players",
}

local SharpTreeTools = {}

local function getOrCreateHandle(inst: Instance, assignIfMissing: boolean?): string?
	local existing = inst:GetAttribute(HANDLE_ATTR)
	if typeof(existing) == "string" and #existing > 0 then
		return existing
	end
	if assignIfMissing == false then
		return nil
	end
	local handle = "sh_" .. HttpService:GenerateGUID(false)
	local ok = pcall(function()
		inst:SetAttribute(HANDLE_ATTR, handle)
	end)
	return if ok then handle else nil
end

local function getInstancePath(inst: Instance): string
	local parts: { string } = {}
	local curr: Instance? = inst
	while curr and curr ~= game do
		table.insert(parts, 1, curr.Name)
		curr = curr.Parent
	end
	return table.concat(parts, ".")
end

local function resolvePath(pathStr: string): Instance?
	if pathStr == "" then
		return nil
	end
	local cleaned = pathStr
	if cleaned == "game" then
		return game
	end
	if string.sub(cleaned, 1, 5) == "game." then
		cleaned = string.sub(cleaned, 6)
	end
	local curr: Instance = game
	local first = true
	for segment in string.gmatch(cleaned, "[^%.]+") do
		local nxt: Instance? = nil
		if first and curr == game then
			local okSvc, svc = pcall(function()
				return game:GetService(segment)
			end)
			if okSvc and svc then
				nxt = svc
			else
				nxt = game:FindFirstChild(segment)
			end
			first = false
		else
			nxt = curr:FindFirstChild(segment)
		end
		if not nxt then
			return nil
		end
		curr = nxt
	end
	return curr
end

local function getSafeRoots(): { Instance }
	local roots: { Instance } = {}
	for _, svcName in ipairs(SAFE_DATAMODEL_SERVICES) do
		local ok, svc = pcall(function()
			return game:GetService(svcName)
		end)
		if ok and svc then
			table.insert(roots, svc)
		end
	end
	return roots
end

local function findByHandle(handle: string): Instance?
	for _, root in ipairs(getSafeRoots()) do
		local okRootAttr, rootAttr = pcall(function()
			return root:GetAttribute(HANDLE_ATTR)
		end)
		if okRootAttr and rootAttr == handle then
			return root
		end
		local okDesc, descs = pcall(function()
			return root:GetDescendants()
		end)
		if okDesc and typeof(descs) == "table" then
			for _, desc in ipairs(descs) do
				local okAttr, attr = pcall(function()
					return desc:GetAttribute(HANDLE_ATTR)
				end)
				if okAttr and attr == handle then
					return desc
				end
			end
		end
	end
	return nil
end

local function resolveTarget(args: { [string]: any }): Instance?
	local handle = args.sharpHandle or args.handle
	if typeof(handle) == "string" and #handle > 0 then
		local found = findByHandle(handle)
		if found then
			return found
		end
	end
	local pathStr = args.path or args.rootPath
	if typeof(pathStr) == "string" and #pathStr > 0 then
		return resolvePath(pathStr)
	end
	return nil
end

local function computeRevision(source: string): string
	-- Deterministic 32-bit FNV-1a checksum paired with byte length for optimistic edit checks
	local hash = 2166136261
	for i = 1, #source do
		hash = bit32.bxor(hash, string.byte(source, i))
		hash = (hash * 16777619) % 4294967296
	end
	return string.format("%d:%08x", #source, hash)
end

local function encodeSimpleValue(val: any): any
	local t = typeof(val)
	if val == nil or t == "boolean" or t == "number" or t == "string" then
		return val
	elseif t == "Vector3" then
		local v = val :: Vector3
		return { X = v.X, Y = v.Y, Z = v.Z }
	elseif t == "Vector2" then
		local v = val :: Vector2
		return { X = v.X, Y = v.Y }
	elseif t == "CFrame" then
		local cf = val :: CFrame
		return { cf:GetComponents() }
	elseif t == "Color3" then
		local c = val :: Color3
		return { R = math.round(c.R * 255), G = math.round(c.G * 255), B = math.round(c.B * 255), Hex = "#" .. c:ToHex() }
	elseif t == "UDim2" then
		local u = val :: UDim2
		return { XScale = u.X.Scale, XOffset = u.X.Offset, YScale = u.Y.Scale, YOffset = u.Y.Offset }
	elseif t == "UDim" then
		local u = val :: UDim
		return { Scale = u.Scale, Offset = u.Offset }
	elseif t == "EnumItem" then
		return tostring(val)
	elseif t == "Instance" then
		return getInstancePath(val :: Instance)
	end
	return tostring(val)
end

function SharpTreeTools.searchTree(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local query = if typeof(opts.query) == "string" and #opts.query > 0
		then string.lower(opts.query)
		else nil
	local className = if typeof(opts.className) == "string" and #opts.className > 0
		then opts.className
		else nil
	local tagFilter = if typeof(opts.tag) == "string" and #opts.tag > 0 then opts.tag else nil
	local maxDepth = math.max(0, math.min(16, tonumber(opts.maxDepth) or 4))
	local limit = math.max(1, math.min(500, tonumber(opts.limit) or 100))
	local assignHandles = opts.assignHandles ~= false

	local roots: { Instance }
	if opts.rootPath ~= nil or opts.sharpHandle ~= nil or opts.handle ~= nil then
		local resolvedRoot = resolveTarget(opts)
		if not resolvedRoot then
			return {
				ok = false,
				code = "ROOT_NOT_FOUND",
				message = "Could not resolve searchTree root target.",
			}
		end
		roots = if resolvedRoot == game then getSafeRoots() else { resolvedRoot }
	else
		roots = getSafeRoots()
	end

	local items: { any } = {}
	local truncated = false

	local function visit(inst: Instance, depth: number)
		if #items >= limit then
			truncated = true
			return
		end

		local matches = true
		if query then
			local nLower = string.lower(inst.Name)
			local cLower = string.lower(inst.ClassName)
			if not string.find(nLower, query, 1, true) and not string.find(cLower, query, 1, true) then
				matches = false
			end
		end
		if matches and className then
			local okIsA, isMatch = pcall(function()
				return inst:IsA(className)
			end)
			if not okIsA or not isMatch then
				matches = false
			end
		end
		if matches and tagFilter then
			local okTag, hasTag = pcall(function()
				return CollectionService:HasTag(inst, tagFilter)
			end)
			if not okTag or not hasTag then
				matches = false
			end
		end

		if matches then
			local okTags, tags = pcall(function()
				return CollectionService:GetTags(inst)
			end)
			local okCh, chList = pcall(function()
				return inst:GetChildren()
			end)
			table.insert(items, {
				Name = inst.Name,
				ClassName = inst.ClassName,
				SharpHandle = getOrCreateHandle(inst, assignHandles),
				Path = getInstancePath(inst),
				ChildCount = if okCh and typeof(chList) == "table" then #chList else 0,
				Tags = if okTags then tags else {},
			})
		end

		if depth < maxDepth and #items < limit then
			local okCh, children = pcall(function()
				return inst:GetChildren()
			end)
			if okCh and typeof(children) == "table" then
				for _, child in ipairs(children) do
					visit(child, depth + 1)
					if #items >= limit then
						truncated = true
						break
					end
				end
			end
		end
	end

	for _, r in ipairs(roots) do
		visit(r, 0)
		if #items >= limit then
			break
		end
	end

	return {
		ok = true,
		count = #items,
		truncated = truncated,
		items = items,
	}
end

function SharpTreeTools.inspectInstance(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local inst = resolveTarget(opts)
	if not inst then
		return {
			ok = false,
			code = "TARGET_NOT_FOUND",
			message = "Could not resolve instance by sharpHandle or path.",
		}
	end

	local handle = getOrCreateHandle(inst, true)
	local attrs: { [string]: any } = {}
	local okAttrs, rawAttrs = pcall(function()
		return inst:GetAttributes()
	end)
	if okAttrs and typeof(rawAttrs) == "table" then
		for k, v in pairs(rawAttrs) do
			attrs[tostring(k)] = encodeSimpleValue(v)
		end
	end

	local okTags, tags = pcall(function()
		return CollectionService:GetTags(inst)
	end)

	local childrenSummary: { any } = {}
	local okCh, chList = pcall(function()
		return inst:GetChildren()
	end)
	if okCh and typeof(chList) == "table" then
		for idx, ch in ipairs(chList) do
			if idx > 100 then
				break
			end
			table.insert(childrenSummary, {
				Name = ch.Name,
				ClassName = ch.ClassName,
				SharpHandle = getOrCreateHandle(ch, true),
				Path = getInstancePath(ch),
			})
		end
	end

	local props: { [string]: any } = {}
	if opts.includeProps ~= false then
		local probeNames = {
			"Archivable",
			"Position",
			"Size",
			"CFrame",
			"Anchored",
			"CanCollide",
			"Transparency",
			"Color",
			"Material",
			"Enabled",
			"Visible",
			"Text",
			"Value",
			"RunContext",
			"PrimaryPart",
			"ModelStreamingMode",
		}
		for _, propName in ipairs(probeNames) do
			local okRead, val = pcall(function()
				return (inst :: any)[propName]
			end)
			if okRead and val ~= nil and typeof(val) ~= "function" and typeof(val) ~= "RBXScriptSignal" then
				props[propName] = encodeSimpleValue(val)
			end
		end
	end

	return {
		ok = true,
		Name = inst.Name,
		ClassName = inst.ClassName,
		SharpHandle = handle,
		Path = getInstancePath(inst),
		Attributes = attrs,
		Tags = if okTags then tags else {},
		ChildCount = if okCh and typeof(chList) == "table" then #chList else 0,
		Children = childrenSummary,
		Properties = props,
	}
end

local function readScriptSourceInternal(scriptInst: LuaSourceContainer): string
	local okEd, edSrc = pcall(function()
		return ScriptEditorService:GetEditorSource(scriptInst)
	end)
	if okEd and typeof(edSrc) == "string" then
		return edSrc
	end
	return (scriptInst :: any).Source
end

function SharpTreeTools.readScript(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local inst = resolveTarget(opts)
	if not inst or not inst:IsA("LuaSourceContainer") then
		return {
			ok = false,
			code = "SCRIPT_NOT_FOUND",
			message = "Target could not be resolved to a Script, LocalScript, or ModuleScript.",
		}
	end

	local scriptInst = inst :: LuaSourceContainer
	local src = readScriptSourceInternal(scriptInst)
	local lines = string.split(src, "\n")
	local revision = computeRevision(src)
	local handle = getOrCreateHandle(scriptInst, true)

	local outSource = src
	local startLine = tonumber(opts.startLine)
	local endLine = tonumber(opts.endLine)
	if startLine or endLine then
		local s = math.max(1, math.floor(startLine or 1))
		local e = math.min(#lines, math.floor(endLine or #lines))
		local sliced: { string } = {}
		for i = s, e do
			table.insert(sliced, lines[i])
		end
		outSource = table.concat(sliced, "\n")
	end

	return {
		ok = true,
		Name = scriptInst.Name,
		ClassName = scriptInst.ClassName,
		SharpHandle = handle,
		Path = getInstancePath(scriptInst),
		revision = revision,
		length = #src,
		lineCount = #lines,
		source = if opts.includeSource == false then nil else outSource,
	}
end

function SharpTreeTools.updateScript(args: { [string]: any }?): (boolean, { [string]: any })
	local opts = args or {}
	local inst = resolveTarget(opts)
	if not inst or not inst:IsA("LuaSourceContainer") then
		return false, {
			ok = false,
			code = "SCRIPT_NOT_FOUND",
			message = "Target could not be resolved to a Script, LocalScript, or ModuleScript.",
		}
	end

	local scriptInst = inst :: LuaSourceContainer
	local expectedRev = if typeof(opts.expectedRevision) == "string" then opts.expectedRevision else nil
	local expectedLen = if typeof(opts.expectedLength) == "number" then opts.expectedLength else nil

	local currentSrc = readScriptSourceInternal(scriptInst)
	local oldRev = computeRevision(currentSrc)
	local oldLen = #currentSrc

	if expectedRev and oldRev ~= expectedRev then
		return false, {
			ok = false,
			code = "REVISION_MISMATCH",
			message = string.format("Expected revision '%s' but current is '%s'.", expectedRev, oldRev),
			currentRevision = oldRev,
			currentLength = oldLen,
		}
	end
	if expectedLen and oldLen ~= expectedLen then
		return false, {
			ok = false,
			code = "REVISION_MISMATCH",
			message = string.format("Expected length %d but current is %d.", expectedLen, oldLen),
			currentRevision = oldRev,
			currentLength = oldLen,
		}
	end

	local function buildUpdatedSource(baseSrc: string): (boolean, string, string?)
		if typeof(opts.newSource) == "string" then
			return true, opts.newSource, nil
		end
		if typeof(opts.findText) == "string" and typeof(opts.replaceText) == "string" then
			local idx = string.find(baseSrc, opts.findText, 1, true)
			if not idx then
				return false, baseSrc, "findText pattern not found in script source"
			end
			local beforePart = string.sub(baseSrc, 1, idx - 1)
			local afterPart = string.sub(baseSrc, idx + #opts.findText)
			return true, beforePart .. opts.replaceText .. afterPart, nil
		end
		return false, baseSrc, "Must provide either newSource or findText + replaceText"
	end

	local okPrep, targetSrc, prepErr = buildUpdatedSource(currentSrc)
	if not okPrep then
		return false, {
			ok = false,
			code = "INVALID_SCRIPT_EDIT",
			message = prepErr or "Invalid script update payload",
		}
	end

	local callbackError: string? = nil
	local okEditor, errEditor = pcall(function()
		ScriptEditorService:UpdateSourceAsync(scriptInst, function(liveSrc: string): string
			if expectedRev and computeRevision(liveSrc) ~= expectedRev then
				callbackError = "REVISION_MISMATCH during UpdateSourceAsync"
				return liveSrc
			end
			if expectedLen and #liveSrc ~= expectedLen then
				callbackError = "LENGTH_MISMATCH during UpdateSourceAsync"
				return liveSrc
			end
			local okInner, nextText, innerErr = buildUpdatedSource(liveSrc)
			if not okInner then
				callbackError = innerErr or "Invalid script edit"
				return liveSrc
			end
			targetSrc = nextText
			return nextText
		end)
	end)

	if callbackError then
		return false, {
			ok = false,
			code = "REVISION_MISMATCH",
			message = callbackError,
		}
	end

	local usedFallback = false
	if not okEditor then
		local okFallback, errFallback = pcall(function()
			(scriptInst :: any).Source = targetSrc
		end)
		if not okFallback then
			return false, {
				ok = false,
				code = "SCRIPT_UPDATE_FAILED",
				message = string.format("UpdateSourceAsync (%s) and Source fallback (%s) failed.", tostring(errEditor), tostring(errFallback)),
			}
		end
		usedFallback = true
	end

	local afterSrc = readScriptSourceInternal(scriptInst)
	local newRev = computeRevision(afterSrc)
	local verified = (afterSrc == targetSrc)

	local payload: { [string]: any } = {
		ok = verified,
		Name = scriptInst.Name,
		ClassName = scriptInst.ClassName,
		SharpHandle = getOrCreateHandle(scriptInst, true),
		Path = getInstancePath(scriptInst),
		oldRevision = oldRev,
		newRevision = newRev,
		oldLength = oldLen,
		newLength = #afterSrc,
		usedSourceFallback = usedFallback,
		verified = verified,
	}
	return verified, payload
end

function SharpTreeTools.readConsoleLogs(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local limit = math.max(1, math.min(500, tonumber(opts.limit) or 50))
	local msgFilter = if typeof(opts.messageType) == "string" and #opts.messageType > 0
		then string.lower(opts.messageType)
		else nil

	local okHist, history = pcall(function()
		return LogService:GetLogHistory()
	end)
	if not okHist or typeof(history) ~= "table" then
		return {
			ok = false,
			code = "LOG_HISTORY_UNAVAILABLE",
			message = "Unable to read LogService:GetLogHistory().",
		}
	end

	local collected: { any } = {}
	for i = #history, 1, -1 do
		local entry = history[i]
		local mType = tostring(entry.messageType)
		local shortType = string.gsub(mType, "^Enum%.MessageType%.Message", "")
		if not msgFilter or string.find(string.lower(shortType), msgFilter, 1, true) then
			table.insert(collected, 1, {
				message = tostring(entry.message or ""),
				messageType = shortType,
				timestamp = entry.timestamp,
			})
			if #collected >= limit then
				break
			end
		end
	end

	return {
		ok = true,
		totalAvailable = #history,
		returnedCount = #collected,
		logs = collected,
	}
end

local function findModuleFunction(mod: { [any]: any }, opName: string): ((any) -> ...any)?
	if typeof(mod[opName]) == "function" then
		return mod[opName]
	end
	local firstUpper = string.upper(string.sub(opName, 1, 1)) .. string.sub(opName, 2)
	if typeof(mod[firstUpper]) == "function" then
		return mod[firstUpper]
	end
	local firstLower = string.lower(string.sub(opName, 1, 1)) .. string.sub(opName, 2)
	if typeof(mod[firstLower]) == "function" then
		return mod[firstLower]
	end
	local targetLower = string.lower(opName)
	for k, v in pairs(mod) do
		if typeof(v) == "function" and string.lower(tostring(k)) == targetLower then
			return v
		end
	end
	return nil
end

function SharpTreeTools.dispatchModuleOp(
	embeddedRoot: Instance,
	moduleName: string,
	opName: string,
	args: { [string]: any }?
): (boolean, any)
	local modInst = embeddedRoot:FindFirstChild(moduleName)
	if not modInst then
		local targetLower = string.lower(moduleName)
		for _, ch in ipairs(embeddedRoot:GetChildren()) do
			if ch:IsA("ModuleScript") and string.lower(ch.Name) == targetLower then
				modInst = ch
				break
			end
		end
	end
	if not modInst or not modInst:IsA("ModuleScript") then
		return false, {
			code = "MODULE_NOT_FOUND",
			module = moduleName,
			message = string.format("Embedded ModuleScript '%s' not found.", moduleName),
		}
	end

	local reqOk, modOrErr = pcall(require, modInst)
	if not reqOk then
		return false, {
			code = "MODULE_REQUIRE_ERROR",
			module = moduleName,
			message = tostring(modOrErr),
		}
	end

	if typeof(modOrErr) ~= "table" then
		if opName == "" or string.lower(opName) == "run" or string.lower(opName) == "execute" then
			return true, modOrErr
		end
		return false, {
			code = "MODULE_NOT_TABLE",
			module = moduleName,
			op = opName,
			message = string.format("Module '%s' returned %s instead of function table.", moduleName, typeof(modOrErr)),
		}
	end

	local fn = findModuleFunction(modOrErr, opName)
	if not fn then
		return false, {
			code = "UNKNOWN_MODULE_OP",
			module = moduleName,
			op = opName,
			message = string.format("Operation '%s' not found on module '%s'.", opName, moduleName),
		}
	end

	local callOk, r1, r2 = xpcall(function()
		return fn(args or {})
	end, debug.traceback)
	if not callOk then
		return false, {
			code = "MODULE_OP_ERROR",
			module = moduleName,
			op = opName,
			message = tostring(r1),
		}
	end

	if typeof(r1) == "boolean" and r2 ~= nil then
		return r1, r2
	end
	return true, r1
end

return SharpTreeTools

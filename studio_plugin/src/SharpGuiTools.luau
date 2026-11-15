--!strict
--[[
	SharpGuiTools
	Direct surgical GUI inspection, non-destructive patching with readback verification,
	and StudioDeviceSimulatorService control for SharpBridgePlugin (no loadstring required).
]]

local GuiService = game:GetService("GuiService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local StarterGui = game:GetService("StarterGui")

local HANDLE_ATTR = "SharpHandle"
local KEY_MODIFIED_PROPS: { string } = {
	"Size",
	"Position",
	"BackgroundColor3",
	"TextColor3",
	"ImageColor3",
}
local INSPECT_EXTRA_PROPS: { string } = {
	"Size",
	"Position",
	"AnchorPoint",
	"BackgroundColor3",
	"BackgroundTransparency",
	"Text",
	"TextColor3",
	"TextSize",
	"Image",
	"ImageColor3",
	"ImageTransparency",
	"ScaleType",
	"SliceCenter",
	"SliceScale",
	"ImageRectOffset",
	"ImageRectSize",
	"ZIndex",
	"LayoutOrder",
	"PaddingTop",
	"PaddingBottom",
	"PaddingLeft",
	"PaddingRight",
	"CornerRadius",
	"FillDirection",
	"Padding",
	"Color",
	"Thickness",
}

local SharpGuiTools = {}

local function getOrCreateHandle(inst: Instance): string
	local existing = inst:GetAttribute(HANDLE_ATTR)
	if typeof(existing) == "string" and #existing > 0 then
		return existing
	end
	local handle = "sh_" .. HttpService:GenerateGUID(false)
	inst:SetAttribute(HANDLE_ATTR, handle)
	return handle
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

local function findByHandleInContainers(handle: string): Instance?
	local containers: { Instance } = {
		StarterGui,
		ReplicatedStorage,
	}
	local lp = Players.LocalPlayer
	if lp then
		local pg = lp:FindFirstChild("PlayerGui")
		if pg then
			table.insert(containers, pg)
		end
	end
	for _, serviceName in ipairs({ "StarterPlayer", "Workspace", "ReplicatedFirst" }) do
		local ok, svc = pcall(function()
			return game:GetService(serviceName)
		end)
		if ok and svc then
			table.insert(containers, svc)
		end
	end
	for _, root in ipairs(containers) do
		if root:GetAttribute(HANDLE_ATTR) == handle then
			return root
		end
		for _, desc in ipairs(root:GetDescendants()) do
			if desc:GetAttribute(HANDLE_ATTR) == handle then
				return desc
			end
		end
	end
	return nil
end

local function resolveTarget(spec: { [string]: any }): Instance?
	local handle = spec.sharpHandle or spec.handle
	if typeof(handle) == "string" and #handle > 0 then
		local byHandle = findByHandleInContainers(handle)
		if byHandle then
			return byHandle
		end
	end
	local pathStr = spec.path
	if typeof(pathStr) == "string" and #pathStr > 0 then
		return resolvePath(pathStr)
	end
	return nil
end

local function encodeValue(val: any): any
	local t = typeof(val)
	if val == nil or t == "boolean" or t == "number" or t == "string" then
		return val
	elseif t == "Vector2" then
		local v = val :: Vector2
		return { X = v.X, Y = v.Y }
	elseif t == "Vector3" then
		local v = val :: Vector3
		return { X = v.X, Y = v.Y, Z = v.Z }
	elseif t == "UDim" then
		local u = val :: UDim
		return { Scale = u.Scale, Offset = u.Offset }
	elseif t == "UDim2" then
		local u = val :: UDim2
		return {
			XScale = u.X.Scale,
			XOffset = u.X.Offset,
			YScale = u.Y.Scale,
			YOffset = u.Y.Offset,
		}
	elseif t == "Color3" then
		local c = val :: Color3
		return {
			R = math.round(c.R * 255),
			G = math.round(c.G * 255),
			B = math.round(c.B * 255),
			Hex = "#" .. c:ToHex(),
		}
	elseif t == "Rect" then
		local r = val :: Rect
		return {
			Min = { X = r.Min.X, Y = r.Min.Y },
			Max = { X = r.Max.X, Y = r.Max.Y },
		}
	elseif t == "ColorSequence" then
		local cs = val :: ColorSequence
		local kps: { any } = {}
		for _, kp in ipairs(cs.Keypoints) do
			table.insert(kps, {
				time = kp.Time,
				color = encodeValue(kp.Value),
			})
		end
		return kps
	elseif t == "NumberSequence" then
		local ns = val :: NumberSequence
		local kps: { any } = {}
		for _, kp in ipairs(ns.Keypoints) do
			table.insert(kps, {
				time = kp.Time,
				value = kp.Value,
				envelope = kp.Envelope,
			})
		end
		return kps
	elseif t == "EnumItem" then
		return tostring(val)
	elseif t == "Font" then
		local f = val :: Font
		return {
			family = f.Family,
			weight = f.Weight.Name,
			style = f.Style.Name,
		}
	elseif t == "Instance" then
		local instVal = val :: Instance
		return {
			Name = instVal.Name,
			ClassName = instVal.ClassName,
			Path = getInstancePath(instVal),
			SharpHandle = getOrCreateHandle(instVal),
		}
	end
	return tostring(val)
end

local function decodeEnum(raw: any, hintEnumType: Enum?): EnumItem?
	if typeof(raw) == "EnumItem" then
		return raw
	end
	if typeof(raw) == "string" then
		if string.sub(raw, 1, 5) == "Enum." then
			local rest = string.sub(raw, 6)
			local dotIdx = string.find(rest, "%.")
			if dotIdx then
				local enumName = string.sub(rest, 1, dotIdx - 1)
				local itemName = string.sub(rest, dotIdx + 1)
				local ok, item = pcall(function()
					return (Enum :: any)[enumName][itemName]
				end)
				if ok and typeof(item) == "EnumItem" then
					return item
				end
			end
		elseif hintEnumType then
			local ok, item = pcall(function()
				return (hintEnumType :: any)[raw]
			end)
			if ok and typeof(item) == "EnumItem" then
				return item
			end
		end
	elseif typeof(raw) == "table" and raw.type == "Enum" and typeof(raw.value) == "string" then
		return decodeEnum(raw.value, hintEnumType)
	end
	return nil
end

local function decodeColor3(raw: any): Color3
	if typeof(raw) == "Color3" then
		return raw
	end
	if typeof(raw) == "string" then
		local hex = if string.sub(raw, 1, 1) == "#" then string.sub(raw, 2) else raw
		return Color3.fromHex(hex)
	end
	if typeof(raw) == "table" then
		if typeof(raw.hex) == "string" or typeof(raw.Hex) == "string" then
			local h = tostring(raw.hex or raw.Hex)
			if string.sub(h, 1, 1) == "#" then
				h = string.sub(h, 2)
			end
			return Color3.fromHex(h)
		end
		local arr = raw.rgb or raw.value or raw
		if typeof(arr) == "table" and arr[1] ~= nil and arr[2] ~= nil and arr[3] ~= nil then
			local r = tonumber(arr[1]) or 0
			local g = tonumber(arr[2]) or 0
			local b = tonumber(arr[3]) or 0
			if r > 1 or g > 1 or b > 1 or raw.fromRGB == true then
				return Color3.fromRGB(r, g, b)
			end
			return Color3.new(r, g, b)
		end
		local r = tonumber(raw.R or raw.r) or 0
		local g = tonumber(raw.G or raw.g) or 0
		local b = tonumber(raw.B or raw.b) or 0
		if r > 1 or g > 1 or b > 1 or raw.fromRGB == true then
			return Color3.fromRGB(r, g, b)
		end
		return Color3.new(r, g, b)
	end
	error("Invalid Color3 specification")
end

local function decodeUDim(raw: any): UDim
	if typeof(raw) == "UDim" then
		return raw
	end
	if typeof(raw) == "table" then
		local arr = raw.value or raw
		if typeof(arr) == "table" and arr[1] ~= nil and arr[2] ~= nil then
			return UDim.new(tonumber(arr[1]) or 0, tonumber(arr[2]) or 0)
		end
		return UDim.new(tonumber(raw.Scale or raw.scale) or 0, tonumber(raw.Offset or raw.offset) or 0)
	end
	error("Invalid UDim specification")
end

local function decodeUDim2(raw: any): UDim2
	if typeof(raw) == "UDim2" then
		return raw
	end
	if typeof(raw) == "table" then
		if typeof(raw.X) == "table" and typeof(raw.Y) == "table" then
			return UDim2.new(
				tonumber(raw.X.Scale or raw.X.scale) or 0,
				tonumber(raw.X.Offset or raw.X.offset) or 0,
				tonumber(raw.Y.Scale or raw.Y.scale) or 0,
				tonumber(raw.Y.Offset or raw.Y.offset) or 0
			)
		end
		local arr = raw.value or raw
		if typeof(arr) == "table" and arr[1] ~= nil and arr[2] ~= nil and arr[3] ~= nil and arr[4] ~= nil then
			return UDim2.new(
				tonumber(arr[1]) or 0,
				tonumber(arr[2]) or 0,
				tonumber(arr[3]) or 0,
				tonumber(arr[4]) or 0
			)
		end
		return UDim2.new(
			tonumber(raw.XScale or raw.xScale or raw.scaleX) or 0,
			tonumber(raw.XOffset or raw.xOffset or raw.offsetX) or 0,
			tonumber(raw.YScale or raw.yScale or raw.scaleY) or 0,
			tonumber(raw.YOffset or raw.yOffset or raw.offsetY) or 0
		)
	end
	error("Invalid UDim2 specification")
end

local function decodeVector2(raw: any): Vector2
	if typeof(raw) == "Vector2" then
		return raw
	end
	if typeof(raw) == "table" then
		local arr = raw.value or raw
		if typeof(arr) == "table" and arr[1] ~= nil and arr[2] ~= nil then
			return Vector2.new(tonumber(arr[1]) or 0, tonumber(arr[2]) or 0)
		end
		return Vector2.new(tonumber(raw.X or raw.x) or 0, tonumber(raw.Y or raw.y) or 0)
	end
	error("Invalid Vector2 specification")
end

local function decodeRect(raw: any): Rect
	if typeof(raw) == "Rect" then
		return raw
	end
	if typeof(raw) == "table" then
		if typeof(raw.Min) == "table" and typeof(raw.Max) == "table" then
			return Rect.new(
				tonumber(raw.Min.X or raw.Min.x) or 0,
				tonumber(raw.Min.Y or raw.Min.y) or 0,
				tonumber(raw.Max.X or raw.Max.x) or 0,
				tonumber(raw.Max.Y or raw.Max.y) or 0
			)
		end
		local arr = raw.value or raw
		if typeof(arr) == "table" and arr[1] ~= nil and arr[4] ~= nil then
			return Rect.new(
				tonumber(arr[1]) or 0,
				tonumber(arr[2]) or 0,
				tonumber(arr[3]) or 0,
				tonumber(arr[4]) or 0
			)
		end
	end
	error("Invalid Rect specification")
end

local function decodeColorSequence(raw: any): ColorSequence
	if typeof(raw) == "ColorSequence" then
		return raw
	end
	local list = if typeof(raw) == "table" and typeof(raw.keypoints) == "table"
		then raw.keypoints
		elseif typeof(raw) == "table" and typeof(raw.value) == "table" then raw.value
		else raw
	if typeof(list) ~= "table" or #list == 0 then
		error("ColorSequence requires a non-empty array of keypoints")
	end
	local kps: { ColorSequenceKeypoint } = {}
	for _, entry in ipairs(list) do
		local tVal = tonumber(entry.time or entry.Time) or 0
		local cVal = decodeColor3(entry.color or entry.Color or entry.value or entry.Value)
		table.insert(kps, ColorSequenceKeypoint.new(tVal, cVal))
	end
	table.sort(kps, function(a, b)
		return a.Time < b.Time
	end)
	return ColorSequence.new(kps)
end

local function inferPropertyTypeHint(propName: string): string?
	local lower = string.lower(propName)
	if string.find(lower, "colorsequence", 1, true) or propName == "Color" then
		-- Note: UIGradient.Color is ColorSequence, while UIStroke.Color is Color3; caller currentVal refines this
		return nil
	end
	if string.find(lower, "color", 1, true) then
		return "Color3"
	end
	if propName == "Size" or propName == "Position" then
		return "UDim2"
	end
	if string.find(lower, "padding", 1, true) or propName == "CornerRadius" then
		return "UDim"
	end
	if propName == "AnchorPoint" or string.find(lower, "rectoffset", 1, true) or string.find(lower, "rectsize", 1, true) then
		return "Vector2"
	end
	if propName == "SliceCenter" then
		return "Rect"
	end
	return nil
end

local function decodeTypedValue(raw: any, targetTypeHint: string?, existingValue: any?): any
	if typeof(raw) == "table" then
		local explicitType = raw.__type or raw.type
		if typeof(explicitType) == "string" then
			if explicitType == "UDim2" then
				return decodeUDim2(raw)
			elseif explicitType == "UDim" then
				return decodeUDim(raw)
			elseif explicitType == "Vector2" then
				return decodeVector2(raw)
			elseif explicitType == "Color3" then
				return decodeColor3(raw)
			elseif explicitType == "ColorSequence" then
				return decodeColorSequence(raw)
			elseif explicitType == "Rect" then
				return decodeRect(raw)
			elseif explicitType == "Enum" then
				local enumItem = decodeEnum(raw, if typeof(existingValue) == "EnumItem" then existingValue.EnumType else nil)
				if enumItem then
					return enumItem
				end
			end
		end
	end

	local resolvedType = if existingValue ~= nil then typeof(existingValue) else targetTypeHint
	if resolvedType == "EnumItem" then
		local enumItem = decodeEnum(raw, (existingValue :: EnumItem).EnumType)
		if enumItem then
			return enumItem
		end
	elseif resolvedType == "UDim2" then
		return decodeUDim2(raw)
	elseif resolvedType == "UDim" then
		return decodeUDim(raw)
	elseif resolvedType == "Vector2" then
		return decodeVector2(raw)
	elseif resolvedType == "Color3" then
		return decodeColor3(raw)
	elseif resolvedType == "ColorSequence" then
		return decodeColorSequence(raw)
	elseif resolvedType == "Rect" then
		return decodeRect(raw)
	elseif resolvedType == "Font" and typeof(raw) == "table" then
		local fam = tostring(raw.family or "rbxasset://fonts/families/BuilderSans.json")
		local weightItem = decodeEnum(raw.weight or "Regular", Enum.FontWeight) or Enum.FontWeight.Regular
		local styleItem = decodeEnum(raw.style or "Normal", Enum.FontStyle) or Enum.FontStyle.Normal
		return Font.new(fam, (weightItem :: any) :: Enum.FontWeight, (styleItem :: any) :: Enum.FontStyle)
	end

	if typeof(raw) == "string" and string.sub(raw, 1, 5) == "Enum." then
		local enumItem = decodeEnum(raw, nil)
		if enumItem then
			return enumItem
		end
	end
	if typeof(raw) == "string" and string.match(raw, "^#%x%x%x%x%x%x$") then
		return Color3.fromHex(string.sub(raw, 2))
	end
	if typeof(raw) == "table" and raw[1] ~= nil and typeof(raw[1]) == "table" and raw[1].color ~= nil then
		return decodeColorSequence(raw)
	end
	return raw
end

local function approxEqual(a: any, b: any): boolean
	if typeof(a) ~= typeof(b) then
		return false
	end
	local t = typeof(a)
	local eps = 1e-3
	if t == "number" then
		return math.abs((a :: number) - (b :: number)) <= eps
	elseif t == "Vector2" then
		local va, vb = a :: Vector2, b :: Vector2
		return math.abs(va.X - vb.X) <= eps and math.abs(va.Y - vb.Y) <= eps
	elseif t == "UDim" then
		local ua, ub = a :: UDim, b :: UDim
		return math.abs(ua.Scale - ub.Scale) <= eps and math.abs(ua.Offset - ub.Offset) <= 1
	elseif t == "UDim2" then
		local ua, ub = a :: UDim2, b :: UDim2
		return math.abs(ua.X.Scale - ub.X.Scale) <= eps
			and math.abs(ua.X.Offset - ub.X.Offset) <= 1
			and math.abs(ua.Y.Scale - ub.Y.Scale) <= eps
			and math.abs(ua.Y.Offset - ub.Y.Offset) <= 1
	elseif t == "Color3" then
		local ca, cb = a :: Color3, b :: Color3
		return math.abs(ca.R - cb.R) <= 0.01
			and math.abs(ca.G - cb.G) <= 0.01
			and math.abs(ca.B - cb.B) <= 0.01
	elseif t == "Rect" then
		local ra, rb = a :: Rect, b :: Rect
		return math.abs(ra.Min.X - rb.Min.X) <= eps
			and math.abs(ra.Min.Y - rb.Min.Y) <= eps
			and math.abs(ra.Max.X - rb.Max.X) <= eps
			and math.abs(ra.Max.Y - rb.Max.Y) <= eps
	elseif t == "ColorSequence" then
		local csa, csb = a :: ColorSequence, b :: ColorSequence
		if #csa.Keypoints ~= #csb.Keypoints then
			return false
		end
		for i = 1, #csa.Keypoints do
			if math.abs(csa.Keypoints[i].Time - csb.Keypoints[i].Time) > eps then
				return false
			end
			if not approxEqual(csa.Keypoints[i].Value, csb.Keypoints[i].Value) then
				return false
			end
		end
		return true
	end
	return a == b
end

local function collectStyleSheetSummary(sheet: StyleSheet): { [string]: any }
	local rules: { any } = {}
	for _, ch in ipairs(sheet:GetChildren()) do
		if ch:IsA("StyleRule") then
			local okProps, rawProps = pcall(function()
				return ch:GetProperties()
			end)
			local propOut: { [string]: any } = {}
			if okProps and typeof(rawProps) == "table" then
				for k, v in pairs(rawProps) do
					propOut[tostring(k)] = encodeValue(v)
				end
			end
			local okErr, selErr = pcall(function()
				return ch.SelectorError
			end)
			table.insert(rules, {
				Name = ch.Name,
				SharpHandle = getOrCreateHandle(ch),
				Path = getInstancePath(ch),
				Selector = ch.Selector,
				Priority = ch.Priority,
				SelectorError = if okErr then selErr else "",
				Properties = propOut,
			})
		end
	end
	return {
		Name = sheet.Name,
		SharpHandle = getOrCreateHandle(sheet),
		Path = getInstancePath(sheet),
		RuleCount = #rules,
		Rules = rules,
	}
end

local function inspectNode(inst: Instance, depth: number, maxDepth: number, includeProps: boolean): { [string]: any }
	local node: { [string]: any } = {
		Name = inst.Name,
		ClassName = inst.ClassName,
		SharpHandle = getOrCreateHandle(inst),
		Path = getInstancePath(inst),
	}

	if inst:IsA("LayerCollector") then
		node.Enabled = inst.Enabled
		node.ResetOnSpawn = inst.ResetOnSpawn
		node.ZIndexBehavior = inst.ZIndexBehavior.Name
		if inst:IsA("ScreenGui") then
			node.DisplayOrder = inst.DisplayOrder
			local okInsets, insets = pcall(function()
				return inst.ScreenInsets.Name
			end)
			if okInsets then
				node.ScreenInsets = insets
			end
		end
		node.AbsoluteSize = encodeValue(inst.AbsoluteSize)
	elseif inst:IsA("GuiObject") then
		node.Visible = inst.Visible
		node.AbsolutePosition = encodeValue(inst.AbsolutePosition)
		node.AbsoluteSize = encodeValue(inst.AbsoluteSize)
		node.ZIndex = inst.ZIndex
		node.LayoutOrder = inst.LayoutOrder
	elseif inst:IsA("UIGridStyleLayout") then
		node.AbsoluteContentSize = encodeValue(inst.AbsoluteContentSize)
	elseif inst:IsA("StyleLink") then
		local sheet = inst.StyleSheet
		if sheet then
			node.StyleSheet = {
				Name = sheet.Name,
				SharpHandle = getOrCreateHandle(sheet),
				Path = getInstancePath(sheet),
			}
			local selectors: { string } = {}
			for _, rule in ipairs(sheet:GetChildren()) do
				if rule:IsA("StyleRule") then
					table.insert(selectors, rule.Selector)
				end
			end
			node.StyleRuleSelectors = selectors
		end
	elseif inst:IsA("StyleSheet") then
		local sheetInfo = collectStyleSheetSummary(inst)
		node.RuleCount = sheetInfo.RuleCount
		node.Rules = sheetInfo.Rules
	elseif inst:IsA("StyleRule") then
		node.Selector = inst.Selector
		node.Priority = inst.Priority
		local okErr, selErr = pcall(function()
			return inst.SelectorError
		end)
		if okErr then
			node.SelectorError = selErr
		end
	end

	-- Track active StyleLinks attached directly on this instance
	local linkSelectors: { any } = {}
	for _, child in ipairs(inst:GetChildren()) do
		if child:IsA("StyleLink") then
			local sheet = child.StyleSheet
			if sheet then
				local selectors: { string } = {}
				for _, r in ipairs(sheet:GetChildren()) do
					if r:IsA("StyleRule") then
						table.insert(selectors, r.Selector)
					end
				end
				table.insert(linkSelectors, {
					StyleLink = child.Name,
					StyleSheetPath = getInstancePath(sheet),
					Selectors = selectors,
				})
			end
		end
	end
	if #linkSelectors > 0 then
		node.ActiveStyleLinks = linkSelectors
	end

	-- Track IsPropertyModified on key UI props
	if inst:IsA("GuiObject") then
		local modified: { string } = {}
		for _, propName in ipairs(KEY_MODIFIED_PROPS) do
			local okMod, isMod = pcall(function()
				return inst:IsPropertyModified(propName)
			end)
			if okMod and isMod == true then
				table.insert(modified, propName)
			end
		end
		node.IsPropertyModified = modified
	end

	if includeProps then
		local propSnapshot: { [string]: any } = {}
		for _, propName in ipairs(INSPECT_EXTRA_PROPS) do
			local okRead, val = pcall(function()
				return (inst :: any)[propName]
			end)
			if okRead and val ~= nil and typeof(val) ~= "function" and typeof(val) ~= "RBXScriptSignal" then
				propSnapshot[propName] = encodeValue(val)
			end
		end
		if next(propSnapshot) ~= nil then
			node.Properties = propSnapshot
		end
	end

	if depth < maxDepth then
		local childrenOut: { any } = {}
		for _, child in ipairs(inst:GetChildren()) do
			table.insert(childrenOut, inspectNode(child, depth + 1, maxDepth, includeProps))
		end
		if #childrenOut > 0 then
			node.Children = childrenOut
		end
	else
		local childCount = #inst:GetChildren()
		if childCount > 0 then
			node.TruncatedChildCount = childCount
		end
	end

	return node
end

function SharpGuiTools.inspect(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local maxDepth = math.max(0, math.min(12, tonumber(opts.maxDepth) or 5))
	local includeProps = opts.includeProps == true

	local targetInst: Instance? = nil
	if typeof(opts.rootHandle) == "string" or typeof(opts.sharpHandle) == "string" or typeof(opts.handle) == "string" or typeof(opts.rootPath) == "string" then
		targetInst = resolveTarget({
			sharpHandle = opts.rootHandle or opts.sharpHandle or opts.handle,
			path = opts.rootPath,
		})
		if not targetInst then
			return {
				ok = false,
				code = "TARGET_NOT_FOUND",
				message = "Could not resolve requested GUI rootPath/rootHandle.",
			}
		end
	else
		local usePlayerGui = opts.target == "PlayerGui" or (opts.target == nil and RunService:IsRunning())
		local lp = Players.LocalPlayer
		local pg = if lp then lp:FindFirstChild("PlayerGui") else nil
		if usePlayerGui and pg then
			targetInst = pg
		else
			targetInst = StarterGui
		end
	end

	local styleSheets: { any } = {}
	if opts.includeStyleSheets ~= false then
		for _, desc in ipairs(ReplicatedStorage:GetDescendants()) do
			if desc:IsA("StyleSheet") then
				table.insert(styleSheets, collectStyleSheetSummary(desc))
			end
		end
		for _, desc in ipairs(StarterGui:GetDescendants()) do
			if desc:IsA("StyleSheet") then
				table.insert(styleSheets, collectStyleSheetSummary(desc))
			end
		end
	end

	local vpSize = Vector2.new(1280, 720)
	local cam = workspace.CurrentCamera
	if cam and cam.ViewportSize.X > 0 and cam.ViewportSize.Y > 0 then
		vpSize = cam.ViewportSize
	end
	local okInset, topbarInset = pcall(function()
		return GuiService.TopbarInset
	end)

	return {
		ok = true,
		rootPath = getInstancePath(targetInst :: Instance),
		viewportSize = encodeValue(vpSize),
		topbarInset = if okInset and topbarInset then encodeValue(topbarInset) else nil,
		tree = inspectNode(targetInst :: Instance, 0, maxDepth, includeProps),
		styleSheets = styleSheets,
	}
end

local function applySingleInstancePatch(spec: { [string]: any }): ({ [string]: any }, { [string]: any }, number, { string })
	local inst = resolveTarget(spec)
	if not inst then
		return {}, {}, 0, { "Target not found for patch spec" }
	end

	local handle = getOrCreateHandle(inst)
	local path = getInstancePath(inst)
	local beforeProps: { [string]: any } = {}
	local afterProps: { [string]: any } = {}
	local expectedSetValues: { [string]: any } = {}
	local resetPropNames: { string } = {}
	local errors: { string } = {}
	local patchedCount = 0

	local resetList = spec.resetProperties
	if typeof(resetList) == "table" then
		for _, propNameAny in ipairs(resetList) do
			local propName = tostring(propNameAny)
			local okOld, oldVal = pcall(function()
				return (inst :: any)[propName]
			end)
			if okOld then
				beforeProps[propName] = encodeValue(oldVal)
			end
			local okReset, resetErr = pcall(function()
				inst:ResetPropertyToDefault(propName)
			end)
			if not okReset then
				table.insert(errors, string.format("%s.%s ResetPropertyToDefault failed: %s", path, propName, tostring(resetErr)))
			else
				table.insert(resetPropNames, propName)
				patchedCount += 1
			end
		end
	end

	local setMap = spec.setProperties
	if typeof(setMap) == "table" then
		for propNameAny, rawTarget in pairs(setMap) do
			local propName = tostring(propNameAny)
			local okOld, oldVal = pcall(function()
				return (inst :: any)[propName]
			end)
			if okOld then
				beforeProps[propName] = encodeValue(oldVal)
			end
			local okDec, decodedVal = pcall(
				decodeTypedValue,
				rawTarget,
				inferPropertyTypeHint(propName),
				if okOld then oldVal else nil
			)
			if not okDec then
				table.insert(errors, string.format("%s.%s decode failed: %s", path, propName, tostring(decodedVal)))
				continue
			end
			local okWrite, writeErr = pcall(function()
				(inst :: any)[propName] = decodedVal
			end)
			if not okWrite then
				table.insert(errors, string.format("%s.%s write failed: %s", path, propName, tostring(writeErr)))
			else
				expectedSetValues[propName] = decodedVal
				patchedCount += 1
			end
		end
	end

	-- Readback verification
	for propName, expectedVal in pairs(expectedSetValues) do
		local okRead, actualVal = pcall(function()
			return (inst :: any)[propName]
		end)
		if not okRead then
			table.insert(errors, string.format("%s.%s readback failed", path, propName))
		else
			afterProps[propName] = encodeValue(actualVal)
			if not approxEqual(actualVal, expectedVal) then
				table.insert(errors, string.format("%s.%s readback mismatch", path, propName))
			end
		end
	end

	for _, propName in ipairs(resetPropNames) do
		local okRead, actualVal = pcall(function()
			return (inst :: any)[propName]
		end)
		if okRead then
			afterProps[propName] = encodeValue(actualVal)
		end
		local okMod, isMod = pcall(function()
			return inst:IsPropertyModified(propName)
		end)
		if okMod and isMod == true then
			table.insert(errors, string.format("%s.%s still reports IsPropertyModified=true after reset", path, propName))
		end
	end

	local beforeRecord = { SharpHandle = handle, Path = path, Properties = beforeProps }
	local afterRecord = { SharpHandle = handle, Path = path, Properties = afterProps }
	return beforeRecord, afterRecord, patchedCount, errors
end

local function applyStyleRuleUpdate(spec: { [string]: any }): ({ [string]: any }, { [string]: any }, number, { string })
	local targetInst = resolveTarget(spec)
	if not targetInst and typeof(spec.styleSheetPath) == "string" and typeof(spec.name) == "string" then
		local sheet = resolvePath(spec.styleSheetPath)
		if sheet and sheet:IsA("StyleSheet") then
			targetInst = sheet:FindFirstChild(spec.name)
		end
	end
	if not targetInst or not targetInst:IsA("StyleRule") then
		return {}, {}, 0, { "StyleRule target not found" }
	end

	local rule = targetInst :: StyleRule
	local handle = getOrCreateHandle(rule)
	local path = getInstancePath(rule)
	local errors: { string } = {}
	local patchedCount = 0

	local okOldProps, oldPropsMap = pcall(function()
		return rule:GetProperties()
	end)
	local beforeRecord: { [string]: any } = {
		SharpHandle = handle,
		Path = path,
		Selector = rule.Selector,
		Priority = rule.Priority,
		Properties = {},
	}
	if okOldProps and typeof(oldPropsMap) == "table" then
		local serOld: { [string]: any } = {}
		for k, v in pairs(oldPropsMap) do
			serOld[tostring(k)] = encodeValue(v)
		end
		beforeRecord.Properties = serOld
	end

	if typeof(spec.selector) == "string" then
		local okSel, selErr = pcall(function()
			rule.Selector = spec.selector
		end)
		if not okSel then
			table.insert(errors, path .. " Selector write failed: " .. tostring(selErr))
		else
			patchedCount += 1
		end
	end
	if typeof(spec.priority) == "number" then
		local okPri, priErr = pcall(function()
			rule.Priority = spec.priority
		end)
		if not okPri then
			table.insert(errors, path .. " Priority write failed: " .. tostring(priErr))
		else
			patchedCount += 1
		end
	end

	local propsInput = spec.setProperties or spec.properties
	local expectedRuleProps: { [string]: any } = {}
	if typeof(propsInput) == "table" then
		local decodedMap: { [string]: any } = {}
		for propNameAny, rawVal in pairs(propsInput) do
			local propName = tostring(propNameAny)
			local existingVal = if okOldProps and typeof(oldPropsMap) == "table" then oldPropsMap[propName] else nil
			local okDec, decVal = pcall(decodeTypedValue, rawVal, inferPropertyTypeHint(propName), existingVal)
			if not okDec then
				table.insert(errors, string.format("%s StyleRule.%s decode failed: %s", path, propName, tostring(decVal)))
			else
				decodedMap[propName] = decVal
				expectedRuleProps[propName] = decVal
			end
		end
		if next(decodedMap) ~= nil then
			local okSet, setErr = pcall(function()
				rule:SetProperties(decodedMap)
			end)
			if not okSet then
				table.insert(errors, path .. " SetProperties failed: " .. tostring(setErr))
			else
				patchedCount += 1
			end
		end
	end

	-- Readback verification
	local okNewProps, newPropsMap = pcall(function()
		return rule:GetProperties()
	end)
	local serNew: { [string]: any } = {}
	if okNewProps and typeof(newPropsMap) == "table" then
		for k, v in pairs(newPropsMap) do
			serNew[tostring(k)] = encodeValue(v)
		end
		for propName, expectedVal in pairs(expectedRuleProps) do
			local actualVal = newPropsMap[propName]
			if actualVal == nil or not approxEqual(actualVal, expectedVal) then
				table.insert(errors, string.format("%s StyleRule.%s readback mismatch", path, propName))
			end
		end
	end
	if typeof(spec.selector) == "string" and rule.Selector ~= spec.selector then
		table.insert(errors, path .. " Selector readback mismatch")
	end
	local okSelErr, selErrMsg = pcall(function()
		return rule.SelectorError
	end)
	if okSelErr and typeof(selErrMsg) == "string" and #selErrMsg > 0 then
		table.insert(errors, path .. " SelectorError: " .. selErrMsg)
	end

	local afterRecord: { [string]: any } = {
		SharpHandle = handle,
		Path = path,
		Selector = rule.Selector,
		Priority = rule.Priority,
		SelectorError = if okSelErr then selErrMsg else "",
		Properties = serNew,
	}
	return beforeRecord, afterRecord, patchedCount, errors
end

function SharpGuiTools.patch(args: { [string]: any }?): (boolean, { [string]: any })
	local opts = args or {}
	local beforeList: { any } = {}
	local afterList: { any } = {}
	local allErrors: { string } = {}
	local totalPatched = 0

	local patches = if typeof(opts.patches) == "table" then opts.patches else nil
	if patches then
		for _, patchSpec in ipairs(patches) do
			if typeof(patchSpec) == "table" then
				local b, a, cnt, errs = applySingleInstancePatch(patchSpec)
				table.insert(beforeList, b)
				table.insert(afterList, a)
				totalPatched += cnt
				for _, e in ipairs(errs) do
					table.insert(allErrors, e)
				end
			end
		end
	elseif opts.sharpHandle ~= nil or opts.handle ~= nil or opts.path ~= nil then
		local b, a, cnt, errs = applySingleInstancePatch(opts)
		table.insert(beforeList, b)
		table.insert(afterList, a)
		totalPatched += cnt
		for _, e in ipairs(errs) do
			table.insert(allErrors, e)
		end
	end

	local styleRuleUpdates = if typeof(opts.styleRuleUpdates) == "table" then opts.styleRuleUpdates else nil
	if styleRuleUpdates then
		for _, ruleSpec in ipairs(styleRuleUpdates) do
			if typeof(ruleSpec) == "table" then
				local b, a, cnt, errs = applyStyleRuleUpdate(ruleSpec)
				table.insert(beforeList, b)
				table.insert(afterList, a)
				totalPatched += cnt
				for _, e in ipairs(errs) do
					table.insert(allErrors, e)
				end
			end
		end
	end

	if totalPatched == 0 and #allErrors == 0 then
		table.insert(allErrors, "No valid patch targets or operations provided")
	end

	local verified = (#allErrors == 0) and (totalPatched > 0)
	local payload: { [string]: any } = {
		ok = verified,
		before = beforeList,
		after = afterList,
		patchedCount = totalPatched,
		verified = verified,
		errors = allErrors,
	}
	return verified, payload
end

function SharpGuiTools.deviceSim(args: { [string]: any }?): { [string]: any }
	local opts = args or {}
	local op = tostring(opts.action or opts.op or opts.mode or "get_device")

	local okSvc, simSvc = pcall(function()
		return game:GetService("StudioDeviceSimulatorService")
	end)
	if not okSvc or not simSvc then
		return {
			ok = false,
			code = "DEVICE_SIMULATOR_UNAVAILABLE",
			message = "StudioDeviceSimulatorService is not available in this Studio environment.",
		}
	end

	if op == "list_devices" then
		local okList, listOrErr = pcall(function()
			return (simSvc :: any):GetDeviceListAsync()
		end)
		if not okList then
			return { ok = false, code = "DEVICE_SIM_ERROR", message = tostring(listOrErr) }
		end
		local devicesOut: { any } = {}
		if typeof(listOrErr) == "table" then
			for _, dev in ipairs(listOrErr) do
				if typeof(dev) == "table" then
					local copy: { [string]: any } = {}
					for k, v in pairs(dev) do
						copy[tostring(k)] = encodeValue(v)
					end
					table.insert(devicesOut, copy)
				else
					table.insert(devicesOut, tostring(dev))
				end
			end
		end
		return { ok = true, op = op, devices = devicesOut }
	elseif op == "get_device" then
		local okCur, curOrErr = pcall(function()
			local svcAny = simSvc :: any
			if typeof(svcAny.GetCurrentDeviceAsync) == "function" then
				return svcAny:GetCurrentDeviceAsync()
			elseif svcAny.CurrentDeviceId ~= nil then
				return svcAny.CurrentDeviceId
			end
			return nil
		end)
		local okOri, ori = pcall(function()
			return (simSvc :: any).Orientation
		end)
		local cam = workspace.CurrentCamera
		return {
			ok = okCur,
			op = op,
			currentDevice = if okCur then encodeValue(curOrErr) else nil,
			orientation = if okOri and ori ~= nil then encodeValue(ori) else nil,
			viewportSize = if cam then encodeValue(cam.ViewportSize) else nil,
			error = if not okCur then tostring(curOrErr) else nil,
		}
	elseif op == "set_device" then
		local deviceId = tostring(opts.deviceId or opts.device or "default")
		local okSet, setErr = pcall(function()
			if deviceId == "default" or deviceId == "" then
				local svcAny = simSvc :: any
				local okDef = pcall(function()
					svcAny:SetDeviceAsync("default")
				end)
				if not okDef and typeof(svcAny.StopSimulationAsync) == "function" then
					svcAny:StopSimulationAsync()
				end
			else
				(simSvc :: any):SetDeviceAsync(deviceId)
			end
		end)
		return {
			ok = okSet,
			op = op,
			deviceId = deviceId,
			error = if not okSet then tostring(setErr) else nil,
		}
	elseif op == "set_resolution" then
		local width = math.max(100, math.floor(tonumber(opts.width) or 1280))
		local height = math.max(100, math.floor(tonumber(opts.height) or 720))
		local okRes, resErr = pcall(function()
			(simSvc :: any):SetResolutionAsync(width, height)
		end)
		if not okRes then
			local okVec, vecErr = pcall(function()
				(simSvc :: any):SetResolutionAsync(Vector2.new(width, height))
			end)
			okRes = okVec
			resErr = vecErr
		end
		return {
			ok = okRes,
			op = op,
			width = width,
			height = height,
			error = if not okRes then tostring(resErr) else nil,
		}
	elseif op == "set_orientation" then
		local orientation = opts.orientation or "LandscapeLeft"
		local okOri, oriErr = pcall(function()
			local svcAny = simSvc :: any
			if typeof(svcAny.SetOrientationAsync) == "function" then
				local enumVal = decodeEnum(orientation, Enum.ScreenOrientation)
				svcAny:SetOrientationAsync(enumVal or orientation)
			else
				local enumVal = decodeEnum(orientation, Enum.ScreenOrientation)
				svcAny.Orientation = enumVal or orientation
			end
		end)
		return {
			ok = okOri,
			op = op,
			orientation = tostring(orientation),
			error = if not okOri then tostring(oriErr) else nil,
		}
	elseif op == "stop" then
		local okStop, stopErr = pcall(function()
			(simSvc :: any):StopSimulationAsync()
		end)
		return {
			ok = okStop,
			op = op,
			error = if not okStop then tostring(stopErr) else nil,
		}
	end

	return {
		ok = false,
		code = "UNKNOWN_DEVICE_SIM_OP",
		message = "Unsupported deviceSim op: " .. op,
	}
end

return SharpGuiTools

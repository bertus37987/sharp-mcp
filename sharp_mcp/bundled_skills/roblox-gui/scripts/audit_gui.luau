--!strict
-- audit_gui.luau
-- Edit & Play Mode Roblox GUI Audit Script.
-- Checks:
--   1. StarterGui direct-child rule & ResetOnSpawn = false for persistent ScreenGuis
--   2. ZIndexBehavior.Sibling enforcement (mandatory for CanvasGroup) & DisplayOrder collisions
--   3. ScreenInsets & live TopbarInset overlap detection on visible interactive controls
--   4. >= 44x44px touch target enforcement on all visible GuiButtons & TextBoxes
--   5. Viewport offscreen clamping (excluding full-bleed None-inset scrims & ScrollingFrame children)
--   6. Mobile bottom-left thumbstick & bottom-right jump zone collisions (when viewport <= 960px wide)
--   7. StyleRule.SelectorError checks & CanvasGroup texture-memory budget warnings
--
-- Run via execute_luau in Edit mode (audits StarterGui) or Play/Client mode (audits PlayerGui).

local GuiService = game:GetService("GuiService")
local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local StarterGui = game:GetService("StarterGui")
local UserInputService = game:GetService("UserInputService")

local MIN_TOUCH_PX = 44
local MAX_CANVAS_GROUP_BUDGET = 6

local errors: { string } = {}
local warnings: { string } = {}

local isRunning = RunService:IsRunning()
local localPlayer = Players.LocalPlayer
local targetRoot: Instance = if isRunning and localPlayer
	then (localPlayer:FindFirstChild("PlayerGui") or StarterGui)
	else StarterGui

local function getViewportSize(): Vector2
	local cam = workspace.CurrentCamera
	if cam and cam.ViewportSize.X > 0 and cam.ViewportSize.Y > 0 then
		return cam.ViewportSize
	end
	for _, ch in ipairs(targetRoot:GetChildren()) do
		if ch:IsA("ScreenGui") and ch.AbsoluteSize.X > 0 and ch.AbsoluteSize.Y > 0 then
			return ch.AbsoluteSize
		end
	end
	return Vector2.new(1280, 720)
end

local function getTopbarBottomPx(): number
	local ok, insetRect = pcall(function()
		return GuiService.TopbarInset
	end)
	if ok and typeof(insetRect) == "Rect" and insetRect.Max.Y > 0 then
		return insetRect.Max.Y
	end
	local ok2, tl = pcall(function()
		local v, _ = GuiService:GetGuiInset()
		return v
	end)
	if ok2 and typeof(tl) == "Vector2" then
		return tl.Y
	end
	return 0
end

local function isEffectivelyVisible(obj: Instance): boolean
	local cur: Instance? = obj
	while cur and cur ~= targetRoot do
		if cur:IsA("ScreenGui") then
			if not cur.Enabled then
				return false
			end
			return true
		elseif cur:IsA("GuiObject") then
			if not cur.Visible then
				return false
			end
		end
		cur = cur.Parent
	end
	return cur == targetRoot
end

local function isInsideScrollingFrame(obj: Instance): boolean
	local cur = obj.Parent
	while cur and not cur:IsA("ScreenGui") do
		if cur:IsA("ScrollingFrame") then
			return true
		end
		cur = cur.Parent
	end
	return false
end

local function isIntentionalFullBleed(sg: ScreenGui, obj: GuiObject): boolean
	if sg.ScreenInsets == Enum.ScreenInsets.None then
		if sg.Name == "ModalBackdropGui" or sg.Name == "BackdropVignetteGui" or sg.Name == "LoadingTransitionGui" or sg.Name == "LoadingTransitionTemplate" then
			return true
		end
		if obj.Size.X.Scale >= 0.99 and obj.Size.Y.Scale >= 0.99 then
			return true
		end
	end
	return false
end

-- 1. Check nested ScreenGuis inside StarterGui folders (breaks ResetOnSpawn=false)
for _, desc in ipairs(StarterGui:GetDescendants()) do
	if desc:IsA("ScreenGui") and desc.Parent ~= StarterGui then
		table.insert(
			errors,
			string.format("Nested ScreenGui '%s' under '%s' (must be direct child of StarterGui so ResetOnSpawn=false works).", desc.Name, desc.Parent and desc.Parent.Name or "?")
		)
	end
end

-- 2. Inspect StyleRules in ReplicatedStorage
for _, desc in ipairs(ReplicatedStorage:GetDescendants()) do
	if desc:IsA("StyleRule") then
		if desc.SelectorError ~= "" then
			table.insert(errors, string.format("StyleRule '%s' SelectorError: %s", desc:GetFullName(), desc.SelectorError))
		end
	end
end

local viewport = getViewportSize()
local topbarBottom = getTopbarBottomPx()
local screenGuis: { ScreenGui } = {}
local displayOrders: { [number]: string } = {}
local canvasGroupCount = 0
local interactiveCount = 0

for _, child in ipairs(targetRoot:GetChildren()) do
	if child:IsA("ScreenGui") and not (isRunning and child.Name == "Freecam") then
		table.insert(screenGuis, child)

		if displayOrders[child.DisplayOrder] then
			table.insert(
				warnings,
				string.format("Duplicate DisplayOrder=%d shared by '%s' and '%s'.", child.DisplayOrder, displayOrders[child.DisplayOrder], child.Name)
			)
		else
			displayOrders[child.DisplayOrder] = child.Name
		end

		if child.ResetOnSpawn and child.Name ~= "ContextualPromptGui" then
			table.insert(warnings, string.format("ScreenGui '%s' has ResetOnSpawn=true; persistent HUD/Modals should use ResetOnSpawn=false.", child.Name))
		end

		local hasCanvasGroup = child:FindFirstChildWhichIsA("CanvasGroup", true) ~= nil
		if child.ZIndexBehavior ~= Enum.ZIndexBehavior.Sibling then
			local msg = string.format("ScreenGui '%s' ZIndexBehavior is %s (recommended Sibling; mandatory for CanvasGroup).", child.Name, tostring(child.ZIndexBehavior))
			if hasCanvasGroup then
				table.insert(errors, msg)
			else
				table.insert(warnings, msg)
			end
		end

		for _, desc in ipairs(child:GetDescendants()) do
			if desc:IsA("CanvasGroup") then
				canvasGroupCount += 1
				if isInsideScrollingFrame(desc) then
					table.insert(warnings, string.format("CanvasGroup '%s' is inside a ScrollingFrame; avoid per-item CanvasGroups due to VRAM limits.", desc:GetFullName()))
				end
			end

			if desc:IsA("GuiObject") and isEffectivelyVisible(desc) then
				local pos = desc.AbsolutePosition
				local size = desc.AbsoluteSize
				local isInteractive = desc:IsA("GuiButton") or desc:IsA("TextBox")

				if isInteractive then
					interactiveCount += 1

					-- Touch target check (skip full-bleed ModalBackdropGui scrim)
					if not isIntentionalFullBleed(child, desc) then
						if size.X < (MIN_TOUCH_PX - 0.5) or size.Y < (MIN_TOUCH_PX - 0.5) then
							table.insert(
								errors,
								string.format("TouchTarget < %dpx: '%s' is %.1fx%.1fpx.", MIN_TOUCH_PX, desc:GetFullName(), size.X, size.Y)
							)
						end

						-- Topbar overlap check: CoreUISafeInsets/DeviceSafeInsets already shift origin below TopbarInset;
						-- TopbarSafeInsets lives beside the Roblox menu. Only ScreenInsets.None overlaps TopbarInset vertically.
						if child.ScreenInsets == Enum.ScreenInsets.None and topbarBottom > 0 then
							if pos.Y < (topbarBottom - 1.5) and not isInsideScrollingFrame(desc) then
								table.insert(
									errors,
									string.format("TopbarOverlap: '%s' top=%.1fpx enters TopbarInset=%.1fpx.", desc:GetFullName(), pos.Y, topbarBottom)
								)
							end
						end

						-- Mobile thumbstick / jump button safe-zone heuristic on compact viewports
						local isTouchSim = viewport.X <= 960 or (UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled)
						if isTouchSim and child.Name == "MainHudGui" then
							local inThumbstick = pos.X < (viewport.X * 0.28) and (pos.Y + size.Y) > (viewport.Y * 0.60)
							local inJumpBtn = (pos.X + size.X) > (viewport.X * 0.80) and (pos.Y + size.Y) > (viewport.Y * 0.64)
							if inThumbstick then
								table.insert(
									warnings,
									string.format("MobileThumbstickZone overlap candidate: '%s' (%.0f,%.0f %.0fx%.0f).", desc:GetFullName(), pos.X, pos.Y, size.X, size.Y)
								)
							elseif inJumpBtn then
								table.insert(
									warnings,
									string.format("MobileJumpZone overlap candidate: '%s' (%.0f,%.0f %.0fx%.0f).", desc:GetFullName(), pos.X, pos.Y, size.X, size.Y)
								)
							end
						end
					end
				end

				-- Offscreen & safe-area clamping check against parent ScreenGui bounds (falls back to viewport)
				if size.X > 0 and size.Y > 0 and not isInsideScrollingFrame(desc) and not isIntentionalFullBleed(child, desc) then
					local boundPos = if child.AbsoluteSize.X > 0 and child.AbsoluteSize.Y > 0 then child.AbsolutePosition else Vector2.zero
					local boundSize = if child.AbsoluteSize.X > 0 and child.AbsoluteSize.Y > 0 then child.AbsoluteSize else viewport
					if pos.X < (boundPos.X - 2)
						or pos.Y < (boundPos.Y - 2)
						or (pos.X + size.X) > (boundPos.X + boundSize.X + 2)
						or (pos.Y + size.Y) > (boundPos.Y + boundSize.Y + 2)
					then
						table.insert(
							errors,
							string.format(
								"OffscreenClip: '%s' rect=(%.0f, %.0f -> %.0f, %.0f) exceeds ScreenGui safe bounds=(%.0f, %.0f -> %.0f, %.0f).",
								desc:GetFullName(),
								pos.X,
								pos.Y,
								pos.X + size.X,
								pos.Y + size.Y,
								boundPos.X,
								boundPos.Y,
								boundPos.X + boundSize.X,
								boundPos.Y + boundSize.Y
							)
						)
					end
				end
			end
		end
	end
end

if canvasGroupCount > MAX_CANVAS_GROUP_BUDGET then
	table.insert(warnings, string.format("High CanvasGroup count (%d > %d); excess CanvasGroups may render blank on low QualityLevel.", canvasGroupCount, MAX_CANVAS_GROUP_BUDGET))
end

local report = {
	mode = if isRunning then "Play" else "Edit",
	targetRoot = targetRoot:GetFullName(),
	viewport = { x = math.round(viewport.X), y = math.round(viewport.Y) },
	topbarBottomPx = math.round(topbarBottom),
	screenGuiCount = #screenGuis,
	interactiveCount = interactiveCount,
	canvasGroupCount = canvasGroupCount,
	errorCount = #errors,
	warningCount = #warnings,
	status = if #errors == 0 then "PASS" else "FAIL",
	errors = errors,
	warnings = warnings,
}

return HttpService:JSONEncode(report)

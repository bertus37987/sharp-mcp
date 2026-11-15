--!strict
-- build_standard_game_gui.luau
-- Builds the complete Standard Game GUI showcase in StarterGui + ReplicatedStorage + StarterPlayerScripts:
--   - DisplayOrder Z-Layers (0..1000) with ScreenInsets, ResetOnSpawn=false, ZIndexBehavior=Sibling
--   - Always-On HUD: PlayerStatus (HP/XP/Level), CurrencyBar (+ Shop), SideRail, ActionHotbar (1..5), ObjectiveTracker
--   - TopbarWidgetsGui (TopbarSafeInsets) & ContextualPromptGui
--   - ModalMenusGui: Tabbed Shop, Inventory (+ Search + 3D ViewportFrame Inspector), Quests, Index/Codes, Settings (UIDragDetector sliders + toggles)
--   - Overlays: ModalBackdropGui, NpcDialogGui (ViewportFrame 3D bust + MaxVisibleGraphemes typewriter), ConfirmDialogGui, FloatingTooltipGui, ToastNotificationGui
--   - ReplicatedStorage.LoadingTransitionTemplate (DisplayOrder=1000, ScreenInsets=None)
--   - StarterPlayerScripts.StandardGuiController (LocalScript wiring full interactive runtime + Debug BindableFunction)
--
-- Prerequisite in Edit mode:
--   Install scripts/ui_theme_and_components.luau as a ModuleScript at ReplicatedStorage.UIThemeAndComponents
--   (or ReplicatedStorage.Modules.UIThemeAndComponents), then run this script via execute_luau.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local StarterPlayer = game:GetService("StarterPlayer")

local CONFIG = {
	EditPreviewModal = "Shop", -- "Shop" | "Inventory" | "Quests" | "IndexCodes" | "Settings" | "None"
	EditPreviewToast = false,
	Assets = (_G.ROBLOX_GUI_ASSETS :: any) or {
		-- Optional uploaded rbxassetid:// overrides:
		-- Panel9SliceId = "rbxassetid://...",
		-- Panel9SliceCenter = Rect.new(111, 131, 400, 339),
		-- Button9SliceId = "rbxassetid://...",
		-- Button9SliceCenter = Rect.new(110, 92, 403, 171),
		-- IconAtlasId = "rbxassetid://...",
		-- IconRects = {
		--   coin = { offset = Vector2.new(4, 4), size = Vector2.new(256, 256) },
		--   gem = { offset = Vector2.new(264, 4), size = Vector2.new(256, 256) },
		--   combat = { offset = Vector2.new(4, 264), size = Vector2.new(256, 256) },
		--   chest = { offset = Vector2.new(264, 264), size = Vector2.new(256, 256) },
		-- },
	},
}

local modInst = ReplicatedStorage:FindFirstChild("UIThemeAndComponents")
	or (ReplicatedStorage:FindFirstChild("Modules") and ReplicatedStorage.Modules:FindFirstChild("UIThemeAndComponents"))
assert(
	modInst and modInst:IsA("ModuleScript"),
	"Missing ModuleScript ReplicatedStorage.UIThemeAndComponents. Install scripts/ui_theme_and_components.luau first."
)

local UIKit = require(modInst) :: any
UIKit.SetAssets(CONFIG.Assets)

local styleSheet = UIKit.BuildStyleSheet(ReplicatedStorage)

-- Clean previous generated ScreenGuis cleanly
local GUI_NAMES = {
	"BackdropVignetteGui",
	"MainHudGui",
	"TopbarWidgetsGui",
	"ContextualPromptGui",
	"ModalBackdropGui",
	"ModalMenusGui",
	"NpcDialogGui",
	"ConfirmDialogGui",
	"FloatingTooltipGui",
	"ToastNotificationGui",
}
for _, name in ipairs(GUI_NAMES) do
	local old = StarterGui:FindFirstChild(name)
	if old then
		old:Destroy()
	end
end

local function makeLayer(name: string, displayOrder: number, insets: Enum.ScreenInsets, enabled: boolean): ScreenGui
	local sg = Instance.new("ScreenGui")
	sg.Name = name
	sg.DisplayOrder = displayOrder
	sg.ScreenInsets = insets
	sg.ResetOnSpawn = false
	sg.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
	sg.Enabled = enabled
	sg.Parent = StarterGui
	UIKit.AttachStyleLink(sg, styleSheet)
	return sg
end

local function makeCorner(parent: Instance, radius: UDim)
	local c = Instance.new("UICorner")
	c.CornerRadius = radius
	c.Parent = parent
end

local function makeStroke(parent: Instance, color: Color3, thickness: number?, trans: number?)
	local s = Instance.new("UIStroke")
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Color = color
	s.Thickness = thickness or 1.5
	s.Transparency = trans or 0.25
	s.Parent = parent
	return s
end

local function makeLabel(
	parent: Instance,
	name: string,
	text: string,
	size: UDim2,
	pos: UDim2,
	textSize: number,
	font: Font,
	color: Color3?,
	xAlign: Enum.TextXAlignment?
): TextLabel
	local lbl = Instance.new("TextLabel")
	lbl.Name = name
	lbl.Size = size
	lbl.Position = pos
	lbl.BackgroundTransparency = 1
	lbl.Text = text
	lbl.TextSize = textSize
	lbl.FontFace = font
	lbl.TextColor3 = color or UIKit.Tokens.Colors.TextPrimary
	lbl.TextXAlignment = xAlign or Enum.TextXAlignment.Left
	lbl.Parent = parent
	return lbl
end

-- Build procedural 3D preview models for ViewportFrames (zero external MeshId dependencies)
local prevModels = ReplicatedStorage:FindFirstChild("GuiPreviewModels")
if prevModels then
	prevModels:Destroy()
end
local modelsFolder = Instance.new("Folder")
modelsFolder.Name = "GuiPreviewModels"
modelsFolder.Parent = ReplicatedStorage

local function buildSwordModel(): Model
	local m = Instance.new("Model")
	m.Name = "GoldenSword"
	local blade = Instance.new("Part")
	blade.Name = "Blade"
	blade.Anchored = true
	blade.Size = Vector3.new(0.45, 3.6, 0.14)
	blade.Color = Color3.fromRGB(220, 232, 248)
	blade.Material = Enum.Material.Metal
	blade.CFrame = CFrame.new(0, 1.4, 0)
	blade.Parent = m

	local fuller = Instance.new("Part")
	fuller.Name = "Fuller"
	fuller.Anchored = true
	fuller.Size = Vector3.new(0.16, 2.8, 0.18)
	fuller.Color = Color3.fromRGB(64, 178, 255)
	fuller.Material = Enum.Material.Neon
	fuller.CFrame = CFrame.new(0, 1.35, 0)
	fuller.Parent = m

	local guard = Instance.new("Part")
	guard.Name = "Guard"
	guard.Anchored = true
	guard.Size = Vector3.new(1.65, 0.3, 0.38)
	guard.Color = Color3.fromRGB(245, 192, 68)
	guard.Material = Enum.Material.Metal
	guard.CFrame = CFrame.new(0, -0.45, 0)
	guard.Parent = m

	local grip = Instance.new("Part")
	grip.Name = "Grip"
	grip.Anchored = true
	grip.Size = Vector3.new(0.28, 1.1, 0.28)
	grip.Color = Color3.fromRGB(62, 42, 34)
	grip.Material = Enum.Material.SmoothPlastic
	grip.CFrame = CFrame.new(0, -1.1, 0)
	grip.Parent = m

	local pommel = Instance.new("Part")
	pommel.Name = "Pommel"
	pommel.Anchored = true
	pommel.Shape = Enum.PartType.Ball
	pommel.Size = Vector3.new(0.5, 0.5, 0.5)
	pommel.Color = Color3.fromRGB(245, 192, 68)
	pommel.Material = Enum.Material.Metal
	pommel.CFrame = CFrame.new(0, -1.75, 0)
	pommel.Parent = m

	m.PrimaryPart = guard
	m:PivotTo(CFrame.Angles(0, 0, math.rad(-18)))
	m.Parent = modelsFolder
	return m
end

local function buildGemRelicModel(): Model
	local m = Instance.new("Model")
	m.Name = "CrystalRelic"
	local core = Instance.new("Part")
	core.Name = "Crystal"
	core.Anchored = true
	core.Size = Vector3.new(1.5, 2.3, 1.5)
	core.Color = Color3.fromRGB(56, 212, 255)
	core.Material = Enum.Material.Glass
	core.CFrame = CFrame.Angles(math.rad(25), math.rad(35), math.rad(15))
	core.Parent = m

	local ring = Instance.new("Part")
	ring.Name = "Ring"
	ring.Anchored = true
	ring.Size = Vector3.new(2.4, 0.22, 2.4)
	ring.Color = Color3.fromRGB(248, 196, 76)
	ring.Material = Enum.Material.Metal
	ring.CFrame = CFrame.Angles(math.rad(-20), 0, math.rad(12))
	ring.Parent = m

	m.PrimaryPart = core
	m.Parent = modelsFolder
	return m
end

local function buildShieldModel(): Model
	local m = Instance.new("Model")
	m.Name = "RoyalShield"
	local plate = Instance.new("Part")
	plate.Name = "Plate"
	plate.Anchored = true
	plate.Size = Vector3.new(2.3, 2.8, 0.28)
	plate.Color = Color3.fromRGB(168, 38, 46)
	plate.Material = Enum.Material.SmoothPlastic
	plate.Parent = m

	local rim = Instance.new("Part")
	rim.Name = "Rim"
	rim.Anchored = true
	rim.Size = Vector3.new(2.55, 3.05, 0.2)
	rim.Color = Color3.fromRGB(240, 188, 68)
	rim.Material = Enum.Material.Metal
	rim.CFrame = CFrame.new(0, 0, -0.05)
	rim.Parent = m

	local boss = Instance.new("Part")
	boss.Name = "Boss"
	boss.Anchored = true
	boss.Shape = Enum.PartType.Ball
	boss.Size = Vector3.new(0.85, 0.85, 0.45)
	boss.Color = Color3.fromRGB(248, 206, 92)
	boss.Material = Enum.Material.Metal
	boss.CFrame = CFrame.new(0, 0.15, 0.14)
	boss.Parent = m

	m.PrimaryPart = plate
	m.Parent = modelsFolder
	return m
end

local function buildNpcBustModel(): Model
	local m = Instance.new("Model")
	m.Name = "MerchantNpcBust"
	local torso = Instance.new("Part")
	torso.Name = "Torso"
	torso.Anchored = true
	torso.Size = Vector3.new(2.1, 1.8, 1.1)
	torso.Color = Color3.fromRGB(44, 72, 128)
	torso.Material = Enum.Material.SmoothPlastic
	torso.CFrame = CFrame.new(0, -0.7, 0)
	torso.Parent = m

	local collar = Instance.new("Part")
	collar.Name = "Collar"
	collar.Anchored = true
	collar.Size = Vector3.new(2.2, 0.35, 1.2)
	collar.Color = Color3.fromRGB(240, 188, 72)
	collar.Material = Enum.Material.Metal
	collar.CFrame = CFrame.new(0, 0.15, 0)
	collar.Parent = m

	local head = Instance.new("Part")
	head.Name = "Head"
	head.Anchored = true
	head.Size = Vector3.new(1.35, 1.35, 1.35)
	head.Color = Color3.fromRGB(242, 206, 170)
	head.Material = Enum.Material.SmoothPlastic
	head.CFrame = CFrame.new(0, 1.05, 0)
	head.Parent = m

	local visor = Instance.new("Part")
	visor.Name = "HatBrim"
	visor.Anchored = true
	visor.Size = Vector3.new(1.85, 0.22, 1.85)
	visor.Color = Color3.fromRGB(30, 40, 64)
	visor.Material = Enum.Material.SmoothPlastic
	visor.CFrame = CFrame.new(0, 1.72, 0)
	visor.Parent = m

	local crown = Instance.new("Part")
	crown.Name = "HatCrown"
	crown.Anchored = true
	crown.Size = Vector3.new(1.3, 0.65, 1.3)
	crown.Color = Color3.fromRGB(218, 162, 54)
	crown.Material = Enum.Material.SmoothPlastic
	crown.CFrame = CFrame.new(0, 2.08, 0)
	crown.Parent = m

	m.PrimaryPart = head
	m.Parent = modelsFolder
	return m
end

local swordModel = buildSwordModel()
local gemRelicModel = buildGemRelicModel()
buildShieldModel()
local npcBustModel = buildNpcBustModel()

-- =========================================================================
-- LAYER 0: BackdropVignetteGui (ScreenInsets = None, non-interactive)
-- =========================================================================
local backdropVignetteGui = makeLayer("BackdropVignetteGui", 0, Enum.ScreenInsets.None, true)
local vignetteFrame = Instance.new("Frame")
vignetteFrame.Name = "DamageVignette"
vignetteFrame.Size = UDim2.fromScale(1, 1)
vignetteFrame.BackgroundColor3 = Color3.fromRGB(190, 28, 42)
vignetteFrame.BackgroundTransparency = 1
vignetteFrame.Active = false
vignetteFrame.BorderSizePixel = 0
vignetteFrame.Parent = backdropVignetteGui

-- =========================================================================
-- LAYER 10: MainHudGui (CoreUISafeInsets)
-- =========================================================================
local mainHudGui = makeLayer("MainHudGui", 10, Enum.ScreenInsets.CoreUISafeInsets, true)
UIKit.BindResponsiveScale(mainHudGui, 0.86, 1.08)

pcall(function()
	local q = Instance.new("StyleQuery")
	q.Name = "CompactPhone"
	q:SetConditions({ MaxSize = Vector2.new(959, 9999) })
	q.Parent = mainHudGui
end)

-- 1A. PlayerStatus (Top-Left)
local playerStatus = UIKit.CreatePanel({
	Name = "PlayerStatus",
	Parent = mainHudGui,
	Size = UDim2.fromOffset(224, 68),
	Position = UDim2.fromOffset(10, 8),
	AnchorPoint = Vector2.zero,
})
makeLabel(
	playerStatus,
	"LevelTitle",
	"Lv. 14  Vanguard",
	UDim2.new(1, -20, 0, 20),
	UDim2.fromOffset(10, 6),
	14,
	UIKit.Tokens.Fonts.Title,
	UIKit.Tokens.Colors.TextPrimary
)
local hpTrack = Instance.new("Frame")
hpTrack.Name = "HpTrack"
hpTrack.Size = UDim2.new(1, -20, 0, 14)
hpTrack.Position = UDim2.fromOffset(10, 30)
hpTrack.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
hpTrack.BorderSizePixel = 0
hpTrack.Parent = playerStatus
makeCorner(hpTrack, UIKit.Tokens.Radii.Pill)
makeStroke(hpTrack, UIKit.Tokens.Colors.OutlineInk, 1.8, 0.1)

local hpFill = Instance.new("Frame")
hpFill.Name = "Fill"
hpFill.Size = UDim2.fromScale(0.84, 1)
hpFill.BackgroundColor3 = UIKit.Tokens.Colors.Success
hpFill.BorderSizePixel = 0
hpFill.Parent = hpTrack
UIKit.ApplyGlossySurface(hpFill, {
	GradientKey = "Success",
	CornerRadius = UIKit.Tokens.Radii.Pill,
	StrokeColor = UIKit.Tokens.Colors.OutlineInk,
	StrokeThickness = 1.2,
	InnerHighlight = false,
})
local hpValLbl = makeLabel(
	hpTrack,
	"HpValue",
	"840 / 1000",
	UDim2.fromScale(1, 1),
	UDim2.new(),
	10,
	UIKit.Tokens.Fonts.Mono,
	Color3.fromRGB(255, 255, 255),
	Enum.TextXAlignment.Center
)
UIKit.AttachTextStroke(hpValLbl, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.1)

local xpTrack = Instance.new("Frame")
xpTrack.Name = "XpTrack"
xpTrack.Size = UDim2.new(1, -20, 0, 8)
xpTrack.Position = UDim2.fromOffset(10, 50)
xpTrack.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
xpTrack.BorderSizePixel = 0
xpTrack.Parent = playerStatus
makeCorner(xpTrack, UIKit.Tokens.Radii.Pill)
makeStroke(xpTrack, UIKit.Tokens.Colors.OutlineInk, 1.5, 0.15)

local xpFill = Instance.new("Frame")
xpFill.Name = "Fill"
xpFill.Size = UDim2.fromScale(0.68, 1)
xpFill.BackgroundColor3 = UIKit.Tokens.Colors.Primary
xpFill.BorderSizePixel = 0
xpFill.Parent = xpTrack
UIKit.ApplyGlossySurface(xpFill, {
	GradientKey = "Primary",
	CornerRadius = UIKit.Tokens.Radii.Pill,
	StrokeColor = UIKit.Tokens.Colors.OutlineInk,
	StrokeThickness = 1.0,
	InnerHighlight = false,
})

-- 1B. CurrencyBar (Top-Right)
local currencyBar = UIKit.CreatePanel({
	Name = "CurrencyBar",
	Parent = mainHudGui,
	Size = UDim2.fromOffset(276, 56),
	Position = UDim2.new(1, -10, 0, 8),
	AnchorPoint = Vector2.new(1, 0),
})
local cRow = Instance.new("UIListLayout")
cRow.FillDirection = Enum.FillDirection.Horizontal
cRow.HorizontalAlignment = Enum.HorizontalAlignment.Right
cRow.VerticalAlignment = Enum.VerticalAlignment.Center
cRow.SortOrder = Enum.SortOrder.LayoutOrder
cRow.Padding = UDim.new(0, 8)
cRow.Parent = currencyBar

local cPad = Instance.new("UIPadding")
cPad.PaddingLeft = UDim.new(0, 10)
cPad.PaddingRight = UDim.new(0, 4)
cPad.Parent = currencyBar

local coinIcon = UIKit.CreateBadgeIcon(currencyBar, "coin", "$", UIKit.Tokens.Colors.Gold, 26)
coinIcon.LayoutOrder = 1
local coinsLabel = makeLabel(
	currencyBar,
	"CoinsLabel",
	"12,450",
	UDim2.fromOffset(72, 26),
	UDim2.new(),
	15,
	UIKit.Tokens.Fonts.Title,
	UIKit.Tokens.Colors.Gold
)
coinsLabel.LayoutOrder = 2

local gemIcon = UIKit.CreateBadgeIcon(currencyBar, "gem", "*", UIKit.Tokens.Colors.Gem, 26)
gemIcon.LayoutOrder = 3
local gemsLabel = makeLabel(
	currencyBar,
	"GemsLabel",
	"320",
	UDim2.fromOffset(48, 26),
	UDim2.new(),
	15,
	UIKit.Tokens.Fonts.Title,
	UIKit.Tokens.Colors.Gem
)
gemsLabel.LayoutOrder = 4

local addCurrencyBtn = UIKit.CreateButton({
	Name = "AddCurrencyBtn",
	Parent = currencyBar,
	Text = "+",
	Size = UDim2.fromOffset(52, 52),
	LayoutOrder = 5,
	Variant = "Success",
	TextSize = 22,
})

-- 1C. ObjectiveTracker (Collapsible card top-right below CurrencyBar; hidden on Compact phone widths via controller)
local objectiveCard = UIKit.CreatePanel({
	Name = "ObjectiveTracker",
	Parent = mainHudGui,
	Size = UDim2.fromOffset(250, 86),
	Position = UDim2.new(1, -10, 0, 72),
	AnchorPoint = Vector2.new(1, 0),
})
objectiveCard:AddTag("CompactHide")
makeLabel(
	objectiveCard,
	"QuestHeading",
	"ACTIVE QUEST",
	UDim2.new(1, -64, 0, 20),
	UDim2.fromOffset(12, 8),
	11,
	UIKit.Tokens.Fonts.Title,
	UIKit.Tokens.Colors.Gold
)
local objBody = makeLabel(
	objectiveCard,
	"QuestBody",
	"Defeat 5 Sentinel Golems (3/5)",
	UDim2.new(1, -64, 0, 42),
	UDim2.fromOffset(12, 30),
	13,
	UIKit.Tokens.Fonts.Body,
	UIKit.Tokens.Colors.TextSecondary
)
objBody.TextWrapped = true
objBody.TextYAlignment = Enum.TextYAlignment.Top

local collapseObjBtn = UIKit.CreateButton({
	Name = "CollapseObjectiveBtn",
	Parent = objectiveCard,
	Text = "-",
	Size = UDim2.fromOffset(52, 52),
	Position = UDim2.new(1, -6, 0, 6),
	AnchorPoint = Vector2.new(1, 0),
	Variant = "Secondary",
	TextSize = 18,
})

-- 1D. SideRail (5 standard modal entry points; ThemeSheet #SideRail/#RailLayout & @CompactPhone >> rules drive layout)
local sideRail = Instance.new("Frame")
sideRail.Name = "SideRail"
sideRail.BackgroundTransparency = 1
sideRail.Parent = mainHudGui

local sideRailLayout = Instance.new("UIListLayout")
sideRailLayout.Name = "RailLayout"
sideRailLayout.SortOrder = Enum.SortOrder.LayoutOrder
sideRailLayout.Padding = UDim.new(0, 6)
sideRailLayout.Parent = sideRail

local railSpecs = {
	{ Key = "Shop", Label = "Shop", Sprite = "coin", Glyph = "$", Accent = UIKit.Tokens.Colors.Primary, Badge = "NEW" },
	{ Key = "Inventory", Label = "Bag", Sprite = "combat", Glyph = "I", Accent = UIKit.Tokens.Colors.Warning, Badge = "" },
	{ Key = "Quests", Label = "Quests", Sprite = "chest", Glyph = "Q", Accent = UIKit.Tokens.Colors.Success, Badge = "2" },
	{ Key = "IndexCodes", Label = "Index", Sprite = "gem", Glyph = "X", Accent = UIKit.Tokens.Colors.Accent, Badge = "" },
	{ Key = "Settings", Label = "Config", Sprite = "coin", Glyph = "*", Accent = UIKit.Tokens.Colors.Secondary, Badge = "" },
}

for idx, spec in ipairs(railSpecs) do
	local btn = Instance.new("TextButton")
	btn.Name = spec.Key .. "Btn"
	btn.LayoutOrder = idx
	btn.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
	btn.BackgroundTransparency = 0.05
	btn.Text = ""
	btn.AutoButtonColor = false
	btn.BorderSizePixel = 0
	btn.Parent = sideRail
	btn:AddTag("RailBtn")
	makeCorner(btn, UIKit.Tokens.Radii.Button)
	UIKit.AttachStackedStrokes(btn, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = math.max(2.5, UIKit.Tokens.Strokes.Panel * 0.72),
		InnerColor = spec.Accent,
		InnerThickness = 1.6,
		InnerTransparency = 0.22,
		CornerRadius = UIKit.Tokens.Radii.Button,
	})
	local railGrad = Instance.new("UIGradient")
	railGrad.Name = "RailGloss"
	railGrad.Rotation = -35
	railGrad.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0.0, Color3.fromRGB(255, 255, 255)),
		ColorSequenceKeypoint.new(0.45, Color3.fromRGB(244, 246, 252)),
		ColorSequenceKeypoint.new(1.0, Color3.fromRGB(198, 206, 224)),
	})
	railGrad.Parent = btn
	UIKit.EnsureMinTouchTarget(btn, 52)

	local rowContent = Instance.new("Frame")
	rowContent.Name = "RowContent"
	rowContent.Size = UDim2.fromScale(1, 1)
	rowContent.BackgroundTransparency = 1
	rowContent.BorderSizePixel = 0
	rowContent.Parent = btn

	local row = Instance.new("UIListLayout")
	row.FillDirection = Enum.FillDirection.Horizontal
	row.HorizontalAlignment = Enum.HorizontalAlignment.Center
	row.VerticalAlignment = Enum.VerticalAlignment.Center
	row.SortOrder = Enum.SortOrder.LayoutOrder
	row.Padding = UDim.new(0, 8)
	row.Parent = rowContent

	local icon = UIKit.CreateBadgeIcon(rowContent, spec.Sprite, spec.Glyph, spec.Accent, 26)
	icon.LayoutOrder = 1

	local title = makeLabel(
		rowContent,
		"RailTitle",
		spec.Label,
		UDim2.fromOffset(66, 28),
		UDim2.new(),
		14,
		UIKit.Tokens.Fonts.Heading,
		UIKit.Tokens.Colors.TextPrimary
	)
	title.LayoutOrder = 2
	title:AddTag("RailTitle")

	if spec.Badge ~= "" then
		local dot = Instance.new("TextLabel")
		dot.Name = "BadgeDot"
		dot.Size = UDim2.fromOffset(34, 18)
		dot.Position = UDim2.new(1, -2, 0, 2)
		dot.AnchorPoint = Vector2.new(1, 0)
		dot.Rotation = UIKit.Tokens.Motifs.BadgeRotation
		dot.ZIndex = 4
		dot.BackgroundColor3 = UIKit.Tokens.Colors.Danger
		dot.Text = spec.Badge
		dot.TextColor3 = UIKit.Tokens.Colors.TextOnDanger
		dot.TextSize = 10
		dot.FontFace = UIKit.Tokens.Fonts.Title
		dot.BorderSizePixel = 0
		dot.Parent = btn
		UIKit.ApplyGlossySurface(dot, {
			GradientKey = "Danger",
			CornerRadius = UIKit.Tokens.Radii.Pill,
			StrokeColor = UIKit.Tokens.Colors.OutlineInk,
			StrokeThickness = 1.8,
			InnerHighlight = false,
		})
		UIKit.AttachTextStroke(dot, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.1)
	end
end

-- 1E. ActionHotbar (Bottom-Center, clears mobile DynamicThumbstick & TouchJumpButton)
local actionHotbar = Instance.new("Frame")
actionHotbar.Name = "ActionHotbar"
actionHotbar.Size = UDim2.fromOffset(298, 60)
actionHotbar.Position = UDim2.new(0.5, 0, 1, -10)
actionHotbar.AnchorPoint = Vector2.new(0.5, 1)
actionHotbar.BackgroundTransparency = 1
actionHotbar.Parent = mainHudGui

local hotbarLayout = Instance.new("UIListLayout")
hotbarLayout.FillDirection = Enum.FillDirection.Horizontal
hotbarLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
hotbarLayout.VerticalAlignment = Enum.VerticalAlignment.Center
hotbarLayout.SortOrder = Enum.SortOrder.LayoutOrder
hotbarLayout.Padding = UDim.new(0, 6)
hotbarLayout.Parent = actionHotbar

local hotbarItems = {
	{ Name = "Sword", Sprite = "combat", Glyph = "SW", Accent = UIKit.Tokens.Colors.Gold },
	{ Name = "Shield", Sprite = "combat", Glyph = "SH", Accent = UIKit.Tokens.Colors.Primary },
	{ Name = "Potion", Sprite = "gem", Glyph = "HP", Accent = UIKit.Tokens.Colors.Success },
	{ Name = "Dash", Sprite = "gem", Glyph = "DS", Accent = UIKit.Tokens.Colors.Gem },
	{ Name = "Relic", Sprite = "chest", Glyph = "RL", Accent = UIKit.Tokens.Rarity.Epic },
}
for slotIdx, item in ipairs(hotbarItems) do
	local slot = Instance.new("TextButton")
	slot.Name = "Slot" .. tostring(slotIdx)
	slot.Size = UDim2.fromOffset(54, 54)
	slot.LayoutOrder = slotIdx
	slot.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
	slot.BackgroundTransparency = 0.05
	slot.Text = ""
	slot.AutoButtonColor = false
	slot.BorderSizePixel = 0
	slot.Parent = actionHotbar
	makeCorner(slot, UIKit.Tokens.Radii.Button)
	local stroke = makeStroke(
		slot,
		if slotIdx == 1 then UIKit.Tokens.Colors.Gold else UIKit.Tokens.Colors.OutlineInk,
		if slotIdx == 1 then 2.8 else 2.0,
		0.05
	)
	stroke.Name = "SlotStroke"

	local slotGrad = Instance.new("UIGradient")
	slotGrad.Name = "SlotGloss"
	slotGrad.Rotation = -40
	slotGrad.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0.0, Color3.fromRGB(255, 255, 255)),
		ColorSequenceKeypoint.new(0.5, Color3.fromRGB(240, 242, 248)),
		ColorSequenceKeypoint.new(1.0, Color3.fromRGB(192, 198, 218)),
	})
	slotGrad.Parent = slot

	local aspect = Instance.new("UIAspectRatioConstraint")
	aspect.AspectRatio = 1
	aspect.Parent = slot
	UIKit.EnsureMinTouchTarget(slot, 52)

	local icon = UIKit.CreateBadgeIcon(slot, item.Sprite, item.Glyph, item.Accent, 28)
	icon.Position = UDim2.fromScale(0.5, 0.52)
	icon.AnchorPoint = Vector2.new(0.5, 0.5)

	local keyPill = Instance.new("TextLabel")
	keyPill.Name = "KeybindPill"
	keyPill.Size = UDim2.fromOffset(18, 16)
	keyPill.Position = UDim2.fromOffset(4, 3)
	keyPill.BackgroundColor3 = UIKit.Tokens.Colors.BgDeep
	keyPill.Text = tostring(slotIdx)
	keyPill.TextColor3 = UIKit.Tokens.Colors.TextSecondary
	keyPill.TextSize = 11
	keyPill.FontFace = UIKit.Tokens.Fonts.Mono
	keyPill.BorderSizePixel = 0
	keyPill.Parent = slot
	keyPill:AddTag("KeybindPill")
	makeCorner(keyPill, UIKit.Tokens.Radii.Xs)
end

-- =========================================================================
-- LAYER 20: TopbarWidgetsGui (TopbarSafeInsets)
-- =========================================================================
local topbarWidgetsGui = makeLayer("TopbarWidgetsGui", 20, Enum.ScreenInsets.TopbarSafeInsets, true)
local topbarPill = UIKit.CreatePanel({
	Name = "TopbarStatusPill",
	Parent = topbarWidgetsGui,
	Size = UDim2.fromOffset(138, 32),
	Position = UDim2.new(0.5, 0, 0, 10),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundTransparency = 0.25,
	CornerRadius = UIKit.Tokens.Radii.Pill,
})
makeLabel(
	topbarPill,
	"StatusText",
	"LIVE  |  v1.0",
	UDim2.fromScale(1, 1),
	UDim2.new(),
	12,
	UIKit.Tokens.Fonts.Mono,
	UIKit.Tokens.Colors.TextSecondary,
	Enum.TextXAlignment.Center
)

-- =========================================================================
-- LAYER 30: ContextualPromptGui (CoreUISafeInsets)
-- =========================================================================
local contextualPromptGui = makeLayer("ContextualPromptGui", 30, Enum.ScreenInsets.CoreUISafeInsets, true)
local npcPromptBtn = UIKit.CreateButton({
	Name = "TalkNpcPromptBtn",
	Parent = contextualPromptGui,
	Text = "[E] Quartermaster",
	Size = UDim2.fromOffset(172, 52),
	Position = UDim2.new(0.5, 0, 1, -80),
	AnchorPoint = Vector2.new(0.5, 1),
	Variant = "Secondary",
	TextSize = 14,
})

-- =========================================================================
-- LAYER 49: ModalBackdropGui (ScreenInsets = None)
-- =========================================================================
local modalBackdropGui = makeLayer("ModalBackdropGui", 49, Enum.ScreenInsets.None, false)
local scrimBtn = Instance.new("TextButton")
scrimBtn.Name = "Scrim"
scrimBtn.Size = UDim2.fromScale(1, 1)
scrimBtn.BackgroundColor3 = UIKit.Tokens.Colors.Scrim
scrimBtn.BackgroundTransparency = 0.42
scrimBtn.Text = ""
scrimBtn.AutoButtonColor = false
scrimBtn.BorderSizePixel = 0
scrimBtn.Parent = modalBackdropGui

-- =========================================================================
-- LAYER 50: ModalMenusGui (CoreUISafeInsets) - 5 Standard Modals
-- =========================================================================
local modalMenusGui = makeLayer("ModalMenusGui", 50, Enum.ScreenInsets.CoreUISafeInsets, true)
UIKit.BindResponsiveScale(modalMenusGui, 0.86, 1.05)

local function buildModalShell(modalName: string, titleText: string, accent: Color3): (GuiObject, Frame, TextButton)
	local panel = UIKit.CreatePanel({
		Name = modalName .. "Modal",
		Parent = modalMenusGui,
		Size = UDim2.fromScale(0.86, 0.86),
		Position = UDim2.fromScale(0.5, 0.5),
		AnchorPoint = Vector2.new(0.5, 0.5),
		StrokeColor = accent,
		StrokeThickness = 2,
		Use9Slice = true,
	})
	panel.Visible = false

	local bounds = Instance.new("UISizeConstraint")
	bounds.MinSize = Vector2.new(300, 260)
	bounds.MaxSize = Vector2.new(780, 500)
	bounds.Parent = panel

	makeLabel(
		panel,
		"Title",
		titleText,
		UDim2.new(1, -92, 0, 44),
		UDim2.fromOffset(22, 12),
		20,
		UIKit.Tokens.Fonts.Title,
		UIKit.Tokens.Colors.TextPrimary
	)

	local closeBtn = UIKit.CreateButton({
		Name = "CloseButton",
		Parent = panel,
		Text = "X",
		Size = UDim2.fromOffset(52, 52),
		Position = UDim2.new(1, -14, 0, 10),
		AnchorPoint = Vector2.new(1, 0),
		Variant = "Danger",
		TextSize = 18,
	}) :: TextButton

	local body = Instance.new("Frame")
	body.Name = "Body"
	body.Size = UDim2.new(1, -36, 1, -76)
	body.Position = UDim2.fromOffset(18, 64)
	body.BackgroundTransparency = 1
	body.Parent = panel

	return panel, body, closeBtn
end

-- 5A. SHOP MODAL
local shopModal, shopBody, _ = buildModalShell("Shop", "ROYAL ARMORY SHOP", UIKit.Tokens.Colors.Primary)
local shopTabsBar = Instance.new("Frame")
shopTabsBar.Name = "TabsBar"
shopTabsBar.Size = UDim2.new(1, 0, 0, 52)
shopTabsBar.BackgroundTransparency = 1
shopTabsBar.Parent = shopBody
local shopTabList = Instance.new("UIListLayout")
shopTabList.FillDirection = Enum.FillDirection.Horizontal
shopTabList.SortOrder = Enum.SortOrder.LayoutOrder
shopTabList.Padding = UDim.new(0, 8)
shopTabList.Parent = shopTabsBar

local shopTabs = { "Featured", "Gear", "Passes", "Currency" }
for idx, tabName in ipairs(shopTabs) do
	local tBtn = UIKit.CreateButton({
		Name = "Tab_" .. tabName,
		Parent = shopTabsBar,
		Text = tabName,
		Size = UDim2.fromOffset(96, 52),
		LayoutOrder = idx,
		Variant = if idx == 1 then "Primary" else "Secondary",
		TextSize = 14,
	})
	tBtn:SetAttribute("TabKey", tabName)
end

local shopScroll = Instance.new("ScrollingFrame")
shopScroll.Name = "ItemsGrid"
shopScroll.Size = UDim2.new(1, 0, 1, -60)
shopScroll.Position = UDim2.fromOffset(0, 60)
shopScroll.BackgroundTransparency = 1
shopScroll.BorderSizePixel = 0
shopScroll.ScrollBarThickness = 6
shopScroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
shopScroll.CanvasSize = UDim2.new()
shopScroll.Parent = shopBody

local shopGrid = Instance.new("UIGridLayout")
shopGrid.CellSize = UDim2.fromOffset(162, 168)
shopGrid.CellPadding = UDim2.fromOffset(10, 10)
shopGrid.SortOrder = Enum.SortOrder.LayoutOrder
shopGrid.Parent = shopScroll

local shopCatalog = {
	{ Id = "sun_blade", Name = "Sunfire Blade", Tab = "Featured", Price = 500, Rarity = "Legendary", Sprite = "combat", Glyph = "SW" },
	{ Id = "aegis_shield", Name = "Aegis Bastion", Tab = "Gear", Price = 350, Rarity = "Epic", Sprite = "combat", Glyph = "SH" },
	{ Id = "vip_pass", Name = "2x Gold Pass", Tab = "Passes", Price = 1200, Rarity = "Rare", Sprite = "chest", Glyph = "2X" },
	{ Id = "gem_bundle", Name = "Azure Crate", Tab = "Currency", Price = 250, Rarity = "Uncommon", Sprite = "gem", Glyph = "GM" },
}
for idx, item in ipairs(shopCatalog) do
	local rarityColor: Color3 = (UIKit.Tokens.Rarity :: any)[item.Rarity] or UIKit.Tokens.Colors.BorderSubtle
	local card = UIKit.CreatePanel({
		Name = "ShopCard_" .. item.Id,
		Parent = shopScroll,
		Size = UDim2.fromOffset(162, 168),
		BackgroundColor3 = UIKit.Tokens.Colors.BgCard,
		StrokeColor = rarityColor,
		StrokeThickness = 2.5,
		CornerRadius = UIKit.Tokens.Radii.Medium,
	})
	card.ClipsDescendants = true
	card.LayoutOrder = idx
	card:SetAttribute("Category", item.Tab)
	card:SetAttribute("ItemName", item.Name)
	card:SetAttribute("Price", item.Price)
	card:SetAttribute("Rarity", item.Rarity)

	local cardGrad = Instance.new("UIGradient")
	cardGrad.Name = "CardGloss"
	cardGrad.Rotation = -42
	cardGrad.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0.0, Color3.fromRGB(255, 255, 255)),
		ColorSequenceKeypoint.new(0.45, Color3.fromRGB(240, 242, 248)),
		ColorSequenceKeypoint.new(1.0, Color3.fromRGB(196, 200, 218)),
	})
	cardGrad.Parent = card

	if (item.Rarity == "Legendary" or item.Rarity == "Epic") and UIKit.Tokens.Motifs.RaysEnabled then
		UIKit.CreateSunburstRays(card, {
			Color = rarityColor,
			RayCount = math.min(10, UIKit.Tokens.Motifs.RayCount),
			Transparency = 0.78,
			RotateSpeed = 8,
			ZIndex = 1,
		})
	end

	local icon = UIKit.CreateBadgeIcon(card, item.Sprite, item.Glyph, rarityColor, 44)
	icon.Position = UDim2.new(0.5, 0, 0, 12)
	icon.AnchorPoint = Vector2.new(0.5, 0)
	icon.ZIndex = 3

	local titleLbl = makeLabel(
		card,
		"ItemTitle",
		item.Name,
		UDim2.new(1, -12, 0, 22),
		UDim2.fromOffset(6, 62),
		14,
		UIKit.Tokens.Fonts.Heading,
		UIKit.Tokens.Colors.TextPrimary,
		Enum.TextXAlignment.Center
	)
	titleLbl.ZIndex = 3
	UIKit.AttachTextStroke(titleLbl, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.18)

	UIKit.CreateBadgePill({
		Name = "RarityTag",
		Parent = card,
		Text = string.upper(item.Rarity),
		Color = rarityColor,
		Size = UDim2.fromOffset(86, 18),
		Position = UDim2.new(0.5, 0, 0, 86),
		AnchorPoint = Vector2.new(0.5, 0),
		Rotation = UIKit.Tokens.Motifs.BadgeRotation,
		TextSize = 10,
		ZIndex = 4,
	})

	local buyBtn = UIKit.CreateButton({
		Name = "BuyBtn",
		Parent = card,
		Text = string.format("%d G", item.Price),
		Size = UDim2.new(1, -16, 0, 52),
		Position = UDim2.new(0.5, 0, 1, -8),
		AnchorPoint = Vector2.new(0.5, 1),
		Variant = "Success",
		Use9Slice = true,
	})
	buyBtn.ZIndex = 3
end

-- 5B. INVENTORY MODAL (Tabs + Search + Grid + 3D ViewportFrame Inspector)
local invModal, invBody, _ = buildModalShell("Inventory", "INVENTORY & LOADOUT", UIKit.Tokens.Colors.Warning)
local invTopBar = Instance.new("Frame")
invTopBar.Name = "TopBar"
invTopBar.Size = UDim2.new(1, 0, 0, 52)
invTopBar.BackgroundTransparency = 1
invTopBar.Parent = invBody
local invTopLayout = Instance.new("UIListLayout")
invTopLayout.FillDirection = Enum.FillDirection.Horizontal
invTopLayout.SortOrder = Enum.SortOrder.LayoutOrder
invTopLayout.Padding = UDim.new(0, 8)
invTopLayout.Parent = invTopBar

for idx, tabName in ipairs({ "All", "Weapons", "Relics" }) do
	local tBtn = UIKit.CreateButton({
		Name = "InvTab_" .. tabName,
		Parent = invTopBar,
		Text = tabName,
		Size = UDim2.fromOffset(78, 52),
		LayoutOrder = idx,
		Variant = if idx == 1 then "Primary" else "Secondary",
		TextSize = 13,
	})
	tBtn:SetAttribute("TabKey", tabName)
end

local searchBox = Instance.new("TextBox")
searchBox.Name = "SearchBox"
searchBox.Size = UDim2.new(0, 156, 0, 52)
searchBox.LayoutOrder = 10
searchBox.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
searchBox.Text = ""
searchBox.PlaceholderText = "Search gear..."
searchBox.PlaceholderColor3 = UIKit.Tokens.Colors.TextMuted
searchBox.TextColor3 = UIKit.Tokens.Colors.TextPrimary
searchBox.TextSize = 14
searchBox.FontFace = UIKit.Tokens.Fonts.Body
searchBox.ClearTextOnFocus = false
searchBox.BorderSizePixel = 0
searchBox.Parent = invTopBar
makeCorner(searchBox, UIKit.Tokens.Radii.Small)
makeStroke(searchBox, UIKit.Tokens.Colors.BorderSubtle, 1.2)
UIKit.EnsureMinTouchTarget(searchBox, 52)

local invContent = Instance.new("Frame")
invContent.Name = "SplitContent"
invContent.Size = UDim2.new(1, 0, 1, -60)
invContent.Position = UDim2.fromOffset(0, 60)
invContent.BackgroundTransparency = 1
invContent.Parent = invBody

local invGridScroll = Instance.new("ScrollingFrame")
invGridScroll.Name = "ItemGrid"
invGridScroll.Size = UDim2.new(0.58, -6, 1, 0)
invGridScroll.BackgroundTransparency = 1
invGridScroll.BorderSizePixel = 0
invGridScroll.ScrollBarThickness = 5
invGridScroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
invGridScroll.CanvasSize = UDim2.new()
invGridScroll.Parent = invContent

local invGrid = Instance.new("UIGridLayout")
invGrid.CellSize = UDim2.fromOffset(92, 92)
invGrid.CellPadding = UDim2.fromOffset(8, 8)
invGrid.SortOrder = Enum.SortOrder.LayoutOrder
invGrid.Parent = invGridScroll

local invItems = {
	{ Id = "Sword", Name = "Sunfire Blade", Cat = "Weapons", ModelName = "GoldenSword", Stats = "+48 ATK  |  Crit +12%", Rarity = "Legendary", Sprite = "combat", Glyph = "SW" },
	{ Id = "Shield", Name = "Royal Aegis", Cat = "Weapons", ModelName = "RoyalShield", Stats = "+65 DEF  |  Block +20%", Rarity = "Epic", Sprite = "combat", Glyph = "SH" },
	{ Id = "Relic", Name = "Azure Shard", Cat = "Relics", ModelName = "CrystalRelic", Stats = "+25% XP Gain", Rarity = "Rare", Sprite = "gem", Glyph = "RL" },
}
for idx, it in ipairs(invItems) do
	local slotBtn = UIKit.CreateButton({
		Name = "InvSlot_" .. it.Id,
		Parent = invGridScroll,
		Text = it.Glyph,
		Size = UDim2.fromOffset(92, 92),
		LayoutOrder = idx,
		Variant = "Secondary",
		TextSize = 18,
	})
	slotBtn:SetAttribute("Category", it.Cat)
	slotBtn:SetAttribute("ItemName", it.Name)
	slotBtn:SetAttribute("ModelName", it.ModelName)
	slotBtn:SetAttribute("Stats", it.Stats)
	slotBtn:SetAttribute("Rarity", it.Rarity)
end

local inspector = UIKit.CreatePanel({
	Name = "Inspector",
	Parent = invContent,
	Size = UDim2.new(0.42, -6, 1, 0),
	Position = UDim2.new(0.58, 6, 0, 0),
	AnchorPoint = Vector2.zero,
	BackgroundColor3 = UIKit.Tokens.Colors.BgCard,
})
local inspPad = Instance.new("UIPadding")
inspPad.PaddingTop = UDim.new(0, 8)
inspPad.PaddingBottom = UDim.new(0, 8)
inspPad.PaddingLeft = UDim.new(0, 8)
inspPad.PaddingRight = UDim.new(0, 8)
inspPad.Parent = inspector

local inspList = Instance.new("UIListLayout")
inspList.FillDirection = Enum.FillDirection.Vertical
inspList.SortOrder = Enum.SortOrder.LayoutOrder
inspList.Padding = UDim.new(0, 6)
inspList.Parent = inspector

local vpHolder = Instance.new("Frame")
vpHolder.Name = "ViewportHolder"
vpHolder.Size = UDim2.new(1, 0, 0.45, 0)
vpHolder.LayoutOrder = 1
vpHolder.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
vpHolder.BorderSizePixel = 0
vpHolder.Parent = inspector
makeCorner(vpHolder, UIKit.Tokens.Radii.Small)

local vpFlex = Instance.new("UIFlexItem")
vpFlex.FlexMode = Enum.UIFlexMode.Fill
vpFlex.Parent = vpHolder

local invViewport = UIKit.CreateViewportPreview(vpHolder, { AutoSpin = true })
invViewport:SetModel(swordModel)

local inspName = makeLabel(
	inspector,
	"InspectorTitle",
	"Sunfire Blade",
	UDim2.new(1, 0, 0, 22),
	UDim2.new(),
	16,
	UIKit.Tokens.Fonts.Title,
	UIKit.Tokens.Colors.Gold
)
inspName.LayoutOrder = 2
inspName.TextTruncate = Enum.TextTruncate.AtEnd

local inspStats = makeLabel(
	inspector,
	"InspectorStats",
	"+48 ATK  |  Crit +12%",
	UDim2.new(1, 0, 0, 20),
	UDim2.new(),
	12,
	UIKit.Tokens.Fonts.Body,
	UIKit.Tokens.Colors.TextSecondary
)
inspStats.LayoutOrder = 3
inspStats.TextTruncate = Enum.TextTruncate.AtEnd

UIKit.CreateButton({
	Name = "EquipBtn",
	Parent = inspector,
	Text = "EQUIP",
	Size = UDim2.new(1, 0, 0, 52),
	LayoutOrder = 4,
	Variant = "Primary",
})

-- 5C. QUESTS MODAL
local questsModal, questsBody, _ = buildModalShell("Quests", "QUESTS & ACHIEVEMENTS", UIKit.Tokens.Colors.Success)
local questScroll = Instance.new("ScrollingFrame")
questScroll.Name = "QuestList"
questScroll.Size = UDim2.fromScale(1, 1)
questScroll.BackgroundTransparency = 1
questScroll.BorderSizePixel = 0
questScroll.ScrollBarThickness = 6
questScroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
questScroll.CanvasSize = UDim2.new()
questScroll.Parent = questsBody
local qList = Instance.new("UIListLayout")
qList.FillDirection = Enum.FillDirection.Vertical
qList.SortOrder = Enum.SortOrder.LayoutOrder
qList.Padding = UDim.new(0, 10)
qList.Parent = questScroll

local questDefs = {
	{ Id = "daily_slay", Title = "Daily: Defeat 5 Sentinel Golems", Reward = 250, Progress = 1.0, StatusText = "5 / 5 Ready!" },
	{ Id = "weekly_chest", Title = "Weekly: Open 10 Armory Chests", Reward = 600, Progress = 0.7, StatusText = "7 / 10" },
}
for idx, q in ipairs(questDefs) do
	local row = UIKit.CreatePanel({
		Name = "QuestRow_" .. q.Id,
		Parent = questScroll,
		Size = UDim2.new(1, -8, 0, 74),
		Position = UDim2.new(),
		AnchorPoint = Vector2.zero,
		BackgroundColor3 = UIKit.Tokens.Colors.BgCard,
	})
	row.LayoutOrder = idx
	row:SetAttribute("RewardCoins", q.Reward)
	row:SetAttribute("Claimable", q.Progress >= 1.0)
	row:SetAttribute("Claimed", false)

	makeLabel(row, "Title", q.Title, UDim2.new(1, -140, 0, 22), UDim2.fromOffset(12, 8), 14, UIKit.Tokens.Fonts.Heading)
	makeLabel(row, "Reward", string.format("Reward: +%d Coins  (%s)", q.Reward, q.StatusText), UDim2.new(1, -140, 0, 18), UDim2.fromOffset(12, 30), 12, UIKit.Tokens.Fonts.Body, UIKit.Tokens.Colors.Gold)

	local pTrack = Instance.new("Frame")
	pTrack.Size = UDim2.new(1, -150, 0, 8)
	pTrack.Position = UDim2.fromOffset(12, 54)
	pTrack.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
	pTrack.BorderSizePixel = 0
	pTrack.Parent = row
	makeCorner(pTrack, UIKit.Tokens.Radii.Pill)
	makeStroke(pTrack, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.2)

	local pFill = Instance.new("Frame")
	pFill.Size = UDim2.fromScale(q.Progress, 1)
	pFill.BackgroundColor3 = UIKit.Tokens.Colors.Success
	pFill.BorderSizePixel = 0
	pFill.Parent = pTrack
	UIKit.ApplyGlossySurface(pFill, {
		GradientKey = "Success",
		CornerRadius = UIKit.Tokens.Radii.Pill,
		StrokeColor = UIKit.Tokens.Colors.OutlineInk,
		StrokeThickness = 1.0,
		InnerHighlight = false,
	})

	UIKit.CreateButton({
		Name = "ClaimBtn",
		Parent = row,
		Text = if q.Progress >= 1.0 then "CLAIM" else "IN PROG",
		Size = UDim2.fromOffset(116, 52),
		Position = UDim2.new(1, -10, 0.5, 0),
		AnchorPoint = Vector2.new(1, 0.5),
		Variant = if q.Progress >= 1.0 then "Success" else "Secondary",
	})
end

-- 5D. INDEX / CODES MODAL
local indexModal, indexBody, _ = buildModalShell("IndexCodes", "INDEX & REDEEM CODES", UIKit.Tokens.Colors.Accent)
local codeRow = Instance.new("Frame")
codeRow.Name = "CodeRedeemBar"
codeRow.Size = UDim2.new(1, 0, 0, 56)
codeRow.BackgroundTransparency = 1
codeRow.Parent = indexBody

local codeBox = Instance.new("TextBox")
codeBox.Name = "CodeInput"
codeBox.Size = UDim2.new(1, -140, 0, 52)
codeBox.Position = UDim2.fromOffset(0, 2)
codeBox.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
codeBox.Text = ""
codeBox.PlaceholderText = "Enter code (e.g. LAUNCH2026)"
codeBox.PlaceholderColor3 = UIKit.Tokens.Colors.TextMuted
codeBox.TextColor3 = UIKit.Tokens.Colors.TextPrimary
codeBox.TextSize = 15
codeBox.FontFace = UIKit.Tokens.Fonts.Mono
codeBox.ClearTextOnFocus = false
codeBox.BorderSizePixel = 0
codeBox.Parent = codeRow
makeCorner(codeBox, UIKit.Tokens.Radii.Small)
makeStroke(codeBox, UIKit.Tokens.Colors.BorderSubtle, 1.4)
UIKit.EnsureMinTouchTarget(codeBox, 52)

UIKit.CreateButton({
	Name = "RedeemBtn",
	Parent = codeRow,
	Text = "REDEEM",
	Size = UDim2.fromOffset(128, 52),
	Position = UDim2.new(1, 0, 0, 2),
	AnchorPoint = Vector2.new(1, 0),
	Variant = "Primary",
})

local indexGrid = Instance.new("Frame")
indexGrid.Name = "DiscoveryGrid"
indexGrid.Size = UDim2.new(1, 0, 1, -68)
indexGrid.Position = UDim2.fromOffset(0, 68)
indexGrid.BackgroundTransparency = 1
indexGrid.Parent = indexBody
local idxGridLayout = Instance.new("UIGridLayout")
idxGridLayout.CellSize = UDim2.fromOffset(118, 108)
idxGridLayout.CellPadding = UDim2.fromOffset(10, 10)
idxGridLayout.Parent = indexGrid

for idx, entry in ipairs({
	{ Name = "Gold Coin", Unlocked = true, Sprite = "coin", Glyph = "$" },
	{ Name = "Azure Gem", Unlocked = true, Sprite = "gem", Glyph = "*" },
	{ Name = "Mystery Chest", Unlocked = false, Sprite = "chest", Glyph = "?" },
}) do
	local card = UIKit.CreatePanel({
		Name = "Idx_" .. tostring(idx),
		Parent = indexGrid,
		Size = UDim2.fromOffset(118, 108),
		BackgroundColor3 = UIKit.Tokens.Colors.BgCard,
	})
	local icon = UIKit.CreateBadgeIcon(
		card,
		entry.Sprite,
		entry.Glyph,
		if entry.Unlocked then UIKit.Tokens.Colors.Gold else Color3.fromRGB(16, 18, 24),
		42
	)
	icon.Position = UDim2.new(0.5, 0, 0, 16)
	icon.AnchorPoint = Vector2.new(0.5, 0)
	if not entry.Unlocked and icon:IsA("ImageLabel") then
		icon.ImageColor3 = Color3.new(0, 0, 0)
	end
	makeLabel(
		card,
		"Name",
		if entry.Unlocked then entry.Name else "???",
		UDim2.new(1, -10, 0, 24),
		UDim2.new(0, 5, 1, -30),
		12,
		UIKit.Tokens.Fonts.Heading,
		if entry.Unlocked then UIKit.Tokens.Colors.TextPrimary else UIKit.Tokens.Colors.TextMuted,
		Enum.TextXAlignment.Center
	)
end

-- 5E. SETTINGS MODAL (UIDragDetector Sliders + Toggles)
local settingsModal, settingsBody, _ = buildModalShell("Settings", "GAME SETTINGS", UIKit.Tokens.Colors.Secondary)
local settingsScroll = Instance.new("ScrollingFrame")
settingsScroll.Name = "SettingsList"
settingsScroll.Size = UDim2.fromScale(1, 1)
settingsScroll.BackgroundTransparency = 1
settingsScroll.BorderSizePixel = 0
settingsScroll.ScrollBarThickness = 6
settingsScroll.AutomaticCanvasSize = Enum.AutomaticSize.Y
settingsScroll.CanvasSize = UDim2.new()
settingsScroll.Parent = settingsBody
local sLayout = Instance.new("UIListLayout")
sLayout.FillDirection = Enum.FillDirection.Vertical
sLayout.SortOrder = Enum.SortOrder.LayoutOrder
sLayout.Padding = UDim.new(0, 8)
sLayout.Parent = settingsScroll

local masterSlider = UIKit.CreateSlider({ Name = "MasterVol", Parent = settingsScroll, Label = "Master Audio", InitialValue = 80 })
masterSlider.Root.LayoutOrder = 1
local sfxSlider = UIKit.CreateSlider({ Name = "SfxVol", Parent = settingsScroll, Label = "SFX Volume", InitialValue = 70, AccentColor = UIKit.Tokens.Colors.Success })
sfxSlider.Root.LayoutOrder = 2
local shadowsToggle = UIKit.CreateToggle(settingsScroll, "ShadowsToggle", "Dynamic Shadows", true)
shadowsToggle.Root.LayoutOrder = 3
local particlesToggle = UIKit.CreateToggle(settingsScroll, "ParticlesToggle", "High Detail FX", true)
particlesToggle.Root.LayoutOrder = 4

-- Apply EditPreviewModal visibility if configured
if CONFIG.EditPreviewModal ~= "None" then
	local previewTarget = modalMenusGui:FindFirstChild(CONFIG.EditPreviewModal .. "Modal")
	if previewTarget and previewTarget:IsA("GuiObject") then
		previewTarget.Visible = true
		modalBackdropGui.Enabled = true
	end
end

-- =========================================================================
-- LAYER 65: NpcDialogGui (ViewportFrame 3D Bust + MaxVisibleGraphemes)
-- =========================================================================
local npcDialogGui = makeLayer("NpcDialogGui", 65, Enum.ScreenInsets.CoreUISafeInsets, false)
UIKit.BindResponsiveScale(npcDialogGui, 0.86, 1.05)

local npcCard = UIKit.CreatePanel({
	Name = "NpcDialogCard",
	Parent = npcDialogGui,
	Size = UDim2.new(0.84, 0, 0, 178),
	Position = UDim2.new(0.5, 0, 1, -16),
	AnchorPoint = Vector2.new(0.5, 1),
	StrokeColor = UIKit.Tokens.Colors.Gold,
	StrokeThickness = 2,
})
local npcBounds = Instance.new("UISizeConstraint")
npcBounds.MinSize = Vector2.new(300, 150)
npcBounds.MaxSize = Vector2.new(720, 210)
npcBounds.Parent = npcCard

local bustFrame = Instance.new("Frame")
bustFrame.Name = "BustFrame"
bustFrame.Size = UDim2.fromOffset(124, 146)
bustFrame.Position = UDim2.fromOffset(14, 16)
bustFrame.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
bustFrame.BorderSizePixel = 0
bustFrame.Parent = npcCard
makeCorner(bustFrame, UIKit.Tokens.Radii.Small)
makeStroke(bustFrame, UIKit.Tokens.Colors.Gold, 1.4)
local npcVp = UIKit.CreateViewportPreview(bustFrame, { AutoSpin = false })
npcVp:SetModel(npcBustModel)

makeLabel(npcCard, "SpeakerName", "GUILD QUARTERMASTER", UDim2.new(1, -160, 0, 24), UDim2.fromOffset(152, 12), 14, UIKit.Tokens.Fonts.Title, UIKit.Tokens.Colors.Gold)
local dialogText = makeLabel(
	npcCard,
	"DialogText",
	"Welcome, traveler! Ready to upgrade your gear or claim <b>daily rewards</b>?",
	UDim2.new(1, -166, 0, 62),
	UDim2.fromOffset(152, 38),
	14,
	UIKit.Tokens.Fonts.Body,
	UIKit.Tokens.Colors.TextPrimary
)
dialogText.RichText = true
dialogText.TextWrapped = true
dialogText.TextYAlignment = Enum.TextYAlignment.Top

local choiceBar = Instance.new("Frame")
choiceBar.Name = "ChoiceBar"
choiceBar.Size = UDim2.new(1, -166, 0, 54)
choiceBar.Position = UDim2.new(0, 152, 1, -10)
choiceBar.AnchorPoint = Vector2.new(0, 1)
choiceBar.BackgroundTransparency = 1
choiceBar.Parent = npcCard
local chLayout = Instance.new("UIListLayout")
chLayout.FillDirection = Enum.FillDirection.Horizontal
chLayout.SortOrder = Enum.SortOrder.LayoutOrder
chLayout.Padding = UDim.new(0, 8)
chLayout.Parent = choiceBar

UIKit.CreateButton({ Name = "OpenShopChoice", Parent = choiceBar, Text = "Shop", Size = UDim2.fromOffset(108, 52), LayoutOrder = 1, Variant = "Primary" })
UIKit.CreateButton({ Name = "OpenQuestsChoice", Parent = choiceBar, Text = "Quests", Size = UDim2.fromOffset(108, 52), LayoutOrder = 2, Variant = "Success" })
UIKit.CreateButton({ Name = "CloseNpcChoice", Parent = choiceBar, Text = "Bye", Size = UDim2.fromOffset(92, 52), LayoutOrder = 3, Variant = "Secondary" })

-- =========================================================================
-- LAYER 80: ConfirmDialogGui (CoreUISafeInsets)
-- =========================================================================
local confirmDialogGui = makeLayer("ConfirmDialogGui", 80, Enum.ScreenInsets.CoreUISafeInsets, false)
UIKit.BindResponsiveScale(confirmDialogGui, 0.86, 1.05)

local confirmCard = UIKit.CreatePanel({
	Name = "ConfirmCard",
	Parent = confirmDialogGui,
	Size = UDim2.fromOffset(360, 198),
	Position = UDim2.fromScale(0.5, 0.5),
	AnchorPoint = Vector2.new(0.5, 0.5),
	StrokeColor = UIKit.Tokens.Colors.Warning,
	StrokeThickness = 2,
})
confirmCard.SelectionGroup = true
confirmCard.SelectionBehaviorUp = Enum.SelectionBehavior.Stop
confirmCard.SelectionBehaviorDown = Enum.SelectionBehavior.Stop
confirmCard.SelectionBehaviorLeft = Enum.SelectionBehavior.Stop
confirmCard.SelectionBehaviorRight = Enum.SelectionBehavior.Stop

makeLabel(confirmCard, "Title", "CONFIRM PURCHASE", UDim2.new(1, -24, 0, 28), UDim2.fromOffset(14, 14), 18, UIKit.Tokens.Fonts.Title, UIKit.Tokens.Colors.TextPrimary, Enum.TextXAlignment.Center)
local confirmMsg = makeLabel(confirmCard, "Message", "Spend 500 Coins on Sunfire Blade?", UDim2.new(1, -28, 0, 62), UDim2.fromOffset(14, 50), 14, UIKit.Tokens.Fonts.Body, UIKit.Tokens.Colors.TextSecondary, Enum.TextXAlignment.Center)
confirmMsg.TextWrapped = true

local confirmRow = Instance.new("Frame")
confirmRow.Name = "Buttons"
confirmRow.Size = UDim2.new(1, -28, 0, 56)
confirmRow.Position = UDim2.new(0, 14, 1, -14)
confirmRow.AnchorPoint = Vector2.new(0, 1)
confirmRow.BackgroundTransparency = 1
confirmRow.Parent = confirmCard
local cfLayout = Instance.new("UIListLayout")
cfLayout.FillDirection = Enum.FillDirection.Horizontal
cfLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
cfLayout.SortOrder = Enum.SortOrder.LayoutOrder
cfLayout.Padding = UDim.new(0, 12)
cfLayout.Parent = confirmRow

UIKit.CreateButton({ Name = "CancelBtn", Parent = confirmRow, Text = "Cancel", Size = UDim2.fromOffset(142, 52), LayoutOrder = 1, Variant = "Secondary" })
UIKit.CreateButton({ Name = "ConfirmBtn", Parent = confirmRow, Text = "Confirm", Size = UDim2.fromOffset(142, 52), LayoutOrder = 2, Variant = "Success" })

-- =========================================================================
-- LAYER 90 & 100: FloatingTooltipGui & ToastNotificationGui
-- =========================================================================
local tooltipGui = makeLayer("FloatingTooltipGui", 90, Enum.ScreenInsets.CoreUISafeInsets, true)
local toastGui = makeLayer("ToastNotificationGui", 100, Enum.ScreenInsets.CoreUISafeInsets, true)

-- =========================================================================
-- LAYER 1000: ReplicatedFirst LoadingTransitionTemplate (CanvasGroup fade demo)
-- =========================================================================
local prevLoad = ReplicatedStorage:FindFirstChild("LoadingTransitionTemplate")
if prevLoad then
	prevLoad:Destroy()
end
local loadingGui = Instance.new("ScreenGui")
loadingGui.Name = "LoadingTransitionTemplate"
loadingGui.DisplayOrder = 1000
loadingGui.ScreenInsets = Enum.ScreenInsets.None
loadingGui.ResetOnSpawn = false
loadingGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
loadingGui.Enabled = false
loadingGui.Parent = ReplicatedStorage

local loadGroup = Instance.new("CanvasGroup")
loadGroup.Name = "SplashGroup"
loadGroup.Size = UDim2.fromScale(1, 1)
loadGroup.BackgroundColor3 = UIKit.Tokens.Colors.BgDeep
loadGroup.BorderSizePixel = 0
loadGroup.Parent = loadingGui
makeLabel(loadGroup, "Title", "LOADING REALM...", UDim2.new(1, -40, 0, 36), UDim2.new(0.5, 0, 0.45, 0), 26, UIKit.Tokens.Fonts.Title, UIKit.Tokens.Colors.TextPrimary, Enum.TextXAlignment.Center).AnchorPoint = Vector2.new(0.5, 0.5)

-- =========================================================================
-- RUNTIME CLIENT CONTROLLER (StarterPlayerScripts.StandardGuiController)
-- =========================================================================
local sps = StarterPlayer:WaitForChild("StarterPlayerScripts")
local prevCtrl = sps:FindFirstChild("StandardGuiController")
if prevCtrl then
	prevCtrl:Destroy()
end

local clientCtrl = Instance.new("LocalScript")
clientCtrl.Name = "StandardGuiController"
clientCtrl.Source = [===[--!strict
local GuiService = game:GetService("GuiService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UserInputService = game:GetService("UserInputService")

local modInst = ReplicatedStorage:FindFirstChild("UIThemeAndComponents")
	or (ReplicatedStorage:FindFirstChild("Modules") and ReplicatedStorage.Modules:FindFirstChild("UIThemeAndComponents"))
assert(modInst and modInst:IsA("ModuleScript"), "Missing UIThemeAndComponents")
local UIKit = require(modInst) :: any

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui") :: PlayerGui

pcall(function()
	StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.Health, false)
	StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.Backpack, false)
end)

local mainHudGui = playerGui:WaitForChild("MainHudGui") :: ScreenGui
local contextualGui = playerGui:WaitForChild("ContextualPromptGui") :: ScreenGui
local backdropGui = playerGui:WaitForChild("ModalBackdropGui") :: ScreenGui
local modalMenusGui = playerGui:WaitForChild("ModalMenusGui") :: ScreenGui
local npcDialogGui = playerGui:WaitForChild("NpcDialogGui") :: ScreenGui
local confirmDialogGui = playerGui:WaitForChild("ConfirmDialogGui") :: ScreenGui
local tooltipGui = playerGui:WaitForChild("FloatingTooltipGui") :: ScreenGui
local toastGui = playerGui:WaitForChild("ToastNotificationGui") :: ScreenGui

-- Clear Edit-mode preview modal cleanly on live client boot
for _, ch in ipairs(modalMenusGui:GetChildren()) do
	if ch:IsA("GuiObject") then
		ch.Visible = false
	end
end
backdropGui.Enabled = false
npcDialogGui.Enabled = false
confirmDialogGui.Enabled = false

local state = {
	coins = 12450,
	gems = 320,
	selectedSlot = 1,
	redeemedCodes = {} :: { [string]: boolean },
	settings = {
		masterVol = 80,
		sfxVol = 70,
		shadows = true,
		particles = true,
	},
}

local currencyBar = mainHudGui:WaitForChild("CurrencyBar") :: GuiObject
local coinsLabel = currencyBar:WaitForChild("CoinsLabel") :: TextLabel
local gemsLabel = currencyBar:WaitForChild("GemsLabel") :: TextLabel
local function updateCurrencyUI()
	coinsLabel.Text = UIKit.FormatNumber(state.coins)
	gemsLabel.Text = UIKit.FormatNumber(state.gems)
end

local modalManager = UIKit.CreateModalManager(modalMenusGui, backdropGui)
local tooltip = UIKit.CreateTooltipController(tooltipGui)
local toasts = UIKit.CreateToastQueue(toastGui, 3)

local modalNames = { "Shop", "Inventory", "Quests", "IndexCodes", "Settings" }
for _, mName in ipairs(modalNames) do
	local mFrame = modalMenusGui:FindFirstChild(mName .. "Modal")
	if mFrame and mFrame:IsA("GuiObject") then
		local closeBtn = mFrame:FindFirstChild("CloseButton")
		modalManager:Register(mName, mFrame, if closeBtn and closeBtn:IsA("GuiObject") then closeBtn else nil)
		if closeBtn and closeBtn:IsA("GuiButton") then
			UIKit.AttachButtonJuice(closeBtn, closeBtn, function()
				modalManager:CloseAll()
			end)
		end
	end
end

-- SideRail & ObjectiveTracker refs (desktop vs compact phone reflow is handled declaratively by ThemeSheet @CompactPhone >> rules)
local sideRail = mainHudGui:WaitForChild("SideRail") :: Frame
local objectiveCard = mainHudGui:WaitForChild("ObjectiveTracker") :: GuiObject

-- Wire SideRail & Currency +
for _, mName in ipairs(modalNames) do
	local btn = sideRail:FindFirstChild(mName .. "Btn")
	if btn and btn:IsA("GuiButton") then
		UIKit.AttachButtonJuice(btn, btn, function()
			modalManager:Open(mName)
		end)
		tooltip:BindHover(btn, function()
			return { title = mName, subtitle = "Menu", body = "Open " .. mName .. " window" }
		end)
	end
end

local addCurrencyBtn = currencyBar:FindFirstChild("AddCurrencyBtn")
if addCurrencyBtn and addCurrencyBtn:IsA("GuiButton") then
	UIKit.AttachButtonJuice(addCurrencyBtn, addCurrencyBtn, function()
		modalManager:Open("Shop")
	end)
end

-- Objective Tracker collapse toggle
local collapseBtn = objectiveCard:FindFirstChild("CollapseObjectiveBtn")
local objBody = objectiveCard:FindFirstChild("QuestBody") :: GuiObject?
local objCollapsed = false
if collapseBtn and collapseBtn:IsA("TextButton") and objBody then
	UIKit.AttachButtonJuice(collapseBtn, collapseBtn, function()
		objCollapsed = not objCollapsed
		objBody.Visible = not objCollapsed
		objectiveCard.Size = if objCollapsed then UDim2.fromOffset(250, 56) else UDim2.fromOffset(250, 86)
		collapseBtn.Text = if objCollapsed then "+" else "-"
	end)
end

-- Hotbar slot selection
local hotbar = mainHudGui:WaitForChild("ActionHotbar") :: Frame
local function selectHotbar(slotIndex: number)
	state.selectedSlot = math.clamp(slotIndex, 1, 5)
	for i = 1, 5 do
		local slot = hotbar:FindFirstChild("Slot" .. tostring(i))
		if slot then
			local st = slot:FindFirstChild("SlotStroke")
			if st and st:IsA("UIStroke") then
				st.Color = if i == state.selectedSlot then UIKit.Tokens.Colors.Gold else UIKit.Tokens.Colors.BorderSubtle
				st.Thickness = if i == state.selectedSlot then 2.4 else 1.4
			end
		end
	end
end
for i = 1, 5 do
	local slot = hotbar:FindFirstChild("Slot" .. tostring(i))
	if slot and slot:IsA("GuiButton") then
		UIKit.AttachButtonJuice(slot, slot, function()
			selectHotbar(i)
		end)
		tooltip:BindHover(slot, function()
			return { title = "Action Slot " .. tostring(i), subtitle = "Hotbar", body = "Press [" .. tostring(i) .. "] or tap to activate." }
		end)
	end
end

-- ConfirmDialog controller
local confirmCard = confirmDialogGui:WaitForChild("ConfirmCard") :: GuiObject
local confirmMsg = confirmCard:WaitForChild("Message") :: TextLabel
local confirmButtons = confirmCard:WaitForChild("Buttons") :: Frame
local confirmBtn = confirmButtons:WaitForChild("ConfirmBtn") :: GuiButton
local cancelBtn = confirmButtons:WaitForChild("CancelBtn") :: GuiButton
local pendingConfirmFn: (() -> ())? = nil

local function openConfirm(msgText: string, onAccept: () -> ())
	confirmMsg.Text = msgText
	pendingConfirmFn = onAccept
	confirmDialogGui.Enabled = true
	if UIKit.GetPreferredInput() == Enum.PreferredInput.Gamepad then
		pcall(function()
			GuiService:Select(confirmBtn)
		end)
	end
end
UIKit.AttachButtonJuice(cancelBtn, cancelBtn, function()
	pendingConfirmFn = nil
	confirmDialogGui.Enabled = false
end)
UIKit.AttachButtonJuice(confirmBtn, confirmBtn, function()
	local fn = pendingConfirmFn
	pendingConfirmFn = nil
	confirmDialogGui.Enabled = false
	if fn then
		fn()
	end
end)

-- Shared tab-bar tag switcher (swaps ButtonPrimary/ButtonSecondary so StyleRule :Hover/:Press stays intact)
local function setActiveTab(tabsContainer: Instance, activeKey: string)
	for _, btn in ipairs(tabsContainer:GetChildren()) do
		if btn:IsA("TextButton") then
			local isMatch = btn:GetAttribute("TabKey") == activeKey
			if isMatch then
				btn:RemoveTag("ButtonSecondary")
				btn:AddTag("ButtonPrimary")
			else
				btn:RemoveTag("ButtonPrimary")
				btn:AddTag("ButtonSecondary")
			end
		end
	end
end

-- Shop wiring (Tabs + Buy -> Confirm -> Toast)
local shopModal = modalMenusGui:WaitForChild("ShopModal") :: GuiObject
local shopBody = shopModal:WaitForChild("Body") :: Frame
local shopTabsBar = shopBody:WaitForChild("TabsBar") :: Frame
local shopGrid = shopBody:WaitForChild("ItemsGrid") :: ScrollingFrame
local function filterShopTab(tabKey: string)
	setActiveTab(shopTabsBar, tabKey)
	for _, card in ipairs(shopGrid:GetChildren()) do
		if card:IsA("GuiObject") then
			card.Visible = (tabKey == "Featured") or (card:GetAttribute("Category") == tabKey)
		end
	end
end
for _, btn in ipairs(shopTabsBar:GetChildren()) do
	if btn:IsA("GuiButton") then
		UIKit.AttachButtonJuice(btn, btn, function()
			filterShopTab(tostring(btn:GetAttribute("TabKey") or "Featured"))
		end)
	end
end
for _, card in ipairs(shopGrid:GetChildren()) do
	if card:IsA("GuiObject") then
		local buyBtn = card:FindFirstChild("BuyBtn")
		if buyBtn and buyBtn:IsA("GuiButton") then
			UIKit.AttachButtonJuice(buyBtn, buyBtn, function()
				local itemName = tostring(card:GetAttribute("ItemName") or "Item")
				local price = tonumber(card:GetAttribute("Price")) or 100
				openConfirm(string.format("Spend %s Coins on %s?", UIKit.FormatNumber(price), itemName), function()
					if state.coins >= price then
						state.coins -= price
						updateCurrencyUI()
						toasts:Push({ title = "Purchased!", message = itemName .. " added to Inventory.", kind = "Reward" })
					else
						toasts:Push({ title = "Insufficient Coins", message = "Need " .. UIKit.FormatNumber(price) .. " Coins.", kind = "Error" })
					end
				end)
			end)
		end
	end
end

-- Inventory wiring (Tabs + Search + 3D ViewportFrame preview + Equip)
local invModal = modalMenusGui:WaitForChild("InventoryModal") :: GuiObject
local invBody = invModal:WaitForChild("Body") :: Frame
local invTopBar = invBody:WaitForChild("TopBar") :: Frame
local searchBox = invTopBar:WaitForChild("SearchBox") :: TextBox
local invSplit = invBody:WaitForChild("SplitContent") :: Frame
local invItemGrid = invSplit:WaitForChild("ItemGrid") :: ScrollingFrame
local inspector = invSplit:WaitForChild("Inspector") :: GuiObject
local vpHolder = inspector:WaitForChild("ViewportHolder") :: Frame
local inspTitle = inspector:WaitForChild("InspectorTitle") :: TextLabel
local inspStats = inspector:WaitForChild("InspectorStats") :: TextLabel
local equipBtn = inspector:WaitForChild("EquipBtn") :: GuiButton
local modelsFolder = ReplicatedStorage:FindFirstChild("GuiPreviewModels")

-- Replace static Edit ViewportFrame with live spinning preview
local oldVp = vpHolder:FindFirstChild("ModelViewport")
if oldVp then
	oldVp:Destroy()
end
local liveInvVp = UIKit.CreateViewportPreview(vpHolder, { AutoSpin = true })
local swordSrc = modelsFolder and modelsFolder:FindFirstChild("GoldenSword")
if swordSrc then
	liveInvVp:SetModel(swordSrc)
end

local activeInvTab = "All"
local function applyInventoryFilter()
	setActiveTab(invTopBar, activeInvTab)
	local q = string.lower(searchBox.Text)
	for _, child in ipairs(invItemGrid:GetChildren()) do
		if child:IsA("GuiObject") then
			local catOk = (activeInvTab == "All") or (child:GetAttribute("Category") == activeInvTab)
			local name = string.lower(tostring(child:GetAttribute("ItemName") or ""))
			local searchOk = (q == "") or (string.find(name, q, 1, true) ~= nil)
			child.Visible = catOk and searchOk
		end
	end
end
for _, btn in ipairs(invTopBar:GetChildren()) do
	if btn:IsA("GuiButton") then
		UIKit.AttachButtonJuice(btn, btn, function()
			activeInvTab = tostring(btn:GetAttribute("TabKey") or "All")
			applyInventoryFilter()
		end)
	end
end
searchBox:GetPropertyChangedSignal("Text"):Connect(applyInventoryFilter)

for _, slot in ipairs(invItemGrid:GetChildren()) do
	if slot:IsA("GuiButton") then
		UIKit.AttachButtonJuice(slot, slot, function()
			inspTitle.Text = tostring(slot:GetAttribute("ItemName") or "Item")
			inspStats.Text = tostring(slot:GetAttribute("Stats") or "")
			local mName = tostring(slot:GetAttribute("ModelName") or "GoldenSword")
			local m = modelsFolder and modelsFolder:FindFirstChild(mName)
			if m then
				liveInvVp:SetModel(m)
			end
		end)
	end
end
UIKit.AttachButtonJuice(equipBtn, equipBtn, function()
	toasts:Push({ title = "Equipped", message = inspTitle.Text .. " equipped to active slot.", kind = "Success" })
end)

-- Quests wiring (Claim -> Coins + Toast)
local questsModal = modalMenusGui:WaitForChild("QuestsModal") :: GuiObject
local questList = questsModal:WaitForChild("Body"):WaitForChild("QuestList") :: ScrollingFrame
for _, row in ipairs(questList:GetChildren()) do
	if row:IsA("GuiObject") then
		local claimBtn = row:FindFirstChild("ClaimBtn")
		if claimBtn and claimBtn:IsA("TextButton") then
			UIKit.AttachButtonJuice(claimBtn, claimBtn, function()
				if row:GetAttribute("Claimed") == true then
					return
				end
				if row:GetAttribute("Claimable") ~= true then
					toasts:Push({ title = "Quest In Progress", message = "Complete all objectives first.", kind = "Warning" })
					return
				end
				row:SetAttribute("Claimed", true)
				local reward = tonumber(row:GetAttribute("RewardCoins")) or 100
				state.coins += reward
				updateCurrencyUI()
				claimBtn.Text = "CLAIMED"
				claimBtn:RemoveTag("ButtonSuccess")
				claimBtn:AddTag("ButtonSecondary")
				claimBtn.Interactable = false
				toasts:Push({ title = "Quest Complete!", message = "+" .. UIKit.FormatNumber(reward) .. " Coins", kind = "Reward" })
			end)
		end
	end
end

-- Index / Codes wiring
local indexModal = modalMenusGui:WaitForChild("IndexCodesModal") :: GuiObject
local codeBar = indexModal:WaitForChild("Body"):WaitForChild("CodeRedeemBar") :: Frame
local codeInput = codeBar:WaitForChild("CodeInput") :: TextBox
local redeemBtn = codeBar:WaitForChild("RedeemBtn") :: GuiButton
local function redeemCode(rawCode: string)
	local code = string.upper(string.gsub(rawCode, "%s+", ""))
	if code == "" then
		toasts:Push({ title = "Enter a Code", message = "Try LAUNCH2026 or GOLD100", kind = "Warning" })
		return
	end
	if state.redeemedCodes[code] then
		toasts:Push({ title = "Already Redeemed", message = code .. " was already claimed.", kind = "Warning" })
		return
	end
	if code == "LAUNCH2026" or code == "GOLD100" then
		state.redeemedCodes[code] = true
		state.coins += 500
		updateCurrencyUI()
		toasts:Push({ title = "Code Redeemed!", message = code .. ": +500 Coins", kind = "Reward" })
	else
		toasts:Push({ title = "Invalid Code", message = "Unknown promo code: " .. code, kind = "Error" })
	end
end
UIKit.AttachButtonJuice(redeemBtn, redeemBtn, function()
	redeemCode(codeInput.Text)
end)

-- Settings wiring (rebuild live UIDragDetector sliders + toggles on client)
local Lighting = game:GetService("Lighting")
local settingsModal = modalMenusGui:WaitForChild("SettingsModal") :: GuiObject
local settingsList = settingsModal:WaitForChild("Body"):WaitForChild("SettingsList") :: ScrollingFrame
for _, ch in ipairs(settingsList:GetChildren()) do
	if ch:IsA("GuiObject") then
		ch:Destroy()
	end
end
local liveMasterSlider = UIKit.CreateSlider({
	Name = "MasterVol",
	Parent = settingsList,
	Label = "Master Audio",
	InitialValue = state.settings.masterVol,
	OnChanged = function(val: number)
		state.settings.masterVol = math.floor(val + 0.5)
	end,
})
liveMasterSlider.Root.LayoutOrder = 1
local liveSfxSlider = UIKit.CreateSlider({
	Name = "SfxVol",
	Parent = settingsList,
	Label = "SFX Volume",
	InitialValue = state.settings.sfxVol,
	AccentColor = UIKit.Tokens.Colors.Success,
	OnChanged = function(val: number)
		state.settings.sfxVol = math.floor(val + 0.5)
	end,
})
liveSfxSlider.Root.LayoutOrder = 2
local liveShadowsToggle = UIKit.CreateToggle(settingsList, "ShadowsToggle", "Dynamic Shadows", state.settings.shadows, function(enabled: boolean)
	state.settings.shadows = enabled
	pcall(function()
		Lighting.GlobalShadows = enabled
	end)
end)
liveShadowsToggle.Root.LayoutOrder = 3
local liveParticlesToggle = UIKit.CreateToggle(settingsList, "ParticlesToggle", "High Detail FX", state.settings.particles, function(enabled: boolean)
	state.settings.particles = enabled
end)
liveParticlesToggle.Root.LayoutOrder = 4

-- NPC Dialog with MaxVisibleGraphemes typewriter
local npcCard = npcDialogGui:WaitForChild("NpcDialogCard") :: GuiObject
local npcDialogText = npcCard:WaitForChild("DialogText") :: TextLabel
local npcChoiceBar = npcCard:WaitForChild("ChoiceBar") :: Frame
local talkPromptBtn = contextualGui:WaitForChild("TalkNpcPromptBtn") :: GuiButton

local function openNpcDialog()
	npcDialogGui.Enabled = true
	npcDialogText.MaxVisibleGraphemes = 0
	task.spawn(function()
		local total = utf8.len(npcDialogText.ContentText) or #npcDialogText.Text
		if UIKit.IsReducedMotion() then
			npcDialogText.MaxVisibleGraphemes = -1
			return
		end
		for i = 1, total do
			if not npcDialogGui.Enabled then
				return
			end
			npcDialogText.MaxVisibleGraphemes = i
			task.wait(0.015)
		end
		npcDialogText.MaxVisibleGraphemes = -1
	end)
end

UIKit.AttachButtonJuice(talkPromptBtn, talkPromptBtn, openNpcDialog)
local shopChoice = npcChoiceBar:WaitForChild("OpenShopChoice") :: GuiButton
local questChoice = npcChoiceBar:WaitForChild("OpenQuestsChoice") :: GuiButton
local closeChoice = npcChoiceBar:WaitForChild("CloseNpcChoice") :: GuiButton
UIKit.AttachButtonJuice(shopChoice, shopChoice, function()
	npcDialogGui.Enabled = false
	modalManager:Open("Shop")
end)
UIKit.AttachButtonJuice(questChoice, questChoice, function()
	npcDialogGui.Enabled = false
	modalManager:Open("Quests")
end)
UIKit.AttachButtonJuice(closeChoice, closeChoice, function()
	npcDialogGui.Enabled = false
end)

-- Keyboard & Gamepad navigation bindings
UserInputService.InputBegan:Connect(function(input, processed)
	if processed then
		return
	end
	if input.KeyCode == Enum.KeyCode.Escape or input.KeyCode == Enum.KeyCode.ButtonB then
		if confirmDialogGui.Enabled then
			confirmDialogGui.Enabled = false
		elseif npcDialogGui.Enabled then
			npcDialogGui.Enabled = false
		else
			modalManager:Pop()
		end
	elseif input.KeyCode == Enum.KeyCode.One then
		selectHotbar(1)
	elseif input.KeyCode == Enum.KeyCode.Two then
		selectHotbar(2)
	elseif input.KeyCode == Enum.KeyCode.Three then
		selectHotbar(3)
	elseif input.KeyCode == Enum.KeyCode.Four then
		selectHotbar(4)
	elseif input.KeyCode == Enum.KeyCode.Five then
		selectHotbar(5)
	elseif input.KeyCode == Enum.KeyCode.E then
		openNpcDialog()
	end
end)

-- Debug / Automated Playtest verification hook
local debugFn = Instance.new("BindableFunction")
debugFn.Name = "StandardGuiDebug"
debugFn.OnInvoke = function(action: string, arg: any)
	if action == "GetState" then
		return {
			activeModal = modalManager:GetActive(),
			coins = state.coins,
			gems = state.gems,
			selectedSlot = state.selectedSlot,
			activeToasts = toasts:GetActiveCount(),
			confirmOpen = confirmDialogGui.Enabled,
			npcOpen = npcDialogGui.Enabled,
			tooltipVisible = tooltip.Card.Visible,
			settings = state.settings,
		}
	elseif action == "SetMasterVolume" then
		liveMasterSlider.SetValue(tonumber(arg) or 50)
		return state.settings.masterVol
	elseif action == "ToggleShadows" then
		local nextVal = if arg ~= nil then (arg == true) else (not liveShadowsToggle.GetState())
		liveShadowsToggle.SetState(nextVal)
		return state.settings.shadows
	elseif action == "OpenModal" then
		modalManager:Open(tostring(arg))
		return modalManager:GetActive()
	elseif action == "CloseAll" then
		modalManager:CloseAll()
		confirmDialogGui.Enabled = false
		npcDialogGui.Enabled = false
		tooltip:Hide()
		return true
	elseif action == "SelectSlot" then
		selectHotbar(tonumber(arg) or 1)
		return state.selectedSlot
	elseif action == "PushToast" then
		toasts:Push({ title = tostring(arg or "Notice"), message = "Live Playtest Toast", kind = "Reward" })
		return toasts:GetActiveCount()
	elseif action == "ShowTooltip" then
		tooltip:Show("Sunfire Blade", "Legendary", "+48 ATK | Crit +12%", Vector2.new(900, 500), UIKit.Tokens.Colors.Gold)
		return tooltip.Card.Visible
	elseif action == "ShowNpcDialog" then
		openNpcDialog()
		return npcDialogGui.Enabled
	elseif action == "RedeemCode" then
		redeemCode(tostring(arg or "LAUNCH2026"))
		return state.coins
	end
	return nil
end
debugFn.Parent = playerGui
]===]
clientCtrl.Parent = sps

return string.format(
	"Built StandardGameGui in StarterGui (%d ScreenGuis) + ReplicatedStorage.UIStyles + StarterPlayerScripts.StandardGuiController",
	#GUI_NAMES
)

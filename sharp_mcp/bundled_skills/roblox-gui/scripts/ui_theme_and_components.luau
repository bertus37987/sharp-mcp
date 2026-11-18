--!strict
-- ui_theme_and_components.luau
-- Production Roblox UI Kit: Design Tokens, StyleSheet/StyleRule builder, 9-slice & native
-- component factories, Modal Stack Manager, Clamped Tooltip, FIFO Toast Queue,
-- ViewportFrame 3D Previewer, UIDragDetector Slider, Tween UI Juice, and Responsive UIScale.
--
-- Install as a ModuleScript at ReplicatedStorage.UIThemeAndComponents (or ReplicatedStorage.Modules.UIThemeAndComponents).

local CollectionService = game:GetService("CollectionService")
local GuiService = game:GetService("GuiService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

export type AssetOverrides = {
	Panel9SliceId: string?,
	Panel9SliceCenter: Rect?,
	PanelSliceScale: number?,
	Button9SliceId: string?,
	Button9SliceCenter: Rect?,
	ButtonSliceScale: number?,
	IconAtlasId: string?,
	IconRects: { [string]: { offset: Vector2, size: Vector2 } }?,
}

export type ToastKind = "Info" | "Success" | "Reward" | "Warning" | "Error"

export type ToastRequest = {
	title: string,
	message: string?,
	kind: ToastKind?,
	duration: number?,
}

local function safeFont(familyAsset: string, weight: Enum.FontWeight, style: Enum.FontStyle, fallbackAsset: string?): Font
	local ok, result = pcall(function()
		return Font.new(familyAsset, weight, style)
	end)
	if ok and result then
		return result
	end
	return Font.new(fallbackAsset or "rbxasset://fonts/families/BuilderSans.json", weight, style)
end

local function makeGlossyStops(base: Color3): { { time: number, color: Color3 } }
	local top = base:Lerp(Color3.fromRGB(255, 255, 255), 0.30)
	local hi = base:Lerp(Color3.fromRGB(255, 255, 255), 0.12)
	local low = base:Lerp(Color3.fromRGB(16, 12, 28), 0.22)
	return {
		{ time = 0.0, color = top },
		{ time = 0.24, color = hi },
		{ time = 0.62, color = base },
		{ time = 1.0, color = low },
	}
end

local UIKit = {}

UIKit.Tokens = {
	Meta = {
		GameTitle = "Sharp Stylized UI",
		Genre = "adventure",
		Mood = "vibrant",
		PresetId = "rpg_arcane",
		SurfaceMode = "dark",
		Harmony = "triadic",
		SeedHash = "00000000",
		TextureStyle = "arcane_emissive_runes",
		AssetStyle = "handpainted_fantasy_rpg",
	},
	Colors = {
		BgDeep = Color3.fromRGB(22, 16, 36),
		BgPanel = Color3.fromRGB(34, 26, 56),
		BgCard = Color3.fromRGB(45, 35, 74),
		BgCardHover = Color3.fromRGB(58, 46, 94),
		BgElevated = Color3.fromRGB(52, 41, 84),
		BgInput = Color3.fromRGB(18, 13, 30),
		BorderSubtle = Color3.fromRGB(98, 78, 142),
		BorderBright = Color3.fromRGB(184, 152, 245),
		OutlineInk = Color3.fromRGB(14, 10, 24),
		InnerHighlight = Color3.fromRGB(255, 255, 255),
		TextPrimary = Color3.fromRGB(250, 246, 255),
		TextSecondary = Color3.fromRGB(204, 194, 228),
		TextMuted = Color3.fromRGB(150, 140, 178),
		TextOnPrimary = Color3.fromRGB(22, 14, 8),
		TextOnSecondary = Color3.fromRGB(250, 246, 255),
		TextOnAccent = Color3.fromRGB(16, 22, 28),
		TextOnSuccess = Color3.fromRGB(12, 26, 18),
		TextOnWarning = Color3.fromRGB(28, 18, 6),
		TextOnDanger = Color3.fromRGB(255, 248, 250),
		Primary = Color3.fromRGB(246, 174, 45),
		PrimaryHover = Color3.fromRGB(255, 196, 86),
		PrimaryPress = Color3.fromRGB(204, 136, 22),
		Secondary = Color3.fromRGB(142, 78, 232),
		SecondaryHover = Color3.fromRGB(166, 108, 246),
		SecondaryPress = Color3.fromRGB(110, 56, 190),
		Accent = Color3.fromRGB(46, 214, 190),
		AccentHover = Color3.fromRGB(88, 234, 212),
		AccentPress = Color3.fromRGB(32, 168, 148),
		Success = Color3.fromRGB(54, 210, 122),
		SuccessHover = Color3.fromRGB(86, 228, 148),
		SuccessPress = Color3.fromRGB(38, 168, 94),
		Warning = Color3.fromRGB(252, 186, 48),
		WarningHover = Color3.fromRGB(255, 206, 88),
		WarningPress = Color3.fromRGB(208, 146, 26),
		Danger = Color3.fromRGB(238, 66, 98),
		DangerHover = Color3.fromRGB(252, 96, 126),
		DangerPress = Color3.fromRGB(192, 46, 74),
		Gold = Color3.fromRGB(255, 212, 72),
		Gem = Color3.fromRGB(46, 214, 190),
		Scrim = Color3.fromRGB(10, 8, 18),
	},
	Rarity = {
		Common = Color3.fromRGB(164, 158, 186),
		Uncommon = Color3.fromRGB(54, 210, 122),
		Rare = Color3.fromRGB(56, 186, 248),
		Epic = Color3.fromRGB(178, 92, 250),
		Legendary = Color3.fromRGB(255, 204, 64),
		Mythic = Color3.fromRGB(246, 68, 126),
	},
	Radii = {
		Xs = UDim.new(0, 4),
		Small = UDim.new(0, 8),
		Medium = UDim.new(0, 14),
		Large = UDim.new(0, 20),
		Panel = UDim.new(0, 16),
		Button = UDim.new(0, 11),
		Badge = UDim.new(0, 6),
		Pill = UDim.new(1, 0),
	},
	Spacing = {
		Xs = 4,
		Sm = 8,
		Md = 12,
		Lg = 16,
		Xl = 24,
	},
	Strokes = {
		OuterInk = 4.0,
		InnerHighlight = 1.8,
		Panel = 3.5,
		Text = 2.0,
		LineJoin = Enum.LineJoinMode.Round,
	},
	Shadows = {
		OffsetX = 0,
		OffsetY = 5,
		PressOffsetY = 3,
		BlurRadius = 6,
		Transparency = 0.24,
		Color = Color3.fromRGB(12, 8, 22),
	},
	Gradients = {
		Primary = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(246, 174, 45)) },
		Secondary = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(142, 78, 232)) },
		Accent = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(46, 214, 190)) },
		Success = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(54, 210, 122)) },
		Warning = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(252, 186, 48)) },
		Danger = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(238, 66, 98)) },
		Gold = { Rotation = -38, Type = "Linear", Stops = makeGlossyStops(Color3.fromRGB(255, 212, 72)) },
		Panel = {
			Rotation = -42,
			Type = "Linear",
			Stops = {
				{ time = 0.0, color = Color3.fromRGB(46, 36, 76) },
				{ time = 0.45, color = Color3.fromRGB(34, 26, 56) },
				{ time = 1.0, color = Color3.fromRGB(24, 18, 42) },
			},
		},
		ShineSweep = { Rotation = -25, Duration = 0.65 },
	},
	Motifs = {
		PresetId = "rpg_arcane",
		RaysEnabled = true,
		RayCount = 12,
		BadgeRotation = -5,
		SurfacePattern = "gilded_arcane_filigree",
	},
	Content = {
		GameTitle = "Sharp Stylized UI",
		Genre = "adventure",
		PresetId = "rpg_arcane",
		OrnamentKind = "arcane_filigree",
		RoleTitle = "Lv. 24 • Arcane",
		ObjectiveTitle = "ACTIVE QUEST",
		ObjectiveText = "Purify 3 Arcane Runestones in Sanctum (2/3)",
		HotbarSkills = { "Runeblade", "Aegis Ward", "Elixir Flask", "Blink Step", "Arcane Sigil" },
	},
	MinTouchPx = 44,
	Fonts = {
		Title = safeFont("rbxasset://fonts/families/BuilderSans.json", Enum.FontWeight.ExtraBold, Enum.FontStyle.Normal),
		Heading = safeFont("rbxasset://fonts/families/BuilderSans.json", Enum.FontWeight.Bold, Enum.FontStyle.Normal),
		Body = safeFont("rbxasset://fonts/families/BuilderSans.json", Enum.FontWeight.Medium, Enum.FontStyle.Normal),
		Mono = safeFont("rbxasset://fonts/families/RobotoMono.json", Enum.FontWeight.Bold, Enum.FontStyle.Normal),
	},
	ZLayers = {
		BackdropVignette = 0,
		MainHud = 10,
		TopbarWidgets = 20,
		ContextualPrompt = 30,
		ModalBackdrop = 49,
		ModalMenus = 50,
		NpcDialog = 65,
		ConfirmDialog = 80,
		FloatingTooltip = 90,
		ToastNotification = 100,
		LoadingTransition = 1000,
	},
}

UIKit.Presets = {
	candy_simulator = {
		Meta = { PresetId = "candy_simulator", SurfaceMode = "dark", Harmony = "triadic" },
		Colors = {
			BgDeep = Color3.fromRGB(36, 18, 56),
			BgPanel = Color3.fromRGB(52, 26, 80),
			BgCard = Color3.fromRGB(68, 36, 102),
			BgCardHover = Color3.fromRGB(84, 46, 124),
			BgElevated = Color3.fromRGB(76, 40, 112),
			BgInput = Color3.fromRGB(28, 14, 44),
			BorderSubtle = Color3.fromRGB(132, 82, 184),
			BorderBright = Color3.fromRGB(255, 138, 198),
			OutlineInk = Color3.fromRGB(24, 12, 38),
			TextPrimary = Color3.fromRGB(255, 250, 255),
			TextSecondary = Color3.fromRGB(224, 206, 246),
			TextMuted = Color3.fromRGB(174, 150, 206),
			TextOnPrimary = Color3.fromRGB(255, 255, 255),
			TextOnSecondary = Color3.fromRGB(18, 22, 32),
			TextOnAccent = Color3.fromRGB(28, 16, 8),
			Primary = Color3.fromRGB(255, 62, 142),
			PrimaryHover = Color3.fromRGB(255, 102, 168),
			PrimaryPress = Color3.fromRGB(212, 38, 112),
			Secondary = Color3.fromRGB(48, 220, 236),
			SecondaryHover = Color3.fromRGB(96, 234, 246),
			SecondaryPress = Color3.fromRGB(30, 174, 190),
			Accent = Color3.fromRGB(255, 196, 48),
			AccentHover = Color3.fromRGB(255, 214, 96),
			AccentPress = Color3.fromRGB(216, 156, 24),
			Gold = Color3.fromRGB(255, 214, 58),
			Gem = Color3.fromRGB(48, 220, 236),
		},
		Radii = { Xs = UDim.new(0, 6), Small = UDim.new(0, 12), Medium = UDim.new(0, 18), Large = UDim.new(0, 24), Panel = UDim.new(0, 22), Button = UDim.new(0, 16), Badge = UDim.new(0, 10), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 5.0, InnerHighlight = 2.0, Panel = 4.5, Text = 2.2, LineJoin = Enum.LineJoinMode.Round },
		Shadows = { OffsetX = 0, OffsetY = 6, PressOffsetY = 3, BlurRadius = 6, Transparency = 0.24, Color = Color3.fromRGB(22, 10, 36) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/FredokaOne.json" },
		Motifs = { PresetId = "candy_simulator", RaysEnabled = true, RayCount = 12, BadgeRotation = -6, SurfacePattern = "glossy_candy_bubbles" },
		Content = {
			PresetId = "candy_simulator",
			OrnamentKind = "bubble_shine",
			RoleTitle = "Rebirth XII • x25",
			ObjectiveTitle = "SWEET GOAL",
			ObjectiveText = "Hatch 3 Sugar Pets & collect 500 Drops (2/3)",
			HotbarSkills = { "Sugar Scoop", "Pet Magnet", "Bubble Boost", "Candy Drop", "Rebirth Pop" },
		},
	},
	anime_neon = {
		Meta = { PresetId = "anime_neon", SurfaceMode = "dark", Harmony = "split_complementary" },
		Colors = {
			BgDeep = Color3.fromRGB(16, 14, 30),
			BgPanel = Color3.fromRGB(26, 22, 48),
			BgCard = Color3.fromRGB(36, 30, 64),
			BgCardHover = Color3.fromRGB(48, 40, 84),
			BgElevated = Color3.fromRGB(42, 36, 74),
			BgInput = Color3.fromRGB(12, 10, 24),
			BorderSubtle = Color3.fromRGB(98, 72, 164),
			BorderBright = Color3.fromRGB(255, 198, 52),
			OutlineInk = Color3.fromRGB(10, 8, 20),
			TextPrimary = Color3.fromRGB(252, 250, 255),
			TextSecondary = Color3.fromRGB(206, 202, 232),
			TextMuted = Color3.fromRGB(146, 140, 182),
			TextOnPrimary = Color3.fromRGB(24, 16, 8),
			TextOnSecondary = Color3.fromRGB(255, 250, 252),
			TextOnAccent = Color3.fromRGB(12, 20, 26),
			Primary = Color3.fromRGB(255, 186, 36),
			PrimaryHover = Color3.fromRGB(255, 206, 84),
			PrimaryPress = Color3.fromRGB(212, 146, 16),
			Secondary = Color3.fromRGB(246, 48, 96),
			SecondaryHover = Color3.fromRGB(255, 86, 128),
			SecondaryPress = Color3.fromRGB(198, 30, 72),
			Accent = Color3.fromRGB(46, 232, 248),
			AccentHover = Color3.fromRGB(98, 242, 255),
			AccentPress = Color3.fromRGB(28, 182, 200),
			Gold = Color3.fromRGB(255, 208, 64),
			Gem = Color3.fromRGB(46, 232, 248),
		},
		Radii = { Xs = UDim.new(0, 3), Small = UDim.new(0, 6), Medium = UDim.new(0, 11), Large = UDim.new(0, 16), Panel = UDim.new(0, 12), Button = UDim.new(0, 8), Badge = UDim.new(0, 4), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 4.5, InnerHighlight = 1.8, Panel = 4.0, Text = 2.4, LineJoin = Enum.LineJoinMode.Bevel },
		Shadows = { OffsetX = 3, OffsetY = 5, PressOffsetY = 3, BlurRadius = 2, Transparency = 0.18, Color = Color3.fromRGB(10, 8, 20) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/Bangers.json" },
		Motifs = { PresetId = "anime_neon", RaysEnabled = true, RayCount = 14, BadgeRotation = -5, SurfacePattern = "diagonal_speed_lines" },
		Content = {
			PresetId = "anime_neon",
			OrnamentKind = "cyber_slash",
			RoleTitle = "Rank S • Awakening",
			ObjectiveTitle = "AWAKENING TRIAL",
			ObjectiveText = "Chain a 25-hit Combo & break 3 Seals (2/3)",
			HotbarSkills = { "Flash Step", "Gale Cleave", "Aura Surge", "Parry Guard", "Zenith Nova" },
		},
	},
	cozy_pastel = {
		Meta = { PresetId = "cozy_pastel", SurfaceMode = "light", Harmony = "analogous" },
		Colors = {
			BgDeep = Color3.fromRGB(238, 224, 202),
			BgPanel = Color3.fromRGB(252, 244, 230),
			BgCard = Color3.fromRGB(246, 234, 214),
			BgCardHover = Color3.fromRGB(255, 248, 236),
			BgElevated = Color3.fromRGB(255, 246, 232),
			BgInput = Color3.fromRGB(232, 218, 196),
			BorderSubtle = Color3.fromRGB(178, 146, 112),
			BorderBright = Color3.fromRGB(228, 116, 78),
			OutlineInk = Color3.fromRGB(62, 42, 30),
			TextPrimary = Color3.fromRGB(48, 32, 22),
			TextSecondary = Color3.fromRGB(98, 72, 54),
			TextMuted = Color3.fromRGB(134, 108, 88),
			TextOnPrimary = Color3.fromRGB(255, 252, 248),
			TextOnSecondary = Color3.fromRGB(252, 255, 252),
			TextOnAccent = Color3.fromRGB(255, 250, 255),
			Primary = Color3.fromRGB(224, 104, 62),
			PrimaryHover = Color3.fromRGB(240, 128, 86),
			PrimaryPress = Color3.fromRGB(186, 80, 44),
			Secondary = Color3.fromRGB(64, 168, 118),
			SecondaryHover = Color3.fromRGB(88, 188, 140),
			SecondaryPress = Color3.fromRGB(46, 134, 92),
			Accent = Color3.fromRGB(146, 98, 214),
			AccentHover = Color3.fromRGB(168, 124, 230),
			AccentPress = Color3.fromRGB(118, 74, 182),
			Gold = Color3.fromRGB(218, 154, 34),
			Gem = Color3.fromRGB(146, 98, 214),
		},
		Radii = { Xs = UDim.new(0, 5), Small = UDim.new(0, 10), Medium = UDim.new(0, 16), Large = UDim.new(0, 22), Panel = UDim.new(0, 18), Button = UDim.new(0, 14), Badge = UDim.new(0, 8), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 3.5, InnerHighlight = 2.0, Panel = 3.5, Text = 1.2, LineJoin = Enum.LineJoinMode.Round },
		Shadows = { OffsetX = 0, OffsetY = 5, PressOffsetY = 3, BlurRadius = 8, Transparency = 0.34, Color = Color3.fromRGB(72, 48, 32) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/Nunito.json", HeadingFamily = "rbxasset://fonts/families/Nunito.json" },
		Motifs = { PresetId = "cozy_pastel", RaysEnabled = false, RayCount = 8, BadgeRotation = 4, SurfacePattern = "warm_linen_stitches" },
		Content = {
			PresetId = "cozy_pastel",
			OrnamentKind = "stitched_warm",
			RoleTitle = "Cosy Lv. 8 • Keeper",
			ObjectiveTitle = "DAILY HARVEST",
			ObjectiveText = "Craft 4 Warm Treats & greet Villagers (3/4)",
			HotbarSkills = { "Water Can", "Harvest Basket", "Warm Whisk", "Cozy Lantern", "Seed Pouch" },
		},
	},
	scifi_holo = {
		Meta = { PresetId = "scifi_holo", SurfaceMode = "dark", Harmony = "tetradic" },
		Colors = {
			BgDeep = Color3.fromRGB(10, 22, 28),
			BgPanel = Color3.fromRGB(16, 34, 42),
			BgCard = Color3.fromRGB(22, 46, 56),
			BgCardHover = Color3.fromRGB(30, 62, 74),
			BgElevated = Color3.fromRGB(26, 54, 66),
			BgInput = Color3.fromRGB(8, 18, 22),
			BorderSubtle = Color3.fromRGB(48, 118, 134),
			BorderBright = Color3.fromRGB(46, 236, 224),
			OutlineInk = Color3.fromRGB(6, 16, 22),
			TextPrimary = Color3.fromRGB(238, 254, 255),
			TextSecondary = Color3.fromRGB(168, 220, 228),
			TextMuted = Color3.fromRGB(110, 166, 178),
			TextOnPrimary = Color3.fromRGB(8, 24, 26),
			TextOnSecondary = Color3.fromRGB(10, 26, 18),
			TextOnAccent = Color3.fromRGB(255, 248, 255),
			Primary = Color3.fromRGB(34, 230, 218),
			PrimaryHover = Color3.fromRGB(86, 244, 234),
			PrimaryPress = Color3.fromRGB(20, 180, 170),
			Secondary = Color3.fromRGB(56, 236, 146),
			SecondaryHover = Color3.fromRGB(98, 246, 172),
			SecondaryPress = Color3.fromRGB(38, 184, 110),
			Accent = Color3.fromRGB(218, 86, 246),
			AccentHover = Color3.fromRGB(232, 126, 255),
			AccentPress = Color3.fromRGB(174, 58, 202),
			Gold = Color3.fromRGB(248, 200, 66),
			Gem = Color3.fromRGB(34, 230, 218),
		},
		Radii = { Xs = UDim.new(0, 2), Small = UDim.new(0, 5), Medium = UDim.new(0, 9), Large = UDim.new(0, 13), Panel = UDim.new(0, 10), Button = UDim.new(0, 6), Badge = UDim.new(0, 3), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 3.0, InnerHighlight = 1.5, Panel = 3.0, Text = 1.5, LineJoin = Enum.LineJoinMode.Bevel },
		Shadows = { OffsetX = 0, OffsetY = 4, PressOffsetY = 2, BlurRadius = 10, Transparency = 0.28, Color = Color3.fromRGB(6, 16, 22) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/Michroma.json" },
		Motifs = { PresetId = "scifi_holo", RaysEnabled = false, RayCount = 10, BadgeRotation = -3, SurfacePattern = "precision_hex_scanlines" },
		Content = {
			PresetId = "scifi_holo",
			OrnamentKind = "holo_brackets",
			RoleTitle = "Cmdr.MkIV • 100%",
			ObjectiveTitle = "ACTIVE DIRECTIVE",
			ObjectiveText = "Stabilize 3 Relay Nodes & scan Sector 7 (2/3)",
			HotbarSkills = { "Pulse Rifle", "Holo Aegis", "Nano Patch", "Thruster Dash", "Orbital Ping" },
		},
	},
	arcade_pop = {
		Meta = { PresetId = "arcade_pop", SurfaceMode = "dark", Harmony = "tetradic" },
		Colors = {
			BgDeep = Color3.fromRGB(24, 16, 46),
			BgPanel = Color3.fromRGB(36, 24, 68),
			BgCard = Color3.fromRGB(48, 34, 88),
			BgCardHover = Color3.fromRGB(62, 46, 112),
			BgElevated = Color3.fromRGB(54, 38, 96),
			BgInput = Color3.fromRGB(18, 12, 36),
			BorderSubtle = Color3.fromRGB(116, 86, 186),
			BorderBright = Color3.fromRGB(255, 222, 48),
			OutlineInk = Color3.fromRGB(10, 6, 18),
			TextPrimary = Color3.fromRGB(255, 255, 255),
			TextSecondary = Color3.fromRGB(218, 210, 248),
			TextMuted = Color3.fromRGB(158, 148, 198),
			TextOnPrimary = Color3.fromRGB(26, 12, 6),
			TextOnSecondary = Color3.fromRGB(10, 24, 14),
			TextOnAccent = Color3.fromRGB(24, 18, 6),
			Primary = Color3.fromRGB(255, 112, 32),
			PrimaryHover = Color3.fromRGB(255, 144, 72),
			PrimaryPress = Color3.fromRGB(214, 82, 16),
			Secondary = Color3.fromRGB(56, 232, 118),
			SecondaryHover = Color3.fromRGB(98, 246, 150),
			SecondaryPress = Color3.fromRGB(36, 184, 88),
			Accent = Color3.fromRGB(255, 222, 42),
			AccentHover = Color3.fromRGB(255, 234, 96),
			AccentPress = Color3.fromRGB(216, 180, 20),
			Gold = Color3.fromRGB(255, 222, 42),
			Gem = Color3.fromRGB(48, 224, 248),
		},
		Radii = { Xs = UDim.new(0, 3), Small = UDim.new(0, 6), Medium = UDim.new(0, 10), Large = UDim.new(0, 14), Panel = UDim.new(0, 10), Button = UDim.new(0, 7), Badge = UDim.new(0, 4), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 5.5, InnerHighlight = 2.2, Panel = 5.0, Text = 2.5, LineJoin = Enum.LineJoinMode.Miter },
		Shadows = { OffsetX = 3, OffsetY = 5, PressOffsetY = 3, BlurRadius = 0, Transparency = 0.12, Color = Color3.fromRGB(10, 6, 18) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/Bangers.json" },
		Motifs = { PresetId = "arcade_pop", RaysEnabled = true, RayCount = 16, BadgeRotation = -7, SurfacePattern = "comic_halftone_dots" },
		Content = {
			PresetId = "arcade_pop",
			OrnamentKind = "comic_stripe",
			RoleTitle = "COMBO x9 • PRO",
			ObjectiveTitle = "BONUS ROUND",
			ObjectiveText = "Score 5,000 Arena Points before timer hits 0 (3/5)",
			HotbarSkills = { "Turbo Boost", "Power Smash", "Mega Bounce", "Nitro Dash", "Super Star" },
		},
	},
	rpg_arcane = {
		Meta = { PresetId = "rpg_arcane", SurfaceMode = "dark", Harmony = "triadic" },
		Colors = {
			BgDeep = Color3.fromRGB(22, 16, 36),
			BgPanel = Color3.fromRGB(34, 26, 56),
			BgCard = Color3.fromRGB(45, 35, 74),
			BgCardHover = Color3.fromRGB(58, 46, 94),
			BgElevated = Color3.fromRGB(52, 41, 84),
			BgInput = Color3.fromRGB(18, 13, 30),
			BorderSubtle = Color3.fromRGB(98, 78, 142),
			BorderBright = Color3.fromRGB(184, 152, 245),
			OutlineInk = Color3.fromRGB(14, 10, 24),
			TextPrimary = Color3.fromRGB(250, 246, 255),
			TextSecondary = Color3.fromRGB(204, 194, 228),
			TextMuted = Color3.fromRGB(150, 140, 178),
			TextOnPrimary = Color3.fromRGB(22, 14, 8),
			TextOnSecondary = Color3.fromRGB(250, 246, 255),
			TextOnAccent = Color3.fromRGB(16, 22, 28),
			Primary = Color3.fromRGB(246, 174, 45),
			PrimaryHover = Color3.fromRGB(255, 196, 86),
			PrimaryPress = Color3.fromRGB(204, 136, 22),
			Secondary = Color3.fromRGB(142, 78, 232),
			SecondaryHover = Color3.fromRGB(166, 108, 246),
			SecondaryPress = Color3.fromRGB(110, 56, 190),
			Accent = Color3.fromRGB(46, 214, 190),
			AccentHover = Color3.fromRGB(88, 234, 212),
			AccentPress = Color3.fromRGB(32, 168, 148),
			Gold = Color3.fromRGB(255, 212, 72),
			Gem = Color3.fromRGB(46, 214, 190),
		},
		Radii = { Xs = UDim.new(0, 3), Small = UDim.new(0, 8), Medium = UDim.new(0, 13), Large = UDim.new(0, 18), Panel = UDim.new(0, 14), Button = UDim.new(0, 9), Badge = UDim.new(0, 5), Pill = UDim.new(1, 0) },
		Strokes = { OuterInk = 4.0, InnerHighlight = 1.8, Panel = 4.0, Text = 2.0, LineJoin = Enum.LineJoinMode.Bevel },
		Shadows = { OffsetX = 0, OffsetY = 5, PressOffsetY = 3, BlurRadius = 8, Transparency = 0.28, Color = Color3.fromRGB(14, 10, 24) },
		Fonts = { TitleFamily = "rbxasset://fonts/families/Fondamento.json" },
		Motifs = { PresetId = "rpg_arcane", RaysEnabled = true, RayCount = 10, BadgeRotation = -4, SurfacePattern = "gilded_arcane_filigree" },
		Content = {
			PresetId = "rpg_arcane",
			OrnamentKind = "arcane_filigree",
			RoleTitle = "Lv. 24 • Arcane",
			ObjectiveTitle = "ACTIVE QUEST",
			ObjectiveText = "Purify 3 Arcane Runestones in Sanctum (2/3)",
			HotbarSkills = { "Runeblade", "Aegis Ward", "Elixir Flask", "Blink Step", "Arcane Sigil" },
		},
	},
}

UIKit.Assets = {} :: AssetOverrides

function UIKit.SetAssets(overrides: AssetOverrides?)
	UIKit.Assets = overrides or {}
end

local function syncLiveStyleSheetTokens()
	local stylesFolder = ReplicatedStorage:FindFirstChild("UIStyles")
	if not stylesFolder then
		return
	end
	local tokensSheet = stylesFolder:FindFirstChild("TokensSheet")
	if not tokensSheet or not tokensSheet:IsA("StyleSheet") then
		return
	end
	local c = UIKit.Tokens.Colors :: any
	local r = UIKit.Tokens.Radii :: any
	local attrColors = {
		"BgPanel", "BgCard", "Primary", "PrimaryHover", "PrimaryPress",
		"Secondary", "SecondaryHover", "SecondaryPress",
		"Accent", "AccentHover", "AccentPress",
		"Danger", "DangerHover", "DangerPress",
		"Success", "SuccessHover", "SuccessPress",
		"Warning", "WarningHover", "WarningPress",
		"TextPrimary", "TextOnPrimary", "TextOnSecondary", "TextOnAccent",
		"TextOnSuccess", "TextOnWarning", "TextOnDanger",
		"BorderSubtle", "BorderBright", "OutlineInk",
	}
	for _, key in ipairs(attrColors) do
		if c[key] ~= nil then
			tokensSheet:SetAttribute(key, c[key])
		end
	end
	tokensSheet:SetAttribute("RadiusMd", r.Medium)
	tokensSheet:SetAttribute("RadiusPanel", r.Panel)
	tokensSheet:SetAttribute("RadiusButton", r.Button)
	tokensSheet:SetAttribute("RadiusBadge", r.Badge)
end

local PRESET_ORNAMENT_MAP: { [string]: string } = {
	candy_simulator = "bubble_shine",
	anime_neon = "cyber_slash",
	cozy_pastel = "stitched_warm",
	scifi_holo = "holo_brackets",
	arcade_pop = "comic_stripe",
	rpg_arcane = "arcane_filigree",
}

function UIKit.ApplyDesignSystem(dsOrPreset: any): { [string]: any }
	local ds = dsOrPreset
	if typeof(dsOrPreset) == "string" then
		ds = (UIKit.Presets :: any)[dsOrPreset]
		if not ds then
			warn(string.format("[UIKit.ApplyDesignSystem] Unknown preset '%s'", dsOrPreset))
			return UIKit.Tokens
		end
	elseif typeof(dsOrPreset) == "table" and dsOrPreset.Preset and (UIKit.Presets :: any)[dsOrPreset.Preset] then
		local basePreset = (UIKit.Presets :: any)[dsOrPreset.Preset]
		UIKit.ApplyDesignSystem(basePreset)
	end
	if typeof(ds) ~= "table" then
		return UIKit.Tokens
	end

	if typeof(ds.Meta) == "table" then
		local tMeta = UIKit.Tokens.Meta :: any
		for k, v in pairs(ds.Meta) do
			tMeta[k] = v
		end
	end
	if typeof(ds.TextureStyle) == "string" and ds.TextureStyle ~= "" then
		(UIKit.Tokens.Meta :: any).TextureStyle = ds.TextureStyle
	end
	if typeof(ds.AssetStyle) == "string" and ds.AssetStyle ~= "" then
		(UIKit.Tokens.Meta :: any).AssetStyle = ds.AssetStyle
	end

	if typeof(ds.Colors) == "table" then
		local tc = UIKit.Tokens.Colors :: any
		for k, v in pairs(ds.Colors) do
			if typeof(v) == "Color3" then
				tc[k] = v
			end
		end
		-- Rebuild default glossy gradients for color keys unless explicitly overridden below
		local gradMap = { "Primary", "Secondary", "Accent", "Success", "Warning", "Danger", "Gold" }
		local tGrad = UIKit.Tokens.Gradients :: any
		for _, gk in ipairs(gradMap) do
			if ds.Colors[gk] and (typeof(ds.Gradients) ~= "table" or ds.Gradients[gk] == nil) then
				tGrad[gk] = {
					Rotation = -38,
					Type = "Linear",
					Stops = makeGlossyStops(ds.Colors[gk]),
				}
			end
		end
		if ds.Colors.BgPanel and (typeof(ds.Gradients) ~= "table" or ds.Gradients.Panel == nil) then
			local bp: Color3 = ds.Colors.BgPanel
			local isDark = ds.Meta == nil or ds.Meta.SurfaceMode ~= "light"
			local hi = if isDark then bp:Lerp(Color3.fromRGB(255, 255, 255), 0.08) else bp:Lerp(Color3.fromRGB(255, 255, 255), 0.14)
			local lo = if isDark then bp:Lerp(Color3.fromRGB(0, 0, 0), 0.16) else bp:Lerp(Color3.fromRGB(48, 36, 24), 0.08)
			UIKit.Tokens.Gradients.Panel = {
				Rotation = -42,
				Type = "Linear",
				Stops = {
					{ time = 0.0, color = hi },
					{ time = 0.48, color = bp },
					{ time = 1.0, color = lo },
				},
			}
		end
	end

	if typeof(ds.Rarity) == "table" then
		local tr = UIKit.Tokens.Rarity :: any
		for k, v in pairs(ds.Rarity) do
			if typeof(v) == "Color3" then
				tr[k] = v
			end
		end
	end

	if typeof(ds.Radii) == "table" then
		local tr = UIKit.Tokens.Radii :: any
		for k, v in pairs(ds.Radii) do
			if typeof(v) == "UDim" then
				tr[k] = v
			elseif typeof(v) == "number" then
				tr[k] = if v >= 999 then UDim.new(1, 0) else UDim.new(0, v)
			end
		end
	end

	if typeof(ds.Strokes) == "table" then
		local ts = UIKit.Tokens.Strokes :: any
		for k, v in pairs(ds.Strokes) do
			ts[k] = v
		end
	end

	if typeof(ds.Shadows) == "table" then
		local tsh = UIKit.Tokens.Shadows :: any
		for k, v in pairs(ds.Shadows) do
			tsh[k] = v
		end
	end

	if typeof(ds.Gradients) == "table" then
		local tg = UIKit.Tokens.Gradients :: any
		for k, v in pairs(ds.Gradients) do
			if typeof(v) == "table" then
				tg[k] = v
			end
		end
	end

	if typeof(ds.Fonts) == "table" then
		if typeof(ds.Fonts.TitleFamily) == "string" then
			UIKit.Tokens.Fonts.Title = safeFont(ds.Fonts.TitleFamily, Enum.FontWeight.ExtraBold, Enum.FontStyle.Normal)
		end
		if typeof(ds.Fonts.HeadingFamily) == "string" then
			UIKit.Tokens.Fonts.Heading = safeFont(ds.Fonts.HeadingFamily, Enum.FontWeight.Bold, Enum.FontStyle.Normal)
		end
		if typeof(ds.Fonts.BodyFamily) == "string" then
			UIKit.Tokens.Fonts.Body = safeFont(ds.Fonts.BodyFamily, Enum.FontWeight.Medium, Enum.FontStyle.Normal)
		end
		if typeof(ds.Fonts.MonoFamily) == "string" then
			UIKit.Tokens.Fonts.Mono = safeFont(ds.Fonts.MonoFamily, Enum.FontWeight.Bold, Enum.FontStyle.Normal, "rbxasset://fonts/families/RobotoMono.json")
		end
	end

	if typeof(ds.Motifs) == "table" then
		local tm = UIKit.Tokens.Motifs :: any
		for k, v in pairs(ds.Motifs) do
			tm[k] = v
		end
	end

	local tContent = UIKit.Tokens.Content :: any
	if typeof(ds.Content) ~= "table" and typeof(ds.Meta) == "table" and typeof(ds.Meta.PresetId) == "string" and ds.Preset == nil then
		local metaPreset = (UIKit.Presets :: any)[ds.Meta.PresetId]
		if typeof(metaPreset) == "table" and typeof(metaPreset.Content) == "table" then
			for ck, cv in pairs(metaPreset.Content) do
				if ck == "HotbarSkills" and typeof(cv) == "table" then
					local prevSkills = if typeof(tContent.HotbarSkills) == "table" then tContent.HotbarSkills else {}
					local copied: { string } = {}
					for i = 1, 5 do
						local item = cv[i]
						copied[i] = if typeof(item) == "string" and item ~= ""
							then item
							elseif typeof(prevSkills[i]) == "string" and prevSkills[i] ~= ""
							then prevSkills[i]
							else ("Skill " .. tostring(i))
					end
					tContent.HotbarSkills = copied
				elseif cv ~= nil then
					tContent[ck] = cv
				end
			end
		end
	end

	if typeof(ds.Meta) == "table" then
		if typeof(ds.Meta.GameTitle) == "string" and ds.Meta.GameTitle ~= "" then
			tContent.GameTitle = ds.Meta.GameTitle
		end
		if typeof(ds.Meta.Genre) == "string" and ds.Meta.Genre ~= "" then
			tContent.Genre = ds.Meta.Genre
		end
		if typeof(ds.Meta.PresetId) == "string" and ds.Meta.PresetId ~= "" then
			tContent.PresetId = ds.Meta.PresetId
			if typeof(ds.Content) ~= "table" or ds.Content.OrnamentKind == nil then
				local mappedOrn = PRESET_ORNAMENT_MAP[ds.Meta.PresetId]
				if mappedOrn then
					tContent.OrnamentKind = mappedOrn
				end
			end
		end
	end

	if typeof(ds.Content) == "table" then
		for k, v in pairs(ds.Content) do
			if k == "HotbarSkills" and typeof(v) == "table" then
				local prevSkills = if typeof(tContent.HotbarSkills) == "table" then tContent.HotbarSkills else {}
				local skills: { string } = {}
				for i = 1, 5 do
					local item = v[i]
					if typeof(item) == "string" and item ~= "" then
						skills[i] = item
					elseif typeof(prevSkills[i]) == "string" and prevSkills[i] ~= "" then
						skills[i] = prevSkills[i]
					else
						skills[i] = "Skill " .. tostring(i)
					end
				end
				tContent.HotbarSkills = skills
			elseif v ~= nil then
				tContent[k] = v
			end
		end
		if typeof(ds.Content.PresetId) == "string" and ds.Content.OrnamentKind == nil then
			local mappedOrn = PRESET_ORNAMENT_MAP[ds.Content.PresetId]
			if mappedOrn then
				tContent.OrnamentKind = mappedOrn
			end
		end
	end

	if typeof(ds.MinTouchPx) == "number" then
		UIKit.Tokens.MinTouchPx = math.max(44, ds.MinTouchPx)
	end

	syncLiveStyleSheetTokens()
	return UIKit.Tokens
end

function UIKit.IsReducedMotion(): boolean
	local ok, val = pcall(function()
		return GuiService.ReducedMotionEnabled
	end)
	return ok and val == true
end

function UIKit.GetPreferredInput(): Enum.PreferredInput
	local ok, val = pcall(function()
		return UserInputService.PreferredInput
	end)
	if ok and val then
		return val
	end
	if UserInputService.TouchEnabled and not UserInputService.KeyboardEnabled then
		return Enum.PreferredInput.Touch
	end
	return Enum.PreferredInput.KeyboardAndMouse
end

function UIKit.GetDisplaySize(): Enum.DisplaySize
	local ok, val = pcall(function()
		return GuiService.ViewportDisplaySize
	end)
	if ok and val then
		return val
	end
	return Enum.DisplaySize.Medium
end

function UIKit.FormatNumber(n: number): string
	local rounded = math.floor(n + 0.5)
	if math.abs(rounded) >= 1000000 then
		return string.format("%.2fM", rounded / 1000000)
	end
	local formatted = tostring(rounded)
	local k = 1
	while k ~= 0 do
		formatted, k = string.gsub(formatted, "^(-?%d+)(%d%d%d)", "%1,%2")
	end
	return formatted
end

function UIKit.Tween(instance: Instance, tweenInfo: TweenInfo, props: { [string]: any }): Tween?
	if UIKit.IsReducedMotion() then
		local instAny = instance :: any
		for k, v in pairs(props) do
			pcall(function()
				instAny[k] = v
			end)
		end
		return nil
	end
	local tw = TweenService:Create(instance, tweenInfo, props)
	tw:Play()
	return tw
end

local function addRule(
	sheet: StyleSheet,
	selector: string,
	priority: number,
	props: { [string]: any },
	transitionInfo: TweenInfo?
): StyleRule
	local rule = Instance.new("StyleRule")
	rule.Name = selector:gsub("[^%w_]", "_")
	rule.Selector = selector
	rule.Priority = priority
	for k, v in pairs(props) do
		pcall(function()
			rule:SetProperty(k, v)
		end)
	end
	if transitionInfo then
		pcall(function()
			rule:SetDefaultPropertyTransition(transitionInfo)
		end)
	end
	rule.Parent = sheet
	if rule.SelectorError ~= "" then
		warn(string.format("[UIKit.BuildStyleSheet] SelectorError on '%s': %s", selector, rule.SelectorError))
	end
	return rule
end

-- Build layered StyleSheet architecture: TokensSheet -> ThemeSheet -> DesignSheet
function UIKit.BuildStyleSheet(parent: Instance?, tokenOverrides: { [string]: any }?): StyleSheet
	local targetParent = parent or game:GetService("ReplicatedStorage")
	local prev = targetParent:FindFirstChild("UIStyles")
	if prev then
		prev:Destroy()
	end

	local folder = Instance.new("Folder")
	folder.Name = "UIStyles"
	folder.Parent = targetParent

	local tokensSheet = Instance.new("StyleSheet")
	tokensSheet.Name = "TokensSheet"
	tokensSheet:SetAttribute("BgPanel", UIKit.Tokens.Colors.BgPanel)
	tokensSheet:SetAttribute("BgCard", UIKit.Tokens.Colors.BgCard)
	tokensSheet:SetAttribute("Primary", UIKit.Tokens.Colors.Primary)
	tokensSheet:SetAttribute("PrimaryHover", UIKit.Tokens.Colors.PrimaryHover)
	tokensSheet:SetAttribute("PrimaryPress", UIKit.Tokens.Colors.PrimaryPress)
	tokensSheet:SetAttribute("Secondary", UIKit.Tokens.Colors.Secondary)
	tokensSheet:SetAttribute("SecondaryHover", UIKit.Tokens.Colors.SecondaryHover)
	tokensSheet:SetAttribute("SecondaryPress", UIKit.Tokens.Colors.SecondaryPress)
	tokensSheet:SetAttribute("Accent", UIKit.Tokens.Colors.Accent)
	tokensSheet:SetAttribute("AccentHover", UIKit.Tokens.Colors.AccentHover)
	tokensSheet:SetAttribute("AccentPress", UIKit.Tokens.Colors.AccentPress)
	tokensSheet:SetAttribute("Danger", UIKit.Tokens.Colors.Danger)
	tokensSheet:SetAttribute("DangerHover", UIKit.Tokens.Colors.DangerHover)
	tokensSheet:SetAttribute("DangerPress", UIKit.Tokens.Colors.DangerPress)
	tokensSheet:SetAttribute("Success", UIKit.Tokens.Colors.Success)
	tokensSheet:SetAttribute("SuccessHover", UIKit.Tokens.Colors.SuccessHover)
	tokensSheet:SetAttribute("SuccessPress", UIKit.Tokens.Colors.SuccessPress)
	tokensSheet:SetAttribute("Warning", UIKit.Tokens.Colors.Warning)
	tokensSheet:SetAttribute("WarningHover", UIKit.Tokens.Colors.WarningHover)
	tokensSheet:SetAttribute("WarningPress", UIKit.Tokens.Colors.WarningPress)
	tokensSheet:SetAttribute("TextPrimary", UIKit.Tokens.Colors.TextPrimary)
	tokensSheet:SetAttribute("TextOnPrimary", UIKit.Tokens.Colors.TextOnPrimary)
	tokensSheet:SetAttribute("TextOnSecondary", UIKit.Tokens.Colors.TextOnSecondary)
	tokensSheet:SetAttribute("TextOnAccent", UIKit.Tokens.Colors.TextOnAccent)
	tokensSheet:SetAttribute("TextOnSuccess", UIKit.Tokens.Colors.TextOnSuccess)
	tokensSheet:SetAttribute("TextOnWarning", UIKit.Tokens.Colors.TextOnWarning)
	tokensSheet:SetAttribute("TextOnDanger", UIKit.Tokens.Colors.TextOnDanger)
	tokensSheet:SetAttribute("BorderSubtle", UIKit.Tokens.Colors.BorderSubtle)
	tokensSheet:SetAttribute("BorderBright", UIKit.Tokens.Colors.BorderBright)
	tokensSheet:SetAttribute("OutlineInk", UIKit.Tokens.Colors.OutlineInk)
	tokensSheet:SetAttribute("RadiusMd", UIKit.Tokens.Radii.Medium)
	tokensSheet:SetAttribute("RadiusPanel", UIKit.Tokens.Radii.Panel)
	tokensSheet:SetAttribute("RadiusButton", UIKit.Tokens.Radii.Button)
	tokensSheet:SetAttribute("RadiusBadge", UIKit.Tokens.Radii.Badge)
	if tokenOverrides then
		for k, v in pairs(tokenOverrides) do
			tokensSheet:SetAttribute(k, v)
		end
	end
	tokensSheet.Parent = folder

	local themeSheet = Instance.new("StyleSheet")
	themeSheet.Name = "ThemeSheet"
	themeSheet.Parent = folder

	local deriveTokens = Instance.new("StyleDerive")
	deriveTokens.Name = "DeriveTokens"
	deriveTokens.StyleSheet = tokensSheet
	deriveTokens.Priority = 1
	deriveTokens.Parent = themeSheet

	local hoverTween: TweenInfo? = if UIKit.IsReducedMotion()
		then nil
		else TweenInfo.new(0.14, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

	addRule(themeSheet, ".CardPanel", 10, {
		BackgroundColor3 = "$BgPanel",
		BorderSizePixel = 0,
	}, nil)
	addRule(themeSheet, ".CardPanel::UICorner", 10, {
		CornerRadius = "$RadiusPanel",
	}, nil)
	addRule(themeSheet, ".CardPanel::UIStroke", 10, {
		ApplyStrokeMode = Enum.ApplyStrokeMode.Border,
		Color = "$OutlineInk",
		Thickness = UIKit.Tokens.Strokes.Panel,
		Transparency = 0.08,
	}, nil)

	addRule(themeSheet, ".GlossyPanel", 12, {
		BackgroundColor3 = "$BgPanel",
		BorderSizePixel = 0,
	}, nil)
	addRule(themeSheet, ".GlossyPanel::UICorner", 12, {
		CornerRadius = "$RadiusPanel",
	}, nil)
	addRule(themeSheet, ".GlossyPanel::UIStroke", 12, {
		ApplyStrokeMode = Enum.ApplyStrokeMode.Border,
		Color = "$OutlineInk",
		Thickness = UIKit.Tokens.Strokes.Panel,
		Transparency = 0,
	}, nil)

	addRule(themeSheet, ".ButtonPrimary", 20, {
		BackgroundColor3 = "$Primary",
		TextColor3 = "$TextOnPrimary",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonPrimary:Hover", 21, {
		BackgroundColor3 = "$PrimaryHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonPrimary:Press", 22, {
		BackgroundColor3 = "$PrimaryPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonPrimary:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	addRule(themeSheet, ".ButtonSecondary", 20, {
		BackgroundColor3 = "$Secondary",
		TextColor3 = "$TextOnSecondary",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonSecondary:Hover", 21, {
		BackgroundColor3 = "$SecondaryHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonSecondary:Press", 22, {
		BackgroundColor3 = "$SecondaryPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonSecondary:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	addRule(themeSheet, ".ButtonAccent", 20, {
		BackgroundColor3 = "$Accent",
		TextColor3 = "$TextOnAccent",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonAccent:Hover", 21, {
		BackgroundColor3 = "$AccentHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonAccent:Press", 22, {
		BackgroundColor3 = "$AccentPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonAccent:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	addRule(themeSheet, ".ButtonDanger", 20, {
		BackgroundColor3 = "$Danger",
		TextColor3 = "$TextOnDanger",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonDanger:Hover", 21, {
		BackgroundColor3 = "$DangerHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonDanger:Press", 22, {
		BackgroundColor3 = "$DangerPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonDanger:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	addRule(themeSheet, ".ButtonSuccess", 20, {
		BackgroundColor3 = "$Success",
		TextColor3 = "$TextOnSuccess",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonSuccess:Hover", 21, {
		BackgroundColor3 = "$SuccessHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonSuccess:Press", 22, {
		BackgroundColor3 = "$SuccessPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonSuccess:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	addRule(themeSheet, ".ButtonWarning", 20, {
		BackgroundColor3 = "$Warning",
		TextColor3 = "$TextOnWarning",
		AutoButtonColor = false,
		BorderSizePixel = 0,
	}, hoverTween)
	addRule(themeSheet, ".ButtonWarning:Hover", 21, {
		BackgroundColor3 = "$WarningHover",
	}, hoverTween)
	addRule(themeSheet, ".ButtonWarning:Press", 22, {
		BackgroundColor3 = "$WarningPress",
	}, hoverTween)
	addRule(themeSheet, ".ButtonWarning:NonInteractable", 23, {
		BackgroundTransparency = 0.45,
	}, hoverTween)

	-- Desktop/default base rules (keep these properties unset on instances so StyleRules & @ queries win)
	addRule(themeSheet, "#SideRail", 35, {
		Size = UDim2.fromOffset(128, 286),
		Position = UDim2.fromOffset(10, 92),
	}, nil)
	addRule(themeSheet, "#RailLayout", 35, {
		FillDirection = Enum.FillDirection.Vertical,
	}, nil)
	addRule(themeSheet, ".RailBtn", 35, {
		Size = UDim2.fromOffset(124, 52),
	}, nil)
	addRule(themeSheet, ".RailTitle", 35, {
		Visible = true,
	}, nil)
	addRule(themeSheet, ".CompactHide", 35, {
		Visible = true,
	}, nil)
	addRule(themeSheet, ".KeybindPill", 35, {
		Visible = true,
	}, nil)

	-- Responsive built-in @ compound selectors & custom StyleQuery @CompactPhone >> descendant rules
	addRule(themeSheet, ".KeybindPill@PreferredInputTouch", 40, {
		Visible = false,
	}, nil)
	addRule(themeSheet, ".CompactHide@ViewportDisplaySizeSmall", 40, {
		Visible = false,
	}, nil)
	addRule(themeSheet, "@CompactPhone >> .CompactHide", 41, {
		Visible = false,
	}, nil)
	addRule(themeSheet, "@CompactPhone >> #SideRail", 41, {
		Size = UDim2.fromOffset(286, 54),
		Position = UDim2.fromOffset(10, 82),
	}, nil)
	addRule(themeSheet, "@CompactPhone >> #RailLayout", 41, {
		FillDirection = Enum.FillDirection.Horizontal,
	}, nil)
	addRule(themeSheet, "@CompactPhone >> .RailBtn", 41, {
		Size = UDim2.fromOffset(52, 52),
	}, nil)
	addRule(themeSheet, "@CompactPhone >> .RailTitle", 41, {
		Visible = false,
	}, nil)

	local designSheet = Instance.new("StyleSheet")
	designSheet.Name = "DesignSheet"
	designSheet.Parent = folder

	local deriveTheme = Instance.new("StyleDerive")
	deriveTheme.Name = "DeriveTheme"
	deriveTheme.StyleSheet = themeSheet
	deriveTheme.Priority = 2
	deriveTheme.Parent = designSheet

	return designSheet
end

function UIKit.AttachStyleLink(gui: Instance, styleSheet: StyleSheet): StyleLink
	local existing = gui:FindFirstChildOfClass("StyleLink")
	if existing then
		existing.StyleSheet = styleSheet
		return existing
	end
	local link = Instance.new("StyleLink")
	link.Name = "StyleLink"
	link.StyleSheet = styleSheet
	link.Parent = gui
	return link
end

function UIKit.EnsureMinTouchTarget(guiObj: GuiObject, minPx: number?): UISizeConstraint
	local px = math.max(UIKit.Tokens.MinTouchPx, minPx or UIKit.Tokens.MinTouchPx)
	local existing = guiObj:FindFirstChild("MinTouchConstraint")
	if existing and existing:IsA("UISizeConstraint") then
		existing.MinSize = Vector2.new(
			math.max(existing.MinSize.X, px),
			math.max(existing.MinSize.Y, px)
		)
		return existing
	end
	local constraint = Instance.new("UISizeConstraint")
	constraint.Name = "MinTouchConstraint"
	constraint.MinSize = Vector2.new(px, px)
	constraint.Parent = guiObj
	return constraint
end

function UIKit.CreateColorSequenceFromRecipe(recipeOrKey: any, fallbackBase: Color3?): (ColorSequence, number)
	local recipe: any = nil
	if typeof(recipeOrKey) == "string" then
		recipe = (UIKit.Tokens.Gradients :: any)[recipeOrKey]
	elseif typeof(recipeOrKey) == "table" then
		recipe = recipeOrKey
	end

	local rot = -38
	local rawStops: { { time: number, color: Color3 } } = {}
	if typeof(recipe) == "table" then
		if typeof(recipe.Rotation) == "number" then
			rot = recipe.Rotation
		end
		if typeof(recipe.Stops) == "table" then
			for _, st in ipairs(recipe.Stops) do
				if typeof(st) == "table" and typeof(st.color) == "Color3" then
					table.insert(rawStops, {
						time = math.clamp(tonumber(st.time) or 0, 0, 1),
						color = st.color,
					})
				end
			end
		end
	end

	if #rawStops < 2 then
		local base = fallbackBase or UIKit.Tokens.Colors.Primary
		rawStops = makeGlossyStops(base)
	end

	table.sort(rawStops, function(a, b)
		return a.time < b.time
	end)
	rawStops[1].time = 0
	rawStops[#rawStops].time = 1

	local keypoints: { ColorSequenceKeypoint } = {}
	local prevTime = -1
	for idx, st in ipairs(rawStops) do
		local t = st.time
		if idx == #rawStops then
			t = 1
		elseif t <= prevTime then
			t = math.min(0.999, prevTime + 0.001)
		end
		prevTime = t
		table.insert(keypoints, ColorSequenceKeypoint.new(t, st.color))
	end

	return ColorSequence.new(keypoints), rot
end

local function srgbToLinear(c: number): number
	if c <= 0.04045 then
		return c / 12.92
	end
	return ((c + 0.055) / 1.055) ^ 2.4
end

function UIKit.RelativeLuminance(col: Color3): number
	return 0.2126 * srgbToLinear(col.R)
		+ 0.7152 * srgbToLinear(col.G)
		+ 0.0722 * srgbToLinear(col.B)
end

function UIKit.AttachTextStroke(
	label: GuiObject,
	color: Color3?,
	thickness: number?,
	transparency: number?,
	textColorOverride: Color3?
): UIStroke
	local resolvedColor = color or UIKit.Tokens.Colors.OutlineInk
	local resolvedThickness = thickness or UIKit.Tokens.Strokes.Text
	local resolvedTransparency = transparency or 0.1

	local effTextColor: Color3? = textColorOverride
	if not effTextColor and (label:IsA("TextLabel") or label:IsA("TextButton") or label:IsA("TextBox")) then
		effTextColor = (label :: any).TextColor3
	end
	if effTextColor and typeof(effTextColor) == "Color3" then
		if UIKit.RelativeLuminance(effTextColor) < 0.35 and UIKit.RelativeLuminance(resolvedColor) < 0.35 then
			-- Dark text on bright pills/buttons blurs into dark blobs with thick dark strokes; switch to a crisp subtle light rim.
			resolvedColor = Color3.fromRGB(255, 255, 255)
			resolvedThickness = math.min(1.0, resolvedThickness * 0.45)
			resolvedTransparency = math.max(0.55, resolvedTransparency)
		end
	end

	local existing = label:FindFirstChild("TextStroke")
	if existing and existing:IsA("UIStroke") then
		existing.Color = resolvedColor
		existing.Thickness = resolvedThickness
		existing.Transparency = resolvedTransparency
		return existing
	end
	local stroke = Instance.new("UIStroke")
	stroke.Name = "TextStroke"
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Contextual
	stroke.Color = resolvedColor
	stroke.Thickness = resolvedThickness
	stroke.Transparency = resolvedTransparency
	stroke.LineJoinMode = UIKit.Tokens.Strokes.LineJoin
	stroke.Parent = label
	return stroke
end

export type StackedStrokeOptions = {
	OuterColor: Color3?,
	OuterThickness: number?,
	OuterTransparency: number?,
	InnerColor: Color3?,
	InnerThickness: number?,
	InnerTransparency: number?,
	LineJoin: Enum.LineJoinMode?,
	CornerRadius: UDim?,
}

function UIKit.AttachStackedStrokes(target: GuiObject, opts: StackedStrokeOptions?): (UIStroke, Instance)
	local o = opts or ({} :: StackedStrokeOptions)
	local targetCorner = target:FindFirstChildOfClass("UICorner")
	local resolvedRadius = o.CornerRadius or (if targetCorner then targetCorner.CornerRadius else UIKit.Tokens.Radii.Button)
	-- Roblox Miter joins on circular/pill UICorners draw solid bounding corner wedges; always use Round on circles/pills.
	local isCircular = (resolvedRadius.Scale >= 0.49 or resolvedRadius.Offset >= 24)
	local lineJoin = if isCircular then Enum.LineJoinMode.Round else (o.LineJoin or UIKit.Tokens.Strokes.LineJoin)

	local outer = Instance.new("UIStroke")
	outer.Name = "OuterStroke"
	outer.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	outer.Color = o.OuterColor or UIKit.Tokens.Colors.OutlineInk
	outer.Thickness = o.OuterThickness or UIKit.Tokens.Strokes.OuterInk
	outer.Transparency = if o.OuterTransparency ~= nil then o.OuterTransparency else 0
	outer.LineJoinMode = lineJoin
	pcall(function()
		local outerAny = outer :: any
		outerAny.BorderStrokePosition = if isCircular then Enum.BorderStrokePosition.Center else Enum.BorderStrokePosition.Outer
	end)
	outer.Parent = target

	local innerThickness = o.InnerThickness or UIKit.Tokens.Strokes.InnerHighlight
	local innerTrans = if o.InnerTransparency ~= nil then o.InnerTransparency else 0.45
	local innerColor = o.InnerColor or UIKit.Tokens.Colors.InnerHighlight

	local innerStrokeOk, innerStroke = pcall(function()
		local s = Instance.new("UIStroke")
		s.Name = "InnerStroke"
		s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		s.Color = innerColor
		s.Thickness = innerThickness
		s.Transparency = innerTrans
		s.LineJoinMode = lineJoin
		-- Will fail cleanly on channels where BorderStrokePosition is disabled so we avoid overlapping Center strokes
		local sAny = s :: any
		sAny.BorderStrokePosition = Enum.BorderStrokePosition.Inner
		s.Parent = target
		return s
	end)
	if innerStrokeOk and innerStroke then
		return outer, innerStroke
	end

	-- Fallback when Improved UIStrokes (BorderStrokePosition) is unavailable: inset highlight border Frame
	local inset = Instance.new("Frame")
	inset.Name = "InnerHighlight"
	inset.Size = UDim2.new(1, -4, 1, -4)
	inset.Position = UDim2.fromOffset(2, 2)
	inset.BackgroundTransparency = 1
	inset.BorderSizePixel = 0
	inset.ZIndex = math.max(1, target.ZIndex) + 1
	inset.Parent = target

	local existingCorner = target:FindFirstChildOfClass("UICorner")
	local radius = o.CornerRadius or (if existingCorner then existingCorner.CornerRadius else UIKit.Tokens.Radii.Button)
	local iCorner = Instance.new("UICorner")
	iCorner.CornerRadius = UDim.new(radius.Scale, math.max(0, radius.Offset - 2))
	iCorner.Parent = inset

	local iStroke = Instance.new("UIStroke")
	iStroke.Name = "InnerStroke"
	iStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	iStroke.Color = innerColor
	iStroke.Thickness = math.max(1, innerThickness * 0.85)
	iStroke.Transparency = math.min(0.65, innerTrans + 0.08)
	iStroke.LineJoinMode = lineJoin
	iStroke.Parent = inset

	return outer, inset
end

function UIKit.PickReadableTextColor(bgColor: Color3): Color3
	local lum = UIKit.RelativeLuminance(bgColor)
	local lightTxt = Color3.fromRGB(255, 253, 250)
	local darkTxt = Color3.fromRGB(22, 16, 30)
	local cLight = 1.05 / (lum + 0.05)
	local cDark = (lum + 0.05) / 0.062
	return if cLight >= cDark then lightTxt else darkTxt
end

local function tryAttachUIShadow(
	target: GuiObject,
	color: Color3,
	transparency: number,
	blurPx: number,
	ox: number,
	oy: number
): Instance?
	local created: Instance? = nil
	local ok, errOrInst = pcall(function()
		local s = Instance.new("UIShadow")
		created = s
		s.Name = "DropShadow"
		s.Color = color
		s.Transparency = transparency
		pcall(function()
			s.BlurRadius = UDim.new(0, blurPx)
		end)
		pcall(function()
			s.Offset = UDim2.fromOffset(ox, oy)
		end)
		pcall(function()
			local sAny = s :: any
			sAny.ShowBehindParent = true
		end)
		s.ZIndex = -1
		s.Parent = target
		return s
	end)
	if ok and errOrInst then
		return errOrInst
	end
	if created then
		local createdInst = created :: Instance
		pcall(function()
			createdInst:Destroy()
		end)
	end
	return nil
end

function UIKit.AttachDropShadow(
	parent: GuiObject,
	offsetY: number?,
	transparency: number?,
	color: Color3?,
	allowSiblingFallback: boolean?
): Instance?
	local ox = UIKit.Tokens.Shadows.OffsetX
	local oy = offsetY or UIKit.Tokens.Shadows.OffsetY
	local alpha = if transparency ~= nil then transparency else UIKit.Tokens.Shadows.Transparency
	local shadowColor = color or UIKit.Tokens.Shadows.Color
	local blurPx = UIKit.Tokens.Shadows.BlurRadius

	local shadow = tryAttachUIShadow(parent, shadowColor, alpha, blurPx, ox, oy)
	if shadow then
		return shadow
	end

	-- Fallback offset sibling Frame when parent is outside a UIGridStyleLayout
	local host = parent.Parent
	local hasLayout = host ~= nil and host:FindFirstChildWhichIsA("UIGridStyleLayout") ~= nil
	if allowSiblingFallback ~= false and host and (host:IsA("GuiObject") or host:IsA("LayerCollector")) and not hasLayout then
		local fbFrame = Instance.new("Frame")
		fbFrame.Name = parent.Name .. "_DropShadow"
		fbFrame.Size = parent.Size
		fbFrame.AnchorPoint = parent.AnchorPoint
		fbFrame.Position = UDim2.new(
			parent.Position.X.Scale,
			parent.Position.X.Offset + ox,
			parent.Position.Y.Scale,
			parent.Position.Y.Offset + oy
		)
		fbFrame.ZIndex = math.max(0, parent.ZIndex - 1)
		fbFrame.BackgroundColor3 = shadowColor
		fbFrame.BackgroundTransparency = math.clamp(alpha, 0.05, 0.75)
		fbFrame.BorderSizePixel = 0
		fbFrame.Visible = parent.Visible

		local existingCorner = parent:FindFirstChildOfClass("UICorner")
		if existingCorner then
			local c = Instance.new("UICorner")
			c.CornerRadius = existingCorner.CornerRadius
			c.Parent = fbFrame
		end

		fbFrame.Parent = host
		parent.Destroying:Connect(function()
			if fbFrame.Parent then
				fbFrame:Destroy()
			end
		end)
		parent:GetPropertyChangedSignal("Visible"):Connect(function()
			fbFrame.Visible = parent.Visible
		end)
		return fbFrame
	end

	-- Minimal fallback border shadow if inside a layout container without UIShadow
	local existingStroke = parent:FindFirstChildOfClass("UIStroke")
	if not existingStroke then
		local fb = Instance.new("UIStroke")
		fb.Name = "ShadowFallbackStroke"
		fb.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		fb.Color = shadowColor
		fb.Thickness = 3
		fb.Transparency = 0.45
		fb.Parent = parent
		return fb
	end
	return existingStroke
end

function UIKit.AttachShadow(parent: GuiObject, offsetY: number?, transparency: number?)
	return UIKit.AttachDropShadow(parent, offsetY, transparency, nil, true)
end

export type GlossySurfaceOptions = {
	GradientKey: string?,
	BaseColor: Color3?,
	CornerRadius: UDim?,
	StrokeColor: Color3?,
	StrokeThickness: number?,
	InnerHighlight: boolean?,
	MultiplyTint: boolean?,
}

function UIKit.ApplyGlossySurface(target: GuiObject, opts: GlossySurfaceOptions?)
	local o = opts or ({} :: GlossySurfaceOptions)
	local existingCorner = target:FindFirstChildOfClass("UICorner")
	local corner = existingCorner or Instance.new("UICorner")
	corner.CornerRadius = o.CornerRadius or UIKit.Tokens.Radii.Panel
	if not existingCorner then
		corner.Parent = target
	end

	local seq: ColorSequence
	local rot: number
	if o.MultiplyTint then
		seq = ColorSequence.new({
			ColorSequenceKeypoint.new(0.0, Color3.fromRGB(255, 255, 255)),
			ColorSequenceKeypoint.new(0.28, Color3.fromRGB(252, 252, 255)),
			ColorSequenceKeypoint.new(0.65, Color3.fromRGB(232, 236, 246)),
			ColorSequenceKeypoint.new(1.0, Color3.fromRGB(184, 192, 212)),
		})
		rot = -38
	else
		seq, rot = UIKit.CreateColorSequenceFromRecipe(o.GradientKey, o.BaseColor or target.BackgroundColor3)
		target.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	end

	local existingGrad = target:FindFirstChild("GlossGradient")
	local grad = if existingGrad and existingGrad:IsA("UIGradient") then existingGrad else Instance.new("UIGradient")
	grad.Name = "GlossGradient"
	grad.Rotation = rot
	grad.Color = seq
	grad.Parent = target

	if o.InnerHighlight ~= false then
		UIKit.AttachStackedStrokes(target, {
			OuterColor = o.StrokeColor or UIKit.Tokens.Colors.OutlineInk,
			OuterThickness = o.StrokeThickness or UIKit.Tokens.Strokes.Panel,
			CornerRadius = corner.CornerRadius,
		})
	else
		local outer = Instance.new("UIStroke")
		outer.Name = "OuterStroke"
		outer.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		outer.Color = o.StrokeColor or UIKit.Tokens.Colors.OutlineInk
		outer.Thickness = o.StrokeThickness or UIKit.Tokens.Strokes.Panel
		outer.LineJoinMode = if (corner.CornerRadius.Scale >= 0.49 or corner.CornerRadius.Offset >= 24) then Enum.LineJoinMode.Round else UIKit.Tokens.Strokes.LineJoin
		outer.Parent = target
	end
end

export type ShineSweepOptions = {
	Rotation: number?,
	Duration: number?,
	Delay: number?,
	Loop: boolean?,
	AutoPlay: boolean?,
	TriggerOnHover: GuiButton?,
	ZIndex: number?,
}

function UIKit.CreateShineSweep(target: GuiObject, opts: ShineSweepOptions?)
	local o = opts or ({} :: ShineSweepOptions)
	local dur = o.Duration or UIKit.Tokens.Gradients.ShineSweep.Duration
	local rot = o.Rotation or UIKit.Tokens.Gradients.ShineSweep.Rotation

	local container = Instance.new("Frame")
	container.Name = "ShineContainer"
	container.Size = UDim2.fromScale(1, 1)
	container.BackgroundTransparency = 1
	container.ClipsDescendants = true
	container.BorderSizePixel = 0
	container.ZIndex = o.ZIndex or math.max(4, target.ZIndex + 2)
	container.Parent = target

	local targetCorner = target:FindFirstChildOfClass("UICorner")
	if targetCorner then
		local c = Instance.new("UICorner")
		c.CornerRadius = targetCorner.CornerRadius
		c.Parent = container
	end

	local sweep = Instance.new("Frame")
	sweep.Name = "ShineSweep"
	sweep.Size = UDim2.fromScale(1, 1)
	sweep.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	sweep.BackgroundTransparency = 0
	sweep.BorderSizePixel = 0
	sweep.Parent = container

	local grad = Instance.new("UIGradient")
	grad.Name = "SweepGradient"
	grad.Rotation = rot
	grad.Offset = Vector2.new(-1.35, 0)
	grad.Color = ColorSequence.new(Color3.fromRGB(255, 255, 255))
	grad.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0.0, 1.0),
		NumberSequenceKeypoint.new(0.32, 0.96),
		NumberSequenceKeypoint.new(0.50, 0.45),
		NumberSequenceKeypoint.new(0.68, 0.96),
		NumberSequenceKeypoint.new(1.0, 1.0),
	})
	grad.Parent = sweep

	local activeTween: Tween? = nil
	local looping = false
	local lastTrigger = 0

	if UIKit.IsReducedMotion() then
		container.Visible = false
		return {
			Overlay = container,
			Play = function() end,
			Stop = function() end,
		}
	end

	local function playOnce()
		local now = os.clock()
		if now - lastTrigger < (dur * 0.6) then
			return
		end
		lastTrigger = now
		if activeTween then
			activeTween:Cancel()
		end
		grad.Offset = Vector2.new(-1.35, 0)
		local info = TweenInfo.new(dur, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut)
		activeTween = TweenService:Create(grad, info, { Offset = Vector2.new(1.35, 0) })
		if activeTween then
			activeTween:Play()
		end
	end

	if o.TriggerOnHover then
		o.TriggerOnHover.MouseEnter:Connect(playOnce)
	end

	if o.Loop then
		looping = true
		task.spawn(function()
			local delaySec = o.Delay or 2.8
			while looping and container.Parent ~= nil do
				if not UIKit.IsReducedMotion() then
					playOnce()
				end
				task.wait(dur + delaySec)
			end
		end)
	elseif o.AutoPlay then
		task.defer(playOnce)
	end

	container.AncestryChanged:Connect(function(_, newParent)
		if not newParent then
			looping = false
			if activeTween then
				activeTween:Cancel()
			end
		end
	end)

	return {
		Overlay = container,
		Play = playOnce,
		Stop = function()
			looping = false
			if activeTween then
				activeTween:Cancel()
			end
		end,
	}
end

export type SunburstOptions = {
	Color: Color3?,
	RayCount: number?,
	Transparency: number?,
	RotateSpeed: number?,
	ZIndex: number?,
}

function UIKit.CreateSunburstRays(parent: GuiObject, opts: SunburstOptions?): Frame
	local o = opts or ({} :: SunburstOptions)
	local count = math.clamp(o.RayCount or UIKit.Tokens.Motifs.RayCount or 12, 4, 20)
	local rayColor = o.Color or UIKit.Tokens.Colors.Gold
	local baseAlpha = if o.Transparency ~= nil then o.Transparency else 0.72

	local container = Instance.new("Frame")
	container.Name = "SunburstRays"
	container.Size = UDim2.fromScale(1, 1)
	container.BackgroundTransparency = 1
	container.ClipsDescendants = true
	container.BorderSizePixel = 0
	container.ZIndex = o.ZIndex or math.max(1, parent.ZIndex)
	container.Parent = parent

	local hub = Instance.new("Frame")
	hub.Name = "RayHub"
	hub.Size = UDim2.fromScale(1, 1)
	hub.Position = UDim2.fromScale(0.5, 0.5)
	hub.AnchorPoint = Vector2.new(0.5, 0.5)
	hub.BackgroundTransparency = 1
	hub.Parent = container

	for i = 1, count do
		local angle = (i - 1) * (360 / count)
		local ray = Instance.new("Frame")
		ray.Name = string.format("Ray_%02d", i)
		-- Keep rotated rays inside container bounds so layout/audit bounds stay clean
		ray.Size = UDim2.fromScale(0.76, 0.13)
		ray.Position = UDim2.fromScale(0.5, 0.5)
		ray.AnchorPoint = Vector2.new(0.5, 0.5)
		ray.Rotation = angle
		ray.BackgroundColor3 = rayColor
		ray.BackgroundTransparency = 0
		ray.BorderSizePixel = 0
		ray.Parent = hub

		local uig = Instance.new("UIGradient")
		uig.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0.0, 1.0),
			NumberSequenceKeypoint.new(0.28, baseAlpha),
			NumberSequenceKeypoint.new(0.50, math.max(0.45, baseAlpha - 0.12)),
			NumberSequenceKeypoint.new(0.72, baseAlpha),
			NumberSequenceKeypoint.new(1.0, 1.0),
		})
		uig.Parent = ray
	end

	local speed = o.RotateSpeed or 12
	if speed ~= 0 and RunService:IsRunning() and not UIKit.IsReducedMotion() then
		local conn: RBXScriptConnection? = nil
		conn = RunService.RenderStepped:Connect(function(dt: number)
			if not container.Parent or UIKit.IsReducedMotion() then
				if conn then
					conn:Disconnect()
					conn = nil
				end
				return
			end
			hub.Rotation = (hub.Rotation + speed * dt) % 360
		end)
		container.AncestryChanged:Connect(function(_, newParent)
			if not newParent and conn then
				conn:Disconnect()
				conn = nil
			end
		end)
	end

	return container
end

export type BadgePillOptions = {
	Name: string?,
	Parent: Instance?,
	Text: string,
	Color: Color3?,
	TextColor: Color3?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	Rotation: number?,
	TextSize: number?,
	ZIndex: number?,
}

function UIKit.CreateBadgePill(opts: BadgePillOptions): Frame
	local pill = Instance.new("Frame")
	pill.Name = opts.Name or "BadgePill"
	pill.Size = opts.Size or UDim2.fromOffset(78, 24)
	pill.Position = opts.Position or UDim2.new(1, -6, 0, -4)
	pill.AnchorPoint = opts.AnchorPoint or Vector2.new(1, 0)
	pill.Rotation = if opts.Rotation ~= nil then opts.Rotation else UIKit.Tokens.Motifs.BadgeRotation
	pill.BorderSizePixel = 0
	pill.ZIndex = opts.ZIndex or 8

	local baseColor = opts.Color or UIKit.Tokens.Colors.Accent
	UIKit.ApplyGlossySurface(pill, {
		BaseColor = baseColor,
		CornerRadius = UIKit.Tokens.Radii.Pill,
		StrokeColor = UIKit.Tokens.Colors.OutlineInk,
		StrokeThickness = math.max(2, UIKit.Tokens.Strokes.OuterInk * 0.65),
		InnerHighlight = false,
	})

	local lbl = Instance.new("TextLabel")
	lbl.Name = "Text"
	lbl.Size = UDim2.new(1, -10, 1, 0)
	lbl.Position = UDim2.fromOffset(5, 0)
	lbl.BackgroundTransparency = 1
	lbl.Text = opts.Text
	lbl.TextColor3 = opts.TextColor or UIKit.PickReadableTextColor(baseColor)
	lbl.TextSize = opts.TextSize or 11
	lbl.FontFace = UIKit.Tokens.Fonts.Title
	lbl.ZIndex = pill.ZIndex + 1
	lbl.Parent = pill
	UIKit.AttachTextStroke(lbl, UIKit.Tokens.Colors.OutlineInk, math.max(1.5, UIKit.Tokens.Strokes.Text * 0.8), 0.1)

	pill.Parent = opts.Parent
	return pill
end

-- Dedicated CanvasGroup container for fade-only modal transitions (stay <= 6 CanvasGroups total)
function UIKit.CreateModalFadeGroup(
	name: string?,
	parent: Instance?,
	size: UDim2?,
	position: UDim2?,
	anchorPoint: Vector2?
): CanvasGroup
	local group = Instance.new("CanvasGroup")
	group.Name = name or "ModalFadeGroup"
	group.Size = size or UDim2.fromScale(1, 1)
	group.Position = position or UDim2.fromScale(0.5, 0.5)
	group.AnchorPoint = anchorPoint or Vector2.new(0.5, 0.5)
	group.BackgroundTransparency = 1
	group.BorderSizePixel = 0
	group.GroupTransparency = 0
	group.Parent = parent
	return group
end

function UIKit.AttachButtonJuice(button: GuiButton, visualTarget: GuiObject?, onActivate: (() -> ())?)
	local target = visualTarget or button
	local scale = target:FindFirstChild("JuiceScale") :: UIScale?
	if not scale then
		local newScale = Instance.new("UIScale")
		newScale.Name = "JuiceScale"
		newScale.Scale = 1
		newScale.Parent = target
		scale = newScale
	end
	local uiScale = scale :: UIScale
	local fastTween = TweenInfo.new(0.11, Enum.EasingStyle.Back, Enum.EasingDirection.Out)

	button.MouseEnter:Connect(function()
		UIKit.Tween(uiScale, fastTween, { Scale = 1.03 })
	end)
	button.MouseLeave:Connect(function()
		UIKit.Tween(uiScale, fastTween, { Scale = 1.0 })
	end)
	button.MouseButton1Down:Connect(function()
		UIKit.Tween(uiScale, TweenInfo.new(0.07, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { Scale = 0.96 })
	end)
	button.MouseButton1Up:Connect(function()
		UIKit.Tween(uiScale, fastTween, { Scale = 1.02 })
	end)
	button.Activated:Connect(function()
		if onActivate then
			onActivate()
		end
	end)
end

function UIKit.AttachPresetOrnament(target: GuiObject, ornamentKind: string?): Instance?
	if target:FindFirstChildWhichIsA("UIGridStyleLayout") ~= nil then
		return nil
	end

	local existing = target:FindFirstChild("PresetOrnament")
	if existing then
		existing:Destroy()
	end

	local resolvedKind = ornamentKind
	if not resolvedKind or resolvedKind == "" then
		local tContent = UIKit.Tokens.Content :: any
		resolvedKind = if typeof(tContent) == "table" and typeof(tContent.OrnamentKind) == "string" and tContent.OrnamentKind ~= ""
			then tContent.OrnamentKind
			else (PRESET_ORNAMENT_MAP[UIKit.Tokens.Meta.PresetId] or "arcane_filigree")
	end

	local c = UIKit.Tokens.Colors
	local container = Instance.new("Frame")
	container.Name = "PresetOrnament"
	container.Size = UDim2.fromScale(1, 1)
	container.Position = UDim2.fromOffset(0, 0)
	container.BackgroundTransparency = 1
	container.BorderSizePixel = 0
	container.ClipsDescendants = true
	container.Active = false
	container.Selectable = false
	container.ZIndex = 0
	container:SetAttribute("OrnamentKind", resolvedKind)

	local existingCorner = target:FindFirstChildOfClass("UICorner")
	if existingCorner then
		local cnr = Instance.new("UICorner")
		cnr.Name = "Corner"
		cnr.CornerRadius = existingCorner.CornerRadius
		cnr.Parent = container
	end

	local function makeDecor(
		name: string,
		size: UDim2,
		pos: UDim2,
		anchor: Vector2,
		color: Color3,
		trans: number,
		rot: number?
	): Frame
		local f = Instance.new("Frame")
		f.Name = name
		f.Size = size
		f.Position = pos
		f.AnchorPoint = anchor
		f.BackgroundColor3 = color
		f.BackgroundTransparency = trans
		f.BorderSizePixel = 0
		f.Rotation = rot or 0
		f.Active = false
		f.Selectable = false
		f.ZIndex = 0
		f.Parent = container
		return f
	end

	if resolvedKind == "holo_brackets" then
		local bracketColor = c.BorderBright
		local accentColor = c.Accent
		makeDecor("BracketTL_H", UDim2.fromOffset(10, 2), UDim2.fromOffset(4, 4), Vector2.new(0, 0), bracketColor, 0.12)
		makeDecor("BracketTL_V", UDim2.fromOffset(2, 10), UDim2.fromOffset(4, 4), Vector2.new(0, 0), bracketColor, 0.12)
		makeDecor("BracketTR_H", UDim2.fromOffset(10, 2), UDim2.new(1, -4, 0, 4), Vector2.new(1, 0), bracketColor, 0.12)
		makeDecor("BracketTR_V", UDim2.fromOffset(2, 10), UDim2.new(1, -4, 0, 4), Vector2.new(1, 0), bracketColor, 0.12)
		makeDecor("BracketBL_H", UDim2.fromOffset(10, 2), UDim2.new(0, 4, 1, -4), Vector2.new(0, 1), bracketColor, 0.12)
		makeDecor("BracketBL_V", UDim2.fromOffset(2, 10), UDim2.new(0, 4, 1, -4), Vector2.new(0, 1), bracketColor, 0.12)
		makeDecor("BracketBR_H", UDim2.fromOffset(10, 2), UDim2.new(1, -4, 1, -4), Vector2.new(1, 1), bracketColor, 0.12)
		makeDecor("BracketBR_V", UDim2.fromOffset(2, 10), UDim2.new(1, -4, 1, -4), Vector2.new(1, 1), bracketColor, 0.12)
		makeDecor("HoloTickTL", UDim2.fromOffset(4, 2), UDim2.fromOffset(16, 4), Vector2.new(0, 0), accentColor, 0.25)
		makeDecor("HoloTickBR", UDim2.fromOffset(4, 2), UDim2.new(1, -16, 1, -4), Vector2.new(1, 1), accentColor, 0.25)
		makeDecor("HoloTopScan", UDim2.new(0.28, 0, 0, 1), UDim2.new(0.5, 0, 0, 4), Vector2.new(0.5, 0), accentColor, 0.55)
	elseif resolvedKind == "cyber_slash" then
		local s1 = makeDecor("SlashTL_Main", UDim2.fromOffset(24, 3), UDim2.fromOffset(20, 9), Vector2.new(0.5, 0.5), c.Accent, 0.16, -18)
		local g1 = Instance.new("UIGradient")
		g1.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.05),
			NumberSequenceKeypoint.new(0.7, 0.15),
			NumberSequenceKeypoint.new(1, 0.85),
		})
		g1.Parent = s1
		makeDecor("SlashTL_Sub", UDim2.fromOffset(14, 2), UDim2.fromOffset(24, 14), Vector2.new(0.5, 0.5), c.Primary, 0.24, -18)

		local s2 = makeDecor("SlashBR_Main", UDim2.fromOffset(24, 3), UDim2.new(1, -20, 1, -9), Vector2.new(0.5, 0.5), c.Primary, 0.16, -18)
		local g2 = Instance.new("UIGradient")
		g2.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.85),
			NumberSequenceKeypoint.new(0.3, 0.15),
			NumberSequenceKeypoint.new(1, 0.05),
		})
		g2.Parent = s2
		makeDecor("SlashBR_Sub", UDim2.fromOffset(14, 2), UDim2.new(1, -24, 1, -14), Vector2.new(0.5, 0.5), c.Accent, 0.24, -18)
	elseif resolvedKind == "bubble_shine" then
		local sheen = makeDecor("GlossPillTL", UDim2.new(0.32, 0, 0, 5), UDim2.fromOffset(10, 5), Vector2.new(0, 0), c.InnerHighlight, 0.60)
		local sc = Instance.new("UICorner")
		sc.CornerRadius = UDim.new(1, 0)
		sc.Parent = sheen
		local sg = Instance.new("UIGradient")
		sg.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.0),
			NumberSequenceKeypoint.new(0.65, 0.25),
			NumberSequenceKeypoint.new(1, 1.0),
		})
		sg.Parent = sheen

		local d1 = makeDecor("SpecularDotA", UDim2.fromOffset(6, 6), UDim2.new(1, -14, 0, 6), Vector2.new(0.5, 0), c.InnerHighlight, 0.56)
		local c1 = Instance.new("UICorner")
		c1.CornerRadius = UDim.new(1, 0)
		c1.Parent = d1

		local d2 = makeDecor("SpecularDotB", UDim2.fromOffset(4, 4), UDim2.new(1, -23, 0, 8), Vector2.new(0.5, 0), c.InnerHighlight, 0.66)
		local c2 = Instance.new("UICorner")
		c2.CornerRadius = UDim.new(1, 0)
		c2.Parent = d2
	elseif resolvedKind == "comic_stripe" then
		local stripe1 = makeDecor("ComicRibbonTR", UDim2.fromOffset(22, 5), UDim2.new(1, -20, 0, 10), Vector2.new(0.5, 0.5), c.Accent, 0.14, -16)
		local st1 = Instance.new("UIStroke")
		st1.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		st1.Color = c.OutlineInk
		st1.Thickness = 1.4
		st1.Transparency = 0.15
		st1.Parent = stripe1

		makeDecor("ComicRibbonTR_Sub", UDim2.fromOffset(12, 3), UDim2.new(1, -15, 0, 16), Vector2.new(0.5, 0.5), c.Primary, 0.20, -16)
		makeDecor("ComicRibbonBL", UDim2.fromOffset(14, 4), UDim2.new(0, 16, 1, -9), Vector2.new(0.5, 0.5), c.Accent, 0.24, -16)
	elseif resolvedKind == "stitched_warm" then
		local inset = makeDecor("WarmInsetBorder", UDim2.new(1, -10, 1, -10), UDim2.fromOffset(5, 5), Vector2.new(0, 0), c.Gold, 1)
		local insetCorner = Instance.new("UICorner")
		local baseR = if existingCorner then existingCorner.CornerRadius else UIKit.Tokens.Radii.Panel
		insetCorner.CornerRadius = UDim.new(baseR.Scale, math.max(0, baseR.Offset - 4))
		insetCorner.Parent = inset
		local insetStroke = Instance.new("UIStroke")
		insetStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		insetStroke.Color = c.Gold
		insetStroke.Thickness = 1.2
		insetStroke.Transparency = 0.58
		insetStroke.Parent = inset

		local function makeStitch(sName: string, pos: UDim2, anchor: Vector2, col: Color3)
			local st = makeDecor(sName, UDim2.fromOffset(7, 2), pos, anchor, col, 0.45)
			local sc = Instance.new("UICorner")
			sc.CornerRadius = UDim.new(1, 0)
			sc.Parent = st
		end
		makeStitch("StitchTL", UDim2.fromOffset(14, 4), Vector2.new(0, 0), c.InnerHighlight)
		makeStitch("StitchTR", UDim2.new(1, -14, 0, 4), Vector2.new(1, 0), c.Gold)
		makeStitch("StitchBL", UDim2.new(0, 14, 1, -4), Vector2.new(0, 1), c.Gold)
		makeStitch("StitchBR", UDim2.new(1, -14, 1, -4), Vector2.new(1, 1), c.InnerHighlight)
	else
		-- "arcane_filigree" (default)
		makeDecor("DiamondTL", UDim2.fromOffset(6, 6), UDim2.fromOffset(8, 8), Vector2.new(0.5, 0.5), c.Gold, 0.18, 45)
		makeDecor("DiamondTR", UDim2.fromOffset(6, 6), UDim2.new(1, -8, 0, 8), Vector2.new(0.5, 0.5), c.Accent, 0.24, 45)
		makeDecor("DiamondBL", UDim2.fromOffset(6, 6), UDim2.new(0, 8, 1, -8), Vector2.new(0.5, 0.5), c.Accent, 0.24, 45)
		makeDecor("DiamondBR", UDim2.fromOffset(6, 6), UDim2.new(1, -8, 1, -8), Vector2.new(0.5, 0.5), c.Gold, 0.18, 45)
		makeDecor("FiligreeTop", UDim2.new(1, -30, 0, 1), UDim2.fromOffset(15, 7), Vector2.new(0, 0), c.Gold, 0.58)
		makeDecor("FiligreeBottom", UDim2.new(1, -30, 0, 1), UDim2.new(0, 15, 1, -8), Vector2.new(0, 0), c.Gold, 0.58)
	end

	container.Parent = target
	return container
end

export type PanelOptions = {
	Name: string?,
	Parent: Instance?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	BackgroundColor3: Color3?,
	BackgroundTransparency: number?,
	CornerRadius: UDim?,
	StrokeColor: Color3?,
	StrokeThickness: number?,
	Use9Slice: boolean?,
	AddShadow: boolean?,
	Glossy: boolean?,
	NoOrnament: boolean?,
}

function UIKit.CreatePanel(opts: PanelOptions): GuiObject
	local assets = UIKit.Assets
	if opts.Use9Slice and assets.Panel9SliceId and assets.Panel9SliceCenter then
		local img = Instance.new("ImageLabel")
		img.Name = opts.Name or "Panel"
		img.Size = opts.Size or UDim2.fromOffset(320, 240)
		img.Position = opts.Position or UDim2.fromScale(0.5, 0.5)
		img.AnchorPoint = opts.AnchorPoint or Vector2.new(0.5, 0.5)
		img.BackgroundTransparency = 1
		img.Image = assets.Panel9SliceId
		img.ScaleType = Enum.ScaleType.Slice
		img.SliceCenter = assets.Panel9SliceCenter
		img.SliceScale = assets.PanelSliceScale or 0.22
		if opts.NoOrnament ~= true then
			UIKit.AttachPresetOrnament(img)
		end
		img.Parent = opts.Parent
		return img
	end

	local frame = Instance.new("Frame")
	frame.Name = opts.Name or "Panel"
	frame.Size = opts.Size or UDim2.fromOffset(320, 240)
	frame.Position = opts.Position or UDim2.fromScale(0.5, 0.5)
	frame.AnchorPoint = opts.AnchorPoint or Vector2.new(0.5, 0.5)
	frame.BackgroundColor3 = opts.BackgroundColor3 or UIKit.Tokens.Colors.BgPanel
	frame.BackgroundTransparency = if opts.BackgroundTransparency ~= nil then opts.BackgroundTransparency else 0.04
	frame.BorderSizePixel = 0

	local radius = opts.CornerRadius or UIKit.Tokens.Radii.Panel
	local corner = Instance.new("UICorner")
	corner.Name = "Corner"
	corner.CornerRadius = radius
	corner.Parent = frame

	if opts.Glossy ~= false and opts.BackgroundColor3 == nil then
		local seq, rot = UIKit.CreateColorSequenceFromRecipe("Panel", UIKit.Tokens.Colors.BgPanel)
		frame.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
		local pGrad = Instance.new("UIGradient")
		pGrad.Name = "SurfaceGradient"
		pGrad.Rotation = rot
		pGrad.Color = seq
		pGrad.Parent = frame
	end

	UIKit.AttachStackedStrokes(frame, {
		OuterColor = opts.StrokeColor or UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = opts.StrokeThickness or UIKit.Tokens.Strokes.Panel,
		InnerTransparency = 0.72,
		CornerRadius = radius,
	})

	if opts.NoOrnament ~= true then
		UIKit.AttachPresetOrnament(frame)
	end

	frame.Parent = opts.Parent
	if opts.AddShadow then
		UIKit.AttachDropShadow(frame, UIKit.Tokens.Shadows.OffsetY + 2, UIKit.Tokens.Shadows.Transparency, nil, true)
	end

	return frame
end

export type ButtonOptions = {
	Name: string?,
	Parent: Instance?,
	Text: string?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	LayoutOrder: number?,
	Variant: ("Primary" | "Secondary" | "Accent" | "Success" | "Warning" | "Danger")?,
	Color: Color3?,
	TextColor: Color3?,
	TextSize: number?,
	Use9Slice: boolean?,
	OnClick: (() -> ())?,
}

function UIKit.CreateButton(opts: ButtonOptions): GuiButton
	local variant = opts.Variant or "Primary"
	local variantColors = {
		Primary = UIKit.Tokens.Colors.Primary,
		Secondary = UIKit.Tokens.Colors.Secondary,
		Accent = UIKit.Tokens.Colors.Accent,
		Success = UIKit.Tokens.Colors.Success,
		Warning = UIKit.Tokens.Colors.Warning,
		Danger = UIKit.Tokens.Colors.Danger,
	}
	local variantTextColors = {
		Primary = UIKit.Tokens.Colors.TextOnPrimary,
		Secondary = UIKit.Tokens.Colors.TextOnSecondary,
		Accent = UIKit.Tokens.Colors.TextOnAccent,
		Success = UIKit.Tokens.Colors.TextOnSuccess,
		Warning = UIKit.Tokens.Colors.TextOnWarning,
		Danger = UIKit.Tokens.Colors.TextOnDanger,
	}
	local fillColor = opts.Color or variantColors[variant] or UIKit.Tokens.Colors.Primary
	local defaultText = variantTextColors[variant] or UIKit.Tokens.Colors.TextPrimary
	local textColor = opts.TextColor or (if opts.Color ~= nil then UIKit.PickReadableTextColor(fillColor) else defaultText)
	local assets = UIKit.Assets

	if opts.Use9Slice and assets.Button9SliceId and assets.Button9SliceCenter then
		local imgBtn = Instance.new("ImageButton")
		imgBtn.Name = opts.Name or "ActionButton"
		imgBtn.Size = opts.Size or UDim2.fromOffset(140, 52)
		imgBtn.Position = opts.Position or UDim2.new()
		imgBtn.AnchorPoint = opts.AnchorPoint or Vector2.zero
		imgBtn.LayoutOrder = opts.LayoutOrder or 0
		imgBtn.BackgroundTransparency = 1
		imgBtn.Image = assets.Button9SliceId
		imgBtn.ImageColor3 = fillColor
		imgBtn.ScaleType = Enum.ScaleType.Slice
		imgBtn.SliceCenter = assets.Button9SliceCenter
		imgBtn.SliceScale = assets.ButtonSliceScale or 0.32
		imgBtn.AutoButtonColor = false

		local lbl = Instance.new("TextLabel")
		lbl.Name = "Label"
		lbl.Size = UDim2.new(1, -16, 1, 0)
		lbl.Position = UDim2.fromOffset(8, 0)
		lbl.BackgroundTransparency = 1
		lbl.Text = opts.Text or "Action"
		lbl.TextColor3 = textColor
		lbl.TextSize = opts.TextSize or 15
		lbl.FontFace = UIKit.Tokens.Fonts.Heading
		lbl.Parent = imgBtn
		UIKit.AttachTextStroke(lbl)

		UIKit.EnsureMinTouchTarget(imgBtn)
		UIKit.AttachButtonJuice(imgBtn, imgBtn, opts.OnClick)
		imgBtn.Parent = opts.Parent
		return imgBtn
	end

	local btn = Instance.new("TextButton")
	btn.Name = opts.Name or "ActionButton"
	btn.Size = opts.Size or UDim2.fromOffset(140, 52)
	btn.Position = opts.Position or UDim2.new()
	btn.AnchorPoint = opts.AnchorPoint or Vector2.zero
	btn.LayoutOrder = opts.LayoutOrder or 0
	-- Leave BackgroundColor3 unmodified only when an ancestor StyleLink binds UIStyles so :Hover/:Press apply.
	local hasStyleLink = false
	local curAnc: Instance? = opts.Parent
	while curAnc do
		if curAnc:FindFirstChildOfClass("StyleLink") ~= nil then
			hasStyleLink = true
			break
		end
		curAnc = curAnc.Parent
	end
	if opts.Color ~= nil or ReplicatedStorage:FindFirstChild("UIStyles") == nil or not hasStyleLink then
		btn.BackgroundColor3 = fillColor
		btn.TextColor3 = textColor
	end
	btn.Text = opts.Text or "Action"
	btn.TextSize = opts.TextSize or 15
	btn.FontFace = UIKit.Tokens.Fonts.Heading
	btn.AutoButtonColor = false
	btn.BorderSizePixel = 0

	local variantTag = if variantColors[variant] then ("Button" .. variant) else "ButtonPrimary"
	CollectionService:AddTag(btn, variantTag)

	local corner = Instance.new("UICorner")
	corner.Name = "Corner"
	corner.CornerRadius = UIKit.Tokens.Radii.Button
	corner.Parent = btn

	UIKit.AttachStackedStrokes(btn, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = math.max(2.5, UIKit.Tokens.Strokes.OuterInk * 0.8),
		InnerTransparency = 0.45,
		CornerRadius = UIKit.Tokens.Radii.Button,
	})
	UIKit.AttachTextStroke(btn, UIKit.Tokens.Colors.OutlineInk, UIKit.Tokens.Strokes.Text * 0.85, 0.15, textColor)

	local grad = Instance.new("UIGradient")
	grad.Name = "Highlight"
	grad.Rotation = -38
	grad.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0.0, Color3.fromRGB(255, 255, 255)),
		ColorSequenceKeypoint.new(0.28, Color3.fromRGB(250, 252, 255)),
		ColorSequenceKeypoint.new(0.66, Color3.fromRGB(232, 236, 246)),
		ColorSequenceKeypoint.new(1.0, Color3.fromRGB(184, 192, 212)),
	})
	grad.Parent = btn

	UIKit.EnsureMinTouchTarget(btn)
	UIKit.AttachButtonJuice(btn, btn, opts.OnClick)
	btn.Parent = opts.Parent
	return btn
end

export type GlossyButtonOptions = {
	Name: string?,
	Parent: Instance?,
	Text: string?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	LayoutOrder: number?,
	Variant: ("Primary" | "Secondary" | "Accent" | "Success" | "Warning" | "Danger" | "Gold")?,
	Color: Color3?,
	TextColor: Color3?,
	TextSize: number?,
	CornerRadius: UDim?,
	IconKey: string?,
	IconFallback: string?,
	EnableShine: boolean?,
	ZIndex: number?,
	OnClick: (() -> ())?,
}

function UIKit.CreateGlossyButton(opts: GlossyButtonOptions): GuiButton
	local variant = opts.Variant or "Primary"
	local variantColors: { [string]: Color3 } = {
		Primary = UIKit.Tokens.Colors.Primary,
		Secondary = UIKit.Tokens.Colors.Secondary,
		Accent = UIKit.Tokens.Colors.Accent,
		Success = UIKit.Tokens.Colors.Success,
		Warning = UIKit.Tokens.Colors.Warning,
		Danger = UIKit.Tokens.Colors.Danger,
		Gold = UIKit.Tokens.Colors.Gold,
	}
	local variantTextColors: { [string]: Color3 } = {
		Primary = UIKit.Tokens.Colors.TextOnPrimary,
		Secondary = UIKit.Tokens.Colors.TextOnSecondary,
		Accent = UIKit.Tokens.Colors.TextOnAccent,
		Success = UIKit.Tokens.Colors.TextOnSuccess,
		Warning = UIKit.Tokens.Colors.TextOnWarning,
		Danger = UIKit.Tokens.Colors.TextOnDanger,
		Gold = UIKit.Tokens.Colors.TextOnWarning,
	}
	local fillColor = opts.Color or variantColors[variant] or UIKit.Tokens.Colors.Primary
	local defaultText = variantTextColors[variant] or UIKit.Tokens.Colors.TextPrimary
	local textColor = opts.TextColor or (if opts.Color ~= nil then UIKit.PickReadableTextColor(fillColor) else defaultText)
	local radius = opts.CornerRadius or UIKit.Tokens.Radii.Button
	local sx = UIKit.Tokens.Shadows.OffsetX
	local sy = math.max(3, UIKit.Tokens.Shadows.OffsetY)
	local pressY = math.clamp(UIKit.Tokens.Shadows.PressOffsetY, 2, sy)
	local baseZ = opts.ZIndex or 2

	local root = Instance.new("TextButton")
	root.Name = opts.Name or "GlossyButton"
	root.Size = opts.Size or UDim2.fromOffset(168, 54)
	root.Position = opts.Position or UDim2.new()
	root.AnchorPoint = opts.AnchorPoint or Vector2.zero
	root.LayoutOrder = opts.LayoutOrder or 0
	root.BackgroundTransparency = 1
	root.Text = ""
	root.AutoButtonColor = false
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	UIKit.EnsureMinTouchTarget(root, 44)

	local faceSize = UDim2.new(1, -math.abs(sx), 1, -sy)
	local faceRestPos = UDim2.fromOffset(0, 0)
	local shadowRestPos = UDim2.fromOffset(sx, sy)

	local dropShadow = Instance.new("Frame")
	dropShadow.Name = "DropShadow"
	dropShadow.Size = faceSize
	dropShadow.Position = shadowRestPos
	dropShadow.BackgroundColor3 = UIKit.Tokens.Shadows.Color
	dropShadow.BackgroundTransparency = math.clamp(UIKit.Tokens.Shadows.Transparency, 0.05, 0.55)
	dropShadow.BorderSizePixel = 0
	dropShadow.ZIndex = baseZ
	dropShadow.Parent = root

	local dCorner = Instance.new("UICorner")
	dCorner.CornerRadius = radius
	dCorner.Parent = dropShadow

	local face = Instance.new("Frame")
	face.Name = "Face"
	face.Size = faceSize
	face.Position = faceRestPos
	face.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	face.BorderSizePixel = 0
	face.ZIndex = baseZ + 1
	face.Parent = root

	local fCorner = Instance.new("UICorner")
	fCorner.CornerRadius = radius
	fCorner.Parent = face

	local recipeKey: any = if opts.Color ~= nil then nil else variant
	local seq, rot = UIKit.CreateColorSequenceFromRecipe(recipeKey, fillColor)
	local grad = Instance.new("UIGradient")
	grad.Name = "GlossGradient"
	grad.Rotation = rot
	grad.Color = seq
	grad.Parent = face

	UIKit.AttachStackedStrokes(face, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = UIKit.Tokens.Strokes.OuterInk,
		InnerColor = UIKit.Tokens.Colors.InnerHighlight,
		InnerThickness = UIKit.Tokens.Strokes.InnerHighlight,
		InnerTransparency = 0.40,
		CornerRadius = radius,
	})

	-- Try native UIShadow on Face; keep internal DropShadow visible only if UIShadow fails
	local uiShadow = tryAttachUIShadow(
		face,
		UIKit.Tokens.Shadows.Color,
		UIKit.Tokens.Shadows.Transparency,
		UIKit.Tokens.Shadows.BlurRadius,
		sx,
		sy
	)
	if uiShadow then
		dropShadow.Visible = false
	end

	local shineCtrl = nil
	if opts.EnableShine ~= false then
		shineCtrl = UIKit.CreateShineSweep(face, {
			TriggerOnHover = root,
			ZIndex = baseZ + 3,
		})
	end

	local labelLeftOffset = 12
	if opts.IconKey or opts.IconFallback then
		local icon = UIKit.CreateBadgeIcon(face, opts.IconKey or "", opts.IconFallback or "*", fillColor, 26)
		icon.Position = UDim2.new(0, 12, 0.5, 0)
		icon.AnchorPoint = Vector2.new(0, 0.5)
		icon.ZIndex = baseZ + 4
		labelLeftOffset = 44
	end

	local lbl = Instance.new("TextLabel")
	lbl.Name = "Label"
	lbl.Size = UDim2.new(1, -(labelLeftOffset + 12), 1, 0)
	lbl.Position = UDim2.fromOffset(labelLeftOffset, 0)
	lbl.BackgroundTransparency = 1
	lbl.Text = opts.Text or "Action"
	lbl.TextColor3 = textColor
	lbl.TextSize = opts.TextSize or 16
	lbl.FontFace = UIKit.Tokens.Fonts.Heading
	lbl.ZIndex = baseZ + 5
	lbl.Parent = face
	UIKit.AttachTextStroke(lbl, UIKit.Tokens.Colors.OutlineInk, UIKit.Tokens.Strokes.Text, 0.1)

	local scale = Instance.new("UIScale")
	scale.Name = "JuiceScale"
	scale.Scale = 1
	scale.Parent = root

	local hoverInfo = TweenInfo.new(0.11, Enum.EasingStyle.Back, Enum.EasingDirection.Out)
	local pressInfo = TweenInfo.new(0.06, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
	local pressedPos = UDim2.fromOffset(math.min(sx, 2), pressY)

	root.MouseEnter:Connect(function()
		UIKit.Tween(scale, hoverInfo, { Scale = 1.03 })
	end)
	root.MouseLeave:Connect(function()
		UIKit.Tween(scale, hoverInfo, { Scale = 1.0 })
		UIKit.Tween(face, pressInfo, { Position = faceRestPos, BackgroundColor3 = Color3.fromRGB(255, 255, 255) })
	end)
	root.MouseButton1Down:Connect(function()
		if UIKit.IsReducedMotion() then
			face.Position = pressedPos
			face.BackgroundColor3 = Color3.fromRGB(224, 224, 232)
			return
		end
		UIKit.Tween(face, pressInfo, { Position = pressedPos, BackgroundColor3 = Color3.fromRGB(224, 224, 232) })
		UIKit.Tween(scale, pressInfo, { Scale = 0.97 })
	end)
	root.MouseButton1Up:Connect(function()
		UIKit.Tween(face, hoverInfo, { Position = faceRestPos, BackgroundColor3 = Color3.fromRGB(255, 255, 255) })
		UIKit.Tween(scale, hoverInfo, { Scale = 1.02 })
	end)
	root.Activated:Connect(function()
		if shineCtrl then
			shineCtrl.Play()
		end
		if opts.OnClick then
			opts.OnClick()
		end
	end)

	root.Parent = opts.Parent
	return root
end

export type GlossyPanelOptions = {
	Name: string?,
	Parent: Instance?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	Title: string?,
	HeaderColor: Color3?,
	CornerRadius: UDim?,
	StrokeColor: Color3?,
	ShowRays: boolean?,
	ShowClose: boolean?,
	ZIndex: number?,
	NoOrnament: boolean?,
}

function UIKit.CreateGlossyPanel(opts: GlossyPanelOptions)
	local radius = opts.CornerRadius or UIKit.Tokens.Radii.Panel
	local sy = math.max(4, UIKit.Tokens.Shadows.OffsetY + 1)
	local sx = UIKit.Tokens.Shadows.OffsetX
	local baseZ = opts.ZIndex or 2

	local root = Instance.new("Frame")
	root.Name = opts.Name or "GlossyPanel"
	root.Size = opts.Size or UDim2.fromOffset(380, 280)
	root.Position = opts.Position or UDim2.fromScale(0.5, 0.5)
	root.AnchorPoint = opts.AnchorPoint or Vector2.new(0.5, 0.5)
	root.BackgroundTransparency = 1
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	root.Parent = opts.Parent

	local faceSize = UDim2.new(1, -math.abs(sx), 1, -sy)
	local dropShadow = Instance.new("Frame")
	dropShadow.Name = "DropShadow"
	dropShadow.Size = faceSize
	dropShadow.Position = UDim2.fromOffset(sx, sy)
	dropShadow.BackgroundColor3 = UIKit.Tokens.Shadows.Color
	dropShadow.BackgroundTransparency = math.clamp(UIKit.Tokens.Shadows.Transparency, 0.08, 0.55)
	dropShadow.BorderSizePixel = 0
	dropShadow.ZIndex = baseZ
	dropShadow.Parent = root

	local dCorner = Instance.new("UICorner")
	dCorner.CornerRadius = radius
	dCorner.Parent = dropShadow

	local face = Instance.new("Frame")
	face.Name = "Face"
	face.Size = faceSize
	face.Position = UDim2.fromOffset(0, 0)
	face.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
	face.BorderSizePixel = 0
	face.ZIndex = baseZ + 1
	face.Parent = root

	UIKit.ApplyGlossySurface(face, {
		GradientKey = "Panel",
		BaseColor = UIKit.Tokens.Colors.BgPanel,
		CornerRadius = radius,
		StrokeColor = opts.StrokeColor or UIKit.Tokens.Colors.OutlineInk,
		StrokeThickness = UIKit.Tokens.Strokes.Panel,
		InnerHighlight = true,
	})

	local uiShadow = tryAttachUIShadow(
		face,
		UIKit.Tokens.Shadows.Color,
		UIKit.Tokens.Shadows.Transparency,
		UIKit.Tokens.Shadows.BlurRadius + 4,
		sx,
		sy
	)
	if uiShadow then
		dropShadow.Visible = false
	end

	if opts.NoOrnament ~= true then
		UIKit.AttachPresetOrnament(face)
	end

	if opts.ShowRays and UIKit.Tokens.Motifs.RaysEnabled then
		UIKit.CreateSunburstRays(face, {
			Color = opts.HeaderColor or UIKit.Tokens.Colors.Gold,
			Transparency = 0.84,
			RotateSpeed = 6,
			ZIndex = baseZ + 2,
		})
	end

	local header: Frame? = nil
	local titleLbl: TextLabel? = nil
	local closeBtn: GuiButton? = nil
	local topOffset = 12

	if opts.Title and opts.Title ~= "" then
		topOffset = 58
		local hdr = Instance.new("Frame")
		hdr.Name = "Header"
		hdr.Size = UDim2.new(1, -16, 0, 42)
		hdr.Position = UDim2.fromOffset(8, 8)
		hdr.BorderSizePixel = 0
		hdr.ZIndex = baseZ + 3
		hdr.Parent = face

		UIKit.ApplyGlossySurface(hdr, {
			GradientKey = if opts.HeaderColor then nil else "Primary",
			BaseColor = opts.HeaderColor or UIKit.Tokens.Colors.Primary,
			CornerRadius = UIKit.Tokens.Radii.Small,
			StrokeColor = UIKit.Tokens.Colors.OutlineInk,
			StrokeThickness = math.max(2, UIKit.Tokens.Strokes.Panel * 0.65),
			InnerHighlight = false,
		})

		local tLbl = Instance.new("TextLabel")
		tLbl.Name = "Title"
		tLbl.Size = UDim2.new(1, -60, 1, 0)
		tLbl.Position = UDim2.fromOffset(14, 0)
		tLbl.BackgroundTransparency = 1
		tLbl.Text = opts.Title
		tLbl.TextColor3 = if opts.HeaderColor then UIKit.PickReadableTextColor(opts.HeaderColor) else UIKit.Tokens.Colors.TextOnPrimary
		tLbl.TextSize = 18
		tLbl.TextXAlignment = Enum.TextXAlignment.Left
		tLbl.FontFace = UIKit.Tokens.Fonts.Title
		tLbl.ZIndex = baseZ + 4
		tLbl.Parent = hdr
		UIKit.AttachTextStroke(tLbl, UIKit.Tokens.Colors.OutlineInk, UIKit.Tokens.Strokes.Text, 0.12)

		header = hdr
		titleLbl = tLbl

		if opts.ShowClose ~= false then
			closeBtn = UIKit.CreateButton({
				Name = "CloseButton",
				Parent = hdr,
				Text = "X",
				Variant = "Danger",
				Size = UDim2.fromOffset(44, 44),
				Position = UDim2.new(1, 2, 0.5, 0),
				AnchorPoint = Vector2.new(1, 0.5),
				TextSize = 15,
			})
		end
	end

	local content = Instance.new("Frame")
	content.Name = "Content"
	content.Size = UDim2.new(1, -24, 1, -(topOffset + 12))
	content.Position = UDim2.fromOffset(12, topOffset)
	content.BackgroundTransparency = 1
	content.BorderSizePixel = 0
	content.ZIndex = baseZ + 3
	content.Parent = face

	return {
		Root = root,
		Face = face,
		Content = content,
		Header = header,
		TitleLabel = titleLbl,
		CloseButton = closeBtn,
	}
end

function UIKit.CreateWindow(opts: GlossyPanelOptions)
	return UIKit.CreateGlossyPanel(opts)
end

function UIKit.CreateBadgeIcon(
	parent: Instance?,
	spriteKey: string,
	fallbackGlyph: string,
	accentColor: Color3,
	sizePx: number?
): GuiObject
	local sz = sizePx or 28
	local assets = UIKit.Assets
	local rectInfo = if assets.IconRects then assets.IconRects[spriteKey] else nil
	if assets.IconAtlasId and rectInfo then
		local img = Instance.new("ImageLabel")
		img.Name = spriteKey .. "Icon"
		img.Size = UDim2.fromOffset(sz, sz)
		img.BackgroundTransparency = 1
		img.Image = assets.IconAtlasId
		img.ImageRectOffset = rectInfo.offset
		img.ImageRectSize = rectInfo.size
		img.ResampleMode = Enum.ResamplerMode.Default
		img.Parent = parent
		return img
	end

	local badge = Instance.new("TextLabel")
	badge.Name = spriteKey .. "Badge"
	badge.Size = UDim2.fromOffset(sz, sz)
	badge.BackgroundColor3 = accentColor
	badge.Text = fallbackGlyph
	badge.TextColor3 = Color3.fromRGB(255, 255, 255)
	badge.TextSize = math.max(12, math.floor(sz * 0.52))
	badge.FontFace = UIKit.Tokens.Fonts.Title
	badge.BorderSizePixel = 0

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UIKit.Tokens.Radii.Pill
	corner.Parent = badge

	local stroke = Instance.new("UIStroke")
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	stroke.Color = Color3.fromRGB(255, 255, 255)
	stroke.Thickness = 1.2
	stroke.Transparency = 0.55
	stroke.Parent = badge

	badge.Parent = parent
	return badge
end

export type SliderOptions = {
	Name: string?,
	Parent: Instance?,
	Label: string,
	InitialValue: number?,
	Min: number?,
	Max: number?,
	AccentColor: Color3?,
	OnChanged: ((value: number) -> ())?,
}

-- Responsive slider powered by UIDragDetector (TranslateLine) + click-on-track support
function UIKit.CreateSlider(opts: SliderOptions): { Root: Frame, GetValue: () -> number, SetValue: (number) -> () }
	local minV = opts.Min or 0
	local maxV = opts.Max or 100
	local currentV = math.clamp(opts.InitialValue or 75, minV, maxV)
	local accent = opts.AccentColor or UIKit.Tokens.Colors.Primary

	local root = Instance.new("Frame")
	root.Name = opts.Name or "SliderRow"
	root.Size = UDim2.new(1, 0, 0, 78)
	root.BackgroundColor3 = UIKit.Tokens.Colors.BgCard
	root.BackgroundTransparency = 0.25
	root.BorderSizePixel = 0
	root.Parent = opts.Parent

	local rCorner = Instance.new("UICorner")
	rCorner.CornerRadius = UIKit.Tokens.Radii.Small
	rCorner.Parent = root

	local title = Instance.new("TextLabel")
	title.Name = "Title"
	title.Size = UDim2.new(0.65, -12, 0, 22)
	title.Position = UDim2.fromOffset(12, 6)
	title.BackgroundTransparency = 1
	title.Text = opts.Label
	title.TextColor3 = UIKit.Tokens.Colors.TextPrimary
	title.TextSize = 14
	title.TextXAlignment = Enum.TextXAlignment.Left
	title.FontFace = UIKit.Tokens.Fonts.Heading
	title.Parent = root

	local valueLbl = Instance.new("TextLabel")
	valueLbl.Name = "ValueLabel"
	valueLbl.Size = UDim2.new(0.35, -12, 0, 22)
	valueLbl.Position = UDim2.new(0.65, 0, 0, 6)
	valueLbl.BackgroundTransparency = 1
	valueLbl.TextColor3 = UIKit.Tokens.Colors.TextSecondary
	valueLbl.TextSize = 14
	valueLbl.TextXAlignment = Enum.TextXAlignment.Right
	valueLbl.FontFace = UIKit.Tokens.Fonts.Mono
	valueLbl.Parent = root

	local trackBtn = Instance.new("TextButton")
	trackBtn.Name = "Track"
	trackBtn.Size = UDim2.new(1, -24, 0, 52)
	trackBtn.Position = UDim2.fromOffset(12, 26)
	trackBtn.BackgroundTransparency = 1
	trackBtn.Text = ""
	trackBtn.AutoButtonColor = false
	trackBtn.Parent = root

	local trackBar = Instance.new("Frame")
	trackBar.Name = "Bar"
	trackBar.Size = UDim2.new(1, 0, 0, 8)
	trackBar.Position = UDim2.fromScale(0, 0.5)
	trackBar.AnchorPoint = Vector2.new(0, 0.5)
	trackBar.BackgroundColor3 = UIKit.Tokens.Colors.BgInput
	trackBar.BorderSizePixel = 0
	trackBar.Parent = trackBtn

	local tCorner = Instance.new("UICorner")
	tCorner.CornerRadius = UIKit.Tokens.Radii.Pill
	tCorner.Parent = trackBar

	local fill = Instance.new("Frame")
	fill.Name = "Fill"
	fill.Size = UDim2.fromScale(0.5, 1)
	fill.BackgroundColor3 = accent
	fill.BorderSizePixel = 0
	fill.Parent = trackBar

	local fCorner = Instance.new("UICorner")
	fCorner.CornerRadius = UIKit.Tokens.Radii.Pill
	fCorner.Parent = fill

	local knob = Instance.new("Frame")
	knob.Name = "Knob"
	knob.Size = UDim2.fromOffset(20, 20)
	knob.AnchorPoint = Vector2.new(0.5, 0.5)
	knob.Position = UDim2.fromScale(0.5, 0.5)
	knob.BackgroundColor3 = Color3.fromRGB(245, 248, 255)
	knob.BorderSizePixel = 0
	knob.Parent = trackBtn

	local kCorner = Instance.new("UICorner")
	kCorner.CornerRadius = UIKit.Tokens.Radii.Pill
	kCorner.Parent = knob

	local kStroke = Instance.new("UIStroke")
	kStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	kStroke.Color = accent
	kStroke.Thickness = 2
	kStroke.Parent = knob

	local function applyRatio(ratio: number, fireCallback: boolean)
		local r = math.clamp(ratio, 0, 1)
		currentV = minV + (maxV - minV) * r
		fill.Size = UDim2.fromScale(r, 1)
		knob.Position = UDim2.fromScale(r, 0.5)
		valueLbl.Text = string.format("%d%%", math.floor(currentV + 0.5))
		if fireCallback and opts.OnChanged then
			opts.OnChanged(currentV)
		end
	end

	local dragOk, detector = pcall(function()
		local d = Instance.new("UIDragDetector")
		d.Name = "SliderDrag"
		d.DragStyle = Enum.UIDragDetectorDragStyle.TranslateLine
		d.ResponseStyle = Enum.UIDragDetectorResponseStyle.Scale
		d.DragAxis = Vector2.new(1, 0)
		d.BoundingUI = trackBtn
		d.Parent = knob
		return d
	end)

	if dragOk and detector then
		local function syncFromKnob()
			local width = math.max(1, trackBtn.AbsoluteSize.X)
			local centerX = knob.AbsolutePosition.X + knob.AbsoluteSize.X * 0.5
			local r = math.clamp((centerX - trackBtn.AbsolutePosition.X) / width, 0, 1)
			applyRatio(r, true)
		end
		detector.DragContinue:Connect(syncFromKnob)
		detector.DragEnd:Connect(syncFromKnob)
	end

	trackBtn.MouseButton1Down:Connect(function(x: number)
		local width = math.max(1, trackBtn.AbsoluteSize.X)
		local r = math.clamp((x - trackBtn.AbsolutePosition.X) / width, 0, 1)
		applyRatio(r, true)
	end)

	applyRatio((currentV - minV) / math.max(1e-4, maxV - minV), false)

	return {
		Root = root,
		GetValue = function()
			return currentV
		end,
		SetValue = function(v: number)
			applyRatio((v - minV) / math.max(1e-4, maxV - minV), true)
		end,
	}
end

function UIKit.CreateToggle(
	parent: Instance?,
	name: string,
	label: string,
	initialState: boolean,
	onChanged: ((enabled: boolean) -> ())?
): { Root: Frame, GetState: () -> boolean, SetState: (boolean) -> () }
	local state = initialState

	local root = Instance.new("Frame")
	root.Name = name
	root.Size = UDim2.new(1, 0, 0, 48)
	root.BackgroundColor3 = UIKit.Tokens.Colors.BgCard
	root.BackgroundTransparency = 0.25
	root.BorderSizePixel = 0
	root.Parent = parent

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UIKit.Tokens.Radii.Small
	corner.Parent = root

	local lbl = Instance.new("TextLabel")
	lbl.Size = UDim2.new(1, -84, 1, 0)
	lbl.Position = UDim2.fromOffset(12, 0)
	lbl.BackgroundTransparency = 1
	lbl.Text = label
	lbl.TextColor3 = UIKit.Tokens.Colors.TextPrimary
	lbl.TextSize = 14
	lbl.TextXAlignment = Enum.TextXAlignment.Left
	lbl.FontFace = UIKit.Tokens.Fonts.Heading
	lbl.Parent = root

	local switch = Instance.new("TextButton")
	switch.Name = "Switch"
	switch.Size = UDim2.fromOffset(58, 52)
	switch.Position = UDim2.new(1, -10, 0.5, 0)
	switch.AnchorPoint = Vector2.new(1, 0.5)
	switch.BackgroundTransparency = 1
	switch.Text = ""
	switch.Parent = root

	local pill = Instance.new("Frame")
	pill.Name = "Pill"
	pill.Size = UDim2.fromOffset(54, 28)
	pill.Position = UDim2.fromScale(0.5, 0.5)
	pill.AnchorPoint = Vector2.new(0.5, 0.5)
	pill.BorderSizePixel = 0
	pill.Parent = switch

	local pCorner = Instance.new("UICorner")
	pCorner.CornerRadius = UIKit.Tokens.Radii.Pill
	pCorner.Parent = pill

	local thumb = Instance.new("Frame")
	thumb.Name = "Thumb"
	thumb.Size = UDim2.fromOffset(22, 22)
	thumb.AnchorPoint = Vector2.new(0.5, 0.5)
	thumb.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
	thumb.BorderSizePixel = 0
	thumb.Parent = pill

	local thCorner = Instance.new("UICorner")
	thCorner.CornerRadius = UIKit.Tokens.Radii.Pill
	thCorner.Parent = thumb

	local function render(animate: boolean)
		local targetColor = if state then UIKit.Tokens.Colors.Success else UIKit.Tokens.Colors.Secondary
		local targetPos = if state then UDim2.new(1, -14, 0.5, 0) else UDim2.new(0, 14, 0.5, 0)
		if animate then
			local info = TweenInfo.new(0.16, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)
			UIKit.Tween(pill, info, { BackgroundColor3 = targetColor })
			UIKit.Tween(thumb, info, { Position = targetPos })
		else
			pill.BackgroundColor3 = targetColor
			thumb.Position = targetPos
		end
	end

	switch.Activated:Connect(function()
		state = not state
		render(true)
		if onChanged then
			onChanged(state)
		end
	end)

	render(false)
	return {
		Root = root,
		GetState = function()
			return state
		end,
		SetState = function(nextState: boolean)
			state = nextState
			render(true)
			if onChanged then
				onChanged(state)
			end
		end,
	}
end

-- Modal Stack Manager: single active modal, backdrop scrim, SelectionGroup focus trapping
function UIKit.CreateModalManager(modalGui: ScreenGui, backdropGui: ScreenGui?)
	local registered: { [string]: { frame: GuiObject, focusTarget: GuiObject? } } = {}
	local activeName: string? = nil
	local previousSelection: GuiObject? = nil
	local listeners: { (active: string?) -> () } = {}

	local manager = {}

	local function emitChange()
		for _, fn in ipairs(listeners) do
			task.spawn(fn, activeName)
		end
	end

	function manager:Register(name: string, frame: GuiObject, defaultFocus: GuiObject?)
		frame.Visible = false
		frame.SelectionGroup = true
		frame.SelectionBehaviorUp = Enum.SelectionBehavior.Stop
		frame.SelectionBehaviorDown = Enum.SelectionBehavior.Stop
		frame.SelectionBehaviorLeft = Enum.SelectionBehavior.Stop
		frame.SelectionBehaviorRight = Enum.SelectionBehavior.Stop
		registered[name] = { frame = frame, focusTarget = defaultFocus }
	end

	function manager:GetActive(): string?
		return activeName
	end

	function manager:IsOpen(name: string): boolean
		return activeName == name
	end

	function manager:OnChanged(fn: (active: string?) -> ())
		table.insert(listeners, fn)
	end

	function manager:CloseAll()
		for _, entry in pairs(registered) do
			entry.frame.Visible = false
			entry.frame.SelectionGroup = false
		end
		activeName = nil
		if backdropGui then
			backdropGui.Enabled = false
		end
		if previousSelection and previousSelection.Parent then
			pcall(function()
				GuiService.SelectedObject = previousSelection
			end)
		end
		previousSelection = nil
		emitChange()
	end

	function manager:Open(name: string)
		local entry = registered[name]
		if not entry then
			warn("[ModalManager] Unknown modal:", name)
			return
		end
		if activeName == name then
			manager:CloseAll()
			return
		end
		if activeName == nil then
			pcall(function()
				previousSelection = GuiService.SelectedObject
			end)
		end
		for otherName, other in pairs(registered) do
			other.frame.Visible = (otherName == name)
			other.frame.SelectionGroup = (otherName == name)
		end
		modalGui.Enabled = true
		if backdropGui then
			backdropGui.Enabled = true
		end
		activeName = name

		local scale = entry.frame:FindFirstChild("ModalPopScale") :: UIScale?
		if not scale then
			local newScale = Instance.new("UIScale")
			newScale.Name = "ModalPopScale"
			newScale.Parent = entry.frame
			scale = newScale
		end
		local popScale = scale :: UIScale
		if not UIKit.IsReducedMotion() then
			popScale.Scale = 0.94
			UIKit.Tween(popScale, TweenInfo.new(0.18, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1.0 })
		else
			popScale.Scale = 1.0
		end

		if RunService:IsRunning() and UIKit.GetPreferredInput() == Enum.PreferredInput.Gamepad then
			pcall(function()
				GuiService:Select(entry.focusTarget or entry.frame)
			end)
		end
		emitChange()
	end

	function manager:Pop(): boolean
		if activeName ~= nil then
			manager:CloseAll()
			return true
		end
		return false
	end

	if backdropGui then
		local scrim = backdropGui:FindFirstChild("Scrim")
		if scrim and scrim:IsA("GuiButton") then
			scrim.Activated:Connect(function()
				manager:Pop()
			end)
		end
	end

	return manager
end

-- Viewport-clamped Tooltip controller (Hover on Mouse, Selection on Gamepad, Tap on Touch)
function UIKit.CreateTooltipController(tooltipGui: ScreenGui)
	local card = Instance.new("Frame")
	card.Name = "TooltipCard"
	card.AutomaticSize = Enum.AutomaticSize.XY
	card.Size = UDim2.fromOffset(0, 0)
	card.BackgroundColor3 = UIKit.Tokens.Colors.BgDeep
	card.BackgroundTransparency = 0.04
	card.BorderSizePixel = 0
	card.Visible = false
	card.Active = false
	card.Parent = tooltipGui

	local corner = Instance.new("UICorner")
	corner.CornerRadius = UIKit.Tokens.Radii.Small
	corner.Parent = card

	local stroke = Instance.new("UIStroke")
	stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	stroke.Color = UIKit.Tokens.Colors.BorderBright
	stroke.Thickness = 1.5
	stroke.Parent = card

	local sizeCap = Instance.new("UISizeConstraint")
	sizeCap.MinSize = Vector2.new(150, 44)
	sizeCap.MaxSize = Vector2.new(270, 220)
	sizeCap.Parent = card

	local pad = Instance.new("UIPadding")
	pad.PaddingTop = UDim.new(0, 8)
	pad.PaddingBottom = UDim.new(0, 8)
	pad.PaddingLeft = UDim.new(0, 10)
	pad.PaddingRight = UDim.new(0, 10)
	pad.Parent = card

	local list = Instance.new("UIListLayout")
	list.FillDirection = Enum.FillDirection.Vertical
	list.SortOrder = Enum.SortOrder.LayoutOrder
	list.Padding = UDim.new(0, 3)
	list.Parent = card

	local titleLbl = Instance.new("TextLabel")
	titleLbl.Name = "Title"
	titleLbl.AutomaticSize = Enum.AutomaticSize.XY
	titleLbl.Size = UDim2.fromOffset(0, 0)
	titleLbl.LayoutOrder = 1
	titleLbl.BackgroundTransparency = 1
	titleLbl.TextColor3 = UIKit.Tokens.Colors.TextPrimary
	titleLbl.TextSize = 15
	titleLbl.TextXAlignment = Enum.TextXAlignment.Left
	titleLbl.FontFace = UIKit.Tokens.Fonts.Heading
	titleLbl.Active = false
	titleLbl.Parent = card

	local subLbl = Instance.new("TextLabel")
	subLbl.Name = "Subtitle"
	subLbl.AutomaticSize = Enum.AutomaticSize.XY
	subLbl.Size = UDim2.fromOffset(0, 0)
	subLbl.LayoutOrder = 2
	subLbl.BackgroundTransparency = 1
	subLbl.TextColor3 = UIKit.Tokens.Colors.Gold
	subLbl.TextSize = 12
	subLbl.TextXAlignment = Enum.TextXAlignment.Left
	subLbl.FontFace = UIKit.Tokens.Fonts.Body
	subLbl.Active = false
	subLbl.Parent = card

	local bodyLbl = Instance.new("TextLabel")
	bodyLbl.Name = "Body"
	bodyLbl.AutomaticSize = Enum.AutomaticSize.XY
	bodyLbl.Size = UDim2.fromOffset(0, 0)
	bodyLbl.LayoutOrder = 3
	bodyLbl.BackgroundTransparency = 1
	bodyLbl.TextWrapped = true
	bodyLbl.TextColor3 = UIKit.Tokens.Colors.TextSecondary
	bodyLbl.TextSize = 13
	bodyLbl.TextXAlignment = Enum.TextXAlignment.Left
	bodyLbl.FontFace = UIKit.Tokens.Fonts.Body
	bodyLbl.Active = false
	bodyLbl.Parent = card

	local controller = { Card = card }

	function controller:Show(title: string, subtitle: string?, body: string?, anchorPos: Vector2?, accent: Color3?)
		titleLbl.Text = title
		subLbl.Visible = (subtitle ~= nil and subtitle ~= "")
		subLbl.Text = subtitle or ""
		subLbl.TextColor3 = accent or UIKit.Tokens.Colors.Gold
		bodyLbl.Visible = (body ~= nil and body ~= "")
		bodyLbl.Text = body or ""
		stroke.Color = accent or UIKit.Tokens.Colors.BorderBright

		card.Visible = true
		tooltipGui.Enabled = true

		local vp = tooltipGui.AbsoluteSize
		local cs = card.AbsoluteSize
		local w = math.max(160, cs.X)
		local h = math.max(56, cs.Y)
		local margin = 12
		local rawX = if anchorPos then anchorPos.X + 16 else (vp.X * 0.5)
		local rawY = if anchorPos then anchorPos.Y + 16 else (vp.Y * 0.5)
		if rawX + w + margin > vp.X and anchorPos then
			rawX = anchorPos.X - w - 12
		end
		local maxX = math.max(margin, vp.X - w - margin)
		local maxY = math.max(margin, vp.Y - h - margin)
		card.Position = UDim2.fromOffset(math.clamp(rawX, margin, maxX), math.clamp(rawY, margin, maxY))
	end

	function controller:Hide()
		card.Visible = false
	end

	function controller:BindHover(target: GuiObject, getData: () -> { title: string, subtitle: string?, body: string?, accent: Color3? })
		target.MouseEnter:Connect(function(x: number, y: number)
			if UIKit.GetPreferredInput() == Enum.PreferredInput.Touch then
				return
			end
			local info = getData()
			local pos = Vector2.new(x, y) - tooltipGui.AbsolutePosition
			controller:Show(info.title, info.subtitle, info.body, pos, info.accent)
		end)
		target.MouseMoved:Connect(function(x: number, y: number)
			if card.Visible and UIKit.GetPreferredInput() ~= Enum.PreferredInput.Touch then
				local info = getData()
				local pos = Vector2.new(x, y) - tooltipGui.AbsolutePosition
				controller:Show(info.title, info.subtitle, info.body, pos, info.accent)
			end
		end)
		target.MouseLeave:Connect(function()
			controller:Hide()
		end)
		target.SelectionGained:Connect(function()
			local info = getData()
			local abs = target.AbsolutePosition - tooltipGui.AbsolutePosition + Vector2.new(target.AbsoluteSize.X, 0)
			controller:Show(info.title, info.subtitle, info.body, abs, info.accent)
		end)
		target.SelectionLost:Connect(function()
			controller:Hide()
		end)
	end

	return controller
end

-- FIFO / capped non-blocking Toast Queue
function UIKit.CreateToastQueue(toastGui: ScreenGui, maxVisible: number?)
	local cap = maxVisible or 3
	local stack = toastGui:FindFirstChild("ToastStack") :: Frame?
	if not stack then
		local f = Instance.new("Frame")
		f.Name = "ToastStack"
		f.Size = UDim2.new(0, 320, 0, 260)
		f.Position = UDim2.new(0.5, 0, 0, 12)
		f.AnchorPoint = Vector2.new(0.5, 0)
		f.BackgroundTransparency = 1
		f.Active = false
		f.Parent = toastGui

		local list = Instance.new("UIListLayout")
		list.FillDirection = Enum.FillDirection.Vertical
		list.HorizontalAlignment = Enum.HorizontalAlignment.Center
		list.SortOrder = Enum.SortOrder.LayoutOrder
		list.Padding = UDim.new(0, 8)
		list.Parent = f
		stack = f
	end

	local stackFrame = stack :: Frame
	local activeCount = 0
	local orderSeq = 0
	local pending: { ToastRequest } = {}
	local kindColors: { [string]: Color3 } = {
		Info = UIKit.Tokens.Colors.Primary,
		Success = UIKit.Tokens.Colors.Success,
		Reward = UIKit.Tokens.Colors.Gold,
		Warning = UIKit.Tokens.Colors.Warning,
		Error = UIKit.Tokens.Colors.Danger,
	}

	local queueObj = {}

	local function spawnToast(req: ToastRequest)
		activeCount += 1
		orderSeq += 1
		local accent = kindColors[req.kind or "Info"] or UIKit.Tokens.Colors.Primary
		local duration = req.duration or 2.6

		local banner = Instance.new("Frame")
		banner.Name = "Toast_" .. tostring(orderSeq)
		banner.Size = UDim2.new(1, 0, 0, 56)
		banner.LayoutOrder = orderSeq
		banner.BackgroundColor3 = UIKit.Tokens.Colors.BgDeep
		banner.BackgroundTransparency = 0.06
		banner.BorderSizePixel = 0
		banner.Active = false
		banner.Parent = stackFrame

		local corner = Instance.new("UICorner")
		corner.CornerRadius = UIKit.Tokens.Radii.Small
		corner.Parent = banner

		local stroke = Instance.new("UIStroke")
		stroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		stroke.Color = accent
		stroke.Thickness = 1.6
		stroke.Parent = banner

		local bar = Instance.new("Frame")
		bar.Size = UDim2.new(0, 5, 1, -12)
		bar.Position = UDim2.fromOffset(6, 6)
		bar.BackgroundColor3 = accent
		bar.BorderSizePixel = 0
		bar.Parent = banner
		local bCorner = Instance.new("UICorner")
		bCorner.CornerRadius = UIKit.Tokens.Radii.Pill
		bCorner.Parent = bar

		local title = Instance.new("TextLabel")
		title.Size = UDim2.new(1, -28, 0, 22)
		title.Position = UDim2.fromOffset(20, 6)
		title.BackgroundTransparency = 1
		title.Text = req.title
		title.TextColor3 = UIKit.Tokens.Colors.TextPrimary
		title.TextSize = 14
		title.TextXAlignment = Enum.TextXAlignment.Left
		title.FontFace = UIKit.Tokens.Fonts.Heading
		title.Parent = banner

		local msg = Instance.new("TextLabel")
		msg.Size = UDim2.new(1, -28, 0, 18)
		msg.Position = UDim2.fromOffset(20, 28)
		msg.BackgroundTransparency = 1
		msg.Text = req.message or ""
		msg.TextColor3 = UIKit.Tokens.Colors.TextSecondary
		msg.TextSize = 12
		msg.TextXAlignment = Enum.TextXAlignment.Left
		msg.FontFace = UIKit.Tokens.Fonts.Body
		msg.Parent = banner

		local scale = Instance.new("UIScale")
		scale.Scale = if UIKit.IsReducedMotion() then 1 else 0.9
		scale.Parent = banner
		if not UIKit.IsReducedMotion() then
			UIKit.Tween(scale, TweenInfo.new(0.16, Enum.EasingStyle.Back, Enum.EasingDirection.Out), { Scale = 1 })
		end

		task.delay(duration, function()
			if banner.Parent then
				if not UIKit.IsReducedMotion() then
					local outInfo = TweenInfo.new(0.18, Enum.EasingStyle.Quad, Enum.EasingDirection.In)
					local tw = UIKit.Tween(banner, outInfo, { BackgroundTransparency = 1 })
					UIKit.Tween(title, outInfo, { TextTransparency = 1 })
					UIKit.Tween(msg, outInfo, { TextTransparency = 1 })
					UIKit.Tween(bar, outInfo, { BackgroundTransparency = 1 })
					UIKit.Tween(stroke, outInfo, { Transparency = 1 })
					if tw then
						tw.Completed:Wait()
					end
				end
				banner:Destroy()
			end
			activeCount = math.max(0, activeCount - 1)
			if #pending > 0 and activeCount < cap then
				local nxt = table.remove(pending, 1)
				if nxt then
					spawnToast(nxt)
				end
			end
		end)
	end

	function queueObj:Push(req: ToastRequest)
		toastGui.Enabled = true
		if activeCount < cap then
			spawnToast(req)
		else
			table.insert(pending, req)
		end
	end

	function queueObj:GetActiveCount(): number
		return activeCount
	end

	return queueObj
end

-- ViewportFrame 3D Model Previewer with WorldModel + ViewportCamera auto-framing
function UIKit.CreateViewportPreview(parent: Instance, opts: { Size: UDim2?, Position: UDim2?, AutoSpin: boolean? }?)
	local cfg = opts or {}
	local vf = Instance.new("ViewportFrame")
	vf.Name = "ModelViewport"
	vf.Size = cfg.Size or UDim2.fromScale(1, 1)
	vf.Position = cfg.Position or UDim2.new()
	vf.BackgroundTransparency = 1
	vf.Ambient = Color3.fromRGB(205, 212, 228)
	vf.LightColor = Color3.fromRGB(255, 244, 224)
	vf.LightDirection = Vector3.new(-1, -1, -0.8)
	vf.Parent = parent

	local world = Instance.new("WorldModel")
	world.Name = "World"
	world.Parent = vf

	local cam = Instance.new("ViewportCamera")
	cam.Name = "PreviewCamera"
	cam.FieldOfView = 35
	cam.Parent = vf
	vf.CurrentCamera = cam

	local currentSubject: Instance? = nil
	local spinEnabled = cfg.AutoSpin == true
	local angle = 0.35
	local dist = 6
	local targetCenter = Vector3.zero
	local conn: RBXScriptConnection? = nil

	local function updateCamera()
		local eye = targetCenter + Vector3.new(math.sin(angle) * dist, dist * 0.35, math.cos(angle) * dist)
		cam.CFrame = CFrame.lookAt(eye, targetCenter)
	end

	local function syncSpinConnection()
		if conn then
			conn:Disconnect()
			conn = nil
		end
		if spinEnabled and RunService:IsRunning() and vf.Parent then
			conn = RunService.RenderStepped:Connect(function(dt: number)
				if not vf.Visible then
					return
				end
				angle += dt * 0.75
				updateCamera()
			end)
		end
	end

	vf.AncestryChanged:Connect(function(_, newParent)
		if not newParent and conn then
			conn:Disconnect()
			conn = nil
		end
	end)

	local api = {
		Frame = vf,
		World = world,
		Camera = cam,
	}

	function api:SetModel(source: Instance)
		if currentSubject then
			currentSubject:Destroy()
			currentSubject = nil
		end
		local clone = source:Clone()
		clone.Parent = world
		currentSubject = clone

		local boxCf, boxSize
		if clone:IsA("Model") then
			boxCf, boxSize = clone:GetBoundingBox()
			clone:PivotTo(CFrame.new(-boxCf.Position) * clone:GetPivot())
			boxCf, boxSize = clone:GetBoundingBox()
		elseif clone:IsA("BasePart") then
			clone.CFrame = CFrame.new(0, 0, 0) * clone.CFrame.Rotation
			boxCf = clone.CFrame
			boxSize = clone.Size
		else
			boxCf = CFrame.new()
			boxSize = Vector3.new(3, 3, 3)
		end
		targetCenter = boxCf.Position
		local maxExtent = math.max(boxSize.X, boxSize.Y, boxSize.Z, 1)
		dist = (maxExtent * 0.5) / math.tan(math.rad(cam.FieldOfView * 0.5)) * 1.48
		updateCamera()
	end

	function api:SetAutoSpin(enabled: boolean)
		spinEnabled = enabled
		syncSpinConnection()
	end

	function api:Destroy()
		if conn then
			conn:Disconnect()
			conn = nil
		end
		vf:Destroy()
	end

	syncSpinConnection()
	return api
end

-- Responsive UIScale binder keeping Desktop/Tablet/Phone crisp
function UIKit.BindResponsiveScale(gui: ScreenGui, minScale: number?, maxScale: number?): UIScale
	local existing = gui:FindFirstChild("ResponsiveScale") :: UIScale?
	local uiScale = existing or Instance.new("UIScale")
	uiScale.Name = "ResponsiveScale"
	uiScale.Parent = gui

	local lo = minScale or 0.86
	local hi = maxScale or 1.08

	local function refresh()
		local abs = gui.AbsoluteSize
		if abs.X <= 0 or abs.Y <= 0 then
			return
		end
		local ratio = math.min(abs.X / 1280, abs.Y / 720)
		local target = math.clamp(ratio, lo, hi)
		-- Ensure comfortable readability on phone landscape/portrait while keeping >=52px buttons >=44px physical
		if abs.X < 920 and abs.Y < 500 then
			target = math.clamp(abs.Y / 410, lo, 0.94)
		end
		uiScale.Scale = target
	end

	gui:GetPropertyChangedSignal("AbsoluteSize"):Connect(refresh)
	refresh()
	return uiScale
end

-- =========================================================================
-- Composable Non-Template Layout Primitives (v0.5)
-- =========================================================================

export type ArcGaugeOptions = {
	Name: string?,
	Parent: Instance?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	Label: string?,
	Unit: string?,
	Value: number?,
	Max: number?,
	Min: number?,
	StartAngleDeg: number?,
	SweepAngleDeg: number?,
	TickCount: number?,
	SegmentCount: number?,
	FillColor: Color3?,
	SecondaryColor: Color3?,
	TrackColor: Color3?,
	GlowEnabled: boolean?,
	ShowTicks: boolean?,
	ShowNeedle: boolean?,
	OrbMode: boolean?,
	ZIndex: number?,
}

function UIKit.CreateArcGauge(opts: ArcGaugeOptions?)
	local o = (opts or {}) :: ArcGaugeOptions
	local baseZ = o.ZIndex or 4
	local minVal = o.Min or 0
	local maxVal = math.max(minVal + 1e-4, o.Max or 100)
	local currentVal = math.clamp(o.Value or 75, minVal, maxVal)
	local startDeg = if o.StartAngleDeg ~= nil then o.StartAngleDeg else -135
	local sweepDeg = if o.SweepAngleDeg ~= nil then o.SweepAngleDeg else 270
	local tickCount = math.clamp(o.TickCount or 11, 3, 24)
	local segCount = math.clamp(o.SegmentCount or 24, 8, 40)
	local fillCol = o.FillColor or UIKit.Tokens.Colors.Primary
	local secCol = o.SecondaryColor or UIKit.Tokens.Colors.Accent
	local trackCol = o.TrackColor or UIKit.Tokens.Colors.BgInput
	local orbMode = o.OrbMode == true
	local showTicks = o.ShowTicks ~= false
	local showNeedle = if o.ShowNeedle ~= nil then o.ShowNeedle else (not orbMode)
	local glowEnabled = o.GlowEnabled ~= false

	local root = Instance.new("Frame")
	root.Name = o.Name or "ArcGauge"
	root.Size = o.Size or UDim2.fromOffset(148, 148)
	root.Position = o.Position or UDim2.fromScale(0.5, 0.5)
	root.AnchorPoint = o.AnchorPoint or Vector2.new(0.5, 0.5)
	root.BackgroundTransparency = 1
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	root.Parent = o.Parent

	local aspect = Instance.new("UIAspectRatioConstraint")
	aspect.AspectRatio = 1
	aspect.Parent = root

	local glowFrame: Frame? = nil
	if glowEnabled then
		local glow = Instance.new("Frame")
		glow.Name = "GlowRing"
		glow.Size = UDim2.fromScale(0.98, 0.98)
		glow.Position = UDim2.fromScale(0.5, 0.5)
		glow.AnchorPoint = Vector2.new(0.5, 0.5)
		glow.BackgroundColor3 = fillCol
		glow.BackgroundTransparency = 0.84
		glow.BorderSizePixel = 0
		glow.Active = false
		glow.ZIndex = baseZ
		glow.Parent = root

		local gCorner = Instance.new("UICorner")
		gCorner.CornerRadius = UDim.new(1, 0)
		gCorner.Parent = glow

		local gStroke = Instance.new("UIStroke")
		gStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		gStroke.Color = fillCol
		gStroke.Thickness = 4
		gStroke.Transparency = 0.45
		gStroke.Parent = glow
		glowFrame = glow
	end

	local dial = Instance.new("Frame")
	dial.Name = "Dial"
	dial.Size = UDim2.fromScale(0.88, 0.88)
	dial.Position = UDim2.fromScale(0.5, 0.5)
	dial.AnchorPoint = Vector2.new(0.5, 0.5)
	dial.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
	dial.BackgroundTransparency = 0.04
	dial.BorderSizePixel = 0
	dial.ZIndex = baseZ + 1
	dial.Parent = root

	local dCorner = Instance.new("UICorner")
	dCorner.CornerRadius = UDim.new(0.5, 0)
	dCorner.Parent = dial

	UIKit.AttachStackedStrokes(dial, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = math.max(2.5, UIKit.Tokens.Strokes.OuterInk * 0.75),
		InnerColor = UIKit.Tokens.Colors.BorderBright,
		InnerThickness = 1.5,
		InnerTransparency = 0.55,
		CornerRadius = UDim.new(0.5, 0),
	})

	local orbCore = Instance.new("Frame")
	orbCore.Name = "OrbFill"
	orbCore.Size = UDim2.fromScale(0.76, 0.76)
	orbCore.Position = UDim2.fromScale(0.5, 0.5)
	orbCore.AnchorPoint = Vector2.new(0.5, 0.5)
	orbCore.BackgroundColor3 = fillCol
	orbCore.BackgroundTransparency = if orbMode then 0.05 else 0.92
	orbCore.BorderSizePixel = 0
	orbCore.Visible = orbMode
	orbCore.ZIndex = baseZ + 2
	orbCore.Parent = dial

	local oCorner = Instance.new("UICorner")
	oCorner.CornerRadius = UDim.new(1, 0)
	oCorner.Parent = orbCore

	local orbGrad = Instance.new("UIGradient")
	orbGrad.Name = "OrbLiquidGradient"
	orbGrad.Rotation = -90
	orbGrad.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0, fillCol:Lerp(Color3.fromRGB(16, 12, 24), 0.25)),
		ColorSequenceKeypoint.new(0.65, fillCol),
		ColorSequenceKeypoint.new(1, secCol),
	})
	orbGrad.Parent = orbCore

	local segFrames: { Frame } = {}
	for i = 1, segCount do
		local frac = (i - 1) / math.max(1, segCount - 1)
		local deg = startDeg + frac * sweepDeg
		local rad = math.rad(deg)
		local rx = 0.5 + math.sin(rad) * 0.41
		local ry = 0.5 - math.cos(rad) * 0.41

		local seg = Instance.new("Frame")
		seg.Name = string.format("ArcSeg_%02d", i)
		seg.Size = UDim2.fromScale(0.085, 0.055)
		seg.Position = UDim2.fromScale(rx, ry)
		seg.AnchorPoint = Vector2.new(0.5, 0.5)
		seg.Rotation = deg
		seg.BackgroundColor3 = trackCol
		seg.BorderSizePixel = 0
		seg.ZIndex = baseZ + 3
		seg.Parent = dial

		local sCorner = Instance.new("UICorner")
		sCorner.CornerRadius = UDim.new(1, 0)
		sCorner.Parent = seg
		table.insert(segFrames, seg)
	end

	if showTicks then
		for i = 1, tickCount do
			local frac = (i - 1) / math.max(1, tickCount - 1)
			local deg = startDeg + frac * sweepDeg
			local rad = math.rad(deg)
			local rx = 0.5 + math.sin(rad) * 0.31
			local ry = 0.5 - math.cos(rad) * 0.31

			local tick = Instance.new("Frame")
			tick.Name = string.format("Tick_%02d", i)
			tick.Size = UDim2.fromOffset(2, if (i == 1 or i == tickCount or i == math.ceil(tickCount / 2)) then 8 else 5)
			tick.Position = UDim2.fromScale(rx, ry)
			tick.AnchorPoint = Vector2.new(0.5, 0.5)
			tick.Rotation = deg
			tick.BackgroundColor3 = UIKit.Tokens.Colors.TextMuted
			tick.BackgroundTransparency = 0.25
			tick.BorderSizePixel = 0
			tick.ZIndex = baseZ + 3
			tick.Parent = dial
		end
	end

	local needlePivot = Instance.new("Frame")
	needlePivot.Name = "NeedlePivot"
	needlePivot.Size = UDim2.fromScale(1, 1)
	needlePivot.Position = UDim2.fromScale(0.5, 0.5)
	needlePivot.AnchorPoint = Vector2.new(0.5, 0.5)
	needlePivot.BackgroundTransparency = 1
	needlePivot.Visible = showNeedle
	needlePivot.ZIndex = baseZ + 4
	needlePivot.Parent = dial

	local needleArm = Instance.new("Frame")
	needleArm.Name = "NeedleArm"
	needleArm.Size = UDim2.new(0, 3, 0.34, 0)
	needleArm.Position = UDim2.fromScale(0.5, 0.5)
	needleArm.AnchorPoint = Vector2.new(0.5, 1)
	needleArm.BackgroundColor3 = secCol
	needleArm.BorderSizePixel = 0
	needleArm.ZIndex = baseZ + 4
	needleArm.Parent = needlePivot

	local nCorner = Instance.new("UICorner")
	nCorner.CornerRadius = UDim.new(1, 0)
	nCorner.Parent = needleArm

	local valueLbl = Instance.new("TextLabel")
	valueLbl.Name = "ValueLabel"
	valueLbl.Size = UDim2.new(0.76, 0, 0.28, 0)
	valueLbl.Position = UDim2.fromScale(0.5, 0.44)
	valueLbl.AnchorPoint = Vector2.new(0.5, 0.5)
	valueLbl.BackgroundTransparency = 1
	valueLbl.TextColor3 = UIKit.Tokens.Colors.TextPrimary
	valueLbl.TextSize = 20
	valueLbl.TextScaled = true
	valueLbl.FontFace = UIKit.Tokens.Fonts.Mono
	valueLbl.ZIndex = baseZ + 5
	valueLbl.Parent = dial
	UIKit.AttachTextStroke(valueLbl, UIKit.Tokens.Colors.OutlineInk, 1.8, 0.1)

	local vConstraint = Instance.new("UITextSizeConstraint")
	vConstraint.MinTextSize = 11
	vConstraint.MaxTextSize = 24
	vConstraint.Parent = valueLbl

	local titleLbl = Instance.new("TextLabel")
	titleLbl.Name = "TitleLabel"
	titleLbl.Size = UDim2.new(0.72, 0, 0.18, 0)
	titleLbl.Position = UDim2.fromScale(0.5, 0.67)
	titleLbl.AnchorPoint = Vector2.new(0.5, 0.5)
	titleLbl.BackgroundTransparency = 1
	titleLbl.Text = o.Label or "GAUGE"
	titleLbl.TextColor3 = UIKit.Tokens.Colors.TextSecondary
	titleLbl.TextSize = 12
	titleLbl.TextTruncate = Enum.TextTruncate.AtEnd
	titleLbl.FontFace = UIKit.Tokens.Fonts.Title
	titleLbl.ZIndex = baseZ + 5
	titleLbl.Parent = dial
	UIKit.AttachTextStroke(titleLbl, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.15)

	local function refreshVisuals()
		local span = math.max(1e-4, maxVal - minVal)
		local ratio = math.clamp((currentVal - minVal) / span, 0, 1)
		local activeSegs = ratio * segCount
		for idx, seg in ipairs(segFrames) do
			local segT = (idx - 1) / math.max(1, segCount - 1)
			local segColor = fillCol:Lerp(secCol, segT)
			if idx <= math.floor(activeSegs) then
				seg.BackgroundColor3 = segColor
				seg.BackgroundTransparency = 0
			elseif idx - 1 < activeSegs then
				seg.BackgroundColor3 = segColor
				seg.BackgroundTransparency = 0.35
			else
				seg.BackgroundColor3 = trackCol
				seg.BackgroundTransparency = 0.25
			end
		end

		local targetAngle = startDeg + ratio * sweepDeg
		if showNeedle then
			if UIKit.IsReducedMotion() then
				needlePivot.Rotation = targetAngle
			else
				UIKit.Tween(needlePivot, TweenInfo.new(0.16, Enum.EasingStyle.Quad, Enum.EasingDirection.Out), { Rotation = targetAngle })
			end
		end

		if orbMode then
			if ratio <= 0.01 then
				orbGrad.Transparency = NumberSequence.new({
					NumberSequenceKeypoint.new(0.0, 0.88),
					NumberSequenceKeypoint.new(1.0, 0.88),
				})
			elseif ratio >= 0.99 then
				orbGrad.Transparency = NumberSequence.new({
					NumberSequenceKeypoint.new(0.0, 0.06),
					NumberSequenceKeypoint.new(1.0, 0.06),
				})
			else
				local cut = math.clamp(ratio, 0.02, 0.96)
				orbGrad.Transparency = NumberSequence.new({
					NumberSequenceKeypoint.new(0.0, 0.06),
					NumberSequenceKeypoint.new(cut, 0.14),
					NumberSequenceKeypoint.new(math.min(0.985, cut + 0.02), 0.88),
					NumberSequenceKeypoint.new(1.0, 0.88),
				})
			end
		end

		local numTxt = tostring(math.floor(currentVal + 0.5))
		local unitSuffix = if o.Unit and o.Unit ~= "" then (" " .. o.Unit) else ""
		valueLbl.Text = numTxt .. unitSuffix
	end

	refreshVisuals()

	local api = {
		Root = root,
		Dial = dial,
		OrbFill = orbCore,
		Glow = glowFrame,
		ValueLabel = valueLbl,
		TitleLabel = titleLbl,
	} :: any

	function api:SetValue(value: number, nextMax: number?)
		if nextMax ~= nil then
			maxVal = math.max(minVal + 1e-4, nextMax)
		end
		currentVal = math.clamp(value, minVal, maxVal)
		refreshVisuals()
	end

	function api:GetValue(): number
		return currentVal
	end

	function api:SetMax(nextMax: number)
		maxVal = math.max(minVal + 1e-4, nextMax)
		currentVal = math.clamp(currentVal, minVal, maxVal)
		refreshVisuals()
	end

	function api:SetColors(nextFill: Color3, nextSecondary: Color3?)
		fillCol = nextFill
		if nextSecondary then
			secCol = nextSecondary
		end
		orbCore.BackgroundColor3 = fillCol
		orbGrad.Color = ColorSequence.new({
			ColorSequenceKeypoint.new(0, fillCol:Lerp(Color3.fromRGB(16, 12, 24), 0.25)),
			ColorSequenceKeypoint.new(0.65, fillCol),
			ColorSequenceKeypoint.new(1, secCol),
		})
		needleArm.BackgroundColor3 = secCol
		refreshVisuals()
	end

	return api
end

export type RadialWheelItem = {
	Id: string?,
	Label: string,
	IconKey: string?,
	IconFallback: string?,
	Color: Color3?,
	Description: string?,
}

export type RadialWheelOptions = {
	Name: string?,
	Parent: Instance?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	RadiusPx: number?,
	SegmentSizePx: number?,
	HubSizePx: number?,
	StartAngleDeg: number?,
	CenterTitle: string?,
	Items: { RadialWheelItem }?,
	ZIndex: number?,
	OnSelect: ((index: number, item: RadialWheelItem) -> ())?,
	OnCenterClick: (() -> ())?,
}

function UIKit.CreateRadialWheel(opts: RadialWheelOptions?)
	local o = (opts or {}) :: RadialWheelOptions
	local baseZ = o.ZIndex or 8
	local segSize = math.max(44, o.SegmentSizePx or 58)
	local hubSize = math.max(48, o.HubSizePx or 72)
	local radiusPx = math.max(math.ceil(hubSize * 0.5 + segSize * 0.5 + 12), o.RadiusPx or 108)
	local startDeg = if o.StartAngleDeg ~= nil then o.StartAngleDeg else -90
	local centerDefault = o.CenterTitle or "SELECT"

	local wheelDim = (radiusPx + math.ceil(segSize * 0.5) + 14) * 2
	local root = Instance.new("Frame")
	root.Name = o.Name or "RadialWheel"
	root.Size = UDim2.fromOffset(wheelDim, wheelDim)
	root.Position = o.Position or UDim2.fromScale(0.5, 0.5)
	root.AnchorPoint = o.AnchorPoint or Vector2.new(0.5, 0.5)
	root.BackgroundTransparency = 1
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	root.Parent = o.Parent

	local ringBack = Instance.new("Frame")
	ringBack.Name = "RingBackdrop"
	ringBack.Size = UDim2.fromOffset(radiusPx * 2 + segSize + 12, radiusPx * 2 + segSize + 12)
	ringBack.Position = UDim2.fromScale(0.5, 0.5)
	ringBack.AnchorPoint = Vector2.new(0.5, 0.5)
	ringBack.BackgroundColor3 = UIKit.Tokens.Colors.BgDeep
	ringBack.BackgroundTransparency = 0.22
	ringBack.BorderSizePixel = 0
	ringBack.Active = false
	ringBack.ZIndex = baseZ
	ringBack.Parent = root

	local rbCorner = Instance.new("UICorner")
	rbCorner.CornerRadius = UDim.new(1, 0)
	rbCorner.Parent = ringBack

	local rbStroke = Instance.new("UIStroke")
	rbStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	rbStroke.Color = UIKit.Tokens.Colors.BorderBright
	rbStroke.Thickness = 2
	rbStroke.Transparency = 0.35
	rbStroke.Parent = ringBack

	local hub = Instance.new("TextButton")
	hub.Name = "CenterHub"
	hub.Size = UDim2.fromOffset(hubSize, hubSize)
	hub.Position = UDim2.fromScale(0.5, 0.5)
	hub.AnchorPoint = Vector2.new(0.5, 0.5)
	hub.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
	hub.Text = ""
	hub.AutoButtonColor = false
	hub.BorderSizePixel = 0
	hub.ZIndex = baseZ + 4
	hub.Parent = root
	UIKit.EnsureMinTouchTarget(hub, 44)

	local hubCorner = Instance.new("UICorner")
	hubCorner.CornerRadius = UDim.new(1, 0)
	hubCorner.Parent = hub

	UIKit.AttachStackedStrokes(hub, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = math.max(2.5, UIKit.Tokens.Strokes.OuterInk * 0.7),
		InnerColor = UIKit.Tokens.Colors.Accent,
		InnerThickness = 1.6,
		InnerTransparency = 0.25,
		CornerRadius = UDim.new(1, 0),
	})

	local hubLabel = Instance.new("TextLabel")
	hubLabel.Name = "HubLabel"
	hubLabel.Size = UDim2.new(1, -10, 1, -10)
	hubLabel.Position = UDim2.fromScale(0.5, 0.5)
	hubLabel.AnchorPoint = Vector2.new(0.5, 0.5)
	hubLabel.BackgroundTransparency = 1
	hubLabel.Text = centerDefault
	hubLabel.TextColor3 = UIKit.Tokens.Colors.TextPrimary
	hubLabel.TextSize = 12
	hubLabel.TextWrapped = true
	hubLabel.TextTruncate = Enum.TextTruncate.AtEnd
	hubLabel.FontFace = UIKit.Tokens.Fonts.Title
	hubLabel.ZIndex = baseZ + 5
	hubLabel.Parent = hub
	UIKit.AttachTextStroke(hubLabel, UIKit.Tokens.Colors.OutlineInk, 1.4, 0.1)

	UIKit.AttachButtonJuice(hub, hub, function()
		if o.OnCenterClick then
			o.OnCenterClick()
		end
	end)

	local defaultItems: { RadialWheelItem } = {
		{ Id = "scan", Label = "Scan", IconKey = "gem", IconFallback = "S", Color = UIKit.Tokens.Colors.Accent },
		{ Id = "shield", Label = "Shield", IconKey = "shield", IconFallback = "D", Color = UIKit.Tokens.Colors.Primary },
		{ Id = "pulse", Label = "Pulse", IconKey = "bolt", IconFallback = "P", Color = UIKit.Tokens.Colors.Warning },
		{ Id = "repair", Label = "Repair", IconKey = "heart", IconFallback = "+", Color = UIKit.Tokens.Colors.Success },
		{ Id = "boost", Label = "Boost", IconKey = "star", IconFallback = "B", Color = UIKit.Tokens.Colors.Secondary },
		{ Id = "comms", Label = "Comms", IconKey = "crown", IconFallback = "C", Color = UIKit.Tokens.Colors.Gold },
	}
	local items: { RadialWheelItem } = if o.Items and #o.Items > 0 then o.Items else defaultItems
	local segments: { TextButton } = {}
	local selectedIdx: number? = nil

	local function updateSelectionVisuals()
		for idx, seg in ipairs(segments) do
			local itemData = items[idx]
			local active = (selectedIdx == idx)
			local segColor = (itemData and itemData.Color) or UIKit.Tokens.Colors.Primary
			seg.BackgroundColor3 = if active then segColor else UIKit.Tokens.Colors.BgPanel
			local outer = seg:FindFirstChild("OuterStroke")
			if outer and outer:IsA("UIStroke") then
				outer.Color = if active then UIKit.Tokens.Colors.Gold else UIKit.Tokens.Colors.OutlineInk
				outer.Thickness = if active then 3.5 else 2.5
			end
		end
		if selectedIdx and items[selectedIdx] then
			hubLabel.Text = items[selectedIdx].Label
		else
			hubLabel.Text = centerDefault
		end
	end

	local function rebuildSegments(nextItems: { RadialWheelItem })
		for _, oldSeg in ipairs(segments) do
			oldSeg:Destroy()
		end
		table.clear(segments)
		items = if #nextItems > 0 then nextItems else defaultItems
		local count = #items
		for i = 1, count do
			local item = items[i]
			local deg = startDeg + (i - 1) * (360 / count)
			local rad = math.rad(deg)
			local px = math.round(math.cos(rad) * radiusPx)
			local py = math.round(math.sin(rad) * radiusPx)
			local itemCol = item.Color or UIKit.Tokens.Colors.Primary

			local segBtn = Instance.new("TextButton")
			segBtn.Name = "Sector_" .. tostring(i)
			segBtn.Size = UDim2.fromOffset(segSize, segSize)
			segBtn.Position = UDim2.new(0.5, px, 0.5, py)
			segBtn.AnchorPoint = Vector2.new(0.5, 0.5)
			segBtn.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
			segBtn.Text = ""
			segBtn.AutoButtonColor = false
			segBtn.BorderSizePixel = 0
			segBtn.ZIndex = baseZ + 2
			segBtn:SetAttribute("SectorId", item.Id or item.Label)
			segBtn.Parent = root
			UIKit.EnsureMinTouchTarget(segBtn, 44)

			local corner = Instance.new("UICorner")
			corner.CornerRadius = UIKit.Tokens.Radii.Button
			corner.Parent = segBtn

			UIKit.AttachStackedStrokes(segBtn, {
				OuterColor = UIKit.Tokens.Colors.OutlineInk,
				OuterThickness = 2.5,
				InnerColor = itemCol,
				InnerThickness = 1.5,
				InnerTransparency = 0.25,
				CornerRadius = UIKit.Tokens.Radii.Button,
			})

			local icon = UIKit.CreateBadgeIcon(segBtn, item.IconKey or "star", item.IconFallback or "*", itemCol, math.max(20, math.floor(segSize * 0.40)))
			icon.Position = UDim2.fromScale(0.5, 0.34)
			icon.AnchorPoint = Vector2.new(0.5, 0.5)
			icon.ZIndex = baseZ + 3

			local lbl = Instance.new("TextLabel")
			lbl.Name = "Label"
			lbl.Size = UDim2.new(1, -6, 0, 16)
			lbl.Position = UDim2.new(0.5, 0, 1, -4)
			lbl.AnchorPoint = Vector2.new(0.5, 1)
			lbl.BackgroundTransparency = 1
			lbl.Text = item.Label
			lbl.TextColor3 = UIKit.Tokens.Colors.TextPrimary
			lbl.TextSize = 10
			lbl.TextTruncate = Enum.TextTruncate.AtEnd
			lbl.FontFace = UIKit.Tokens.Fonts.Heading
			lbl.ZIndex = baseZ + 3
			lbl.Parent = segBtn
			UIKit.AttachTextStroke(lbl, UIKit.Tokens.Colors.OutlineInk, 1.2, 0.12)

			segBtn.MouseEnter:Connect(function()
				hubLabel.Text = item.Label
			end)
			segBtn.MouseLeave:Connect(function()
				updateSelectionVisuals()
			end)
			UIKit.AttachButtonJuice(segBtn, segBtn, function()
				selectedIdx = i
				updateSelectionVisuals()
				if o.OnSelect then
					o.OnSelect(i, item)
				end
			end)

			table.insert(segments, segBtn)
		end
		selectedIdx = nil
		updateSelectionVisuals()
	end

	rebuildSegments(items)

	local api = {
		Root = root,
		Hub = hub,
		Segments = segments,
	} :: any

	function api:SetSelected(index: number?)
		if index ~= nil and index >= 1 and index <= #items then
			selectedIdx = index
		else
			selectedIdx = nil
		end
		updateSelectionVisuals()
	end

	function api:GetSelected(): number?
		return selectedIdx
	end

	function api:SetItems(nextItems: { RadialWheelItem })
		rebuildSegments(nextItems)
	end

	return api
end

export type CardFanItem = {
	Id: string?,
	Title: string,
	Cost: (number | string)?,
	Body: string?,
	RarityColor: Color3?,
	IconKey: string?,
	IconFallback: string?,
}

export type CardFanOptions = {
	Name: string?,
	Parent: Instance?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	CardSize: Vector2?,
	MaxAngleDeg: number?,
	ArcDropPx: number?,
	HoverLiftPx: number?,
	Cards: { CardFanItem }?,
	ZIndex: number?,
	OnCardClick: ((index: number, card: CardFanItem, button: GuiButton) -> ())?,
}

function UIKit.CreateCardFan(opts: CardFanOptions?)
	local o = (opts or {}) :: CardFanOptions
	local baseZ = o.ZIndex or 6
	local cardSize = o.CardSize or Vector2.new(112, 152)
	local cardW = math.max(52, cardSize.X)
	local cardH = math.max(64, cardSize.Y)
	local maxAngle = math.clamp(o.MaxAngleDeg or 22, 0, 45)
	local arcDrop = math.max(0, o.ArcDropPx or 24)
	local hoverLift = math.max(8, o.HoverLiftPx or 22)
	local minHeight = cardH + arcDrop + hoverLift + 16

	local root = Instance.new("Frame")
	root.Name = o.Name or "CardFan"
	root.Size = o.Size or UDim2.fromOffset(560, math.max(214, minHeight))
	root.Position = o.Position or UDim2.new(0.5, 0, 1, -12)
	root.AnchorPoint = o.AnchorPoint or Vector2.new(0.5, 1)
	root.BackgroundTransparency = 1
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	root.Parent = o.Parent

	local defaultCards: { CardFanItem } = {
		{ Id = "strike", Title = "Sun Strike", Cost = 1, Body = "Deal 12 DMG", RarityColor = UIKit.Tokens.Rarity.Common, IconKey = "sword", IconFallback = "S" },
		{ Id = "guard", Title = "Iron Ward", Cost = 1, Body = "Gain 10 Block", RarityColor = UIKit.Tokens.Rarity.Uncommon, IconKey = "shield", IconFallback = "G" },
		{ Id = "nova", Title = "Arc Nova", Cost = 2, Body = "18 AoE + Burn", RarityColor = UIKit.Tokens.Rarity.Rare, IconKey = "bolt", IconFallback = "N" },
		{ Id = "surge", Title = "Mana Surge", Cost = 0, Body = "Draw 2 Cards", RarityColor = UIKit.Tokens.Rarity.Epic, IconKey = "gem", IconFallback = "M" },
		{ Id = "crown", Title = "Royal Decree", Cost = 3, Body = "Double Buffs", RarityColor = UIKit.Tokens.Rarity.Legendary, IconKey = "crown", IconFallback = "R" },
	}
	local cards: { CardFanItem } = if o.Cards and #o.Cards > 0 then o.Cards else defaultCards
	local cardButtons: { GuiButton } = {}
	local selectedIdx: number? = nil

	local function rebuildCards(nextCards: { CardFanItem })
		for _, oldBtn in ipairs(cardButtons) do
			oldBtn:Destroy()
		end
		table.clear(cardButtons)
		cards = if #nextCards > 0 then nextCards else defaultCards
		local count = #cards
		local totalSpan = math.min(420, math.max(0, (count - 1) * math.floor(cardW * 0.78)))
		local halfSpan = totalSpan * 0.5

		for i = 1, count do
			local card = cards[i]
			local t = if count <= 1 then 0 else (-1 + 2 * (i - 1) / (count - 1))
			local angleDeg = t * maxAngle
			local arcY = math.round((t * t) * arcDrop)
			local xOff = math.round(t * halfSpan)
			local baseYOff = -(8 + arcDrop) + arcY
			local restPos = UDim2.new(0.5, xOff, 1, baseYOff)
			local liftPos = UDim2.new(0.5, xOff, 1, baseYOff - hoverLift)
			local restZ = baseZ + i
			local rarityCol = card.RarityColor or UIKit.Tokens.Colors.Primary

			local btn = Instance.new("TextButton")
			btn.Name = "Card_" .. tostring(i)
			btn.Size = UDim2.fromOffset(cardW, cardH)
			btn.Position = restPos
			btn.AnchorPoint = Vector2.new(0.5, 1)
			btn.Rotation = angleDeg
			btn.BackgroundColor3 = UIKit.Tokens.Colors.BgPanel
			btn.Text = ""
			btn.AutoButtonColor = false
			btn.BorderSizePixel = 0
			btn.ZIndex = restZ
			btn:SetAttribute("CardId", card.Id or card.Title)
			btn.Parent = root
			UIKit.EnsureMinTouchTarget(btn, 44)

			local corner = Instance.new("UICorner")
			corner.CornerRadius = UIKit.Tokens.Radii.Button
			corner.Parent = btn

			UIKit.ApplyGlossySurface(btn, {
				GradientKey = "Panel",
				BaseColor = UIKit.Tokens.Colors.BgPanel,
				CornerRadius = UIKit.Tokens.Radii.Button,
				StrokeColor = UIKit.Tokens.Colors.OutlineInk,
				StrokeThickness = 2.6,
				InnerHighlight = true,
			})

			local stripe = Instance.new("Frame")
			stripe.Name = "RarityHeader"
			stripe.Size = UDim2.new(1, -10, 0, 24)
			stripe.Position = UDim2.fromOffset(5, 6)
			stripe.BackgroundColor3 = rarityCol
			stripe.BorderSizePixel = 0
			stripe.ZIndex = restZ + 1
			stripe.Parent = btn

			local stCorner = Instance.new("UICorner")
			stCorner.CornerRadius = UIKit.Tokens.Radii.Xs
			stCorner.Parent = stripe

			local titleLbl = Instance.new("TextLabel")
			titleLbl.Name = "Title"
			titleLbl.Size = UDim2.new(1, -28, 1, 0)
			titleLbl.Position = UDim2.fromOffset(24, 0)
			titleLbl.BackgroundTransparency = 1
			titleLbl.Text = card.Title
			titleLbl.TextColor3 = UIKit.PickReadableTextColor(rarityCol)
			titleLbl.TextSize = 11
			titleLbl.TextXAlignment = Enum.TextXAlignment.Left
			titleLbl.TextTruncate = Enum.TextTruncate.AtEnd
			titleLbl.FontFace = UIKit.Tokens.Fonts.Title
			titleLbl.ZIndex = restZ + 2
			titleLbl.Parent = stripe

			local costBadge = Instance.new("Frame")
			costBadge.Name = "CostBadge"
			costBadge.Size = UDim2.fromOffset(24, 24)
			costBadge.Position = UDim2.fromOffset(2, 2)
			costBadge.BackgroundColor3 = UIKit.Tokens.Colors.Gold
			costBadge.BorderSizePixel = 0
			costBadge.ZIndex = restZ + 3
			costBadge.Parent = btn

			local cbCorner = Instance.new("UICorner")
			cbCorner.CornerRadius = UDim.new(1, 0)
			cbCorner.Parent = costBadge

			local cbStroke = Instance.new("UIStroke")
			cbStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
			cbStroke.Color = UIKit.Tokens.Colors.OutlineInk
			cbStroke.Thickness = 1.6
			cbStroke.Parent = costBadge

			local costLbl = Instance.new("TextLabel")
			costLbl.Name = "CostText"
			costLbl.Size = UDim2.fromScale(1, 1)
			costLbl.BackgroundTransparency = 1
			costLbl.Text = tostring(if card.Cost ~= nil then card.Cost else 1)
			costLbl.TextColor3 = UIKit.PickReadableTextColor(UIKit.Tokens.Colors.Gold)
			costLbl.TextSize = 12
			costLbl.FontFace = UIKit.Tokens.Fonts.Mono
			costLbl.ZIndex = restZ + 4
			costLbl.Parent = costBadge

			local artBox = Instance.new("Frame")
			artBox.Name = "ArtMedallion"
			artBox.Size = UDim2.new(1, -16, 0, math.max(36, math.floor(cardH * 0.34)))
			artBox.Position = UDim2.fromOffset(8, 34)
			artBox.BackgroundColor3 = UIKit.Tokens.Colors.BgCard
			artBox.BorderSizePixel = 0
			artBox.ZIndex = restZ + 1
			artBox.Parent = btn

			local artCorner = Instance.new("UICorner")
			artCorner.CornerRadius = UIKit.Tokens.Radii.Xs
			artCorner.Parent = artBox

			local icon = UIKit.CreateBadgeIcon(artBox, card.IconKey or "star", card.IconFallback or "*", rarityCol, 28)
			icon.Position = UDim2.fromScale(0.5, 0.5)
			icon.AnchorPoint = Vector2.new(0.5, 0.5)
			icon.ZIndex = restZ + 2

			local bodyLbl = Instance.new("TextLabel")
			bodyLbl.Name = "Body"
			bodyLbl.Size = UDim2.new(1, -14, 1, -(42 + math.max(36, math.floor(cardH * 0.34))))
			bodyLbl.Position = UDim2.fromOffset(7, 38 + math.max(36, math.floor(cardH * 0.34)))
			bodyLbl.BackgroundTransparency = 1
			bodyLbl.Text = card.Body or ""
			bodyLbl.TextColor3 = UIKit.Tokens.Colors.TextSecondary
			bodyLbl.TextSize = 11
			bodyLbl.TextWrapped = true
			bodyLbl.TextTruncate = Enum.TextTruncate.AtEnd
			bodyLbl.FontFace = UIKit.Tokens.Fonts.Body
			bodyLbl.ZIndex = restZ + 2
			bodyLbl.Parent = btn

			local scale = Instance.new("UIScale")
			scale.Name = "HoverScale"
			scale.Scale = 1
			scale.Parent = btn

			local liftTween = TweenInfo.new(0.14, Enum.EasingStyle.Back, Enum.EasingDirection.Out)
			local restTween = TweenInfo.new(0.14, Enum.EasingStyle.Quad, Enum.EasingDirection.Out)

			local function setHovered(hovering: boolean)
				if hovering then
					btn.ZIndex = baseZ + count + 10
					UIKit.Tween(btn, liftTween, { Position = liftPos, Rotation = angleDeg * 0.25 })
					UIKit.Tween(scale, liftTween, { Scale = 1.06 })
				else
					btn.ZIndex = restZ
					UIKit.Tween(btn, restTween, { Position = restPos, Rotation = angleDeg })
					UIKit.Tween(scale, restTween, { Scale = 1.0 })
				end
			end

			btn.MouseEnter:Connect(function()
				setHovered(true)
			end)
			btn.MouseLeave:Connect(function()
				if selectedIdx ~= i then
					setHovered(false)
				end
			end)
			btn.SelectionGained:Connect(function()
				setHovered(true)
			end)
			btn.SelectionLost:Connect(function()
				if selectedIdx ~= i then
					setHovered(false)
				end
			end)
			btn.Activated:Connect(function()
				selectedIdx = i
				if o.OnCardClick then
					o.OnCardClick(i, card, btn)
				end
			end)

			table.insert(cardButtons, btn)
		end
	end

	rebuildCards(cards)

	local api = {
		Root = root,
		Cards = cardButtons,
	} :: any

	function api:SetCards(nextCards: { CardFanItem })
		selectedIdx = nil
		rebuildCards(nextCards)
	end

	function api:SetSelected(index: number?)
		selectedIdx = index
	end

	return api
end

export type BookTabItem = {
	Id: string?,
	Label: string,
	Color: Color3?,
	IconKey: string?,
	IconFallback: string?,
}

export type BookSpreadOptions = {
	Name: string?,
	Parent: Instance?,
	Size: UDim2?,
	Position: UDim2?,
	AnchorPoint: Vector2?,
	BookTitle: string?,
	Tabs: { BookTabItem }?,
	PageColor: Color3?,
	CoverColor: Color3?,
	ShowClose: boolean?,
	ZIndex: number?,
	OnTabChanged: ((index: number, tabId: string, leftPage: Frame, rightPage: Frame) -> ())?,
	OnClose: (() -> ())?,
}

function UIKit.CreateBookSpread(opts: BookSpreadOptions?)
	local o = (opts or {}) :: BookSpreadOptions
	local baseZ = o.ZIndex or 12
	local tabWidth = 64
	local isLight = UIKit.Tokens.Meta.SurfaceMode == "light"
	local pageColor = o.PageColor or (if isLight then UIKit.Tokens.Colors.BgPanel else UIKit.Tokens.Colors.BgCard)
	local coverColor = o.CoverColor or UIKit.Tokens.Colors.Primary:Lerp(UIKit.Tokens.Colors.OutlineInk, 0.45)
	local pageInk = UIKit.PickReadableTextColor(pageColor)

	local root = Instance.new("Frame")
	root.Name = o.Name or "BookSpread"
	root.Size = o.Size or UDim2.fromOffset(680, 420)
	root.Position = o.Position or UDim2.fromScale(0.5, 0.5)
	root.AnchorPoint = o.AnchorPoint or Vector2.new(0.5, 0.5)
	root.BackgroundTransparency = 1
	root.BorderSizePixel = 0
	root.ZIndex = baseZ
	root.Parent = o.Parent

	local tabColumn = Instance.new("Frame")
	tabColumn.Name = "BookmarkTabs"
	tabColumn.Size = UDim2.new(0, tabWidth + 6, 1, -48)
	tabColumn.Position = UDim2.new(1, -(tabWidth + 6), 0, 28)
	tabColumn.BackgroundTransparency = 1
	tabColumn.BorderSizePixel = 0
	tabColumn.ZIndex = baseZ + 1
	tabColumn.Parent = root

	local tabList = Instance.new("UIListLayout")
	tabList.FillDirection = Enum.FillDirection.Vertical
	tabList.HorizontalAlignment = Enum.HorizontalAlignment.Right
	tabList.SortOrder = Enum.SortOrder.LayoutOrder
	tabList.Padding = UDim.new(0, 8)
	tabList.Parent = tabColumn

	local cover = Instance.new("Frame")
	cover.Name = "BookCover"
	cover.Size = UDim2.new(1, -(tabWidth - 6), 1, 0)
	cover.Position = UDim2.fromOffset(0, 0)
	cover.BackgroundColor3 = coverColor
	cover.BorderSizePixel = 0
	cover.ZIndex = baseZ + 2
	cover.Parent = root

	local cCorner = Instance.new("UICorner")
	cCorner.CornerRadius = UIKit.Tokens.Radii.Panel
	cCorner.Parent = cover

	UIKit.AttachStackedStrokes(cover, {
		OuterColor = UIKit.Tokens.Colors.OutlineInk,
		OuterThickness = UIKit.Tokens.Strokes.Panel,
		InnerColor = UIKit.Tokens.Colors.Gold,
		InnerThickness = 1.6,
		InnerTransparency = 0.45,
		CornerRadius = UIKit.Tokens.Radii.Panel,
	})

	local spread = Instance.new("Frame")
	spread.Name = "Spread"
	spread.Size = UDim2.new(1, -20, 1, -20)
	spread.Position = UDim2.fromOffset(10, 10)
	spread.BackgroundTransparency = 1
	spread.BorderSizePixel = 0
	spread.ZIndex = baseZ + 3
	spread.Parent = cover

	local function buildPage(pageName: string, posXScale: number, posXOffset: number): Frame
		local page = Instance.new("Frame")
		page.Name = pageName
		page.Size = UDim2.new(0.5, -3, 1, 0)
		page.Position = UDim2.new(posXScale, posXOffset, 0, 0)
		page.BackgroundColor3 = pageColor
		page.BorderSizePixel = 0
		page.ZIndex = baseZ + 3
		page.Parent = spread

		local pCorner = Instance.new("UICorner")
		pCorner.CornerRadius = UIKit.Tokens.Radii.Small
		pCorner.Parent = page

		local pStroke = Instance.new("UIStroke")
		pStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		pStroke.Color = UIKit.Tokens.Colors.BorderSubtle
		pStroke.Thickness = 1.5
		pStroke.Transparency = 0.2
		pStroke.Parent = page

		local pad = Instance.new("UIPadding")
		pad.PaddingTop = UDim.new(0, 14)
		pad.PaddingBottom = UDim.new(0, 14)
		pad.PaddingLeft = UDim.new(0, 16)
		pad.PaddingRight = UDim.new(0, 16)
		pad.Parent = page

		return page
	end

	local leftPage = buildPage("LeftPage", 0, 0)
	local rightPage = buildPage("RightPage", 0.5, 3)

	if o.BookTitle and o.BookTitle ~= "" then
		local titleHdr = Instance.new("TextLabel")
		titleHdr.Name = "BookTitle"
		titleHdr.Size = UDim2.new(1, 0, 0, 26)
		titleHdr.BackgroundTransparency = 1
		titleHdr.Text = o.BookTitle
		titleHdr.TextColor3 = pageInk
		titleHdr.TextSize = 18
		titleHdr.TextXAlignment = Enum.TextXAlignment.Left
		titleHdr.TextTruncate = Enum.TextTruncate.AtEnd
		titleHdr.FontFace = UIKit.Tokens.Fonts.Title
		titleHdr.ZIndex = baseZ + 4
		titleHdr.Parent = leftPage
	end

	local spineShadow = Instance.new("Frame")
	spineShadow.Name = "SpineShadow"
	spineShadow.Size = UDim2.new(0, 24, 1, 4)
	spineShadow.Position = UDim2.fromScale(0.5, 0.5)
	spineShadow.AnchorPoint = Vector2.new(0.5, 0.5)
	spineShadow.BackgroundColor3 = UIKit.Tokens.Colors.OutlineInk
	spineShadow.BackgroundTransparency = 0
	spineShadow.BorderSizePixel = 0
	spineShadow.Active = false
	spineShadow.ZIndex = baseZ + 5
	spineShadow.Parent = spread

	local spineGrad = Instance.new("UIGradient")
	spineGrad.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0.0, 1.0),
		NumberSequenceKeypoint.new(0.35, 0.72),
		NumberSequenceKeypoint.new(0.50, 0.30),
		NumberSequenceKeypoint.new(0.65, 0.72),
		NumberSequenceKeypoint.new(1.0, 1.0),
	})
	spineGrad.Parent = spineShadow

	local spineCrease = Instance.new("Frame")
	spineCrease.Name = "SpineCrease"
	spineCrease.Size = UDim2.new(0, 2, 1, -8)
	spineCrease.Position = UDim2.fromScale(0.5, 0.5)
	spineCrease.AnchorPoint = Vector2.new(0.5, 0.5)
	spineCrease.BackgroundColor3 = UIKit.Tokens.Colors.OutlineInk
	spineCrease.BackgroundTransparency = 0.25
	spineCrease.BorderSizePixel = 0
	spineCrease.Active = false
	spineCrease.ZIndex = baseZ + 6
	spineCrease.Parent = spineShadow

	local closeBtn: GuiButton? = nil
	if o.ShowClose ~= false then
		closeBtn = UIKit.CreateButton({
			Name = "CloseButton",
			Parent = cover,
			Text = "X",
			Variant = "Danger",
			Size = UDim2.fromOffset(44, 44),
			Position = UDim2.new(1, -8, 0, 8),
			AnchorPoint = Vector2.new(1, 0),
			TextSize = 15,
			OnClick = function()
				if o.OnClose then
					o.OnClose()
				else
					root.Visible = false
				end
			end,
		})
		if closeBtn then
			closeBtn.ZIndex = baseZ + 8
		end
	end

	local defaultTabs: { BookTabItem } = {
		{ Id = "quests", Label = "Quests", Color = UIKit.Tokens.Colors.Primary },
		{ Id = "bestiary", Label = "Index", Color = UIKit.Tokens.Colors.Secondary },
		{ Id = "recipes", Label = "Craft", Color = UIKit.Tokens.Colors.Success },
		{ Id = "map", Label = "Map", Color = UIKit.Tokens.Colors.Accent },
	}
	local tabs: { BookTabItem } = if o.Tabs and #o.Tabs > 0 then o.Tabs else defaultTabs
	local tabButtons: { TextButton } = {}
	local activeIndex = 1

	local function refreshTabs()
		for idx, btn in ipairs(tabButtons) do
			local tData = tabs[idx]
			local isActive = (idx == activeIndex)
			local tCol = (tData and tData.Color) or UIKit.Tokens.Colors.Primary
			btn.BackgroundColor3 = if isActive then tCol else UIKit.Tokens.Colors.BgPanel
			btn.Size = if isActive then UDim2.fromOffset(tabWidth + 6, 48) else UDim2.fromOffset(tabWidth - 2, 46)
			local txt = btn:FindFirstChild("TabLabel")
			if txt and txt:IsA("TextLabel") then
				txt.TextColor3 = if isActive then UIKit.PickReadableTextColor(tCol) else UIKit.Tokens.Colors.TextSecondary
			end
		end
	end

	for idx, tab in ipairs(tabs) do
		local tCol = tab.Color or UIKit.Tokens.Colors.Primary
		local tabBtn = Instance.new("TextButton")
		tabBtn.Name = "Tab_" .. tostring(tab.Id or idx)
		tabBtn.LayoutOrder = idx
		tabBtn.Size = UDim2.fromOffset(tabWidth, 46)
		tabBtn.BackgroundColor3 = tCol
		tabBtn.Text = ""
		tabBtn.AutoButtonColor = false
		tabBtn.BorderSizePixel = 0
		tabBtn.ZIndex = baseZ + 1
		tabBtn:SetAttribute("TabId", tab.Id or tab.Label)
		tabBtn.Parent = tabColumn
		UIKit.EnsureMinTouchTarget(tabBtn, 44)

		local tCorner = Instance.new("UICorner")
		tCorner.CornerRadius = UIKit.Tokens.Radii.Small
		tCorner.Parent = tabBtn

		local tStroke = Instance.new("UIStroke")
		tStroke.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
		tStroke.Color = UIKit.Tokens.Colors.OutlineInk
		tStroke.Thickness = 2.4
		tStroke.Parent = tabBtn

		local tLbl = Instance.new("TextLabel")
		tLbl.Name = "TabLabel"
		tLbl.Size = UDim2.new(1, -8, 1, 0)
		tLbl.Position = UDim2.fromOffset(6, 0)
		tLbl.BackgroundTransparency = 1
		tLbl.Text = tab.Label
		tLbl.TextColor3 = UIKit.Tokens.Colors.TextPrimary
		tLbl.TextSize = 11
		tLbl.TextTruncate = Enum.TextTruncate.AtEnd
		tLbl.FontFace = UIKit.Tokens.Fonts.Title
		tLbl.ZIndex = baseZ + 2
		tLbl.Parent = tabBtn

		UIKit.AttachButtonJuice(tabBtn, tabBtn, function()
			activeIndex = idx
			refreshTabs()
			if o.OnTabChanged then
				o.OnTabChanged(idx, tab.Id or tab.Label, leftPage, rightPage)
			end
		end)

		table.insert(tabButtons, tabBtn)
	end

	refreshTabs()

	local api = {
		Root = root,
		Cover = cover,
		LeftPage = leftPage,
		RightPage = rightPage,
		SpineShadow = spineShadow,
		TabButtons = tabButtons,
		CloseButton = closeBtn,
	} :: any

	function api:SetActiveTab(indexOrId: number | string)
		if typeof(indexOrId) == "number" then
			activeIndex = math.clamp(indexOrId, 1, #tabs)
		else
			for i, t in ipairs(tabs) do
				if t.Id == indexOrId or t.Label == indexOrId then
					activeIndex = i
					break
				end
			end
		end
		refreshTabs()
		local chosen = tabs[activeIndex]
		if chosen and o.OnTabChanged then
			o.OnTabChanged(activeIndex, chosen.Id or chosen.Label, leftPage, rightPage)
		end
	end

	function api:GetActiveTab(): number
		return activeIndex
	end

	return api
end

return UIKit

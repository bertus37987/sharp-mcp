--!strict
--[[
	AtmospherePresets
	Curated Roblox Lighting, Atmosphere, Clouds, Sky, GlobalWind, Terrain Water/Grass,
	and PostEffect presets with non-destructive snapshot/restore support.

	Verified engine guardrails:
	- NEVER writes Lighting.Technology (RobloxScriptSecurity + deprecated). Uses
	  Lighting.LightingStyle + Lighting.PrioritizeLightingQuality instead.
	- ALWAYS parents Clouds under Workspace.Terrain (Clouds elsewhere never renders).
	- ALWAYS parents ColorGradingEffect under Lighting (ignored under Camera/elsewhere).
	- Ensures Atmosphere.Haze > 0 whenever Glare > 0 (Decay also requires Haze > 0 and Glare > 0).
]]

local Lighting = game:GetService("Lighting")
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

export type PresetName =
	"DaylightMeadow"
	| "GoldenSunset"
	| "GoldenHour"
	| "StormyCoast"
	| "MoonlitNight"
	| "VolcanicAsh"
	| "ClearMedDay"
	| "MistyDawn"
	| "OvercastStorm"
	| "CyberpunkNight"
	| "DesertHeat"
	| "HorrorFog"

export type LightingSpec = {
	ClockTime: number,
	GeographicLatitude: number,
	Brightness: number,
	Ambient: Color3,
	OutdoorAmbient: Color3,
	ColorShift_Bottom: Color3,
	ColorShift_Top: Color3,
	EnvironmentDiffuseScale: number,
	EnvironmentSpecularScale: number,
	ExposureCompensation: number,
	GlobalShadows: boolean,
	ShadowSoftness: number,
	LightingStyle: Enum.LightingStyle?,
	PrioritizeLightingQuality: boolean?,
}

export type AtmosphereSpec = {
	Density: number,
	Offset: number,
	Color: Color3,
	Decay: Color3,
	Glare: number,
	Haze: number,
}

export type CloudsSpec = {
	Enabled: boolean,
	Cover: number,
	Density: number,
	Color: Color3,
}

export type SkySpec = {
	CelestialBodiesShown: boolean,
	StarCount: number,
	SunAngularSize: number,
	MoonAngularSize: number,
	SkyboxOrientation: Vector3?,
}

export type WaterSpec = {
	WaterColor: Color3,
	WaterTransparency: number,
	WaterReflectance: number,
	WaterWaveSize: number,
	WaterWaveSpeed: number,
}

export type GrassSpec = {
	Decoration: boolean,
	GrassLength: number,
}

export type BloomSpec = {
	Enabled: boolean,
	Intensity: number,
	Size: number,
	Threshold: number,
}

export type ColorCorrectionSpec = {
	Enabled: boolean,
	Brightness: number,
	Contrast: number,
	Saturation: number,
	TintColor: Color3,
}

export type ColorGradingSpec = {
	Enabled: boolean,
	TonemapperPreset: Enum.TonemapperPreset,
}

export type SunRaysSpec = {
	Enabled: boolean,
	Intensity: number,
	Spread: number,
}

export type DepthOfFieldSpec = {
	Enabled: boolean,
	FarIntensity: number,
	FocusDistance: number,
	InFocusRadius: number,
	NearIntensity: number,
}

export type PostEffectsSpec = {
	Bloom: BloomSpec?,
	ColorCorrection: ColorCorrectionSpec?,
	ColorGrading: ColorGradingSpec?,
	SunRays: SunRaysSpec?,
	DepthOfField: DepthOfFieldSpec?,
}

export type PresetSpec = {
	Name: string,
	Description: string,
	Lighting: LightingSpec,
	Atmosphere: AtmosphereSpec,
	Clouds: CloudsSpec,
	Sky: SkySpec,
	GlobalWind: Vector3,
	Water: WaterSpec,
	Grass: GrassSpec,
	PostEffects: PostEffectsSpec,
}

export type ApplyOptions = {
	ApplyWater: boolean?,
	ApplyGrass: boolean?,
	ApplyWind: boolean?,
	ApplyPostEffects: boolean?,
	CleanLegacyFog: boolean?,
}

export type ApplyReport = {
	PresetName: string,
	Warnings: { string },
	CreatedInstances: { string },
	UpdatedInstances: { string },
}

type SnapshotRecord = {
	Instance: Instance?,
	Existed: boolean,
	Parent: Instance?,
	Properties: { [string]: any },
}

export type EnvironmentSnapshot = {
	LightingProps: { [string]: any },
	GlobalWind: Vector3,
	TerrainProps: { [string]: any },
	Atmosphere: SnapshotRecord,
	Sky: SnapshotRecord,
	Clouds: SnapshotRecord,
	PostEffects: { [string]: SnapshotRecord },
	CreatedByPreset: { Instance },
}

local AtmospherePresets = {}

local PRESETS: { [PresetName]: PresetSpec } = {
	DaylightMeadow = {
		Name = "DaylightMeadow",
		Description = "Crisp midday sunlight with bright atmospheric perspective, billowing white clouds, and lush swaying grass.",
		Lighting = {
			ClockTime = 14.0,
			GeographicLatitude = 41.7,
			Brightness = 3.0,
			Ambient = Color3.fromRGB(64, 72, 82),
			OutdoorAmbient = Color3.fromRGB(116, 126, 138),
			ColorShift_Bottom = Color3.fromRGB(18, 22, 28),
			ColorShift_Top = Color3.fromRGB(255, 252, 245),
			EnvironmentDiffuseScale = 1.0,
			EnvironmentSpecularScale = 1.0,
			ExposureCompensation = 0.0,
			GlobalShadows = true,
			ShadowSoftness = 0.2,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.28,
			Offset = 0.15,
			Color = Color3.fromRGB(199, 224, 248),
			Decay = Color3.fromRGB(106, 130, 152),
			Glare = 0.18,
			Haze = 0.85,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.54,
			Density = 0.65,
			Color = Color3.fromRGB(255, 255, 255),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 2400,
			SunAngularSize = 21,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(8, 0, 4),
		Water = {
			WaterColor = Color3.fromRGB(48, 128, 156),
			WaterTransparency = 0.35,
			WaterReflectance = 0.85,
			WaterWaveSize = 0.18,
			WaterWaveSpeed = 10,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.72,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.35, Size = 22, Threshold = 1.25 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.02,
				Contrast = 0.06,
				Saturation = 0.08,
				TintColor = Color3.fromRGB(255, 253, 248),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.08, Spread = 0.6 },
		},
	},

	GoldenSunset = {
		Name = "GoldenSunset",
		Description = "Warm low-angle golden hour with strong atmospheric glare, amber horizon decay, and long shadows.",
		Lighting = {
			ClockTime = 17.65,
			GeographicLatitude = 36.0,
			Brightness = 2.6,
			Ambient = Color3.fromRGB(72, 54, 48),
			OutdoorAmbient = Color3.fromRGB(132, 98, 78),
			ColorShift_Bottom = Color3.fromRGB(36, 22, 24),
			ColorShift_Top = Color3.fromRGB(255, 198, 146),
			EnvironmentDiffuseScale = 0.95,
			EnvironmentSpecularScale = 1.0,
			ExposureCompensation = 0.1,
			GlobalShadows = true,
			ShadowSoftness = 0.35,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.36,
			Offset = 0.22,
			Color = Color3.fromRGB(255, 196, 138),
			Decay = Color3.fromRGB(178, 92, 58),
			Glare = 1.6,
			Haze = 2.4,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.62,
			Density = 0.72,
			Color = Color3.fromRGB(255, 212, 174),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 2600,
			SunAngularSize = 24,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(10, 0, -3),
		Water = {
			WaterColor = Color3.fromRGB(64, 114, 128),
			WaterTransparency = 0.30,
			WaterReflectance = 0.95,
			WaterWaveSize = 0.22,
			WaterWaveSpeed = 12,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.78,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.65, Size = 28, Threshold = 1.1 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.03,
				Contrast = 0.10,
				Saturation = 0.12,
				TintColor = Color3.fromRGB(255, 240, 226),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.18, Spread = 0.75 },
		},
	},

	StormyCoast = {
		Name = "StormyCoast",
		Description = "Overcast maritime squall with dense blue-grey haze, dark heavy cloud cover, high wind, and rough waves.",
		Lighting = {
			ClockTime = 15.2,
			GeographicLatitude = 52.0,
			Brightness = 1.8,
			Ambient = Color3.fromRGB(52, 62, 74),
			OutdoorAmbient = Color3.fromRGB(88, 102, 118),
			ColorShift_Bottom = Color3.fromRGB(24, 30, 38),
			ColorShift_Top = Color3.fromRGB(182, 198, 214),
			EnvironmentDiffuseScale = 0.85,
			EnvironmentSpecularScale = 0.75,
			ExposureCompensation = -0.1,
			GlobalShadows = true,
			ShadowSoftness = 0.65,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.50,
			Offset = 0.05,
			Color = Color3.fromRGB(132, 150, 168),
			Decay = Color3.fromRGB(72, 86, 102),
			Glare = 0.0,
			Haze = 4.2,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.88,
			Density = 0.92,
			Color = Color3.fromRGB(118, 130, 146),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 1200,
			SunAngularSize = 18,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(26, 0, 14),
		Water = {
			WaterColor = Color3.fromRGB(32, 74, 92),
			WaterTransparency = 0.22,
			WaterReflectance = 0.70,
			WaterWaveSize = 0.75,
			WaterWaveSpeed = 24,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.85,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.25, Size = 18, Threshold = 1.4 },
			ColorCorrection = {
				Enabled = true,
				Brightness = -0.02,
				Contrast = 0.12,
				Saturation = -0.18,
				TintColor = Color3.fromRGB(228, 238, 248),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = false, Intensity = 0.0, Spread = 0.3 },
		},
	},

	MoonlitNight = {
		Name = "MoonlitNight",
		Description = "Deep midnight sky with bright stars, cool indigo horizon haze, calm water, and readable night ambient.",
		Lighting = {
			ClockTime = 23.2,
			GeographicLatitude = 45.0,
			Brightness = 1.15,
			Ambient = Color3.fromRGB(28, 36, 56),
			OutdoorAmbient = Color3.fromRGB(58, 72, 104),
			ColorShift_Bottom = Color3.fromRGB(14, 18, 30),
			ColorShift_Top = Color3.fromRGB(130, 152, 204),
			EnvironmentDiffuseScale = 0.8,
			EnvironmentSpecularScale = 0.9,
			ExposureCompensation = 0.15,
			GlobalShadows = true,
			ShadowSoftness = 0.45,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.34,
			Offset = 0.12,
			Color = Color3.fromRGB(70, 96, 148),
			Decay = Color3.fromRGB(28, 38, 68),
			Glare = 0.0,
			Haze = 1.8,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.42,
			Density = 0.55,
			Color = Color3.fromRGB(142, 166, 208),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 3500,
			SunAngularSize = 18,
			MoonAngularSize = 14,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(5, 0, 3),
		Water = {
			WaterColor = Color3.fromRGB(22, 48, 78),
			WaterTransparency = 0.28,
			WaterReflectance = 0.90,
			WaterWaveSize = 0.14,
			WaterWaveSpeed = 8,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.65,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.45, Size = 24, Threshold = 1.15 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.0,
				Contrast = 0.08,
				Saturation = -0.10,
				TintColor = Color3.fromRGB(218, 228, 252),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = false, Intensity = 0.0, Spread = 0.25 },
		},
	},

	VolcanicAsh = {
		Name = "VolcanicAsh",
		Description = "Smoldering volcanic caldera with dense ash haze, ember glare, dark clouds, and barren scorched terrain.",
		Lighting = {
			ClockTime = 18.4,
			GeographicLatitude = 20.0,
			Brightness = 2.0,
			Ambient = Color3.fromRGB(62, 42, 36),
			OutdoorAmbient = Color3.fromRGB(112, 74, 58),
			ColorShift_Bottom = Color3.fromRGB(48, 20, 14),
			ColorShift_Top = Color3.fromRGB(224, 142, 104),
			EnvironmentDiffuseScale = 0.8,
			EnvironmentSpecularScale = 0.85,
			ExposureCompensation = -0.05,
			GlobalShadows = true,
			ShadowSoftness = 0.4,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.56,
			Offset = 0.0,
			Color = Color3.fromRGB(184, 118, 88),
			Decay = Color3.fromRGB(98, 46, 32),
			Glare = 0.85,
			Haze = 5.5,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.82,
			Density = 0.88,
			Color = Color3.fromRGB(108, 84, 78),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 800,
			SunAngularSize = 19,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(16, 2, -10),
		Water = {
			WaterColor = Color3.fromRGB(58, 52, 48),
			WaterTransparency = 0.15,
			WaterReflectance = 0.45,
			WaterWaveSize = 0.35,
			WaterWaveSpeed = 14,
		},
		Grass = {
			Decoration = false,
			GrassLength = 0.35,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.75, Size = 26, Threshold = 1.05 },
			ColorCorrection = {
				Enabled = true,
				Brightness = -0.01,
				Contrast = 0.14,
				Saturation = 0.05,
				TintColor = Color3.fromRGB(255, 224, 206),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.12, Spread = 0.5 },
		},
	},

	ClearMedDay = {
		Name = "ClearMedDay",
		Description = "Crisp Mediterranean daylight with azure sky, low atmospheric haze, and sparkling coastal water.",
		Lighting = {
			ClockTime = 13.5,
			GeographicLatitude = 38.0,
			Brightness = 3.1,
			Ambient = Color3.fromRGB(68, 76, 88),
			OutdoorAmbient = Color3.fromRGB(122, 134, 148),
			ColorShift_Bottom = Color3.fromRGB(20, 24, 32),
			ColorShift_Top = Color3.fromRGB(255, 253, 248),
			EnvironmentDiffuseScale = 1.0,
			EnvironmentSpecularScale = 1.0,
			ExposureCompensation = 0.05,
			GlobalShadows = true,
			ShadowSoftness = 0.18,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.24,
			Offset = 0.18,
			Color = Color3.fromRGB(192, 224, 252),
			Decay = Color3.fromRGB(98, 128, 156),
			Glare = 0.22,
			Haze = 0.75,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.46,
			Density = 0.60,
			Color = Color3.fromRGB(255, 255, 255),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 2400,
			SunAngularSize = 21,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(9, 0, 5),
		Water = {
			WaterColor = Color3.fromRGB(36, 138, 168),
			WaterTransparency = 0.38,
			WaterReflectance = 0.88,
			WaterWaveSize = 0.16,
			WaterWaveSpeed = 10,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.70,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.35, Size = 22, Threshold = 1.25 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.02,
				Contrast = 0.06,
				Saturation = 0.10,
				TintColor = Color3.fromRGB(255, 254, 250),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.09, Spread = 0.6 },
		},
	},

	MistyDawn = {
		Name = "MistyDawn",
		Description = "Soft early-morning valley mist with pastel rose-gold horizon decay and gentle dew lighting.",
		Lighting = {
			ClockTime = 6.45,
			GeographicLatitude = 44.0,
			Brightness = 2.1,
			Ambient = Color3.fromRGB(64, 62, 76),
			OutdoorAmbient = Color3.fromRGB(118, 112, 132),
			ColorShift_Bottom = Color3.fromRGB(28, 26, 38),
			ColorShift_Top = Color3.fromRGB(252, 210, 198),
			EnvironmentDiffuseScale = 0.9,
			EnvironmentSpecularScale = 0.95,
			ExposureCompensation = 0.08,
			GlobalShadows = true,
			ShadowSoftness = 0.42,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.44,
			Offset = 0.10,
			Color = Color3.fromRGB(224, 198, 214),
			Decay = Color3.fromRGB(142, 112, 138),
			Glare = 0.95,
			Haze = 3.2,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.58,
			Density = 0.68,
			Color = Color3.fromRGB(246, 218, 224),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 1800,
			SunAngularSize = 22,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(6, 0, 4),
		Water = {
			WaterColor = Color3.fromRGB(58, 108, 128),
			WaterTransparency = 0.32,
			WaterReflectance = 0.92,
			WaterWaveSize = 0.12,
			WaterWaveSpeed = 8,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.76,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.55, Size = 26, Threshold = 1.15 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.02,
				Contrast = 0.05,
				Saturation = 0.04,
				TintColor = Color3.fromRGB(252, 242, 246),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.14, Spread = 0.68 },
		},
	},

	OvercastStorm = {
		Name = "OvercastStorm",
		Description = "Heavy overcast storm front with thick slate clouds, strong wind gusts, and dramatic contrast.",
		Lighting = {
			ClockTime = 14.8,
			GeographicLatitude = 54.0,
			Brightness = 1.65,
			Ambient = Color3.fromRGB(48, 58, 70),
			OutdoorAmbient = Color3.fromRGB(82, 96, 112),
			ColorShift_Bottom = Color3.fromRGB(22, 28, 36),
			ColorShift_Top = Color3.fromRGB(174, 190, 208),
			EnvironmentDiffuseScale = 0.82,
			EnvironmentSpecularScale = 0.75,
			ExposureCompensation = -0.12,
			GlobalShadows = true,
			ShadowSoftness = 0.68,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.52,
			Offset = 0.04,
			Color = Color3.fromRGB(126, 144, 162),
			Decay = Color3.fromRGB(68, 82, 98),
			Glare = 0.15,
			Haze = 4.5,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.90,
			Density = 0.94,
			Color = Color3.fromRGB(112, 124, 140),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 1000,
			SunAngularSize = 18,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(28, 0, 16),
		Water = {
			WaterColor = Color3.fromRGB(30, 68, 86),
			WaterTransparency = 0.20,
			WaterReflectance = 0.68,
			WaterWaveSize = 0.80,
			WaterWaveSpeed = 25,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.85,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.24, Size = 18, Threshold = 1.4 },
			ColorCorrection = {
				Enabled = true,
				Brightness = -0.02,
				Contrast = 0.14,
				Saturation = -0.20,
				TintColor = Color3.fromRGB(224, 236, 248),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = false, Intensity = 0.0, Spread = 0.3 },
		},
	},

	CyberpunkNight = {
		Name = "CyberpunkNight",
		Description = "Neon-drenched cyberpunk midnight with electric indigo/magenta atmosphere and high specular bloom.",
		Lighting = {
			ClockTime = 0.5,
			GeographicLatitude = 35.6,
			Brightness = 1.35,
			Ambient = Color3.fromRGB(32, 28, 64),
			OutdoorAmbient = Color3.fromRGB(64, 52, 118),
			ColorShift_Bottom = Color3.fromRGB(18, 12, 38),
			ColorShift_Top = Color3.fromRGB(148, 112, 244),
			EnvironmentDiffuseScale = 0.85,
			EnvironmentSpecularScale = 1.0,
			ExposureCompensation = 0.18,
			GlobalShadows = true,
			ShadowSoftness = 0.32,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.38,
			Offset = 0.14,
			Color = Color3.fromRGB(88, 64, 168),
			Decay = Color3.fromRGB(164, 48, 132),
			Glare = 0.65,
			Haze = 2.4,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.48,
			Density = 0.62,
			Color = Color3.fromRGB(96, 78, 156),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 3800,
			SunAngularSize = 18,
			MoonAngularSize = 15,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(6, 0, -4),
		Water = {
			WaterColor = Color3.fromRGB(28, 36, 84),
			WaterTransparency = 0.24,
			WaterReflectance = 0.96,
			WaterWaveSize = 0.12,
			WaterWaveSpeed = 9,
		},
		Grass = {
			Decoration = false,
			GrassLength = 0.45,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.85, Size = 32, Threshold = 0.98 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.01,
				Contrast = 0.16,
				Saturation = 0.18,
				TintColor = Color3.fromRGB(236, 224, 255),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = false, Intensity = 0.0, Spread = 0.25 },
		},
	},

	DesertHeat = {
		Name = "DesertHeat",
		Description = "Scorching desert afternoon with intense sun glare, warm sand-colored horizon haze, and arid wind.",
		Lighting = {
			ClockTime = 15.1,
			GeographicLatitude = 24.0,
			Brightness = 3.4,
			Ambient = Color3.fromRGB(84, 68, 52),
			OutdoorAmbient = Color3.fromRGB(148, 122, 92),
			ColorShift_Bottom = Color3.fromRGB(42, 30, 20),
			ColorShift_Top = Color3.fromRGB(255, 232, 188),
			EnvironmentDiffuseScale = 1.0,
			EnvironmentSpecularScale = 0.9,
			ExposureCompensation = 0.12,
			GlobalShadows = true,
			ShadowSoftness = 0.22,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.35,
			Offset = 0.20,
			Color = Color3.fromRGB(244, 212, 162),
			Decay = Color3.fromRGB(186, 132, 78),
			Glare = 1.35,
			Haze = 2.8,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.28,
			Density = 0.42,
			Color = Color3.fromRGB(255, 244, 224),
		},
		Sky = {
			CelestialBodiesShown = true,
			StarCount = 2000,
			SunAngularSize = 25,
			MoonAngularSize = 11,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(18, 0, 8),
		Water = {
			WaterColor = Color3.fromRGB(44, 134, 142),
			WaterTransparency = 0.36,
			WaterReflectance = 0.85,
			WaterWaveSize = 0.14,
			WaterWaveSpeed = 10,
		},
		Grass = {
			Decoration = false,
			GrassLength = 0.30,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.52, Size = 24, Threshold = 1.15 },
			ColorCorrection = {
				Enabled = true,
				Brightness = 0.03,
				Contrast = 0.09,
				Saturation = 0.08,
				TintColor = Color3.fromRGB(255, 244, 224),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = true, Intensity = 0.16, Spread = 0.72 },
		},
	},

	HorrorFog = {
		Name = "HorrorFog",
		Description = "Claustrophobic low-visibility horror fog with cold desaturated slate lighting and eerie stillness.",
		Lighting = {
			ClockTime = 21.5,
			GeographicLatitude = 58.0,
			Brightness = 0.85,
			Ambient = Color3.fromRGB(22, 26, 30),
			OutdoorAmbient = Color3.fromRGB(44, 52, 58),
			ColorShift_Bottom = Color3.fromRGB(10, 12, 14),
			ColorShift_Top = Color3.fromRGB(112, 128, 136),
			EnvironmentDiffuseScale = 0.65,
			EnvironmentSpecularScale = 0.60,
			ExposureCompensation = -0.18,
			GlobalShadows = true,
			ShadowSoftness = 0.55,
			LightingStyle = Enum.LightingStyle.Realistic,
			PrioritizeLightingQuality = true,
		},
		Atmosphere = {
			Density = 0.68,
			Offset = 0.02,
			Color = Color3.fromRGB(92, 106, 114),
			Decay = Color3.fromRGB(36, 44, 50),
			Glare = 0.10,
			Haze = 6.5,
		},
		Clouds = {
			Enabled = true,
			Cover = 0.92,
			Density = 0.95,
			Color = Color3.fromRGB(74, 84, 92),
		},
		Sky = {
			CelestialBodiesShown = false,
			StarCount = 400,
			SunAngularSize = 14,
			MoonAngularSize = 12,
			SkyboxOrientation = Vector3.zero,
		},
		GlobalWind = Vector3.new(3, 0, 2),
		Water = {
			WaterColor = Color3.fromRGB(20, 32, 36),
			WaterTransparency = 0.14,
			WaterReflectance = 0.50,
			WaterWaveSize = 0.08,
			WaterWaveSpeed = 5,
		},
		Grass = {
			Decoration = true,
			GrassLength = 0.82,
		},
		PostEffects = {
			Bloom = { Enabled = true, Intensity = 0.20, Size = 18, Threshold = 1.35 },
			ColorCorrection = {
				Enabled = true,
				Brightness = -0.04,
				Contrast = 0.15,
				Saturation = -0.35,
				TintColor = Color3.fromRGB(210, 224, 228),
			},
			ColorGrading = { Enabled = true, TonemapperPreset = Enum.TonemapperPreset.Default },
			SunRays = { Enabled = false, Intensity = 0.0, Spread = 0.2 },
		},
	},
}
PRESETS.GoldenHour = PRESETS.GoldenSunset

AtmospherePresets.Presets = PRESETS

local function safeSet(instance: Instance, prop: string, value: any, warnings: { string }?)
	local ok, err = pcall(function()
		(instance :: any)[prop] = value
	end)
	if not ok and warnings then
		table.insert(warnings, string.format("Failed setting %s.%s: %s", instance.Name, prop, tostring(err)))
	end
end

local function safeGet(instance: Instance, prop: string): (boolean, any)
	return pcall(function()
		return (instance :: any)[prop]
	end)
end

local function captureProperties(instance: Instance, propNames: { string }): { [string]: any }
	local out: { [string]: any } = {}
	for _, prop in ipairs(propNames) do
		local ok, val = safeGet(instance, prop)
		if ok then
			out[prop] = val
		end
	end
	return out
end

local function getOrCreateChild(
	parent: Instance,
	className: string,
	defaultName: string,
	report: ApplyReport?
): Instance
	local existing = parent:FindFirstChildOfClass(className)
	if existing then
		if report then
			table.insert(report.UpdatedInstances, existing:GetFullName())
		end
		return existing
	end
	local created = Instance.new(className)
	created.Name = defaultName
	created.Parent = parent
	if report then
		table.insert(report.CreatedInstances, created:GetFullName())
	end
	return created
end

local function captureInstanceSnapshot(parent: Instance, className: string, propNames: { string }): SnapshotRecord
	local inst = parent:FindFirstChildOfClass(className)
	if inst then
		return {
			Instance = inst,
			Existed = true,
			Parent = inst.Parent,
			Properties = captureProperties(inst, propNames),
		}
	end
	return {
		Instance = nil,
		Existed = false,
		Parent = nil,
		Properties = {},
	}
end

function AtmospherePresets.GetPresetNames(): { PresetName }
	local names: { PresetName } = {}
	for k in pairs(PRESETS) do
		table.insert(names, k :: PresetName)
	end
	table.sort(names)
	return names
end

function AtmospherePresets.SnapshotEnvironment(): EnvironmentSnapshot
	local terrain = Workspace.Terrain
	local snapshot: EnvironmentSnapshot = {
		LightingProps = captureProperties(Lighting, {
			"ClockTime",
			"GeographicLatitude",
			"Brightness",
			"Ambient",
			"OutdoorAmbient",
			"ColorShift_Bottom",
			"ColorShift_Top",
			"EnvironmentDiffuseScale",
			"EnvironmentSpecularScale",
			"ExposureCompensation",
			"GlobalShadows",
			"ShadowSoftness",
			"LightingStyle",
			"PrioritizeLightingQuality",
			"FogStart",
			"FogEnd",
			"FogColor",
		}),
		GlobalWind = Workspace.GlobalWind,
		TerrainProps = captureProperties(terrain, {
			"WaterColor",
			"WaterTransparency",
			"WaterReflectance",
			"WaterWaveSize",
			"WaterWaveSpeed",
			"Decoration",
			"GrassLength",
		}),
		Atmosphere = captureInstanceSnapshot(
			Lighting,
			"Atmosphere",
			{ "Density", "Offset", "Color", "Decay", "Glare", "Haze" }
		),
		Sky = captureInstanceSnapshot(
			Lighting,
			"Sky",
			{ "CelestialBodiesShown", "StarCount", "SunAngularSize", "MoonAngularSize", "SkyboxOrientation" }
		),
		Clouds = captureInstanceSnapshot(terrain, "Clouds", { "Enabled", "Cover", "Density", "Color" }),
		PostEffects = {
			BloomEffect = captureInstanceSnapshot(
				Lighting,
				"BloomEffect",
				{ "Enabled", "Intensity", "Size", "Threshold" }
			),
			ColorCorrectionEffect = captureInstanceSnapshot(
				Lighting,
				"ColorCorrectionEffect",
				{ "Enabled", "Brightness", "Contrast", "Saturation", "TintColor" }
			),
			ColorGradingEffect = captureInstanceSnapshot(
				Lighting,
				"ColorGradingEffect",
				{ "Enabled", "TonemapperPreset" }
			),
			SunRaysEffect = captureInstanceSnapshot(Lighting, "SunRaysEffect", { "Enabled", "Intensity", "Spread" }),
			DepthOfFieldEffect = captureInstanceSnapshot(
				Lighting,
				"DepthOfFieldEffect",
				{ "Enabled", "FarIntensity", "FocusDistance", "InFocusRadius", "NearIntensity" }
			),
		},
		CreatedByPreset = {},
	}
	return snapshot
end

function AtmospherePresets.RestoreEnvironment(snapshot: EnvironmentSnapshot)
	local terrain = Workspace.Terrain

	for prop, val in pairs(snapshot.LightingProps) do
		safeSet(Lighting, prop, val, nil)
	end
	Workspace.GlobalWind = snapshot.GlobalWind
	for prop, val in pairs(snapshot.TerrainProps) do
		safeSet(terrain, prop, val, nil)
	end

	local function restoreRecord(record: SnapshotRecord, parentFallback: Instance, className: string)
		if record.Existed and record.Instance then
			record.Instance.Parent = record.Parent or parentFallback
			for prop, val in pairs(record.Properties) do
				safeSet(record.Instance, prop, val, nil)
			end
		elseif not record.Existed then
			local leftover = parentFallback:FindFirstChildOfClass(className)
			if leftover then
				leftover:Destroy()
			end
		end
	end

	restoreRecord(snapshot.Atmosphere, Lighting, "Atmosphere")
	restoreRecord(snapshot.Sky, Lighting, "Sky")
	restoreRecord(snapshot.Clouds, terrain, "Clouds")

	for className, rec in pairs(snapshot.PostEffects) do
		restoreRecord(rec, Lighting, className)
	end

	for _, created in ipairs(snapshot.CreatedByPreset) do
		if created and created.Parent then
			created:Destroy()
		end
	end
end

function AtmospherePresets.ApplyPreset(nameOrSpec: PresetName | PresetSpec, options: ApplyOptions?): ApplyReport
	local spec: PresetSpec
	if type(nameOrSpec) == "string" then
		local found = PRESETS[nameOrSpec :: PresetName]
		assert(found ~= nil, string.format("Unknown preset '%s'", tostring(nameOrSpec)))
		spec = found
	else
		spec = nameOrSpec :: PresetSpec
	end

	local opts: ApplyOptions = options or {}
	local applyWater = if opts.ApplyWater == nil then true else opts.ApplyWater
	local applyGrass = if opts.ApplyGrass == nil then true else opts.ApplyGrass
	local applyWind = if opts.ApplyWind == nil then true else opts.ApplyWind
	local applyPost = if opts.ApplyPostEffects == nil then true else opts.ApplyPostEffects
	local cleanLegacyFog = if opts.CleanLegacyFog == nil then true else opts.CleanLegacyFog

	local report: ApplyReport = {
		PresetName = spec.Name,
		Warnings = {},
		CreatedInstances = {},
		UpdatedInstances = {},
	}

	-- 1. Lighting (NEVER write Lighting.Technology: RobloxScriptSecurity + deprecated)
	local lSpec = spec.Lighting
	Lighting.ClockTime = lSpec.ClockTime
	Lighting.GeographicLatitude = lSpec.GeographicLatitude
	Lighting.Brightness = lSpec.Brightness
	Lighting.Ambient = lSpec.Ambient
	Lighting.OutdoorAmbient = lSpec.OutdoorAmbient
	Lighting.ColorShift_Bottom = lSpec.ColorShift_Bottom
	Lighting.ColorShift_Top = lSpec.ColorShift_Top
	Lighting.EnvironmentDiffuseScale = lSpec.EnvironmentDiffuseScale
	Lighting.EnvironmentSpecularScale = lSpec.EnvironmentSpecularScale
	Lighting.ExposureCompensation = lSpec.ExposureCompensation
	Lighting.GlobalShadows = lSpec.GlobalShadows
	Lighting.ShadowSoftness = lSpec.ShadowSoftness
	if lSpec.LightingStyle ~= nil then
		safeSet(Lighting, "LightingStyle", lSpec.LightingStyle, report.Warnings)
	end
	if lSpec.PrioritizeLightingQuality ~= nil then
		safeSet(Lighting, "PrioritizeLightingQuality", lSpec.PrioritizeLightingQuality, report.Warnings)
	end
	if cleanLegacyFog then
		-- Atmosphere automatically suppresses legacy Fog*; push FogEnd high for fallback cleanliness.
		if Lighting.FogEnd < 10000 then
			Lighting.FogEnd = 100000
		end
	end

	-- 2. Atmosphere under Lighting (enforce Haze > 0 when Glare > 0)
	local atmo = getOrCreateChild(Lighting, "Atmosphere", "Atmosphere", report) :: Atmosphere
	local haze = math.clamp(spec.Atmosphere.Haze, 0, 10)
	local glare = math.clamp(spec.Atmosphere.Glare, 0, 10)
	if glare > 0 and haze <= 0 then
		haze = 0.25
		table.insert(report.Warnings, "Atmosphere.Glare > 0 requires Haze > 0; clamped Haze to 0.25.")
	end
	atmo.Density = math.clamp(spec.Atmosphere.Density, 0, 1)
	atmo.Offset = math.clamp(spec.Atmosphere.Offset, 0, 1)
	atmo.Color = spec.Atmosphere.Color
	atmo.Decay = spec.Atmosphere.Decay
	atmo.Glare = glare
	atmo.Haze = haze

	-- 3. Clouds MUST be parented under Workspace.Terrain to render
	local terrain = Workspace.Terrain
	local misplacedClouds = Lighting:FindFirstChildOfClass("Clouds")
	if misplacedClouds then
		table.insert(
			report.Warnings,
			"Found Clouds under Lighting (invisible); Roblox only renders Clouds under Workspace.Terrain."
		)
	end
	local clouds = getOrCreateChild(terrain, "Clouds", "Clouds", report) :: Clouds
	clouds.Enabled = spec.Clouds.Enabled
	clouds.Cover = math.clamp(spec.Clouds.Cover, 0, 1)
	clouds.Density = math.clamp(spec.Clouds.Density, 0, 1)
	clouds.Color = spec.Clouds.Color

	-- 4. Sky under Lighting
	local sky = getOrCreateChild(Lighting, "Sky", "Sky", report) :: Sky
	sky.CelestialBodiesShown = spec.Sky.CelestialBodiesShown
	sky.StarCount = math.clamp(spec.Sky.StarCount, 0, 5000)
	sky.SunAngularSize = math.clamp(spec.Sky.SunAngularSize, 0, 60)
	sky.MoonAngularSize = math.clamp(spec.Sky.MoonAngularSize, 0, 60)
	if spec.Sky.SkyboxOrientation ~= nil then
		safeSet(sky, "SkyboxOrientation", spec.Sky.SkyboxOrientation, report.Warnings)
	end

	-- 5. GlobalWind & Terrain Water / Grass
	if applyWind then
		Workspace.GlobalWind = spec.GlobalWind
	end
	if applyWater then
		terrain.WaterColor = spec.Water.WaterColor
		terrain.WaterTransparency = math.clamp(spec.Water.WaterTransparency, 0, 1)
		terrain.WaterReflectance = math.clamp(spec.Water.WaterReflectance, 0, 1)
		terrain.WaterWaveSize = math.clamp(spec.Water.WaterWaveSize, 0, 1)
		terrain.WaterWaveSpeed = math.clamp(spec.Water.WaterWaveSpeed, 0, 100)
	end
	if applyGrass then
		safeSet(terrain, "Decoration", spec.Grass.Decoration, report.Warnings)
		safeSet(terrain, "GrassLength", math.clamp(spec.Grass.GrassLength, 0.1, 1.0), report.Warnings)
	end

	-- 6. PostEffects under Lighting (ColorGradingEffect ONLY works under Lighting)
	if applyPost then
		local pfx = spec.PostEffects
		if pfx.Bloom then
			local bloom = getOrCreateChild(Lighting, "BloomEffect", "Bloom", report) :: BloomEffect
			bloom.Enabled = pfx.Bloom.Enabled
			bloom.Intensity = pfx.Bloom.Intensity
			bloom.Size = pfx.Bloom.Size
			bloom.Threshold = pfx.Bloom.Threshold
		end
		if pfx.ColorCorrection then
			local cc = getOrCreateChild(Lighting, "ColorCorrectionEffect", "ColorCorrection", report) :: ColorCorrectionEffect
			cc.Enabled = pfx.ColorCorrection.Enabled
			cc.Brightness = pfx.ColorCorrection.Brightness
			cc.Contrast = pfx.ColorCorrection.Contrast
			cc.Saturation = pfx.ColorCorrection.Saturation
			cc.TintColor = pfx.ColorCorrection.TintColor
		end
		if pfx.ColorGrading then
			local cg = getOrCreateChild(Lighting, "ColorGradingEffect", "ColorGrading", report) :: ColorGradingEffect
			cg.Enabled = pfx.ColorGrading.Enabled
			safeSet(cg, "TonemapperPreset", pfx.ColorGrading.TonemapperPreset, report.Warnings)
		end
		if pfx.SunRays then
			local sr = getOrCreateChild(Lighting, "SunRaysEffect", "SunRays", report) :: SunRaysEffect
			sr.Enabled = pfx.SunRays.Enabled
			sr.Intensity = pfx.SunRays.Intensity
			sr.Spread = math.clamp(pfx.SunRays.Spread, 0, 1)
		end
		if pfx.DepthOfField then
			local dof = getOrCreateChild(Lighting, "DepthOfFieldEffect", "DepthOfField", report) :: DepthOfFieldEffect
			dof.Enabled = pfx.DepthOfField.Enabled
			dof.FarIntensity = pfx.DepthOfField.FarIntensity
			dof.FocusDistance = pfx.DepthOfField.FocusDistance
			dof.InFocusRadius = pfx.DepthOfField.InFocusRadius
			dof.NearIntensity = pfx.DepthOfField.NearIntensity
		end
	end

	return report
end

--[[
	Cycles Workspace.GlobalWind periodically between baseWind and (baseWind + gustVector)
	with smooth TweenService transitions. Returns a stop callback that halts the loop
	and restores baseWind.
]]
function AtmospherePresets.StartWindGustLoop(
	baseWind: Vector3,
	gustVector: Vector3,
	cycleDelay: number?,
	cycleDuration: number?
): () -> ()
	local delaySec = math.max(1, cycleDelay or 8)
	local durSec = math.max(0.5, cycleDuration or 3.5)
	local stopped = false
	local activeTween: Tween? = nil

	Workspace.GlobalWind = baseWind
	local gustTweenInfo = TweenInfo.new(durSec * 0.45, Enum.EasingStyle.Sine, Enum.EasingDirection.Out)
	local settleTweenInfo = TweenInfo.new(durSec * 0.55, Enum.EasingStyle.Sine, Enum.EasingDirection.InOut)

	task.spawn(function()
		while not stopped do
			task.wait(delaySec)
			if stopped then
				break
			end
			local peakTween = TweenService:Create(Workspace, gustTweenInfo, {
				GlobalWind = baseWind + gustVector,
			})
			activeTween = peakTween
			peakTween:Play()
			peakTween.Completed:Wait()

			if stopped then
				break
			end
			local calmTween = TweenService:Create(Workspace, settleTweenInfo, {
				GlobalWind = baseWind,
			})
			activeTween = calmTween
			calmTween:Play()
			calmTween.Completed:Wait()
		end
	end)

	return function()
		stopped = true
		if activeTween then
			activeTween:Cancel()
			activeTween = nil
		end
		Workspace.GlobalWind = baseWind
	end
end

return AtmospherePresets

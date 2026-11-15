--!strict
--[[
	audit_environment.luau
	Non-destructive Roblox Terrain, Lighting, Atmosphere, Sky, Clouds, GlobalWind,
	MaterialService, PostEffect, and Streaming diagnostic.

	Safe across Studio Command Bar, MCP execute_luau, and runtime scripts:
	- Wraps RobloxScriptSecurity / PluginSecurity / PluginOrOpenCloud reads
	  (Lighting.Technology, MaterialService.Use2022Materials, Streaming radii) in pcall.
	- Returns HttpService:JSONEncode(report) with structured passes, warnings,
	  errors, and environment metrics.
]]

local HttpService = game:GetService("HttpService")
local Lighting = game:GetService("Lighting")
local MaterialService = game:GetService("MaterialService")
local Workspace = game:GetService("Workspace")

type AuditReport = {
	status: string,
	passCount: number,
	warningCount: number,
	errorCount: number,
	passes: { string },
	warnings: { string },
	errors: { string },
	metrics: { [string]: any },
}

local function safeReadProp(inst: Instance, prop: string): (boolean, any)
	return pcall(function()
		return (inst :: any)[prop]
	end)
end

local function serializeColor3(c: Color3): { number }
	return {
		math.floor(c.R * 255 + 0.5),
		math.floor(c.G * 255 + 0.5),
		math.floor(c.B * 255 + 0.5),
	}
end

local function addPass(report: AuditReport, msg: string)
	table.insert(report.passes, msg)
end

local function addWarn(report: AuditReport, msg: string)
	table.insert(report.warnings, msg)
end

local function addError(report: AuditReport, msg: string)
	table.insert(report.errors, msg)
end

local function findAllOfClass(roots: { Instance }, className: string): { Instance }
	local matches: { Instance } = {}
	local seen: { [Instance]: boolean } = {}
	for _, root in ipairs(roots) do
		local ok, descendants = pcall(function()
			return root:GetDescendants()
		end)
		if ok and type(descendants) == "table" then
			for _, desc in ipairs(descendants :: { Instance }) do
				if not seen[desc] then
					local okClass, isMatch = pcall(function()
						return desc.ClassName == className
					end)
					if okClass and isMatch then
						seen[desc] = true
						table.insert(matches, desc)
					end
				end
			end
		end
	end
	return matches
end

local function safeAuditRoots(): { Instance }
	local roots: { Instance } = { Workspace, Lighting, MaterialService }
	local okRep, repStorage = pcall(function()
		return game:GetService("ReplicatedStorage")
	end)
	if okRep and repStorage then
		table.insert(roots, repStorage)
	end
	return roots
end

local function runAudit(): AuditReport
	local report: AuditReport = {
		status = "PASS",
		passCount = 0,
		warningCount = 0,
		errorCount = 0,
		passes = {},
		warnings = {},
		errors = {},
		metrics = {},
	}

	local terrain = Workspace.Terrain
	local auditRoots = safeAuditRoots()

	-- 1. Clouds Parenting & Configuration (CRITICAL: Clouds ONLY renders under Workspace.Terrain)
	local allClouds = findAllOfClass(auditRoots, "Clouds")
	local cloudsUnderTerrain: { Clouds } = {}
	local misplacedCloudsPaths: { string } = {}
	for _, inst in ipairs(allClouds) do
		if inst.Parent == terrain then
			table.insert(cloudsUnderTerrain, inst :: Clouds)
		else
			-- Ignore StarterGui/CoreGui/internal non-scene storage? Report explicit workspace/lighting mistakes.
			local fullName = inst:GetFullName()
			if inst:IsDescendantOf(Lighting) or inst:IsDescendantOf(Workspace) then
				table.insert(misplacedCloudsPaths, fullName)
			end
		end
	end

	if #misplacedCloudsPaths > 0 then
		addError(
			report,
			"Clouds must be parented directly under Workspace.Terrain to render; misplaced: "
				.. table.concat(misplacedCloudsPaths, ", ")
		)
	end
	if #cloudsUnderTerrain == 0 then
		addWarn(report, "No Clouds instance directly under Workspace.Terrain (volumetric clouds inactive).")
	elseif #cloudsUnderTerrain > 1 then
		addWarn(
			report,
			string.format("Multiple (%d) Clouds instances under Workspace.Terrain; keep a single Clouds object.", #cloudsUnderTerrain)
		)
	else
		local c = cloudsUnderTerrain[1]
		if c.Enabled then
			addPass(report, string.format("Clouds active under Workspace.Terrain (Cover=%.2f, Density=%.2f).", c.Cover, c.Density))
		else
			addWarn(report, "Clouds exists under Workspace.Terrain but Enabled=false.")
		end
	end
	report.metrics.clouds = {
		underTerrainCount = #cloudsUnderTerrain,
		misplacedCount = #misplacedCloudsPaths,
		misplacedPaths = misplacedCloudsPaths,
		enabled = if #cloudsUnderTerrain > 0 then cloudsUnderTerrain[1].Enabled else false,
		cover = if #cloudsUnderTerrain > 0 then cloudsUnderTerrain[1].Cover else nil,
		density = if #cloudsUnderTerrain > 0 then cloudsUnderTerrain[1].Density else nil,
	}

	-- 2. Lighting (Security-safe read for Technology + LightingStyle)
	local techOk, techVal = safeReadProp(Lighting, "Technology")
	local styleOk, styleVal = safeReadProp(Lighting, "LightingStyle")
	local qualOk, qualVal = safeReadProp(Lighting, "PrioritizeLightingQuality")

	if styleOk then
		addPass(report, string.format("Lighting.LightingStyle = %s.", tostring(styleVal)))
	else
		addWarn(report, "Lighting.LightingStyle unreadable in this script context.")
	end

	if Lighting.GlobalShadows then
		local amb = Lighting.Ambient
		local out = Lighting.OutdoorAmbient
		local ambLum = amb.R + amb.G + amb.B
		local outLum = out.R + out.G + out.B
		if outLum + 0.01 < ambLum then
			addWarn(
				report,
				"Lighting.OutdoorAmbient is darker than Lighting.Ambient while GlobalShadows=true; Roblox clamps OutdoorAmbient >= Ambient."
			)
		else
			addPass(report, "Lighting.GlobalShadows=true with coherent Ambient/OutdoorAmbient.")
		end
	else
		addWarn(report, "Lighting.GlobalShadows=false; terrain and structural shadows are disabled.")
	end

	report.metrics.lighting = {
		clockTime = Lighting.ClockTime,
		geographicLatitude = Lighting.GeographicLatitude,
		brightness = Lighting.Brightness,
		exposureCompensation = Lighting.ExposureCompensation,
		environmentDiffuseScale = Lighting.EnvironmentDiffuseScale,
		environmentSpecularScale = Lighting.EnvironmentSpecularScale,
		globalShadows = Lighting.GlobalShadows,
		shadowSoftness = Lighting.ShadowSoftness,
		ambient = serializeColor3(Lighting.Ambient),
		outdoorAmbient = serializeColor3(Lighting.OutdoorAmbient),
		lightingStyle = if styleOk then tostring(styleVal) else "Inaccessible",
		prioritizeLightingQuality = if qualOk then qualVal else "Inaccessible",
		technologyReadAccess = techOk,
		technology = if techOk then tostring(techVal) else "RobloxScriptSecurity (Studio UI only)",
	}

	-- 3. Atmosphere Coupling Rules (Glare requires Haze > 0; Decay requires Haze > 0 AND Glare > 0)
	local atmospheres: { Atmosphere } = {}
	for _, child in ipairs(Lighting:GetChildren()) do
		if child:IsA("Atmosphere") then
			table.insert(atmospheres, child)
		end
	end

	if #atmospheres == 0 then
		addWarn(report, "No Atmosphere under Lighting (falling back to legacy FogStart/FogEnd).")
		report.metrics.atmosphere = { present = false }
	else
		if #atmospheres > 1 then
			addWarn(report, string.format("Found %d Atmosphere instances under Lighting; only one should exist.", #atmospheres))
		end
		local atmo = atmospheres[1]
		if atmo.Glare > 0 and atmo.Haze <= 0 then
			addWarn(
				report,
				string.format("Atmosphere.Glare=%.2f has no visible effect because Atmosphere.Haze=%.2f (must be > 0).", atmo.Glare, atmo.Haze)
			)
		else
			addPass(
				report,
				string.format("Atmosphere under Lighting valid (Density=%.2f, Offset=%.2f, Haze=%.2f, Glare=%.2f).", atmo.Density, atmo.Offset, atmo.Haze, atmo.Glare)
			)
		end
		report.metrics.atmosphere = {
			present = true,
			count = #atmospheres,
			density = atmo.Density,
			offset = atmo.Offset,
			haze = atmo.Haze,
			glare = atmo.Glare,
			color = serializeColor3(atmo.Color),
			decay = serializeColor3(atmo.Decay),
		}
	end

	-- 4. Sky Check
	local skies: { Sky } = {}
	for _, child in ipairs(Lighting:GetChildren()) do
		if child:IsA("Sky") then
			table.insert(skies, child)
		end
	end
	if #skies == 0 then
		addWarn(report, "No Sky instance under Lighting (using engine default skybox).")
	elseif #skies > 1 then
		addWarn(report, string.format("Multiple (%d) Sky instances under Lighting.", #skies))
	else
		addPass(report, "Single Sky instance under Lighting.")
	end
	report.metrics.sky = {
		count = #skies,
		celestialBodiesShown = if #skies > 0 then skies[1].CelestialBodiesShown else nil,
		starCount = if #skies > 0 then skies[1].StarCount else nil,
	}

	-- 5. PostEffects Audit (ColorGradingEffect ONLY works under Lighting!)
	local postClasses = {
		"BloomEffect",
		"BlurEffect",
		"ColorCorrectionEffect",
		"ColorGradingEffect",
		"DepthOfFieldEffect",
		"SunRaysEffect",
	}
	local postMetrics: { [string]: any } = {}
	local cam = Workspace.CurrentCamera
	for _, cls in ipairs(postClasses) do
		local inLighting: { Instance } = {}
		local inCamera: { Instance } = {}
		local misplaced: { string } = {}
		for _, inst in ipairs(findAllOfClass(auditRoots, cls)) do
			if inst.Parent == Lighting then
				table.insert(inLighting, inst)
			elseif cam and inst.Parent == cam then
				table.insert(inCamera, inst)
			elseif inst:IsDescendantOf(Workspace) or inst:IsDescendantOf(Lighting) then
				table.insert(misplaced, inst:GetFullName())
			end
		end

		if #misplaced > 0 then
			addWarn(report, string.format("%s outside Lighting/CurrentCamera does not render: %s", cls, table.concat(misplaced, ", ")))
		end
		if cls == "ColorGradingEffect" then
			if #inCamera > 0 then
				addError(
					report,
					"ColorGradingEffect under Workspace.CurrentCamera is ignored by Roblox; parent ColorGradingEffect directly under Lighting."
				)
			end
			if #inLighting > 1 then
				addWarn(
					report,
					string.format("Multiple (%d) ColorGradingEffect instances under Lighting; only the most recently parented applies.", #inLighting)
				)
			elseif #inLighting == 1 then
				local okPreset, presetVal = safeReadProp(inLighting[1], "TonemapperPreset")
				addPass(
					report,
					string.format(
						"ColorGradingEffect correctly under Lighting (TonemapperPreset=%s).",
						if okPreset then tostring(presetVal) else "Unknown"
					)
				)
			end
		elseif cls == "BlurEffect" then
			if (#inLighting + #inCamera) > 1 then
				addWarn(report, "Multiple BlurEffect instances active; Roblox only renders the one with largest Size.")
			end
		elseif cls == "SunRaysEffect" then
			for _, sr in ipairs(inLighting) do
				local spread = (sr :: SunRaysEffect).Spread
				if spread < 0 or spread > 1 then
					addWarn(report, string.format("SunRaysEffect '%s' Spread=%.2f outside recommended [0, 1].", sr.Name, spread))
				end
			end
		end

		postMetrics[cls] = {
			inLighting = #inLighting,
			inCamera = #inCamera,
			misplaced = misplaced,
		}
	end
	report.metrics.postEffects = postMetrics

	-- 6. MaterialService, MaterialVariants, TerrainDetails, and Expanded Terrain Slots
	local use2022Ok, use2022Val = safeReadProp(MaterialService, "Use2022Materials")
	local variants: { MaterialVariant } = {}
	local badTerrainDetailVariants: { string } = {}
	for _, child in ipairs(MaterialService:GetChildren()) do
		if child:IsA("MaterialVariant") then
			table.insert(variants, child)
			local tdCount = 0
			local seenFaces: { [Enum.TerrainFace]: boolean } = {}
			local dupFace = false
			for _, sub in ipairs(child:GetChildren()) do
				if sub:IsA("TerrainDetail") then
					tdCount += 1
					if seenFaces[sub.Face] then
						dupFace = true
					end
					seenFaces[sub.Face] = true
				end
			end
			if tdCount > 3 or dupFace then
				table.insert(badTerrainDetailVariants, string.format("%s (TerrainDetails=%d, dupFace=%s)", child.Name, tdCount, tostring(dupFace)))
			end
		end
	end
	if #badTerrainDetailVariants > 0 then
		addError(
			report,
			"MaterialVariant TerrainDetail limit/face error (max 3 TerrainDetails, unique Top/Side/Bottom): "
				.. table.concat(badTerrainDetailVariants, ", ")
		)
	else
		addPass(report, string.format("MaterialService valid (%d MaterialVariant children).", #variants))
	end

	local configuredSlots = 0
	local slotProbeSupported = false
	for slot = 2, 63 do
		local okSlot, baseMat = pcall(function()
			return terrain:GetMaterialSlot(slot)
		end)
		if okSlot then
			slotProbeSupported = true
			if baseMat ~= nil then
				configuredSlots += 1
			end
		else
			break
		end
	end
	report.metrics.materials = {
		use2022ReadAccess = use2022Ok,
		use2022Materials = if use2022Ok then use2022Val else "RobloxScriptSecurity (Studio MaterialService UI)",
		materialVariantCount = #variants,
		expandedTerrainSlotApiAvailable = slotProbeSupported,
		configuredMaterialSlots = configuredSlots,
	}

	-- 7. Terrain Grass, Water, Cell Count & GlobalWind
	local cellCount = terrain:CountCells()
	if cellCount == 0 then
		addWarn(report, "Workspace.Terrain:CountCells() == 0 (no terrain voxels present).")
	else
		addPass(report, string.format("Workspace.Terrain populated (~%d non-empty voxel cells).", cellCount))
	end
	local grassLenOk, grassLen = safeReadProp(terrain, "GrassLength")
	local decoOk, decoVal = safeReadProp(terrain, "Decoration")
	if grassLenOk and ((grassLen :: number) < 0.1 or (grassLen :: number) > 1.0) then
		addWarn(report, string.format("Terrain.GrassLength=%.2f outside standard [0.1, 1.0] range.", grassLen :: number))
	end

	report.metrics.terrain = {
		cellCount = cellCount,
		decoration = if decoOk then decoVal else "Unavailable",
		grassLength = if grassLenOk then grassLen else "Unavailable",
		waterColor = serializeColor3(terrain.WaterColor),
		waterTransparency = terrain.WaterTransparency,
		waterReflectance = terrain.WaterReflectance,
		waterWaveSize = terrain.WaterWaveSize,
		waterWaveSpeed = terrain.WaterWaveSpeed,
		globalWind = { Workspace.GlobalWind.X, Workspace.GlobalWind.Y, Workspace.GlobalWind.Z },
	}

	-- 8. StreamingEnabled Interaction Risk (PluginOrOpenCloud reads guarded by pcall)
	local streamingEnabled = Workspace.StreamingEnabled
	local minRadOk, minRad = safeReadProp(Workspace, "StreamingMinRadius")
	local tgtRadOk, tgtRad = safeReadProp(Workspace, "StreamingTargetRadius")
	local integrityOk, integrityVal = safeReadProp(Workspace, "StreamingIntegrityMode")

	if streamingEnabled then
		if minRadOk and (minRad :: number) <= 128 then
			addWarn(
				report,
				string.format(
					"StreamingEnabled=true with StreamingMinRadius=%d; thin terrain features (<16 voxels / 64 studs thick) risk disappearing on low streaming radii.",
					minRad :: number
				)
			)
		else
			addPass(report, "StreamingEnabled=true; keep structural terrain volumes >= 16 voxels (64 studs) thick.")
		end
	else
		addPass(report, "StreamingEnabled=false (full terrain loaded on clients).")
	end

	report.metrics.streaming = {
		streamingEnabled = streamingEnabled,
		streamingMinRadius = if minRadOk then minRad else "PluginOrOpenCloud",
		streamingTargetRadius = if tgtRadOk then tgtRad else "PluginOrOpenCloud",
		streamingIntegrityMode = if integrityOk then tostring(integrityVal) else "PluginOrOpenCloud",
	}

	report.passCount = #report.passes
	report.warningCount = #report.warnings
	report.errorCount = #report.errors
	if report.errorCount > 0 then
		report.status = "FAIL"
	elseif report.warningCount > 0 then
		report.status = "WARN"
	else
		report.status = "PASS"
	end

	return report
end

return HttpService:JSONEncode(runAudit())

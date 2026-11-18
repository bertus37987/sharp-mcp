--!strict
-- terrain_chunked_builder.luau
-- Production chunked procedural Terrain builder for Roblox Studio & Server scripts.
-- Supports:
--   * 4x4x4 stud grid alignment (:ExpandToGrid(4)) & automatic <= 4,194,304 voxel chunking
--   * fBM + ridged multifractal noise (native math.noise) with compact seed offsets
--   * Smoothstep circular & box flatten plateaus for buildings, spawns, and roads
--   * Custom prompt height layers (crater, river, ridge, terrace, plateau) & material rules
--   * Slope- & altitude-based biome material painting (Alpine, Meadow, Desert, Volcanic, Arctic, Coast)
--   * Modern WriteVoxelChannels (SolidMaterial / SolidMaterialIndex + SolidOccupancy + LiquidOccupancy)
--     with optional WriteVoxels fallback and task.wait() yielding between chunks
--   * Geometric carving/stamping helpers (FillBlock / FillCylinder / FillBall / FillWedge / ReplaceMaterial)

local TerrainBuilder = {}

local VOXEL_SIZE = 4
local MAX_VOXELS_PER_CALL = 4194304
local DEFAULT_CHUNK_CELLS = 64
local OCC_EPSILON = 1 / 256

export type BiomeName = "Alpine" | "Meadow" | "Desert" | "Volcanic" | "Arctic" | "Coast" | "Canyon"

export type FlattenZone = {
	x: number,
	z: number,
	h: number,
	shape: ("Circle" | "Box")?,
	r0: number?,
	r1: number?,
	halfX: number?,
	halfZ: number?,
	blend: number?,
	material: Enum.Material?,
}

export type Vec2Point = {
	x: number,
	z: number,
}

export type HeightLayer = {
	type: string,
	x: number?,
	z: number?,
	x1: number?,
	z1: number?,
	x2: number?,
	z2: number?,
	radius: number?,
	depth: number?,
	height: number?,
	rimHeight: number?,
	rimWidth: number?,
	width: number?,
	stepHeight: number?,
	blend: number?,
	minY: number?,
	maxY: number?,
	waterFill: boolean?,
	waterLevel: number?,
	material: Enum.Material?,
	points: { Vec2Point }?,
}

export type MaterialRule = {
	minY: number?,
	maxY: number?,
	minSlope: number?,
	maxSlope: number?,
	x: number?,
	z: number?,
	minRadius: number?,
	maxRadius: number?,
	material: Enum.Material,
}

export type BiomePalette = {
	low: Enum.Material,
	shore: Enum.Material,
	underwater: Enum.Material,
	mid: Enum.Material,
	cliff: Enum.Material,
	high: Enum.Material,
}

export type BuildConfig = {
	min: Vector3?,
	max: Vector3?,
	center: Vector3?,
	size: Vector3?,
	seed: number?,
	biome: BiomeName?,
	palette: BiomePalette?,
	baseHeight: number?,
	mountainHeight: number?,
	noiseWeight: number?,
	noiseScale: number?,
	octaves: number?,
	lacunarity: number?,
	persistence: number?,
	ridgeWeight: number?,
	waterLevel: number?,
	flattenZones: { FlattenZone }?,
	heightLayers: { HeightLayer }?,
	materialRules: { MaterialRule }?,
	chunkCellsXZ: number?,
	useVoxelChannels: boolean?,
	yieldPerChunk: boolean?,
	solidSlotResolver: ((mat: Enum.Material, wx: number, height: number, slope: number) -> number)?,
}

export type Vec3Coords = {
	X: number,
	Y: number,
	Z: number,
}

export type BuildReport = {
	apiUsed: string,
	regionMin: Vec3Coords,
	regionMax: Vec3Coords,
	cellsSize: Vec3Coords,
	chunksWritten: number,
	voxelsProcessed: number,
	solidVoxelsWritten: number,
	waterVoxelsWritten: number,
	elapsedSeconds: number,
}

TerrainBuilder.BIOME_PALETTES = {
	Alpine = {
		low = Enum.Material.Grass,
		shore = Enum.Material.Sand,
		underwater = Enum.Material.Ground,
		mid = Enum.Material.LeafyGrass,
		cliff = Enum.Material.Rock,
		high = Enum.Material.Snow,
	},
	Meadow = {
		low = Enum.Material.Grass,
		shore = Enum.Material.Sand,
		underwater = Enum.Material.Mud,
		mid = Enum.Material.LeafyGrass,
		cliff = Enum.Material.Rock,
		high = Enum.Material.Grass,
	},
	Desert = {
		low = Enum.Material.Sand,
		shore = Enum.Material.Sand,
		underwater = Enum.Material.Sandstone,
		mid = Enum.Material.Sandstone,
		cliff = Enum.Material.Limestone,
		high = Enum.Material.Rock,
	},
	Volcanic = {
		low = Enum.Material.Basalt,
		shore = Enum.Material.Ground,
		underwater = Enum.Material.Basalt,
		mid = Enum.Material.Slate,
		cliff = Enum.Material.Basalt,
		high = Enum.Material.CrackedLava,
	},
	Arctic = {
		low = Enum.Material.Snow,
		shore = Enum.Material.Ice,
		underwater = Enum.Material.Glacier,
		mid = Enum.Material.Glacier,
		cliff = Enum.Material.Rock,
		high = Enum.Material.Snow,
	},
	Coast = {
		low = Enum.Material.Grass,
		shore = Enum.Material.Sand,
		underwater = Enum.Material.Sand,
		mid = Enum.Material.Grass,
		cliff = Enum.Material.Limestone,
		high = Enum.Material.Rock,
	},
	Canyon = {
		low = Enum.Material.Sandstone,
		shore = Enum.Material.Sand,
		underwater = Enum.Material.Slate,
		mid = Enum.Material.Sandstone,
		cliff = Enum.Material.Limestone,
		high = Enum.Material.Slate,
	},
} :: { [BiomeName]: BiomePalette }

local function orderedMinMax(a: Vector3, b: Vector3): (Vector3, Vector3)
	return Vector3.new(math.min(a.X, b.X), math.min(a.Y, b.Y), math.min(a.Z, b.Z)),
		Vector3.new(math.max(a.X, b.X), math.max(a.Y, b.Y), math.max(a.Z, b.Z))
end

local function smoothstep01(t: number): number
	local c = math.clamp(t, 0, 1)
	return c * c * (3 - 2 * c)
end

local function distPointToSegment2D(px: number, pz: number, ax: number, az: number, bx: number, bz: number): number
	local vx = bx - ax
	local vz = bz - az
	local lenSq = vx * vx + vz * vz
	if lenSq <= 1e-8 then
		return math.sqrt((px - ax) ^ 2 + (pz - az) ^ 2)
	end
	local t = math.clamp(((px - ax) * vx + (pz - az) * vz) / lenSq, 0, 1)
	local cx = ax + vx * t
	local cz = az + vz * t
	return math.sqrt((px - cx) ^ 2 + (pz - cz) ^ 2)
end

local function distToLayerPath2D(wx: number, wz: number, layer: HeightLayer): number?
	local pts = layer.points
	if pts and #pts >= 2 then
		local best = math.huge
		for idx = 1, #pts - 1 do
			local a = pts[idx]
			local b = pts[idx + 1]
			local d = distPointToSegment2D(wx, wz, a.x, a.z, b.x, b.z)
			if d < best then
				best = d
			end
		end
		return best
	elseif pts and #pts == 1 then
		local p = pts[1]
		return math.sqrt((wx - p.x) ^ 2 + (wz - p.z) ^ 2)
	end

	local x1, z1, x2, z2 = layer.x1, layer.z1, layer.x2, layer.z2
	if x1 ~= nil and z1 ~= nil and x2 ~= nil and z2 ~= nil then
		return distPointToSegment2D(wx, wz, x1, z1, x2, z2)
	end

	local lx, lz = layer.x, layer.z
	if lx ~= nil and lz ~= nil then
		return math.sqrt((wx - lx) ^ 2 + (wz - lz) ^ 2)
	end
	return nil
end

function TerrainBuilder.AlignRegionToGrid(minPos: Vector3, maxPos: Vector3): Region3
	local lo, hi = orderedMinMax(minPos, maxPos)
	-- Ensure non-zero extent along every axis before expanding to 4-stud grid
	if hi.X - lo.X < VOXEL_SIZE then
		hi = Vector3.new(lo.X + VOXEL_SIZE, hi.Y, hi.Z)
	end
	if hi.Y - lo.Y < VOXEL_SIZE then
		hi = Vector3.new(hi.X, lo.Y + VOXEL_SIZE, hi.Z)
	end
	if hi.Z - lo.Z < VOXEL_SIZE then
		hi = Vector3.new(hi.X, hi.Y, lo.Z + VOXEL_SIZE)
	end
	return Region3.new(lo, hi):ExpandToGrid(VOXEL_SIZE)
end

function TerrainBuilder.ComputeVoxelCount(region: Region3): number
	local cells = region.Size / VOXEL_SIZE
	return math.round(cells.X) * math.round(cells.Y) * math.round(cells.Z)
end

function TerrainBuilder.ResolveBounds(config: BuildConfig): Region3
	if config.min and config.max then
		return TerrainBuilder.AlignRegionToGrid(config.min, config.max)
	end
	local center = config.center or Vector3.new(0, 64, 0)
	local size = config.size or Vector3.new(256, 128, 256)
	local half = size * 0.5
	return TerrainBuilder.AlignRegionToGrid(center - half, center + half)
end

function TerrainBuilder.ApplyFlattenZones(
	baseHeight: number,
	wx: number,
	wz: number,
	zones: { FlattenZone }?
): (number, Enum.Material?, number)
	if not zones or #zones == 0 then
		return baseHeight, nil, 0
	end
	local h = baseHeight
	local overrideMat: Enum.Material? = nil
	local maxPadWeight = 0

	for _, zone in ipairs(zones) do
		local shape = zone.shape or "Circle"
		local weight = 0
		if shape == "Box" then
			local hx = zone.halfX or zone.r0 or 20
			local hz = zone.halfZ or zone.r0 or 20
			local blend = math.max(zone.blend or ((zone.r1 or (math.max(hx, hz) + 20)) - math.max(hx, hz)), 0.001)
			local dx = math.max(math.abs(wx - zone.x) - hx, 0)
			local dz = math.max(math.abs(wz - zone.z) - hz, 0)
			local outsideDist = math.sqrt(dx * dx + dz * dz)
			if outsideDist <= 0 then
				weight = 1
			elseif outsideDist < blend then
				weight = 1 - smoothstep01(outsideDist / blend)
			end
		else
			local r0 = zone.r0 or 20
			local r1 = math.max(zone.r1 or (r0 * 2), r0 + 0.001)
			local dist = math.sqrt((wx - zone.x) ^ 2 + (wz - zone.z) ^ 2)
			if dist <= r0 then
				weight = 1
			elseif dist < r1 then
				weight = 1 - smoothstep01((dist - r0) / (r1 - r0))
			end
		end

		if weight > 0 then
			h = h + (zone.h - h) * weight
			if zone.material and weight >= 0.75 and weight >= maxPadWeight then
				overrideMat = zone.material
			end
			if weight > maxPadWeight then
				maxPadWeight = weight
			end
		end
	end

	return h, overrideMat, maxPadWeight
end

function TerrainBuilder.ApplyHeightLayers(
	baseHeight: number,
	wx: number,
	wz: number,
	layers: { HeightLayer }?
): (number, Enum.Material?, number?)
	if not layers or #layers == 0 then
		return baseHeight, nil, nil
	end
	local h = baseHeight
	local overrideMat: Enum.Material? = nil
	local overrideWater: number? = nil

	for _, layer in ipairs(layers) do
		local kind = string.lower(layer.type or "")
		if kind == "crater" then
			local cx = layer.x or 0
			local cz = layer.z or 0
			local r = math.max(layer.radius or 40, 1)
			local depth = layer.depth or 24
			local rimH = if layer.rimHeight ~= nil then layer.rimHeight else depth * 0.35
			local rimW = math.max(layer.rimWidth or (r * 0.45), 1)
			local d = math.sqrt((wx - cx) ^ 2 + (wz - cz) ^ 2)
			if d <= r then
				local u = d / r
				local bowl = (1 - u * u) * depth
				local rim = smoothstep01((u - 0.55) / 0.45) * rimH
				h += rim - bowl
				if layer.material and u <= 0.85 then
					overrideMat = layer.material
				end
			elseif d < r + rimW then
				local v = (d - r) / rimW
				h += (1 - smoothstep01(v)) * rimH
			end
		elseif kind == "river" then
			local minDist = distToLayerPath2D(wx, wz, layer)
			if minDist ~= nil then
				local halfW = math.max((layer.width or 16) * 0.5, 1)
				local blend = math.max(layer.blend or (halfW * 0.85), 1)
				local depth = layer.depth or 14
				if minDist < halfW + blend then
					local factor = if minDist <= halfW
						then (1 - 0.25 * (minDist / halfW) ^ 2)
						else (1 - smoothstep01((minDist - halfW) / blend))
					local bankHeight = h
					h -= depth * factor
					local fillWater = if layer.waterFill == nil then true else layer.waterFill
					if fillWater and minDist <= halfW + blend * 0.45 then
						local wl = if layer.waterLevel ~= nil
							then layer.waterLevel
							else (bankHeight - math.min(depth * 0.28, 3.5))
						overrideWater = if overrideWater ~= nil then math.max(overrideWater, wl) else wl
					end
					if layer.material and minDist <= halfW * 0.9 then
						overrideMat = layer.material
					end
				end
			end
		elseif kind == "ridge" then
			local minDist = distToLayerPath2D(wx, wz, layer)
			if minDist ~= nil then
				local halfW = math.max((layer.width or 24) * 0.5, 1)
				local blend = math.max(layer.blend or halfW, 1)
				local ridgeH = layer.height or layer.rimHeight or 32
				local totalW = halfW + blend
				if minDist < totalW then
					local t = math.clamp(minDist / totalW, 0, 1)
					local crest = (1 - smoothstep01(t)) * (1 - 0.35 * t)
					h += ridgeH * crest
					if layer.material and t <= 0.45 then
						overrideMat = layer.material
					end
				end
			end
		elseif kind == "terrace" then
			local stepH = math.max(layer.stepHeight or 8, 1)
			local weight = 1
			local lx, lz = layer.x, layer.z
			if lx ~= nil and lz ~= nil then
				local r = math.max(layer.radius or 80, 1)
				local blend = math.max(layer.blend or (r * 0.35), 1)
				local d = math.sqrt((wx - lx) ^ 2 + (wz - lz) ^ 2)
				if d >= r + blend then
					weight = 0
				elseif d > r then
					weight = 1 - smoothstep01((d - r) / blend)
				end
			end
			if layer.minY ~= nil and h < layer.minY then
				weight = 0
			end
			if layer.maxY ~= nil and h > layer.maxY then
				weight = 0
			end
			if weight > 0 then
				local band = h / stepH
				local fl = math.floor(band)
				local frac = band - fl
				local sharp = 0.35
				local stepFrac = smoothstep01((frac - (0.5 - sharp * 0.5)) / sharp)
				local terraced = (fl + stepFrac) * stepH
				h = h + (terraced - h) * weight
				if layer.material and weight >= 0.75 then
					overrideMat = layer.material
				end
			end
		elseif kind == "plateau" then
			local cx = layer.x or 0
			local cz = layer.z or 0
			local r = math.max(layer.radius or 40, 1)
			local targetH = layer.height or 96
			local blend = math.max(layer.blend or (r * 0.5), 1)
			local d = math.sqrt((wx - cx) ^ 2 + (wz - cz) ^ 2)
			local weight = 0
			if d <= r then
				weight = 1
			elseif d < r + blend then
				weight = 1 - smoothstep01((d - r) / blend)
			end
			if weight > 0 then
				h = h + (targetH - h) * weight
				if layer.material and weight >= 0.75 then
					overrideMat = layer.material
				end
			end
		end
	end

	return h, overrideMat, overrideWater
end

function TerrainBuilder.ResolveMaterialRules(
	wx: number,
	wz: number,
	height: number,
	slope: number,
	rules: { MaterialRule }?
): Enum.Material?
	if not rules or #rules == 0 then
		return nil
	end
	for _, rule in ipairs(rules) do
		local minY = rule.minY
		local maxY = rule.maxY
		local minSlope = rule.minSlope
		local maxSlope = rule.maxSlope
		local minRadius = rule.minRadius
		local maxRadius = rule.maxRadius

		local ok = true
		if minY ~= nil and height < minY then
			ok = false
		elseif maxY ~= nil and height > maxY then
			ok = false
		elseif minSlope ~= nil and slope < minSlope then
			ok = false
		elseif maxSlope ~= nil and slope > maxSlope then
			ok = false
		elseif minRadius ~= nil or maxRadius ~= nil then
			local rx = rule.x or 0
			local rz = rule.z or 0
			local d = math.sqrt((wx - rx) ^ 2 + (wz - rz) ^ 2)
			if minRadius ~= nil and d < minRadius then
				ok = false
			end
			if maxRadius ~= nil and d > maxRadius then
				ok = false
			end
		end
		if ok then
			return rule.material
		end
	end
	return nil
end

function TerrainBuilder.SampleHeightFbm(wx: number, wz: number, config: BuildConfig): (number, Enum.Material?, number?)
	local seed = config.seed or 42
	-- Keep offsets well under 10k so math.noise retains full floating-point precision
	local sx = ((seed * 73) % 9973) * 0.137
	local sy = ((seed * 199) % 7919) * 0.071
	local sz = ((seed * 313) % 9967) * 0.193

	local baseHeight = config.baseHeight or 56
	local mountainHeight = config.mountainHeight or 84
	local noiseWeight = if config.noiseWeight == nil then 1.0 else config.noiseWeight
	local scale = config.noiseScale or (1 / 140)
	local octaves = math.clamp(config.octaves or 4, 1, 8)
	local lacunarity = config.lacunarity or 2.05
	local persistence = config.persistence or 0.48
	local ridgeWeight = math.clamp(config.ridgeWeight or 0.45, 0, 1)

	local freq = scale
	local amp = 1.0
	local ampSum = 0.0
	local fbmSum = 0.0
	local ridgeSum = 0.0
	local ridgeFactor = 1.0

	for oct = 1, octaves do
		local n = math.noise(wx * freq + sx + oct * 19.3, sy + oct * 7.1, wz * freq + sz - oct * 11.7)
		fbmSum += n * amp

		local ridgeSignal = 1.0 - math.abs(n)
		ridgeSignal = ridgeSignal * ridgeSignal * ridgeFactor
		ridgeFactor = math.clamp(ridgeSignal * 1.4, 0.25, 1.0)
		ridgeSum += ridgeSignal * amp

		ampSum += amp
		amp *= persistence
		freq *= lacunarity
	end

	local fbmNorm = (fbmSum / math.max(ampSum, 1e-6)) * 0.5 + 0.5 -- [0..1] centered ~0.5
	local ridgeNorm = math.clamp(ridgeSum / math.max(ampSum, 1e-6), 0, 1)
	local combined = fbmNorm * (1 - ridgeWeight) + ridgeNorm * ridgeWeight

	-- Shift around baseHeight so valleys can dip below baseHeight while peaks climb cleanly
	local rawHeight = baseHeight + (combined - 0.35) * mountainHeight * noiseWeight
	local layeredHeight, layerMat, layerWater = TerrainBuilder.ApplyHeightLayers(rawHeight, wx, wz, config.heightLayers)
	local finalHeight, padMat, _ = TerrainBuilder.ApplyFlattenZones(layeredHeight, wx, wz, config.flattenZones)
	return finalHeight, (padMat or layerMat), layerWater
end

function TerrainBuilder.ResolveSlopeMaterial(
	height: number,
	slope: number,
	padMat: Enum.Material?,
	config: BuildConfig,
	wx: number?,
	wz: number?,
	waterLevelOverride: number?
): Enum.Material
	if padMat then
		return padMat
	end
	if config.materialRules then
		local ruleMat = TerrainBuilder.ResolveMaterialRules(wx or 0, wz or 0, height, slope, config.materialRules)
		if ruleMat then
			return ruleMat
		end
	end
	local biome: BiomeName = config.biome or "Alpine"
	local palette = config.palette or TerrainBuilder.BIOME_PALETTES[biome] or TerrainBuilder.BIOME_PALETTES.Alpine
	local baseHeight = config.baseHeight or 56
	local mountainHeight = config.mountainHeight or 84
	local waterLevel = if waterLevelOverride ~= nil then waterLevelOverride else config.waterLevel

	if waterLevel and height <= waterLevel - 3 then
		return palette.underwater
	end
	if waterLevel and height <= waterLevel + 3.5 then
		return palette.shore
	end
	if slope > 0.62 then
		return palette.cliff
	end
	if height > baseHeight + mountainHeight * 0.52 then
		return palette.high
	end
	if height > baseHeight + mountainHeight * 0.25 or slope > 0.35 then
		return palette.mid
	end
	return palette.low
end

function TerrainBuilder.BuildRegion(config: BuildConfig): BuildReport
	local t0 = os.clock()
	local terrain = workspace.Terrain
	local region = TerrainBuilder.ResolveBounds(config)
	local regionMin = region.CFrame.Position - region.Size * 0.5
	local regionMax = region.CFrame.Position + region.Size * 0.5
	local totalCells = region.Size / VOXEL_SIZE
	local cellsX = math.round(totalCells.X)
	local cellsY = math.round(totalCells.Y)
	local cellsZ = math.round(totalCells.Z)

	local chunkXZ = math.clamp(config.chunkCellsXZ or DEFAULT_CHUNK_CELLS, 4, 128)
	local maxCellsYPerChunk = math.max(1, math.floor(MAX_VOXELS_PER_CALL / (chunkXZ * chunkXZ)))
	local chunkY = math.min(cellsY, maxCellsYPerChunk)

	local useChannels = if config.useVoxelChannels == nil then true else config.useVoxelChannels
	local shouldYield = if config.yieldPerChunk == nil then true else config.yieldPerChunk
	local waterLevel = config.waterLevel
	local slotResolver = config.solidSlotResolver

	local chunksWritten = 0
	local voxelsProcessed = 0
	local solidVoxelsWritten = 0
	local waterVoxelsWritten = 0
	local apiUsed = if useChannels then "WriteVoxelChannels" else "WriteVoxels"

	for bx = 0, cellsX - 1, chunkXZ do
		local sx = math.min(chunkXZ, cellsX - bx)
		for bz = 0, cellsZ - 1, chunkXZ do
			local sz = math.min(chunkXZ, cellsZ - bz)

			-- Precompute height, slope, and surface material once per (x, z) column
			local colH: { { number } } = table.create(sx)
			local colMat: { { Enum.Material } } = table.create(sx)
			local colSlope: { { number } } = table.create(sx)
			local colWater: { { number? } } = table.create(sx)
			for ix = 1, sx do
				colH[ix] = table.create(sz)
				colMat[ix] = table.create(sz)
				colSlope[ix] = table.create(sz)
				colWater[ix] = table.create(sz)
				local wx = regionMin.X + (bx + ix - 0.5) * VOXEL_SIZE
				for iz = 1, sz do
					local wz = regionMin.Z + (bz + iz - 0.5) * VOXEL_SIZE
					local h, padMat, localWater = TerrainBuilder.SampleHeightFbm(wx, wz, config)
					local hx, _ = TerrainBuilder.SampleHeightFbm(wx + VOXEL_SIZE, wz, config)
					local hz, _ = TerrainBuilder.SampleHeightFbm(wx, wz + VOXEL_SIZE, config)
					local slope = math.max(math.abs(hx - h), math.abs(hz - h)) / VOXEL_SIZE
					local effWater = if localWater ~= nil then localWater else waterLevel
					colH[ix][iz] = h
					colSlope[ix][iz] = slope
					colWater[ix][iz] = effWater
					colMat[ix][iz] = TerrainBuilder.ResolveSlopeMaterial(h, slope, padMat, config, wx, wz, effWater)
				end
			end

			for by = 0, cellsY - 1, chunkY do
				local sy = math.min(chunkY, cellsY - by)
				local chunkMin = Vector3.new(
					regionMin.X + bx * VOXEL_SIZE,
					regionMin.Y + by * VOXEL_SIZE,
					regionMin.Z + bz * VOXEL_SIZE
				)
				local chunkMax = chunkMin + Vector3.new(sx * VOXEL_SIZE, sy * VOXEL_SIZE, sz * VOXEL_SIZE)
				local chunkRegion = Region3.new(chunkMin, chunkMax):ExpandToGrid(VOXEL_SIZE)

				if useChannels then
					local solidOcc = table.create(sx)
					local liquidOcc = table.create(sx)
					local solidMat = if slotResolver == nil then table.create(sx) else nil
					local solidIdx = if slotResolver ~= nil then table.create(sx) else nil

					for ix = 1, sx do
						local wx = regionMin.X + (bx + ix - 0.5) * VOXEL_SIZE
						solidOcc[ix] = table.create(sy)
						liquidOcc[ix] = table.create(sy)
						if solidMat then
							solidMat[ix] = table.create(sy)
						end
						if solidIdx then
							solidIdx[ix] = table.create(sy)
						end

						for iy = 1, sy do
							local wy = regionMin.Y + (by + iy - 0.5) * VOXEL_SIZE
							local cellBottom = wy - (VOXEL_SIZE * 0.5)
							solidOcc[ix][iy] = table.create(sz)
							liquidOcc[ix][iy] = table.create(sz)
							if solidMat then
								solidMat[ix][iy] = table.create(sz)
							end
							if solidIdx then
								solidIdx[ix][iy] = table.create(sz)
							end

							for iz = 1, sz do
								local h = colH[ix][iz]
								local colWL = colWater[ix][iz]
								local sOcc = math.clamp((h - cellBottom) / VOXEL_SIZE, 0, 1)
								local lOcc = 0
								local mat = colMat[ix][iz]

								if sOcc <= OCC_EPSILON then
									sOcc = 0
									mat = Enum.Material.Air
								else
									solidVoxelsWritten += 1
								end

								if colWL and cellBottom < colWL and sOcc <= (1 - OCC_EPSILON) then
									lOcc = math.clamp((colWL - cellBottom) / VOXEL_SIZE, 0, 1)
									if lOcc <= OCC_EPSILON then
										lOcc = 0
									else
										waterVoxelsWritten += 1
									end
								end

								solidOcc[ix][iy][iz] = sOcc
								liquidOcc[ix][iy][iz] = lOcc
								if solidMat then
									-- Water is invalid in SolidMaterial; only solid/Air materials belong here
									solidMat[ix][iy][iz] = mat
								elseif solidIdx and slotResolver then
									if mat == Enum.Material.Air then
										solidIdx[ix][iy][iz] = 0
									else
										solidIdx[ix][iy][iz] = slotResolver(mat, wx, h, colSlope[ix][iz])
									end
								end
							end
						end
					end

					local payload: { [string]: any } = {
						SolidOccupancy = solidOcc,
						LiquidOccupancy = liquidOcc,
					}
					if solidIdx then
						payload.SolidMaterialIndex = solidIdx
					else
						payload.SolidMaterial = solidMat
					end

					local ok, err = pcall(function()
						terrain:WriteVoxelChannels(chunkRegion, VOXEL_SIZE, payload)
					end)
					if not ok then
						error(string.format("WriteVoxelChannels failed on chunk (%d,%d,%d): %s", bx, by, bz, tostring(err)))
					end
				else
					local materials = table.create(sx)
					local occupancies = table.create(sx)
					for ix = 1, sx do
						materials[ix] = table.create(sy)
						occupancies[ix] = table.create(sy)
						for iy = 1, sy do
							local wy = regionMin.Y + (by + iy - 0.5) * VOXEL_SIZE
							local cellBottom = wy - (VOXEL_SIZE * 0.5)
							materials[ix][iy] = table.create(sz)
							occupancies[ix][iy] = table.create(sz)
							for iz = 1, sz do
								local h = colH[ix][iz]
								local colWL = colWater[ix][iz]
								local occ = math.clamp((h - cellBottom) / VOXEL_SIZE, 0, 1)
								if occ <= OCC_EPSILON then
									if colWL and cellBottom < colWL then
										materials[ix][iy][iz] = Enum.Material.Water
										occupancies[ix][iy][iz] = math.clamp((colWL - cellBottom) / VOXEL_SIZE, 0, 1)
										waterVoxelsWritten += 1
									else
										materials[ix][iy][iz] = Enum.Material.Air
										occupancies[ix][iy][iz] = 0
									end
								else
									materials[ix][iy][iz] = colMat[ix][iz]
									occupancies[ix][iy][iz] = occ
									solidVoxelsWritten += 1
								end
							end
						end
					end
					terrain:WriteVoxels(chunkRegion, VOXEL_SIZE, materials, occupancies)
				end

				chunksWritten += 1
				voxelsProcessed += sx * sy * sz
				if shouldYield then
					task.wait()
				end
			end
		end
	end

	return {
		apiUsed = apiUsed,
		regionMin = { X = regionMin.X, Y = regionMin.Y, Z = regionMin.Z },
		regionMax = { X = regionMax.X, Y = regionMax.Y, Z = regionMax.Z },
		cellsSize = { X = cellsX, Y = cellsY, Z = cellsZ },
		chunksWritten = chunksWritten,
		voxelsProcessed = voxelsProcessed,
		solidVoxelsWritten = solidVoxelsWritten,
		waterVoxelsWritten = waterVoxelsWritten,
		elapsedSeconds = os.clock() - t0,
	}
end

function TerrainBuilder.StampBuildingPad(
	center: Vector3,
	size: Vector3,
	padMaterial: Enum.Material?,
	clearHeadroomStuds: number?
): ()
	local terrain = workspace.Terrain
	local mat = padMaterial or Enum.Material.Cobblestone
	local headroom = clearHeadroomStuds or 32
	local padCFrame = CFrame.new(center)
	terrain:FillBlock(padCFrame, size, mat)
	if headroom > 0 then
		local airCenter = center + Vector3.new(0, size.Y * 0.5 + headroom * 0.5, 0)
		terrain:FillBlock(CFrame.new(airCenter), Vector3.new(size.X, headroom, size.Z), Enum.Material.Air)
	end
end

function TerrainBuilder.ClearRegion(minPos: Vector3, maxPos: Vector3): Region3
	local region = TerrainBuilder.AlignRegionToGrid(minPos, maxPos)
	workspace.Terrain:FillRegion(region, VOXEL_SIZE, Enum.Material.Air)
	return region
end

return TerrainBuilder

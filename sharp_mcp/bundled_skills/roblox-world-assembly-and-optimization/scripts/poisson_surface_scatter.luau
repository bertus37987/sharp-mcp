--!strict
--[[
	PoissonSurfaceScatter
	Deterministic spatial-hashed Poisson-disc raycast scatter engine for Roblox
	Terrain and world geometry. Filters by altitude, slope angle, and
	Enum.Material, aligns to surface normal, and parents under a managed Folder.
]]

local CollectionService = game:GetService("CollectionService")
local Workspace = game:GetService("Workspace")

export type ScatterConfig = {
	minXZ: Vector2,
	maxXZ: Vector2,
	rayStartY: number?,
	rayDropDistance: number?,
	minAltitudeY: number?,
	maxAltitudeY: number?,
	maxSlopeDeg: number?,
	minSpacingStuds: number?,
	maxCount: number?,
	candidateAttempts: number?,
	seed: number?,
	normalAlignmentAlpha: number?,
	scaleRange: Vector2?,
	excludedMaterials: { [Enum.Material]: boolean }?,
	folderName: string?,
	tag: string?,
}

export type ScatterPlacement = {
	position: Vector3,
	normal: Vector3,
	cframe: CFrame,
	scale: number,
	material: Enum.Material,
}

export type ScatterReport = {
	placedCount: number,
	rejectedWaterOrMaterial: number,
	rejectedSlope: number,
	rejectedAltitude: number,
	rejectedSpacing: number,
	folderPath: string,
}

local DEFAULT_TAG = "SharpWorldScatterManaged"

local PoissonSurfaceScatter = {}

local function alignToNormal(upVector: Vector3, yawRad: number, normalAlignAlpha: number): CFrame
	local targetUp = Vector3.yAxis:Lerp(upVector, math.clamp(normalAlignAlpha, 0, 1)).Unit
	local refForward = Vector3.new(math.sin(yawRad), 0, math.cos(yawRad))
	local right = refForward:Cross(targetUp)
	if right.Magnitude < 1e-4 then
		right = Vector3.xAxis
	else
		right = right.Unit
	end
	local forward = targetUp:Cross(right).Unit
	return CFrame.fromMatrix(Vector3.zero, right, targetUp, -forward)
end

function PoissonSurfaceScatter.GeneratePlacements(
	config: ScatterConfig,
	excludeInstances: { Instance }?
): ({ ScatterPlacement }, ScatterReport)
	local rng = Random.new(config.seed or 42)
	local minSpacing = math.max(1.0, config.minSpacingStuds or 12.0)
	local minSpacingSq = minSpacing * minSpacing
	local cellSize = minSpacing
	local maxCount = config.maxCount or 60
	local attempts = config.candidateAttempts or (maxCount * 6)
	local rayStartY = config.rayStartY or 260.0
	local rayDrop = config.rayDropDistance or 320.0
	local minAlt = config.minAltitudeY or -500.0
	local maxAlt = config.maxAltitudeY or 500.0
	local maxSlopeDeg = config.maxSlopeDeg or 34.0
	local alignAlpha = config.normalAlignmentAlpha or 0.35
	local scaleRange = config.scaleRange or Vector2.new(0.85, 1.20)

	local excludedMats: { [Enum.Material]: boolean } = config.excludedMaterials or {
		[Enum.Material.Water] = true,
		[Enum.Material.Cobblestone] = true,
		[Enum.Material.Pavement] = true,
		[Enum.Material.CrackedLava] = true,
	}

	local grid: { [string]: { Vector2 } } = {}
	local placements: { ScatterPlacement } = {}
	local rejMat = 0
	local rejSlope = 0
	local rejAlt = 0
	local rejSpace = 0

	local rayParams = RaycastParams.new()
	rayParams.FilterType = Enum.RaycastFilterType.Exclude
	rayParams.FilterDescendantsInstances = excludeInstances or {}
	rayParams.IgnoreWater = false

	local function isTooClose(pt2D: Vector2): boolean
		local gx = math.floor(pt2D.X / cellSize)
		local gz = math.floor(pt2D.Y / cellSize)
		for dx = -1, 1 do
			for dz = -1, 1 do
				local key = tostring(gx + dx) .. ":" .. tostring(gz + dz)
				local bucket = grid[key]
				if bucket then
					for _, existing in ipairs(bucket) do
						local diff = pt2D - existing
						if diff:Dot(diff) < minSpacingSq then
							return true
						end
					end
				end
			end
		end
		return false
	end

	local function insertGrid(pt2D: Vector2)
		local gx = math.floor(pt2D.X / cellSize)
		local gz = math.floor(pt2D.Y / cellSize)
		local key = tostring(gx) .. ":" .. tostring(gz)
		local bucket = grid[key]
		if not bucket then
			bucket = {}
			grid[key] = bucket
		end
		table.insert(bucket, pt2D)
	end

	for _ = 1, attempts do
		if #placements >= maxCount then
			break
		end
		local wx = rng:NextNumber(config.minXZ.X, config.maxXZ.X)
		local wz = rng:NextNumber(config.minXZ.Y, config.maxXZ.Y)
		local pt2D = Vector2.new(wx, wz)

		if isTooClose(pt2D) then
			rejSpace += 1
			continue
		end

		local hit = Workspace:Raycast(Vector3.new(wx, rayStartY, wz), Vector3.new(0, -rayDrop, 0), rayParams)
		if not hit then
			continue
		end

		if excludedMats[hit.Material] then
			rejMat += 1
			continue
		end

		local y = hit.Position.Y
		if y < minAlt or y > maxAlt then
			rejAlt += 1
			continue
		end

		local slopeDeg = math.deg(math.acos(math.clamp(hit.Normal.Y, -1, 1)))
		if slopeDeg > maxSlopeDeg then
			rejSlope += 1
			continue
		end

		insertGrid(pt2D)
		local yaw = rng:NextNumber(0, math.pi * 2)
		local scale = rng:NextNumber(scaleRange.X, scaleRange.Y)
		local rotCf = alignToNormal(hit.Normal, yaw, alignAlpha)
		table.insert(placements, {
			position = hit.Position,
			normal = hit.Normal,
			cframe = CFrame.new(hit.Position) * rotCf,
			scale = scale,
			material = hit.Material,
		})
	end

	return placements, {
		placedCount = #placements,
		rejectedWaterOrMaterial = rejMat,
		rejectedSlope = rejSlope,
		rejectedAltitude = rejAlt,
		rejectedSpacing = rejSpace,
		folderPath = "Workspace." .. (config.folderName or "SharpScatteredProps"),
	}
end

function PoissonSurfaceScatter.ScatterStylizedTreesAndRocks(config: ScatterConfig): (Folder, ScatterReport)
	local managedTag = config.tag or DEFAULT_TAG
	local folderName = config.folderName or "SharpScatteredProps"
	local existing = Workspace:FindFirstChild(folderName)
	if existing then
		existing:Destroy()
	end

	local folder = Instance.new("Folder")
	folder.Name = folderName
	CollectionService:AddTag(folder, managedTag)
	folder.Parent = Workspace

	local placements, report = PoissonSurfaceScatter.GeneratePlacements(config, { folder })
	for idx, p in ipairs(placements) do
		local isRock = (idx % 4 == 0)
		local model = Instance.new("Model")
		model.Name = if isRock then string.format("Rock_%03d", idx) else string.format("PineTree_%03d", idx)
		pcall(function()
			model.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
		end)
		CollectionService:AddTag(model, managedTag)

		if isRock then
			local rock = Instance.new("Part")
			rock.Name = "Boulder"
			rock.Size = Vector3.new(3.6, 2.4, 3.2) * p.scale
			rock.CFrame = p.cframe * CFrame.new(0, rock.Size.Y * 0.35, 0)
			rock.Anchored = true
			rock.Material = Enum.Material.Slate
			rock.Color = Color3.fromRGB(112, 116, 122)
			rock.CanTouch = false
			rock.Parent = model
			model.PrimaryPart = rock
		else
			local trunk = Instance.new("Part")
			trunk.Name = "Trunk"
			trunk.Size = Vector3.new(1.4, 7.0, 1.4) * p.scale
			trunk.CFrame = p.cframe * CFrame.new(0, trunk.Size.Y * 0.5, 0)
			trunk.Anchored = true
			trunk.Material = Enum.Material.Wood
			trunk.Color = Color3.fromRGB(108, 78, 54)
			trunk.CanTouch = false
			trunk.Parent = model

			local canopy = Instance.new("Part")
			canopy.Name = "Canopy"
			canopy.Shape = Enum.PartType.Ball
			canopy.Size = Vector3.new(6.2, 7.4, 6.2) * p.scale
			canopy.CFrame = trunk.CFrame * CFrame.new(0, trunk.Size.Y * 0.55, 0)
			canopy.Anchored = true
			canopy.CanCollide = false
			canopy.CanTouch = false
			canopy.Material = Enum.Material.Grass
			canopy.Color = Color3.fromRGB(58, 118, 68)
			canopy.Parent = model
			model.PrimaryPart = trunk
		end

		model.Parent = folder
	end

	report.folderPath = folder:GetFullName()
	return folder, report
end

function PoissonSurfaceScatter.Cleanup(tag: string?): number
	local targetTag = tag or DEFAULT_TAG
	local removed = 0
	for _, inst in ipairs(CollectionService:GetTagged(targetTag)) do
		if inst.Parent then
			inst:Destroy()
			removed += 1
		end
	end
	return removed
end

return PoissonSurfaceScatter

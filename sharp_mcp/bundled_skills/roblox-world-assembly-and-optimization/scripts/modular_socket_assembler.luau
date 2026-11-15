--!strict
--[[
	ModularSocketAssembler
	Snaps modular 3D architecture kits (walls, arches, corridors, floors) together
	using named Attachment sockets (`SnapSocket_North`, `SnapSocket_South`,
	`SnapSocket_East`, `SnapSocket_West`) and PivotTo math.
]]

local CollectionService = game:GetService("CollectionService")

local DEFAULT_TAG = "SharpModularKitManaged"

local ModularSocketAssembler = {}

function ModularSocketAssembler.CreateModularSegment(
	name: string,
	size: Vector3,
	originCFrame: CFrame,
	parent: Instance?,
	tag: string?
): Model
	local managedTag = tag or DEFAULT_TAG
	local model = Instance.new("Model")
	model.Name = name
	CollectionService:AddTag(model, managedTag)

	local part = Instance.new("Part")
	part.Name = "StructureBody"
	part.Size = size
	part.CFrame = originCFrame
	part.Anchored = true
	part.CanTouch = false
	part.Material = Enum.Material.Limestone
	part.Color = Color3.fromRGB(214, 206, 192)
	part.Parent = model

	local halfX = size.X * 0.5
	local halfZ = size.Z * 0.5

	local sockets = {
		{ name = "SnapSocket_North", pos = Vector3.new(0, 0, -halfZ), rot = CFrame.Angles(0, 0, 0) },
		{ name = "SnapSocket_South", pos = Vector3.new(0, 0, halfZ), rot = CFrame.Angles(0, math.pi, 0) },
		{ name = "SnapSocket_East", pos = Vector3.new(halfX, 0, 0), rot = CFrame.Angles(0, -math.pi * 0.5, 0) },
		{ name = "SnapSocket_West", pos = Vector3.new(-halfX, 0, 0), rot = CFrame.Angles(0, math.pi * 0.5, 0) },
	}

	for _, s in ipairs(sockets) do
		local att = Instance.new("Attachment")
		att.Name = s.name
		att.CFrame = CFrame.new(s.pos) * s.rot
		att.Parent = part
	end

	model.PrimaryPart = part
	if parent then
		model.Parent = parent
	end
	return model
end

function ModularSocketAssembler.FindSocket(model: Model, socketName: string): Attachment?
	for _, d in ipairs(model:GetDescendants()) do
		if d:IsA("Attachment") and d.Name == socketName then
			return d
		end
	end
	return nil
end

function ModularSocketAssembler.SnapModelToSocket(
	newModel: Model,
	sourceSocketName: string,
	targetModel: Model,
	targetSocketName: string
): (boolean, CFrame?, string)
	local srcAtt = ModularSocketAssembler.FindSocket(newModel, sourceSocketName)
	if not srcAtt then
		return false, nil, "SOURCE_SOCKET_NOT_FOUND:" .. sourceSocketName
	end
	local tgtAtt = ModularSocketAssembler.FindSocket(targetModel, targetSocketName)
	if not tgtAtt then
		return false, nil, "TARGET_SOCKET_NOT_FOUND:" .. targetSocketName
	end

	-- Sockets point outward; rotate 180 deg around Y so sourceSocket faces targetSocket flush
	local desiredSocketWorldCF = tgtAtt.WorldCFrame * CFrame.Angles(0, math.pi, 0)
	local pivotToSourceOffset = newModel:GetPivot():ToObjectSpace(srcAtt.WorldCFrame)
	local targetPivotCF = desiredSocketWorldCF * pivotToSourceOffset:Inverse()
	newModel:PivotTo(targetPivotCF)

	local snapErrorStuds = (srcAtt.WorldCFrame.Position - tgtAtt.WorldCFrame.Position).Magnitude
	if snapErrorStuds > 1e-2 then
		return false, targetPivotCF, string.format("SNAP_ALIGNMENT_DRIFT:%.4f", snapErrorStuds)
	end
	return true, targetPivotCF, "SNAPPED_FLUSH"
end

function ModularSocketAssembler.Cleanup(tag: string?): number
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

return ModularSocketAssembler

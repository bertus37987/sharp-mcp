--!strict
--[[
	VfxPresetAndHighlightPool
	Provides:
	1. Deterministic one-shot ParticleEmitter burst presets (Rate = 0 + :Emit(n))
	   with power-of-two FlipbookLayout support and built-in rbxasset://textures/particles/*.
	2. A hard-capped Highlight Pool Manager (max 28 active Highlights, safely under
	   Roblox's 31 simultaneous Highlight engine limit) with LRU eviction.
]]

local CollectionService = game:GetService("CollectionService")
local Workspace = game:GetService("Workspace")

export type VfxPresetKind = "HitSparks" | "ExplosionFlipbook" | "LevelUpNova" | "DashSmoke"

export type HighlightSlot = {
	highlight: Highlight,
	inUse: boolean,
	assignedAt: number,
	target: Instance?,
}

export type HighlightPool = {
	container: Folder,
	maxSlots: number,
	slots: { HighlightSlot },
}

local MAX_SAFE_HIGHLIGHTS = 28
local DEFAULT_TAG = "SharpVfxAndHighlightManaged"

local VfxPresetAndHighlightPool = {
	MAX_SAFE_HIGHLIGHTS = MAX_SAFE_HIGHLIGHTS,
}

function VfxPresetAndHighlightPool.CreateEmitterPreset(
	presetKind: VfxPresetKind,
	parent: Instance,
	emitImmediatelyCount: number?,
	tag: string?
): ParticleEmitter
	local managedTag = tag or DEFAULT_TAG
	local pe = Instance.new("ParticleEmitter")
	pe.Name = "VFX_" .. presetKind
	pe.Rate = 0 -- Strict burst discipline: Rate = 0 + :Emit(n)
	CollectionService:AddTag(pe, managedTag)

	if presetKind == "HitSparks" then
		pe.Texture = "rbxasset://textures/particles/sparkles_main.dds"
		pe.Color = ColorSequence.new(Color3.fromRGB(255, 220, 120), Color3.fromRGB(255, 95, 40))
		pe.LightEmission = 0.85
		pe.Size = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.55),
			NumberSequenceKeypoint.new(1, 0.0),
		})
		pe.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.0),
			NumberSequenceKeypoint.new(1, 1.0),
		})
		pe.Lifetime = NumberRange.new(0.18, 0.35)
		pe.Speed = NumberRange.new(16, 32)
		pe.SpreadAngle = Vector2.new(180, 180)
		pe.Drag = 6.0
	elseif presetKind == "ExplosionFlipbook" then
		pe.Texture = "rbxasset://textures/particles/explosion01_implosion_main.dds"
		pcall(function()
			pe.FlipbookLayout = Enum.ParticleFlipbookLayout.FourByFour
			pe.FlipbookMode = Enum.ParticleFlipbookMode.OneShot
		end)
		pe.LightEmission = 0.75
		pe.Size = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 1.5),
			NumberSequenceKeypoint.new(0.5, 4.2),
			NumberSequenceKeypoint.new(1, 5.0),
		})
		pe.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.05),
			NumberSequenceKeypoint.new(0.8, 0.35),
			NumberSequenceKeypoint.new(1, 1.0),
		})
		pe.Lifetime = NumberRange.new(0.35, 0.55)
		pe.Speed = NumberRange.new(2, 8)
		pe.SpreadAngle = Vector2.new(90, 90)
	elseif presetKind == "LevelUpNova" then
		pe.Texture = "rbxasset://textures/particles/sparkles_main.dds"
		pe.Color = ColorSequence.new(Color3.fromRGB(110, 235, 255), Color3.fromRGB(185, 130, 255))
		pe.LightEmission = 1.0
		pe.Size = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.8),
			NumberSequenceKeypoint.new(0.7, 1.2),
			NumberSequenceKeypoint.new(1, 0.0),
		})
		pe.Lifetime = NumberRange.new(0.5, 0.9)
		pe.Speed = NumberRange.new(12, 24)
		pe.SpreadAngle = Vector2.new(180, 45)
		pe.Acceleration = Vector3.new(0, 14, 0)
	else -- DashSmoke
		pe.Texture = "rbxasset://textures/particles/smoke_main.dds"
		pe.Color = ColorSequence.new(Color3.fromRGB(200, 210, 225))
		pe.LightEmission = 0.1
		pe.Size = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 1.2),
			NumberSequenceKeypoint.new(1, 2.8),
		})
		pe.Transparency = NumberSequence.new({
			NumberSequenceKeypoint.new(0, 0.35),
			NumberSequenceKeypoint.new(1, 1.0),
		})
		pe.Lifetime = NumberRange.new(0.25, 0.45)
		pe.Speed = NumberRange.new(4, 10)
		pe.SpreadAngle = Vector2.new(60, 30)
	end

	pe.Parent = parent
	if emitImmediatelyCount and emitImmediatelyCount > 0 then
		pe:Emit(emitImmediatelyCount)
	end
	return pe
end

function VfxPresetAndHighlightPool.CreateHighlightPool(maxSlots: number?, tag: string?): HighlightPool
	local managedTag = tag or DEFAULT_TAG
	local capped = math.clamp(maxSlots or MAX_SAFE_HIGHLIGHTS, 1, MAX_SAFE_HIGHLIGHTS)

	local existing = Workspace:FindFirstChild("_SharpHighlightPool")
	if existing then
		existing:Destroy()
	end

	local folder = Instance.new("Folder")
	folder.Name = "_SharpHighlightPool"
	folder:SetAttribute("MaxHighlightCap", capped)
	CollectionService:AddTag(folder, managedTag)
	folder.Parent = Workspace

	local slots: { HighlightSlot } = table.create(capped)
	for i = 1, capped do
		local hl = Instance.new("Highlight")
		hl.Name = string.format("PooledHighlight_%02d", i)
		hl.Enabled = false
		hl.Adornee = nil
		hl.DepthMode = Enum.HighlightDepthMode.Occluded
		hl.FillTransparency = 1
		hl.OutlineTransparency = 1
		CollectionService:AddTag(hl, managedTag)
		hl.Parent = folder
		slots[i] = {
			highlight = hl,
			inUse = false,
			assignedAt = 0,
			target = nil,
		}
	end

	return {
		container = folder,
		maxSlots = capped,
		slots = slots,
	}
end

function VfxPresetAndHighlightPool.AcquireHighlight(
	pool: HighlightPool,
	target: Instance,
	fillColor: Color3?,
	outlineColor: Color3?,
	fillTransparency: number?,
	outlineTransparency: number?
): (Highlight, boolean)
	-- 1. Check if target already has an active highlight in the pool
	for _, slot in ipairs(pool.slots) do
		if slot.inUse and slot.target == target then
			slot.assignedAt = os.clock()
			slot.highlight.FillColor = fillColor or Color3.fromRGB(255, 80, 80)
			slot.highlight.OutlineColor = outlineColor or Color3.fromRGB(255, 255, 255)
			slot.highlight.FillTransparency = fillTransparency or 0.30
			slot.highlight.OutlineTransparency = outlineTransparency or 0.0
			return slot.highlight, false
		end
	end

	-- 2. Find first free slot, or evict oldest (LRU) so we NEVER exceed 28 active Highlights
	local chosenSlot: HighlightSlot? = nil
	local evicted = false
	for _, slot in ipairs(pool.slots) do
		if not slot.inUse then
			chosenSlot = slot
			break
		end
	end

	if not chosenSlot then
		evicted = true
		local oldest = pool.slots[1]
		for i = 2, #pool.slots do
			if pool.slots[i].assignedAt < oldest.assignedAt then
				oldest = pool.slots[i]
			end
		end
		chosenSlot = oldest
	end

	assert(chosenSlot ~= nil, "HighlightPool must have at least 1 slot")
	chosenSlot.inUse = true
	chosenSlot.assignedAt = os.clock()
	chosenSlot.target = target
	chosenSlot.highlight.Adornee = target
	chosenSlot.highlight.FillColor = fillColor or Color3.fromRGB(255, 80, 80)
	chosenSlot.highlight.OutlineColor = outlineColor or Color3.fromRGB(255, 255, 255)
	chosenSlot.highlight.FillTransparency = fillTransparency or 0.30
	chosenSlot.highlight.OutlineTransparency = outlineTransparency or 0.0
	chosenSlot.highlight.Enabled = true
	return chosenSlot.highlight, evicted
end

function VfxPresetAndHighlightPool.ReleaseHighlight(pool: HighlightPool, targetOrHighlight: Instance): boolean
	for _, slot in ipairs(pool.slots) do
		if slot.target == targetOrHighlight or slot.highlight == targetOrHighlight then
			slot.inUse = false
			slot.target = nil
			slot.highlight.Enabled = false
			slot.highlight.Adornee = nil
			slot.highlight.FillTransparency = 1
			slot.highlight.OutlineTransparency = 1
			return true
		end
	end
	return false
end

function VfxPresetAndHighlightPool.GetActiveCount(pool: HighlightPool): number
	local c = 0
	for _, slot in ipairs(pool.slots) do
		if slot.inUse then
			c += 1
		end
	end
	return c
end

function VfxPresetAndHighlightPool.Cleanup(tag: string?): number
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

return VfxPresetAndHighlightPool

--!strict
-- probe_rig.luau
-- Dumps ANY Roblox Studio rig (R15, R6, AnimationConstraint, Motor6D, Skinned MeshPart+Bone,
-- held Weapons/Shields, or Non-Humanoid Model) into compact JSON for Blender rig building.
--
-- Usage in execute_luau (datamodel_type = "Edit"):
--   1. Select the target Model in Studio Explorer (or set TARGET_PATH below), OR
--   2. Leave nothing selected to dump a freshly created standard Blocky R15 rig.

local HttpService = game:GetService("HttpService")
local Players = game:GetService("Players")
local Selection = game:GetService("Selection")

-- Optional explicit path, e.g. "Workspace.MyCreature". Empty = use Selection or spawn temp R15.
local TARGET_PATH: string = ""
-- If spawning a temporary avatar when nothing is selected: "R15" or "R6"
local DEFAULT_FALLBACK_RIG: "R15" | "R6" = "R15"

local function resolvePath(path: string): Instance?
	if path == "" then
		return nil
	end
	local current: Instance = game
	for segment in string.gmatch(path, "[^%.]+") do
		local nextInst = if current == game
			then (pcall(function() return game:GetService(segment) end) and game:GetService(segment) or current:FindFirstChild(segment))
			else current:FindFirstChild(segment)
		if not nextInst then
			return nil
		end
		current = nextInst
	end
	return current
end

local function cfComponents(cf: CFrame): { number }
	local x, y, z, r00, r01, r02, r10, r11, r12, r20, r21, r22 = cf:GetComponents()
	return {
		math.round(x * 1e6) / 1e6, math.round(y * 1e6) / 1e6, math.round(z * 1e6) / 1e6,
		math.round(r00 * 1e6) / 1e6, math.round(r01 * 1e6) / 1e6, math.round(r02 * 1e6) / 1e6,
		math.round(r10 * 1e6) / 1e6, math.round(r11 * 1e6) / 1e6, math.round(r12 * 1e6) / 1e6,
		math.round(r20 * 1e6) / 1e6, math.round(r21 * 1e6) / 1e6, math.round(r22 * 1e6) / 1e6,
	}
end

local targetModel: Model? = nil
local cleanupModel = false

local explicit = resolvePath(TARGET_PATH)
if explicit and explicit:IsA("Model") then
	targetModel = explicit
elseif #Selection:Get() > 0 then
	local first = Selection:Get()[1]
	if first:IsA("Model") then
		targetModel = first
	end
end

if not targetModel then
	local desc = Instance.new("HumanoidDescription")
	local rigType = if DEFAULT_FALLBACK_RIG == "R6" then Enum.HumanoidRigType.R6 else Enum.HumanoidRigType.R15
	targetModel = Players:CreateHumanoidModelFromDescriptionAsync(desc, rigType)
	desc:Destroy()
	cleanupModel = true
end

assert(targetModel ~= nil, "Failed to resolve or spawn target Model")

local parts: { [string]: any } = {}
local joints: { [string]: any } = {}
local bones: { [string]: any } = {}
local grips: { [string]: any } = {}
local seenPartNames: { [string]: number } = {}

local function uniqueKey(map: { [string]: any }, counts: { [string]: number }, baseName: string): string
	if map[baseName] == nil then
		counts[baseName] = 1
		return baseName
	end
	local n = (counts[baseName] or 1) + 1
	counts[baseName] = n
	return baseName .. "_" .. tostring(n)
end

for _, inst in ipairs(targetModel:GetDescendants()) do
	if inst:IsA("BasePart") then
		local key = uniqueKey(parts, seenPartNames, inst.Name)
		parts[key] = {
			name = inst.Name,
			class = inst.ClassName,
			size = {
				math.round(inst.Size.X * 1e5) / 1e5,
				math.round(inst.Size.Y * 1e5) / 1e5,
				math.round(inst.Size.Z * 1e5) / 1e5,
			},
			cf = cfComponents(inst.CFrame),
			anchored = inst.Anchored,
		}
	elseif inst:IsA("AnimationConstraint") then
		local a0 = inst.Attachment0
		local a1 = inst.Attachment1
		if a0 and a1 and a0.Parent and a1.Parent then
			table.insert(joints, {
				name = inst.Name,
				kind = "AnimationConstraint",
				p0 = a0.Parent.Name,
				p1 = a1.Parent.Name,
				c0 = cfComponents(a0.CFrame),
				c1 = cfComponents(a1.CFrame),
				isKinematic = inst.IsKinematic,
			})
		end
	elseif inst:IsA("Motor6D") then
		if inst.Part0 and inst.Part1 then
			table.insert(joints, {
				name = inst.Name,
				kind = "Motor6D",
				p0 = inst.Part0.Name,
				p1 = inst.Part1.Name,
				c0 = cfComponents(inst.C0),
				c1 = cfComponents(inst.C1),
			})
		end
	elseif inst:IsA("Bone") then
		local parent = inst.Parent
		local hostPart = inst:FindFirstAncestorWhichIsA("BasePart")
		table.insert(bones, {
			name = inst.Name,
			parent = if parent then parent.Name else nil,
			parentIsBone = if parent then parent:IsA("Bone") else false,
			hostPart = if hostPart then hostPart.Name else nil,
			cf = cfComponents(inst.CFrame),
			worldCf = cfComponents(inst.WorldCFrame),
		})
	elseif inst:IsA("Attachment") and not inst:IsA("Bone") then
		if string.find(inst.Name, "Grip") or string.find(inst.Name, "Socket") then
			local parentPart = inst.Parent
			if parentPart and parentPart:IsA("BasePart") then
				grips[parentPart.Name .. "." .. inst.Name] = {
					name = inst.Name,
					parent = parentPart.Name,
					cf = cfComponents(inst.CFrame),
				}
			end
		end
	end
end

local humanoid = targetModel:FindFirstChildOfClass("Humanoid")
local animController = targetModel:FindFirstChildOfClass("AnimationController")
local rootPart = targetModel:FindFirstChild("HumanoidRootPart") :: BasePart?
	or targetModel.PrimaryPart
	or targetModel:FindFirstChildWhichIsA("BasePart")

local rigKind = "Custom"
if humanoid then
	rigKind = if humanoid.RigType == Enum.HumanoidRigType.R6 then "R6" else "R15"
elseif #bones > 0 and #joints == 0 then
	rigKind = "Skinned"
end

local payload = {
	modelName = targetModel.Name,
	rigKind = rigKind,
	hasHumanoid = humanoid ~= nil,
	hasAnimationController = animController ~= nil,
	rootName = if rootPart then rootPart.Name else nil,
	hipHeight = if humanoid then humanoid.HipHeight else nil,
	parts = parts,
	joints = joints,
	bones = bones,
	grips = grips,
}

if cleanupModel then
	targetModel:Destroy()
end

local json = HttpService:JSONEncode(payload)
return json

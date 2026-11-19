--!strict
--[[
	WeaponToolAssembler
	Builds Motor6D weapon/holster socket bindings, combo state machines, and
	modern Input Action System (InputContext -> InputAction -> InputBinding)
	hierarchies without legacy server Scripts inside Tool instances.
]]

local CollectionService = game:GetService("CollectionService")

export type WeaponSpec = {
	weaponId: string,
	displayName: string,
	gripPartName: string?,
	holsterPartName: string?,
	gripOffsetCFrame: CFrame?,
	holsterOffsetCFrame: CFrame?,
	comboCount: number?,
	comboResetWindowSec: number?,
	baseDamage: number?,
	attackCooldownSec: number?,
	rangeStuds: number?,
	bladeSize: Vector3?,
	tag: string?,
}

export type ComboState = {
	weaponId: string,
	equipped: boolean,
	blocking: boolean,
	comboStep: number,
	maxCombo: number,
	lastSwingTime: number,
	cooldownSec: number,
	comboResetWindowSec: number,
}

local DEFAULT_TAG = "SharpWeaponSystemManaged"

local WeaponToolAssembler = {}

function WeaponToolAssembler.BuildInputContext(parent: Instance, contextName: string?, tag: string?): Instance
	local ctxName = contextName or "CombatInputContext"
	local managedTag = tag or DEFAULT_TAG

	local existing = parent:FindFirstChild(ctxName)
	if existing then
		existing:Destroy()
	end

	local okIas, ctxOrErr = pcall(function()
		local ctx = Instance.new("InputContext")
		ctx.Name = ctxName
		CollectionService:AddTag(ctx, managedTag)

		local actions = {
			{ name = "AttackPrimary", key = Enum.KeyCode.MouseLeftButton, gamepad = Enum.KeyCode.ButtonR2, touchBtn = true },
			{ name = "AttackHeavy", key = Enum.KeyCode.R, gamepad = Enum.KeyCode.ButtonY, touchBtn = true },
			{ name = "BlockHold", key = Enum.KeyCode.F, gamepad = Enum.KeyCode.ButtonL2, touchBtn = true },
			{ name = "Dash", key = Enum.KeyCode.Q, gamepad = Enum.KeyCode.ButtonB, touchBtn = true },
			{ name = "ToggleEquip", key = Enum.KeyCode.One, gamepad = Enum.KeyCode.DPadUp, touchBtn = false },
		}

		for _, spec in ipairs(actions) do
			local act = Instance.new("InputAction")
			act.Name = spec.name
			act.Type = Enum.InputActionType.Bool
			act.Parent = ctx

			local kbBind = Instance.new("InputBinding")
			kbBind.Name = "KeyboardMouseBinding"
			kbBind.KeyCode = spec.key
			kbBind.Parent = act

			local gpBind = Instance.new("InputBinding")
			gpBind.Name = "GamepadBinding"
			gpBind.KeyCode = spec.gamepad
			gpBind.Parent = act
		end

		ctx.Parent = parent
		return ctx
	end)

	if okIas and ctxOrErr then
		return ctxOrErr :: Instance
	end

	-- Fallback Folder descriptor if InputContext is disabled in older Studio FFlags
	local fallback = Instance.new("Folder")
	fallback.Name = ctxName
	fallback:SetAttribute("InputSystemKind", "FallbackDescriptor")
	CollectionService:AddTag(fallback, managedTag)
	fallback.Parent = parent
	return fallback
end

function WeaponToolAssembler.AssembleWeaponModel(spec: WeaponSpec, parent: Instance?): (Model, BasePart)
	local managedTag = spec.tag or DEFAULT_TAG
	local model = Instance.new("Model")
	model.Name = spec.weaponId
	model:SetAttribute("WeaponId", spec.weaponId)
	model:SetAttribute("DisplayName", spec.displayName)
	model:SetAttribute("BaseDamage", spec.baseDamage or 25)
	model:SetAttribute("AttackCooldownSec", spec.attackCooldownSec or 0.42)
	model:SetAttribute("RangeStuds", spec.rangeStuds or 8.5)
	model:SetAttribute("MaxCombo", spec.comboCount or 3)
	CollectionService:AddTag(model, managedTag)

	local handle = Instance.new("Part")
	handle.Name = "Handle"
	handle.Size = Vector3.new(0.4, 1.2, 0.4)
	handle.CanCollide = false
	handle.CanQuery = false
	handle.CanTouch = false
	handle.Massless = true
	handle.Color = Color3.fromRGB(95, 102, 118)
	handle.Material = Enum.Material.Metal
	handle.Parent = model

	local blade = Instance.new("Part")
	blade.Name = "BladeHitbox"
	blade.Size = spec.bladeSize or Vector3.new(0.35, 3.8, 0.8)
	blade.CFrame = handle.CFrame * CFrame.new(0, 2.4, 0)
	blade.CanCollide = false
	blade.CanQuery = false
	blade.CanTouch = false
	blade.Massless = true
	blade.Color = Color3.fromRGB(210, 220, 235)
	blade.Material = Enum.Material.Metal
	blade.Parent = model

	local weld = Instance.new("WeldConstraint")
	weld.Name = "BladeWeld"
	weld.Part0 = handle
	weld.Part1 = blade
	weld.Parent = handle

	local gripAtt = Instance.new("Attachment")
	gripAtt.Name = "GripAttachment"
	gripAtt.Parent = handle

	local trailTop = Instance.new("Attachment")
	trailTop.Name = "TrailTipAttachment"
	trailTop.Position = Vector3.new(0, blade.Size.Y * 0.5, 0)
	trailTop.Parent = blade

	local trailBase = Instance.new("Attachment")
	trailBase.Name = "TrailBaseAttachment"
	trailBase.Position = Vector3.new(0, -blade.Size.Y * 0.5, 0)
	trailBase.Parent = blade

	local trail = Instance.new("Trail")
	trail.Name = "SwingTrail"
	trail.Attachment0 = trailBase
	trail.Attachment1 = trailTop
	trail.Enabled = false
	trail.Lifetime = 0.18
	trail.MinLength = 0.05
	trail.FaceCamera = false
	trail.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.15),
		NumberSequenceKeypoint.new(1, 1.0),
	})
	trail.Parent = blade

	model.PrimaryPart = handle
	if parent then
		model.Parent = parent
	end
	return model, handle
end

function WeaponToolAssembler.BindToCharacter(
	character: Model,
	weaponModel: Model,
	spec: WeaponSpec,
	equipped: boolean,
	jointMode: ("auto" | "Motor6D" | "AnimationConstraint")?
): Motor6D | AnimationConstraint
	local handle = (weaponModel.PrimaryPart or weaponModel:FindFirstChild("Handle")) :: BasePart?
	assert(handle ~= nil, "Weapon Model must have a PrimaryPart or Handle.")

	local handName = spec.gripPartName or "RightHand"
	local holsterName = spec.holsterPartName or "UpperTorso"
	local targetPartName = if equipped then handName else holsterName
	local hostPart = (character:FindFirstChild(targetPartName) or character:FindFirstChild("HumanoidRootPart") or character.PrimaryPart) :: BasePart?
	assert(hostPart ~= nil, "Character lacks target socket part for WeaponToolAssembler.")

	weaponModel.Parent = character
	local motorName = "WeaponMotor_" .. spec.weaponId
	local animJointName = "WeaponAnimConstraint_" .. spec.weaponId
	local offsetCf = if equipped
		then (spec.gripOffsetCFrame or CFrame.new(0, -0.15, 0) * CFrame.Angles(math.rad(-90), 0, 0))
		else (spec.holsterOffsetCFrame or CFrame.new(-0.85, -0.6, 0.55) * CFrame.Angles(0, 0, math.rad(135)))

	-- Remove any competing Motor6D or AnimationConstraint bindings across sockets
	for _, d in ipairs(character:GetDescendants()) do
		if (d:IsA("Motor6D") and d.Name == motorName) or (d:IsA("AnimationConstraint") and d.Name == animJointName) then
			d:Destroy()
		end
	end

	local mode = jointMode or "auto"
	local useAnimConstraint = (mode == "AnimationConstraint") or (mode == "auto" and character:FindFirstChildWhichIsA("AnimationConstraint", true) ~= nil)
	if useAnimConstraint then
		local hostAttName = "WeaponSocketAtt_" .. spec.weaponId
		local hostAttInst = hostPart:FindFirstChild(hostAttName)
		local hostAtt: Attachment
		if hostAttInst and hostAttInst:IsA("Attachment") then
			hostAtt = hostAttInst
		else
			hostAtt = Instance.new("Attachment")
			hostAtt.Name = hostAttName
			hostAtt.Parent = hostPart
		end
		hostAtt.CFrame = offsetCf

		local handleAttName = "WeaponGripAtt_" .. spec.weaponId
		local handleAttInst = handle:FindFirstChild(handleAttName)
		local handleAtt: Attachment
		if handleAttInst and handleAttInst:IsA("Attachment") then
			handleAtt = handleAttInst
		else
			handleAtt = Instance.new("Attachment")
			handleAtt.Name = handleAttName
			handleAtt.CFrame = CFrame.identity
			handleAtt.Parent = handle
		end

		local animJoint = Instance.new("AnimationConstraint")
		animJoint.Name = animJointName
		animJoint.Attachment0 = hostAtt
		animJoint.Attachment1 = handleAtt
		animJoint.Enabled = true
		animJoint.Parent = hostPart

		character:SetAttribute("EquippedWeaponId", if equipped then spec.weaponId else "")
		return animJoint
	end

	local motor = Instance.new("Motor6D")
	motor.Name = motorName
	motor.Part0 = hostPart
	motor.Part1 = handle
	motor.C0 = offsetCf
	motor.C1 = CFrame.identity
	motor.Parent = hostPart

	character:SetAttribute("EquippedWeaponId", if equipped then spec.weaponId else "")
	return motor
end

function WeaponToolAssembler.CreateComboState(spec: WeaponSpec): ComboState
	return {
		weaponId = spec.weaponId,
		equipped = true,
		blocking = false,
		comboStep = 0,
		maxCombo = spec.comboCount or 3,
		lastSwingTime = 0,
		cooldownSec = spec.attackCooldownSec or 0.42,
		comboResetWindowSec = spec.comboResetWindowSec or 1.25,
	}
end

function WeaponToolAssembler.TryAdvanceCombo(state: ComboState, nowClock: number?): (boolean, number, string)
	local now = nowClock or os.clock()
	if not state.equipped then
		return false, state.comboStep, "NOT_EQUIPPED"
	end
	if state.blocking then
		return false, state.comboStep, "BLOCKING"
	end
	if (now - state.lastSwingTime) < state.cooldownSec then
		return false, state.comboStep, "ON_COOLDOWN"
	end
	if (now - state.lastSwingTime) > state.comboResetWindowSec or state.comboStep >= state.maxCombo then
		state.comboStep = 1
	else
		state.comboStep += 1
	end
	state.lastSwingTime = now
	return true, state.comboStep, "SWING_" .. tostring(state.comboStep)
end

function WeaponToolAssembler.Cleanup(tag: string?): number
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

return WeaponToolAssembler

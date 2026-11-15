--!strict
--[[
	ControllerManagerRig
	Configures modern Roblox physics character controllers (ControllerManager +
	GroundController + AirController + ClimbController + SwimController +
	ControllerPartSensor) on R15 or custom character rigs, with deterministic
	dash, jump impulse, and state evaluation helpers.
]]

local CollectionService = game:GetService("CollectionService")

export type ControllerRigConfig = {
	baseMoveSpeed: number?,
	sprintMultiplier: number?,
	groundOffset: number?,
	floorSearchDistance: number?,
	ladderSearchDistance: number?,
	airControlForce: number?,
	turnSpeedFactor: number?,
	disableHumanoidStateMachine: boolean?,
	tag: string?,
}

export type ControllerRigBundle = {
	character: Model,
	rootPart: BasePart,
	manager: ControllerManager,
	groundController: GroundController,
	airController: AirController,
	climbController: ClimbController,
	swimController: SwimController,
	floorSensor: ControllerPartSensor,
	climbSensor: ControllerPartSensor,
}

local DEFAULT_TAG = "SharpControllerManagerManaged"

local ControllerManagerRig = {}

local function getOrCreate(parent: Instance, className: string, name: string, tag: string): Instance
	local existing = parent:FindFirstChild(name)
	if existing and existing.ClassName == className then
		CollectionService:AddTag(existing, tag)
		return existing
	end
	if existing then
		existing:Destroy()
	end
	local inst = Instance.new(className)
	inst.Name = name
	CollectionService:AddTag(inst, tag)
	inst.Parent = parent
	return inst
end

function ControllerManagerRig.Attach(character: Model, config: ControllerRigConfig?): ControllerRigBundle
	local cfg: ControllerRigConfig = config or {}
	local tag = cfg.tag or DEFAULT_TAG
	local rootPart = (character:FindFirstChild("HumanoidRootPart") or character.PrimaryPart or character:FindFirstChildWhichIsA("BasePart")) :: BasePart?
	assert(rootPart ~= nil, "Character Model must contain a HumanoidRootPart or BasePart.")

	local humanoid = character:FindFirstChildOfClass("Humanoid")
	local hipHeight = if humanoid then math.max(1.5, humanoid.HipHeight) else 2.0
	local groundOffset = cfg.groundOffset or hipHeight

	if humanoid and (if cfg.disableHumanoidStateMachine == nil then true else cfg.disableHumanoidStateMachine) then
		pcall(function()
			humanoid.EvaluateStateMachine = false
		end)
	end

	local floorSensor = getOrCreate(rootPart, "ControllerPartSensor", "GroundSensor", tag) :: ControllerPartSensor
	floorSensor.SensorMode = Enum.SensorMode.Floor
	floorSensor.UpdateType = Enum.SensorUpdateType.OnRead
	floorSensor.SearchDistance = cfg.floorSearchDistance or (groundOffset + 1.25)

	local climbSensor = getOrCreate(rootPart, "ControllerPartSensor", "ClimbSensor", tag) :: ControllerPartSensor
	climbSensor.SensorMode = Enum.SensorMode.Ladder
	climbSensor.UpdateType = Enum.SensorUpdateType.OnRead
	climbSensor.SearchDistance = cfg.ladderSearchDistance or 1.75

	local manager = getOrCreate(character, "ControllerManager", "ControllerManager", tag) :: ControllerManager
	manager.RootPart = rootPart
	manager.BaseMoveSpeed = cfg.baseMoveSpeed or 18
	manager.BaseTurnSpeed = cfg.turnSpeedFactor or 8
	manager.GroundSensor = floorSensor
	manager.ClimbSensor = climbSensor
	manager.MovingDirection = Vector3.zero
	manager.FacingDirection = rootPart.CFrame.LookVector

	local groundCtrl = getOrCreate(manager, "GroundController", "GroundController", tag) :: GroundController
	groundCtrl.GroundOffset = groundOffset
	groundCtrl.AccelerationTime = 0.08
	groundCtrl.DecelerationTime = 0.06
	groundCtrl.Friction = 2.0
	groundCtrl.FrictionWeight = 1.0
	groundCtrl.StandForce = 20000
	groundCtrl.StandSpeed = 20
	groundCtrl.BalanceRigidityEnabled = true

	local airCtrl = getOrCreate(manager, "AirController", "AirController", tag) :: AirController
	airCtrl.MoveMaxForce = cfg.airControlForce or 12000
	airCtrl.MaintainLinearMomentum = true
	airCtrl.MaintainAngularMomentum = false
	airCtrl.BalanceRigidityEnabled = true

	local climbCtrl = getOrCreate(manager, "ClimbController", "ClimbController", tag) :: ClimbController
	climbCtrl.AccelerationTime = 0.05
	climbCtrl.MoveMaxForce = 10000

	local swimCtrl = getOrCreate(manager, "SwimController", "SwimController", tag) :: SwimController
	swimCtrl.AccelerationTime = 0.12

	manager.ActiveController = groundCtrl
	character:SetAttribute("SharpControllerSpeed", manager.BaseMoveSpeed)
	character:SetAttribute("SharpSprintMultiplier", cfg.sprintMultiplier or 1.45)

	return {
		character = character,
		rootPart = rootPart,
		manager = manager,
		groundController = groundCtrl,
		airController = airCtrl,
		climbController = climbCtrl,
		swimController = swimCtrl,
		floorSensor = floorSensor,
		climbSensor = climbSensor,
	}
end

function ControllerManagerRig.StepState(
	bundle: ControllerRigBundle,
	worldMoveDir: Vector3,
	facingDir: Vector3?,
	isSprinting: boolean?
): string
	local moveUnit = if worldMoveDir.Magnitude > 1e-3 then Vector3.new(worldMoveDir.X, 0, worldMoveDir.Z).Unit else Vector3.zero
	local baseSpeed = (bundle.character:GetAttribute("SharpControllerSpeed") :: number?) or 18
	local sprintMult = (bundle.character:GetAttribute("SharpSprintMultiplier") :: number?) or 1.45
	bundle.manager.BaseMoveSpeed = if isSprinting then baseSpeed * sprintMult else baseSpeed
	bundle.manager.MovingDirection = moveUnit

	if facingDir and facingDir.Magnitude > 1e-3 then
		bundle.manager.FacingDirection = Vector3.new(facingDir.X, 0, facingDir.Z).Unit
	elseif moveUnit.Magnitude > 1e-3 then
		bundle.manager.FacingDirection = moveUnit
	end

	if bundle.climbSensor.SensedPart ~= nil then
		bundle.manager.ActiveController = bundle.climbController
		return "Climb"
	elseif bundle.floorSensor.SensedPart ~= nil then
		bundle.manager.ActiveController = bundle.groundController
		return "Ground"
	else
		bundle.manager.ActiveController = bundle.airController
		return "Air"
	end
end

function ControllerManagerRig.PerformDash(
	bundle: ControllerRigBundle,
	direction: Vector3?,
	dashSpeedStudsPerSec: number?,
	upwardBoost: number?
): Vector3
	local dir = direction or bundle.manager.FacingDirection
	local flat = Vector3.new(dir.X, 0, dir.Z)
	local unit = if flat.Magnitude > 1e-3 then flat.Unit else Vector3.new(0, 0, -1)
	local speed = dashSpeedStudsPerSec or 68
	local up = upwardBoost or 8
	local velocity = unit * speed + Vector3.new(0, up, 0)
	bundle.rootPart.AssemblyLinearVelocity = velocity
	bundle.character:SetAttribute("LastDashTimestamp", os.clock())
	return velocity
end

function ControllerManagerRig.Cleanup(tag: string?): number
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

return ControllerManagerRig

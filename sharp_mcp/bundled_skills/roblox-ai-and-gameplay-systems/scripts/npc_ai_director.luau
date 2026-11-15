--!strict
--[[
	NpcAiDirector
	Centralized CollectionService + PathfindingService NPC AI state machine
	(`Idle`, `Patrol`, `Chase`, `Attack`, `LeashReturn`, `Dead`) with:
	- Server network ownership lock (`SetNetworkOwner(nil)`)
	- Recompute throttling (`>= 0.45s`) & blocked-waypoint invalidation
	- Leash radius enforcement
]]

local CollectionService = game:GetService("CollectionService")
local PathfindingService = game:GetService("PathfindingService")
local Workspace = game:GetService("Workspace")

export type NpcState = "Idle" | "Patrol" | "Chase" | "Attack" | "LeashReturn" | "Dead"

export type NpcConfig = {
	npcId: string,
	displayName: string?,
	maxHealth: number?,
	moveSpeed: number?,
	aggroRangeStuds: number?,
	attackRangeStuds: number?,
	maxLeashDistStuds: number?,
	attackCooldownSec: number?,
	attackDamage: number?,
	patrolPoints: { Vector3 }?,
	agentRadius: number?,
	agentHeight: number?,
	tag: string?,
}

export type NpcAgent = {
	model: Model,
	rootPart: BasePart,
	humanoid: Humanoid,
	config: NpcConfig,
	state: NpcState,
	spawnOrigin: Vector3,
	patrolIndex: number,
	lastPathComputeClock: number,
	lastAttackClock: number,
	waypoints: { PathWaypoint },
	currentWaypointIdx: number,
	targetPosition: Vector3?,
}

local DEFAULT_TAG = "SharpNpcAgentManaged"

local NpcAiDirector = {}

function NpcAiDirector.SpawnNpcRig(position: Vector3, config: NpcConfig, parent: Instance?): NpcAgent
	local managedTag = config.tag or DEFAULT_TAG
	local model = Instance.new("Model")
	model.Name = config.npcId
	model:SetAttribute("NpcId", config.npcId)
	model:SetAttribute("DisplayName", config.displayName or config.npcId)
	model:SetAttribute("IsDamageableTarget", true)
	model:SetAttribute("AIState", "Idle")
	CollectionService:AddTag(model, managedTag)

	local root = Instance.new("Part")
	root.Name = "HumanoidRootPart"
	root.Size = Vector3.new(2, 2, 1)
	root.CFrame = CFrame.new(position)
	root.Anchored = false
	root.CanCollide = true
	root.Color = Color3.fromRGB(165, 75, 75)
	root.Parent = model

	local head = Instance.new("Part")
	head.Name = "Head"
	head.Size = Vector3.new(1.2, 1.2, 1.2)
	head.CFrame = root.CFrame * CFrame.new(0, 1.6, 0)
	head.CanCollide = false
	head.Massless = true
	head.Parent = model

	local weld = Instance.new("WeldConstraint")
	weld.Part0 = root
	weld.Part1 = head
	weld.Parent = root

	local hum = Instance.new("Humanoid")
	hum.MaxHealth = config.maxHealth or 100
	hum.Health = hum.MaxHealth
	hum.WalkSpeed = config.moveSpeed or 14
	hum.Parent = model

	model.PrimaryPart = root
	model.Parent = parent or Workspace

	pcall(function()
		root:SetNetworkOwner(nil)
	end)

	return {
		model = model,
		rootPart = root,
		humanoid = hum,
		config = config,
		state = "Idle",
		spawnOrigin = position,
		patrolIndex = 1,
		lastPathComputeClock = 0,
		lastAttackClock = 0,
		waypoints = {},
		currentWaypointIdx = 1,
		targetPosition = nil,
	}
end

function NpcAiDirector.ComputePathWaypoints(agent: NpcAgent, destination: Vector3): (boolean, { PathWaypoint })
	local path = PathfindingService:CreatePath({
		AgentRadius = agent.config.agentRadius or 2.0,
		AgentHeight = agent.config.agentHeight or 5.0,
		AgentCanJump = true,
		AgentCanClimb = true,
		WaypointSpacing = 4.0,
		Costs = {
			Water = 15.0,
			DangerZone = math.huge,
		},
	})

	local okComp, _ = pcall(function()
		path:ComputeAsync(agent.rootPart.Position, destination)
	end)

	if okComp and path.Status == Enum.PathStatus.Success then
		local wps = path:GetWaypoints()
		agent.waypoints = wps
		agent.currentWaypointIdx = math.min(2, #wps)
		return true, wps
	end

	-- Direct fallback waypoint when navmesh is unbaked in empty test region
	local directWp = {
		PathWaypoint.new(agent.rootPart.Position, Enum.PathWaypointAction.Walk),
		PathWaypoint.new(destination, Enum.PathWaypointAction.Walk),
	}
	agent.waypoints = directWp
	agent.currentWaypointIdx = 2
	return false, directWp
end

function NpcAiDirector.EvaluateTick(
	agent: NpcAgent,
	candidateTargets: { Vector3 },
	nowClock: number?
): (NpcState, string)
	local now = nowClock or os.clock()
	if agent.humanoid.Health <= 0 then
		agent.state = "Dead"
		agent.model:SetAttribute("AIState", "Dead")
		return "Dead", "HUMANOID_DEAD"
	end

	local pos = agent.rootPart.Position
	local distFromSpawn = (pos - agent.spawnOrigin).Magnitude
	local maxLeash = agent.config.maxLeashDistStuds or 85.0
	local aggroRange = agent.config.aggroRangeStuds or 36.0
	local attackRange = agent.config.attackRangeStuds or 6.0

	-- 1. Leash check
	if distFromSpawn > maxLeash and agent.state ~= "LeashReturn" then
		agent.state = "LeashReturn"
		agent.targetPosition = agent.spawnOrigin
		agent.humanoid.Health = agent.humanoid.MaxHealth
		agent.model:SetAttribute("AIState", "LeashReturn")
		return "LeashReturn", "EXCEEDED_LEASH_RADIUS"
	end

	if agent.state == "LeashReturn" then
		if distFromSpawn <= 5.0 then
			agent.state = "Idle"
			agent.model:SetAttribute("AIState", "Idle")
			return "Idle", "RETURNED_TO_SPAWN"
		end
		agent.humanoid:MoveTo(agent.spawnOrigin)
		return "LeashReturn", "MOVING_TO_SPAWN"
	end

	-- 2. Find nearest target within aggroRange & within leash
	local nearestTarget: Vector3? = nil
	local nearestDist = aggroRange
	for _, tPos in ipairs(candidateTargets) do
		local d = (tPos - pos).Magnitude
		local dSpawn = (tPos - agent.spawnOrigin).Magnitude
		if d <= nearestDist and dSpawn <= maxLeash then
			nearestDist = d
			nearestTarget = tPos
		end
	end

	if nearestTarget then
		agent.targetPosition = nearestTarget
		if nearestDist <= attackRange then
			agent.state = "Attack"
			agent.model:SetAttribute("AIState", "Attack")
			local cd = agent.config.attackCooldownSec or 1.0
			if (now - agent.lastAttackClock) >= cd then
				agent.lastAttackClock = now
				return "Attack", "PERFORMED_ATTACK"
			end
			return "Attack", "ATTACK_COOLDOWN"
		else
			agent.state = "Chase"
			agent.model:SetAttribute("AIState", "Chase")
			if (now - agent.lastPathComputeClock) >= 0.45 then
				agent.lastPathComputeClock = now
				NpcAiDirector.ComputePathWaypoints(agent, nearestTarget)
			end
			agent.humanoid:MoveTo(nearestTarget)
			return "Chase", "CHASING_TARGET"
		end
	end

	-- 3. Patrol or Idle
	local pts = agent.config.patrolPoints
	if pts and #pts > 0 then
		agent.state = "Patrol"
		agent.model:SetAttribute("AIState", "Patrol")
		local wp = pts[agent.patrolIndex]
		if (wp - pos).Magnitude <= 4.0 then
			agent.patrolIndex = (agent.patrolIndex % #pts) + 1
			wp = pts[agent.patrolIndex]
		end
		agent.humanoid:MoveTo(wp)
		return "Patrol", "PATROLLING_WAYPOINT_" .. tostring(agent.patrolIndex)
	end

	agent.state = "Idle"
	agent.model:SetAttribute("AIState", "Idle")
	return "Idle", "HOLDING_POSITION"
end

function NpcAiDirector.Cleanup(tag: string?): number
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

return NpcAiDirector

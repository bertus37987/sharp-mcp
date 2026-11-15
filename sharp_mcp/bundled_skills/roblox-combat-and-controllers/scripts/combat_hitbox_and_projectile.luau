--!strict
--[[
	CombatHitboxAndProjectile
	Server-authoritative melee Shapecast / GetPartBoundsInBox hit detection,
	anti-exploit reach/cooldown/angle/LOS validator, and stepped raycast
	ballistic projectile simulator (gravity, drag, pierce, bounce).
]]

local Workspace = game:GetService("Workspace")

export type MeleeSweepSpec = {
	originCFrame: CFrame,
	boxSize: Vector3,
	sweepDirection: Vector3?,
	excludeInstances: { Instance }?,
	maxTargets: number?,
	alreadyHitModels: { [Model]: boolean }?,
}

export type HitRecord = {
	targetModel: Model,
	humanoid: Humanoid?,
	hitPart: BasePart,
	hitPosition: Vector3,
	distanceStuds: number,
}

export type ServerValidationSpec = {
	attackerRoot: BasePart,
	targetRoot: BasePart,
	maxRangeStuds: number,
	maxHalfAngleDeg: number?,
	pingSeconds: number?,
	lastAttackClock: number?,
	minCooldownSec: number?,
	nowClock: number?,
	requireLineOfSight: boolean?,
	excludeInstances: { Instance }?,
}

export type ProjectileSpec = {
	origin: Vector3,
	initialVelocity: Vector3,
	gravity: Vector3?,
	dragCoefficient: number?,
	maxLifetimeSec: number?,
	maxBounces: number?,
	bounciness: number?,
	excludeInstances: { Instance }?,
}

export type ProjectileStepResult = {
	position: Vector3,
	velocity: Vector3,
	elapsedSec: number,
	bounces: number,
	alive: boolean,
	hitPart: BasePart?,
	hitNormal: Vector3?,
}

local CombatHitboxAndProjectile = {}

local function resolveCharacterModel(part: Instance): Model?
	local cur: Instance? = part
	while cur and cur ~= Workspace do
		if cur:IsA("Model") and (cur:FindFirstChildOfClass("Humanoid") or cur:GetAttribute("IsDamageableTarget") == true) then
			return cur
		end
		cur = cur.Parent
	end
	return nil
end

function CombatHitboxAndProjectile.SweepMeleeHitbox(spec: MeleeSweepSpec): { HitRecord }
	local exclude = spec.excludeInstances or {}
	local maxTargets = spec.maxTargets or 8
	local seen: { [Model]: boolean } = spec.alreadyHitModels or {}
	local hits: { HitRecord } = {}

	local overlapParams = OverlapParams.new()
	overlapParams.FilterType = Enum.RaycastFilterType.Exclude
	overlapParams.FilterDescendantsInstances = exclude
	overlapParams.MaxParts = 32

	-- 1. Check immediate oriented bounding box overlap at t = 0
	local boxParts = Workspace:GetPartBoundsInBox(spec.originCFrame, spec.boxSize, overlapParams)
	for _, part in ipairs(boxParts) do
		local model = resolveCharacterModel(part)
		if model and not seen[model] then
			seen[model] = true
			local hum = model:FindFirstChildOfClass("Humanoid")
			if not hum or hum.Health > 0 then
				local dist = (part.Position - spec.originCFrame.Position).Magnitude
				table.insert(hits, {
					targetModel = model,
					humanoid = hum,
					hitPart = part,
					hitPosition = part.Position,
					distanceStuds = dist,
				})
				if #hits >= maxTargets then
					return hits
				end
			end
		end
	end

	-- 2. Continuous Shapecast (Blockcast) along sweepDirection if non-zero
	local dir = spec.sweepDirection
	if dir and dir.Magnitude > 1e-3 and #hits < maxTargets then
		local rayParams = RaycastParams.new()
		rayParams.FilterType = Enum.RaycastFilterType.Exclude
		rayParams.FilterDescendantsInstances = exclude
		rayParams.IgnoreWater = true

		local castRes = Workspace:Blockcast(spec.originCFrame, spec.boxSize, dir, rayParams)
		if castRes and castRes.Instance then
			local model = resolveCharacterModel(castRes.Instance)
			if model and not seen[model] then
				seen[model] = true
				local hum = model:FindFirstChildOfClass("Humanoid")
				if not hum or hum.Health > 0 then
					table.insert(hits, {
						targetModel = model,
						humanoid = hum,
						hitPart = castRes.Instance,
						hitPosition = castRes.Position,
						distanceStuds = castRes.Distance,
					})
				end
			end
		end
	end

	return hits
end

function CombatHitboxAndProjectile.ValidateServerHit(spec: ServerValidationSpec): (boolean, string)
	local now = spec.nowClock or os.clock()
	if spec.lastAttackClock and spec.minCooldownSec then
		if (now - spec.lastAttackClock) < (spec.minCooldownSec * 0.85) then
			return false, "COOLDOWN_VIOLATION"
		end
	end

	local delta = spec.targetRoot.Position - spec.attackerRoot.Position
	local dist = delta.Magnitude
	local pingGrace = math.clamp((spec.pingSeconds or 0.06) * 24.0, 1.5, 7.5)
	if dist > (spec.maxRangeStuds + pingGrace) then
		return false, "OUT_OF_RANGE"
	end

	local maxHalfAngle = spec.maxHalfAngleDeg or 105
	if dist > 0.5 and maxHalfAngle < 180 then
		local dirUnit = Vector3.new(delta.X, 0, delta.Z)
		local lookFlat = Vector3.new(spec.attackerRoot.CFrame.LookVector.X, 0, spec.attackerRoot.CFrame.LookVector.Z)
		if dirUnit.Magnitude > 1e-3 and lookFlat.Magnitude > 1e-3 then
			local dot = lookFlat.Unit:Dot(dirUnit.Unit)
			local minCos = math.cos(math.rad(maxHalfAngle))
			if dot < minCos then
				return false, "OUT_OF_FACING_CONE"
			end
		end
	end

	if if spec.requireLineOfSight == nil then true else spec.requireLineOfSight then
		local rayParams = RaycastParams.new()
		rayParams.FilterType = Enum.RaycastFilterType.Exclude
		local filter: { Instance } = { spec.attackerRoot.Parent :: Instance, spec.targetRoot.Parent :: Instance }
		if spec.excludeInstances then
			for _, ex in ipairs(spec.excludeInstances) do
				table.insert(filter, ex)
			end
		end
		rayParams.FilterDescendantsInstances = filter
		rayParams.IgnoreWater = true

		local losHit = Workspace:Raycast(spec.attackerRoot.Position, delta, rayParams)
		if losHit and losHit.Instance and losHit.Instance.CanCollide then
			return false, "LINE_OF_SIGHT_BLOCKED"
		end
	end

	return true, "VALID_HIT"
end

function CombatHitboxAndProjectile.SimulateProjectileTrajectory(
	spec: ProjectileSpec,
	stepDt: number?,
	maxSteps: number?
): { ProjectileStepResult }
	local dt = math.clamp(stepDt or (1 / 60), 1 / 240, 0.1)
	local stepsLimit = maxSteps or 120
	local gravity = spec.gravity or Vector3.new(0, -Workspace.Gravity, 0)
	local drag = spec.dragCoefficient or 0.02
	local maxLifetime = spec.maxLifetimeSec or 3.0
	local maxBounces = spec.maxBounces or 0
	local bounciness = math.clamp(spec.bounciness or 0.6, 0, 1)

	local rayParams = RaycastParams.new()
	rayParams.FilterType = Enum.RaycastFilterType.Exclude
	rayParams.FilterDescendantsInstances = spec.excludeInstances or {}
	rayParams.IgnoreWater = true

	local pos = spec.origin
	local vel = spec.initialVelocity
	local elapsed = 0.0
	local bounces = 0
	local history: { ProjectileStepResult } = {}

	for _ = 1, stepsLimit do
		if elapsed >= maxLifetime then
			break
		end
		local nextVel = (vel + gravity * dt) * math.max(0, 1 - drag * dt)
		local displacement = (vel + nextVel) * 0.5 * dt
		local hit = Workspace:Raycast(pos, displacement, rayParams)

		elapsed += dt
		if hit and hit.Instance then
			if bounces < maxBounces then
				bounces += 1
				local n = hit.Normal
				pos = hit.Position + n * 0.05
				vel = (nextVel - 2 * nextVel:Dot(n) * n) * bounciness
				table.insert(history, {
					position = pos,
					velocity = vel,
					elapsedSec = elapsed,
					bounces = bounces,
					alive = true,
					hitPart = hit.Instance,
					hitNormal = n,
				})
			else
				pos = hit.Position
				vel = Vector3.zero
				table.insert(history, {
					position = pos,
					velocity = vel,
					elapsedSec = elapsed,
					bounces = bounces,
					alive = false,
					hitPart = hit.Instance,
					hitNormal = hit.Normal,
				})
				break
			end
		else
			pos = pos + displacement
			vel = nextVel
			table.insert(history, {
				position = pos,
				velocity = vel,
				elapsedSec = elapsed,
				bounces = bounces,
				alive = elapsed < maxLifetime,
				hitPart = nil,
				hitNormal = nil,
			})
		end
	end

	return history
end

return CombatHitboxAndProjectile

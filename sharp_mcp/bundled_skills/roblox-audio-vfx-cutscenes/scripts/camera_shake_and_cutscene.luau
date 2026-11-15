--!strict
--[[
	CameraShakeAndCutscene
	Provides:
	1. Perlin-noise trauma camera shake (`shakeIntensity = trauma^2`) safe for
	   `Enum.RenderPriority.Camera.Value + 1`.
	2. Catmull-Rom CFrame spline evaluator for cinematic camera paths with
	   smooth orientation slerp and non-destructive camera state restoration.
]]

export type TraumaShaker = {
	trauma: number,
	decayPerSec: number,
	maxOffsetStuds: Vector3,
	maxRotDeg: Vector3,
	frequency: number,
	seed: number,
	elapsed: number,
}

export type CutsceneKeyframe = {
	cframe: CFrame,
	fov: number?,
	focusDistance: number?,
}

local CameraShakeAndCutscene = {}

function CameraShakeAndCutscene.CreateTraumaShaker(
	decayPerSec: number?,
	maxOffsetStuds: Vector3?,
	maxRotDeg: Vector3?,
	frequency: number?,
	seed: number?
): TraumaShaker
	return {
		trauma = 0.0,
		decayPerSec = decayPerSec or 1.35,
		maxOffsetStuds = maxOffsetStuds or Vector3.new(1.2, 1.2, 0.4),
		maxRotDeg = maxRotDeg or Vector3.new(4.5, 4.5, 6.0),
		frequency = frequency or 22.0,
		seed = seed or 1337,
		elapsed = 0.0,
	}
end

function CameraShakeAndCutscene.AddTrauma(shaker: TraumaShaker, amount: number): number
	shaker.trauma = math.clamp(shaker.trauma + amount, 0.0, 1.0)
	return shaker.trauma
end

function CameraShakeAndCutscene.StepTraumaShake(shaker: TraumaShaker, dt: number): CFrame
	if shaker.trauma <= 1e-4 then
		shaker.trauma = 0.0
		return CFrame.identity
	end
	shaker.elapsed += dt
	local t = shaker.elapsed * shaker.frequency
	local s = shaker.seed
	local shake = shaker.trauma * shaker.trauma -- Quadratic trauma falloff feels natural

	local nx = math.noise(t, s + 1.1, 0.0)
	local ny = math.noise(t, s + 2.3, 0.0)
	local nz = math.noise(t, s + 3.7, 0.0)
	local rx = math.noise(t, s + 5.1, 1.0)
	local ry = math.noise(t, s + 7.3, 1.0)
	local rz = math.noise(t, s + 9.7, 1.0)

	local offset = Vector3.new(
		nx * shaker.maxOffsetStuds.X * shake,
		ny * shaker.maxOffsetStuds.Y * shake,
		nz * shaker.maxOffsetStuds.Z * shake
	)
	local rot = CFrame.Angles(
		math.rad(rx * shaker.maxRotDeg.X * shake),
		math.rad(ry * shaker.maxRotDeg.Y * shake),
		math.rad(rz * shaker.maxRotDeg.Z * shake)
	)

	shaker.trauma = math.max(0.0, shaker.trauma - shaker.decayPerSec * dt)
	return CFrame.new(offset) * rot
end

local function catmullRomVector3(p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3, t: number): Vector3
	local t2 = t * t
	local t3 = t2 * t
	return 0.5 * (
		(2 * p1)
		+ (-p0 + p2) * t
		+ (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
		+ (-p0 + 3 * p1 - 3 * p2 + p3) * t3
	)
end

function CameraShakeAndCutscene.EvaluateSpline(
	waypoints: { CutsceneKeyframe },
	alpha: number
): (CFrame, number, number)
	local n = #waypoints
	assert(n >= 2, "Cutscene spline requires at least 2 waypoints.")

	local clamped = math.clamp(alpha, 0.0, 1.0)
	local scaled = clamped * (n - 1)
	local segIdx = math.clamp(math.floor(scaled) + 1, 1, n - 1)
	local localT = scaled - (segIdx - 1)

	local w0 = waypoints[math.max(1, segIdx - 1)]
	local w1 = waypoints[segIdx]
	local w2 = waypoints[math.min(n, segIdx + 1)]
	local w3 = waypoints[math.min(n, segIdx + 2)]

	local pos = catmullRomVector3(w0.cframe.Position, w1.cframe.Position, w2.cframe.Position, w3.cframe.Position, localT)
	local rotCf = (w1.cframe - w1.cframe.Position):Lerp(w2.cframe - w2.cframe.Position, localT)
	local fov1 = w1.fov or 70
	local fov2 = w2.fov or 70
	local fov = fov1 + (fov2 - fov1) * localT

	local fd1 = w1.focusDistance or 15
	local fd2 = w2.focusDistance or 15
	local focusDist = fd1 + (fd2 - fd1) * localT

	return CFrame.new(pos) * rotCf, fov, focusDist
end

return CameraShakeAndCutscene

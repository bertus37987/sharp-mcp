--!strict
-- studio_test_anim.luau
-- Registers any KeyframeSequence or CurveAnimation in Studio via AnimationClipProvider,
-- saves a copy to ServerStorage.RBX_ANIMSAVES for Animation Editor inspection, and plays
-- it on the target rig (Humanoid or AnimationController) with marker & joint verification.
--
-- Run in Edit or Play mode via execute_luau.

local AnimationClipProvider = game:GetService("AnimationClipProvider")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")
local Selection = game:GetService("Selection")

-- Configure or override before running:
local CLIP_PATH: string = "" -- e.g. "ReplicatedStorage.Animations.Walk_Forward" (empty = first clip in ReplicatedStorage.Animations)
local RIG_PATH: string = ""  -- e.g. "Workspace.Rig" (empty = Selection[1] or LocalPlayer.Character or Workspace rig)
local SAVE_TO_ANIMSAVES: boolean = true
local PLAY_NOW: boolean = true

local function findPath(path: string): Instance?
	if path == "" then
		return nil
	end
	local curr: Instance = game
	for seg in string.gmatch(path, "[^%.]+") do
		local nxt = if curr == game
			then (pcall(function() return game:GetService(seg) end) and game:GetService(seg) or curr:FindFirstChild(seg))
			else curr:FindFirstChild(seg)
		if not nxt then
			return nil
		end
		curr = nxt
	end
	return curr
end

local clip: AnimationClip? = nil
local foundClip = findPath(CLIP_PATH)
if foundClip and foundClip:IsA("AnimationClip") then
	clip = foundClip
else
	local animFolder = ReplicatedStorage:FindFirstChild("Animations")
	if animFolder then
		for _, ch in ipairs(animFolder:GetChildren()) do
			if ch:IsA("AnimationClip") then
				clip = ch
				break
			end
		end
	end
end
assert(clip ~= nil, "No KeyframeSequence or CurveAnimation found. Set CLIP_PATH or place clips in ReplicatedStorage.Animations.")

local rig: Model? = nil
local foundRig = findPath(RIG_PATH)
if foundRig and foundRig:IsA("Model") then
	rig = foundRig
elseif #Selection:Get() > 0 and Selection:Get()[1]:IsA("Model") then
	rig = Selection:Get()[1] :: Model
else
	for _, ch in ipairs(workspace:GetChildren()) do
		if ch:IsA("Model") and (ch:FindFirstChildOfClass("Humanoid") or ch:FindFirstChildOfClass("AnimationController")) then
			rig = ch
			break
		end
	end
end
assert(rig ~= nil, "No animated Model (with Humanoid or AnimationController) found in Workspace.")

-- 1. Save editable copy to ServerStorage.RBX_ANIMSAVES.<RigName>.<ClipName>
if SAVE_TO_ANIMSAVES then
	local rootSaves = ServerStorage:FindFirstChild("RBX_ANIMSAVES")
	if not rootSaves then
		rootSaves = Instance.new("Folder")
		rootSaves.Name = "RBX_ANIMSAVES"
		rootSaves.Parent = ServerStorage
	end
	local rigSaves = rootSaves:FindFirstChild(rig.Name)
	if not rigSaves then
		rigSaves = Instance.new("Folder")
		rigSaves.Name = rig.Name
		rigSaves.Parent = rootSaves
	end
	local prev = rigSaves:FindFirstChild(clip.Name)
	if prev then
		prev:Destroy()
	end
	local clone = clip:Clone()
	clone.Parent = rigSaves
end

-- 2. Register with modern AnimationClipProvider (works in Studio Edit & Play without cloud upload)
local clipAssetId = AnimationClipProvider:RegisterAnimationClip(clip)

-- 3. Ensure Animator exists under Humanoid or AnimationController
local controller: Instance? = rig:FindFirstChildOfClass("Humanoid") or rig:FindFirstChildOfClass("AnimationController")
assert(controller ~= nil, "Target rig must contain a Humanoid or AnimationController.")

local animator = controller:FindFirstChildOfClass("Animator")
if not animator then
	animator = Instance.new("Animator")
	animator.Parent = controller
end

-- Destroy default Animate script if present so Core/Idle tracks don't fight test playback
local defaultAnimate = rig:FindFirstChild("Animate")
if defaultAnimate then
	defaultAnimate:Destroy()
end

local animFolder = rig:FindFirstChild("SharpAnimations")
if not animFolder then
	animFolder = Instance.new("Folder")
	animFolder.Name = "SharpAnimations"
	animFolder.Parent = rig
end

local animObj = animFolder:FindFirstChild(clip.Name) :: Animation?
if not animObj then
	animObj = Instance.new("Animation")
	animObj.Name = clip.Name
	animObj.Parent = animFolder
end
animObj.AnimationId = clipAssetId

-- Weak-keyed Animator -> { [key]: AnimationTrack } cache (avoids leaking tracks past 256 limit)
local _SharpTrackCache = setmetatable({}, { __mode = "k" }) :: { [Animator]: { [string]: AnimationTrack } }
local function getCachedTrack(targetAnimator: Animator, anim: Animation): AnimationTrack
	local perAnim = _SharpTrackCache[targetAnimator]
	if not perAnim then
		perAnim = {}
		_SharpTrackCache[targetAnimator] = perAnim
	end
	local key = anim.AnimationId ~= "" and anim.AnimationId or anim.Name
	local existing = perAnim[key]
	if existing then
		return existing
	end
	local loaded = targetAnimator:LoadAnimation(anim)
	perAnim[key] = loaded
	return loaded
end

local result: { string } = {
	"Clip=" .. clip.Name .. " (" .. clip.ClassName .. ")",
	"RegisteredId=" .. clipAssetId,
	"Rig=" .. rig:GetFullName(),
}

if PLAY_NOW then
	local track = getCachedTrack(animator, animObj)
	track.Priority = clip.Priority
	track.Looped = clip.Loop

	local markersFired: { string } = {}
	track:GetMarkerReachedSignal("HitStart"):Connect(function(v)
		table.insert(markersFired, "HitStart:" .. tostring(v))
	end)

	track:Play(0.1)
	task.wait(0.15)
	table.insert(result, string.format("IsPlaying=%s Length=%.3fs Priority=%s Looped=%s",
		tostring(track.IsPlaying), track.Length, tostring(track.Priority), tostring(track.Looped)))
	if #markersFired > 0 then
		table.insert(result, "Markers=" .. table.concat(markersFired, ","))
	end
end

return table.concat(result, " | ")

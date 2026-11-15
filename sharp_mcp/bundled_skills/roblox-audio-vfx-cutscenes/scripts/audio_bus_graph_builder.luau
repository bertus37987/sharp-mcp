--!strict
--[[
	AudioBusGraphBuilder
	Builds Roblox's modern node-based Audio Wiring topology under SoundService
	(AudioPlayer -> Wire -> AudioFader / AudioCompressor / AudioReverb ->
	AudioEmitter / AudioListener -> AudioDeviceOutput) and provides built-in
	rbxasset://sounds/* playback helpers.
]]

local CollectionService = game:GetService("CollectionService")
local SoundService = game:GetService("SoundService")
local Workspace = game:GetService("Workspace")

export type BusName = "Master" | "BGM" | "SFX" | "UI" | "Ambient"

export type AudioGraphConfig = {
	masterVolume: number?,
	bgmVolume: number?,
	sfxVolume: number?,
	uiVolume: number?,
	ambientVolume: number?,
	enableSidechainDucking: boolean?,
	tag: string?,
}

export type AudioGraphBundle = {
	container: Folder,
	deviceOutput: Instance,
	masterFader: Instance,
	buses: { [BusName]: Instance },
	wiresCreated: number,
	usingModernAudioApi: boolean,
}

local DEFAULT_TAG = "SharpAudioGraphManaged"

local BUILTIN_SOUNDS: { [string]: { assetId: string, bus: BusName, volume: number, looped: boolean } } = {
	UI_ButtonClick = { assetId = "rbxasset://sounds/button.wav", bus = "UI", volume = 0.65, looped = false },
	UI_QuestPing = { assetId = "rbxasset://sounds/electronicpingshort.wav", bus = "UI", volume = 0.75, looped = false },
	Combat_SwordSlash = { assetId = "rbxasset://sounds/swordslash.wav", bus = "SFX", volume = 0.85, looped = false },
	Combat_SwordLunge = { assetId = "rbxasset://sounds/lunge.wav", bus = "SFX", volume = 0.90, looped = false },
	Movement_Footstep = { assetId = "rbxasset://sounds/action_footsteps_plastic.mp3", bus = "SFX", volume = 0.50, looped = true },
}

local AudioBusGraphBuilder = {
	BuiltInSounds = BUILTIN_SOUNDS,
}

local function connectWire(parent: Instance, name: string, source: Instance, target: Instance, targetPin: string?, tag: string): Instance?
	local ok, wireOrErr = pcall(function()
		local w = Instance.new("Wire")
		w.Name = name
		w.SourceInstance = source
		w.TargetInstance = target
		if targetPin and #targetPin > 0 then
			w.TargetName = targetPin
		end
		CollectionService:AddTag(w, tag)
		w.Parent = parent
		return w
	end)
	if ok then
		return wireOrErr :: Instance
	end
	return nil
end

function AudioBusGraphBuilder.BuildMasterGraph(config: AudioGraphConfig?): AudioGraphBundle
	local cfg: AudioGraphConfig = config or {}
	local tag = cfg.tag or DEFAULT_TAG

	local existing = SoundService:FindFirstChild("SharpAudioBuses")
	if existing then
		existing:Destroy()
	end

	local container = Instance.new("Folder")
	container.Name = "SharpAudioBuses"
	CollectionService:AddTag(container, tag)
	container.Parent = SoundService

	local wiresCount = 0
	local okModern, bundleOrErr = pcall(function()
		local deviceOut = Instance.new("AudioDeviceOutput")
		deviceOut.Name = "MainDeviceOutput"
		CollectionService:AddTag(deviceOut, tag)
		deviceOut.Parent = container

		local masterFader = Instance.new("AudioFader")
		masterFader.Name = "MasterFader"
		masterFader.Volume = cfg.masterVolume or 1.0
		CollectionService:AddTag(masterFader, tag)
		masterFader.Parent = container

		if connectWire(container, "Wire_Master_To_Output", masterFader, deviceOut, nil, tag) then
			wiresCount += 1
		end

		local bgmFader = Instance.new("AudioFader")
		bgmFader.Name = "BGM_Bus"
		bgmFader.Volume = cfg.bgmVolume or 0.70
		CollectionService:AddTag(bgmFader, tag)
		bgmFader.Parent = container

		local bgmComp = Instance.new("AudioCompressor")
		bgmComp.Name = "BGM_DuckingCompressor"
		bgmComp.Threshold = -18
		bgmComp.Ratio = 6
		bgmComp.Attack = 0.03
		bgmComp.Release = 0.25
		CollectionService:AddTag(bgmComp, tag)
		bgmComp.Parent = container

		if connectWire(container, "Wire_BGM_To_Comp", bgmFader, bgmComp, nil, tag) then
			wiresCount += 1
		end
		if connectWire(container, "Wire_BGMComp_To_Master", bgmComp, masterFader, nil, tag) then
			wiresCount += 1
		end

		local sfxFader = Instance.new("AudioFader")
		sfxFader.Name = "SFX_Bus"
		sfxFader.Volume = cfg.sfxVolume or 0.90
		CollectionService:AddTag(sfxFader, tag)
		sfxFader.Parent = container

		local sfxReverb = Instance.new("AudioReverb")
		sfxReverb.Name = "SFX_Reverb"
		sfxReverb.WetLevel = -12
		sfxReverb.DryLevel = 0
		CollectionService:AddTag(sfxReverb, tag)
		sfxReverb.Parent = container

		if connectWire(container, "Wire_SFX_To_Reverb", sfxFader, sfxReverb, nil, tag) then
			wiresCount += 1
		end
		if connectWire(container, "Wire_SFXReverb_To_Master", sfxReverb, masterFader, nil, tag) then
			wiresCount += 1
		end

		if if cfg.enableSidechainDucking == nil then true else cfg.enableSidechainDucking then
			if connectWire(container, "Wire_SFX_Sidechain_BGM", sfxFader, bgmComp, "Sidechain", tag) then
				wiresCount += 1
			end
		end

		local uiFader = Instance.new("AudioFader")
		uiFader.Name = "UI_Bus"
		uiFader.Volume = cfg.uiVolume or 0.85
		CollectionService:AddTag(uiFader, tag)
		uiFader.Parent = container
		if connectWire(container, "Wire_UI_To_Master", uiFader, masterFader, nil, tag) then
			wiresCount += 1
		end

		local ambFader = Instance.new("AudioFader")
		ambFader.Name = "Ambient_Bus"
		ambFader.Volume = cfg.ambientVolume or 0.65
		CollectionService:AddTag(ambFader, tag)
		ambFader.Parent = container
		if connectWire(container, "Wire_Ambient_To_Master", ambFader, masterFader, nil, tag) then
			wiresCount += 1
		end

		-- Attach a default 3D AudioListener to CurrentCamera if present
		local cam = Workspace.CurrentCamera
		if cam then
			local oldListener = cam:FindFirstChild("SharpCameraAudioListener")
			if oldListener then
				oldListener:Destroy()
			end
			local listener = Instance.new("AudioListener")
			listener.Name = "SharpCameraAudioListener"
			listener.AudioInteractionGroup = "SharpWorldAudio"
			CollectionService:AddTag(listener, tag)
			listener.Parent = cam
			if connectWire(container, "Wire_Listener_To_SFX", listener, sfxFader, nil, tag) then
				wiresCount += 1
			end
		end

		return {
			container = container,
			deviceOutput = deviceOut,
			masterFader = masterFader,
			buses = {
				Master = masterFader,
				BGM = bgmFader,
				SFX = sfxFader,
				UI = uiFader,
				Ambient = ambFader,
			},
			wiresCreated = wiresCount,
			usingModernAudioApi = true,
		}
	end)

	if okModern and bundleOrErr then
		return bundleOrErr :: AudioGraphBundle
	end

	-- Fallback SoundGroup hierarchy if AudioPlayer/Wire FFlags are disabled
	local masterSg = Instance.new("SoundGroup")
	masterSg.Name = "Master"
	masterSg.Volume = cfg.masterVolume or 1.0
	CollectionService:AddTag(masterSg, tag)
	masterSg.Parent = container

	local busesFallback: { [BusName]: Instance } = { Master = masterSg }
	for _, bName in ipairs({ "BGM", "SFX", "UI", "Ambient" } :: { BusName }) do
		local sg = Instance.new("SoundGroup")
		sg.Name = bName .. "_Bus"
		sg.Volume = 0.8
		CollectionService:AddTag(sg, tag)
		sg.Parent = masterSg
		busesFallback[bName] = sg
	end

	return {
		container = container,
		deviceOutput = masterSg,
		masterFader = masterSg,
		buses = busesFallback,
		wiresCreated = 0,
		usingModernAudioApi = false,
	}
end

function AudioBusGraphBuilder.SpawnAudioPlayer2D(
	bundle: AudioGraphBundle,
	soundKeyOrAssetId: string,
	busName: BusName?,
	autoPlay: boolean?,
	tag: string?
): Instance
	local managedTag = tag or DEFAULT_TAG
	local preset = BUILTIN_SOUNDS[soundKeyOrAssetId]
	local assetId = if preset then preset.assetId else soundKeyOrAssetId
	local targetBusName: BusName = busName or (if preset then preset.bus else "SFX")
	local volume = if preset then preset.volume else 0.8
	local looped = if preset then preset.looped else false
	local targetBus = bundle.buses[targetBusName] or bundle.masterFader

	if bundle.usingModernAudioApi then
		local player = Instance.new("AudioPlayer")
		player.Name = "AudioPlayer_" .. soundKeyOrAssetId
		player.Asset = assetId
		player.Volume = volume
		player.Looping = looped
		CollectionService:AddTag(player, managedTag)
		player.Parent = bundle.container
		connectWire(bundle.container, "Wire_" .. player.Name, player, targetBus, nil, managedTag)
		if autoPlay then
			pcall(function()
				player:Play()
			end)
		end
		return player
	else
		local snd = Instance.new("Sound")
		snd.Name = "Sound_" .. soundKeyOrAssetId
		snd.SoundId = assetId
		snd.Volume = volume
		snd.Looped = looped
		if targetBus:IsA("SoundGroup") then
			snd.SoundGroup = targetBus
		end
		CollectionService:AddTag(snd, managedTag)
		snd.Parent = bundle.container
		if autoPlay then
			pcall(function()
				snd:Play()
			end)
		end
		return snd
	end
end

function AudioBusGraphBuilder.Attach3DEmitter(
	hostPartOrAttachment: Instance,
	soundKeyOrAssetId: string,
	tag: string?
): (Instance, Instance?)
	local managedTag = tag or DEFAULT_TAG
	local preset = BUILTIN_SOUNDS[soundKeyOrAssetId]
	local assetId = if preset then preset.assetId else soundKeyOrAssetId
	local volume = if preset then preset.volume else 0.85

	local okModern, pOrErr, eOrErr = pcall(function()
		local player = Instance.new("AudioPlayer")
		player.Name = "SpatialPlayer_" .. soundKeyOrAssetId
		player.Asset = assetId
		player.Volume = volume
		CollectionService:AddTag(player, managedTag)
		player.Parent = hostPartOrAttachment

		local emitter = Instance.new("AudioEmitter")
		emitter.Name = "SpatialEmitter_" .. soundKeyOrAssetId
		emitter.AudioInteractionGroup = "SharpWorldAudio"
		CollectionService:AddTag(emitter, managedTag)
		emitter.Parent = hostPartOrAttachment

		connectWire(hostPartOrAttachment, "Wire_Player_To_Emitter", player, emitter, nil, managedTag)
		return player, emitter
	end)

	if okModern and pOrErr then
		return pOrErr :: Instance, eOrErr :: Instance?
	end

	local snd = Instance.new("Sound")
	snd.Name = "SpatialSound_" .. soundKeyOrAssetId
	snd.SoundId = assetId
	snd.Volume = volume
	snd.RollOffMaxDistance = 80
	snd.RollOffMinDistance = 8
	CollectionService:AddTag(snd, managedTag)
	snd.Parent = hostPartOrAttachment
	return snd, nil
end

function AudioBusGraphBuilder.Cleanup(tag: string?): number
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

return AudioBusGraphBuilder

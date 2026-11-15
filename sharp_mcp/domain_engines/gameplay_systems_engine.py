"""Gameplay, Audio/VFX, Economy/DataStore, NPC AI, World Assembly & Playtest Bot Engine.

Embeds all 15 `--!strict` Luau scripts across the 5 new gameplay & world production skills:
- `roblox-combat-and-controllers` (`07_roblox_combat_and_controllers`)
  - `controller_manager_rig.luau`
  - `weapon_tool_assembler.luau`
  - `combat_hitbox_and_projectile.luau`
- `roblox-audio-vfx-cutscenes` (`08_roblox_audio_vfx_cutscenes`)
  - `audio_bus_graph_builder.luau`
  - `vfx_preset_and_highlight_pool.luau`
  - `camera_shake_and_cutscene.luau`
- `roblox-data-economy-monetization` (`09_roblox_data_economy_monetization`)
  - `session_locked_datastore.luau`
  - `economy_inventory_quest_service.luau`
  - `monetization_receipt_handler.luau`
- `roblox-ai-and-gameplay-systems` (`10_roblox_ai_and_gameplay_systems`)
  - `npc_ai_director.luau`
  - `dialogue_and_interaction.luau`
  - `round_and_wave_director.luau`
- `roblox-world-assembly-and-optimization` (`11_roblox_world_assembly_and_optimization`)
  - `poisson_surface_scatter.luau`
  - `modular_socket_assembler.luau`
  - `scene_budget_optimizer.luau`
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional


SKILL_ARCHIVE_DIRS: Dict[str, str] = {
    "roblox-combat-and-controllers": "07_roblox_combat_and_controllers",
    "roblox-audio-vfx-cutscenes": "08_roblox_audio_vfx_cutscenes",
    "roblox-data-economy-monetization": "09_roblox_data_economy_monetization",
    "roblox-ai-and-gameplay-systems": "10_roblox_ai_and_gameplay_systems",
    "roblox-world-assembly-and-optimization": "11_roblox_world_assembly_and_optimization",
}


class GameplaySystemsEngine:
    def __init__(self, skills_dir: Path, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir

    def _read_skill_script(self, skill_name: str, script_name: str) -> str:
        primary = self.skills_dir / skill_name / "scripts" / script_name
        if primary.is_file():
            return primary.read_text(encoding="utf-8")
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / skill_name / "scripts" / script_name
        if bundled.is_file():
            return bundled.read_text(encoding="utf-8")
        if self.archive_dir:
            archive_folder = SKILL_ARCHIVE_DIRS[skill_name]
            fallback = self.archive_dir / archive_folder / "skill" / "scripts" / script_name
            return fallback.read_text(encoding="utf-8")
        raise FileNotFoundError(f"Skill script not found: {skill_name}/{script_name}")

    # ------------------------------------------------------------------
    # 1. Combat, Weapons & Physics Character Controllers
    # ------------------------------------------------------------------
    def compile_combat_and_controller_luau(
        self,
        action: str = "install",  # "install" | "smoke_test" | "cleanup"
        root_prefix: str = "",
        weapon_id: str = "IronBroadsword",
        base_damage: float = 28.0,
        range_studs: float = 8.5,
    ) -> str:
        ctrl_src = self._read_skill_script("roblox-combat-and-controllers", "controller_manager_rig.luau")
        weap_src = self._read_skill_script("roblox-combat-and-controllers", "weapon_tool_assembler.luau")
        hit_src = self._read_skill_script("roblox-combat-and-controllers", "combat_hitbox_and_projectile.luau")

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local ACTION = {json.dumps(action)}
local ROOT_PREFIX = {json.dumps(root_prefix)}
local WEAPON_ID = {json.dumps(weapon_id)}
local BASE_DAMAGE = {float(base_damage)}
local RANGE_STUDS = {float(range_studs)}

local ControllerManagerRig = (function()
{ctrl_src}
end)()

local WeaponToolAssembler = (function()
{weap_src}
end)()

local CombatHitboxAndProjectile = (function()
{hit_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpCombatController", "Sharp MCP: Combat & Controller (" .. ACTION .. ")")
local ok, resOrErr = xpcall(function()
	local repRoot = if ROOT_PREFIX ~= ""
		then ReplicatedStorage:FindFirstChild(ROOT_PREFIX) or ReplicatedStorage
		else ReplicatedStorage
	local sharedFolder = repRoot:FindFirstChild("Shared") or repRoot

	if ACTION == "cleanup" then
		local combatFolder = sharedFolder:FindFirstChild("SharpCombatModules")
		if combatFolder then combatFolder:Destroy() end
		local c1 = ControllerManagerRig.Cleanup()
		local c2 = WeaponToolAssembler.Cleanup()
		return {{ action = "cleanup", removedControllerInstances = c1, removedWeaponInstances = c2 }}
	end

	if ACTION == "install" or ACTION == "smoke_test" then
		local oldFolder = sharedFolder:FindFirstChild("SharpCombatModules")
		if oldFolder then oldFolder:Destroy() end
		local folder = Instance.new("Folder")
		folder.Name = "SharpCombatModules"
		folder:SetAttribute("SharpManaged", true)
		folder.Parent = sharedFolder

		for modName, src in pairs({{
			ControllerManagerRig = [========[{ctrl_src}]========],
			WeaponToolAssembler = [========[{weap_src}]========],
			CombatHitboxAndProjectile = [========[{hit_src}]========],
		}}) do
			local m = Instance.new("ModuleScript")
			m.Name = modName
			m.Source = src
			m.Parent = folder
		end

		if ACTION == "install" then
			return {{
				action = "install",
				installedFolderPath = folder:GetFullName(),
				modulesInstalled = {{ "ControllerManagerRig", "WeaponToolAssembler", "CombatHitboxAndProjectile" }},
			}}
		end
	end

	-- Deterministic smoke test of ControllerManagerRig + WeaponToolAssembler + CombatHitboxAndProjectile
	local rig = Instance.new("Model")
	rig.Name = "_SharpCombatSmokeRig"
	local hrp = Instance.new("Part")
	hrp.Name = "HumanoidRootPart"
	hrp.Size = Vector3.new(2, 2, 1)
	hrp.CFrame = CFrame.new(0, 50, 0)
	hrp.Anchored = true
	hrp.Parent = rig
	local rHand = Instance.new("Part")
	rHand.Name = "RightHand"
	rHand.Size = Vector3.new(1, 1, 1)
	rHand.CFrame = CFrame.new(1.5, 50, 0)
	rHand.Anchored = false
	rHand.Parent = rig
	local hum = Instance.new("Humanoid")
	hum.Parent = rig
	rig.PrimaryPart = hrp
	rig.Parent = Workspace

	local targetDummy = Instance.new("Model")
	targetDummy.Name = "_SharpCombatTargetDummy"
	targetDummy:SetAttribute("IsDamageableTarget", true)
	local tRoot = Instance.new("Part")
	tRoot.Name = "HumanoidRootPart"
	tRoot.Size = Vector3.new(2, 4, 2)
	tRoot.CFrame = CFrame.new(0, 50, -5)
	tRoot.Anchored = true
	tRoot.Parent = targetDummy
	local tHum = Instance.new("Humanoid")
	tHum.Parent = targetDummy
	targetDummy.PrimaryPart = tRoot
	targetDummy.Parent = Workspace

	local ctrlBundle = ControllerManagerRig.Attach(rig, {{ baseMoveSpeed = 20, sprintMultiplier = 1.5 }})
	local activeState = ControllerManagerRig.StepState(ctrlBundle, Vector3.new(0, 0, -1), Vector3.new(0, 0, -1), true)
	local dashVel = ControllerManagerRig.PerformDash(ctrlBundle, Vector3.new(0, 0, -1), 64, 6)

	local wSpec = {{
		weaponId = WEAPON_ID,
		displayName = WEAPON_ID,
		baseDamage = BASE_DAMAGE,
		rangeStuds = RANGE_STUDS,
		attackCooldownSec = 0.35,
		comboCount = 3,
	}}
	local wModel, _ = WeaponToolAssembler.AssembleWeaponModel(wSpec, rig)
	local motor = WeaponToolAssembler.BindToCharacter(rig, wModel, wSpec, true)
	local comboState = WeaponToolAssembler.CreateComboState(wSpec)
	local okS1, step1, label1 = WeaponToolAssembler.TryAdvanceCombo(comboState, 10.0)
	local okS2, step2, label2 = WeaponToolAssembler.TryAdvanceCombo(comboState, 10.5)

	local hits = CombatHitboxAndProjectile.SweepMeleeHitbox({{
		originCFrame = hrp.CFrame * CFrame.new(0, 0, -3),
		boxSize = Vector3.new(5, 5, 6),
		sweepDirection = Vector3.new(0, 0, -4),
		excludeInstances = {{ rig }},
	}})

	local validNear, reasonNear = CombatHitboxAndProjectile.ValidateServerHit({{
		attackerRoot = hrp,
		targetRoot = tRoot,
		maxRangeStuds = RANGE_STUDS,
		nowClock = 20.0,
		lastAttackClock = 19.0,
		minCooldownSec = 0.35,
	}})

	tRoot.CFrame = CFrame.new(0, 50, -45) -- Move out of reach
	local validFar, reasonFar = CombatHitboxAndProjectile.ValidateServerHit({{
		attackerRoot = hrp,
		targetRoot = tRoot,
		maxRangeStuds = RANGE_STUDS,
		nowClock = 21.0,
	}})

	local projSteps = CombatHitboxAndProjectile.SimulateProjectileTrajectory({{
		origin = Vector3.new(0, 60, 0),
		initialVelocity = Vector3.new(0, 10, -80),
		maxLifetimeSec = 0.5,
		excludeInstances = {{ rig, targetDummy }},
	}}, 1 / 30, 15)

	rig:Destroy()
	targetDummy:Destroy()
	ControllerManagerRig.Cleanup()
	WeaponToolAssembler.Cleanup()
	local combatFolder = sharedFolder:FindFirstChild("SharpCombatModules")
	if combatFolder then combatFolder:Destroy() end

	local allPass = (ctrlBundle.manager ~= nil)
		and (motor ~= nil)
		and okS1 and (step1 == 1)
		and okS2 and (step2 == 2)
		and (#hits == 1)
		and validNear and (reasonNear == "VALID_HIT")
		and (not validFar) and (reasonFar == "OUT_OF_RANGE")
		and (#projSteps >= 5)

	return {{
		action = "smoke_test",
		allAssertionsPassed = allPass,
		controllerState = activeState,
		dashSpeedMagnitude = dashVel.Magnitude,
		comboLabels = {{ label1, label2 }},
		meleeHitsDetected = #hits,
		serverValidationNear = reasonNear,
		serverValidationFar = reasonFar,
		projectileStepsSimulated = #projSteps,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    # ------------------------------------------------------------------
    # 2. Audio Wiring Graph, VFX Flipbooks, Highlight Pool & Cutscenes
    # ------------------------------------------------------------------
    def compile_audio_vfx_cutscene_luau(
        self,
        action: str = "install",  # "install" | "smoke_test" | "cleanup"
        root_prefix: str = "",
        max_highlight_slots: int = 28,
        master_volume: float = 1.0,
    ) -> str:
        audio_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "audio_bus_graph_builder.luau")
        vfx_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "vfx_preset_and_highlight_pool.luau")
        cam_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "camera_shake_and_cutscene.luau")

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local ACTION = {json.dumps(action)}
local ROOT_PREFIX = {json.dumps(root_prefix)}
local MAX_HL_SLOTS = {int(max_highlight_slots)}
local MASTER_VOL = {float(master_volume)}

local AudioBusGraphBuilder = (function()
{audio_src}
end)()

local VfxPresetAndHighlightPool = (function()
{vfx_src}
end)()

local CameraShakeAndCutscene = (function()
{cam_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpAudioVfxCutscene", "Sharp MCP: Audio, VFX & Cutscene (" .. ACTION .. ")")
local ok, resOrErr = xpcall(function()
	local repRoot = if ROOT_PREFIX ~= ""
		then ReplicatedStorage:FindFirstChild(ROOT_PREFIX) or ReplicatedStorage
		else ReplicatedStorage
	local sharedFolder = repRoot:FindFirstChild("Shared") or repRoot

	if ACTION == "cleanup" then
		local modFolder = sharedFolder:FindFirstChild("SharpAudioVfxModules")
		if modFolder then modFolder:Destroy() end
		local aRemoved = AudioBusGraphBuilder.Cleanup()
		local vRemoved = VfxPresetAndHighlightPool.Cleanup()
		return {{ action = "cleanup", removedAudioInstances = aRemoved, removedVfxInstances = vRemoved }}
	end

	local oldFolder = sharedFolder:FindFirstChild("SharpAudioVfxModules")
	if oldFolder then oldFolder:Destroy() end
	local folder = Instance.new("Folder")
	folder.Name = "SharpAudioVfxModules"
	folder:SetAttribute("SharpManaged", true)
	folder.Parent = sharedFolder

	for modName, src in pairs({{
		AudioBusGraphBuilder = [========[{audio_src}]========],
		VfxPresetAndHighlightPool = [========[{vfx_src}]========],
		CameraShakeAndCutscene = [========[{cam_src}]========],
	}}) do
		local m = Instance.new("ModuleScript")
		m.Name = modName
		m.Source = src
		m.Parent = folder
	end

	local graphBundle = AudioBusGraphBuilder.BuildMasterGraph({{ masterVolume = MASTER_VOL }})
	local hlPool = VfxPresetAndHighlightPool.CreateHighlightPool(MAX_HL_SLOTS)

	if ACTION == "install" then
		return {{
			action = "install",
			installedFolderPath = folder:GetFullName(),
			audioGraphPath = graphBundle.container:GetFullName(),
			usingModernAudioApi = graphBundle.usingModernAudioApi,
			wiresCreated = graphBundle.wiresCreated,
			highlightPoolMaxSlots = hlPool.maxSlots,
		}}
	end

	-- Smoke test: Audio 2D/3D emitters, 4 VFX emitters, 30 Highlight requests capped at 28, Camera shaker & spline
	local uiPlayer = AudioBusGraphBuilder.SpawnAudioPlayer2D(graphBundle, "UI_ButtonClick", "UI", false)
	local testPart = Instance.new("Part")
	testPart.Name = "_SharpVfxSmokePart"
	testPart.Anchored = true
	testPart.Position = Vector3.new(0, 40, 0)
	testPart.Parent = Workspace

	local emitter3D, _ = AudioBusGraphBuilder.Attach3DEmitter(testPart, "Combat_SwordSlash")
	local peSparks = VfxPresetAndHighlightPool.CreateEmitterPreset("HitSparks", testPart, 10)
	local peExp = VfxPresetAndHighlightPool.CreateEmitterPreset("ExplosionFlipbook", testPart, 4)

	-- Request 30 highlights on 30 dummy parts to prove LRU cap never exceeds 28
	local dummyParts = {{}}
	local evictionTriggered = false
	for i = 1, 30 do
		local p = Instance.new("Part")
		p.Anchored = true
		p.Parent = Workspace
		table.insert(dummyParts, p)
		local _, evicted = VfxPresetAndHighlightPool.AcquireHighlight(hlPool, p)
		if evicted then
			evictionTriggered = true
		end
	end
	local activeHlCount = VfxPresetAndHighlightPool.GetActiveCount(hlPool)

	local shaker = CameraShakeAndCutscene.CreateTraumaShaker()
	CameraShakeAndCutscene.AddTrauma(shaker, 0.8)
	local shakeCf = CameraShakeAndCutscene.StepTraumaShake(shaker, 1 / 60)

	local splineCf, fov, focusDist = CameraShakeAndCutscene.EvaluateSpline({{
		{{ cframe = CFrame.new(0, 10, 0), fov = 70, focusDistance = 12 }},
		{{ cframe = CFrame.new(0, 20, -20), fov = 60, focusDistance = 20 }},
		{{ cframe = CFrame.new(10, 25, -40), fov = 50, focusDistance = 30 }},
	}}, 0.5)

	for _, p in ipairs(dummyParts) do p:Destroy() end
	testPart:Destroy()
	folder:Destroy()
	AudioBusGraphBuilder.Cleanup()
	VfxPresetAndHighlightPool.Cleanup()

	local allPass = (uiPlayer ~= nil)
		and (emitter3D ~= nil)
		and (peSparks.Rate == 0)
		and (peExp.Rate == 0)
		and evictionTriggered
		and (activeHlCount <= 28)
		and (shakeCf ~= CFrame.identity)
		and (fov >= 50 and fov <= 70)
		and (splineCf.Position.Magnitude > 0)
		and (focusDist > 0)

	return {{
		action = "smoke_test",
		allAssertionsPassed = allPass,
		usingModernAudioApi = graphBundle.usingModernAudioApi,
		wiresCreated = graphBundle.wiresCreated,
		activeHighlightCountCappedAt = activeHlCount,
		evictionTriggeredOn30Requests = evictionTriggered,
		evaluatedSplineFov = fov,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    # ------------------------------------------------------------------
    # 3. Session-Locked DataStore, Economy, Inventory, Quests & Monetization
    # ------------------------------------------------------------------
    def compile_data_economy_monetization_luau(
        self,
        action: str = "install",  # "install" | "smoke_test" | "cleanup"
        root_prefix: str = "",
        store_name: str = "SharpPlayerProfile_v1",
    ) -> str:
        ds_src = self._read_skill_script("roblox-data-economy-monetization", "session_locked_datastore.luau")
        econ_src = self._read_skill_script("roblox-data-economy-monetization", "economy_inventory_quest_service.luau")
        mon_src = self._read_skill_script("roblox-data-economy-monetization", "monetization_receipt_handler.luau")

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ServerScriptService = game:GetService("ServerScriptService")

local ACTION = {json.dumps(action)}
local ROOT_PREFIX = {json.dumps(root_prefix)}
local STORE_NAME = {json.dumps(store_name)}

local SessionLockedDataStore = (function()
{ds_src}
end)()

local EconomyInventoryQuestService = (function()
{econ_src}
end)()

local MonetizationReceiptHandler = (function()
{mon_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpDataEconomy", "Sharp MCP: DataStore, Economy & Monetization (" .. ACTION .. ")")
local ok, resOrErr = xpcall(function()
	local sssRoot = if ROOT_PREFIX ~= ""
		then ServerScriptService:FindFirstChild(ROOT_PREFIX) or ServerScriptService
		else ServerScriptService
	local serverFolder = sssRoot:FindFirstChild("Server") or sssRoot

	if ACTION == "cleanup" then
		local old = serverFolder:FindFirstChild("SharpEconomyServices")
		if old then old:Destroy() end
		return {{ action = "cleanup", cleaned = true }}
	end

	local old = serverFolder:FindFirstChild("SharpEconomyServices")
	if old then old:Destroy() end
	local folder = Instance.new("Folder")
	folder.Name = "SharpEconomyServices"
	folder:SetAttribute("SharpManaged", true)
	folder:SetAttribute("StoreName", STORE_NAME)
	folder.Parent = serverFolder

	for modName, src in pairs({{
		SessionLockedDataStore = [========[{ds_src}]========],
		EconomyInventoryQuestService = [========[{econ_src}]========],
		MonetizationReceiptHandler = [========[{mon_src}]========],
	}}) do
		local m = Instance.new("ModuleScript")
		m.Name = modName
		m.Source = src
		m.Parent = folder
	end

	if ACTION == "install" then
		return {{
			action = "install",
			installedFolderPath = folder:GetFullName(),
			modulesInstalled = {{ "SessionLockedDataStore", "EconomyInventoryQuestService", "MonetizationReceiptHandler" }},
		}}
	end

	-- Deterministic smoke test of SessionLockedDataStore + EconomyInventoryQuestService + MonetizationReceiptHandler
	local mgr = SessionLockedDataStore.CreateManager({{
		storeName = STORE_NAME,
		schemaVersion = 2,
		defaultDataFactory = EconomyInventoryQuestService.CreateDefaultData,
		forceMock = true,
	}})

	local okLoad, profile, loadStatus = mgr.LoadProfile(9001)
	assert(okLoad and profile ~= nil, "Profile load failed: " .. tostring(loadStatus))

	local okBuy, buyMsg = EconomyInventoryQuestService.PurchaseShopItem(profile.data, {{
		itemId = "DragonShield",
		displayName = "Dragon Shield",
		currency = "Coins",
		price = 100,
	}}, 1)

	local okQuest, questMsg = EconomyInventoryQuestService.AdvanceQuest(
		profile.data,
		"DefeatBandits",
		5,
		"Coins",
		200
	)

	local okCode1, codeMsg1 = EconomyInventoryQuestService.RedeemPromoCode(
		profile.data,
		"SHARP2026",
		{{ SHARP2026 = {{ currency = "Gems", amount = 50 }} }}
	)
	local okCodeDup, codeMsgDup = EconomyInventoryQuestService.RedeemPromoCode(
		profile.data,
		"SHARP2026",
		{{ SHARP2026 = {{ currency = "Gems", amount = 50 }} }}
	)

	-- Roll loot 5 times with pityThreshold = 3 to guarantee Legendary drop
	local lootTable = {{
		{{ itemId = "IronDagger", rarity = "Common" :: "Common", weight = 80 }},
		{{ itemId = "MythicPhoenixBlade", rarity = "Legendary" :: "Legendary", weight = 1 }},
	}}
	local gotLegendary = false
	for _ = 1, 3 do
		local drop = EconomyInventoryQuestService.RollWeightedLoot(profile.data, lootTable, 3)
		if drop.rarity == "Legendary" then
			gotLegendary = true
		end
	end

	-- Idempotent ProcessReceipt verification
	local processor = MonetizationReceiptHandler.CreateProcessor(mgr, {{
		[1001] = function(data, _receipt)
			EconomyInventoryQuestService.AddCurrency(data, "Gems", 500)
			return true
		end,
	}})

	local dec1, msg1 = processor.ProcessReceipt({{
		PurchaseId = "rcpt_unique_001",
		PlayerId = 9001,
		ProductId = 1001,
	}})
	local gemsAfterFirst = profile.data.Currencies.Gems

	-- Replay exact same PurchaseId -> must return PurchaseGranted WITHOUT double-granting 500 Gems!
	local dec2, msg2 = processor.ProcessReceipt({{
		PurchaseId = "rcpt_unique_001",
		PlayerId = 9001,
		ProductId = 1001,
	}})
	local gemsAfterReplay = profile.data.Currencies.Gems

	local flushed = mgr.FlushAllProfiles()
	folder:Destroy()

	local allPass = okLoad
		and okBuy
		and okQuest and (questMsg == "QUEST_COMPLETED_AND_REWARDED")
		and okCode1 and (not okCodeDup) and (codeMsgDup == "CODE_ALREADY_REDEEMED")
		and gotLegendary
		and (dec1 == Enum.ProductPurchaseDecision.PurchaseGranted)
		and (dec2 == Enum.ProductPurchaseDecision.PurchaseGranted)
		and (msg2 == "ALREADY_PROCESSED_IDEMPOTENT")
		and (gemsAfterFirst == gemsAfterReplay)
		and (flushed == 1)

	return {{
		action = "smoke_test",
		allAssertionsPassed = allPass,
		buyStatus = buyMsg,
		questStatus = questMsg,
		codeReplayStatus = codeMsgDup,
		pityGuaranteedLegendary = gotLegendary,
		firstReceiptStatus = msg1,
		replayReceiptStatus = msg2,
		finalCoins = profile.data.Currencies.Coins,
		finalGems = gemsAfterReplay,
		profilesFlushed = flushed,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    # ------------------------------------------------------------------
    # 4. NPC AI Director, Branching Dialogue & Round/Wave Director
    # ------------------------------------------------------------------
    def compile_ai_and_gameplay_luau(
        self,
        action: str = "install",  # "install" | "smoke_test" | "cleanup"
        root_prefix: str = "",
        max_waves: int = 3,
        default_map: str = "AlpineCitadel",
    ) -> str:
        npc_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "npc_ai_director.luau")
        dlg_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "dialogue_and_interaction.luau")
        rnd_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "round_and_wave_director.luau")

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerScriptService = game:GetService("ServerScriptService")

local ACTION = {json.dumps(action)}
local ROOT_PREFIX = {json.dumps(root_prefix)}
local MAX_WAVES = {int(max_waves)}
local DEFAULT_MAP = {json.dumps(default_map)}

local NpcAiDirector = (function()
{npc_src}
end)()

local DialogueAndInteraction = (function()
{dlg_src}
end)()

local RoundAndWaveDirector = (function()
{rnd_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpAiGameplay", "Sharp MCP: AI & Gameplay Director (" .. ACTION .. ")")
local ok, resOrErr = xpcall(function()
	local sssRoot = if ROOT_PREFIX ~= ""
		then ServerScriptService:FindFirstChild(ROOT_PREFIX) or ServerScriptService
		else ServerScriptService
	local serverFolder = sssRoot:FindFirstChild("Server") or sssRoot

	if ACTION == "cleanup" then
		local old = serverFolder:FindFirstChild("SharpAiAndGameplayServices")
		if old then old:Destroy() end
		local n1 = NpcAiDirector.Cleanup()
		local n2 = DialogueAndInteraction.Cleanup()
		return {{ action = "cleanup", removedNpcs = n1, removedPrompts = n2 }}
	end

	local old = serverFolder:FindFirstChild("SharpAiAndGameplayServices")
	if old then old:Destroy() end
	local folder = Instance.new("Folder")
	folder.Name = "SharpAiAndGameplayServices"
	folder:SetAttribute("SharpManaged", true)
	folder.Parent = serverFolder

	for modName, src in pairs({{
		NpcAiDirector = [========[{npc_src}]========],
		DialogueAndInteraction = [========[{dlg_src}]========],
		RoundAndWaveDirector = [========[{rnd_src}]========],
	}}) do
		local m = Instance.new("ModuleScript")
		m.Name = modName
		m.Source = src
		m.Parent = folder
	end

	if ACTION == "install" then
		return {{
			action = "install",
			installedFolderPath = folder:GetFullName(),
			modulesInstalled = {{ "NpcAiDirector", "DialogueAndInteraction", "RoundAndWaveDirector" }},
		}}
	end

	-- Deterministic smoke test of NpcAiDirector + DialogueAndInteraction + RoundAndWaveDirector
	local spawnPos = Vector3.new(0, 60, 0)
	local agent = NpcAiDirector.SpawnNpcRig(spawnPos, {{
		npcId = "BanditCaptain",
		aggroRangeStuds = 35,
		attackRangeStuds = 6,
		maxLeashDistStuds = 60,
		patrolPoints = {{ Vector3.new(10, 60, 0), Vector3.new(0, 60, 10) }},
	}})

	local stPatrol, _ = NpcAiDirector.EvaluateTick(agent, {{}}, 1.0)
	local stChase, _ = NpcAiDirector.EvaluateTick(agent, {{ Vector3.new(0, 60, 18) }}, 2.0)
	local stAttack, _ = NpcAiDirector.EvaluateTick(agent, {{ Vector3.new(0, 60, 4) }}, 3.5)

	-- Teleport NPC past leash radius -> must enter LeashReturn
	agent.rootPart.CFrame = CFrame.new(0, 60, 100)
	local stLeash, _ = NpcAiDirector.EvaluateTick(agent, {{ Vector3.new(0, 60, 102) }}, 5.0)

	local prompt = DialogueAndInteraction.AttachInteractPrompt(agent.rootPart, "Talk", "Captain Vance", 10, 0)
	local okPromptNear, _ = DialogueAndInteraction.ValidateServerPromptTrigger(
		prompt,
		Vector3.new(0, 60, 95),
		agent.rootPart.Position
	)
	local okPromptFar, _ = DialogueAndInteraction.ValidateServerPromptTrigger(
		prompt,
		Vector3.new(0, 60, 0),
		agent.rootPart.Position
	)

	local dlgTree = {{
		npcId = "CaptainVance",
		rootNodeId = "intro",
		nodes = {{
			intro = {{
				nodeId = "intro",
				speakerName = "Captain Vance",
				bodyText = "Bandits have seized the watchtower. Will you help?",
				choices = {{
					{{ text = "I'll clear the watchtower!", nextNodeId = "accepted", grantQuestId = "DefeatBandits" }},
				}},
			}},
			accepted = {{
				nodeId = "accepted",
				speakerName = "Captain Vance",
				bodyText = "Good luck out there.",
				choices = {{
					{{ text = "Farewell.", nextNodeId = "" }},
				}},
			}},
		}},
	}}
	local okDlg, nextNode, grantedQuest, _ = DialogueAndInteraction.SelectDialogueChoice(dlgTree, "intro", 1, nil)

	local director = RoundAndWaveDirector.CreateDirector(MAX_WAVES, DEFAULT_MAP)
	RoundAndWaveDirector.CastMapVote(director, "VolcanicKeep", 2)
	RoundAndWaveDirector.CastMapVote(director, "AlpineCitadel", 1)
	local winningMap = RoundAndWaveDirector.ResolveWinningMap(director)

	for _ = 1, MAX_WAVES do
		local started, waveSpec, _ = RoundAndWaveDirector.StartNextWave(director)
		if started and waveSpec then
			RoundAndWaveDirector.RecordEnemyDefeated(director, waveSpec.enemyCount)
		end
	end

	NpcAiDirector.Cleanup()
	DialogueAndInteraction.Cleanup()
	folder:Destroy()

	local allPass = (stPatrol == "Patrol")
		and (stChase == "Chase")
		and (stAttack == "Attack")
		and (stLeash == "LeashReturn")
		and okPromptNear and (not okPromptFar)
		and okDlg and (nextNode ~= nil) and (grantedQuest == "DefeatBandits")
		and (winningMap == "VolcanicKeep")
		and (director.phase == "Victory")

	return {{
		action = "smoke_test",
		allAssertionsPassed = allPass,
		fsmStatesObserved = {{ stPatrol, stChase, stAttack, stLeash }},
		winningMap = winningMap,
		finalRoundPhase = director.phase,
		grantedQuest = grantedQuest,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    # ------------------------------------------------------------------
    # 5. World Assembly, Poisson Surface Scatter, Socket Snapping & Optimizer
    # ------------------------------------------------------------------
    def compile_world_assembly_optimize_luau(
        self,
        action: str = "install",  # "install" | "scatter_and_optimize" | "audit_overlaps" | "fix_overlaps" | "smoke_test" | "cleanup"
        root_prefix: str = "",
        min_xz: Optional[List[float]] = None,
        max_xz: Optional[List[float]] = None,
        min_spacing_studs: float = 14.0,
        max_count: int = 24,
        seed: int = 42,
        tolerance_studs: float = 0.15,
        float_tolerance_studs: float = 0.5,
        max_iterations: int = 8,
    ) -> str:
        if not math.isfinite(float_tolerance_studs):
            raise ValueError("float_tolerance_studs must be finite")
        float_tolerance_studs = max(0.0, min(float(float_tolerance_studs), 512.0))
        max_iterations = max(1, min(int(max_iterations), 64))
        scat_src = self._read_skill_script("roblox-world-assembly-and-optimization", "poisson_surface_scatter.luau")
        sock_src = self._read_skill_script("roblox-world-assembly-and-optimization", "modular_socket_assembler.luau")
        opt_src = self._read_skill_script("roblox-world-assembly-and-optimization", "scene_budget_optimizer.luau")

        mn = min_xz or [2016.0, 2016.0]
        mx = max_xz or [2240.0, 2240.0]

        return f"""--!strict
local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local ACTION = {json.dumps(action)}
local ROOT_PREFIX = {json.dumps(root_prefix)}
local MIN_XZ = Vector2.new({float(mn[0])}, {float(mn[1])})
local MAX_XZ = Vector2.new({float(mx[0])}, {float(mx[1])})
local MIN_SPACING = {float(min_spacing_studs)}
local MAX_COUNT = {int(max_count)}
local SEED = {int(seed)}
local OVERLAP_TOLERANCE = {float(tolerance_studs)}
local FLOAT_TOLERANCE = {float_tolerance_studs}
local MAX_ITERATIONS = {max_iterations}

local function _isAnchored(inst: Instance): boolean
	if inst:IsA("BasePart") then return inst.Anchored end
	local hasParts = false
	for _, part in ipairs(inst:GetDescendants()) do
		if part:IsA("BasePart") then
			hasParts = true
			if not part.Anchored then return false end
		end
	end
	return hasParts
end

local function _collectTopAssets()
	local assets = {{}}
	for _, child in ipairs(Workspace:GetChildren()) do
		if child:IsA("Terrain") or child:IsA("Camera") then
			continue
		end
		local lower = string.lower(child.Name)
		if string.find(lower, "baseplate", 1, true) or string.find(lower, "ground", 1, true) or string.find(lower, "floor", 1, true) then
			continue
		end
		if child:IsA("Model") then
			local okBox, cf, size = pcall(function()
				return (child :: Model):GetBoundingBox()
			end)
			if okBox and size.Magnitude > 0.2 then
				table.insert(assets, {{ name = child:GetFullName(), inst = child, cf = cf, half = size * 0.5, isModel = true }})
			end
		elseif child:IsA("BasePart") then
			local part = child :: BasePart
			if part.CanCollide and part.Size.Magnitude > 0.2 then
				table.insert(assets, {{ name = part:GetFullName(), inst = part, cf = part.CFrame, half = part.Size * 0.5, isModel = false }})
			end
		end
	end
	return assets
end

local function _obbOverlap(aCf: CFrame, aHalf: Vector3, bCf: CFrame, bHalf: Vector3, tol: number): (boolean, number, Vector3)
	local ax = {{ aCf.RightVector, aCf.UpVector, aCf.LookVector }}
	local bx = {{ bCf.RightVector, bCf.UpVector, bCf.LookVector }}
	local d = bCf.Position - aCf.Position
	local minPen = math.huge
	local bestAxis = Vector3.new(1, 0, 0)

	local function testAxis(axis: Vector3): boolean
		local mag = axis.Magnitude
		if mag < 1e-4 then return true end
		local u = axis / mag
		local ra = math.abs(ax[1]:Dot(u)) * aHalf.X + math.abs(ax[2]:Dot(u)) * aHalf.Y + math.abs(ax[3]:Dot(u)) * aHalf.Z
		local rb = math.abs(bx[1]:Dot(u)) * bHalf.X + math.abs(bx[2]:Dot(u)) * bHalf.Y + math.abs(bx[3]:Dot(u)) * bHalf.Z
		local dist = math.abs(d:Dot(u))
		local pen = (ra + rb) - dist
		if pen <= tol then
			return false
		end
		if pen < minPen then
			minPen = pen
			bestAxis = if d:Dot(u) >= 0 then u else -u
		end
		return true
	end

	for i = 1, 3 do
		if not testAxis(ax[i]) then return false, 0, Vector3.zero end
		if not testAxis(bx[i]) then return false, 0, Vector3.zero end
	end
	for i = 1, 3 do
		for j = 1, 3 do
			if not testAxis(ax[i]:Cross(bx[j])) then return false, 0, Vector3.zero end
		end
	end
	return true, minPen, bestAxis
end

local function _auditWorkspaceOverlaps(tol: number)
	local assets = _collectTopAssets()
	local overlaps = {{}}
	for i = 1, #assets do
		for j = i + 1, #assets do
			local A, B = assets[i], assets[j]
			local hit, pen, axis = _obbOverlap(A.cf, A.half, B.cf, B.half, tol)
			if hit then
				table.insert(overlaps, {{
					a = A.name,
					b = B.name,
					penetrationStuds = math.round(pen * 1000) / 1000,
					axis = {{ math.round(axis.X * 1000) / 1000, math.round(axis.Y * 1000) / 1000, math.round(axis.Z * 1000) / 1000 }},
					_a = A,
					_b = B,
				}})
			end
		end
	end
	return assets, overlaps
end

local function _verticalRadius(asset): number
	local cf, half = asset.cf, asset.half
	return math.abs(cf.RightVector.Y) * half.X + math.abs(cf.UpVector.Y) * half.Y + math.abs(cf.LookVector.Y) * half.Z
end

local function _auditFloatingAssets(assets)
	local floating = {{}}
	for _, asset in ipairs(assets) do
		if not _isAnchored(asset.inst) or asset.inst:GetAttribute("SharpAllowFloating") == true then
			continue
		end
		local bottom = asset.cf.Position.Y - _verticalRadius(asset)
		local params = RaycastParams.new()
		params.FilterType = Enum.RaycastFilterType.Exclude
		params.FilterDescendantsInstances = {{ asset.inst }}
		params.RespectCanCollide = true
		local origin = Vector3.new(asset.cf.Position.X, bottom + 3, asset.cf.Position.Z)
		local hit = Workspace:Raycast(origin, Vector3.new(0, -512, 0), params)
		local gap = if hit then bottom - hit.Position.Y else nil
		if not hit or (gap and math.abs(gap) > FLOAT_TOLERANCE) then
			table.insert(floating, {{
				name = asset.name,
				gapStuds = gap,
				kind = if not hit then "void" elseif gap < 0 then "embedded" else "floating",
				groundHit = if hit then hit.Instance:GetFullName() else nil,
				_asset = asset,
			}})
		end
	end
	return floating
end

local function _worldResult(action, assets, rawOverlaps, rawFloating)
	local overlaps, floating = {{}}, {{}}
	for _, ov in ipairs(rawOverlaps) do
		table.insert(overlaps, {{ a = ov.a, b = ov.b, penetrationStuds = ov.penetrationStuds, axis = ov.axis }})
	end
	for _, entry in ipairs(rawFloating) do
		table.insert(floating, {{ name = entry.name, gapStuds = entry.gapStuds, groundHit = entry.groundHit, kind = entry.kind }})
	end
	return {{
		action = action,
		assetsChecked = #assets,
		overlapCount = #overlaps,
		overlaps = overlaps,
		floatingCount = #floating,
		floating = floating,
		allClean = (#overlaps == 0 and #floating == 0),
	}}
end

local function _translateAsset(asset, shift: Vector3)
	local inst = asset.inst
	if inst:IsA("Model") then
		inst:PivotTo(inst:GetPivot() + shift)
	elseif inst:IsA("BasePart") then
		inst.CFrame = inst.CFrame + shift
	end
	asset.cf = asset.cf + shift
end

if ACTION == "audit_overlaps" then
	local assets, rawOverlaps = _auditWorkspaceOverlaps(OVERLAP_TOLERANCE)
	return HttpService:JSONEncode({{
		ok = true,
		recordingStatus = "None",
		result = _worldResult(ACTION, assets, rawOverlaps, _auditFloatingAssets(assets)),
	}})
end

local PoissonSurfaceScatter = (function()
{scat_src}
end)()

local ModularSocketAssembler = (function()
{sock_src}
end)()

local SceneBudgetOptimizer = (function()
{opt_src}
end)()

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpWorldAssembly", "Sharp MCP: World Assembly & Optimization (" .. ACTION .. ")")
local ok, resOrErr = xpcall(function()
	local repRoot = if ROOT_PREFIX ~= ""
		then ReplicatedStorage:FindFirstChild(ROOT_PREFIX) or ReplicatedStorage
		else ReplicatedStorage
	local sharedFolder = repRoot:FindFirstChild("Shared") or repRoot

	if ACTION == "fix_overlaps" then
		local moves, grounded = {{}}, {{}}
		local iterations = 0
		for iteration = 1, MAX_ITERATIONS do
			local assets, rawOverlaps = _auditWorkspaceOverlaps(OVERLAP_TOLERANCE)
			if #rawOverlaps == 0 and #_auditFloatingAssets(assets) == 0 then break end
			iterations = iteration
			local moved = {{}}
			local changed = false
			for _, ov in ipairs(rawOverlaps) do
				local A, B = ov._a, ov._b
				local canA = A.inst:GetAttribute("SharpLocked") ~= true
				local canB = B.inst:GetAttribute("SharpLocked") ~= true
				if not canA and not canB then continue end
				local volumeA = A.half.X * A.half.Y * A.half.Z
				local volumeB = B.half.X * B.half.Y * B.half.Z
				local target = if canA and (not canB or volumeA < volumeB) then A else B
				if moved[target.inst] then continue end
				local hit, penetration, axis = _obbOverlap(A.cf, A.half, B.cf, B.half, OVERLAP_TOLERANCE)
				if not hit then continue end
				local away = if target == B then axis else -axis
				local shift: Vector3
				if math.abs(away.Y) > 0.9 then
					local other = if target == A then B else A
					local top = other.cf.Position.Y + _verticalRadius(other)
					local bottom = target.cf.Position.Y - _verticalRadius(target)
					shift = Vector3.new(0, math.max(penetration, top - bottom) + 0.25, 0)
				else
					local horizontal = Vector3.new(away.X, 0, away.Z)
					local horizontalMagnitude = horizontal.Magnitude
					shift = horizontal / horizontalMagnitude * ((penetration + 0.25) / horizontalMagnitude)
				end
				_translateAsset(target, shift)
				moved[target.inst] = true
				changed = true
				table.insert(moves, {{ a = ov.a, b = ov.b, name = target.name, shiftedStuds = shift.Magnitude }})
			end
			for _, entry in ipairs(_auditFloatingAssets(assets)) do
				if moved[entry._asset.inst] then continue end
				local current = _auditFloatingAssets({{ entry._asset }})[1]
				if not current then continue end
				entry = current
				if entry.groundHit and entry.gapStuds and entry._asset.inst:GetAttribute("SharpLocked") ~= true then
					_translateAsset(entry._asset, Vector3.new(0, -entry.gapStuds, 0))
					moved[entry._asset.inst] = true
					changed = true
					table.insert(grounded, {{ name = entry.name, gapStuds = entry.gapStuds, groundHit = entry.groundHit, kind = entry.kind }})
				end
			end
			if not changed then break end
		end
		local assets, rawOverlaps = _auditWorkspaceOverlaps(OVERLAP_TOLERANCE)
		local result = _worldResult(ACTION, assets, rawOverlaps, _auditFloatingAssets(assets))
		result.fixedCount = #moves + #grounded
		result.iterations = iterations
		result.moves = moves
		result.fixed = moves
		result.grounded = grounded
		result.remainingOverlapCount = result.overlapCount
		result.remainingFloatingCount = result.floatingCount
		return result
	end

	if ACTION == "cleanup" then
		local old = sharedFolder:FindFirstChild("SharpWorldAssemblyModules")
		if old then old:Destroy() end
		local r1 = PoissonSurfaceScatter.Cleanup()
		local r2 = ModularSocketAssembler.Cleanup()
		return {{ action = "cleanup", removedScattered = r1, removedModular = r2 }}
	end

	local old = sharedFolder:FindFirstChild("SharpWorldAssemblyModules")
	if old then old:Destroy() end
	local folder = Instance.new("Folder")
	folder.Name = "SharpWorldAssemblyModules"
	folder:SetAttribute("SharpManaged", true)
	folder.Parent = sharedFolder

	for modName, src in pairs({{
		PoissonSurfaceScatter = [========[{scat_src}]========],
		ModularSocketAssembler = [========[{sock_src}]========],
		SceneBudgetOptimizer = [========[{opt_src}]========],
	}}) do
		local m = Instance.new("ModuleScript")
		m.Name = modName
		m.Source = src
		m.Parent = folder
	end

	if ACTION == "install" then
		return {{
			action = "install",
			installedFolderPath = folder:GetFullName(),
			modulesInstalled = {{ "PoissonSurfaceScatter", "ModularSocketAssembler", "SceneBudgetOptimizer" }},
		}}
	end

	if ACTION == "scatter_and_optimize" then
		local propFolder, scatReport = PoissonSurfaceScatter.ScatterStylizedTreesAndRocks({{
			minXZ = MIN_XZ,
			maxXZ = MAX_XZ,
			minSpacingStuds = MIN_SPACING,
			maxCount = MAX_COUNT,
			seed = SEED,
		}})
		local optReport = SceneBudgetOptimizer.OptimizeScene({{
			targetRoot = propFolder,
			smallPartDiagonalStuds = 6.0,
		}})
		return {{
			action = "scatter_and_optimize",
			scatterReport = scatReport,
			optimizationReport = optReport,
		}}
	end

	-- Deterministic smoke test of PoissonSurfaceScatter + ModularSocketAssembler + SceneBudgetOptimizer
	local groundPlate = Instance.new("Part")
	groundPlate.Name = "_SharpScatterTestGround"
	groundPlate.Size = Vector3.new(120, 4, 120)
	groundPlate.CFrame = CFrame.new(0, 40, 0)
	groundPlate.Anchored = true
	groundPlate.Material = Enum.Material.Grass
	groundPlate.Parent = Workspace

	local propFolder, scatReport = PoissonSurfaceScatter.ScatterStylizedTreesAndRocks({{
		minXZ = Vector2.new(-45, -45),
		maxXZ = Vector2.new(45, 45),
		rayStartY = 80,
		rayDropDistance = 60,
		minSpacingStuds = 12,
		maxCount = 12,
		seed = SEED,
	}})

	local segA = ModularSocketAssembler.CreateModularSegment("Wall_A", Vector3.new(16, 12, 4), CFrame.new(0, 48, 0), Workspace)
	local segB = ModularSocketAssembler.CreateModularSegment("Wall_B", Vector3.new(16, 12, 4), CFrame.new(50, 80, 50), Workspace)
	local okSnap, _, snapStatus = ModularSocketAssembler.SnapModelToSocket(
		segB,
		"SnapSocket_West",
		segA,
		"SnapSocket_East"
	)

	local optReport = SceneBudgetOptimizer.OptimizeScene({{
		targetRoot = propFolder,
		smallPartDiagonalStuds = 6.0,
	}})

	groundPlate:Destroy()
	PoissonSurfaceScatter.Cleanup()
	ModularSocketAssembler.Cleanup()
	folder:Destroy()

	local allPass = (scatReport.placedCount > 0)
		and okSnap and (snapStatus == "SNAPPED_FLUSH")
		and (optReport.totalBasePartsScanned > 0)

	return {{
		action = "smoke_test",
		allAssertionsPassed = allPass,
		scatterReport = scatReport,
		modularSnapStatus = snapStatus,
		optimizationReport = optReport,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    # ------------------------------------------------------------------
    # 6. Automated Playtest Scenario Bot Runner (`sharp_playtest_scenario`)
    # ------------------------------------------------------------------
    def compile_playtest_scenario_luau(
        self,
        scenario: str = "full_slice_bot",
        cleanup_after: bool = True,
    ) -> str:
        ctrl_src = self._read_skill_script("roblox-combat-and-controllers", "controller_manager_rig.luau")
        weap_src = self._read_skill_script("roblox-combat-and-controllers", "weapon_tool_assembler.luau")
        hit_src = self._read_skill_script("roblox-combat-and-controllers", "combat_hitbox_and_projectile.luau")
        audio_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "audio_bus_graph_builder.luau")
        vfx_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "vfx_preset_and_highlight_pool.luau")
        cam_src = self._read_skill_script("roblox-audio-vfx-cutscenes", "camera_shake_and_cutscene.luau")
        ds_src = self._read_skill_script("roblox-data-economy-monetization", "session_locked_datastore.luau")
        econ_src = self._read_skill_script("roblox-data-economy-monetization", "economy_inventory_quest_service.luau")
        mon_src = self._read_skill_script("roblox-data-economy-monetization", "monetization_receipt_handler.luau")
        npc_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "npc_ai_director.luau")
        dlg_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "dialogue_and_interaction.luau")
        rnd_src = self._read_skill_script("roblox-ai-and-gameplay-systems", "round_and_wave_director.luau")
        scat_src = self._read_skill_script("roblox-world-assembly-and-optimization", "poisson_surface_scatter.luau")
        sock_src = self._read_skill_script("roblox-world-assembly-and-optimization", "modular_socket_assembler.luau")
        opt_src = self._read_skill_script("roblox-world-assembly-and-optimization", "scene_budget_optimizer.luau")

        return f"""local HttpService = game:GetService("HttpService")
local LogService = game:GetService("LogService")
local Workspace = game:GetService("Workspace")

local SCENARIO = {json.dumps(scenario)}
local CLEANUP_AFTER = {"true" if cleanup_after else "false"}

local ControllerManagerRig = (function() {ctrl_src} end)()
local WeaponToolAssembler = (function() {weap_src} end)()
local CombatHitboxAndProjectile = (function() {hit_src} end)()
local AudioBusGraphBuilder = (function() {audio_src} end)()
local VfxPresetAndHighlightPool = (function() {vfx_src} end)()
local CameraShakeAndCutscene = (function() {cam_src} end)()
local SessionLockedDataStore = (function() {ds_src} end)()
local EconomyInventoryQuestService = (function() {econ_src} end)()
local MonetizationReceiptHandler = (function() {mon_src} end)()
local NpcAiDirector = (function() {npc_src} end)()
local DialogueAndInteraction = (function() {dlg_src} end)()
local RoundAndWaveDirector = (function() {rnd_src} end)()
local PoissonSurfaceScatter = (function() {scat_src} end)()
local ModularSocketAssembler = (function() {sock_src} end)()
local SceneBudgetOptimizer = (function() {opt_src} end)()

if SCENARIO == "cleanup" then
	ControllerManagerRig.Cleanup()
	WeaponToolAssembler.Cleanup()
	AudioBusGraphBuilder.Cleanup()
	VfxPresetAndHighlightPool.Cleanup()
	NpcAiDirector.Cleanup()
	DialogueAndInteraction.Cleanup()
	PoissonSurfaceScatter.Cleanup()
	ModularSocketAssembler.Cleanup()
	return HttpService:JSONEncode({{ ok = true, scenario = "cleanup" }})
end

local ok, resOrErr = xpcall(function()
	local logsBefore = #LogService:GetLogHistory()
	local stepsCompleted = {{}}

	-- Step 1: World Arena Floor, Modular Kit Snapping & Prop Scatter
	local arenaFloor = Instance.new("Part")
	arenaFloor.Name = "_SharpBotArenaFloor"
	arenaFloor.Size = Vector3.new(96, 4, 96)
	arenaFloor.CFrame = CFrame.new(0, 120, 0)
	arenaFloor.Anchored = true
	arenaFloor.Material = Enum.Material.Grass
	arenaFloor.Parent = Workspace

	local wall1 = ModularSocketAssembler.CreateModularSegment("GateWall_1", Vector3.new(12, 10, 4), CFrame.new(0, 127, -30), Workspace)
	local wall2 = ModularSocketAssembler.CreateModularSegment("GateWall_2", Vector3.new(12, 10, 4), CFrame.new(25, 140, 0), Workspace)
	local okSnap, _, _ = ModularSocketAssembler.SnapModelToSocket(wall2, "SnapSocket_West", wall1, "SnapSocket_East")
	local propFolder, scatRep = PoissonSurfaceScatter.ScatterStylizedTreesAndRocks({{
		minXZ = Vector2.new(-40, -40),
		maxXZ = Vector2.new(40, 40),
		rayStartY = 160,
		rayDropDistance = 60,
		minSpacingStuds = 16,
		maxCount = 8,
		seed = 77,
	}})
	local optRep = SceneBudgetOptimizer.OptimizeScene({{ targetRoot = propFolder }})
	table.insert(stepsCompleted, "WorldAssembly_ScatterAndSnap")

	-- Step 2: Audio Bus Graph, Highlight Pool & Camera Cutscene Spline
	local audioGraph = AudioBusGraphBuilder.BuildMasterGraph()
	local hlPool = VfxPresetAndHighlightPool.CreateHighlightPool(28)
	local shaker = CameraShakeAndCutscene.CreateTraumaShaker()
	CameraShakeAndCutscene.AddTrauma(shaker, 0.65)
	local shakeDelta = CameraShakeAndCutscene.StepTraumaShake(shaker, 1 / 60)
	table.insert(stepsCompleted, "AudioVfx_GraphAndHighlightPool")

	-- Step 3: Player Bot Rig + ControllerManager + Weapon Equip + NPC Spawn & Combat Loop
	local botRig = Instance.new("Model")
	botRig.Name = "_SharpPlaytestBot"
	local botHrp = Instance.new("Part")
	botHrp.Name = "HumanoidRootPart"
	botHrp.Size = Vector3.new(2, 2, 1)
	botHrp.CFrame = CFrame.new(0, 125, 0)
	botHrp.Anchored = true
	botHrp.Parent = botRig
	local botHum = Instance.new("Humanoid")
	botHum.Parent = botRig
	botRig.PrimaryPart = botHrp
	botRig.Parent = Workspace

	local ctrlBundle = ControllerManagerRig.Attach(botRig, {{ baseMoveSpeed = 20 }})
	ControllerManagerRig.StepState(ctrlBundle, Vector3.new(0, 0, -1), Vector3.new(0, 0, -1), true)
	local wSpec = {{ weaponId = "HeroBlade", displayName = "Hero Blade", baseDamage = 50, rangeStuds = 10 }}
	local wModel, _ = WeaponToolAssembler.AssembleWeaponModel(wSpec, botRig)
	WeaponToolAssembler.BindToCharacter(botRig, wModel, wSpec, true)

	local npcAgent = NpcAiDirector.SpawnNpcRig(Vector3.new(0, 125, -6), {{
		npcId = "ArenaGuard",
		maxHealth = 100,
		aggroRangeStuds = 30,
		attackRangeStuds = 5,
	}})
	local npcState, _ = NpcAiDirector.EvaluateTick(npcAgent, {{ botHrp.Position }}, 1.0)

	local hits = CombatHitboxAndProjectile.SweepMeleeHitbox({{
		originCFrame = botHrp.CFrame * CFrame.new(0, 0, -3),
		boxSize = Vector3.new(6, 6, 8),
		excludeInstances = {{ botRig }},
	}})
	local validHit, _ = CombatHitboxAndProjectile.ValidateServerHit({{
		attackerRoot = botHrp,
		targetRoot = npcAgent.rootPart,
		maxRangeStuds = 10,
	}})
	if #hits > 0 and validHit then
		VfxPresetAndHighlightPool.AcquireHighlight(hlPool, npcAgent.model)
		VfxPresetAndHighlightPool.CreateEmitterPreset("HitSparks", npcAgent.rootPart, 12)
		npcAgent.humanoid:TakeDamage(100)
	end
	local npcAfterDeath, _ = NpcAiDirector.EvaluateTick(npcAgent, {{ botHrp.Position }}, 2.0)
	table.insert(stepsCompleted, "CombatAndAI_BotDefeatedEnemy")

	-- Step 4: DataStore Profile, Quest Reward, Shop Purchase & Idempotent Receipt
	local dsMgr = SessionLockedDataStore.CreateManager({{
		storeName = "SharpBotScenarioStore",
		schemaVersion = 1,
		defaultDataFactory = EconomyInventoryQuestService.CreateDefaultData,
		forceMock = true,
	}})
	local _, profile, _ = dsMgr.LoadProfile(777001)
	assert(profile ~= nil, "Bot profile failed to load")
	EconomyInventoryQuestService.AdvanceQuest(profile.data, "DefeatBandits", 5, "Coins", 300)
	local okShop, _ = EconomyInventoryQuestService.PurchaseShopItem(profile.data, {{
		itemId = "PhoenixArmor",
		displayName = "Phoenix Armor",
		currency = "Coins",
		price = 400,
	}}, 1)
	local rcptProc = MonetizationReceiptHandler.CreateProcessor(dsMgr, {{
		[501] = function(data, _)
			EconomyInventoryQuestService.AddCurrency(data, "Gems", 250)
			return true
		end,
	}})
	local d1, _ = rcptProc.ProcessReceipt({{ PurchaseId = "bot_rcpt_1", PlayerId = 777001, ProductId = 501 }})
	local d2, rStatus2 = rcptProc.ProcessReceipt({{ PurchaseId = "bot_rcpt_1", PlayerId = 777001, ProductId = 501 }})
	dsMgr.FlushAllProfiles()
	table.insert(stepsCompleted, "EconomyAndMonetization_QuestShopAndReceipt")

	-- Step 5: Round & Wave Director Progression
	local roundDir = RoundAndWaveDirector.CreateDirector(1, "AlpineCitadel")
	local _, wave1, _ = RoundAndWaveDirector.StartNextWave(roundDir)
	if wave1 then
		RoundAndWaveDirector.RecordEnemyDefeated(roundDir, wave1.enemyCount)
	end
	table.insert(stepsCompleted, "RoundDirector_Victory")

	-- Check LogService for any runtime errors emitted during scenario
	local allLogs = LogService:GetLogHistory()
	local runtimeErrors = {{}}
	for i = logsBefore + 1, #allLogs do
		local entry = allLogs[i]
		if entry and entry.messageType == Enum.MessageType.MessageError then
			table.insert(runtimeErrors, entry.message)
		end
	end

	if CLEANUP_AFTER then
		arenaFloor:Destroy()
		botRig:Destroy()
		ControllerManagerRig.Cleanup()
		WeaponToolAssembler.Cleanup()
		AudioBusGraphBuilder.Cleanup()
		VfxPresetAndHighlightPool.Cleanup()
		NpcAiDirector.Cleanup()
		DialogueAndInteraction.Cleanup()
		PoissonSurfaceScatter.Cleanup()
		ModularSocketAssembler.Cleanup()
	end

	local passed = okSnap
		and (scatRep.placedCount > 0)
		and (optRep.totalBasePartsScanned > 0)
		and (audioGraph.container ~= nil)
		and (shakeDelta ~= CFrame.identity)
		and (npcState == "Chase")
		and (npcAfterDeath == "Dead")
		and okShop
		and (d1 == Enum.ProductPurchaseDecision.PurchaseGranted)
		and (d2 == Enum.ProductPurchaseDecision.PurchaseGranted)
		and (rStatus2 == "ALREADY_PROCESSED_IDEMPOTENT")
		and (roundDir.phase == "Victory")
		and (#runtimeErrors == 0)

	return {{
		scenario = SCENARIO,
		allAssertionsPassed = passed,
		stepsCompleted = stepsCompleted,
		scatteredPropsCount = scatRep.placedCount,
		modularSnapSuccess = okSnap,
		enemyInitialState = npcState,
		enemyFinalState = npcAfterDeath,
		shopPurchaseSucceeded = okShop,
		idempotentReceiptReplay = rStatus2,
		finalRoundPhase = roundDir.phase,
		runtimeErrorCount = #runtimeErrors,
		runtimeErrors = runtimeErrors,
	}}
end, debug.traceback)

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	result = resOrErr,
}})
"""

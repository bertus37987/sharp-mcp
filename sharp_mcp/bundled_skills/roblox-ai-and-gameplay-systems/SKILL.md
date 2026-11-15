---
name: roblox-ai-and-gameplay-systems
description: >-
  Build Roblox NPC AI state machines (CollectionService + PathfindingService
  with AgentParameters, PathfindingModifier, PathfindingLink, Blocked recompute
  throttling, SetNetworkOwner(nil)), ProximityPrompt branching dialogue trees
  wired to NpcDialogGui, and round/wave/lobby directors. Use whenever the user
  asks for enemy AI, patrol/chase/attack NPCs, boss behavior, quest giver
  dialogues, ProximityPrompts, or wave-defense/arena/obby/round game loops.
---

# Roblox NPC AI, Pathfinding, Dialogue & Round/Wave Directors (`roblox-ai-and-gameplay-systems`)

Production architecture and `--!strict` Luau modules for **centralized `CollectionService` NPC AI directors** (`PathfindingService`), **branching `ProximityPrompt` dialogue trees** wired to `NpcDialogGui` (`02_roblox_gui`), and **configurable Round/Wave state machines**.

---

## 1. Non-Negotiable AI & Gameplay Guardrails

1. **Centralized AI Tick (Never 1 `while true do` Script Per NPC):**
   - Never clone a separate `Script` into every enemy `Model`. Tag NPCs with `CollectionService:AddTag(npcModel, "SharpNpcAgentManaged")` and drive all agents from a single `NpcAiDirector` tick loop in `ServerScriptService` (throttling path recomputation to `>= 0.45s` per agent).
2. **Server Network Ownership (`SetNetworkOwner(nil)`):**
   - Always call `pcall(function() rootPart:SetNetworkOwner(nil) end)` on server-controlled NPCs so nearby clients cannot hijack physics or freeze enemy movement.
3. **`PathfindingService` Best Practices:**
   - Configure `PathfindingService:CreatePath({ AgentRadius = 2.2, AgentHeight = 5.5, AgentCanJump = true, AgentCanClimb = true, WaypointSpacing = 4.0, Costs = { Water = 20.0, DangerZone = math.huge } })`.
   - Connect `path.Blocked:Connect(...)` to mark the path stale when dynamic obstacles block upcoming waypoints (`blockedWaypointIdx >= currentWaypointIdx`).
   - Enforce a **Leash Radius** (`maxLeashDistStuds`, e.g., `90` studs from `spawnOrigin`) so kited enemies transition to `LeashReturn` and heal back to spawn instead of chasing across the entire map.
4. **`ProximityPrompt` Server Validation:**
   - When `ProximityPrompt.Triggered` fires on the server, ALWAYS verify `(player.Character.PrimaryPart.Position - promptParent.Position).Magnitude <= prompt.MaxActivationDistance + 6.0` before advancing dialogue or granting items.

---

## 2. Canonical Scripts & References

### Scripts (`scripts/`)
- [`scripts/npc_ai_director.luau`](scripts/npc_ai_director.luau): `NpcAiDirector` — Centralized FSM (`Idle`, `Patrol`, `Chase`, `Attack`, `LeashReturn`, `Dead`) with `PathfindingService:CreatePath`, `PathfindingModifier` cost support, `SetNetworkOwner(nil)`, and deterministic step evaluation.
- [`scripts/dialogue_and_interaction.luau`](scripts/dialogue_and_interaction.luau): `DialogueAndInteraction` — Attaches server-validated `ProximityPrompt`s (`RequiresLineOfSight = true`, `HoldDuration`, `UIOffset`) and evaluates branching dialogue graphs (`nodes`, `choices`, `conditionTag`, `questTrigger`).
- [`scripts/round_and_wave_director.luau`](scripts/round_and_wave_director.luau): `RoundAndWaveDirector` — Configurable game loop state machine (`Lobby` -> `Intermission` -> `MapVote` -> `ActiveRound` -> `WaveClear` -> `Victory` -> `Reset`) with wave enemy scaling and reward distribution.

### References (`references/`)
- [`references/npc_ai_dialogue_and_round_director.md`](references/npc_ai_dialogue_and_round_director.md): `PathfindingService` cost modifiers, `PathfindingLink` jump/climb attachments, FSM transition table, and round director state diagram.

---

## 3. Execution Workflow via `Sharp` MCP

1. Call `sharp_ai_and_gameplay_systems(action="install", ...)` to install `NpcAiDirector`, `DialogueAndInteraction`, and `RoundAndWaveDirector` under `ServerScriptService`.
2. Call `sharp_ai_and_gameplay_systems(action="smoke_test")` to verify FSM transitions (`Patrol` -> `Chase` -> `Attack` -> `LeashReturn`), `ProximityPrompt` distance validation, branching dialogue choices, and wave/map-vote progression.

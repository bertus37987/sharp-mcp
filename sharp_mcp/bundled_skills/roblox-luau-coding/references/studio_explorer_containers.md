# Studio Explorer Container Architecture

This reference maps every standard Explorer container service in Roblox Studio, its replication boundary, runtime target mapping, script execution behavior, and critical architectural rules.

---

## 1. Replication & Script Execution Matrix

```
+-----------------------------+--------------------+-------------------------------+------------------------------+
| Edit-Time Container         | Replicates?        | Runtime Client Counterpart    | Script Execution Rule        |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| Workspace                   | Yes (3D / stream)  | Workspace                     | Server/Client RunContext ok; |
|                             |                    |                               | Legacy Script runs if enabled|
+-----------------------------+--------------------+-------------------------------+------------------------------+
| Players                     | Partial (Players)  | Players (LocalPlayer set)     | Container for runtime Players|
+-----------------------------+--------------------+-------------------------------+------------------------------+
| Lighting                    | Yes                | Lighting                      | Visual/atmosphere objects    |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| MaterialService             | Yes                | MaterialService               | MaterialVariant definitions  |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| NetworkClient               | NotReplicated      | NetworkClient (client VM)     | Client network events only   |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| ReplicatedFirst             | Yes (FIRST, once)  | ReplicatedFirst               | LocalScript / Client Script  |
|                             |                    |                               | runs immediately on load     |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| ReplicatedStorage           | Yes (all clients)  | ReplicatedStorage             | NO Legacy Scripts run;       |
|                             |                    |                               | ModuleScripts CAN be         |
|                             |                    |                               | decompiled by exploiters     |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| ServerScriptService         | NotReplicated      | (Hidden from clients)         | Canonical home of Server     |
|                             |                    |                               | Scripts & Server Modules     |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| ServerStorage               | NotReplicated      | (Hidden from clients)         | SCRIPTS DO NOT EXECUTE HERE; |
|                             |                    |                               | Server ModuleScripts only    |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| StarterGui                  | Cloned per spawn   | Player.PlayerGui              | LocalScript / Client Script  |
|                             |                    |                               | cloned into PlayerGui        |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| StarterPack                 | Cloned per spawn   | Player.Backpack               | Tool scripts run on equip/   |
|                             |                    |                               | when inside Backpack/Char    |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| StarterPlayer               | Container root     | Holds subcontainers + props   | Configures Player/Camera/Ctrl|
|  |- StarterPlayerScripts    | Cloned once/join   | Player.PlayerScripts          | Runs once on join (ideal for |
|  |                          |                    |                               | client controllers)          |
|  +- StarterCharacterScripts | Cloned every spawn | Player.Character              | Runs fresh each respawn      |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| Teams                       | Yes                | Teams                         | Team objects; groups         |
|                             |                    |                               | PlayerList & SpawnLocations  |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| SoundService                | Yes                | SoundService                  | Audio config & SoundGroups   |
+-----------------------------+--------------------+-------------------------------+------------------------------+
| TextChatService             | Yes                | TextChatService               | Channels, commands, chat UI  |
+-----------------------------+--------------------+-------------------------------+------------------------------+
```

> [!CAUTION]
> Everything outside `ServerScriptService` and `ServerStorage` that replicates to the client (including disabled `LocalScript`s, `Client` scripts, and **unrequired `ModuleScript`s** inside `ReplicatedStorage` or `Workspace`) can be extracted and decompiled by exploiters.

---

## 2. All 15 Explorer Container Services (+ `VoiceChatService`)

### 2.1 `Workspace`
- **Inheritance:** `WorldRoot` > `Model` > `PVInstance` > `Instance`.
- **Purpose:** The active 3D world. Only `BasePart`s, `Model`s, `Terrain`, attachments, and world effects inside `Workspace` simulate physics and render on screen.
- **Canonical Children:** `Terrain` (voxel ground/water), `CurrentCamera` (`Camera` per client; assigning `Workspace.CurrentCamera` destroys other `Camera` instances inside `Workspace`), world geometry folders (`World`, `Props`, `NPCs`, `SpawnLocations`).
- **Key Properties:**
  - `GlobalWind`: `Vector3` driving wind-reactive grass, clouds, and particles.
  - `StreamingEnabled`, `ModelStreamingBehavior` (`Legacy` vs `Improved`), `StreamingMinRadius`, `StreamingTargetRadius`, `StreamingIntegrityMode`.
  - `FallenPartsDestroyHeight`: Y threshold below which unanchored falling parts are destroyed.
  - `LuauTypeCheckMode`: Project-wide default type-check strictness (`Default`, `NoCheck`, `Nonstrict`, `Strict`).
  - `AuthorityMode` / `PlayerScriptsUseInputActionSystem` (`Enum.RolloutState`): Server authority and modern IAS defaults.
- **Pitfall:** Avoid dropping hundreds of scattered legacy `Script`s inside individual `Part`s in `Workspace`; prefer `CollectionService` tags + centralized server/client controllers.

### 2.2 `Players`
- **Purpose:** Holds connected runtime `Player` instances and fires lifecycle signals (`PlayerAdded`, `PlayerRemoving`, `CharacterAdded`).
- **Key Members:**
  - `Players.LocalPlayer`: Client-only reference to the local user (`nil` on server scripts).
  - `Players.CharacterAutoLoads`, `Player:LoadCharacterAsync()`, `Players.RespawnTime`, `Players.MaxPlayers`, `Players:GetPlayerFromCharacter(character)`.
  - `Players.BanningEnabled` with server moderation methods `BanAsync`, `UnbanAsync`, `GetBanHistoryAsync`.
- **Runtime Child Containers on Each `Player`:**
  - `PlayerGui` (receives `StarterGui` clones; client UI manipulation happens here, **not** by editing `StarterGui` for a single player)
  - `Backpack` (receives `StarterPack` clones + equipped/unequipped `Tool`s)
  - `StarterGear` (persists player-owned `Tool`s across respawns)
  - `PlayerScripts` (receives `StarterPlayerScripts` once per join)
- **Pitfall:** **NEVER** manually insert `Player` objects into `Players` in Studio Edit mode.

### 2.3 `Lighting`
- **Purpose:** Controls global illumination, time of day, skyboxes, atmosphere, and screen-wide post-processing.
- **Canonical Children:** `Sky`, `Atmosphere`, `Clouds` (or under `Terrain`), and global `PostEffect`s (`BloomEffect`, `ColorCorrectionEffect`, `ColorGradingEffect`, `SunRaysEffect`, `BlurEffect`, `DepthOfFieldEffect`).
- **Key Properties:** `ClockTime`, `GeographicLatitude`, `Brightness`, `Ambient`, `OutdoorAmbient`, `ColorShift_Top`, `FogStart`/`FogEnd` (legacy when `Atmosphere` is absent).
- **Security Note:** `Lighting.Technology` is `RobloxScriptSecurity` (read/write restricted at runtime for standard game scripts); configure lighting technology in Studio properties rather than mutating `Lighting.Technology` from runtime scripts.

### 2.4 `MaterialService`
- **Purpose:** Manages custom PBR materials and built-in material overrides across `BasePart`s and `Terrain`.
- **Key Members:**
  - `Use2022Materials`: `boolean` toggling updated built-in Roblox material appearances.
  - `MaterialVariant` children: Keyed uniquely by `(Name, BaseMaterial)` pairs with custom `ColorMap`, `NormalMap`, `RoughnessMap`, `MetalnessMap`, `StudsPerTile`.
  - `MaterialService:SetBaseMaterialOverride(material, name)` / `GetBaseMaterialOverride(material)`.
- **Pitfall:** Raw string override properties (e.g. `*Name`) are `RobloxEngineSecurity` — use `SetBaseMaterialOverride` / `GetBaseMaterialOverride` in Luau, and note that pairing legacy terrain with `MaterialVariant` overrides incurs a performance penalty.

### 2.5 `NetworkClient`
- **Inheritance:** `NetworkPeer` (`NotCreatable`, `Service`, **`NotReplicated`**).
- **Purpose:** Exists on the client to manage its live `ClientReplicator` session and connection diagnostics.
- **Key Events & Methods:**
  - `ConnectionAccepted(peer: string, replicator: Instance)` (`ClientReplicator`)
  - `ConnectionFailed(peer: string, code: number, reason: string)` (`Capabilities: Network`)
  - `SetOutgoingKBPSLimit(limit: number)`
- **Usage:** Read-only/diagnostic client instrumentation; never expect `NetworkClient` children to replicate to the server.

### 2.6 `ReplicatedFirst`
- **Purpose:** Replicates to connecting clients **once, immediately before** all other replicated containers (`ReplicatedStorage`, `Workspace`, `StarterGui`, etc.).
- **Primary Use:** Instant custom loading screens, initial branding, preloading essential startup UI assets (`ContentProvider:PreloadAsync`), and calling `ReplicatedFirst:RemoveDefaultLoadingScreen()` (note: Roblox automatically removes the default screen after a few seconds even if omitted).
- **Critical `WaitForChild` Pitfall:**
  - Because `ReplicatedFirst` executes *before* `ReplicatedStorage` or `Workspace` finishes replicating, objects outside `ReplicatedFirst` may still be `nil` when a `ReplicatedFirst` script starts.
  - Conversely, when `StreamingEnabled` is active, **never** block loading screen exit on unbounded `WaitForChild()` calls targeting world geometry — keep critical-path startup scripts non-blocking with `FindFirstChild` + `nil` guards or bounded timeouts.

### 2.7 `ReplicatedStorage`
- **Purpose:** Shared client + server storage replicated to **all** connected clients.
- **Canonical Contents:**
  - `Modules` / `Shared`: Pure, non-secret shared constants, types, enums, math helpers, and read-only public catalogs.
  - `Remotes`: `RemoteEvent`, `UnreliableRemoteEvent`, `RemoteFunction` (client -> server only; never `InvokeClient`).
  - `Inputs`: Canonical `InputContext` -> `InputAction` -> `InputBinding` hierarchy for the Input Action System (IAS).
  - `Assets` / `Prefabs`: Client-spawnable VFX, UI templates, and streamed/cloned visual models.
- **CRITICAL SECURITY RULE:**
  - **NEVER** store API secrets, admin passcodes, unreleased secret maps, server-side loot/drop formulas, or server-only `ModuleScript`s in `ReplicatedStorage`.
  - Exploiter tools dump every `ReplicatedStorage` descendant (including disabled `LocalScript`s and **unrequired `ModuleScript`s**). Keep server-only modules in `ServerScriptService` or `ServerStorage`.

### 2.8 `ServerScriptService`
- **Inheritance:** `Instance` (**`NotReplicated`**).
- **Purpose:** Secure server-only execution container. Nothing inside `ServerScriptService` ever leaves the server.
- **Canonical Contents:**
  - Single server bootstrapper `Script` (`Init` -> `Start` orchestration).
  - Server-only `ModuleScript` services (`Services/`, `Systems/`, `Data/`, `Security/`).
- **Critical Security Property:** `ServerScriptService.LoadStringEnabled` defaults to `false`. Keep it `false` to prevent arbitrary code injection (`loadstring()`) vulnerabilities.

### 2.9 `ServerStorage`
- **Inheritance:** `Instance` (**`NotReplicated`**).
- **Purpose:** Secure server-only storage for heavy maps, arenas, server-spawned NPC/weapon prefabs, and confidential server data tables. Keeping unspawned maps in `ServerStorage` avoids bloating initial client join memory and bandwidth.
- **CRITICAL RULE:** **`Script` instances placed inside `ServerStorage` do NOT execute!**
  - Only server `Script`s running in `ServerScriptService` (or server `Workspace` contexts) can `require()` `ModuleScript`s stored in `ServerStorage` or `:Clone()` prefabs from `ServerStorage` into `Workspace`.

### 2.10 `StarterGui`
- **Purpose:** Blueprint container whose direct `LayerCollector` children (`ScreenGui`, `BillboardGui`, `SurfaceGui`) are cloned into `Player.PlayerGui` when the player joins and on character spawn.
- **Critical Rules:**
  - `ScreenGui.ResetOnSpawn = false` **only** persists across respawns when the `ScreenGui` is a **direct child** of `StarterGui`. Nesting a `ScreenGui` inside a `Folder` in `StarterGui` breaks persistence (`ResetOnSpawn` behavior).
  - `StarterGui:SetCoreGuiEnabled(coreGuiType, enabled)` and `StarterGui:SetCore(...)` must run client-side (e.g., `PlayerScripts` / UI controller).
  - `ShowDevelopmentGui`, `ScreenOrientation`, `VirtualCursorMode` configure global UI defaults.
  - Keep HUD/modal UI logic modular in `StarterPlayerScripts` or co-located `Client` `RunContext` controllers rather than duplicating heavy scripts across UI templates.

### 2.11 `StarterPack`
- **Purpose:** Cloned into each player's `Player.Backpack` on join and on every character spawn.
- **Canonical Contents:** Default `Tool`s granted universally to every player (`StarterSword`, `Flashlight`).
- **Best Practice:** Give conditional, purchased, or role-specific tools dynamically on the server by cloning from `ServerStorage` into `player.Backpack` (one life) and `player.StarterGear` (persists across respawns within the session).

### 2.12 `StarterPlayer`
- **Purpose:** Configures default character physics, camera constraints, movement modes, and client script cloning behavior.
- **Subcontainers:**
  - `StarterPlayerScripts`: Cloned into `Player.PlayerScripts` **once per join** (survives character death/respawn). Put persistent client controllers, IAS binders, UI managers, and remote listeners here.
  - `StarterCharacterScripts`: Cloned into `Player.Character` **every character spawn** (destroyed on respawn). Put short-lived character-attached scripts here, or handle `CharacterAdded` cleanly from `StarterPlayerScripts`.
- **Special Optional Rig Templates:** `StarterCharacter` (`Model`) and `StarterHumanoid` (`Humanoid`) override default avatar rigs/humanoid defaults when placed directly inside `StarterPlayer`.
- **Key Properties:**
  - Movement & Camera locks: `DevComputerMovementMode`, `DevTouchMovementMode`, `DevComputerCameraMovementMode`, `DevTouchCameraMovementMode`, `DevCameraOcclusionMode`, `EnableMouseLockOption`.
  - Camera bounds & character options: `CameraMinZoomDistance`, `CameraMaxZoomDistance`, `AutoJumpEnabled`, `AvatarJointUpgrade`, `EnableDynamicHeads`, `LoadCharacterAppearance`, `LoadCharacterLayeredClothing`, `UserEmotesEnabled`.

### 2.13 `Teams`
- **Purpose:** Holds `Team` instances (`TeamColor: BrickColor`, `AutoAssignable: boolean`) to organize players into teams.
- **Engine Integrations:**
  - Groups players visually on the default PlayerList (`Leaderboard`) and tints character overhead names with `Team.TeamColor`.
  - New players automatically join the `AutoAssignable = true` team with the fewest members (or remain `Player.Neutral = true` if none are auto-assignable).
  - Integrates natively with `SpawnLocation` (`Neutral`, `TeamColor`, `AllowTeamChangeOnTouch`).
- **API Note:** Use `Teams:GetTeams()` to inspect configured teams. `Teams:RebalanceTeams()` is **deprecated** — implement custom team-balancing logic on the server.

### 2.14 `SoundService`
- **Purpose:** Configures global 3D audio physics, listener defaults, `SoundGroup` mixer buses, and audio API routing options.
- **Key Properties:**
  - Legacy spatial physics (`Sound` objects): `AmbientReverb`, `DistanceFactor`, `DopplerScale`, `RolloffScale`.
  - Modern Audio API & simulation: `AcousticSimulationEnabled`, `CharacterSoundsUseNewApi`, `DefaultListenerLocation`, `RespectFilteringEnabled` (must remain `true` so client-started sounds do not leak globally).
- **Modern Audio API Note:** Modern `AudioPlayer` -> `Wire` (`SourceInstance`, `TargetInstance`) -> `AudioEmitter` / `AudioDeviceOutput` pipelines are **not** affected by `SoundService.AmbientReverb` — attach an `AudioReverb` node inside the `Wire` graph instead.

### 2.15 `TextChatService` (+ `VoiceChatService`)
- **`TextChatService`:** Modern filtered chat service replacing legacy `Chat`.
  - Default channels (`TextChannel` inside `TextChannels`): `RBXGeneral`, `RBXSystem`, `RBXTeam[BrickColorName]`, `RBXWhisper:[UserId1]_[UserId2]`.
  - Customization: `TextChatCommand`, singleton configs (`ChatWindowConfiguration`, `ChatInputBarConfiguration`, `BubbleChatConfiguration`, `ChannelTabsConfiguration`), `CreateDefaultCommands`, `CreateDefaultTextChannels`, `ChatTranslationEnabled`.
  - Permissions & Filtering: `CanUserChatAsync(userId)`, `CanUsersChatAsync(fromId, toId)`, `CanUsersDirectChatAsync(requesterId, userIds)` (server-only checks for parental/privacy settings), `TextChatService:DisplayBubble(partOrChar, message)` (remember to filter custom player-entered strings through Roblox text filtering before displaying!). Note `ChatVersion` write access is `RobloxScriptSecurity`.
- **`VoiceChatService`:** Spatial voice chat coordinator.
  - `UseAudioApi = Enum.AudioApiRollout.Enabled` automatically provisions an `AudioDeviceInput` under each eligible `Player`, an `AudioEmitter` under `Player.Character`, and an `AudioListener` under `Workspace.CurrentCamera`.
  - Pairing `UseAudioApi = Enabled` with `EnableDefaultVoice = false` disables automatic spatial wiring while keeping `AudioDeviceInput` active for custom radio/team voice routing; when `UseAudioApi = Disabled`, `EnableDefaultVoice = false` disables voice completely.

---

## 3. Canonical Explorer Folder Scaffold

Use [`project_scaffold.luau`](../scripts/project_scaffold.luau) to idempotently create the clean baseline folder hierarchy (`ServerScriptService/{Services,Systems,Security}`, `ServerStorage/{Maps,Prefabs,Modules}`, `ReplicatedStorage/{Shared,Remotes,Inputs,Assets}`, `StarterGui`, `StarterPack`, `StarterPlayer/StarterPlayerScripts/{Controllers,Components}`, `StarterPlayer/StarterCharacterScripts`, `SoundService/SoundGroups`, `Workspace/{World,NPCs,Interactables}`). Always pass `isolatedRoot` when testing in Studio so existing place hierarchy stays untouched.

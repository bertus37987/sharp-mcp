# Game Elements, Streaming, Modern APIs & Built-In Skill Routing

This reference covers production patterns for streaming worlds, gameplay systems, modern Roblox APIs, and when to delegate to Roblox Studio's built-in `rbx-*` skills.

---

## 1. `StreamingEnabled` & `CollectionService` Tag Lifecycle

### Key Streaming Settings (`Workspace`)
- `Workspace.StreamingEnabled = true` streams 3D content dynamically based on distance and memory (note: streaming scopes **only** `Workspace`; `ReplicatedStorage` / `StarterGui` / etc. still replicate in full).
- `ModelStreamingBehavior`: `Enum.ModelStreamingBehavior.Improved` (recommended modern default over `Legacy`).
- `StreamingMinRadius` (recommended `64`) < `StreamingTargetRadius` (recommended `1024`).
- `StreamOutBehavior`: `LowMemory` (frees only under pressure) vs `Opportunistic` (aggressively reclaims far regions).
- `StreamingIntegrityMode`: e.g. `PauseOutsideLoadedArea` pauses client simulation (`Player.GameplayPaused`) when a player enters an unloaded area; customize via `GuiService:SetGameplayPausedNotificationEnabled(false)`.
- **Per-Model Overrides (`Model.ModelStreamingMode`):**
  - `Nonatomic` (parts stream independently — fragile if scripts expect complete rigs!)
  - `Atomic` (all descendants replicate/stream out together; pair with `Workspace.PersistentLoaded` or `Model` signals)
  - `Persistent` (always replicated to all players; **must** stay small/critical-only such as round arenas or spawn hubs)
  - `PersistentPerPlayer` (targeted persistence via `model:AddPersistentPlayer(player)` / `RemovePersistentPlayer(player)`)
- **Explicit Stream Requests:** `Player.ReplicationFocus`, `Player:AddReplicationFocus(part)`, `player:RequestStreamAroundAsync(position, timeout?)` before teleporting a character across the map.

### Critical Streaming Pitfalls
1. **Stream-Out Re-Parents to `nil`:** Streamed-out instances move to `nil` (`ChildRemoved` / `DescendantRemoving` fire) and lose any client-only property edits.
2. **CRITICAL `CollectionService` Tag Trap:** `CollectionService` replicates **all tags on an instance together as a set**. Whenever the server modifies tags — **or an instance streams out and streams back in** — server tags overwrite any client-local tags added to that instance! Never store durable client state inside local `CollectionService` tags on replicated instances; use client-local tracking tables or server-authoritative `Attribute`s (`GetAttributeChangedSignal`).
3. **Critical-Path Startup Rule:** In `ReplicatedFirst` or `StarterPlayerScripts` code running before the loading screen finishes, use `FindFirstChild(...)` + `nil` guards — **NEVER** block on unconditional `WaitForChild()` against world geometry.
4. **Workspace Configuration Exemption & Raycast Range:** `workspace.Configuration` can hold non-spatial config folders without streaming loss; keep gameplay raycasts reasonably bounded (`<= 500` studs).
5. **Defensive `OnClientEvent`:** Wrap `OnClientEvent` handlers touching `Workspace` instances in `pcall` + nil/ancestry checks in case target parts streamed out mid-packet.

---

## 2. Core Game Elements

### 2.1 `Tool` & Weapon Systems
- **Properties:** `RequiresHandle` (boolean; set `false` for invisible/fist/custom-viewmodel tools), `CanBeDropped`, `Enabled`.
- **Events:** `Activated`, `Deactivated`, `Equipped`, `Unequipped`.
- **Server-Authoritative Pattern:**
  - Client handles input/VFX prediction + sends aim ray / fire intent via `RemoteEvent` (validated by `SafeRemoteGateway`).
  - Server owns ammo, cooldown timers, character alive state, equipped tool check (`character:FindFirstChildOfClass("Tool")`), origin distance from `Head`/`HumanoidRootPart`, and server raycast (`Workspace:Raycast`) before applying `Humanoid:TakeDamage`.

### 2.2 NPCs & `PathfindingService`
- Create a reusable path specification with `PathfindingService:CreatePath({ AgentRadius = 2, AgentHeight = 5, AgentCanJump = true, AgentCanClimb = false, WaypointSpacing = 4, Costs = { Water = 20 } })`.
- Call `local ok = pcall(function() path:ComputeAsync(startPos, targetPos) end)` and verify `ok and path.Status == Enum.PathStatus.Success` before reading `path:GetWaypoints()`.
- Listen to `path.Blocked:Connect(function(blockedWaypointIndex) ... end)` to recompute dynamically when obstacles move.
- Use `PathfindingModifier` inside obstacle/zone parts (`PassThrough`, `Label`) rather than rebuilding collision geometry.
- Always set `npcRoot:SetNetworkOwner(nil)` so nearby clients do not hijack NPC physics!

### 2.3 Persistence vs Live Tuning (`DataStoreService` vs `ConfigService`)
| Use Case | Service | Rules & Limits |
|---|---|---|
| Player saves, currencies, inventories, leaderboards | `DataStoreService` (`GetDataStore`, `GetOrderedDataStore`) | Server-only (`NotReplicated`); prefer `UpdateAsync` over `SetAsync` to avoid race overwrites; monitor `GetRequestBudgetForRequestType`; save cleanly on `PlayerRemoving` + `game:BindToClose` |
| Tunable constants (boss HP, prices, drop rates, feature flags, A/B tests) | `ConfigService` (`GetConfigAsync`, `GetConfigForPlayerAsync`) | Server-only; live updates without restarting servers; limit **1,000 active configs**; ~**5-minute** propagation; A/B experiment enrollment is **sticky** after first `ConfigSnapshot:GetValue(key)`; watch `UpdateAvailable` + `Refresh()` + `GetValueChangedSignal(key)`; use `SetTestingValue`/`ClearTestingValue` in Studio; wrap calls in `pcall` |

### 2.4 Modern Input Action System (IAS)
Use Roblox's **Input Action System** (`InputContext` -> `InputAction` -> `InputBinding`) instead of legacy `UserInputService` / `ContextActionService` boilerplate for new controls:
- **Hierarchy:**
  - `InputContext`: Groups modal bindings (`Enabled: boolean`, `Priority: number` [default `1000`], `Sink: boolean` stops lower-priority contexts from receiving matched keys).
  - `InputAction`: Semantic action (`Type: Enum.InputActionType.{Bool, Direction1D, Direction2D, Direction3D, ViewportPosition}`, `Enabled`, `PreferredBinding`), signals `Pressed`, `Released`, `StateChanged`, and method `:GetState()`.
  - `InputBinding`: Physical binding (`Type: Enum.InputBindingType.{Automatic, Scriptable}`, `KeyCode` — note left click is **`Enum.KeyCode.MouseLeftButton`**, **NOT** `MouseButton1`!, `UIButton` for mobile touch buttons, directional composites `Up`/`Down`/`Left`/`Right`/`Forward`/`Backward`, analog thresholds `PressedThreshold`/`ReleasedThreshold`, `Scale`).
  - `InputActionLabel`: Binds to an `InputAction` to display live `ResolvedText` and `ResolvedImageContent` matching the player's current input device!
- **Placement:** Keep canonical `InputContext`s in `ReplicatedStorage/Inputs` (never register directly from `Starter*` templates). Enable `Workspace.PlayerScriptsUseInputActionSystem = Enum.RolloutState.Enabled` for modern default character controls.

### 2.5 `ProximityPrompt` Interactions
- Configure `ActionText` ("Open"), `ObjectText` ("Vault Door"), `HoldDuration` (seconds), `MaxActivationDistance` (default `10` studs), and `RequiresLineOfSight` (default `true`).
- Connect interaction rewards to `ProximityPrompt.Triggered:Connect(function(player) ... end)` on the **server** (`Triggered` enforces server-side distance validation).
- Treat `PromptButtonHoldBegan` and `TriggerEnded` as UX feedback hooks rather than trusted grants, because they do not enforce the same strict server distance check as `Triggered`.

---

## 3. Decision Routing to Built-In Studio `rbx-*` Skills

When executing inside Roblox Studio (MCP/Assistant), invoke the specialized built-in skill **before** authoring subsystem code:

| Task / Symptom | Built-In Studio Skill | What It Covers |
|---|---|---|
| Keyboard, mouse, gamepad, touch controls, keybinds, CAS/UIS migration | `rbx-input-action-system` | IAS (`InputContext`/`InputAction`/`InputBinding`), `InputActionManager`, migration from UIS/CAS |
| Enabling `StreamingEnabled`, fixing `WaitForChild` stalls or stream-out bugs | `rbx-convert-to-streaming` | `ApplyRecommendedStreamingSettings()`, 9-step audit, anti-patterns AP#1–AP#13 |
| Live-ops tuning, feature flags, A/B experiments | `rbx-configs-experimentation` | `ConfigService`, `GetConfigAsync`/`GetConfigForPlayerAsync`, Studio overrides |
| Scene memory, unparented instance leaks, instance composition | `rbx-scene-analysis` | `SceneAnalysisService` rendering/memory/animation/audio composition analysis |
| Growing Luau RAM, leaking tables/closures/threads | `rbx-luau-heap-profiling` | Luau heap snapshots and retention-path leak tracing (Play mode) |
| CPU/GPU framerate spikes, slow loops | `rbx-perf-profiling` | MicroProfiler (`LibMP`) frame-time bottleneck analysis |
| Testing 3G/4G/Wi-Fi latency, jitter, packet loss, client-server desync | `rbx-network-simulator` | `settings().Network` presets and lag/desync playtest measurement |
| Economy, funnel, and custom game telemetry | `rbx-instrument-analytics` | `AnalyticsService` event plan and centralized analytics wrapper |
| Auditing Developer Product `ProcessReceipt` code | `rbx-process-receipt-misuse` | Receipt persistence, `PurchaseGranted` ordering, out-of-experience blockers |
| Writing/running `ModuleScript` unit tests or live Studio debugging | `rbx-unit-test` / `rbx-debug` | Test suites and programmatic breakpoints/thread inspection |

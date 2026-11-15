# Client-Server Security, RunContext & Networking

Roblox's client runtime executes on hardware fully controlled by the player. Treat **every** client-supplied signal, property on client-owned assemblies, and client-visible asset as adversarial.

---

## 1. "Never Trust the Client" & Threat Model

### What Exploiters Control on the Client
- Any running `LocalScript`, `Script` with `RunContext.Client`, and any **`ModuleScript` located in a replicated container** (`ReplicatedStorage`, `Workspace`, `ReplicatedFirst`, `StarterGui`, `StarterPack`, `StarterPlayer`, `Teams`, `SoundService`) — **even if disabled or never `require()`d!** Exploiter dumpers decompile all replicated bytecode.
- Arguments passed to `RemoteEvent:FireServer(...)`, `UnreliableRemoteEvent:FireServer(...)`, and `RemoteFunction:InvokeServer(...)`.
- Local character `HumanoidRootPart` transform, velocity, and physics state for any `BasePart` whose network owner is that client (including `Inf` / `NaN` velocity injection).
- Client memory, client-only `Attribute`s / tags, `ProximityPrompt` client hold timings (`PromptButtonHoldBegan` / `TriggerEnded` lack the server distance check enforced by `Triggered`).

### Non-Negotiable Security Rules
1. **Separate Server and Client Storage:** Never put server secrets, API keys, reward tables, unreleased maps, or mixed `if RunService:IsServer() then ... end` logic inside `ReplicatedStorage` or `Workspace`. Keep server modules inside `ServerScriptService` or `ServerStorage` (`NotReplicated`).
2. **Keep `LoadStringEnabled = false`:** Leave `ServerScriptService.LoadStringEnabled = false` in production to eliminate arbitrary string execution vectors.
3. **Validate Everything Server-Side ("Intent, Not Outcome"):** Clients send **requests** ("fire toward direction X", "buy item Y", "equip slot 2"), never **results** ("deal 999 damage to Player B", "grant 500 gold").
   - Validate identity (`player` from `OnServerEvent`, never a trusted `userId` parameter), `typeof()`, finite numbers (`not (x ~= x)` and `math.abs(x) < math.huge`), bounded string lengths, distance / line-of-sight (`<= 500` stud reasonable raycast limits), cooldowns, inventory ownership, and team/state permissions.
4. **Lock Critical Physics Ownership:** Call `rootPart:SetNetworkOwner(nil)` on server-controlled projectiles, boss NPCs, elevators, vaults, and hazard platforms so clients cannot freeze or fling them. Use leaky-bucket velocity/distance checks on server-validated player movement (or evaluate `Workspace.AuthorityMode` Server Authority + `RunService.Misprediction`).
5. **Subplace Teleport Security:** Client-side teleport payloads can be forged; rely on `TeleportOptions:SetTeleportData` / `GetJoinData` **within the universe** alongside server-validated persistence (`DataStoreService` / `MemoryStoreService`) rather than trusting client-passed state.

---

## 2. `RunContext` Rules (`Legacy` vs `Server` vs `Client`)

`Script.RunContext` (`Enum.RunContext`) decouples *where* a script runs from *which class* it uses:

| `RunContext` | Where It Runs | Security & Placement Rule |
|---|---|---|
| `Legacy` | Server VM only when under `Workspace` or `ServerScriptService` | Prefer explicit modular architecture; **never** place in `ServerStorage` (does not run) |
| `Server` | Runs on the Server VM wherever loaded (except inactive containers like `ServerStorage`) | **STILL place only inside `ServerScriptService`**, never `ReplicatedStorage`/`Workspace`, so client never sees the container structure or source |
| `Client` | Runs on each Client VM wherever replicated (`ReplicatedFirst`, `StarterGui`, `StarterPlayerScripts`, `Workspace`, `ReplicatedStorage`) | Zero server trust; use alongside `LocalScript` for self-contained client behavior |

- Keep `LocalScript` or `RunContext.Client` controllers inside `StarterPlayerScripts` (persistent) or `StarterGui` (per-UI), and keep **all** authoritative scripts inside `ServerScriptService`.

---

## 3. Networking Primitives & Serialization

### Choosing the Right Remote Class

| Primitive | Delivery & Ordering | Limits & Edge Cases | Recommended Use |
|---|---|---|---|
| `RemoteEvent` | Reliable, ordered per client | Queued if receiver hasn't connected yet (bounded engine queue warns on overflow) | Combat intents, purchases, UI state sync, inventory mutations |
| `UnreliableRemoteEvent` | Unreliable, **unordered**, not re-sent | **1,000-byte hard payload cap**; silently drops if throttled or no handler connected | High-frequency cosmetic VFX, aim look vectors, ephemeral footsteps |
| `RemoteFunction` | Synchronous request/response (`InvokeServer`) | **NEVER call `InvokeClient()` in production**: client errors propagate to server, disconnect throws, unresponsive/cheating client hangs calling thread forever | Sparingly for client-initiated server queries; prefer `RemoteEvent` request/response pairs |

### Engine Serialization Traps (Every Remote Call)
- **No mixed tables:** A table containing both array indices (`1, 2, 3`) and dictionary keys (`foo = "bar"`) drops data during replication! Keep arrays contiguous (`1..#arr`) and dictionaries string-keyed.
- **No sparse arrays / `nil` holes:** `{ "a", nil, "c" }` truncates at the first `nil` hole.
- **Non-string keys coerce:** Numeric dictionary keys `{ [10] = "x" }` serialize to `{ ["10"] = "x" }`.
- **Metatables & functions strip:** Metatables are removed and functions serialize to `nil`.
- **Non-replicated `Instance` references become `nil`:** Passing an instance parented to `ServerStorage` to a client (or a client-created `Part` to the server) delivers `nil` on the receiving side.
- **No shared table identity:** Each remote call deep-copies tables across the boundary.

---

## 4. Schema Validation & Token-Bucket Rate Limiting

Every `RemoteEvent` / `UnreliableRemoteEvent` boundary should pass through a shared gateway (`SafeRemoteGateway` in [`scripts/safe_remote_gateway.luau`](../scripts/safe_remote_gateway.luau)):

1. **Central Registry:** Put remote instances under `ReplicatedStorage/Remotes` and register handlers from one server gateway rather than scattering loose `.OnServerEvent:Connect(...)` callbacks across dozens of scripts.
2. **Typed Runtime Schema:** Validate exact argument count, primitive/Instance types (`FieldValidator`), finite numeric bounds (`min`, `max`, reject `NaN` and `±math.huge`), string byte/length caps (`maxLength`), integer flags, and nested flat dictionaries (`no mixed tables`, bounded key count/depth).
3. **Per-Player Token Bucket:** Assign each route `{ capacity: number, refillPerSecond: number }`. Burst spam drains tokens and drops excess packets cleanly before touching game logic; prune player buckets on `Players.PlayerRemoving`.
4. **Defensive Client Receivers:** Wrap `OnClientEvent` handlers touching 3D geometry in `pcall` + `IsDescendantOf(workspace)` guards when `Workspace.StreamingEnabled = true`, because server-referred instances can stream out before or during callback delivery.

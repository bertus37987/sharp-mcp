# Sharp Critical Audit Rules Catalog

Reference catalog for `CriticalAuditEngine` (`sharp_critical_audit`) and `GamePlanner` (`sharp_game_plan`) stage-gate thresholds.

---

## 1. Verdict & Severity Scoring Model

| Verdict | Criteria | Gate Effect |
|---|---|---|
| `SHIP` | `0 BLOCKER`, `0 CRITICAL`, `0 MAJOR`, `score >= 85` | Clears all stage gates including `S7` Release-Hardening |
| `FIX_FIRST` | `0 BLOCKER`, `< 3 CRITICAL` (`CRITICAL > 0` or `MAJOR > 0`), `50 <= score < 85` | Passes non-release stages only if `CRITICAL == 0` and `MAJOR <= stage_max_major` |
| `REJECT` | `BLOCKER >= 1` OR `CRITICAL >= 3` OR `score < 50` | Hard-blocks every stage gate (`S0`..`S7`) |

Penalty weights from baseline score `100`:
- `BLOCKER` (`-30`, caps score at `<= 49`)
- `CRITICAL` (`-15`)
- `MAJOR` (`-7`)
- `MINOR` (`-2`)
- `INFO` (`0`)

---

## 2. Audit Modes

| Mode | Description |
|---|---|
| `static` | Tokenizer-based offline Luau analyzer (ignores comments and strings, handles Luau backtick `{expr}` interpolations) combined with GUI, animation, world, plan/state, and cross-check rules. |
| `live` | Compiles Studio read-only audit + world/GUI telemetry + bounded script inventory (`LuauAuditSnapshotEngine.compile_critical_audit_luau`) and merges live DataModel results with static checks. |
| `challenge` | Adversarial pre-mortem across **100 concurrent players**, **mobile phone**, and **after rejoin / shutdown**, highlighting risks confirmed in project inputs. |
| `gate` | Evaluates stage-specific exit thresholds (`0 BLOCKER`, `0 CRITICAL`, bounded `MAJOR`, and `SHIP` for `S7`) and reports exact `blocking_reasons`. |

---

## 3. Rules Reference by Domain

### A. Luau Security, Economy, Performance, Memory & Types (`luau`)

| Rule ID | Severity | Domain | What It Flags | Auto-Fixable |
|---|---|---|---|---|
| `LUAU-SEC-001` | `BLOCKER` | `luau` | `RemoteFunction:InvokeClient(...)` hang/error exploit vector | No |
| `LUAU-SEC-002` | `BLOCKER` | `luau` | `loadstring(...)`, `getfenv(...)`, `setfenv(...)` dynamic code/env escape | No |
| `LUAU-SEC-003` | `BLOCKER` | `luau` | `RemoteEvent.OnServerEvent` / `OnServerInvoke` missing argument type/bounds validation | No |
| `LUAU-SEC-004` | `CRITICAL` | `luau` | `RemoteEvent.OnServerEvent` validates types but lacks per-player rate limiting | No |
| `LUAU-SEC-005` | `BLOCKER` | `luau` | Client-trusted values (`damage`, `amount`, `gold`, `price`, `userId`, unverified `TakeDamage`) | No |
| `LUAU-ECO-001` | `BLOCKER` | `luau` | Non-idempotent `MarketplaceService.ProcessReceipt` missing `PurchaseId` tracking or `pcall`/`NotProcessedYet` | No |
| `LUAU-ECO-002` | `CRITICAL` | `luau` | Unprotected `DataStoreService` / `MarketplaceService` async calls outside `pcall`/`xpcall` | No |
| `LUAU-ECO-003` | `CRITICAL` | `luau` | `DataStoreService` usage without `game:BindToClose(...)` shutdown flush | No |
| `LUAU-PERF-001` | `CRITICAL` | `luau` | Deprecated globals `wait(...)`, `spawn(...)`, `delay(...)` instead of `task.*` | Yes |
| `LUAU-PERF-002` | `CRITICAL` | `luau` | Unbounded `while`/`repeat` polling loops using `task.wait`/`wait` instead of signals | No |
| `LUAU-PERF-003` | `CRITICAL` | `luau` | Unbounded `Instance.new(...)` inside loops or `RunService` per-frame hooks without pooling | No |
| `LUAU-PERF-004` | `CRITICAL` / `MAJOR` | `luau` | `.Touched:Connect(...)` spam (`CRITICAL` without debounce, `MAJOR` with debounce vs spatial query) | No |
| `LUAU-PERF-005` | `CRITICAL` / `MAJOR` | `luau` | `Debris:AddItem(...)` misuse (`CRITICAL` inside loops/per-frame hooks, `MAJOR` elsewhere vs pooling) | No |
| `LUAU-PERF-006` | `BLOCKER` | `luau` | Infinite non-yielding `while true do` loop without yield or `break`/`return` | No |
| `LUAU-MEM-001` | `CRITICAL` | `luau` | Unmanaged `:Connect(...)` inside loops or nested `PlayerAdded`/`CharacterAdded` callbacks | No |
| `LUAU-MEM-002` | `MAJOR` | `luau` | `Players.PlayerAdded` connected without `Players.PlayerRemoving` cleanup | No |
| `LUAU-TYPE-001` | `CRITICAL` / `MAJOR` | `luau` | `--!nocheck` (`CRITICAL`) or missing `--!strict` directive (`MAJOR`) | Yes |
| `LUAU-STREAM-001` | `MAJOR` | `luau` | Unbounded `WaitForChild(name)` without timeout inside `ReplicatedFirst` or `OnClientEvent` | No |
| `LUAU-ARCH-002` | `BLOCKER` | `luau` | Executable `.server.luau` Script placed inside `ServerStorage` | No |
| `LUAU-ARCH-003` | `BLOCKER` | `luau` | Server-only APIs (`DataStoreService`, `ProcessReceipt`, `GetSecret`) inside replicated paths | No |

### B. GUI & Anti-Slop Rules (`gui`)

| Rule ID | Severity | Domain | What It Flags | Auto-Fixable |
|---|---|---|---|---|
| `GUI-SAFE-001` | `CRITICAL` | `gui` | Interactive `ScreenGui` using `ScreenInsets=None` (overlaps Topbar / notch) | Yes |
| `GUI-SAFE-002` | `MAJOR` | `gui` | Duplicate `DisplayOrder` across `ScreenGui` instances | Yes |
| `GUI-SAFE-003` | `BLOCKER` / `MAJOR` | `gui` | `ZIndexBehavior ~= Sibling` (`BLOCKER` if `CanvasGroup` present) | Yes |
| `GUI-TOUCH-001` | `BLOCKER` | `gui` | Interactive `GuiButton`/`TextBox` smaller than `44x44` px | Yes |
| `GUI-CONTRAST-001` | `CRITICAL` | `gui` | WCAG contrast ratio `< 4.5:1` (text) or `< 3.0:1` (large text/icons) | Yes |
| `GUI-MOBILE-001` | `MAJOR` | `gui` | Interactive control enters mobile bottom-left thumbstick or bottom-right jump zone | No |
| `GUI-PERF-001` | `CRITICAL` | `gui` | `CanvasGroup` count `> 6` or `CanvasGroup` nested inside a `ScrollingFrame` | No |
| `GUI-TEXT-001` | `MAJOR` | `gui` | `TextScaled = true` without a `UITextSizeConstraint` child | Yes |
| `GUI-SLOP-*` | `CRITICAL` / `MAJOR` | `gui` | Ingested anti-slop defects from `design_lint` JSON (flat buttons, low hue variety, etc.) | Varies |

### C. Animation Rules (`animation`)

| Rule ID | Severity | Domain | What It Flags | Auto-Fixable |
|---|---|---|---|---|
| `LUAU-ANIM-001` | `CRITICAL` | `animation` | Deprecated `Humanoid:LoadAnimation(...)` instead of `Animator:LoadAnimation(...)` | Yes |
| `LUAU-ANIM-002` | `CRITICAL` | `animation` | `:LoadAnimation(...)` inside loops/input/equip callbacks without track caching | No |
| `ANIM-SEAM-001` | `MAJOR` | `animation` | Looping clip start-vs-end pose delta exceeds seam tolerance | Yes |
| `ANIM-PRIO-001` | `MAJOR` | `animation` | Missing or invalid `AnimationPriority` | Yes |
| `ANIM-PRIO-002` | `MAJOR` | `animation` | Combat/action clip using `Core` or `Idle` priority | Yes |
| `ANIM-PRIO-003` | `MAJOR` | `animation` | Every clip crammed onto `Action4`, breaking animation layering | No |

### D. World & Performance Rules (`world`)

| Rule ID | Severity | Domain | What It Flags | Auto-Fixable |
|---|---|---|---|---|
| `WORLD-BUDGET-001` | `CRITICAL` | `world` | `Workspace` part count exceeds `plan.asset_budget.max_workspace_parts` | No |
| `WORLD-COL-001` | `MAJOR` | `world` | Excessive `PreciseConvexDecomposition` MeshParts/Unions (`> 10`) | Yes |
| `WORLD-STREAM-001` | `CRITICAL` | `world` | `StreamingEnabled = false` on worlds exceeding 1,500 parts | No |
| `WORLD-PHYS-001` | `MAJOR` | `world` | Excessive unanchored `BasePart`s (`> 25`) without physics ownership lock | No |
| `WORLD-SPAWN-001` | `CRITICAL` | `world` | Zero `SpawnLocation` instances in `Workspace` | No |

### E. Plan, State & Cross-Checks (`plan`, `cross_check`)

| Rule ID | Severity | Domain | What It Flags | Auto-Fixable |
|---|---|---|---|---|
| `PLAN-001` | `BLOCKER` | `plan` | Missing or empty `plan.json` in project directory | No |
| `PLAN-002` | `BLOCKER` | `plan` | Stage gates skipped or `S3`/`S5`/`S6` progressed before MVP (`S0`-`S2` + `S4.1`) passes | No |
| `PLAN-003` | `CRITICAL` | `plan` | Required asset for a completed stage missing from `asset_manifest.json` | No |
| `PLAN-004` | `MAJOR` | `plan` | Version drift between `game_state.json`, `plan_history.json`, snapshots, or `SharpAssetRegistry.luau` | Yes |
| `XCHK-001` | `CRITICAL` | `cross_check` | Plan declares completed system/feature that no active domain or scanned Luau code implements | No |

### F. Live Bridge & Challenge Rules (`luau`, `gui`, `world`, `challenge`)

- `LIVE-SEC-*` / `LIVE-ARCH-*` / `LIVE-GUI-*` / `LIVE-WORLD-*`: Converted from live Studio `ArchitectureSecurityAudit`, `audit_gui.luau`, and `audit_environment.luau` outputs.
- `CHAL-100P-01..03`, `CHAL-PHN-01..03`, `CHAL-REJ-01..03`: Skeptic stress-test probes across 100 concurrent players, mobile phone constraints, and rejoin/shutdown recovery.

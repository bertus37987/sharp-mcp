# Luau Language, Task Scheduler, Frame Hooks & Parallel Luau

Roblox runs **Luau** (gradually typed, bytecode-compiled, sandboxed descendant of Lua 5.1) augmented by Roblox's task scheduler, `RunService` step pipeline, and `Actor`-based multithreading.

---

## 1. Strict Type Checking & Type System

Add a directive on line 1 of every script/module, or set project default via `Workspace.LuauTypeCheckMode`:

| Directive | Behavior | When to Use |
|---|---|---|
| `--!strict` | Full static inference + flags type mismatches, nil risks, and unknown fields | Default for all new `ModuleScript`s and core game services |
| `--!nonstrict` | Checks only explicit annotations; leaves dynamic tables loosely typed | Transitional legacy modules |
| `--!nocheck` | Disables type checking in the file | Generated binary/data blobs only |

### Essential Luau Type Syntax
```luau
--!strict
export type PlayerId = number
export type Role = "Admin" | "Moderator" | "Player" -- Literal union

export type RateLimitConfig = {
	capacity: number,
	refillPerSecond: number,
}

-- Generic dictionary / array helpers
export type Result<T, E> = { ok: true, value: T } | { ok: false, error: E }

-- Variadic & function types
type Validator = (value: unknown) -> (boolean, string?)
type LogFn = (level: "INFO" | "WARN", ...string) -> ()

-- Canonical typed OOP table + metatable pattern
local Inventory = {}
Inventory.__index = Inventory

export type Inventory = typeof(setmetatable({} :: {
	ownerId: number,
	items: { [string]: number },
}, Inventory))

function Inventory.new(ownerId: number): Inventory
	local self = setmetatable({
		ownerId = ownerId,
		items = {},
	}, Inventory)
	return self
end
```

- Use the type assertion operator `expr :: TargetType` sparingly to refine `unknown` or `Instance` lookups (`local root = character:FindFirstChild("HumanoidRootPart") :: BasePart?`). Never abuse `:: any` to hide validation gaps at network boundaries.

---

## 2. Modern Luau Idioms & Engine Libraries

| Feature | Idiom / Example | Avoid |
|---|---|---|
| Generalized iteration | `for key, value in dictionary do` and `for index, item in array do` | `pairs(...)` / `ipairs(...)` boilerplate |
| Skip iteration | `if not entry.Active then continue end` | Deeply nested `if ... else` pyramids |
| Compound assignment | `score += delta`, `bufferText ..= line` | `score = score + delta` |
| String interpolation | `` `Player {player.Name} scored {points}` `` | Multi-part `..` concatenation chains |
| Immutability | `table.freeze(CONFIG)` / `local copy = table.clone(defaults)` | Mutating shared config tables across modules |
| Zero-alloc binary IO | `buffer.create(bytes)`, `buffer.writeu16(b, 0, val)`, `buffer.readu16(b, 0)` | Giant string packs or nested table arrays for packed binary packets |
| Native codegen | `--!native` at file top or `@native` above hot math/buffer functions | Placing `--!native` on yielding remote/UI glue (zero gain + compile cost) |

### `buffer` Key Facts
- `buffer` offsets are **0-based** (`0 .. buffer.len(b) - 1`), unlike 1-based Luau arrays.
- Uses **little-endian** integers (`i8`/`u8`, `i16`/`u16`, `i32`/`u32`) and IEEE floats (`f32`/`f64`).
- `buffer` values replicate across `RemoteEvent`s when passed explicitly, making them ideal for compact coordinate/voxel streams within `UnreliableRemoteEvent`'s 1,000-byte budget.

---

## 3. Modern Task Scheduler (`task` Library)

Roblox **deprecated** global `wait()`, `spawn()`, `delay()`, and lowercase `Wait()` — they throttle unpredictably at 30 Hz and can delay indefinitely under load. **Always** use the `task` library:

| Function | Behavior | Use Case |
|---|---|---|
| `task.wait(seconds?)` | Yields current thread until at least `seconds` elapsed; resumes in `Heartbeat` step | Frame-synced waits, polling fallbacks (prefer event signals over loops!) |
| `task.spawn(fnOrThread, ...)` | Immediately executes `fnOrThread` synchronously until its first yield | Starting an independent coroutine right now |
| `task.defer(fnOrThread, ...)` | Queues `fnOrThread` for the **end of the current resumption cycle**, preserving serial/parallel phase | Avoiding re-entrancy hazards inside signals/destruction handlers |
| `task.delay(seconds, fnOrThread, ...)` | Schedules `fnOrThread` after `seconds` without blocking the caller | Cooldown resets, timed cleanup |
| `task.cancel(thread)` | Cancels a scheduled or suspended `thread` cleanly | Aborting pending timers on cleanup/disconnect |

---

## 4. `RunService` Step Hooks & Runtime Context

### Context Guards
Always check runtime environment cleanly inside shared `ModuleScript`s:
- `RunService:IsServer()` / `RunService:IsClient()`: Execution side (`IsServer` + `IsClient` are both `true` in Edit-mode Play Solo? Wait: in Play Solo, server and client run in separate VMs — `IsServer()` is `true` only on server VM, `IsClient()` only on client VM; in Studio Edit mode before Play, **both `IsStudio()` and `IsEdit()` are `true`**, while `IsRunning()` is `false`).
- `RunService:IsEdit()` / `RunService:IsRunning()` / `RunService:IsRunMode()`: Guard Editor plugin / Command Bar helpers vs live Play loops.

### Canonical Frame Order (Client & Server)
```
Frame Start
  1. [Client only] PreRender(deltaTimeRender)       -- Replaces deprecated RenderStepped; camera/HUD before GPU draw
                   BindToRenderStep(name, prio, fn) -- Deterministic camera priority (Enum.RenderPriority)
  2. PreAnimation(deltaTimeSim)                     -- Adjust animation weights/speeds before joints solve
     BindToAnimation / BindToAnimationParallel
  3. PreSimulation(deltaTimeSim)                    -- Replaces deprecated Stepped; apply forces/velocity pre-physics
     BindToSimulation / BindToSimulationParallel
  4. Physics Solver Step(s)                         -- May sub-step at higher frequency
  5. PostSimulation(deltaTimeSim)                   -- Read/adjust final physics state post-solve
  6. Heartbeat(deltaTime)                           -- Game systems, periodic updates, queued `task.*` resumes
  7. Network Replication Send/Receive
```
- Also available when Server Authority is enabled: `RunService.Misprediction(time, instances, stats)` for telemetry on client-predicted vs server-authoritative property/attribute divergence.

---

## 5. Parallel Luau (`Actor` + `SharedTable`)

Roblox achieves true multi-core parallelism by sharding execution across **`Actor`** containers (each `Actor` runs its own isolated Luau VM slice).

### Execution & Ownership Rules
1. Every `Script` / `LocalScript` associates with its **closest ancestor `Actor`** (`instance:GetActor()`). Scripts under the **same** `Actor` run serially with respect to each other; scripts under **different** `Actor`s can run concurrently on worker threads.
2. **Entering & Leaving Parallel Execution:**
   - Preferred event hook: `signal:ConnectParallel(callback)` starts directly in the parallel phase.
   - Inline toggle: `task.desynchronize()` switches to parallel; `task.synchronize()` returns to serial. Calling `task.synchronize()` inside a serial context yields/returns cleanly, and `task.desynchronize()` requires an ancestor `Actor` to actually unlock multi-core parallel execution.
3. **CRITICAL `require()` RESTRICTION:**
   - **NEVER call `require()` during desynchronized parallel execution.** Always `require()` all `ModuleScript`s in the serial phase *before* calling `task.desynchronize()` or using `ConnectParallel`.
4. **Thread Safety Levels:**
   - Only `Read Parallel` (e.g., spatial queries/property reads) and `Safe` / `Local Safe` APIs may be touched while desynchronized.
   - `Unsafe` operations (creating `Instance`s, setting `.Parent`, mutating `Workspace` properties, firing `RemoteEvent`s) **must** wait until after `task.synchronize()`.

### Inter-Actor Communication
- **Actor Messaging:**
  - `actor:SendMessage(topic: string, ...)` posts asynchronously to scripts inside `actor`.
  - `actor:BindToMessage(topic, fn)` (serial) / `actor:BindToMessageParallel(topic, fn)` (parallel).
- **`SharedTable` & `SharedTableRegistry`:**
  - Stores cross-actor primitives (`boolean`, `number`, `string`, `Vector3`, nested `SharedTable`s — **not** regular Luau tables, functions, `Instance`s, or raw `buffer`s).
  - Use `SharedTable.increment(st, key, delta)` for lock-free atomic counters and `SharedTable.cloneAndFreeze(st)` for read-only snapshots.
  - Register globally via `SharedTableRegistry:SetSharedTable(name, st)` and retrieve via `SharedTableRegistry:GetSharedTable(name)`.

---

## 6. Modular Single-Script Lifecycle & Cleanup

Instead of placing dozens of independent `Script`s inside world `Part`s:
1. Run one bootstrapper `Script` in `ServerScriptService` and one bootstrapper client controller in `StarterPlayerScripts`.
2. Require feature `ModuleScript`s (note: `ModuleScript` executes **once per Luau VM** and caches its return value; circular `require()` throws `"Requested module was required recursively"`).
3. Run a deterministic two-phase boot:
   - **Phase 1 (`Init`):** Construct services, allocate `SharedTable`s, register remotes, read configs — no cross-service calls that assume peers have finished `Init`.
   - **Phase 2 (`Start`):** Connect player/world listeners and start background loops.
4. **Deterministic Teardown (Maid / Janitor Pattern):** Track every `RBXScriptConnection`, `task.cancel` thread handle, and owned `Instance` in a scoped cleanup list so respawns, streamed-out models, and test teardowns leak **zero** connections or memory.

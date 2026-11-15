---
name: roblox-combat-and-controllers
description: >-
  Build deterministic Roblox physics character controllers, melee/ranged weapons,
  shapecast hitboxes, and lag-compensated projectiles. Use whenever the user asks
  to create combat systems, sword/melee hitboxes, guns/projectiles, dashes,
  wall-jumps, ControllerManager/GroundController/AirController setups, or Motor6D
  weapon equip/holster state machines with InputActionSystem.
---

# Roblox Combat, Weapons & Physics Character Controllers (`roblox-combat-and-controllers`)

Production architecture and `--!strict` Luau modules for responsive character movement (`ControllerManager`), Motor6D weapon/holster state machines (`InputActionSystem`), and server-authoritative melee/projectile hit detection.

---

## 1. Non-Negotiable Architecture & Security Guardrails

1. **`--!strict` Everywhere:** Every combat module, weapon controller, and hitbox validator MUST start with `--!strict` on line 1.
2. **Modern Physics Character Controller (`ControllerManager`):**
   - For custom dashes, air-control, wall-slides, or knockback without legacy `Humanoid` tripping, attach a `ControllerManager` to the character `Model` (`RootPart = HumanoidRootPart`), set `Humanoid.EvaluateStateMachine = false`, and wire `GroundController`, `AirController`, `ClimbController`, `SwimController`, plus `ControllerPartSensor` (`SensorMode.Floor` / `SensorMode.Ladder`).
3. **Motor6D Weapon & Holster State Machine (Zero Server Scripts in `Tool`s):**
   - Never place executable server `Script`s inside replicated `Tool` instances.
   - Bind weapons via `Motor6D` (`RightHand.RightGripAttachment` or `Socket_RightGrip` when equipped; `UpperTorso` / `LowerTorso` sheath socket when holstered) and drive input through Roblox's modern **Input Action System (IAS)** (`InputContext` -> `InputAction` -> `InputBinding` for Keyboard/Mouse, Gamepad, and Touch).
4. **Animation-Marker Driven Melee Hitboxes (`Workspace:Shapecast` / `GetPartBoundsInBox`):**
   - Never use `BasePart.Touched` for melee weapons (unreliable at high swing speeds and vulnerable to client reach exploits).
   - Gate active hit frames strictly between `AnimationTrack:GetMarkerReachedSignal("HitStart")` and `GetMarkerReachedSignal("HitEnd")`, using `Workspace:Blockcast` / `Workspace:Spherecast` / `Workspace:GetPartBoundsInBox` with `OverlapParams` (`FilterType = Enum.RaycastFilterType.Exclude`, `MaxParts = 16`) and a per-swing `hitTargets: { [Model]: boolean }` deduplication table.
5. **Server-Authoritative Hit Validation & Lag Compensation:**
   - Clients may predict visual projectiles and hit VFX immediately, but the server MUST validate every attack through `SafeRemoteGateway`:
     - Verify attacker alive state, weapon equip state, and attack cooldown (`os.clock() - lastAttack >= minInterval * 0.85`).
     - Verify distance (`(attackerRoot.Position - targetRoot.Position).Magnitude <= maxReachStuds + pingToleranceStuds`).
     - Verify line-of-sight (`Workspace:Raycast` between attacker and target not obstructed by static world geometry).

---

## 2. Canonical Scripts & References

### Scripts (`scripts/`)
- [`scripts/controller_manager_rig.luau`](scripts/controller_manager_rig.luau): `ControllerManagerRig` — Attaches and updates `ControllerManager`, `GroundController`, `AirController`, `ClimbController`, `SwimController`, `FloorSensor`, and `ClimbSensor` on any R15/custom character rig, with impulse dash and knockback helpers.
- [`scripts/weapon_tool_assembler.luau`](scripts/weapon_tool_assembler.luau): `WeaponToolAssembler` — Builds Motor6D weapon/holster rigs, `Attachment` sockets, combo state machines, and `InputContext` / `InputAction` / `InputBinding` action trees (`AttackPrimary`, `AttackHeavy`, `BlockHold`, `Dash`, `ToggleEquip`).
- [`scripts/combat_hitbox_and_projectile.luau`](scripts/combat_hitbox_and_projectile.luau): `CombatHitboxAndProjectile` — Server-validated melee `Blockcast`/`GetPartBoundsInBox` sweep engine, stepped raycast ballistic projectile simulator (`Gravity`, `Drag`, `MaxBounces`, `Pierce`), and anti-exploit reach/LOS verifier.

### References (`references/`)
- [`references/physics_controller_and_combat_patterns.md`](references/physics_controller_and_combat_patterns.md): Complete `ControllerManager` property tuning table, `Shapecast` vs `GetPartBoundsInBox` tradeoffs, combo window state machine timings, and server lag-compensation formulas.

---

## 3. Execution Workflow via `Sharp` MCP

1. Call `sharp_combat_and_controllers(action="install", ...)` to install the `--!strict` combat modules into `ReplicatedStorage.Shared` (`SharpCombatModules`) and optionally configure a rig with `ControllerManager`.
2. Call `sharp_combat_and_controllers(action="smoke_test")` to run deterministic Edit/Play mode verification of `ControllerManagerRig`, `WeaponToolAssembler`, and `CombatHitboxAndProjectile` (verifying hit deduplication, reach rejection, and ballistic step raycasting).

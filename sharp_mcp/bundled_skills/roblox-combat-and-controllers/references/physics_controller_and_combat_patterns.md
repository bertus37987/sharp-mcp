# Physics Character Controller, Weapon Socket & Combat Hitbox Reference

## 1. `ControllerManager` Hierarchy & Properties

```text
Character (Model)
├── Humanoid (EvaluateStateMachine = false)
├── HumanoidRootPart (Part)
│   ├── RootAttachment (Attachment)
│   ├── GroundSensor (ControllerPartSensor, SensorMode = Floor, SearchDistance = 3.2)
│   └── ClimbSensor (ControllerPartSensor, SensorMode = Ladder, SearchDistance = 1.8)
└── ControllerManager
    ├── GroundController (GroundOffset = 2.0, Friction = 2.0, AccelerationTime = 0.08, DecelerationTime = 0.06)
    ├── AirController (MoveMaxForce = 12000, MaintainAngularMomentum = false,MaintainLinearMomentum = true)
    ├── ClimbController (MoveMaxForce = 10000, AccelerationTime = 0.05)
    └── SwimController (AccelerationTime = 0.12)
```

### Key Sensor Update Loop (`RunService.PreSimulation`)
- When `GroundSensor.SensedPart ~= nil`, set `ControllerManager.ActiveController = GroundController`.
- When `ClimbSensor.SensedPart ~= nil`, set `ControllerManager.ActiveController = ClimbController`.
- Otherwise, set `ControllerManager.ActiveController = AirController`.

---

## 2. Melee Hitbox Comparison (`Shapecast` vs `GetPartBoundsInBox` vs `Raycast`)

| Method | Best For | Pros | Cons / Limits |
| :--- | :--- | :--- | :--- |
| `Workspace:Blockcast(cf, size, dir, params)` | Sword slashes, hammers, dash strikes | Continuous swept volume prevents tunneling between frames; returns exact `RaycastResult.Position` & `Normal`. | Direction vector magnitude must be `< 1024` studs; does not detect parts already overlapping the initial box at `t = 0` (pair with one initial `GetPartBoundsInBox`). |
| `Workspace:GetPartBoundsInBox(cf, size, params)` | Instant AoE slams, stationary hurtboxes | Detects all parts currently overlapping oriented box; fast with `OverlapParams.MaxParts`. | Discrete sample per frame; fast swings need swept interpolation or `Blockcast`. |
| Stepped `Workspace:Raycast(p0, p1 - p0, params)` | Bows, magic bolts, firearms | Exact parabolic trajectory with gravity `0.5 * g * dt^2`; easy pierce/ricochet reflection (`v - 2 * v:Dot(n) * n`). | Thin ray; use `Spherecast` (`radius = 0.35..0.75`) for generous projectile hit registration. |

---

## 3. Server Anti-Exploit Combat Validation Rules

1. **Cooldown Gate:** `now - state.lastAttackClock >= weaponSpec.cooldownSec * 0.85` (15% network jitter grace).
2. **Distance Gate:** `(attackerRoot.Position - targetRoot.Position).Magnitude <= weaponSpec.rangeStuds + math.clamp(player:GetNetworkPing() * 24, 2.0, 8.0)`.
3. **Angle Gate:** `attackerRoot.CFrame.LookVector:Dot((targetRoot.Position - attackerRoot.Position).Unit) >= math.cos(math.rad(weaponSpec.maxHalfAngleDeg))` (prevents 360-degree aura killaura exploits on directional swings).
4. **Line-of-Sight Gate:** Server raycast from `attackerRoot.Position` to `targetRoot.Position` excluding character models must not hit opaque world geometry (`CanCollide == true`).

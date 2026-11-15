# NPC AI Pathfinding, Branching Dialogue & Round Director Reference

## 1. NPC Finite State Machine (FSM) Transitions

| Current State | Condition | Next State | Action |
| :--- | :--- | :--- | :--- |
| `Idle` | `elapsedInState >= patrolWaitSec` and `#patrolPoints > 0` | `Patrol` | Advance `patrolIndex` and compute path to next waypoint. |
| `Idle` / `Patrol` | Nearest player `< aggroRangeStuds` and `< maxLeashDistStuds` from `spawnOrigin` | `Chase` | Lock target player; throttle `ComputeAsync` to `>= 0.45s`. |
| `Chase` | Distance to target `<= attackRangeStuds` | `Attack` | Face target; trigger attack cooldown & melee hitbox sweep. |
| `Chase` / `Attack` | Distance from `spawnOrigin > maxLeashDistStuds` OR target invalid/dead | `LeashReturn` | Clear target; path back to `spawnOrigin`. |
| `LeashReturn` | Distance to `spawnOrigin <= 5.0` studs | `Idle` | Restore health and resume patrol. |
| `*` | `Humanoid.Health <= 0` | `Dead` | Disable collisions, grant XP/loot, despawn after delay. |

---

## 2. `PathfindingModifier` & `PathfindingLink` Usage

- **Hazard Avoidance (`PathfindingModifier`):**
  Insert a `PathfindingModifier` inside lava/trap parts with `Label = "DangerZone"` and `PassThrough = false`, then pass `Costs = { DangerZone = math.huge, Mud = 5.0 }` into `PathfindingService:CreatePath`.
- **Gap Jumping (`PathfindingLink`):**
  Connect two `Attachment` instances across a chasm or ledge with a `PathfindingLink` (`IsBidirectional = true`, `Label = "JumpGap"`).

---
name: roblox-world-assembly-and-optimization
description: >-
  Populate and optimize Roblox 3D worlds using Poisson-disc raycast surface
  scattering (slope, altitude, and Enum.Material filtering), Attachment-socket
  modular architecture snapping (targetSocket.WorldCFrame * sourceSocket.CFrame:Inverse()),
  and Scene Budget & StreamingEnabled optimization (CollisionFidelity,
  RenderFidelity, CastShadow, ModelStreamingMode). Use whenever the user asks
  to scatter trees/rocks/props on Terrain, snap modular building/dungeon kits
  together, or optimize world performance/streaming.
---

# Roblox World Assembly, Surface Scatter & Scene Optimization (`roblox-world-assembly-and-optimization`)

Production architecture and `--!strict` Luau modules for **deterministic Poisson-disc raycast prop scattering**, **Attachment-socket modular kit assembly**, and **automated Streaming/CollisionFidelity/Shadow budget optimization**.

---

## 1. Non-Negotiable World Assembly & Optimization Guardrails

1. **`--!strict` Everywhere:** All scatter, modular assembly, and optimization scripts MUST start with `--!strict` on line 1.
2. **Poisson-Disc Surface Scattering Rules:**
   - Raycast downward (`Vector3.new(0, -maxDropStuds, 0)`) with `RaycastParams.IgnoreWater = false` so water hits are detected and rejected (`rayResult.Material == Enum.Material.Water` -> skip).
   - Filter by **Altitude** (`minY <= hitPos.Y <= maxY`), **Slope Angle** (`math.deg(math.acos(math.clamp(hitNormal.Y, -1, 1))) <= maxSlopeDeg`), and **Allowed/Excluded `Enum.Material`** (never scatter forest trees onto `Enum.Material.Cobblestone` roads or `Enum.Material.Water`).
   - Enforce minimum 2D spacing (`minSpacingStuds`) using a spatial hash grid (`cellSize = minSpacingStuds`) for $O(1)$ neighbor rejection.
3. **Attachment-Socket Modular Snapping Formula:**
   - Place named `Attachment` sockets (`SnapSocket_North`, `SnapSocket_South`, `SnapSocket_East`, `SnapSocket_West`) on modular wall/arch/corridor models with outward-facing `Axis`/`CFrame`.
   - Snap `newPiece` (`sourceSocket`) onto `existingPiece` (`targetSocket`) using the exact `PivotTo` formula:
     ```lua
     local alignRotation = CFrame.Angles(0, math.pi, 0) -- Face opposite socket
     local desiredSocketWorldCF = targetSocket.WorldCFrame * alignRotation
     local pivotToSocketOffset = newPiece:GetPivot():ToObjectSpace(sourceSocket.WorldCFrame)
     newPiece:PivotTo(desiredSocketWorldCF * pivotToSocketOffset:Inverse())
     ```
4. **Scene Budget & Streaming Optimizer Rules:**
   - Small decorative props (`boundingBoxSize.Magnitude < 6.0` studs): set `CastShadow = false` and `CanTouch = false`, `CanQuery = false`.
   - Set `ModelStreamingMode = Enum.ModelStreamingMode.Atomic` on multi-part gameplay prefabs (NPCs, interactive chests, vehicles) so clients never see half-streamed models.

---

## 2. Canonical Scripts & References

### Scripts (`scripts/`)
- [`scripts/poisson_surface_scatter.luau`](scripts/poisson_surface_scatter.luau): `PoissonSurfaceScatter` — Spatial-hashed Poisson-disc raycast scatterer with altitude, slope, and `Enum.Material` filters, surface-normal alignment blend, and deterministic `Random.new(seed)`.
- [`scripts/modular_socket_assembler.luau`](scripts/modular_socket_assembler.luau): `ModularSocketAssembler` — Attachment-socket snapping engine (`SnapModelToSocket`, `CreateStandard4mRoomKit`) with `Workspace:GetPartBoundsInBox` overlap validation.
- [`scripts/scene_budget_optimizer.luau`](scripts/scene_budget_optimizer.luau): `SceneBudgetOptimizer` — Audits and optimizes `CastShadow`, `CanTouch`, `CanQuery`, `Anchored`, and `ModelStreamingMode` across Workspace folders.

### References (`references/`)
- [`references/world_scatter_snapping_and_streaming.md`](references/world_scatter_snapping_and_streaming.md): Spatial hash grid math, socket CFrame alignment derivation, and `ModelStreamingMode` selection matrix.

---

## 3. Execution Workflow via `Sharp` MCP

1. Call `sharp_world_assembly_and_optimization(action="install", ...)` (or `"scatter_and_optimize"`) to install `PoissonSurfaceScatter`, `ModularSocketAssembler`, and `SceneBudgetOptimizer` and scatter/optimize props under `Workspace.SharpScatteredProps`.
2. Call `sharp_world_assembly_and_optimization(action="audit_overlaps", tolerance_studs=0.15)` after placing buildings/props to run a read-only 15-axis 3D OBB SAT check for interpenetrating/glitching map meshes; run `action="fix_overlaps"` inside a `SharpUndo` transaction when automated XZ MTV separation is desired.
3. Call `sharp_world_assembly_and_optimization(action="smoke_test")` to verify raycast slope/altitude/water filtering, flush attachment-socket snapping, and `CastShadow`/`ModelStreamingMode` optimization.

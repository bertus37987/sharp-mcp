# World Surface Scatter, Attachment Socket Snapping & Streaming Optimization Reference

## 1. Poisson-Disc Spatial Hash Grid ($O(1)$ Minimum Distance Check)

- Divide the XZ plane into cells of size `cellSize = minSpacingStuds`.
- For candidate point `(x, z)`, compute `(gx, gz) = (math.floor(x / cellSize), math.floor(z / cellSize))` and check only the `3x3` neighborhood `[gx-1..gx+1] x [gz-1..gz+1]`.
- Combine with `Workspace:Raycast` downward:
  - Reject if `hit.Material == Enum.Material.Water` or in `excludedMaterials` (e.g., `Cobblestone`, `Pavement`, `CrackedLava`).
  - Compute slope angle in degrees: `slopeDeg = math.deg(math.acos(math.clamp(hit.Normal.Y, -1, 1)))`.

---

## 2. Attachment-Socket Snapping Derivation

Given:
- `targetSocket: Attachment` on an already-placed `Model`
- `sourceSocket: Attachment` on the `newModel` to attach
- Both sockets have their `CFrame.LookVector` pointing **outward** from the module boundary:

```lua
local desiredWorldSocketCF = targetSocket.WorldCFrame * CFrame.Angles(0, math.pi, 0)
local modelPivotToSourceSocket = newModel:GetPivot():ToObjectSpace(sourceSocket.WorldCFrame)
local targetPivotCF = desiredWorldSocketCF * modelPivotToSourceSocket:Inverse()
newModel:PivotTo(targetPivotCF)
```

---

## 3. Scene Budget & `ModelStreamingMode` Matrix

| Asset Type | `ModelStreamingMode` | `CastShadow` | `CanTouch` / `CanQuery` |
| :--- | :--- | :---: | :---: |
| Small grass / pebbles /flowers (`< 6` studs) | `Default` | `false` | `false` / `false` |
| Trees / boulders / streetlamps (`6..35` studs) | `Atomic` | `true` (trunk/canopy) | `false` / `true` |
| Interactive chests / doors / NPCs | `Atomic` | `true` | `false` / `true` |
| Critical game manager / boss arena floor | `Persistent` | `true` | `false` / `true` |

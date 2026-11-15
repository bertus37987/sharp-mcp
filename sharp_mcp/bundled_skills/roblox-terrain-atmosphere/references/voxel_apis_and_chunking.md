# Voxel APIs, Grid Math, Limits, and Chunked Generation

Roblox `Terrain` (`Workspace.Terrain`, class `Terrain` inheriting from `BasePart`) stores smooth terrain on a **4×4×4 stud voxel grid** spanning up to `Terrain.MaxExtents`. Scripts cannot read or write arbitrary unaligned boxes or unlimited volumes in a single call — every voxel operation must respect grid alignment, `[x][y][z]` array layout, the **4,194,304-voxel cap**, and Studio responsiveness.

---

## 1. Grid Geometry & Coordinate Conversions

Each terrain cell is a **4×4×4 stud** cube in world space (`RESOLUTION = 4`, the only valid `resolution` argument for `ReadVoxels`, `WriteVoxels`, `ReadVoxelChannels`, `WriteVoxelChannels`, `FillRegion`, and `ReplaceMaterial`).

| Member | Signature / Value | Meaning |
| :--- | :--- | :--- |
| `Terrain.MaxExtents` | `Region3int16` (`-32000..32000` per axis) | Max editable cell bounds (`-128,000` to `+128,000` studs per axis); read-only |
| `Terrain:CellCornerToWorld(x, y, z)` | `Vector3` `(x*4, y*4, z*4)` | Lower-left-forward (`-X, -Y, -Z`) corner of cell `(x, y, z)` |
| `Terrain:CellCenterToWorld(x, y, z)` | `Vector3` `(x*4+2, y*4+2, z*4+2)` | Exact world center of cell `(x, y, z)` |
| `Terrain:WorldToCell(pos)` | `Vector3` | Cell coordinates containing `pos` |
| `Terrain:WorldToCellPreferEmpty(pos)` | `Vector3` | Cell coordinates biased toward an empty neighbor on boundaries |
| `Terrain:WorldToCellPreferSolid(pos)` | `Vector3` | Cell coordinates biased toward a solid neighbor on boundaries |
| `Terrain:CountCells()` | `int` | Approximate count of non-Air cells with occupancy > 0 |
| `Region3:ExpandToGrid(4)` | `Region3` | Floors `Min` and ceils `Max` to multiples of `4` studs |

### Critical `Region3` & Cell-Center Formula
- Always ensure `minVec.X <= maxVec.X` (and `Y`, `Z`) before `Region3.new(minVec, maxVec)` so `Region3.Size` never has negative components.
- Always call `region = region:ExpandToGrid(4)` before voxel calls.
- When iterating 1-based voxel arrays `ix = 1..size.X`, `iy = 1..size.Y`, `iz = 1..size.Z` inside a grid-aligned `region`, compute each cell's world bounds from `regionMin = region.CFrame.Position - region.Size * 0.5`:
  ```lua
  local wx = regionMin.X + (ix - 0.5) * 4
  local wy = regionMin.Y + (iy - 0.5) * 4
  local wz = regionMin.Z + (iz - 0.5) * 4
  ```
  Notice the `(ix - 0.5) * 4` center offset (not `ix * 4`), which aligns voxel centers cleanly to `CellCenterToWorld` and places surface occupancy at `0.5` when `height == wy`:
  ```lua
  local occ = math.clamp((surfaceHeight - (wy - 2)) / 4, 0, 1)
  ```

---

## 2. The 4,194,304 Voxel Limit & Chunked Loops

`ReadVoxels`, `WriteVoxels`, `ReadVoxelChannels`, and `WriteVoxelChannels` throw an error if the aligned `Region3` exceeds **`4,194,304` (`2^22`) voxels**:

$$\text{Voxels} = \frac{\text{Size.X}}{4} \times \frac{\text{Size.Y}}{4} \times \frac{\text{Size.Z}}{4} \le 4{,}194{,}304$$

- A **`64 × 64` cell** horizontal chunk (`256 × 256` studs) allows up to `4,194,304 / (64 * 64) = 1,024` vertical cells (`4,096` studs tall!) in one call.
- If a region is taller than `1,024` cells (`4,096` studs), compute the max safe `chunkY = math.floor(4_194_304 / (chunkX * chunkZ))` and loop along `Y` as well as `X` and `Z`.
- **Always yield (`task.wait()`) between chunks** when generating large maps (`> 64×64` cells) so Studio's main thread and UI stay responsive without script timeouts.

---

## 3. `[x][y][z]` Array Layout & `.Size`

Both `ReadVoxels` and `ReadVoxelChannels` return 3D Luau arrays indexed strictly as **`[x][y][z]`** (`1`-based) and include a `Vector3` **`.Size`** field (`materials.Size` or `channelOutput.Size`) equal to `region.Size / 4`. Always iterate with `size.X`, `size.Y`, `size.Z` rather than assuming dimensions.

---

## 4. `WriteVoxelChannels` vs `WriteVoxels` (Water & Custom Slots)

| Method | Signature | Supported Channels / Behavior |
| :--- | :--- | :--- |
| `Terrain:WriteVoxelChannels(region, 4, channels)` | Modern dictionary API | `"SolidMaterial"` OR `"SolidMaterialIndex"` (never both!), `"SolidOccupancy"` (`0..1`), `"LiquidOccupancy"` (`0..1` for Water) |
| `Terrain:ReadVoxelChannels(region, 4, channelIds)` | Modern dictionary read | Returns requested channel 3D tables + `.Size` (`Vector3`) |
| `Terrain:WriteVoxels(region, 4, materials, occupancy)` | Classic 2-array API | Writes `Enum.Material` (including `Enum.Material.Water`) + single occupancy `[0..1]` |
| `Terrain:ReadVoxels(region, 4)` | Classic tuple read | Returns `materials, occupancies` (each with `.Size`) |

### Crucial `WriteVoxelChannels` Rules (Verified from Engine Reference)
1. **Water uses `LiquidOccupancy`, NOT `SolidMaterial`**: `SolidMaterial` no longer supports `Enum.Material.Water`. For water-only voxels, set:
   - `SolidMaterial[x][y][z] = Enum.Material.Air`
   - `SolidOccupancy[x][y][z] = 0`
   - `LiquidOccupancy[x][y][z] = waterOcc` (`0 < waterOcc <= 1`)
2. **Solid vs Liquid exclusivity**: If `SolidOccupancy == 1` (or `> 1 - 1/256`) and `SolidMaterial ~= Enum.Material.Air`, `LiquidOccupancy` MUST be `0`.
3. **Mutually exclusive material keys**: Passing **both** `"SolidMaterial"` and `"SolidMaterialIndex"` in the same `WriteVoxelChannels` call throws an error.
4. **`SolidMaterialIndex` slots (`0..63`)**: Slots `0` (`Air`) and `1` (`Water`) are reserved. Writable custom terrain material slots are **`2..63`** (configured via `Terrain:SetMaterialSlot()` with Expanded Terrain enabled). Passing an unset or out-of-range slot index throws an error.

---

## 5. Geometric Primitives, Copy/Paste & Deprecated APIs

### Scriptable Geometric Primitives (`Security: None`)
| Method | Signature | Best Use |
| :--- | :--- | :--- |
| `FillBlock` | `FillBlock(cframe: CFrame, size: Vector3, material: Material)` | Rotated ramps, flat pads, cutting caves/rooms with `Enum.Material.Air` |
| `FillBall` | `FillBall(center: Vector3, radius: float, material: Material)` | Rounded hills, craters (`Air`), boulders |
| `FillCylinder` | `FillCylinder(cframe: CFrame, height: float, radius: float, material: Material)` | Circular arenas, lakes (`Water`), vertical shafts (`Air`) |
| `FillWedge` | `FillWedge(cframe: CFrame, size: Vector3, material: Material)` | Sloped embankments, natural stairs/ramps |
| `FillRegion` | `FillRegion(region: Region3, 4, material: Material)` | Grid-aligned bulk fill or clear (`Air`) |
| `ReplaceMaterial` | `ReplaceMaterial(region: Region3, 4, sourceMaterial: Material, targetMaterial: Material)` | Grid-aligned biome re-skinning (`Grass` -> `Snow`) |
| `CopyRegion` | `CopyRegion(region: Region3int16): TerrainRegion` | Snapshotting terrain regions (`MaxExtents` or chunk bounds) |
| `PasteRegion` | `PasteRegion(region: TerrainRegion, corner: Vector3int16, pasteEmptyCells: boolean)` | Restoring snapshots or stamping prefab terrain islands |
| `Clear` | `Clear()` | Wipes all terrain in the place |

- **Replication gotcha**: `TerrainRegion` objects returned by `CopyRegion` do **not** replicate between server and client.
- **Deprecated Legacy APIs (NEVER USE)**: `GetCell`, `GetWaterCell`, `SetCell`, `SetCells`, `SetWaterCell`, `AutowedgeCell`, `AutowedgeCells`, `ConvertToSmooth` (`PluginSecurity`), and `IsSmooth` (always `true`). Use `WriteVoxelChannels` / `WriteVoxels` / `Fill*` exclusively.

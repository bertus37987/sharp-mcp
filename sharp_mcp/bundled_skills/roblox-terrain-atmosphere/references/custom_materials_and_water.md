# Custom Terrain Materials, Expanded Terrain, and Water

Roblox offers three layers of terrain material customization — **per-material color tinting**, **global `MaterialVariant` PBR overrides**, and **Expanded Terrain (up to 62 paintable custom material slots)** — plus animated **Grass decoration** and **Water** optics/waves.

---

## 1. Material Customization Decision Matrix

| Feature | Scope | Script Security | Reopen Required? |
| :--- | :--- | :--- | :--- |
| `Terrain:SetMaterialColor(mat, color3)` | Global tint per built-in `Enum.Material` (not `Air`/`Water`) | `None` | No |
| `MaterialService:SetBaseMaterialOverride(mat, variantName)` | Replaces a built-in material globally for Terrain + Parts | `None` (creating/assigning `MaterialVariant` PBR maps requires `PluginSecurity`) | No |
| **Expanded Terrain** (`Terrain:SetMaterialSlot`) | Up to **62** distinct paintable slots (`2..63`) with custom `MaterialVariant` + per-slot `Color3` tint | `None` for slots (`PluginSecurity` to write `ColorMap`/`NormalMap` on new `MaterialVariant`) | **Yes** (`Workspace` toggle requires Place Restart; ~15s wait in Team Create) |
| `MaterialService.Use2022Materials` | Switches built-in material pack (Pre-2022 vs 2022+) | **`RobloxScriptSecurity`** (cannot read or write in scripts; wrap checks in `pcall`) | Studio Property |

---

## 2. Expanded Terrain (Up to 62 Paintable Custom Materials)

Expanded Terrain is **off by default** and swaps the terrain backend per place:

1. **Enable in Studio**: Select `Workspace` in Explorer -> set **Expanded Terrain** to **Enabled** in Properties -> click **Restart** in the Restart Place dialog (in **Team Create**, exit the place and wait ~15 seconds before reopening).
2. **Slot Layout (`0..63`)**:
   - Slots `0` (`Air`) and `1` (`Water`) are **reserved** (`ResetMaterialSlot`/`SetMaterialSlot` on `0` or `1` throws an error).
   - Writable slots are **`2` through `63`** (62 custom materials).
3. **Programmatic Slot API (`Security: None`)**:
   ```lua
   local MaterialService = game:GetService("MaterialService")
   local Terrain = workspace.Terrain

   -- Set slot 2 to use MaterialVariant "MossyGrass" on BaseMaterial Grass with a tint
   -- Pass "" for variantName to tint the base material directly without a MaterialVariant
   Terrain:SetMaterialSlot(2, Enum.Material.Grass, "MossyGrass", Color3.fromRGB(72, 115, 58))

   local baseMat, variantName, color = Terrain:GetMaterialSlot(2)
   -- Clear slot later:
   -- Terrain:ResetMaterialSlot(2)
   ```
4. **Painting Slots via Voxels**: Pass `SolidMaterialIndex` (`0..63`) + `SolidOccupancy` to `Terrain:WriteVoxelChannels(region, 4, { SolidMaterialIndex = indices, SolidOccupancy = occ })`. **Never** pass both `SolidMaterial` and `SolidMaterialIndex` in the same call.

### Expanded Terrain Caveats
- **Clearing a used slot**: Calling `ResetMaterialSlot(slot)` or deleting a slot while voxels still reference its index renders affected terrain in a bright **purple / invalid-material indicator** until repainted.
- **Physical properties**: Custom `PhysicalProperties` on a `MaterialVariant` are not yet respected by custom terrain material slots.
- **Team Create**: Editing terrain in Team Create may introduce meshing or visual bugs.
- **Colormaps**: Heightmap/colormap import is more sensitive to exact RGB colors under Expanded Terrain — use hard-edged exact RGB PNGs.
- **Streaming thickness**: Keep terrain **>= 16 voxels (64 studs) thick**; thinning terrain under Expanded Terrain saves little or no memory and risks disappearing on low streaming radii.

---

## 3. `MaterialService`, `MaterialVariant`, and `TerrainDetail`

- **Parenting rule**: `MaterialVariant` instances ONLY work when parented as descendants of `MaterialService`.
- **PBR Maps (`PluginSecurity` to assign via script/Edit)**:
  - `ColorMap` / `ColorMapContent` (albedo; alpha unused unless `AlphaMode` applies)
  - `NormalMap` / `NormalMapContent` (**must be OpenGL tangent-space** — invert green channel if converting from DirectX!)
  - `RoughnessMap` / `RoughnessMapContent` (black = smooth, white = rough)
  - `MetalnessMap` / `MetalnessMapContent` (black = non-metal, white = metal; requires `Lighting.EnvironmentSpecularScale > 0` to reflect!)
  - `EmissiveMaskContent` + `EmissiveStrength` (`None` security) + `EmissiveTint` (`None` security)
  - `StudsPerTile` (`float`), `MaterialPattern` (`Enum.MaterialPattern.Regular` | `Organic`)
- **`TerrainDetail` (Per-Face Terrain PBR)**:
  - Terrain renders **Top (`+Y`)**, **Side (`XZ`)**, and **Bottom (`-Y`)** faces (`Enum.TerrainFace`).
  - Add up to **3** `TerrainDetail` children inside a `MaterialVariant` (one per `Face`). If none exist, the `MaterialVariant` tiles uniformly on all faces.
  - `BaseMaterial` of the parent `MaterialVariant` must be a valid Terrain material (e.g., `Basalt`, `Grass`, `Rock` — NOT `Plastic` or `Neon`).
- **Global Base Material Override**:
  ```lua
  MaterialService:SetBaseMaterialOverride(Enum.Material.Grass, "StylizedGrass")
  ```
- **Material Tint Color (`Terrain:SetMaterialColor`)**:
  - `Terrain:SetMaterialColor(Enum.Material.Grass, Color3.fromRGB(92, 148, 70))` tints built-in terrain (`GetMaterialColor` reads it).
  - Throws an error if passed `Enum.Material.Air` or `Enum.Material.Water`.
  - `Terrain.MaterialColors` (`BinaryString`) cannot be edited directly by scripts.

---

## 4. Animated Grass (`Decoration`) & Water Properties

### Animated Grass
- `Terrain.Decoration = true` enables animated grass blades on **`Enum.Material.Grass` only** (does not render on `LeafyGrass`, `Ground`, etc.).
- `Terrain.GrassLength` accepts values from **`0.1` to `1.0`**.
- Sway direction and intensity follow **`Workspace.GlobalWind`** (players with Roblox's **Reduce Motion** setting enabled see slower grass sway, though wind direction stays unchanged).

### Water Appearance (`Workspace.Terrain`)
| Property | Range / Type | Default | Behavior |
| :--- | :--- | :--- | :--- |
| `WaterColor` | `Color3` | `[0.05, 0.33, 0.36]` (RGB ~13, 84, 92) | Shifts overall water tint |
| `WaterTransparency` | `0..1` (`float`) | `0.3` | `0` = opaque, `1` = crystal clear |
| `WaterReflectance` | `0..1` (`float`) | `1` | `0` = matte, `1` = full sky/world reflection |
| `WaterWaveSize` | `0..1` (`float`) | `0.15` | Wave height in studs (`0` = flat mirror) |
| `WaterWaveSpeed` | `0..100` (`float`) | `10` | Oscillation cycles per minute (`0` = still) |

> **Studio Preview Tip**: Some water reflections, wave shaders, and post-processing effects only render at full fidelity during Playtest or when **Studio Settings -> Rendering -> Editor Quality Level** is set to maximum.

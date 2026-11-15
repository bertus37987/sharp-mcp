# Heightmaps, Biomes, AI Terrain Workflows, and Streaming

AI agents generate reliable, playable Roblox worlds when terrain shaping, material painting, building pads, and `StreamingEnabled` thickness are treated as one integrated system.

---

## 1. AI Terrain Workflow Selection

| Goal | Best Tool / API | Why |
| :--- | :--- | :--- |
| Procedural landscape + buildings/spawns | [terrain_chunked_builder.luau](../scripts/terrain_chunked_builder.luau) (`WriteVoxelChannels`) | Combines fBM/ridge noise, **smoothstep flatten plateaus**, slope-based materials, water, and safe chunk yielding |
| External sculpt / satellite / artistic elevation map | [heightmap_generator.py](../scripts/heightmap_generator.py) + Studio **Terrain Editor -> Create -> Import** | `1 px = 4 studs`, up to `4096 × 4096`, deterministic 16-bit elevation + exact-RGB 23-material colormap |
| Fast caves, ponds, roads, terrain cuts | `FillBlock`, `FillBall`, `FillCylinder`, `FillWedge`, `ReplaceMaterial` | Zero voxel-table boilerplate; supports rotated `CFrame`s and `Enum.Material.Air` carving |
| Reusable terrain islands / undo snapshots | `CopyRegion(Region3int16)` + `PasteRegion(region, corner, pasteEmptyCells)` | Lossless voxel snapshot/restore in Edit or Server scripts |

---

## 2. Procedural fBM + Ridge Noise & Flatten Plateaus

Raw noise produces bumpy slopes where AI-placed buildings, `SpawnLocation`s, and NPCs either float or sink into hillsides. Always apply **flatten zones (plateaus)** during height evaluation:

1. **Multi-octave fBM + Ridge Blend**:
   - Use Luau's native C++ `math.noise(wx * freq + sx, sy, wz * freq + sz)`. Keep seed offsets compact (e.g., `(seed % 10000) * 0.1731`) so floating-point precision never degrades.
   - Blend standard fBM (`n`) with ridged noise (`1 - math.abs(n)`) via `ridgeWeight` (`0..1`) to produce sharp alpine peaks, canyons, or smooth rolling hills.
2. **Smoothstep Flatten Zones (Building & Spawn Pads)**:
   - Define an inner flat radius `r0` (or half-extents for rectangular `"Box"` pads) where height is forced exactly to target `h`, plus an outer transition radius `r1 > r0` blended via cubic smoothstep:
     $$s = t^2 (3 - 2t), \quad t = \operatorname{clamp}\left(\frac{\text{dist} - r_0}{r_1 - r_0},\, 0,\, 1\right)$$
     $$h_{\text{final}} = h_{\text{target}} + (h_{\text{noise}} - h_{\text{target}}) \cdot s$$
   - Snap `h_target` cleanly (e.g., multiples of `2` or `4` studs) and paint the inner pad with `Grass`, `Cobblestone`, `Pavement`, or `Sand` as desired.
3. **Slope-Based Material Painting**:
   - Compute central/forward height differences across `4` studs: `slope = math.max(math.abs(hx - h), math.abs(hz - h)) / 4`.
   - Steep cliffs (`slope > 0.55`) switch to `Rock`/`Basalt`/`Slate`/`Sandstone` regardless of altitude, while gentler slopes use biome altitude bands (`Snow` peaks, `Grass`/`LeafyGrass` midlands, `Sand`/`Mud` shorelines).

---

## 3. Heightmap + Colormap PNG Pipeline

Verified rules from Roblox's Terrain import docs:
- **Resolution & Scale**: **1 pixel = 4 studs** horizontally (`512 × 512` px = `2,048 × 2,048` studs). Maximum image dimensions: **`4096 × 4096` pixels** (`.png` or `.jpg`).
- **Height Scaling**: Grayscale intensity maps linearly across the Studio Import selection region's **Y size**: pure black (`0`) = `center.Y - size.Y / 2`; pure white (`255` in 8-bit or `65535` in 16-bit) = `center.Y + size.Y / 2`. Use **16-bit PNG** (`heightmap_16bit.png`) whenever possible to avoid stair-stepping terraces on gentle hills.
- **Hard Edges Only on Colormaps**: Never use anti-aliasing, bilinear resizing, or JPEG compression on colormaps — smoothed edge pixels fall outside exact material RGBs and cause unintended stray materials (especially under **Expanded Terrain**, which is more color-sensitive).

### Official 23-Material Roblox Terrain ColorMap Table

| `Enum.Material` | RGB | Hex | Typical Use |
| :--- | :--- | :--- | :--- |
| `Air` | `[255, 255, 255]` | `#FFFFFF` | Empty / sky void |
| `Asphalt` | `[115, 123, 107]` | `#737B6B` | Roads, airstrips |
| `Basalt` | `[30, 30, 37]` | `#1E1E25` | Volcanic cliff rock |
| `Brick` | `[138, 86, 62]` | `#8A563E` | Masonry embankments |
| `Cobblestone` | `[132, 123, 90]` | `#847B5A` | Medieval plazas, paths |
| `Concrete` | `[127, 102, 63]` | `#7F663F` | Urban foundations |
| `CrackedLava` | `[232, 156, 74]` | `#E89C4A` | Magma vents, calderas |
| `Glacier` | `[101, 176, 234]` | `#65B0EA` | Glacial walls |
| `Grass` | `[106, 127, 63]` | `#6A7F3F` | Meadows (supports animated grass) |
| `Ground` | `[102, 92, 59]` | `#665C3B` | Dirt, forest floor |
| `Ice` | `[129, 194, 224]` | `#81C2E0` | Frozen lakes |
| `LeafyGrass` | `[115, 132, 74]` | `#73844A` | Dense jungle/forest turf |
| `Limestone` | `[206, 173, 148]` | `#CEAD94` | Karst cliffs, pale stone |
| `Mud` | `[58, 46, 36]` | `#3A2E24` | Swamps, riverbeds |
| `Pavement` | `[148, 148, 140]` | `#94948C` | Sidewalks, courtyards |
| `Rock` | `[102, 108, 111]` | `#666C6F` | Alpine peaks, cliffs |
| `Salt` | `[198, 189, 181]` | `#C6BDB5` | Salt flats |
| `Sand` | `[143, 126, 95]` | `#8F7E5F` | Beaches, dunes |
| `Sandstone` | `[137, 90, 71]` | `#895A47` | Desert canyons, mesas |
| `Slate` | `[63, 127, 107]` | `#3F7F6B` | Dark wet stone |
| `Snow` | `[195, 199, 218]` | `#C3C7DA` | Peaks, arctic plains |
| `WoodPlanks` | `[139, 109, 79]` | `#8B6D4F` | Docks, boardwalks |
| `Water` | `[12, 84, 92]` | `#0C545C` | Rivers, lakes, oceans |

Run `python heightmap_generator.py --size 256 --seed 42 --biome alpine --out-dir ./out` to generate paired 16-bit/8-bit heightmaps, exact-RGB colormaps, and import bounds metadata.

---

## 4. `StreamingEnabled` Interaction & Thin-Terrain Pitfall

When `Workspace.StreamingEnabled == true`:
- **Minimum 16-Voxel (64-Stud) Thickness Rule**: Under tight `StreamingMinRadius` / `StreamingTargetRadius` values (especially with **Expanded Terrain**), thin terrain features **less than 16 voxels (64 studs) thick** can disappear on clients or during playtesting. Always keep structural terrain floors, floating islands, and mountain walls at least **64 studs thick** vertically/horizontally (`y0` deep enough below lowest valley floor!).
- **Expanded Terrain Memory Note**: Thinning terrain below 16 voxels saves little or no memory under Expanded Terrain, so never hollow out terrain shells thin to save memory.
- **Buffer Margin**: Always keep `Workspace.StreamingTargetRadius > Workspace.StreamingMinRadius` (recommended defaults: `StreamingMinRadius = 64`, `StreamingTargetRadius = 1024`, `StreamOutBehavior = Enum.StreamOutBehavior.Opportunistic`). Setting `TargetRadius == MinRadius` removes the streaming buffer and triggers network pauses.

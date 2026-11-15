# AI-Generated UI Textures, Icon Atlases & Upload Pipeline

## 1. Native Vectors vs. Raster PNGs Decision Matrix

| Visual Element | Recommended Approach | Why |
| :--- | :--- | :--- |
| Flat/gradient rounded cards, status bars, toolbars, borders | **Native `Frame` + `UICorner` + `UIStroke` + `UIGradient`** | Infinitely sharp at all DPIs, zero moderation delay, instant StyleSheet theming |
| Ornate beveled frames, glossy tintable pill buttons, plaques | **9-Slice PNG (`ScaleType = Slice`)** | Preserves decorative corner plates & specular bevels without stretching |
| Currencies, skills, badges, item icons | **Packed `<=1024x1024` PNG Atlas (`ImageRectOffset`/`ImageRectSize`)** or Lucide pack | Single HTTP texture load, zero edge bleed with 2–4px gutters + alpha bleed |
| 3D weapons, armor, chests, NPC portraits | **`ViewportFrame` + `ViewportCamera` + `WorldModel`** | Live 3D shading & turntable rotation without flat baked sprites |
| Labels & numbers on panels/buttons | **Always Roblox `TextLabel` / `TextButton`** | Never bake text into AI textures (breaks localization, scaling, and crispness) |

---

## 2. MCP & Cloud Image Upload Matrix

| Tool / API | Accepted Input | Output | Use for 2D Roblox GUI? |
| :--- | :--- | :--- | :--- |
| **`Roblox_Studio:upload_image`** | `imagePaths: string[]` (**HTTP/HTTPS URLs ONLY**, e.g. `http://localhost:8765/panel.png` or `https://www.figma.com/api/mcp/asset/...`) | `{ url: "rbxassetid://<id>" }` | **YES** — fastest live Studio upload; serve local PNGs via a quick local HTTP server (`python -m http.server`) |
| **`Roblox_Studio:open_cloud_invoke`** | `POST /assets/v1/assets` with local file in creator-approved directory (`<= 20 MB`), poll `GET /assets/v1/operations/{id}` | Permanent asset ID (`assetId`) | **YES** — permanent Open Cloud upload (`assetType: "Decal"`; note `ImageContent` resolves Decal/Image URIs cleanly) |
| **`Roblox_Studio:store_image`** | Local `.png`/`.jpg`/`.jpeg` (`<= 5 MB`) | `IMAGEID_<id>` URI | **NO** — AI reference only (`generate_procedural_model` `attachedImageUri`), NOT GUI `rbxassetid://` |
| **`Roblox_Studio:generate_texture`** | `instance_path` (`MeshPart` / `Model`) + `textPrompt` | Retextures 3D mesh in place | **NO** — 3D meshes only, NOT 2D `ScreenGui` / `ImageLabel` |
| **`AssetService:CreateEditableImage`** | Luau `WritePixelsBuffer` (`<= 1024x1024`) | `ImageLabel.ImageContent = Content.fromObject(ei)` | **Offline Edit/Local Preview ONLY** (does NOT replicate server -> client; requires *Allow Mesh / Image APIs* if used live) |

---

## 3. Solving AI & Figma UI Image Pitfalls (`slice_and_atlas_helper.py`)

Raw outputs from AI image generators (`.jpg` / `.png`) and unprepped Figma exports exhibit four classic Roblox failures — all automated by [slice_and_atlas_helper.py](../scripts/slice_and_atlas_helper.py):

1. **Opaque Solid / Navy / Checkerboard Backgrounds -> `remove_border_background()`**:
   - Performs a **perimeter BFS flood-fill** from sampled border pixels (`sample_margin`) using Euclidean RGB distance (`tolerance`) + 1-ring edge feathering (`feather`).
   - Why flood-fill instead of global color thresholding? Dark-outlined icons (coins, shields, chests) have black/dark interior outlines that global thresholding would punch holes into. Perimeter flood-fill stops cleanly at the outer silhouette!
2. **Black Fringe / Dark Halo on Transparent Edges -> `alpha_bleed_rgba()`**:
   - Under bilinear interpolation (`Enum.ResamplerMode.Default`), Roblox blends adjacent `alpha = 0` pixels (often RGB `(0,0,0)`) into visible sprite borders, causing ugly dark outlines.
   - `alpha_bleed_rgba(img, iterations=2)` dilates RGB values outward from `alpha > 0` border pixels into neighboring `alpha = 0` pixels while keeping `alpha = 0` transparent.
3. **Excessive Margins & >1024px Downscale Shift -> `crop_to_alpha_bbox()` + `fit_max_dimension()`**:
   - Generated 9-slice pill buttons often arrive centered in large empty margins (`1024x1024`), and Roblox silently downscales uploads `> 1024px`, corrupting pixel `SliceCenter` coordinates.
   - `prepare_nine_slice_png()` crops tight (`crop_to_alpha_bbox`), caps dimensions (`<= 512px` default, `<= 1024px` hard limit), runs `alpha_bleed_rgba`, and computes `detect_nine_slice_center()` using 95th-percentile column/row uniformity so ornate corner brackets are never stretched!
4. **Grid Spritesheet Seams & Neighbor Bleed -> `split_grid_and_pack_atlas()` / `pack_icon_atlas()`**:
   - Generated 2x2 / 3x3 icon grids often have slight shade differences per quadrant (`TL` vs `TR`) and center seam lines.
   - `split_grid_and_pack_atlas()` trims `4px` along shared seams, runs `remove_border_background()` independently per cell, fits each icon uniformly into `cell_size`, runs `alpha_bleed_rgba`, and packs into a `<= 1024x1024` RGBA PNG with `gutter = 4` transparent spacing, outputting exact `ImageRectOffset` and `ImageRectSize` (`compute_atlas_uvs()`).
   - Set `ImageLabel.ResampleMode = Enum.ResamplerMode.Pixelated` ONLY for pixel art; keep `Enum.ResamplerMode.Default` for smooth painted/vector icons.

---

## 4. End-to-End CLI Recipes

### A. Prepare Ornate Panel & White-Tint Button 9-Slice PNGs
```bash
python slice_and_atlas_helper.py prepare-9slice raw_panel.jpg out/panel_9slice.png --max-dim 512
python slice_and_atlas_helper.py prepare-9slice raw_button.jpg out/button_tint_9slice.png --max-dim 512
```
Example output JSON provides exact Luau `SliceCenter = Rect.new(minX, minY, maxX, maxY)` and Studio edge offsets (`left`, `top`, `right`, `bottom`).

### B. Split a 2x2 AI Icon Sheet into a Clean Packed Atlas
```bash
python slice_and_atlas_helper.py split-atlas raw_icons_2x2.jpg out/icons_atlas.png --rows 2 --cols 2 --names "coin,gem,combat,chest" --cell-size 256 --gutter 4
```
Pass the resulting `assetId` and JSON coordinates into `CONFIG.Assets` in [build_standard_game_gui.luau](../scripts/build_standard_game_gui.luau) or `--assets-json` in [generate_rbxmx_gui.py](../scripts/generate_rbxmx_gui.py).

### C. Localhost HTTP Upload Pattern (`Roblox_Studio:upload_image`)
1. Start a temporary server in the output folder: `python -m http.server 8765 --bind 127.0.0.1`
2. Call `upload_image(imagePaths=["http://127.0.0.1:8765/panel_9slice.png", ...], studio_id=...)`
3. Stop the temporary HTTP server once `rbxassetid://...` IDs are returned.

---

## 5. AI Image Generator Prompt Templates (`prompt-template`)

For copy-paste AI generator prompt templates (`9slice_panel`, `9slice_tint_button`, `icon_grid_2x2`, `icon_grid_3x3`, `hud_bar`, `rarity_frame`, `tile_pattern`) and the 6 Golden Rules of Roblox UI prompting, see [ai_image_prompt_templates.md](./ai_image_prompt_templates.md) or run:
```bash
python slice_and_atlas_helper.py prompt-template --kind 9slice_panel --theme "stylized dark fantasy RPG"
python slice_and_atlas_helper.py prompt-template --kind 9slice_tint_button --theme "sleek sci-fi cyberpunk"
python slice_and_atlas_helper.py prompt-template --kind icon_grid_2x2 --theme "vibrant anime action simulator"
```

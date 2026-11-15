# AI Image Generator Prompt Templates for Roblox GUI (`roblox-gui`)

Production palette-locked prompt templates and engineering rules for generating **9-Slice Panels**, **Tintable Grayscale Buttons (`ImageColor3`)**, **Arbitrary `R×C` Icon Grid Atlases**, **HUD Progress Bars**, **Item Rarity Slot Frames**, **Seamless Tile Patterns**, and **Loading Backdrops** that pass cleanly through [slice_and_atlas_helper.py](../scripts/slice_and_atlas_helper.py), `Sharp:sharp_design_system(action="image_prompts")`, and `Sharp:sharp_gui_slice_and_pack`.

---

## 1. The 6 Golden Rules of Roblox UI Image Prompting (Anti-Slop)

Standard AI image prompts fail in Roblox `ScreenGui` pipelines because of perspective warp, noisy backgrounds, fake checkerboards, muddy gradients, stretched corner details, or baked-in text. Always enforce these 6 structural constraints + the per-game `{PALETTE_HEXES}` & `{STYLE_SIGNATURE}` tokens:

1. **Strict Orthographic 2D Front View (`Zero Perspective`)**
   - Always include: `"flat 2D orthographic front-facing game UI element, 90-degree straight-on view, zero perspective tilt, zero 3D camera angle"`
   - *Why:* Any perspective trapezoid skew breaks horizontal/vertical `SliceCenter = Rect.new(minX, minY, maxX, maxY)` slicing.
2. **Dynamic Solid Key Background (`{KEY_BG_HEX}` — No Fake Checkerboard)**
   - Always include: `"isolated on a single flat uniform solid {KEY_BG_HEX} chroma-key background with a generous 40px empty outer margin, no outer drop shadow, no glow bleeding into background, no transparency checkerboard"` (pick `#FF00FF` magenta for dark-ink themes or `#00FF00` / high-contrast key away from palette colors).
   - *Why:* AI generators often draw grey-and-white squares when asked for a "transparent PNG". A flat uniform key color lets `remove_border_background()` flood-fill key the exterior to `alpha = 0` in one pass while preserving dark `outline_ink` contours, followed by `alpha_bleed_rgba()` to prevent dark bilinear fringes.
3. **Uniform Straight Middle Span for 9-Slice (`Corners Only Ornate`)**
   - For 9-slice panels and buttons, always include: `"ornate rivets/filigree/corner brackets strictly confined to the 4 outer corners (outer 22% of width and height); the middle 56% of the top, bottom, left, and right borders must be completely straight, uniform, and horizontally/vertically repeatable; flat uniform interior center"`
   - *Why:* `detect_nine_slice_center()` measures 95th-percentile row/column uniformity to locate the stretchable center rectangle. Keeping decorative motifs inside the 4 corners prevents mid-border distortion when stretched to arbitrary modal sizes.
4. **White / Silver Grayscale for Tintable Buttons (`ImageColor3` Ready)**
   - For reusable buttons, badges, and progress fills, include: `"rendered in neutral white, light silver, and soft cool-gray grayscale (#FFFFFF highlights, #D8E0EA midtones, #8C96A6 bevel shadows), zero color hue saturation"`
   - *Why:* In Roblox, `ImageButton.ImageColor3` multiplies against the texture RGB. One single uploaded white/grayscale 9-slice button (`rbxassetid://...`) can be tinted via `UIKit.Tokens` into `Primary`, `Success`, `Danger`, `Accent`, or `Gold` with zero extra texture memory.
5. **Invisible Grid & Wide Gutters for Arbitrary `R×C` Icon Sheets (`No Grid Lines`)**
   - For `2×2`, `3×3`, `4×4`, or arbitrary `R×C` icon sheets, include: `"arranged in a clean {ROWS}x{COLS} grid ({ICON_COUNT} icons total, one centered in each cell), wide uniform solid {KEY_BG_HEX} background spacing between icons, NO dividing grid lines, NO boxes or frames around individual icons, bold crisp {OUTLINE_INK} outer contour silhouette on every icon"`
   - *Why:* `split_grid_and_pack_atlas()` proportionally slices the image into `rows × cols` cells, perimeter flood-fill keys `{KEY_BG_HEX}`, **tight-trims every icon to its opaque bounding box**, alpha-bleeds edges, and packs into a `<= 1024×1024` spritesheet. Visible divider lines connect to borders and interfere with cell isolation.
6. **Zero Baked Text & Palette Lock (`Anti-Slop`)**
   - Always embed your game's **`{PALETTE_HEXES}`** (`Primary`, `Secondary`, `Accent`, `Gold`, `BgPanel`, `OutlineInk`) and **`{STYLE_SIGNATURE}`**, plus **Negative Prompt**:
     `NO text, NO letters, NO numbers, NO watermarks, NO fake transparency checkerboard, NO muddy grey-brown desaturated gradients, NO flat generic dark-blue corporate rectangles, NO drop shadow overlapping {KEY_BG_HEX}, NO perspective skew.`

---

## 2. Copy-Paste Prompt Templates by UI Category (With Batch Plan)

Generate an entire per-screen prompt batch locked to a game's design system via `DesignEngine.build_image_prompt_batch(design_system, screens=..., icon_grid=(rows, cols))` (`sharp_design_system(action="image_prompts")`), or single templates via `python slice_and_atlas_helper.py prompt-template`.

### Template A: Ornate 9-Slice Modal / Window Panel (`9slice_panel`)
> **Prompt:**
> `Flat 2D orthographic front-facing game UI modal window frame matching style signature [{STYLE_SIGNATURE}], strictly locked to palette {PALETTE_HEXES}, 1:1 square aspect ratio. Symmetrical rectangular frame with {DETAILS} and crisp {OUTLINE_INK} outer contour outline. Decorative corner plates, rivets, or bevel accents strictly confined to the 4 outer corners (outer 22% of width and height). The middle 56% of the top, bottom, left, and right border edges are completely straight, uniform thickness, and smoothly repeatable for 9-slice scaling. The interior center area is a flat, uniform {BG_PANEL} surface with no inner pattern. Isolated on a single flat uniform solid {KEY_BG_HEX} background with a 48px empty margin on all sides. Crisp vector-clean edges, glossy specular edge highlights, zero perspective tilt, no outer drop shadow, no glow outside frame border, no transparency checkerboard, no muddy gradients, strictly no text, no letters, no numbers.`

- **Post-Processing Command:**
  ```bash
  python slice_and_atlas_helper.py prepare-9slice raw_panel.png panel_9slice.png --max-dim 512
  ```

---

### Template B: Tintable White/Grayscale 9-Slice Button (`9slice_tint_button`)
> **Prompt:**
> `Flat 2D orthographic front-facing game UI rectangular pill button matching shape signature [{STYLE_SIGNATURE}], centered horizontally. Rendered strictly in neutral white and silver grayscale (#FFFFFF top specular edge highlight, #E2E8F0 glossy diagonal upper sheen, #CBD5E1 lower bevel, #64748B crisp outer border outline) with zero color hue saturation so it can be vertex-tinted via ImageColor3 against palette {PALETTE_HEXES}. Rounded / beveled corner caps confined to the left and right 24% ends; the middle 52% horizontal span has completely straight, parallel, uniform top and bottom edges for 9-slice horizontal stretching. Isolated on a single flat uniform solid {KEY_BG_HEX} background with generous empty margin around the button. Zero perspective tilt, no outer drop shadow, no transparency checkerboard, no muddy gradients, strictly no text, no icons, blank button face.`

- **Post-Processing Command:**
  ```bash
  python slice_and_atlas_helper.py prepare-9slice raw_button.png button_tint_9slice.png --max-dim 512
  ```
- **Luau `StyleRule` Tinting Example:**
  ```luau
  -- Reuse one single rbxassetid:// across Primary, Success, Danger, Accent, and Gold buttons:
  button.Image = "rbxassetid://YOUR_TINT_BUTTON_ID"
  button.ScaleType = Enum.ScaleType.Slice
  button.SliceCenter = Rect.new(64, 43, 448, 211)
  button.ImageColor3 = UIKit.Tokens.Colors.Primary
  ```

---

### Template C: Generalized `R×C` Game UI Icon Grid Atlas (`icon_grid_rxc`)
> **Prompt (`{ROWS}×{COLS}` — `{ICON_COUNT}` Icons):**
> `Flat 2D orthographic game UI icon sheet arranged in a strict {ROWS}x{COLS} grid ({ICON_COUNT} distinct icons total, {ROWS} rows by {COLS} columns) matching [{STYLE_SIGNATURE}] and palette {PALETTE_HEXES}: {ICON_LIST}. Each icon is centered inside its cell with generous empty {KEY_BG_HEX} spacing around it, bold crisp {OUTLINE_INK} outer contour silhouette, vibrant cel-shaded gradients, and sharp top-left specular highlights. Isolated on a single flat uniform solid {KEY_BG_HEX} chroma background across the entire canvas. Strictly NO grid dividing lines, NO boxes or frames around individual icons, no outer drop shadows or glowing halos bleeding into the background, no transparency checkerboard, no muddy grey gradients, strictly no text, no numbers.`

- **Post-Processing Command (Arbitrary `rows × cols` with tight per-cell trim + `<=1024px` cap):**
  ```bash
  python slice_and_atlas_helper.py split-atlas raw_icons_3x3.png icons_atlas.png --rows 3 --cols 3 --names "coin,gem,sword,chest,shield,potion,crown,key,star" --cell-size 256 --gutter 4
  ```

---

### Template D: HUD Status / Health / XP Bar Frame (`hud_bar`)
> **Prompt:**
> `Flat 2D orthographic horizontal game UI status bar frame matching [{STYLE_SIGNATURE}] and palette {PALETTE_HEXES}. Wide horizontal capsule/beveled trough with decorative end-caps on the far left and far right 18% ends, and a completely straight, uniform horizontal middle 64% span for 9-slice stretching. Dark recessed inner track ({BG_DEEP}) with bold {OUTLINE_INK} outer contour and glossy specular rim highlight ({PRIMARY}/{ACCENT}). Isolated on a single flat uniform solid {KEY_BG_HEX} background with wide margin, zero perspective, no outer shadow, no transparency checkerboard, no text, no numbers.`

---

### Template E: Square Item Rarity Slot Frame (`rarity_frame`)
> **Prompt:**
> `Flat 2D orthographic square 1:1 game UI inventory item slot frame matching [{STYLE_SIGNATURE}], neutral silver/white grayscale metallic border with ornamental corner notches and crisp outer rim so it can be ImageColor3 tinted across rarity hues ({PALETTE_HEXES}), recessed center ({BG_DEEP}), completely straight uniform middle edges for 9-slice scaling. Isolated on a single flat uniform solid {KEY_BG_HEX} background with 40px outer margin, no outer glow, no transparency checkerboard, no baked text, empty center.`

---

### Template F: Seamless Tileable UI Pattern (`tile_pattern` for `ScaleType = Tile`)
> **Prompt:**
> `Seamless 2D tileable repeating game UI background pattern matching [{STYLE_SIGNATURE}] and palette {BG_DEEP}/{BG_PANEL} ({DETAILS}). Full-bleed edge-to-edge subtle low-contrast geometric motif strictly in subtle surface tones around {BG_DEEP} and {BG_PANEL} so foreground UI text remains 100% legible. Strictly seamless horizontal and vertical wrap-around edges, flat orthographic 2D texture, no vignette, no central focal point, no muddy grey noise, no text.`

---

### Template G: Stylized Loading / Title Screen Backdrop (`loading_backdrop`)
> **Prompt:**
> `Wide 16:9 stylized illustrated game loading screen backdrop for [{GAME_TITLE}] matching [{STYLE_SIGNATURE}], anchored cleanly to palette {PALETTE_HEXES}. Atmospheric depth silhouettes toward focal center with dramatic rim-lighting in {PRIMARY} and {ACCENT}, keeping the central 55% uncluttered for live Luau progress-bar and logo overlays. Crisp stylized art direction, zero perspective UI frames baked in, no muddy grey-brown blur, no fake checkerboard, strictly NO baked text, NO letters, NO logos, NO buttons.`

---

## 3. Ready-to-Use Genre Presets (`theme` + `details`)

| Genre Preset | `{STYLE_THEME}` | `{DETAILS}` (Panels & Frames) | Typical `2×2` Icons |
| :--- | :--- | :--- | :--- |
| **`rpg_arcane`** | `"ornate gilded arcane guild RPG UI"` | `"handcrafted dark iron bevels, subtle brushed bronze corner brackets with tiny diamond rivets"` | `"golden embossed coin, glowing cyan mana crystal, crossed steel broadswords, ornate wooden treasure chest"` |
| **`scifi_holo`** | `"precision chamfered aerospace holographic HUD"` | `"chamfered matte carbon-titanium plates, crisp cyan neon corner bracket inlays, precision tech notches"` | `"hexagonal credit chip, plasma energy core, laser rifle reticle, encrypted supply crate"` |
| **`candy_simulator`** | `"glossy lacquered sugar-coat cel-shaded simulator"` | `"bold dark berry-ink outlines, glossy jelly chamfered bevels, star-shaped corner pins"` | `"shiny gold star coin, rainbow prism gem, aura flame fist, winged pet egg"` |
| **`anime_neon`** | `"high-contrast anime cel-shaded action HUD"` | `"razor-sharp specular slash bevels, bold ink contours, dynamic speed-line corner brackets"` | `"blazing shonen emblem, neon soul orb, katana crest, gilded gacha scroll"` |
| **`arcade_pop`** | `"bold punchy arcade pop-art comic HUD"` | `"thick jet-black ink borders, hard-edge comic halftone highlights, angled bolt corner pins"` | `"arcade token, lightning boost, retro blaster badge, mystery prize box"` |
| **`cozy_pastel`** | `"warm stylized storybook cartoon craft UI"` | `"smooth rounded stitched wood/parchment-style bevels with brass corner tacks"` | `"gold clover coin, ruby heart crystal, wooden mallet, ribbon gift box"` |

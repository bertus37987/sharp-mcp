# Styling (`StyleSheet`), 9-Slice Math & Responsive Layout

Modern Roblox UI pairs **declarative `StyleSheet` token hierarchies** with **flex/grid layout constraints**, **clean 9-slice image borders**, and **`UIDragDetector` interactions**.

---

## 1. Engine UI Styling System (`StyleSheet` / `StyleRule` / `StyleLink` / `StyleQuery`)

In [ui_theme_and_components.luau](../scripts/ui_theme_and_components.luau), `UIKit.BuildStyleSheet()` creates a 3-tier `StyleDerive` chain under `ReplicatedStorage.UIStyles`:

1. **`TokensSheet`**: Stores theme attributes (`setAttribute("Primary", Color3...)`, `"$Primary"` in rules).
2. **`ThemeSheet`**: Derives `TokensSheet` (`Priority = 1`) and defines selector rules + hover/press `TweenInfo` transitions.
3. **`DesignSheet`**: Derives `ThemeSheet` (`Priority = 2`) and links to each `ScreenGui` via `UIKit.AttachStyleLink(gui, styleSheet)` (`StyleLink`, max 1 per subtree).

### Exact Selector Syntax (Verified)
- **Class**: `"Frame"`, `"TextButton"`, `"ImageLabel"`
- **Tag (`CollectionService:AddTag`)**: `".ButtonPrimary"`, `".CardPanel"`, `".KeybindPill"`
- **Instance Name**: `"#SideRail"`, `"#RailLayout"`
- **Interactive States (`Enum.GuiState`)**: `":Hover"`, `":Press"`, `":NonInteractable"` (**NOTE: `:Press`, NOT `:Pressed`!**)
- **Modifier (Phantom `UIComponent`)**: `"::UICorner"`, `"::UIStroke"`, `"::UIPadding"`, `"::UIShadow"`, `"::UIGradient"` (alias multiple with `"::UIStroke #Outer"`)
- **Combinators**: `>` (direct child), `>>` (descendant), `,` (selector list) — **NOTE: whitespace is NOT a descendant combinator in Roblox CSS; use `>>` for descendants and NO space for compound same-instance `@` filters!**
- **Built-in `@` Media Queries (Compound vs Descendant)**:
  - `@PreferredInputTouch`, `@PreferredInputKeyboardAndMouse`, `@PreferredInputGamepad`
  - `@ViewportDisplaySizeSmall`, `@ViewportDisplaySizeMedium`, `@ViewportDisplaySizeLarge`
  - `@ReducedMotionEnabledTrue`, `@ReducedMotionEnabledFalse`
  - `@PreferredTextSizeMedium`, `@PreferredTextSizeLarge`, `@PreferredTextSizeLarger`, `@PreferredTextSizeLargest`
  - Example compound filters on the tagged element itself: `".KeybindPill@PreferredInputTouch"`, `".CompactHide@ViewportDisplaySizeSmall"`
- **Custom `StyleQuery` (`@CompactPhone`)**: Parent a `StyleQuery` under `MainHudGui`, call `q:SetConditions({ MaxSize = Vector2.new(959, 9999) })`, and target its descendants via `>>`: `"@CompactPhone >> #SideRail"`, `"@CompactPhone >> #RailLayout"`, `"@CompactPhone >> .RailBtn"`, `"@CompactPhone >> .RailTitle"`, `"@CompactPhone >> .CompactHide"`.

> **Compatibility & `IsPropertyModified` Precedence Rules**:
> 1. **Never directly assign a property on an instance that `StyleRule` or `@Query` controls** (e.g. `btn.BackgroundColor3 = ...`, `sideRail.Size = ...`, `layout.FillDirection = ...`). Assigning directly sets `IsPropertyModified == true`, silently locking out `:Hover`, `:Press`, `:NonInteractable`, and `@` overrides. Put desktop defaults in base rules (`Priority = 35`) and override them in `@` rules (`Priority = 40..41`); at runtime, swap tags (`:RemoveTag` / `:AddTag`) instead of writing `BackgroundColor3`.
> 2. Always inspect `rule.SelectorError` after setting `StyleRule.Selector`, and wrap newer `SetProperty` keys (e.g. `BorderStrokePosition`, `StrokeSizingMode`, `BorderOffset`, `UIShadow`) in `pcall` or assign on instances directly.

---

## 2. Layout, Visual Modifiers & `CanvasGroup` Rules

- **`UIListLayout` + `UIFlexItem`**:
  - `UIListLayout`: `FillDirection`, `SortOrder`, `HorizontalAlignment`, `VerticalAlignment`, `Padding`, `HorizontalFlex` / `VerticalFlex` (`Enum.UIFlexAlignment`: `None`, `Fill`, `SpaceAround`, `SpaceBetween`, `SpaceEvenly`), `ItemLineAlignment` (`Automatic`, `Start`, `Center`, `End`, `Stretch`), `Wraps`.
  - `UIFlexItem`: `FlexMode` (`Enum.UIFlexMode`: `None`, `Grow`, `Shrink`, `Fill`, `Custom`), `GrowRatio`, `ShrinkRatio`. Great for split inspector panels (`ViewportHolder` fills remaining height cleanly across Desktop and Phone!).
  - Reserve `UIGridLayout` (`CellSize`, `CellPadding`, `FillDirectionMaxCells`) for uniform 2D item grids; don't enable flex on static lists.
- **`UIStroke`**: `ApplyStrokeMode` (`Contextual` for text, `Border` for containers), `BorderStrokePosition` (`Outer`, `Center`, `Inner` — wrap `BorderStrokePosition` in `pcall` + inset `InnerHighlight` fallback via `UIKit.AttachStackedStrokes()`), `BorderOffset: UDim`, `StrokeSizingMode` (`FixedSize`, `ScaledSize`), `LineJoinMode` (`Round`, `Bevel`, `Miter`).
- **`UIGradient`**: `Type` (`Linear`, `Radial`, `Conical`, `Elliptical`), `TileMode` (`Clamp`, `Repeat`, `Mirror`), `Color: ColorSequence` (**keep `<= 6` stops**, 4-stop `-35..-45deg` glossy ramp), `Transparency: NumberSequence`, `Offset: Vector2` (`UIKit.CreateShineSweep()`). Remember `UIGradient.Color` multiplies against `BackgroundColor3`.
- **`UIShadow`**: `Mode` (`Shape`, `Text`), `BlurRadius`, `Offset`, `Spread`, `Inset`, `ShowBehindParent`, `ZIndex` (`<= 0`). Always guard `Instance.new("UIShadow")` with `pcall` + offset sibling `Frame` fallback when outside `UIGridStyleLayout` (`UIKit.AttachDropShadow()` / `UIKit.CreateGlossyButton()`).
- **`UIKit.ApplyDesignSystem()` & Anti-Slop Factories**: Call `UIKit.ApplyDesignSystem(ds)` (or preset `"candy_simulator" | "anime_neon" | "cozy_pastel" | "scifi_holo" | "arcade_pop" | "rpg_arcane"`) before `UIKit.BuildStyleSheet()`, and build rich interactive widgets via `UIKit.CreateGlossyButton()` (`+3px Y` press tween, `IsReducedMotion()` respected), `UIKit.CreateGlossyPanel()`, `UIKit.CreateSunburstRays()`, `UIKit.CreateBadgePill()`, and `UIKit.CreateModalFadeGroup()`.
- **`CanvasGroup` Texture Budget (Critical)**:
  - Flattens descendants for `GroupTransparency`, `GroupColor3`, `UICorner`, and `UIGradient`, and forces `ClipsDescendants = true`.
  - **Requires ancestor `ScreenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling`** (fails to flatten under `Global`).
  - Hardware texture buffer is capped at **2048x2048px** max (**1024x1024px** on lower-end devices). Oversized or excessive `CanvasGroup`s blur text, burn VRAM, and **render completely blank** if the client memory budget is exceeded. Reserve `CanvasGroup` for temporary transitions (`LoadingTransitionTemplate`) and NEVER put one on every scrolling list card.

---

## 3. Exact 9-Slice Math (`SliceCenter` vs Studio Editor)

When setting `ImageLabel.ScaleType = Enum.ScaleType.Slice` (or `ImageButton`):
- **`SliceCenter = Rect.new(minX, minY, maxX, maxY)`** uses **raw source pixel coordinates** measured from the top-left `(0, 0)` of the uploaded texture.
- **Studio 9-Slice Editor displays inward edge offsets `(Left, Top, Right, Bottom)`**, NOT `SliceCenter` coordinates! Convert for an image of size `(W, H)` via `compute_slice_center_from_offsets()` in [slice_and_atlas_helper.py](../scripts/slice_and_atlas_helper.py):
  ```text
  minX = Left
  minY = Top
  maxX = W - Right
  maxY = H - Bottom
  ```
- **`SliceScale`**: Scales border thickness independently of container size (e.g., `0.22` on a 512px ornate frame keeps the bezel crisp and compact inside modals).
- **1024px Cap Rule**: Always clamp `max_dim <= 1024` BEFORE computing `SliceCenter` or atlas UVs (`prepare_nine_slice_png()`, generalized `split_grid_and_pack_atlas()` with tight per-cell trim, and `pack_icon_atlas()` automatically enforce `<= 1024x1024` downscaling and auto-fit cell sizing). If Roblox downscales an oversized upload on import, `SliceCenter` and `ImageRectOffset`/`ImageRectSize` pixel coordinates shift!
- **White-Tint Trick**: Author one monochrome white/silver glossy button PNG (`button_tint_9slice`) and tint per variant via `ImageColor3`.

---

## 4. Responsive Scaling & `UIDragDetector` Sliders

- **`UIKit.BindResponsiveScale(gui, minScale, maxScale)`**: Keeps `UIScale` clamped (`0.86..1.08`). Pairing `minScale = 0.86` with `>= 52px` button sizes ensures physical `AbsoluteSize >= 44.7px` even on compact `844x390` phones!
- **`UIDragDetector` (`UIKit.CreateSlider`)**:
  - `DragStyle = Enum.UIDragDetectorDragStyle.TranslateLine`
  - `ResponseStyle = Enum.UIDragDetectorResponseStyle.Scale`
  - `DragAxis = Vector2.new(1, 0)`
  - `BoundingUI = trackBtn`
  - Parented to `Knob`, synced on `DragContinue` / `DragEnd` plus direct `trackBtn.MouseButton1Down` click-jump.

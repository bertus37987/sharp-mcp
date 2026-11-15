# Standard Game GUI Mapping & Layer Architecture

A complete Roblox game UI must separate **full-bleed backdrops**, **always-on HUD**, **topbar widgets**, **single-active modals**, **high-priority confirmations**, **non-blocking tooltips/toasts**, and **loading transitions** into distinct `ScreenGui` layers with deterministic `DisplayOrder`, `ScreenInsets`, and cross-platform safe zones.

---

## 1. Canonical `DisplayOrder` Z-Layer Stack

All game `ScreenGui` instances (except `LoadingTransitionGui` in `ReplicatedFirst`) MUST be **direct children of `StarterGui`** with **`ResetOnSpawn = false`** and **`ZIndexBehavior = Enum.ZIndexBehavior.Sibling`**.

> **Critical Rule**: Placing a `ScreenGui` inside a `Folder` under `StarterGui` forces `ResetOnSpawn` behavior on respawn even when `ResetOnSpawn = false`. Always parent `ScreenGui`s directly to `StarterGui`.

| `DisplayOrder` | `ScreenGui` Name | `ScreenInsets` | `ResetOnSpawn` | Purpose & Contents |
| :---: | :--- | :--- | :---: | :--- |
| `0` | `BackdropVignetteGui` | `None` | `false` | Full-bleed non-interactive (`Active = false`) low-HP vignette or screen tint |
| `10` | `MainHudGui` | `CoreUISafeInsets` | `false` | Always-on HUD: `PlayerStatus`, `CurrencyBar`, `SideRail`, `ActionHotbar`, `ObjectiveTracker` |
| `20` | `TopbarWidgetsGui` | `TopbarSafeInsets` | `false` | Optional slim indicators inside free topbar gap (or TopbarPlus v3.5.0 buttons) |
| `30` | `ContextualPromptGui` | `CoreUISafeInsets` | `false` | Custom `ProximityPrompt` cards & contextual action chips |
| `49` | `ModalBackdropGui` | `None` | `false` | Full-bleed dim `Scrim` behind notches/topbar while any modal is open (`Enabled = false` by default) |
| `50` | `ModalMenusGui` | `CoreUISafeInsets` | `false` | Modal Stack Manager: **Shop**, **Inventory**, **Quests**, **IndexCodes**, **Settings** (max 1 visible) |
| `65` | `NpcDialogGui` | `CoreUISafeInsets` | `false` | Speaker `ViewportFrame` 3D bust, `MaxVisibleGraphemes` typewriter, choice buttons |
| `80` | `ConfirmDialogGui` | `CoreUISafeInsets` | `false` | Blocking confirmation prompt above modals (`SelectionGroup = true`, `SelectionBehavior* = Stop`) |
| `90` | `FloatingTooltipGui` | `CoreUISafeInsets` | `false` | Viewport-clamped hover/selection tooltip (`Active = false` pass-through) |
| `100` | `ToastNotificationGui` | `CoreUISafeInsets` | `false` | FIFO/capped non-blocking toast stack (max 3 visible) |
| `1000` | `LoadingTransitionGui` | `None` | `false` | `ReplicatedFirst` splash / teleport curtain (stored as `LoadingTransitionTemplate` in Edit) |

---

## 2. `ScreenGui.ScreenInsets` & Safe-Area Rules

`ScreenInsets` (`Enum.ScreenInsets`) governs how Roblox clips/offsets a `ScreenGui` relative to the Unibar/Topbar and hardware notches:

- **`Enum.ScreenInsets.CoreUISafeInsets` (Default for interactive HUD & Modals)**: Clears both device cutouts/home bars AND the top Unibar/Controls bar (`GuiService.TopbarInset`).
- **`Enum.ScreenInsets.DeviceSafeInsets`**: Clears device notch/home bar, allows drawing inside the topbar region (legacy `IgnoreGuiInset = true` maps here, NOT to `None`!).
- **`Enum.ScreenInsets.TopbarSafeInsets`**: Slices specifically to the horizontal gap between left/right Roblox Topbar controls.
- **`Enum.ScreenInsets.None`**: True edge-to-edge full screen (`0,0 -> ViewportSize`). Use ONLY for non-interactive backdrops (`BackdropVignetteGui`), full-screen modal dim scrims (`ModalBackdropGui`), and loading curtains (`LoadingTransitionGui`).
- **Legacy `IgnoreGuiInset` trap**: `IgnoreGuiInset` is a non-saved legacy alias (`false -> CoreUISafeInsets`, `true -> DeviceSafeInsets`). Always set `ScreenInsets` explicitly.

---

## 3. CoreUI Collision Avoidance Map

```text
+-------------------------------------------------------------------+
| [Unibar / Menu]       TopbarSafeInsets (~58px)      [SelfView/Etc]|
+--------------------+-------------------------+--------------------+
| PlayerStatus       |   Top-Center / Clear    | CurrencyBar (+Btn) |
| (or below Chat)    |     Toast Stack         | (or left of List)  |
|                    |                         | [PlayerList ~210w] |
| SideRail (Desktop) |      OPEN 3D VIEW       | ObjectiveTracker   |
| (Phone: compact    |      & MODALS (50)      | (auto-hides small) |
|  row below Status) |                         |                    |
+--------------------+-------------------------+--------------------+
| [Touch Thumbstick] |  ActionHotbar [1..5]    | [Touch JumpBtn]    |
|  (~34%W x 44%H)    |  (Centered <=55% W)     | (~130x130px)       |
+--------------------+-------------------------+--------------------+
```

1. **Top Bar (`GuiService.TopbarInset`)**: ~58px modern Unibar height. Never place buttons inside `y < TopbarInset.Max.Y` unless inside a `TopbarSafeInsets` `ScreenGui`.
2. **Default Chat (Top-Left)** & **Leaderboard `PlayerList` (Top-Right)**: Either keep `PlayerStatus` compact, offset `CurrencyBar` clear of `PlayerList` (or disable unused core modules cleanly via `StarterGui:SetCoreGuiEnabled(Enum.CoreGuiType.Health | Backpack | PlayerList, false)`).
3. **Mobile Bottom Corners (`TouchEnabled` / `PreferredInput == Touch`)**: Keep `ActionHotbar` centered bottom (`<= 55%` viewport width on small devices) so the bottom-left `DynamicThumbstick` and bottom-right `TouchJumpButton` have unobstructed space. On compact phone viewports (`<= 959x540`), reflow `SideRail` into a compact horizontal strip under `PlayerStatus` (`StyleQuery` `CompactPhone` + `StandardGuiController`).
4. **Console / 10-Foot (`GuiService:IsTenFootInterface()`)**: Apply ~5% overscan inset inside `CoreUISafeInsets`, enable `Selectable = true`, trap focus inside open modals (`SelectionGroup = true`, `SelectionBehavior* = Enum.SelectionBehavior.Stop`, `GuiService:AddSelectionParent`, `GuiService:Select`), and pop modals on `Enum.KeyCode.ButtonB`.

---

## 4. Cross-Platform Controls & Input Adaptation

| Aspect | Desktop (`KeyboardAndMouse`) | Mobile (`Touch`) | Console (`Gamepad`) |
| :--- | :--- | :--- | :--- |
| **Detection** | `UserInputService.PreferredInput` | Dynamic switch on touch/controller | `PreferredInput == Gamepad` |
| **Min Button Size** | `>= 44x44px` (`52px` standard) | **`>= 44x44px` physical** (`52px` base ensures `>= 44px` at `0.86` `UIScale`) | `>= 48x48px` with clear focus border |
| **Keybind Hints** | Show `.KeybindPill` (`[1]..[5]`, `[E]`, `[Esc]`) | Hide `.KeybindPill` via `@PreferredInputTouch` | Swap to `ButtonA`/`ButtonB`/`L1`/`R1` glyphs (`UserInputService:GetImageForKeyCode`) |
| **Tooltips** | Hover (`MouseEnter` / `MouseLeave`, clamped) | Tap-to-inspect in `Inventory` / `Shop` | `SelectionGained` triggers inspector/tooltip |
| **Closing Modals** | `X` button, outside scrim tap, `Escape` | `X` button (`>= 44x44px`) or scrim tap | `ButtonB` pops `ConfirmDialog` -> `NpcDialog` -> `ModalManager` |

---

## 5. Required Standard Game Screens & Validation Script

Every standard game UI package should cover:
1. **Always-On HUD (`MainHudGui`)**: `PlayerStatus` (Level, HP, XP), `CurrencyBar` (Coins/Gems + `+` Shop shortcut), `ActionHotbar` (1..5 slots, `UIAspectRatioConstraint 1:1`), `SideRail` (Shop, Inventory, Quests, IndexCodes, Settings + notification badges), collapsible `ObjectiveTracker`.
2. **Modals (`ModalMenusGui`)**:
   - **Shop**: Category tabs (`Featured`, `Gear`, `Passes`, `Currency`), `UIGridLayout` cards, Buy -> `ConfirmDialog`.
   - **Inventory**: Tabs + Search `TextBox` + Grid + Right-side `ViewportFrame` 3D Inspector + `Equip`.
   - **Quests**: Progress bars + `Claim` -> Coin reward + Toast.
   - **IndexCodes**: Unlocked vs silhouette items (`Color3.new(0,0,0)`) + Code `TextBox` + `Redeem`.
   - **Settings**: `UIDragDetector` audio/scale sliders + graphics toggles.
3. **Overlays**: `FloatingTooltipGui`, `ToastNotificationGui`, `ConfirmDialogGui`, `NpcDialogGui`.
4. **Loading Screen**: `LoadingTransitionGui` (`DisplayOrder = 1000`, `ScreenInsets = None`, `ReplicatedFirst`).

Validate and export declarative GUI maps with [gui_map_spec.py](../scripts/gui_map_spec.py):
- `get_standard_gui_map()` — returns the canonical dict spec
- `validate_gui_map(spec)` — verifies zero `DisplayOrder` collisions, valid `ScreenInsets`, `Sibling` `ZIndexBehavior`, `min_touch_target_px >= 44`, and all required widgets
- `generate_starter_gui_manifest(spec)` — builds a normalized `StarterGui` + `ReplicatedFirst` manifest JSON

# Runtime Luau Patterns, UX Polish & Studio Verification

## 1. Modal Stack Manager (`UIKit.CreateModalManager`)

In [ui_theme_and_components.luau](../scripts/ui_theme_and_components.luau), `UIKit.CreateModalManager(modalGui, backdropGui)` enforces a **single active modal** at any moment:
- Calls `Register(name, frame, defaultFocus)` to configure `SelectionGroup = true` and `SelectionBehaviorUp/Down/Left/Right = Enum.SelectionBehavior.Stop` so gamepad `D-Pad`/`Thumbstick` navigation never escapes behind an open dialog.
- Toggles `ModalBackdropGui` (`DisplayOrder = 49`, `ScreenInsets = None`) so the dim scrim covers under notches and topbar, and clicking outside pops the modal via `Pop()`.
- Saves `GuiService.SelectedObject` before opening and restores focus on `CloseAll()`, calling `GuiService:AddSelectionParent` / `GuiService:Select` when `UserInputService.PreferredInput == Enum.PreferredInput.Gamepad`.
- Bind `Enum.KeyCode.Escape` and `Enum.KeyCode.ButtonB` to pop `ConfirmDialogGui` -> `NpcDialogGui` -> `ModalManager` in priority order.

---

## 2. Clamped Tooltip, FIFO Toast Queue & Tween Juice

### A. Viewport-Clamped Tooltip (`UIKit.CreateTooltipController`)
- `FloatingTooltipGui` (`DisplayOrder = 90`) uses `Active = false` pass-through so hover never steals mouse events.
- `TooltipCard` uses `AutomaticSize = Enum.AutomaticSize.XY` with `UISizeConstraint(MinSize = (150, 44), MaxSize = (270, 220))`.
- `Show(title, subtitle, body, anchorPos, accent)` flips to the left if near the right edge and clamps strictly via `math.clamp(raw, margin, viewport - cardSize - margin)`.
- `BindHover(target, getData)` skips `MouseEnter` on `Enum.PreferredInput.Touch` (using tap-to-inspect instead) and listens to `SelectionGained`/`SelectionLost` for Gamepad!

### B. FIFO Toast Queue (`UIKit.CreateToastQueue`)
- Caps concurrent visible banners (`maxVisible = 3`) in `ToastNotificationGui` (`DisplayOrder = 100`), queuing overflow requests in FIFO order.
- Supports semantic kinds: `"Info"`, `"Success"`, `"Reward"`, `"Warning"`, `"Error"`.

### C. Accessible Tween UI Juice (`UIKit.Tween` & `UIKit.AttachButtonJuice`)
- `UIKit.AttachButtonJuice(button, visualTarget, onActivate)` animates a child `UIScale` (`1.03` hover, `0.95` press) via `TweenService`.
- **Accessibility Check**: `UIKit.IsReducedMotion()` reads `GuiService.ReducedMotionEnabled` and snaps property transitions immediately when enabled — never trap reduced-motion users in bouncy tweens or rapid camera motion.

---

## 3. `ViewportFrame` 3D Previews & NPC Typewriter Dialog

### A. `UIKit.CreateViewportPreview(parent, opts)`
- Wraps subject `Model`/`BasePart` inside a **`WorldModel`** child (required for `Animator` / idle animations inside `ViewportFrame`) and creates a **`ViewportCamera`** (`FieldOfView = 35`) rather than an unserialized `Camera`.
- Automatically computes `GetBoundingBox()` and frames the object cleanly (`dist = (maxExtent * 0.5) / math.tan(rad(fov * 0.5)) * 1.48`).
- Disconnects `RunService.RenderStepped` automatically on `Destroy()` or `AncestryChanged` so closed modals never leak connections.
- **Limitations**: No dynamic shadows or `Lighting` post-processing; `Neon`/`Glass` render at low quality; nested `GuiObject`s inside `ViewportFrame` do not render.

### B. NPC Dialog Typewriter (`NpcDialogGui`)
- Combine `TextLabel.RichText = true` with **`TextLabel.MaxVisibleGraphemes`** (iterating `1 .. utf8.len(label.ContentText)` and finishing with `-1`).
- Never slice `TextLabel.Text` manually with `string.sub`, which exposes raw `<b>`/`<font>` tags mid-animation and breaks multi-byte UTF-8 characters.

---

## 4. Input Action System (IAS) & Dynamic Input Icons

For multi-platform games beyond `UserInputService.InputBegan`:
- Structure actions declaratively using **`InputContext`** (`Enabled`, `Priority`, `Sink`) -> **`InputAction`** (`Type: Enum.InputActionType`, `Pressed`/`Released`/`StateChanged`) -> **`InputBinding`** (`KeyCode`, `UIButton`, `DisplayName`, `DisplayImage`).
- Pair with **`InputActionLabel`** (`InputAction`, `ResolvedText`, `ResolvedImageContent`) or `UserInputService:GetImageForKeyCode()` / `GetStringForKeyCode()` so prompts update automatically when a player plugs in a gamepad or switches from touch to keyboard.

---

## 5. Studio MCP Verification & Audit Loop

1. **Install & Build (Edit Mode)**:
   - Install [ui_theme_and_components.luau](../scripts/ui_theme_and_components.luau) as `ModuleScript` `ReplicatedStorage.UIThemeAndComponents`.
   - Execute [build_standard_game_gui.luau](../scripts/build_standard_game_gui.luau) via `execute_luau(datamodel_type="Edit")`.
2. **Automated Structural & Layout Audit**:
   - Execute [audit_gui.luau](../scripts/audit_gui.luau) in **Edit** mode (`StarterGui`) and **Play** mode (`PlayerGui`), confirming `errorCount == 0` (`status == "PASS"`).
3. **Device Simulator + Visual Inspection**:
   - Test across Desktop (`1920x1080`) and Phone (`844x390` iPhone landscape) using Studio's Device Simulator (`rbx-device-simulator-lua`), calling `screen_capture` and inspecting with `read_file` to verify `TopbarInset` clearance, thumbstick/jump clearance, and crisp 9-slice/icon rendering.
4. **Live Playtest Interaction Check**:
   - Start Playtest (`start_stop_play`), test button clicks (`user_mouse_input` / `PlayerGui.StandardGuiDebug`), switch modals (`Shop` -> `ConfirmDialog` -> `Toast`, `Inventory` 3D preview, `Quests` claim, `IndexCodes` redeem `"LAUNCH2026"`, `Settings` `UIDragDetector` slider, `NpcDialog` typewriter), check `LogService:GetLogHistory()` for zero errors/warnings, and capture a Playtest screenshot before stopping Playtest.

# Open-Source UI Frameworks, Icon Packs & Plugin Boundaries

## 1. UI Framework Comparison & Exact Version APIs

Choose the architecture matching your project scale and delivery workflow:

| Framework / Approach | Verified Version & Package | Key APIs & Paradigm | Best Fit & Caveats |
| :--- | :--- | :--- | :--- |
| **Pure Luau + `StyleSheet`** (`UIThemeAndComponents`) | Engine-native | `Instance.new`, `StyleSheet` / `StyleRule` / `StyleLink`, modular `UIKit` tokens & factories | **Primary choice** for zero-dependency Studio MCP `execute_luau` execution, clean `.rbxmx` export, and fast iteration |
| **Fusion** (`dphfox/Fusion`) | **v0.3.0** (`elttob.uk/Fusion/latest/`) | `scoped(Fusion)`, `scope:Value`, `scope:Computed`, `scope:Spring`, `scope:Tween`, `scope:Hydrate`, `scope:New`, `peek()`, `use()`, `doCleanup(scope)` | Expressive spring-physics game UIs. *Breaking v0.2 -> v0.3*: `:get()` removed in favor of `peek()`/`use()`, explicit `scoped()` lifetime |
| **Vide** (`centau/vide`) | **v0.4.1** (`centau.github.io/vide/`) | `source()`, `derive()`, `effect()`, `cleanup()`, `show()`, `indexes()`, `values()`, `create "Frame" {}`, `mount()` | Ultra-lightweight SolidJS-style reactivity with minimal allocations and clean Luau strict typing |
| **React-Lua** (`jsdotlua/react-lua`) | **v17.2.1** (Wally `@jsdotlua/react`, `ReactRoblox`) | VDOM, `useState`, `useEffect`, `useMemo`, `React.createElement` | Large multi-engineer teams, complex data-heavy tools, or Studio plugins; heavier runtime & VDOM overhead |
| **TopbarPlus** (`1ForeverHD/TopbarPlus`) | **v3.5.0** (Wally `1foreverhd/topbarplus@3.5.0`) | `Icon.new():setImage():setLabel():bindToggleItem():setDropdown()` | De facto standard for topbar quick-toggle buttons aligned with Unibar / `TopbarSafeInsets`; keep `>= v3.5.0` for current CoreUI safety |
| **Onyx-UI** (`loneka/onyx-ui`) | **v1.0.4** (`loneka.com/onyx-ui/`) | Fusion v0.3 component library + theme tokens + UI Labs stories | Rapid themed components if your project already depends on Fusion |
| **Lucide Roblox** (`latte-soft/lucide-roblox`) | Wally `latte-soft/lucide-icons@0.1.2` (Tarmac) | `Lucide.GetAsset(iconName, size)` -> `{ Id, Url, ImageRectSize, ImageRectOffset }` | Crisp monochrome vector-style UI icons via packed Tarmac spritesheets |
| **WindUI / Fluent** (`Footagesus/WindUI`, `dawid-scripts/Fluent`) | Utility window libs | `CreateWindow`, `AddTab`, `AddButton`, `Notify` | Desktop script-hub / debug drawer style only — **do NOT use** for player-facing cross-platform mobile/console game HUDs |

---

## 2. Integrating Open-Source Frameworks with Standard GUI Mapping

Whichever framework mounts the UI tree (`Pure Luau`, `Fusion v0.3`, `Vide`, or `React-Lua`), the **GUI Mapping contract remains identical**:
- Mount separate `ScreenGui`s directly under `PlayerGui` / `StarterGui` with `DisplayOrder` (`0, 10, 20, 30, 49, 50, 65, 80, 90, 100, 1000`), `ResetOnSpawn = false`, `ZIndexBehavior = Enum.ZIndexBehavior.Sibling`, and explicit `ScreenInsets`.
- Enforce `>= 44x44px` hitboxes (`UISizeConstraint`), single-active Modal Stack with `SelectionGroup = true`, and clamped tooltips/toasts.
- Run [audit_gui.luau](../scripts/audit_gui.luau) against the live `PlayerGui` regardless of which framework spawned the instances!

---

## 3. Antigravity Skill vs. Plugin & Roblox Studio Plugin Boundaries

### A. Antigravity Layer (`~/.gemini/config/skills/roblox-gui/`)
- **Standalone global skill auto-discovers cleanly** at Global Discovery priority #3 (`~/.gemini/config/skills/`). No custom Antigravity Plugin (`plugin.json`) is needed.
- Always keep skill folders as **real directories** (not symlinks).
- `Roblox_Studio:create_skill` creates Studio MCP-internal markdown notes only (no Python/Luau `scripts/` or `references/` folders; cannot start with `rbx-`), so keep `roblox-gui-workflow` in Studio MCP as a lightweight companion pointer to `~/.gemini/config/skills/roblox-gui/`.

### B. Roblox Studio Layer (No Custom Studio Plugin Needed for Authoring)
- **Works directly via `Roblox_Studio` MCP + Python + Luau + Open Cloud**:
  - Building & editing `ScreenGui`s, `StyleSheet`s, `UIFlexItem`, `UIDragDetector`, `ViewportFrame`, `LocalScript`s (`execute_luau`)
  - Generating `.rbxmx` & `.png` atlases/9-slices on disk (`generate_rbxmx_gui.py`, `slice_and_atlas_helper.py`)
  - Uploading UI images (`upload_image` via local HTTP server, or `open_cloud_invoke` `POST /assets/v1/assets`)
  - Device Simulator multi-resolution layout verification, Playtest input simulation, `LogService` checks, and `screen_capture`
- **Only requires a custom Roblox Studio Plugin (`PluginSecurity`) if you specifically want**:
  - Persistent human-clickable Studio DockWidgets, toolbar buttons, or 3D viewport gizmos (`Plugin:CreateDockWidgetPluginGuiAsync`, `Plugin:Activate`)
  - Studio-native OS file dialogs (`Plugin:PromptSaveSelectionAsync`, `StudioService:PromptImportFileAsync`) or interactive `Plugin:SaveSelectedToRoblox()` popups.

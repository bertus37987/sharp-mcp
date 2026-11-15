"""Standard Roblox Game GUI Mapping schema, validator, and StarterGui manifest builder.

Defines the canonical DisplayOrder Z-layer stack, ScreenInsets, Safe-Zone collision
rules, cross-platform controls mapping (Desktop / Mobile / Console), and required
standard game screens (HUD, Modals, Overlays, Loading Screen) for Roblox Studio.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

MIN_TOUCH_TARGET_PX: int = 44

VALID_SCREEN_INSETS: set[str] = {
    "CoreUISafeInsets",
    "DeviceSafeInsets",
    "TopbarSafeInsets",
    "None",
}

VALID_ZINDEX_BEHAVIORS: set[str] = {
    "Sibling",
    "Global",
}

VALID_CORE_GUI_TYPES: set[str] = {
    "PlayerList",
    "Health",
    "Backpack",
    "Chat",
    "EmotesMenu",
    "SelfView",
    "Captures",
    "AvatarSwitcher",
    "ExperienceShop",
    "All",
}

REQUIRED_HUD_WIDGETS: tuple[str, ...] = (
    "PlayerStatus",
    "CurrencyBar",
    "ActionHotbar",
    "SideRail",
    "ObjectiveTracker",
)

REQUIRED_MODALS: tuple[str, ...] = (
    "Shop",
    "Inventory",
    "Quests",
    "IndexCodes",
    "Settings",
)

REQUIRED_OVERLAYS: tuple[str, ...] = (
    "FloatingTooltip",
    "ToastNotification",
    "ConfirmDialog",
    "NpcDialog",
)


@dataclass(frozen=True)
class LayerSpec:
    """Represents one ScreenGui layer in StarterGui (or ReplicatedFirst)."""

    name: str
    display_order: int
    screen_insets: str
    reset_on_spawn: bool = False
    zindex_behavior: str = "Sibling"
    parent_service: str = "StarterGui"
    interactive: bool = True
    purpose: str = ""
    widgets: tuple[str, ...] = ()
    safe_zone_notes: str = ""


@dataclass
class GuiMapSpec:
    """Complete game GUI architecture specification for validation and export."""

    title: str = "StandardGameGui"
    min_touch_target_px: int = MIN_TOUCH_TARGET_PX
    console_overscan_margin_scale: float = 0.05
    layers: list[LayerSpec] = field(default_factory=list)
    disabled_core_gui: list[str] = field(default_factory=lambda: ["Backpack", "Health"])
    hud_widgets: list[str] = field(default_factory=lambda: list(REQUIRED_HUD_WIDGETS))
    modals: list[str] = field(default_factory=lambda: list(REQUIRED_MODALS))
    overlays: list[str] = field(default_factory=lambda: list(REQUIRED_OVERLAYS))
    has_loading_screen: bool = True


STANDARD_LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        name="BackdropVignetteGui",
        display_order=0,
        screen_insets="None",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=False,
        purpose="Full-bleed non-interactive damage/low-HP vignette or atmospheric tint.",
        widgets=("DamageVignette",),
        safe_zone_notes="Active=false pass-through; covers under notches/topbar.",
    ),
    LayerSpec(
        name="MainHudGui",
        display_order=10,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="Always-on player HUD: status, currencies, hotbar, side rail, objective tracker.",
        widgets=REQUIRED_HUD_WIDGETS,
        safe_zone_notes=(
            "Clears TopbarInset automatically. Keep bottom-left clear of Mobile DynamicThumbstick, "
            "bottom-right clear of TouchJumpButton, top-left clear of Chat, top-right clear of PlayerList."
        ),
    ),
    LayerSpec(
        name="TopbarWidgetsGui",
        display_order=20,
        screen_insets="TopbarSafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="Optional slim topbar status/toggle pill aligned inside free TopbarSafeInsets space.",
        widgets=("TopbarStatusPill",),
        safe_zone_notes="Uses TopbarSafeInsets (or TopbarPlus v3) to avoid Unibar overlap.",
    ),
    LayerSpec(
        name="ContextualPromptGui",
        display_order=30,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="World interaction prompt / contextual action button.",
        widgets=("ProximityActionChip",),
        safe_zone_notes="Keep centered-bottom above Hotbar or near screen center.",
    ),
    LayerSpec(
        name="ModalBackdropGui",
        display_order=49,
        screen_insets="None",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="Full-bleed dim scrim behind notches/topbar while any modal is open.",
        widgets=("BackdropScrim",),
        safe_zone_notes="Active=true when visible to absorb outside clicks and pop modal stack.",
    ),
    LayerSpec(
        name="ModalMenusGui",
        display_order=50,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="Single-active Modal Stack: Shop, Inventory (ViewportFrame), Quests, Index/Codes, Settings.",
        widgets=REQUIRED_MODALS,
        safe_zone_notes="SelectionGroup=true + SelectionBehavior*=Stop; >=44x44px close button.",
    ),
    LayerSpec(
        name="NpcDialogGui",
        display_order=65,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="NPC dialogue panel with ViewportFrame 3D bust, MaxVisibleGraphemes typewriter, choices.",
        widgets=("NpcDialog",),
        safe_zone_notes="Bottom-center safe card above mobile thumb/jump corners.",
    ),
    LayerSpec(
        name="ConfirmDialogGui",
        display_order=80,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=True,
        purpose="High-priority blocking confirmation modal above standard menus.",
        widgets=("ConfirmDialog",),
        safe_zone_notes="Traps gamepad focus above ModalMenusGui; ButtonB/Esc cancels.",
    ),
    LayerSpec(
        name="FloatingTooltipGui",
        display_order=90,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=False,
        purpose="Viewport-clamped hover/selection tooltip.",
        widgets=("FloatingTooltip",),
        safe_zone_notes="Active=false pass-through; clamped to AbsoluteSize - padding.",
    ),
    LayerSpec(
        name="ToastNotificationGui",
        display_order=100,
        screen_insets="CoreUISafeInsets",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="StarterGui",
        interactive=False,
        purpose="FIFO/capped non-blocking toast banners (max 3 visible).",
        widgets=("ToastNotification",),
        safe_zone_notes="Top-center safe margin below TopbarInset.",
    ),
    LayerSpec(
        name="LoadingTransitionGui",
        display_order=1000,
        screen_insets="None",
        reset_on_spawn=False,
        zindex_behavior="Sibling",
        parent_service="ReplicatedFirst",
        interactive=True,
        purpose="Immediate ReplicatedFirst splash screen and teleport transition curtain.",
        widgets=("LoadingScreen",),
        safe_zone_notes="ScreenInsets=None covers notches; disabled in Edit preview unless testing.",
    ),
)


def get_standard_gui_map() -> dict[str, Any]:
    """Return the canonical Standard Game GUI Mapping dictionary."""
    spec = GuiMapSpec(layers=list(STANDARD_LAYERS))
    data = asdict(spec)
    data["safe_zones"] = {
        "topbar_unibar_approx_px": 58,
        "chat_top_left": {"width_pct": 0.30, "height_px": 240, "core_gui": "Chat"},
        "leaderboard_top_right": {"width_px": 210, "core_gui": "PlayerList"},
        "mobile_thumbstick_bottom_left": {"width_pct": 0.34, "height_pct": 0.44},
        "mobile_jump_bottom_right": {"width_px": 130, "height_px": 130},
        "console_overscan_pct": 0.05,
    }
    data["platform_rules"] = {
        "KeyboardAndMouse": {
            "show_keybind_pills": True,
            "tooltip_mode": "HoverClamped",
            "close_keys": ["Escape", "Tab"],
        },
        "Touch": {
            "show_keybind_pills": False,
            "tooltip_mode": "TapInspect",
            "min_button_px": MIN_TOUCH_TARGET_PX,
        },
        "Gamepad": {
            "show_gamepad_glyphs": True,
            "tooltip_mode": "SelectionFocus",
            "tab_cycle_keys": ["ButtonL1", "ButtonR1"],
            "close_keys": ["ButtonB"],
        },
    }
    return data


def validate_gui_map(spec: dict[str, Any]) -> list[str]:
    """Validate a GUI Mapping dictionary and return a list of issues (empty = valid)."""
    issues: list[str] = []

    min_touch = int(spec.get("min_touch_target_px", 0))
    if min_touch < MIN_TOUCH_TARGET_PX:
        issues.append(
            f"min_touch_target_px={min_touch} is below recommended {MIN_TOUCH_TARGET_PX}px."
        )

    overscan = float(spec.get("console_overscan_margin_scale", 0.0))
    if overscan < 0.04:
        issues.append(
            f"console_overscan_margin_scale={overscan:.3f} should be >= 0.05 for 10-foot TVs."
        )

    for core_name in spec.get("disabled_core_gui", []):
        if core_name not in VALID_CORE_GUI_TYPES:
            issues.append(f"Unknown CoreGuiType '{core_name}' in disabled_core_gui.")

    layers = spec.get("layers", [])
    if not layers:
        issues.append("No ScreenGui layers defined in 'layers'.")
        return issues

    seen_names: set[str] = set()
    seen_orders: dict[int, str] = {}
    covered_widgets: set[str] = set()

    for idx, layer in enumerate(layers):
        name = str(layer.get("name", "")).strip()
        if not name:
            issues.append(f"Layer index {idx} has empty name.")
            continue
        if name in seen_names:
            issues.append(f"Duplicate ScreenGui name '{name}'.")
        seen_names.add(name)

        order = layer.get("display_order")
        if not isinstance(order, int):
            issues.append(f"Layer '{name}' display_order must be an integer, got {order!r}.")
        else:
            if order in seen_orders:
                issues.append(
                    f"DisplayOrder collision at {order}: '{seen_orders[order]}' and '{name}'."
                )
            seen_orders[order] = name

        insets = str(layer.get("screen_insets", ""))
        if insets not in VALID_SCREEN_INSETS:
            issues.append(
                f"Layer '{name}' has invalid screen_insets='{insets}'. "
                f"Expected one of {sorted(VALID_SCREEN_INSETS)}."
            )

        zbehav = str(layer.get("zindex_behavior", ""))
        if zbehav not in VALID_ZINDEX_BEHAVIORS:
            issues.append(
                f"Layer '{name}' has invalid zindex_behavior='{zbehav}'."
            )
        elif zbehav != "Sibling":
            issues.append(
                f"Layer '{name}' uses zindex_behavior='{zbehav}'; 'Sibling' is required for CanvasGroup and clean isolation."
            )

        if layer.get("reset_on_spawn", True) and name not in ("ContextualPromptGui",):
            issues.append(
                f"Persistent layer '{name}' has reset_on_spawn=True (causes HUD/Modal flicker on respawn)."
            )

        if bool(layer.get("interactive", True)) and insets == "None" and name not in (
            "ModalBackdropGui",
            "LoadingTransitionGui",
        ):
            issues.append(
                f"Interactive layer '{name}' uses screen_insets='None'; interactive UI should use CoreUISafeInsets or TopbarSafeInsets."
            )

        for w in layer.get("widgets", ()):
            covered_widgets.add(str(w))

    hud_set = set(spec.get("hud_widgets", []))
    for req_hud in REQUIRED_HUD_WIDGETS:
        if req_hud not in hud_set and req_hud not in covered_widgets:
            issues.append(f"Missing required HUD widget '{req_hud}'.")

    modal_set = set(spec.get("modals", []))
    for req_modal in REQUIRED_MODALS:
        if req_modal not in modal_set and req_modal not in covered_widgets:
            issues.append(f"Missing required standard modal '{req_modal}'.")

    overlay_set = set(spec.get("overlays", []))
    for req_overlay in REQUIRED_OVERLAYS:
        if req_overlay not in overlay_set and req_overlay not in covered_widgets:
            issues.append(f"Missing required standard overlay '{req_overlay}'.")

    if not spec.get("has_loading_screen", False) and "LoadingTransitionGui" not in seen_names:
        issues.append("Missing ReplicatedFirst LoadingTransitionGui / loading screen.")

    return issues


def generate_starter_gui_manifest(spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate a normalized StarterGui + ReplicatedFirst installation manifest."""
    resolved = spec if spec is not None else get_standard_gui_map()
    issues = validate_gui_map(resolved)
    if issues:
        raise ValueError("Invalid GUI mapping spec:\n - " + "\n - ".join(issues))

    starter_gui_screens: list[dict[str, Any]] = []
    replicated_first_screens: list[dict[str, Any]] = []

    for layer in sorted(resolved["layers"], key=lambda item: int(item["display_order"])):
        entry = {
            "ClassName": "ScreenGui",
            "Name": layer["name"],
            "Properties": {
                "DisplayOrder": int(layer["display_order"]),
                "ScreenInsets": layer["screen_insets"],
                "ResetOnSpawn": bool(layer.get("reset_on_spawn", False)),
                "ZIndexBehavior": layer.get("zindex_behavior", "Sibling"),
                "Enabled": layer["name"] != "LoadingTransitionGui",
            },
            "Widgets": list(layer.get("widgets", ())),
            "SafeZoneNotes": layer.get("safe_zone_notes", ""),
        }
        if layer.get("parent_service", "StarterGui") == "ReplicatedFirst":
            replicated_first_screens.append(entry)
        else:
            starter_gui_screens.append(entry)

    return {
        "Title": resolved.get("title", "StandardGameGui"),
        "MinTouchTargetPx": int(resolved.get("min_touch_target_px", MIN_TOUCH_TARGET_PX)),
        "DisabledCoreGui": list(resolved.get("disabled_core_gui", [])),
        "StarterGui": starter_gui_screens,
        "ReplicatedFirst": replicated_first_screens,
        "PlatformRules": resolved.get("platform_rules", {}),
        "SafeZones": resolved.get("safe_zones", {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or export Standard Roblox Game GUI Mapping specs."
    )
    parser.add_argument(
        "--validate",
        type=Path,
        default=None,
        help="Path to a GUI mapping JSON file to validate.",
    )
    parser.add_argument(
        "--dump-standard",
        type=Path,
        default=None,
        help="Write the canonical standard GUI mapping JSON to this path.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Write the normalized StarterGui manifest JSON to this path.",
    )
    args = parser.parse_args(argv)

    if args.validate is not None:
        data = json.loads(args.validate.read_text(encoding="utf-8"))
        issues = validate_gui_map(data)
        if issues:
            print("VALIDATION FAILED:")
            for issue in issues:
                print(f" - {issue}")
            return 1
        print(f"VALID: {args.validate} passed all GUI mapping checks.")
        return 0

    standard = get_standard_gui_map()
    if args.dump_standard is not None:
        args.dump_standard.parent.mkdir(parents=True, exist_ok=True)
        args.dump_standard.write_text(json.dumps(standard, indent=2), encoding="utf-8")
        print(f"Wrote standard GUI mapping spec to {args.dump_standard}")

    if args.manifest is not None:
        manifest = generate_starter_gui_manifest(standard)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"Wrote StarterGui manifest to {args.manifest}")

    if args.dump_standard is None and args.manifest is None:
        issues = validate_gui_map(standard)
        print(json.dumps({"valid": len(issues) == 0, "issues": issues, "layers": len(standard["layers"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

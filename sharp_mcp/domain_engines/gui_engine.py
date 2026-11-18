"""GUI, 9-Slice, Atlas & StyleSheet Domain Engine (`roblox-gui`).

Embeds:
- `slice_and_atlas_helper.py` (background strip, 1-2px RGB alpha bleed, auto SliceCenter, 4px atlas packing)
- `gui_map_spec.py` (canonical 11-layer DisplayOrder & ScreenInsets specification)
- `generate_rbxmx_gui.py` (offline .rbxmx GUI package serializer)
- `ui_theme_and_components.luau` (StyleSheet / StyleRule token system & responsive rules)
- `build_standard_game_gui.luau` (live 11-layer StarterGui HUD/Modals/Shop/Dialog/Tooltip/Toast builder)
- `audit_gui.luau` (safe-zone, >=44px touch target, CanvasGroup VRAM, and StyleRule auditor)
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image

from .design_engine import DesignEngine


LAYOUT_PARADIGM_BLUEPRINTS: Dict[str, Dict[str, Any]] = {
    "arpg_orbs": {
        "paradigm_id": "arpg_orbs",
        "label": "ARPG Health/Mana Orbs & Bottom Skill Bar",
        "recommended_presets": ["rpg_arcane", "anime_neon"],
        "recommended_primitives": [
            "UIKit.CreateArcGauge",
            "UIKit.CreateGlossyButton",
            "UIKit.CreateBadgePill",
            "UIKit.CreateModalManager",
        ],
        "screen_layout": {
            "HealthOrb": "Bottom-left glowing crimson/primary liquid orb gauge (OrbMode = true, SweepAngleDeg = 360, clear of compact mobile thumbstick)",
            "ManaOrb": "Bottom-right glowing cyan/accent liquid orb gauge (OrbMode = true, SweepAngleDeg = 360)",
            "SkillBar": "Bottom-center 5x >=52px glossy ability buttons + slim XP arc/bar",
            "QuestChip": "Top-right compact collapsible quest banner",
        },
        "anti_slop_notes": [
            "Use circular liquid orbs + centered combat bar instead of generic top-left rectangle HUDs.",
            "Keep all interactive buttons >= 52px and ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local hud = Instance.new("ScreenGui")
hud.Name = "ArpgOrbsHudGui"
hud.DisplayOrder = 10
hud.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
hud.ResetOnSpawn = false
hud.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
hud.Parent = StarterGui
UIKit.BindResponsiveScale(hud, 0.86, 1.08)
local hpOrb = UIKit.CreateArcGauge({
	Name = "HealthOrb",
	Parent = hud,
	Size = UDim2.fromOffset(132, 132),
	Position = UDim2.new(0, 18, 1, -18),
	AnchorPoint = Vector2.new(0, 1),
	Label = "HP",
	Value = 860,
	Max = 1000,
	StartAngleDeg = 0,
	SweepAngleDeg = 360,
	OrbMode = true,
	GlowEnabled = true,
	FillColor = UIKit.Tokens.Colors.Danger,
	SecondaryColor = UIKit.Tokens.Colors.Primary,
})
local manaOrb = UIKit.CreateArcGauge({
	Name = "ManaOrb",
	Parent = hud,
	Size = UDim2.fromOffset(132, 132),
	Position = UDim2.new(1, -18, 1, -18),
	AnchorPoint = Vector2.new(1, 1),
	Label = "MANA",
	Value = 420,
	Max = 500,
	StartAngleDeg = 0,
	SweepAngleDeg = 360,
	OrbMode = true,
	GlowEnabled = true,
	FillColor = UIKit.Tokens.Colors.Accent,
	SecondaryColor = UIKit.Tokens.Colors.Secondary,
})
return { Hud = hud, HpOrb = hpOrb, ManaOrb = manaOrb }
""",
    },
    "scifi_visor_radial": {
        "paradigm_id": "scifi_visor_radial",
        "label": "Sci-Fi Visor Telemetry & Polar Radial Command Wheel",
        "recommended_presets": ["scifi_holo"],
        "recommended_primitives": [
            "UIKit.CreateRadialWheel",
            "UIKit.CreateArcGauge",
            "UIKit.CreatePanel",
            "UIKit.CreateBadgePill",
        ],
        "screen_layout": {
            "CommandWheel": "Center polar N-segment tactical radial wheel (SegmentSizePx >= 56, MinSize >= 44)",
            "ShieldArc": "Top-left curved energy/shield arc gauge with telemetry ticks",
            "VisorFrame": "Non-interactive holo_brackets corner HUD frames",
        },
        "anti_slop_notes": [
            "Use polar radial sectors instead of flat vertical list buttons.",
            "Keep every radial sector and center hub >= 44x44px.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local hud = Instance.new("ScreenGui")
hud.Name = "VisorRadialHudGui"
hud.DisplayOrder = 10
hud.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
hud.ResetOnSpawn = false
hud.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
hud.Parent = StarterGui
UIKit.BindResponsiveScale(hud, 0.86, 1.08)
local wheel = UIKit.CreateRadialWheel({
	Name = "TacticalWheel",
	Parent = hud,
	Position = UDim2.fromScale(0.5, 0.52),
	CenterTitle = "SYSTEMS",
	RadiusPx = 110,
	SegmentSizePx = 58,
})
local shieldArc = UIKit.CreateArcGauge({
	Name = "ShieldArc",
	Parent = hud,
	Size = UDim2.fromOffset(124, 124),
	Position = UDim2.fromOffset(16, 14),
	AnchorPoint = Vector2.zero,
	Label = "SHIELD",
	Unit = "%",
	Value = 92,
	Max = 100,
	FillColor = UIKit.Tokens.Colors.Primary,
	SecondaryColor = UIKit.Tokens.Colors.Accent,
})
return { Hud = hud, Wheel = wheel, ShieldArc = shieldArc }
""",
    },
    "cozy_book_journal": {
        "paradigm_id": "cozy_book_journal",
        "label": "Cozy Two-Page Open Book Journal & Bookmark Tabs",
        "recommended_presets": ["cozy_pastel", "candy_simulator"],
        "recommended_primitives": [
            "UIKit.CreateBookSpread",
            "UIKit.CreateBadgePill",
            "UIKit.CreateGlossyButton",
            "UIKit.CreateViewportPreview",
        ],
        "screen_layout": {
            "JournalSpread": "Centered two-page open book with SpineShadow, LeftPage, RightPage, and right-edge >=44px bookmark tabs",
            "LeftPage": "Illustrated title/item preview or ViewportFrame specimen",
            "RightPage": "Handcrafted quest checklist + reward claim button",
        },
        "anti_slop_notes": [
            "Build an authentic open-book spread with spine crease shadow and protruding bookmark tabs rather than a generic modal table.",
            "Keep right-edge bookmark tabs >= 44px tall and SpineShadow Active = false.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local journalGui = Instance.new("ScreenGui")
journalGui.Name = "CozyJournalGui"
journalGui.DisplayOrder = 50
journalGui.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
journalGui.ResetOnSpawn = false
journalGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
journalGui.Parent = StarterGui
UIKit.BindResponsiveScale(journalGui, 0.86, 1.08)
local book = UIKit.CreateBookSpread({
	Name = "FieldJournal",
	Parent = journalGui,
	BookTitle = "Field Almanac",
	Size = UDim2.fromOffset(660, 410),
	Position = UDim2.fromScale(0.5, 0.5),
})
local claimBtn = UIKit.CreateGlossyButton({
	Name = "HarvestClaimBtn",
	Parent = book.RightPage,
	Text = "Collect Harvest",
	Size = UDim2.fromOffset(180, 50),
	Position = UDim2.new(0.5, 0, 1, -12),
	AnchorPoint = Vector2.new(0.5, 1),
	Variant = "Success",
})
return { Gui = journalGui, Book = book, ClaimBtn = claimBtn }
""",
    },
    "card_battler_fan": {
        "paradigm_id": "card_battler_fan",
        "label": "Card Battler Curved Hand Fan & Mana Orb",
        "recommended_presets": ["rpg_arcane", "arcade_pop", "anime_neon"],
        "recommended_primitives": [
            "UIKit.CreateCardFan",
            "UIKit.CreateArcGauge",
            "UIKit.CreateGlossyButton",
            "UIKit.CreateBadgePill",
        ],
        "screen_layout": {
            "HandFan": "Bottom-center curved card fan across [-maxAngle, +maxAngle] with cost badges, body text, and hover lift",
            "ManaGauge": "Bottom-left circular energy gauge",
            "EndTurnBtn": "Bottom-right glossy End Turn action button (>=52px)",
        },
        "anti_slop_notes": [
            "Fan cards cleanly across [-maxAngle, +maxAngle] with parabolic Y drop instead of a flat horizontal grid.",
            "Keep hover-lifted card tops inside ScreenGui CoreUISafeInsets bounds.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local hud = Instance.new("ScreenGui")
hud.Name = "CardBattlerHudGui"
hud.DisplayOrder = 10
hud.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
hud.ResetOnSpawn = false
hud.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
hud.Parent = StarterGui
UIKit.BindResponsiveScale(hud, 0.86, 1.08)
local fan = UIKit.CreateCardFan({
	Name = "PlayerHandFan",
	Parent = hud,
	Position = UDim2.new(0.5, 0, 1, -8),
	MaxAngleDeg = 20,
	ArcDropPx = 22,
	HoverLiftPx = 22,
})
local mana = UIKit.CreateArcGauge({
	Name = "ManaGauge",
	Parent = hud,
	Size = UDim2.fromOffset(108, 108),
	Position = UDim2.new(0, 18, 1, -18),
	AnchorPoint = Vector2.new(0, 1),
	Label = "MANA",
	Value = 4,
	Max = 5,
	OrbMode = true,
	FillColor = UIKit.Tokens.Colors.Secondary,
	SecondaryColor = UIKit.Tokens.Colors.Accent,
})
local endTurn = UIKit.CreateGlossyButton({
	Name = "EndTurnBtn",
	Parent = hud,
	Text = "END TURN",
	Size = UDim2.fromOffset(132, 52),
	Position = UDim2.new(1, -18, 1, -24),
	AnchorPoint = Vector2.new(1, 1),
	Variant = "Primary",
})
return { Hud = hud, Fan = fan, Mana = mana, EndTurn = endTurn }
""",
    },
    "street_racer_cockpit": {
        "paradigm_id": "street_racer_cockpit",
        "label": "Street Racer Tachometer Arc & Nitro Telemetry",
        "recommended_presets": ["arcade_pop", "anime_neon", "scifi_holo"],
        "recommended_primitives": [
            "UIKit.CreateArcGauge",
            "UIKit.CreateBadgePill",
            "UIKit.CreateGlossyPanel",
            "UIKit.CreateShineSweep",
        ],
        "screen_layout": {
            "Speedometer": "Bottom-right large 270-deg arc gauge with needle, ticks, MPH unit, and glow",
            "NitroGauge": "Adjacent compact arc gauge for boost charge",
            "PositionBadge": "Top-left high-contrast race placement & lap pill",
        },
        "anti_slop_notes": [
            "Keep speedometer cluster clear of mobile right touch jump zone when compact.",
            "Use tabular Mono fonts for live speed and split timers so digits never jitter.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local hud = Instance.new("ScreenGui")
hud.Name = "RacerCockpitGui"
hud.DisplayOrder = 10
hud.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
hud.ResetOnSpawn = false
hud.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
hud.Parent = StarterGui
UIKit.BindResponsiveScale(hud, 0.86, 1.08)
local speedo = UIKit.CreateArcGauge({
	Name = "Speedometer",
	Parent = hud,
	Size = UDim2.fromOffset(172, 172),
	Position = UDim2.new(1, -20, 1, -20),
	AnchorPoint = Vector2.new(1, 1),
	Label = "SPEED",
	Unit = "MPH",
	Value = 148,
	Max = 220,
	StartAngleDeg = -135,
	SweepAngleDeg = 270,
	TickCount = 13,
	ShowNeedle = true,
	GlowEnabled = true,
})
local posPill = UIKit.CreateBadgePill({
	Name = "RaceRankPill",
	Parent = hud,
	Text = "POS 1 / 8  •  LAP 2/3",
	Size = UDim2.fromOffset(186, 36),
	Position = UDim2.fromOffset(16, 14),
	AnchorPoint = Vector2.zero,
	Rotation = 0,
	Color = UIKit.Tokens.Colors.Primary,
	TextSize = 13,
})
return { Hud = hud, Speedo = speedo, PosPill = posPill }
""",
    },
    "minimal_horror_cam": {
        "paradigm_id": "minimal_horror_cam",
        "label": "Minimal Diegetic Bodycam / Camcorder Overlay",
        "recommended_presets": ["scifi_holo", "rpg_arcane"],
        "recommended_primitives": [
            "UIKit.CreateArcGauge",
            "UIKit.CreateBadgePill",
            "UIKit.CreatePanel",
        ],
        "screen_layout": {
            "RecBadge": "Top-left minimal REC indicator & Mono timecode inside CoreUISafeInsets",
            "BatteryArc": "Top-right compact flashlight/stamina arc gauge",
            "ViewfinderCorners": "Thin non-interactive corner brackets (Active = false) leaving >=85% screen open",
        },
        "anti_slop_notes": [
            "Never clutter horror HUDs with opaque boxes; leave >=85% viewport clear.",
            "Set Active = false on all viewfinder overlay strokes/frames.",
        ],
        "starter_luau_example": """--!strict
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local UIKit = require(ReplicatedStorage:WaitForChild("UIThemeAndComponents")) :: any
local camGui = Instance.new("ScreenGui")
camGui.Name = "BodycamOverlayGui"
camGui.DisplayOrder = 10
camGui.ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets
camGui.ResetOnSpawn = false
camGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
camGui.Parent = StarterGui
UIKit.BindResponsiveScale(camGui, 0.86, 1.08)
local recPill = UIKit.CreateBadgePill({
	Name = "RecIndicator",
	Parent = camGui,
	Text = "REC  00:04:19",
	Size = UDim2.fromOffset(146, 32),
	Position = UDim2.fromOffset(18, 16),
	AnchorPoint = Vector2.zero,
	Rotation = 0,
	Color = UIKit.Tokens.Colors.Danger,
	TextSize = 13,
})
local battery = UIKit.CreateArcGauge({
	Name = "BatteryGauge",
	Parent = camGui,
	Size = UDim2.fromOffset(96, 96),
	Position = UDim2.new(1, -18, 0, 16),
	AnchorPoint = Vector2.new(1, 0),
	Label = "CELL",
	Unit = "%",
	Value = 64,
	Max = 100,
	ShowNeedle = false,
	GlowEnabled = false,
	FillColor = UIKit.Tokens.Colors.Accent,
})
return { Gui = camGui, RecPill = recPill, Battery = battery }
""",
    },
}


class GuiDomainEngine:
    def __init__(self, skills_dir: Path, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir
        self.skill_path = self._resolve_skill_path()

    def _resolve_skill_path(self) -> Path:
        p = self.skills_dir / "roblox-gui"
        if p.is_dir():
            return p
        bundled = Path(__file__).resolve().parent.parent / "bundled_skills" / "roblox-gui"
        if bundled.is_dir():
            return bundled
        if self.archive_dir:
            return self.archive_dir / "02_roblox_gui" / "skill"
        return p

    def _read_script(self, script_name: str) -> str:
        return (self.skill_path / "scripts" / script_name).read_text(encoding="utf-8")

    def _load_py_module(self, script_name: str, mod_alias: str) -> Any:
        py_path = self.skill_path / "scripts" / script_name
        scripts_dir = str(py_path.parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        spec = importlib.util.spec_from_file_location(mod_alias, py_path)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_alias] = mod
        prev_dwb = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = prev_dwb
        return mod

    def process_slice_and_atlas(
        self,
        output_dir: str,
        panel_source_path: Optional[str] = None,
        button_source_path: Optional[str] = None,
        icon_source_paths: Optional[List[str]] = None,
        alpha_bleed_px: int = 2,
        gutter_px: int = 4,
        export_rbxmx: bool = True,
        grid_rows: Optional[int] = None,
        grid_cols: Optional[int] = None,
        icon_names: Optional[List[str]] = None,
        cell_size: Optional[int] = None,
        max_dim: int = 512,
        skip_empty_cells: bool = False,
    ) -> Dict[str, Any]:
        """Processes 9-slice panels/buttons and packs arbitrary RxC icon atlases with RGB alpha bleed."""
        helper = self._load_py_module("slice_and_atlas_helper.py", "sharp_slice_helper")
        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)
        safe_max_dim = max(16, min(int(max_dim), 1024))

        staged_files: List[Path] = []
        results: Dict[str, Any] = {"ok": True, "output_dir": str(out_path), "assets": {}}

        if panel_source_path and Path(panel_source_path).is_file():
            p_out = out_path / "panel_9slice.png"
            meta = helper.prepare_nine_slice_png(
                input_path=str(Path(panel_source_path).resolve()),
                output_path=str(p_out),
                max_dim=safe_max_dim,
                bleed_px=max(1, alpha_bleed_px),
            )
            results["assets"]["panel_9slice"] = meta
            results["panel_9slice"] = meta
            staged_files.append(p_out)

        if button_source_path and Path(button_source_path).is_file():
            b_out = out_path / "button_9slice.png"
            meta = helper.prepare_nine_slice_png(
                input_path=str(Path(button_source_path).resolve()),
                output_path=str(b_out),
                max_dim=safe_max_dim,
                bleed_px=max(1, alpha_bleed_px),
            )
            results["assets"]["button_9slice"] = meta
            results["button_9slice"] = meta
            staged_files.append(b_out)

        valid_icons = [str(Path(p).resolve()) for p in (icon_source_paths or []) if Path(p).is_file()]
        if valid_icons:
            a_out = out_path / "icons_atlas.png"
            stem_l = Path(valid_icons[0]).stem.lower()
            rxc_match = re.search(r"(\d+)x(\d+)", stem_l)
            is_grid_sheet = len(valid_icons) == 1 and (
                grid_rows is not None
                or grid_cols is not None
                or rxc_match is not None
                or any(tag in stem_l for tag in ("grid", "sheet"))
            )
            if is_grid_sheet:
                det_rows = int(rxc_match.group(1)) if rxc_match else 2
                det_cols = int(rxc_match.group(2)) if rxc_match else 2
                rows = max(1, int(grid_rows if grid_rows is not None else det_rows))
                cols = max(1, int(grid_cols if grid_cols is not None else det_cols))
                if icon_names is not None:
                    resolved_names: Optional[List[str]] = list(icon_names)
                elif rows == 2 and cols == 2:
                    resolved_names = ["coin", "gem", "combat", "chest"]
                else:
                    resolved_names = None
                eff_cell = int(cell_size) if cell_size is not None else 256
                atlas_meta = helper.split_grid_and_pack_atlas(
                    input_path=valid_icons[0],
                    output_path=str(a_out),
                    rows=rows,
                    cols=cols,
                    names=resolved_names,
                    cell_size=eff_cell,
                    gutter=max(4, gutter_px),
                    bleed_px=max(1, alpha_bleed_px),
                    auto_fit_cell_size=True,
                    tight_trim=True,
                    skip_empty_cells=skip_empty_cells,
                )
            else:
                icon_dict: Dict[str, str | Path] = {}
                for idx, p_str in enumerate(valid_icons):
                    if icon_names and idx < len(icon_names) and icon_names[idx]:
                        key = str(icon_names[idx])
                    else:
                        stem = Path(p_str).stem
                        key = f"{stem}_{idx}" if stem in icon_dict else stem
                    icon_dict[key] = p_str
                atlas_meta = helper.pack_icon_atlas(
                    icon_paths=icon_dict,
                    output_path=str(a_out),
                    cell_size=int(cell_size) if cell_size is not None else 128,
                    gutter=max(4, gutter_px),
                    bleed_px=max(1, alpha_bleed_px),
                    key_background=True,
                    auto_fit_cell_size=True,
                )
            results["assets"]["icons_atlas"] = atlas_meta
            results["icon_atlas"] = atlas_meta
            staged_files.append(a_out)

        if export_rbxmx:
            rbxmx_gen = self._load_py_module("generate_rbxmx_gui.py", "sharp_rbxmx_gui")
            rbxmx_file = out_path / "SharpStandardGameGui.rbxmx"
            rbxmx_gen.generate_standard_gui_rbxmx(str(rbxmx_file))
            results["rbxmx_path"] = str(rbxmx_file)

        results["staged_file_paths"] = [str(p) for p in staged_files]
        return results

    def get_gui_map_spec_summary(self) -> Dict[str, Any]:
        spec_mod = self._load_py_module("gui_map_spec.py", "sharp_gui_map_spec")
        raw_layers = getattr(spec_mod, "STANDARD_LAYERS", getattr(spec_mod, "STANDARD_GUI_LAYERS", ()))
        layers = [asdict(item) if is_dataclass(item) else item for item in raw_layers]
        return {
            "layer_count": len(layers),
            "layers": layers,
        }

    def _prepare_theme_source_and_assets(
        self,
        panel_asset_id: str = "",
        button_asset_id: str = "",
        atlas_asset_id: str = "",
        design_system: Optional[Dict[str, Any] | str] = None,
    ) -> tuple[str, Dict[str, str]]:
        """Inject optional asset IDs and DesignTheme tokens into ui_theme_and_components.luau."""
        theme_src = self._read_script("ui_theme_and_components.luau")

        asset_overrides: Dict[str, str] = {}
        luau_override_entries: List[str] = []
        if panel_asset_id:
            asset_overrides["Panel9SliceId"] = panel_asset_id
            luau_override_entries.append(f"\tPanel9SliceId = {json.dumps(panel_asset_id)},")
        if button_asset_id:
            asset_overrides["Button9SliceId"] = button_asset_id
            luau_override_entries.append(f"\tButton9SliceId = {json.dumps(button_asset_id)},")
        if atlas_asset_id:
            asset_overrides["IconAtlasId"] = atlas_asset_id
            luau_override_entries.append(f"\tIconAtlasId = {json.dumps(atlas_asset_id)},")

        if luau_override_entries:
            override_block = "{\n" + "\n".join(luau_override_entries) + "\n}"
            assets_pattern = re.compile(r"UIKit\.Assets\s*=\s*\{\}\s*::\s*AssetOverrides")
            if assets_pattern.search(theme_src):
                theme_src = assets_pattern.sub(
                    lambda _: f"UIKit.Assets = {override_block} :: AssetOverrides",
                    theme_src,
                    count=1,
                )
            else:
                theme_src = theme_src.replace(
                    "return UIKit",
                    f"UIKit.SetAssets({override_block})\nreturn UIKit",
                    1,
                )

        if design_system:
            design_engine = DesignEngine(self.skills_dir, self.archive_dir)
            if isinstance(design_system, str):
                stripped = design_system.strip()
                if stripped.startswith("{"):
                    ds_obj: Dict[str, Any] = json.loads(stripped)
                else:
                    ds_obj = design_engine.generate_design_system(
                        game_title="Custom Experience",
                        genre=stripped,
                    )
            else:
                ds_obj = design_system
            theme_block = design_engine.compile_theme_luau(ds_obj, module_mode=False).replace("]========]", "]=======]")
            idx = theme_src.rfind("return UIKit")
            if idx != -1:
                theme_src = (
                    theme_src[:idx]
                    + f"\n{theme_block}\nUIKit.ApplyDesignSystem(DesignTheme)\n"
                    + theme_src[idx:]
                )
            else:
                theme_src = theme_src + f"\n{theme_block}\nUIKit.ApplyDesignSystem(DesignTheme)\n"

        return theme_src, asset_overrides

    def get_custom_ui_authoring_guide(
        self,
        paradigm: str = "arpg_orbs",
        design_system: Optional[Dict[str, Any] | str] = None,
    ) -> Dict[str, Any]:
        """Return custom UI layout blueprint, UIKit composable primitive contracts, and design tokens."""
        norm = str(paradigm or "arpg_orbs").strip().lower()
        available = list(LAYOUT_PARADIGM_BLUEPRINTS.keys())

        resolved_ds: Optional[Dict[str, Any]] = None
        if design_system:
            design_engine = DesignEngine(self.skills_dir, self.archive_dir)
            if isinstance(design_system, str):
                stripped = design_system.strip()
                if stripped.startswith("{"):
                    resolved_ds = json.loads(stripped)
                else:
                    resolved_ds = design_engine.generate_design_system("Custom Experience", genre=stripped)
            elif isinstance(design_system, dict):
                resolved_ds = design_system

        tokens_summary: Optional[Dict[str, Any]] = None
        if isinstance(resolved_ds, dict):
            tokens_summary = {
                "game_title": resolved_ds.get("game_title"),
                "preset_id": resolved_ds.get("preset_id"),
                "surface_mode": resolved_ds.get("surface_mode"),
                "texture_style": resolved_ds.get("texture_style"),
                "asset_style": resolved_ds.get("asset_style"),
                "palette": resolved_ds.get("palette"),
                "typography": (resolved_ds.get("tokens") or {}).get("typography"),
                "radii": (resolved_ds.get("tokens") or {}).get("radii"),
            }

        uikit_primitives = [
            {
                "name": "UIKit.CreateArcGauge(opts)",
                "purpose": "Circular/arc progress & speedometer/liquid-orb widget with label, value/max, ticks, needle, and optional glow.",
                "key_options": ["Name", "Parent", "Size", "Position", "AnchorPoint", "Label", "Unit", "Value", "Max", "StartAngleDeg", "SweepAngleDeg", "TickCount", "FillColor", "SecondaryColor", "GlowEnabled", "ShowNeedle", "OrbMode"],
            },
            {
                "name": "UIKit.CreateRadialWheel(opts)",
                "purpose": "Polar N-segment radial menu with sector buttons, icons/labels, center hub, and >=44px touch targets.",
                "key_options": ["Name", "Parent", "Position", "RadiusPx", "SegmentSizePx", "HubSizePx", "StartAngleDeg", "CenterTitle", "Items", "OnSelect", "OnCenterClick"],
            },
            {
                "name": "UIKit.CreateCardFan(opts)",
                "purpose": "Curved hand of cards across [-MaxAngleDeg, +MaxAngleDeg] with parabolic ArcDropPx, cost badge, body text, and hover lift.",
                "key_options": ["Name", "Parent", "Size", "Position", "CardSize", "MaxAngleDeg", "ArcDropPx", "HoverLiftPx", "Cards", "OnCardClick"],
            },
            {
                "name": "UIKit.CreateBookSpread(opts)",
                "purpose": "Two-page open book/journal with spine shadow, right-edge >=44px bookmark tabs, LeftPage & RightPage frames.",
                "key_options": ["Name", "Parent", "Size", "Position", "BookTitle", "Tabs", "PageColor", "CoverColor", "ShowClose", "OnTabChanged", "OnClose"],
            },
            {
                "name": "UIKit.CreateGlossyPanel / UIKit.CreateGlossyButton / UIKit.CreateBadgePill / UIKit.CreateModalManager",
                "purpose": "Supporting glossy beveled containers, buttons, tilted pills, sliders, toggles, tooltips, toasts, and 3D ViewportFrame previews.",
                "key_options": ["Name", "Parent", "Size", "Position", "Variant", "Text", "Title", "OnClick"],
            },
        ]

        rules = [
            "Start custom_builder_luau with `--!strict` and avoid semicolons.",
            "Every persistent ScreenGui must be a direct child of StarterGui with ResetOnSpawn=false, ZIndexBehavior=Enum.ZIndexBehavior.Sibling, and explicit ScreenInsets (CoreUISafeInsets for HUD/modals).",
            "Call UIKit.BindResponsiveScale(gui, 0.86, 1.08) and ensure all interactive buttons meet >= 44x44px (>= 52px recommended).",
            "Never hardcode flat dark-navy/blue boxes; read colors/fonts/radii from UIKit.Tokens and compose UIKit primitives.",
            "NO DEAD UI: Wire every HUD widget and button to live runtime signals (Humanoid.HealthChanged for HP, RenderStepped/RemoteEvent sync for charge/cooldown/reload/ammo, Activated/UserInputService for buttons), and grant player weapons via StarterPack Tool + Humanoid:EquipTool.",
        ]

        if norm == "all":
            return {
                "ok": True,
                "paradigm": "all",
                "available_paradigms": available,
                "blueprints": LAYOUT_PARADIGM_BLUEPRINTS,
                "uikit_primitives": uikit_primitives,
                "design_tokens_summary": tokens_summary,
                "rules": rules,
            }

        if norm not in LAYOUT_PARADIGM_BLUEPRINTS:
            return {
                "ok": False,
                "error": f"Unknown layout paradigm '{paradigm}'.",
                "available_paradigms": available,
                "uikit_primitives": uikit_primitives,
                "design_tokens_summary": tokens_summary,
            }

        blueprint = dict(LAYOUT_PARADIGM_BLUEPRINTS[norm])
        return {
            "ok": True,
            "paradigm": norm,
            "blueprint": blueprint,
            "starter_luau": blueprint["starter_luau_example"],
            "available_paradigms": available,
            "uikit_primitives": uikit_primitives,
            "design_tokens_summary": tokens_summary,
            "rules": rules,
        }

    def compile_custom_gui_build_luau(
        self,
        custom_builder_luau: str,
        *,
        panel_asset_id: str = "",
        button_asset_id: str = "",
        atlas_asset_id: str = "",
        run_audit_after: bool = True,
        design_system: Optional[Dict[str, Any] | str] = None,
        clear_previous_sharp_guis: bool = True,
    ) -> str:
        """Compile a bespoke custom GUI builder script with UIKit, DesignTheme, UIStyles, ChangeHistory, and audit."""
        if not isinstance(custom_builder_luau, str) or not custom_builder_luau.strip():
            raise ValueError("custom_builder_luau must be a non-empty Luau string.")

        theme_src, asset_overrides = self._prepare_theme_source_and_assets(
            panel_asset_id=panel_asset_id,
            button_asset_id=button_asset_id,
            atlas_asset_id=atlas_asset_id,
            design_system=design_system,
        )
        audit_src = self._read_script("audit_gui.luau")
        assets_json = json.dumps(asset_overrides)
        custom_body = custom_builder_luau.rstrip() + "\n"

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local CollectionService = game:GetService("CollectionService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local StarterGui = game:GetService("StarterGui")
local StarterPlayer = game:GetService("StarterPlayer")

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpCustomGuiBuild", "Sharp MCP: Build Custom Game GUI & StyleSheet")
local ok, resOrErr = xpcall(function()
	local oldMod = ReplicatedStorage:FindFirstChild("UIThemeAndComponents")
	if oldMod then oldMod:Destroy() end

	local themeMod = Instance.new("ModuleScript")
	themeMod.Name = "UIThemeAndComponents"
	themeMod.Source = [========[{theme_src}]========]
	themeMod.Parent = ReplicatedStorage

	local UIKit = require(themeMod) :: any
	local customAssets = HttpService:JSONDecode({json.dumps(assets_json)})
	if next(customAssets) ~= nil then
		_G.ROBLOX_GUI_ASSETS = customAssets
		UIKit.SetAssets(customAssets)
	end

	local clearPrev = {"true" if clear_previous_sharp_guis else "false"}
	if clearPrev then
		local standardGuiNames: {{ [string]: boolean }} = {{
			BackdropVignetteGui = true,
			MainHudGui = true,
			TopbarWidgetsGui = true,
			ContextualPromptGui = true,
			ModalBackdropGui = true,
			ModalMenusGui = true,
			NpcDialogGui = true,
			ConfirmDialogGui = true,
			FloatingTooltipGui = true,
			ToastNotificationGui = true,
		}}
		for _, child in ipairs(StarterGui:GetChildren()) do
			if child:IsA("ScreenGui") and (standardGuiNames[child.Name] or child:GetAttribute("SharpManagedGui") == true or CollectionService:HasTag(child, "SharpManagedGui")) then
				child:Destroy()
			end
		end
		local oldModels = ReplicatedStorage:FindFirstChild("GuiPreviewModels")
		if oldModels then oldModels:Destroy() end
		local oldTpl = ReplicatedStorage:FindFirstChild("LoadingTransitionTemplate")
		if oldTpl then oldTpl:Destroy() end
		local sps = StarterPlayer:FindFirstChild("StarterPlayerScripts")
		if sps then
			local oldCtrl = sps:FindFirstChild("StandardGuiController")
			if oldCtrl then oldCtrl:Destroy() end
		end
	end

	local existingStarterGuis: {{ [Instance]: boolean }} = {{}}
	for _, child in ipairs(StarterGui:GetChildren()) do
		if child:IsA("ScreenGui") then
			existingStarterGuis[child] = true
		end
	end

	UIKit.BuildStyleSheet(ReplicatedStorage)

	local customBuilderFn = function()
{custom_body}
	end
	local buildRes = customBuilderFn()
	_G.ROBLOX_GUI_ASSETS = nil

	local stylesFolder = ReplicatedStorage:FindFirstChild("UIStyles")
	local activeDesignSheet = if stylesFolder then stylesFolder:FindFirstChild("DesignSheet") else nil
	if not activeDesignSheet or not activeDesignSheet:IsA("StyleSheet") then
		activeDesignSheet = UIKit.BuildStyleSheet(ReplicatedStorage)
	end

	local createdScreenGuis: {{ string }} = {{}}
	for _, child in ipairs(StarterGui:GetChildren()) do
		if child:IsA("ScreenGui") then
			if not existingStarterGuis[child] then
				child:SetAttribute("SharpManagedGui", true)
				CollectionService:AddTag(child, "SharpManagedGui")
				table.insert(createdScreenGuis, child.Name)
			end
			if activeDesignSheet and activeDesignSheet:IsA("StyleSheet") and child:FindFirstChildOfClass("StyleLink") == nil then
				UIKit.AttachStyleLink(child, activeDesignSheet)
			end
		end
	end

	local auditRes = nil
	if {"true" if run_audit_after else "false"} then
		task.wait(0.05)
		local auditFn = function()
{audit_src}
		end
		local rawAudit = auditFn()
		if type(rawAudit) == "string" then
			local okDec, decoded = pcall(function() return HttpService:JSONDecode(rawAudit) end)
			auditRes = if okDec then decoded else rawAudit
		else
			auditRes = rawAudit
		end
	end

	return {{
		mode = "custom",
		createdScreenGuis = createdScreenGuis,
		buildResult = buildRes,
		auditReport = auditRes,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	mode = "custom",
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    def compile_gui_build_luau(
        self,
        panel_asset_id: str = "",
        button_asset_id: str = "",
        atlas_asset_id: str = "",
        run_audit_after: bool = True,
        design_system: Optional[Dict[str, Any] | str] = None,
    ) -> str:
        theme_src, asset_overrides = self._prepare_theme_source_and_assets(
            panel_asset_id=panel_asset_id,
            button_asset_id=button_asset_id,
            atlas_asset_id=atlas_asset_id,
            design_system=design_system,
        )
        builder_src = self._read_script("build_standard_game_gui.luau")
        audit_src = self._read_script("audit_gui.luau")

        assets_json = json.dumps(asset_overrides)

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpGuiBuild", "Sharp MCP: Build 11-Layer Game GUI & StyleSheet")
local ok, resOrErr = xpcall(function()
	local oldMod = ReplicatedStorage:FindFirstChild("UIThemeAndComponents")
	if oldMod then oldMod:Destroy() end

	local themeMod = Instance.new("ModuleScript")
	themeMod.Name = "UIThemeAndComponents"
	themeMod.Source = [========[{theme_src}]========]
	themeMod.Parent = ReplicatedStorage

	local customAssets = HttpService:JSONDecode({json.dumps(assets_json)})
	if next(customAssets) ~= nil then
		_G.ROBLOX_GUI_ASSETS = customAssets
	end

	local builderFn = function()
{builder_src}
	end
	local buildRes = builderFn()
	_G.ROBLOX_GUI_ASSETS = nil

	local auditRes = nil
	if {"true" if run_audit_after else "false"} then
		local StarterGui = game:GetService("StarterGui")
		local mainHud = StarterGui:FindFirstChild("MainHudGui")
		local rail = mainHud and mainHud:FindFirstChild("SideRail")
		local t0 = os.clock()
		while rail and rail.AbsoluteSize.X < 10 and (os.clock() - t0) < 1.0 do
			task.wait(0.05)
		end
		task.wait(0.05)
		local auditFn = function()
{audit_src}
		end
		local rawAudit = auditFn()
		if type(rawAudit) == "string" then
			local okDec, decoded = pcall(function() return HttpService:JSONDecode(rawAudit) end)
			auditRes = if okDec then decoded else rawAudit
		else
			auditRes = rawAudit
		end
	end

	return {{
		buildResult = buildRes,
		auditReport = auditRes,
	}}
end, debug.traceback)

if recId then
	pcall(function()
		ChangeHistoryService:FinishRecording(
			recId,
			if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel
		)
	end)
end

if not ok then
	error(resOrErr)
end

return HttpService:JSONEncode({{
	ok = true,
	recordingStatus = if (recId or activePluginRec) then "Committed" else "NoRecording",
	result = resOrErr,
}})
"""

    @staticmethod
    def build_inspect_module_op(
        *,
        root_path: Optional[str] = None,
        root_handle: Optional[str] = None,
        target: Optional[str] = None,
        max_depth: int = 5,
        include_props: bool = False,
        include_style_sheets: bool = True,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.inspect module op payload."""
        args: Dict[str, Any] = {
            "maxDepth": max(0, min(12, int(max_depth))),
            "includeProps": bool(include_props),
            "includeStyleSheets": bool(include_style_sheets),
        }
        if root_path:
            args["rootPath"] = root_path
        if root_handle:
            args["rootHandle"] = root_handle
        if target:
            args["target"] = target
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "inspect",
            "kind": "read",
            "args": args,
        }

    @staticmethod
    def build_patch_module_op(
        *,
        patches: Optional[List[Dict[str, Any]]] = None,
        path: Optional[str] = None,
        sharp_handle: Optional[str] = None,
        set_properties: Optional[Dict[str, Any]] = None,
        reset_properties: Optional[List[str]] = None,
        style_rule_updates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.patch module op payload."""
        args: Dict[str, Any] = {}
        if patches is not None:
            args["patches"] = patches
        if path:
            args["path"] = path
        if sharp_handle:
            args["sharpHandle"] = sharp_handle
        if set_properties is not None:
            args["setProperties"] = set_properties
        if reset_properties is not None:
            args["resetProperties"] = reset_properties
        if style_rule_updates is not None:
            args["styleRuleUpdates"] = style_rule_updates
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "patch",
            "kind": "write",
            "args": args,
        }

    @staticmethod
    def build_device_sim_module_op(
        *,
        action: str = "get_device",
        device_id: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        orientation: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build a declarative SharpGuiTools.deviceSim module op payload."""
        args: Dict[str, Any] = {"action": action}
        if device_id is not None:
            args["deviceId"] = device_id
        if width is not None:
            args["width"] = int(width)
        if height is not None:
            args["height"] = int(height)
        if orientation is not None:
            args["orientation"] = orientation
        read_actions = {"get_device", "list_devices"}
        return {
            "mode": "module_op",
            "module": "SharpGuiTools",
            "op": "deviceSim",
            "kind": "read" if action in read_actions else "write",
            "args": args,
        }

    @staticmethod
    def compute_visual_diff(
        before_path: str | Path,
        after_path: str | Path,
        diff_out_path: Optional[str | Path] = None,
        threshold: int = 8,
    ) -> Dict[str, Any]:
        """Compare two RGBA screenshots using Pillow + numpy, detect blank frames, and optionally emit a diff image."""
        return compute_visual_diff(
            before_path=before_path,
            after_path=after_path,
            diff_out_path=diff_out_path,
            threshold=threshold,
        )


def compute_visual_diff(
    before_path: str | Path,
    after_path: str | Path,
    diff_out_path: Optional[str | Path] = None,
    threshold: int = 8,
) -> Dict[str, Any]:
    """Compare two images pixel-by-pixel with RGBA alignment, blank detection, and bounding-box delta."""
    p_before = Path(before_path).expanduser()
    p_after = Path(after_path).expanduser()
    if not p_before.is_file():
        return {"ok": False, "error": f"Before image not found: {p_before}"}
    if not p_after.is_file():
        return {"ok": False, "error": f"After image not found: {p_after}"}

    before_bytes = p_before.read_bytes()
    after_bytes = p_after.read_bytes()
    sha_before = hashlib.sha256(before_bytes).hexdigest()
    sha_after = hashlib.sha256(after_bytes).hexdigest()

    img_before = Image.open(p_before).convert("RGBA")
    img_after = Image.open(p_after).convert("RGBA")
    orig_before_size = list(img_before.size)
    orig_after_size = list(img_after.size)
    size_aligned = img_before.size != img_after.size
    if size_aligned:
        img_after = img_after.resize(img_before.size, Image.Resampling.BILINEAR)

    width, height = img_before.size
    arr_before = np.asarray(img_before, dtype=np.int16)
    arr_after = np.asarray(img_after, dtype=np.int16)

    before_is_blank = bool(
        arr_before[:, :, 3].max() == 0
        or float(arr_before[:, :, :3].reshape(-1, 3).std(axis=0).max()) < 1.0
    )
    after_is_blank = bool(
        arr_after[:, :, 3].max() == 0
        or float(arr_after[:, :, :3].reshape(-1, 3).std(axis=0).max()) < 1.0
    )

    abs_diff = np.abs(arr_before - arr_after)
    max_per_pixel = abs_diff.max(axis=2)
    changed_mask = max_per_pixel > int(threshold)

    total_pixels = int(width * height)
    changed_pixels = int(changed_mask.sum())
    changed_ratio = round(changed_pixels / max(1, total_pixels), 6)
    max_channel_delta = int(abs_diff.max()) if total_pixels > 0 else 0
    mean_delta = round(float(abs_diff.mean()), 4) if total_pixels > 0 else 0.0

    diff_bbox: Optional[List[int]] = None
    if changed_pixels > 0:
        ys, xs = np.where(changed_mask)
        diff_bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]

    written_diff_path: Optional[str] = None
    if diff_out_path is not None:
        out_p = Path(diff_out_path).expanduser()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        overlay = (arr_after.astype(np.float32) * 0.35).astype(np.uint8)
        overlay[:, :, 3] = 255
        overlay[changed_mask] = np.array([255, 48, 96, 255], dtype=np.uint8)
        Image.fromarray(overlay, mode="RGBA").save(out_p, format="PNG")
        written_diff_path = str(out_p)

    return {
        "ok": True,
        "sha256_before": sha_before,
        "sha256_after": sha_after,
        "width": width,
        "height": height,
        "size_aligned": size_aligned,
        "original_before_size": orig_before_size,
        "original_after_size": orig_after_size,
        "blank_frame_detected": before_is_blank or after_is_blank,
        "before_is_blank": before_is_blank,
        "after_is_blank": after_is_blank,
        "threshold": int(threshold),
        "total_pixels": total_pixels,
        "changed_pixels": changed_pixels,
        "changed_ratio": changed_ratio,
        "max_channel_delta": max_channel_delta,
        "mean_delta": mean_delta,
        "diff_bbox": diff_bbox,
        "diff_image_path": written_diff_path,
    }


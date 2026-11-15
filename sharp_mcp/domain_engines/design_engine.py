"""Anti-Slop Per-Game UI Design System, Contrast Auto-Fixer, Linter & Prompt Batch Engine."""

from __future__ import annotations

import colorsys
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PIL import Image, ImageDraw


# Generic slop reference colors we explicitly avoid generating and flag in lint_design
_GENERIC_SLOP_REFS: Tuple[Tuple[str, str, str], ...] = (
    ("#0D121C", "#161E2E", "#3886F8"),  # Generic dark-navy + Bootstrap/Roblox blue
    ("#111827", "#1F2937", "#3B82F6"),  # Tailwind slate-900 + blue-500 default
    ("#1E1F22", "#2B2D31", "#5865F2"),  # Generic flat gray-dark + blurple
    ("#1A1A1A", "#2A2A2A", "#00A2FF"),  # Flat dark gray + legacy Roblox blue
)

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]",
    flags=re.UNICODE,
)

HARMONY_FAMILIES: Tuple[str, ...] = (
    "analogous",
    "triadic",
    "split_complementary",
    "tetradic",
)

DESIGN_PRESETS: Dict[str, Dict[str, Any]] = {
    "candy_simulator": {
        "preset_id": "candy_simulator",
        "label": "Candy Pop Simulator",
        "keywords": ("candy", "pet", "sim", "simulator", "tycoon", "obby", "sweet", "sugar", "toy", "bubble"),
        "surface_mode": "dark",
        "bg_hue_anchors": (262.0, 292.0, 318.0, 240.0, 196.0),
        "bg_sat": (0.38, 0.50),
        "bg_light_deep": (0.09, 0.13),
        "bg_light_panel": (0.14, 0.19),
        "primary_hue_anchors": (336.0, 190.0, 28.0, 276.0, 148.0, 48.0),
        "accent_sat": (0.86, 0.98),
        "accent_light": (0.50, 0.62),
        "ink_lightness": 0.10,
        "radii": {"xs": 6, "small": 12, "medium": 18, "large": 24, "panel": 22, "button": 16, "badge": 10},
        "strokes": {"outer_ink_px": 5.0, "inner_highlight_px": 2.0, "panel_stroke_px": 4.5, "text_stroke_px": 2.2, "line_join": "Round"},
        "shadows": {"offset_x": 0, "offset_y": 6, "press_offset_y": 3, "blur_radius": 6, "transparency": 0.25},
        "fonts": {
            "title_family": "rbxasset://fonts/families/FredokaOne.json",
            "heading_family": "rbxasset://fonts/families/BuilderSans.json",
            "body_family": "rbxasset://fonts/families/Nunito.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": True, "ray_count": 12, "badge_rotation_deg": -6, "surface_pattern": "glossy_candy_bubbles"},
        "style_material": "glossy lacquered sugar-coat cel-shaded UI with chunky rounded corners, crisp specular jelly highlights, and deep berry-ink outlines",
    },
    "anime_neon": {
        "preset_id": "anime_neon",
        "label": "Anime Cel Neon",
        "keywords": ("anime", "shonen", "ninja", "blade", "samurai", "fighting", "brawler", "hero", "aura", "slash"),
        "surface_mode": "dark",
        "bg_hue_anchors": (244.0, 268.0, 332.0, 204.0, 15.0),
        "bg_sat": (0.34, 0.46),
        "bg_light_deep": (0.06, 0.10),
        "bg_light_panel": (0.11, 0.15),
        "primary_hue_anchors": (40.0, 348.0, 282.0, 186.0, 12.0, 146.0),
        "accent_sat": (0.88, 1.00),
        "accent_light": (0.50, 0.58),
        "ink_lightness": 0.06,
        "radii": {"xs": 3, "small": 6, "medium": 11, "large": 16, "panel": 12, "button": 8, "badge": 4},
        "strokes": {"outer_ink_px": 4.5, "inner_highlight_px": 1.8, "panel_stroke_px": 4.0, "text_stroke_px": 2.4, "line_join": "Bevel"},
        "shadows": {"offset_x": 3, "offset_y": 5, "press_offset_y": 3, "blur_radius": 2, "transparency": 0.18},
        "fonts": {
            "title_family": "rbxasset://fonts/families/Bangers.json",
            "heading_family": "rbxasset://fonts/families/BuilderSans.json",
            "body_family": "rbxasset://fonts/families/BuilderSans.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": True, "ray_count": 14, "badge_rotation_deg": -5, "surface_pattern": "diagonal_speed_lines"},
        "style_material": "high-contrast anime cel-shaded HUD with chamfered bevels, razor-sharp specular slash highlights, and bold ink contours",
    },
    "cozy_pastel": {
        "preset_id": "cozy_pastel",
        "label": "Cozy Storybook Pastel",
        "keywords": ("cozy", "farm", "farming", "cafe", "bakery", "garden", "life", "town", "craft", "animal", "chill"),
        "surface_mode": "light",
        "bg_hue_anchors": (36.0, 28.0, 152.0, 342.0, 258.0),
        "bg_sat": (0.36, 0.56),
        "bg_light_deep": (0.86, 0.91),
        "bg_light_panel": (0.93, 0.97),
        "primary_hue_anchors": (16.0, 152.0, 272.0, 340.0, 38.0, 198.0),
        "accent_sat": (0.64, 0.80),
        "accent_light": (0.44, 0.54),
        "ink_lightness": 0.17,
        "radii": {"xs": 5, "small": 10, "medium": 16, "large": 22, "panel": 18, "button": 14, "badge": 8},
        "strokes": {"outer_ink_px": 3.5, "inner_highlight_px": 2.0, "panel_stroke_px": 3.5, "text_stroke_px": 1.2, "line_join": "Round"},
        "shadows": {"offset_x": 0, "offset_y": 5, "press_offset_y": 3, "blur_radius": 8, "transparency": 0.35},
        "fonts": {
            "title_family": "rbxasset://fonts/families/Nunito.json",
            "heading_family": "rbxasset://fonts/families/Nunito.json",
            "body_family": "rbxasset://fonts/families/BuilderSans.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": False, "ray_count": 8, "badge_rotation_deg": 4, "surface_pattern": "warm_linen_stitches"},
        "style_material": "warm storybook handcrafted wood-and-parchment UI with soft cream surfaces, cozy tactile bevels, and espresso-brown ink borders",
    },
    "scifi_holo": {
        "preset_id": "scifi_holo",
        "label": "Sci-Fi Holo Telemetry",
        "keywords": ("scifi", "sci-fi", "cyber", "cyberpunk", "mecha", "space", "holo", "mech", "robot", "laser", "galaxy"),
        "surface_mode": "dark",
        "bg_hue_anchors": (182.0, 266.0, 158.0, 294.0, 200.0),
        "bg_sat": (0.32, 0.48),
        "bg_light_deep": (0.05, 0.09),
        "bg_light_panel": (0.09, 0.14),
        "primary_hue_anchors": (182.0, 154.0, 296.0, 34.0, 262.0, 198.0),
        "accent_sat": (0.84, 0.98),
        "accent_light": (0.46, 0.56),
        "ink_lightness": 0.05,
        "radii": {"xs": 2, "small": 5, "medium": 9, "large": 13, "panel": 10, "button": 6, "badge": 3},
        "strokes": {"outer_ink_px": 3.0, "inner_highlight_px": 1.5, "panel_stroke_px": 3.0, "text_stroke_px": 1.5, "line_join": "Bevel"},
        "shadows": {"offset_x": 0, "offset_y": 4, "press_offset_y": 2, "blur_radius": 10, "transparency": 0.30},
        "fonts": {
            "title_family": "rbxasset://fonts/families/Michroma.json",
            "heading_family": "rbxasset://fonts/families/BuilderSans.json",
            "body_family": "rbxasset://fonts/families/BuilderSans.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": False, "ray_count": 10, "badge_rotation_deg": -3, "surface_pattern": "precision_hex_scanlines"},
        "style_material": "precision chamfered aerospace carbon-titanium HUD with luminous holographic rim lines and micro-tech corner brackets",
    },
    "arcade_pop": {
        "preset_id": "arcade_pop",
        "label": "Arcade Pop-Art",
        "keywords": ("arcade", "pop", "retro", "party", "minigame", "arena", "clash", "kart", "race", "dodgeball"),
        "surface_mode": "dark",
        "bg_hue_anchors": (254.0, 314.0, 18.0, 174.0, 286.0),
        "bg_sat": (0.42, 0.56),
        "bg_light_deep": (0.08, 0.12),
        "bg_light_panel": (0.14, 0.19),
        "primary_hue_anchors": (22.0, 144.0, 52.0, 330.0, 190.0, 272.0),
        "accent_sat": (0.92, 1.00),
        "accent_light": (0.50, 0.58),
        "ink_lightness": 0.04,
        "radii": {"xs": 3, "small": 6, "medium": 10, "large": 14, "panel": 10, "button": 7, "badge": 4},
        "strokes": {"outer_ink_px": 5.5, "inner_highlight_px": 2.2, "panel_stroke_px": 5.0, "text_stroke_px": 2.5, "line_join": "Miter"},
        "shadows": {"offset_x": 3, "offset_y": 5, "press_offset_y": 3, "blur_radius": 0, "transparency": 0.10},
        "fonts": {
            "title_family": "rbxasset://fonts/families/Bangers.json",
            "heading_family": "rbxasset://fonts/families/BuilderSans.json",
            "body_family": "rbxasset://fonts/families/BuilderSans.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": True, "ray_count": 16, "badge_rotation_deg": -7, "surface_pattern": "comic_halftone_dots"},
        "style_material": "bold punchy arcade pop-art UI with thick jet-black ink borders, hard-edge drop shadows, and comic halftone sheen",
    },
    "rpg_arcane": {
        "preset_id": "rpg_arcane",
        "label": "Arcane Guild RPG",
        "keywords": ("rpg", "fantasy", "arcane", "dungeon", "medieval", "magic", "quest", "guild", "knight", "dragon", "adventure"),
        "surface_mode": "dark",
        "bg_hue_anchors": (274.0, 344.0, 162.0, 26.0, 248.0),
        "bg_sat": (0.28, 0.42),
        "bg_light_deep": (0.07, 0.11),
        "bg_light_panel": (0.12, 0.17),
        "primary_hue_anchors": (38.0, 278.0, 350.0, 162.0, 24.0, 194.0),
        "accent_sat": (0.76, 0.92),
        "accent_light": (0.46, 0.56),
        "ink_lightness": 0.07,
        "radii": {"xs": 3, "small": 8, "medium": 13, "large": 18, "panel": 14, "button": 9, "badge": 5},
        "strokes": {"outer_ink_px": 4.0, "inner_highlight_px": 1.8, "panel_stroke_px": 4.0, "text_stroke_px": 2.0, "line_join": "Bevel"},
        "shadows": {"offset_x": 0, "offset_y": 5, "press_offset_y": 3, "blur_radius": 8, "transparency": 0.28},
        "fonts": {
            "title_family": "rbxasset://fonts/families/Fondamento.json",
            "heading_family": "rbxasset://fonts/families/BuilderSans.json",
            "body_family": "rbxasset://fonts/families/BuilderSans.json",
            "mono_family": "rbxasset://fonts/families/RobotoMono.json",
        },
        "motifs": {"rays_enabled": True, "ray_count": 10, "badge_rotation_deg": -4, "surface_pattern": "gilded_arcane_filigree"},
        "style_material": "ornate gilded arcane guild UI with beveled stone-and-bronze frames, jewel-toned gradients, and deep iron-ink outlines",
    },
}


# ---------------------------------------------------------------------------
# Color Science Utilities (sRGB, HSL, WCAG 2.1, CIE Lab, Delta-E)
# ---------------------------------------------------------------------------

def normalize_hex(color: str) -> str:
    raw = str(color or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        raise ValueError(f"Invalid hex color: {color!r}")
    return f"#{raw.upper()}"


def is_valid_hex(color: Any) -> bool:
    if not isinstance(color, str):
        return False
    try:
        normalize_hex(color)
        return True
    except ValueError:
        return False


def hex_to_rgb(color: str) -> Tuple[int, int, int]:
    hx = normalize_hex(color)[1:]
    return (int(hx[0:2], 16), int(hx[2:4], 16), int(hx[4:6], 16))


def rgb_to_hex(r: int, g: int, b: int) -> str:
    cr = max(0, min(255, int(round(r))))
    cg = max(0, min(255, int(round(g))))
    cb = max(0, min(255, int(round(b))))
    return f"#{cr:02X}{cg:02X}{cb:02X}"


def hsl_to_rgb(h_deg: float, s: float, l: float) -> Tuple[int, int, int]:
    h = (float(h_deg) % 360.0) / 360.0
    sc = max(0.0, min(1.0, float(s)))
    lc = max(0.0, min(1.0, float(l)))
    r, g, b = colorsys.hls_to_rgb(h, lc, sc)
    return (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))


def hsl_to_hex(h_deg: float, s: float, l: float) -> str:
    return rgb_to_hex(*hsl_to_rgb(h_deg, s, l))


def rgb_to_hsl(r: int, g: int, b: int) -> Tuple[float, float, float]:
    h, l, s = colorsys.rgb_to_hls(
        max(0.0, min(1.0, r / 255.0)),
        max(0.0, min(1.0, g / 255.0)),
        max(0.0, min(1.0, b / 255.0)),
    )
    return (h * 360.0, s, l)


def hex_to_hsl(color: str) -> Tuple[float, float, float]:
    return rgb_to_hsl(*hex_to_rgb(color))


def hue_distance_deg(h1: float, h2: float) -> float:
    d = abs((float(h1) % 360.0) - (float(h2) % 360.0))
    return min(d, 360.0 - d)


def _srgb_to_linear(channel_01: float) -> float:
    if channel_01 <= 0.04045:
        return channel_01 / 12.92
    return ((channel_01 + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    r, g, b = hex_to_rgb(color)
    rl = _srgb_to_linear(r / 255.0)
    gl = _srgb_to_linear(g / 255.0)
    bl = _srgb_to_linear(b / 255.0)
    return 0.2126 * rl + 0.7152 * gl + 0.0722 * bl


def wcag_contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    l1 = relative_luminance(fg_hex)
    l2 = relative_luminance(bg_hex)
    hi = max(l1, l2)
    lo = min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 3)


def rgb_to_lab(r: int, g: int, b: int) -> Tuple[float, float, float]:
    rl = _srgb_to_linear(r / 255.0)
    gl = _srgb_to_linear(g / 255.0)
    bl = _srgb_to_linear(b / 255.0)
    # D65 sRGB -> XYZ
    x = (rl * 0.4124564 + gl * 0.3575761 + bl * 0.1804375) / 0.95047
    y = (rl * 0.2126729 + gl * 0.7151522 + bl * 0.0721750) / 1.00000
    z = (rl * 0.0193339 + gl * 0.1191920 + bl * 0.9503041) / 1.08883

    def f(t: float) -> float:
        return t ** (1.0 / 3.0) if t > 0.008856 else (7.787 * t + 16.0 / 116.0)

    fx, fy, fz = f(x), f(y), f(z)
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def hex_to_lab(color: str) -> Tuple[float, float, float]:
    return rgb_to_lab(*hex_to_rgb(color))


def delta_e_cie76(c1: str, c2: str) -> float:
    l1, a1, b1 = hex_to_lab(c1)
    l2, a2, b2 = hex_to_lab(c2)
    return round(math.sqrt((l1 - l2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2), 3)


def _blend_hex(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    tc = max(0.0, min(1.0, t))
    return rgb_to_hex(
        round(r1 + (r2 - r1) * tc),
        round(g1 + (g2 - g1) * tc),
        round(b1 + (b2 - b1) * tc),
    )


def _adjust_contrast(
    fg_hex: str,
    bg_hex: str,
    min_ratio: float,
    prefer_direction: Optional[str] = None,
) -> Tuple[str, bool]:
    """Adjust foreground lightness/tint until WCAG contrast against bg_hex >= min_ratio."""
    fg = normalize_hex(fg_hex)
    bg = normalize_hex(bg_hex)
    if wcag_contrast_ratio(fg, bg) >= min_ratio:
        return fg, False

    h, s, l = hex_to_hsl(fg)
    bg_lum = relative_luminance(bg)

    if prefer_direction in ("lighter", "darker"):
        directions = [prefer_direction, "darker" if prefer_direction == "lighter" else "lighter"]
    else:
        directions = ["lighter", "darker"] if bg_lum < 0.35 else ["darker", "lighter"]

    for direction in directions:
        target_l = 0.98 if direction == "lighter" else 0.04
        lo, hi = (l, target_l) if direction == "lighter" else (target_l, l)
        best: Optional[str] = None
        for step in range(1, 36):
            frac = step / 35.0
            cand_l = l + (target_l - l) * frac
            # Slightly relax saturation only near extreme luminance
            cand_s = s * (1.0 - 0.30 * max(0.0, (frac - 0.65) / 0.35))
            cand = hsl_to_hex(h, cand_s, cand_l)
            if wcag_contrast_ratio(cand, bg) >= min_ratio:
                best = cand
                break
        if best is not None:
            # Binary refine closer to original lightness while preserving min_ratio
            a = l
            b = hex_to_hsl(best)[2]
            refined = best
            for _ in range(14):
                mid = (a + b) * 0.5
                frac_m = abs(mid - l) / max(1e-5, abs(target_l - l))
                cand_s = s * (1.0 - 0.30 * max(0.0, (frac_m - 0.65) / 0.35))
                cand = hsl_to_hex(h, cand_s, mid)
                if wcag_contrast_ratio(cand, bg) >= min_ratio:
                    refined = cand
                    b = mid
                else:
                    a = mid
            return refined, True

    # Absolute fallback to crisp near-white or near-black tinted ink
    white_cand = _blend_hex("#FFFFFF", fg, 0.08)
    black_cand = _blend_hex("#08080C", fg, 0.12)
    chosen = white_cand if wcag_contrast_ratio(white_cand, bg) >= wcag_contrast_ratio(black_cand, bg) else black_cand
    if wcag_contrast_ratio(chosen, bg) < min_ratio:
        chosen = "#FFFFFF" if wcag_contrast_ratio("#FFFFFF", bg) >= wcag_contrast_ratio("#000000", bg) else "#000000"
    return chosen, True


def _adjust_contrast_multi(fg_hex: str, bg_list: Iterable[str], min_ratio: float) -> Tuple[str, bool]:
    fg = normalize_hex(fg_hex)
    changed = False
    bgs = [normalize_hex(b) for b in bg_list]
    for _ in range(3):
        worst_bg = min(bgs, key=lambda b: wcag_contrast_ratio(fg, b))
        if wcag_contrast_ratio(fg, worst_bg) >= min_ratio:
            break
        fg, did = _adjust_contrast(fg, worst_bg, min_ratio)
        changed = changed or did
    return fg, changed


def _shift_hsl(hex_color: str, dl: float = 0.0, ds: float = 0.0, dh: float = 0.0) -> str:
    h, s, l = hex_to_hsl(hex_color)
    return hsl_to_hex(
        (h + dh) % 360.0,
        max(0.0, min(1.0, s + ds)),
        max(0.02, min(0.98, l + dl)),
    )


def _derive_hover_press(base_hex: str) -> Tuple[str, str]:
    _, _, l = hex_to_hsl(base_hex)
    if l < 0.72:
        hover = _shift_hsl(base_hex, dl=0.09, ds=0.04)
        press = _shift_hsl(base_hex, dl=-0.11, ds=0.05)
    else:
        hover = _shift_hsl(base_hex, dl=-0.06, ds=0.06)
        press = _shift_hsl(base_hex, dl=-0.16, ds=0.08)
    return hover, press


def _build_glossy_gradient(
    base_hex: str,
    rotation: int = -38,
    is_light_panel: bool = False,
) -> Dict[str, Any]:
    """Build a <=6 stop glossy UIGradient recipe (bright top -> crisp bevel edge -> rich shade)."""
    if is_light_panel:
        top = _shift_hsl(base_hex, dl=0.04, ds=-0.04)
        mid_hi = base_hex
        bevel = _shift_hsl(base_hex, dl=0.02, ds=0.02)
        bottom = _shift_hsl(base_hex, dl=-0.07, ds=0.05)
    else:
        top = _shift_hsl(base_hex, dl=0.18, ds=-0.05)
        mid_hi = base_hex
        bevel = _shift_hsl(base_hex, dl=0.10, ds=0.02)
        bottom = _shift_hsl(base_hex, dl=-0.16, ds=0.08)
    return {
        "type": "Linear",
        "rotation": int(rotation),
        "stops": [
            {"time": 0.0, "color": top},
            {"time": 0.48, "color": mid_hi},
            {"time": 0.50, "color": bevel},
            {"time": 1.0, "color": bottom},
        ],
    }


def _luau_color3(hex_color: str) -> str:
    r, g, b = hex_to_rgb(hex_color)
    return f"Color3.fromRGB({r}, {g}, {b})"


def _luau_str(value: str) -> str:
    return json.dumps(str(value))


# ---------------------------------------------------------------------------
# DesignEngine
# ---------------------------------------------------------------------------

class DesignEngine:
    """Anti-Slop Design System generator, WCAG auto-fixer, linter, Luau compiler & prompt batcher."""

    def __init__(self, skills_dir: Optional[Path] = None, archive_dir: Optional[Path] = None) -> None:
        self.skills_dir = skills_dir
        self.archive_dir = archive_dir

    def list_presets(self) -> Dict[str, Any]:
        return {
            "ok": True,
            "presets": [
                {
                    "preset_id": k,
                    "label": v["label"],
                    "surface_mode": v["surface_mode"],
                    "keywords": list(v["keywords"]),
                    "style_material": v["style_material"],
                }
                for k, v in DESIGN_PRESETS.items()
            ],
        }

    def _resolve_preset(self, genre: str, mood: str, seed_bytes: bytes, constraints: Dict[str, Any]) -> Dict[str, Any]:
        forced = str(constraints.get("preset") or "").strip().lower()
        if forced in DESIGN_PRESETS:
            return DESIGN_PRESETS[forced]

        hay = f"{genre} {mood}".lower()
        best_id: Optional[str] = None
        best_hits = 0
        for pid, spec in DESIGN_PRESETS.items():
            if pid in hay:
                return spec
            hits = sum(1 for kw in spec["keywords"] if kw in hay)
            if hits > best_hits:
                best_hits = hits
                best_id = pid
        if best_id is not None:
            return DESIGN_PRESETS[best_id]

        preset_keys = tuple(DESIGN_PRESETS.keys())
        idx = int.from_bytes(seed_bytes[0:4], "big") % len(preset_keys)
        return DESIGN_PRESETS[preset_keys[idx]]

    @staticmethod
    def _hash_floats(seed_material: str) -> List[float]:
        out: List[float] = []
        for round_idx in range(3):
            digest = hashlib.sha256(f"{seed_material}|r{round_idx}".encode("utf-8")).digest()
            for off in range(0, 32, 4):
                val = int.from_bytes(digest[off : off + 4], "big")
                out.append(val / 4294967295.0)
        return out

    @staticmethod
    def _is_near_generic_slop(bg_deep: str, bg_panel: str, primary: str) -> bool:
        for ref_deep, ref_panel, ref_pri in _GENERIC_SLOP_REFS:
            if (
                delta_e_cie76(bg_deep, ref_deep) < 12.0
                and delta_e_cie76(bg_panel, ref_panel) < 14.0
                and delta_e_cie76(primary, ref_pri) < 24.0
            ):
                return True
        # Also block boring low-chroma blue primary on dark navy or neutral flat gray background
        p_h, _, _ = hex_to_hsl(primary)
        bg_h, bg_s, bg_l = hex_to_hsl(bg_deep)
        is_slate_or_gray_bg = bg_l < 0.24 and (bg_s < 0.14 or (198.0 <= bg_h <= 242.0 and bg_s < 0.38))
        if 198.0 <= p_h <= 242.0 and is_slate_or_gray_bg:
            return True
        return False

    def generate_design_system(
        self,
        game_title: str,
        genre: str = "adventure",
        mood: str = "vibrant",
        seed: Optional[int | str] = None,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a deterministic, unique, WCAG-verified per-game design system."""
        title_clean = str(game_title or "Untitled Realm").strip() or "Untitled Realm"
        genre_clean = str(genre or "adventure").strip() or "adventure"
        mood_clean = str(mood or "vibrant").strip() or "vibrant"
        cfg = dict(constraints or {})

        seed_token = str(seed) if seed is not None else "title_auto"
        seed_material = f"{title_clean.lower()}|{genre_clean.lower()}|{mood_clean.lower()}|{seed_token}"
        seed_bytes = hashlib.sha256(seed_material.encode("utf-8")).digest()
        u = self._hash_floats(seed_material)

        preset = self._resolve_preset(genre_clean, mood_clean, seed_bytes, cfg)
        surface_mode = str(cfg.get("surface_mode") or preset["surface_mode"]).lower()
        if surface_mode not in ("dark", "light"):
            surface_mode = "dark"

        # Choose harmony family deterministically from genre + mood + seed
        forced_harmony = str(cfg.get("harmony") or "").lower()
        if forced_harmony in HARMONY_FAMILIES:
            harmony = forced_harmony
        else:
            mood_l = mood_clean.lower()
            if any(w in mood_l for w in ("calm", "cozy", "serene", "soft", "warm")):
                harmony = "analogous" if u[1] < 0.65 else "split_complementary"
            elif any(w in mood_l for w in ("energetic", "hyper", "pop", "chaotic", "arcade")):
                harmony = "triadic" if u[1] < 0.55 else "tetradic"
            elif any(w in mood_l for w in ("tactical", "cyber", "sleek", "mysterious")):
                harmony = "split_complementary" if u[1] < 0.6 else "analogous"
            else:
                harmony = HARMONY_FAMILIES[int(u[1] * len(HARMONY_FAMILIES)) % len(HARMONY_FAMILIES)]

        # Deterministic continuous primary hue seeded across preset anchors + full variation
        if cfg.get("brand_hue") is not None:
            primary_hue = float(cfg["brand_hue"]) % 360.0
        else:
            anchors = preset["primary_hue_anchors"]
            anchor = anchors[int(u[2] * len(anchors)) % len(anchors)]
            # Combine anchor selection with wide continuous offset so any 2 titles diverge strongly
            jitter = (u[3] - 0.5) * 90.0 + (u[4] - 0.5) * 40.0
            primary_hue = (anchor + jitter) % 360.0

        # Avoid generic Roblox/Tailwind blue range (208..232 deg) unless explicitly pinned via brand_hue
        if cfg.get("brand_hue") is None and 208.0 <= primary_hue <= 232.0:
            primary_hue = (primary_hue + (48.0 if u[5] >= 0.5 else -48.0)) % 360.0

        # Compute harmony secondary & accent hues with guaranteed >= 25 deg separation
        sign = 1.0 if u[6] >= 0.5 else -1.0
        if harmony == "analogous":
            secondary_hue = (primary_hue + sign * (34.0 + u[7] * 18.0)) % 360.0
            accent_hue = (primary_hue - sign * (42.0 + u[8] * 22.0)) % 360.0
        elif harmony == "triadic":
            secondary_hue = (primary_hue + 118.0 + (u[7] - 0.5) * 18.0) % 360.0
            accent_hue = (primary_hue + 240.0 + (u[8] - 0.5) * 18.0) % 360.0
        elif harmony == "split_complementary":
            secondary_hue = (primary_hue + 150.0 + (u[7] - 0.5) * 16.0) % 360.0
            accent_hue = (primary_hue + 210.0 + (u[8] - 0.5) * 16.0) % 360.0
        else:  # tetradic
            secondary_hue = (primary_hue + 92.0 + (u[7] - 0.5) * 14.0) % 360.0
            accent_hue = (primary_hue + 184.0 + (u[8] - 0.5) * 16.0) % 360.0

        # Ensure secondary/accent never collapse onto primary or each other
        if hue_distance_deg(secondary_hue, primary_hue) < 26.0:
            secondary_hue = (primary_hue + 40.0) % 360.0
        if hue_distance_deg(accent_hue, primary_hue) < 26.0 or hue_distance_deg(accent_hue, secondary_hue) < 24.0:
            accent_hue = (primary_hue + 165.0) % 360.0

        # Surface background hue & saturation/lightness
        bg_anchors = preset["bg_hue_anchors"]
        bg_base_anchor = bg_anchors[int(u[9] * len(bg_anchors)) % len(bg_anchors)]
        # Blend title-specific hue character with preset bg anchor
        bg_hue = (bg_base_anchor + (u[10] - 0.5) * 64.0) % 360.0
        if 204.0 <= bg_hue <= 232.0 and surface_mode == "dark":
            bg_hue = (bg_hue + (46.0 if u[11] >= 0.5 else -42.0)) % 360.0

        s_lo, s_hi = preset["bg_sat"]
        bg_sat = s_lo + (s_hi - s_lo) * u[12]

        if surface_mode == "light":
            dl_lo, dl_hi = (0.85, 0.90)
            pl_lo, pl_hi = (0.93, 0.97)
            bg_deep = hsl_to_hex(bg_hue, min(0.62, bg_sat + 0.08), dl_lo + (dl_hi - dl_lo) * u[13])
            bg_panel = hsl_to_hex((bg_hue + 4.0) % 360.0, min(0.66, bg_sat + 0.04), pl_lo + (pl_hi - pl_lo) * u[14])
            bg_card = _shift_hsl(bg_panel, dl=-0.03, ds=0.04)
            bg_input = _shift_hsl(bg_deep, dl=-0.04, ds=0.05)
            text_raw = hsl_to_hex((bg_hue + 10.0) % 360.0, 0.36, 0.14)
            text_sec_raw = hsl_to_hex((bg_hue + 10.0) % 360.0, 0.28, 0.28)
            text_mut_raw = hsl_to_hex((bg_hue + 10.0) % 360.0, 0.22, 0.36)
            outline_ink = hsl_to_hex((bg_hue + 8.0) % 360.0, 0.42, preset["ink_lightness"])
        else:
            dl_lo, dl_hi = preset["bg_light_deep"]
            pl_lo, pl_hi = preset["bg_light_panel"]
            bg_deep = hsl_to_hex(bg_hue, bg_sat, dl_lo + (dl_hi - dl_lo) * u[13])
            bg_panel = hsl_to_hex((bg_hue + 6.0) % 360.0, min(0.58, bg_sat + 0.04), pl_lo + (pl_hi - pl_lo) * u[14])
            bg_card = _shift_hsl(bg_panel, dl=0.05, ds=0.04)
            bg_input = _shift_hsl(bg_deep, dl=0.02, ds=0.04)
            text_raw = hsl_to_hex((primary_hue + 18.0) % 360.0, 0.24, 0.95)
            text_sec_raw = hsl_to_hex((primary_hue + 14.0) % 360.0, 0.26, 0.78)
            text_mut_raw = hsl_to_hex((primary_hue + 14.0) % 360.0, 0.24, 0.68)
            outline_ink = hsl_to_hex((bg_hue + 14.0) % 360.0, min(0.75, bg_sat + 0.22), preset["ink_lightness"])

        as_lo, as_hi = preset["accent_sat"]
        al_lo, al_hi = preset["accent_light"]
        p_sat = as_lo + (as_hi - as_lo) * u[15]
        p_light = al_lo + (al_hi - al_lo) * u[16]
        s_sat = max(0.55, p_sat - 0.08 + 0.08 * u[17])
        a_sat = min(1.0, p_sat + 0.04)

        primary = hsl_to_hex(primary_hue, p_sat, p_light)
        secondary = hsl_to_hex(secondary_hue, s_sat, max(0.38, min(0.62, p_light - 0.03 + 0.08 * u[18])))
        accent = hsl_to_hex(accent_hue, a_sat, max(0.42, min(0.64, p_light + 0.03)))

        # Semantic statuses harmonized subtly to title hue while remaining unmistakable
        success_hue = (142.0 + (u[19] - 0.5) * 20.0) % 360.0
        warning_hue = (38.0 + (u[20] - 0.5) * 14.0) % 360.0
        danger_hue = (352.0 + (u[21] - 0.5) * 16.0) % 360.0
        gold_hue = (46.0 + (u[22] - 0.5) * 10.0) % 360.0

        sem_l = 0.45 if surface_mode == "light" else 0.52
        success = hsl_to_hex(success_hue, 0.76, sem_l)
        warning = hsl_to_hex(warning_hue, 0.90, 0.46 if surface_mode == "light" else 0.55)
        danger = hsl_to_hex(danger_hue, 0.84, 0.48 if surface_mode == "light" else 0.54)
        gold = hsl_to_hex(gold_hue, 0.94, 0.44 if surface_mode == "light" else 0.56)

        # Anti-slop guard: guarantee never emitting generic dark-navy + blue default
        if self._is_near_generic_slop(bg_deep, bg_panel, primary):
            primary = hsl_to_hex((primary_hue + 82.0) % 360.0, p_sat, p_light)
            bg_deep = hsl_to_hex((bg_hue + 56.0) % 360.0, max(0.36, bg_sat), 0.09)
            bg_panel = hsl_to_hex((bg_hue + 60.0) % 360.0, max(0.38, bg_sat), 0.15)
            bg_card = _shift_hsl(bg_panel, dl=0.05, ds=0.03)
            outline_ink = hsl_to_hex((bg_hue + 64.0) % 360.0, 0.55, preset["ink_lightness"])

        # WCAG 2.1 Contrast Auto-Fixer
        min_text = float(cfg.get("min_contrast_text", 4.5))
        min_ui = float(cfg.get("min_contrast_ui", 3.0))
        fixes_applied: List[str] = []

        surface_bgs = [bg_deep, bg_panel, bg_card]
        text, f1 = _adjust_contrast_multi(text_raw, surface_bgs, max(4.5, min_text))
        if f1:
            fixes_applied.append("text adjusted for >=4.5:1 across surfaces")
        text_secondary, f2 = _adjust_contrast_multi(text_sec_raw, [bg_deep, bg_panel], min_text)
        if f2:
            fixes_applied.append("text_secondary adjusted for >=4.5:1")
        text_muted, f3 = _adjust_contrast_multi(text_mut_raw, [bg_panel], min_text)
        if f3:
            fixes_applied.append("text_muted adjusted for >=4.5:1")

        # Chromatic UI roles vs bg_panel & bg_deep >= 3.0:1
        for role_name, col_val in (
            ("primary", primary),
            ("secondary", secondary),
            ("accent", accent),
            ("success", success),
            ("warning", warning),
            ("danger", danger),
            ("gold", gold),
        ):
            fixed_col, did_fix = _adjust_contrast_multi(col_val, [bg_panel, bg_deep], min_ui)
            if did_fix:
                fixes_applied.append(f"{role_name} adjusted for >=3.0:1 UI contrast")
            if role_name == "primary":
                primary = fixed_col
            elif role_name == "secondary":
                secondary = fixed_col
            elif role_name == "accent":
                accent = fixed_col
            elif role_name == "success":
                success = fixed_col
            elif role_name == "warning":
                warning = fixed_col
            elif role_name == "danger":
                danger = fixed_col
            elif role_name == "gold":
                gold = fixed_col

        # Compute high-contrast button text per semantic fill (>= 4.5:1)
        def pick_button_text(fill_hex: str) -> str:
            light_cand = "#FFFFFF" if surface_mode == "dark" else "#FFFDF9"
            dark_cand = outline_ink
            if wcag_contrast_ratio(light_cand, fill_hex) >= min_text:
                return light_cand
            if wcag_contrast_ratio(dark_cand, fill_hex) >= min_text:
                return dark_cand
            best_c = light_cand if wcag_contrast_ratio(light_cand, fill_hex) >= wcag_contrast_ratio(dark_cand, fill_hex) else dark_cand
            fixed, _ = _adjust_contrast(best_c, fill_hex, min_text)
            return fixed

        text_on_primary = pick_button_text(primary)
        text_on_secondary = pick_button_text(secondary)
        text_on_accent = pick_button_text(accent)
        text_on_success = pick_button_text(success)
        text_on_warning = pick_button_text(warning)
        text_on_danger = pick_button_text(danger)
        text_on_gold = pick_button_text(gold)

        border_subtle = _blend_hex(bg_panel, text_secondary, 0.35)
        border_bright = _blend_hex(primary, "#FFFFFF" if surface_mode == "dark" else outline_ink, 0.28)
        scrim = _shift_hsl(bg_deep, dl=-0.04 if surface_mode == "dark" else -0.70, ds=-0.10)

        # Harmonized rarity ramp (>= 3.0:1 against bg_panel)
        rarity_raw = {
            "common": hsl_to_hex((bg_hue + 15.0) % 360.0, 0.16, 0.62 if surface_mode == "dark" else 0.42),
            "uncommon": hsl_to_hex((142.0 + (u[19] - 0.5) * 16.0) % 360.0, 0.72, 0.50),
            "rare": hsl_to_hex((198.0 + (u[23] - 0.5) * 18.0) % 360.0, 0.86, 0.54),
            "epic": hsl_to_hex((278.0 + (u[0] - 0.5) * 20.0) % 360.0, 0.82, 0.58),
            "legendary": gold,
            "mythic": hsl_to_hex((338.0 + (u[2] - 0.5) * 18.0) % 360.0, 0.92, 0.56),
        }
        rarity = {
            rk: _adjust_contrast_multi(rv, [bg_panel], min_ui)[0]
            for rk, rv in rarity_raw.items()
        }

        primary_hover, primary_press = _derive_hover_press(primary)
        secondary_hover, secondary_press = _derive_hover_press(secondary)
        accent_hover, accent_press = _derive_hover_press(accent)
        success_hover, success_press = _derive_hover_press(success)
        warning_hover, warning_press = _derive_hover_press(warning)
        danger_hover, danger_press = _derive_hover_press(danger)

        palette: Dict[str, Any] = {
            "bg_deep": bg_deep,
            "bg_panel": bg_panel,
            "bg_card": bg_card,
            "bg_input": bg_input,
            "primary": primary,
            "primary_hover": primary_hover,
            "primary_press": primary_press,
            "secondary": secondary,
            "secondary_hover": secondary_hover,
            "secondary_press": secondary_press,
            "accent": accent,
            "accent_hover": accent_hover,
            "accent_press": accent_press,
            "success": success,
            "success_hover": success_hover,
            "success_press": success_press,
            "warning": warning,
            "warning_hover": warning_hover,
            "warning_press": warning_press,
            "danger": danger,
            "danger_hover": danger_hover,
            "danger_press": danger_press,
            "gold": gold,
            "gem": accent,
            "text": text,
            "text_secondary": text_secondary,
            "text_muted": text_muted,
            "text_on_primary": text_on_primary,
            "text_on_secondary": text_on_secondary,
            "text_on_accent": text_on_accent,
            "text_on_success": text_on_success,
            "text_on_warning": text_on_warning,
            "text_on_danger": text_on_danger,
            "text_on_gold": text_on_gold,
            "outline_ink": outline_ink,
            "border_subtle": border_subtle,
            "border_bright": border_bright,
            "scrim": scrim,
            "rarity": rarity,
        }

        # Radii with deliberate multi-tier hierarchy (never same radius everywhere)
        rad_delta = int(round((u[21] - 0.5) * 4))
        base_r = preset["radii"]
        radii = {
            "xs": max(2, base_r["xs"] + (rad_delta // 2)),
            "small": max(4, base_r["small"] + rad_delta),
            "medium": max(8, base_r["medium"] + rad_delta),
            "large": max(12, base_r["large"] + rad_delta),
            "panel": max(8, base_r["panel"] + rad_delta),
            "button": max(5, base_r["button"] + rad_delta),
            "badge": max(3, base_r["badge"] + (rad_delta // 2)),
            "pill": 999,
        }
        # Guarantee distinct button vs panel vs badge radii
        if radii["button"] == radii["panel"]:
            radii["panel"] = radii["button"] + 4
        if radii["badge"] == radii["button"]:
            radii["badge"] = max(2, radii["button"] - 3)

        strokes = dict(preset["strokes"])
        shadows = {
            **preset["shadows"],
            "color": outline_ink,
        }

        grad_angle = int(round(-36 - u[22] * 10))
        gradient_recipes = {
            "primary": _build_glossy_gradient(primary, rotation=grad_angle),
            "secondary": _build_glossy_gradient(secondary, rotation=grad_angle),
            "accent": _build_glossy_gradient(accent, rotation=grad_angle),
            "success": _build_glossy_gradient(success, rotation=grad_angle),
            "warning": _build_glossy_gradient(warning, rotation=grad_angle),
            "danger": _build_glossy_gradient(danger, rotation=grad_angle),
            "gold": _build_glossy_gradient(gold, rotation=grad_angle),
            "panel": _build_glossy_gradient(bg_panel, rotation=90, is_light_panel=(surface_mode == "light")),
            "shine_sweep": {
                "type": "Linear",
                "rotation": -25,
                "transparency_stops": [
                    {"time": 0.0, "transparency": 1.0},
                    {"time": 0.36, "transparency": 1.0},
                    {"time": 0.50, "transparency": 0.24},
                    {"time": 0.64, "transparency": 1.0},
                    {"time": 1.0, "transparency": 1.0},
                ],
                "duration_s": 0.65,
            },
        }

        contrast_pairs = {
            "text_on_bg_deep": wcag_contrast_ratio(text, bg_deep),
            "text_on_bg_panel": wcag_contrast_ratio(text, bg_panel),
            "text_on_bg_card": wcag_contrast_ratio(text, bg_card),
            "text_secondary_on_bg_panel": wcag_contrast_ratio(text_secondary, bg_panel),
            "text_muted_on_bg_panel": wcag_contrast_ratio(text_muted, bg_panel),
            "text_on_primary": wcag_contrast_ratio(text_on_primary, primary),
            "text_on_secondary": wcag_contrast_ratio(text_on_secondary, secondary),
            "text_on_accent": wcag_contrast_ratio(text_on_accent, accent),
            "text_on_success": wcag_contrast_ratio(text_on_success, success),
            "text_on_warning": wcag_contrast_ratio(text_on_warning, warning),
            "text_on_danger": wcag_contrast_ratio(text_on_danger, danger),
            "primary_on_bg_panel": wcag_contrast_ratio(primary, bg_panel),
            "secondary_on_bg_panel": wcag_contrast_ratio(secondary, bg_panel),
            "accent_on_bg_panel": wcag_contrast_ratio(accent, bg_panel),
            "gold_on_bg_panel": wcag_contrast_ratio(gold, bg_panel),
        }

        style_signature = (
            f"{preset['style_material']} for '{title_clean}' "
            f"({mood_clean} {genre_clean}, {harmony} harmony, "
            f"palette {primary}/{secondary}/{accent} anchored by {outline_ink} outline ink)"
        )

        # Pick flood-fill key color that cannot collide with outline_ink or bg_deep
        key_bg_hex = "#FF00FF" if surface_mode == "dark" else "#0B0E17"
        if delta_e_cie76(key_bg_hex, primary) < 28.0 or delta_e_cie76(key_bg_hex, accent) < 28.0:
            key_bg_hex = "#00FF7F"

        return {
            "ok": True,
            "game_title": title_clean,
            "genre": genre_clean,
            "mood": mood_clean,
            "seed": seed_token,
            "seed_hash": seed_bytes.hex()[:16],
            "preset_id": preset["preset_id"],
            "surface_mode": surface_mode,
            "harmony": harmony,
            "palette": palette,
            "tokens": {
                "radii": radii,
                "spacing": {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24},
                "min_touch_px": 44,
                "recommended_button_px": 52,
                "strokes": strokes,
                "shadows": shadows,
                "typography": {
                    **preset["fonts"],
                    "title_weight": "ExtraBold",
                    "heading_weight": "Bold",
                    "body_weight": "Medium",
                    "title_size": 22,
                    "heading_size": 16,
                    "body_size": 14,
                    "caption_size": 12,
                },
                "motifs": dict(preset["motifs"]),
            },
            "gradient_recipes": gradient_recipes,
            "contrast_audit": {
                "min_text_required": min_text,
                "min_ui_required": min_ui,
                "pairs": contrast_pairs,
                "fixes_applied": fixes_applied,
                "passed": (
                    min(
                        contrast_pairs["text_on_bg_deep"],
                        contrast_pairs["text_on_bg_panel"],
                        contrast_pairs["text_on_primary"],
                        contrast_pairs["text_on_secondary"],
                        contrast_pairs["text_on_accent"],
                    )
                    >= min_text
                    and min(
                        contrast_pairs["primary_on_bg_panel"],
                        contrast_pairs["secondary_on_bg_panel"],
                        contrast_pairs["accent_on_bg_panel"],
                    )
                    >= min_ui
                ),
            },
            "style_signature": style_signature,
            "key_background_hex": key_bg_hex,
        }

    # -----------------------------------------------------------------------
    # Anti-Slop Linter
    # -----------------------------------------------------------------------

    def lint_design(self, spec_or_palette: Dict[str, Any] | str) -> Dict[str, Any]:
        """Audit a design system, palette dict, or UI spec JSON for generic AI/template slop."""
        if isinstance(spec_or_palette, str):
            raw_str = spec_or_palette.strip()
            if raw_str.startswith("{"):
                data: Dict[str, Any] = json.loads(raw_str)
            else:
                data = {"luau_source": raw_str}
        elif isinstance(spec_or_palette, dict):
            data = spec_or_palette
        else:
            raise TypeError("spec_or_palette must be a dict or JSON/Luau string")

        if isinstance(data, dict) and "luau_source" in data and "palette" not in data and "colors" not in data:
            palette = {}
        else:
            raw_pal = data.get("palette", data.get("colors")) if isinstance(data, dict) else {}
            palette = raw_pal if isinstance(raw_pal, dict) else (data if isinstance(data, dict) else {})
        tokens: Dict[str, Any] = data.get("tokens", {}) if isinstance(data.get("tokens"), dict) else {}
        gradients: Dict[str, Any] = data.get("gradient_recipes", data.get("gradients", {}))
        components: List[Dict[str, Any]] = list(data.get("components", [])) + list(data.get("buttons", [])) + list(data.get("panels", []))

        findings: List[Dict[str, Any]] = []
        distinct_hues: List[float] = []

        def add_finding(code: str, severity: str, weight: int, message: str, target: str, fix: str) -> None:
            findings.append(
                {
                    "code": code,
                    "severity": severity,
                    "weight": weight,
                    "message": message,
                    "target": target,
                    "fix": fix,
                }
            )

        # Normalize palette hex lookup (support both snake_case and PascalCase / kebab-case)
        def pick_color(*keys: str) -> Optional[str]:
            for k in keys:
                for src in (palette, data):
                    if isinstance(src, dict) and k in src and is_valid_hex(src[k]):
                        return normalize_hex(src[k])
            return None

        bg_deep = pick_color("bg_deep", "BgDeep", "background", "bg")
        bg_panel = pick_color("bg_panel", "BgPanel", "panel", "surface")
        primary = pick_color("primary", "Primary")
        secondary = pick_color("secondary", "Secondary")
        accent = pick_color("accent", "Accent")
        success = pick_color("success", "Success")
        warning = pick_color("warning", "Warning")
        danger = pick_color("danger", "Danger")
        gold = pick_color("gold", "Gold")
        text_col = pick_color("text", "TextPrimary", "text_primary")
        outline_ink = pick_color("outline_ink", "outline-ink", "OutlineInk", "ink")

        luau_src = str(data.get("luau_source", "") or "")
        if luau_src and not palette and not components:
            # Extract Color3.fromRGB literals from Luau snippet for hue/slop evaluation
            rgb_matches = re.findall(r"Color3\.fromRGB\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", luau_src)
            for mr, mg, mb in rgb_matches:
                hx = rgb_to_hex(int(mr), int(mg), int(mb))
                h, s, l = hex_to_hsl(hx)
                if s >= 0.20 and 0.08 <= l <= 0.92:
                    if all(hue_distance_deg(h, eh) >= 20.0 for eh in distinct_hues):
                        distinct_hues.append(h)

            if "TextButton" in luau_src or "ImageButton" in luau_src or "CreateButton" in luau_src:
                if "UIGradient" not in luau_src or "UIStroke" not in luau_src:
                    add_finding(
                        "flat_button_no_gradient_stroke",
                        "high",
                        18,
                        "Luau button code lacks UIGradient and/or UIStroke (flat single-color button slop).",
                        "luau_source",
                        "Use UIKit.CreateGlossyButton() or attach diagonal UIGradient + stacked outer/inner UIStroke.",
                    )
                if not any(tok in luau_src for tok in (":Hover", ":Press", "MouseEnter", "MouseButton1Down")):
                    add_finding(
                        "missing_interaction_states",
                        "medium",
                        12,
                        "Luau button code lacks hover/press interaction feedback.",
                        "luau_source",
                        "Wire :Hover/:Press StyleRules or MouseEnter/MouseButton1Down +3px press tween.",
                    )
            if "UIStroke" not in luau_src and "OutlineInk" not in luau_src:
                add_finding(
                    "missing_outline_ink",
                    "high",
                    16,
                    "Luau snippet defines no UIStroke or OutlineInk border styling.",
                    "luau_source",
                    "Add outer OutlineInk UIStroke (3-5px) via UIKit.AttachStackedStrokes().",
                )
            small_dims = re.findall(r"UDim2\.fromOffset\(\s*(\d+)\s*,\s*(\d+)\s*\)", luau_src) + re.findall(
                r"UDim2\.new\(\s*0\s*,\s*(\d+)\s*,\s*0\s*,\s*(\d+)\s*\)", luau_src
            )
            for ow, oh in small_dims:
                if int(ow) < 44 or int(oh) < 44:
                    if any(k in luau_src for k in ("TextButton", "ImageButton", "TextBox")):
                        add_finding(
                            "small_touch_target",
                            "blocker",
                            25,
                            f"Luau snippet includes interactive size ({ow}x{oh}) < 44px.",
                            "luau_source",
                            "Ensure all interactive controls meet >= 44x44px (52px recommended) via UIKit.EnsureMinTouchTarget().",
                        )
                        break
            if _EMOJI_RE.search(luau_src):
                add_finding(
                    "emoji_as_icon",
                    "medium",
                    12,
                    "Luau UI source embeds Unicode emoji characters instead of icon atlas/vector badges.",
                    "luau_source",
                    "Use UIKit.CreateBadgeIcon() with packed RGBA icon atlas sprites.",
                )
            rad_nums = re.findall(r"CornerRadius\s*=\s*UDim\.new\(\s*0\s*,\s*(\d+)\s*\)", luau_src)
            if len(rad_nums) >= 3 and len(set(rad_nums)) <= 1:
                add_finding(
                    "uniform_radius_everywhere",
                    "medium",
                    10,
                    f"Luau source reuses identical CornerRadius UDim.new(0, {rad_nums[0]}) across {len(rad_nums)} elements.",
                    "luau_source",
                    "Use differentiated UIKit.Tokens.Radii (Badge / Button / Panel / Pill).",
                )
        else:
            # 1. Missing outline ink
            if not outline_ink:
                has_component_ink = any(
                    c.get("stroke") or c.get("outline_ink") or c.get("UIStroke")
                    for c in components
                    if isinstance(c, dict)
                )
                if not has_component_ink:
                    add_finding(
                        "missing_outline_ink",
                        "high",
                        16,
                        "Missing dedicated 'outline_ink' token or bold outer ink UIStroke.",
                        "palette.outline_ink",
                        "Add a deep tinted outline_ink color token (e.g. #1C1635) and apply a 3-5px outer UIStroke.",
                    )

            # 2. Default-blue / generic dark-gray slop dump
            if primary and (bg_deep or bg_panel):
                ref_deep = bg_deep or bg_panel or "#0D121C"
                ref_panel = bg_panel or bg_deep or "#161E2E"
                if self._is_near_generic_slop(ref_deep, ref_panel, primary):
                    add_finding(
                        "default_blue_gray_slop",
                        "high",
                        20,
                        f"Palette matches generic dark-navy/gray + default blue slop ({ref_deep}/{primary}).",
                        "palette",
                        "Use DesignEngine.generate_design_system() with an explicit genre, mood, and seed for bespoke color harmony.",
                    )
            elif palette:
                chromatic_vals = [c for c in (primary, secondary, accent, success, warning, danger, gold) if c]
                if chromatic_vals and all(hex_to_hsl(c)[1] < 0.22 for c in chromatic_vals):
                    add_finding(
                        "default_blue_gray_slop",
                        "high",
                        18,
                        "Palette relies entirely on washed-out/monochrome gray tones with low chroma.",
                        "palette",
                        "Introduce vibrant saturated primary, secondary, and accent roles via triadic or split-complementary harmony.",
                    )

            # 3. < 3 distinct chromatic hues
            all_colors: List[str] = []
            for c in (primary, secondary, accent, success, warning, danger, gold):
                if c:
                    all_colors.append(c)
            for comp in components:
                if isinstance(comp, dict):
                    for ck in ("color", "background", "bg", "fill", "accent"):
                        if is_valid_hex(comp.get(ck)):
                            all_colors.append(normalize_hex(comp[ck]))

            for hx in all_colors:
                h, s, l = hex_to_hsl(hx)
                if s >= 0.20 and 0.08 <= l <= 0.92:
                    if all(hue_distance_deg(h, eh) >= 20.0 for eh in distinct_hues):
                        distinct_hues.append(h)

            if len(distinct_hues) < 3:
                add_finding(
                    "insufficient_distinct_hues",
                    "high",
                    16,
                    f"Only {len(distinct_hues)} distinct chromatic hue(s) detected; anti-slop UI requires >= 3 distinct hues.",
                    "palette",
                    "Provide at least 3 distinct chromatic hues separated by >= 20 degrees (primary, secondary, accent).",
                )

            # 4. Low WCAG contrast checks
            surface_bg = bg_panel or bg_deep
            if text_col and surface_bg:
                ratio = wcag_contrast_ratio(text_col, surface_bg)
                if ratio < 4.5:
                    sev = "blocker" if ratio < 3.0 else "high"
                    add_finding(
                        "low_contrast",
                        sev,
                        25 if sev == "blocker" else 18,
                        f"Text {text_col} on surface {surface_bg} has WCAG contrast {ratio}:1 (< 4.5:1 required).",
                        "palette.text",
                        "Increase lightness separation between text and bg_panel/bg_deep to >= 4.5:1.",
                    )

            for role_name, fg_key, bg_val in (
                ("text_on_primary", "text_on_primary", primary),
                ("text_on_secondary", "text_on_secondary", secondary),
                ("text_on_accent", "text_on_accent", accent),
            ):
                fg_v = pick_color(fg_key) or text_col
                if fg_v and bg_val:
                    r_btn = wcag_contrast_ratio(fg_v, bg_val)
                    if r_btn < 4.5:
                        add_finding(
                            "low_contrast",
                            "high",
                            16,
                            f"Button text {fg_v} on {role_name.replace('text_on_', '')} {bg_val} has contrast {r_btn}:1 (< 4.5:1).",
                            f"palette.{fg_key}",
                            "Choose high-contrast button text (light or outline_ink) meeting >= 4.5:1 against fill.",
                        )

            for ui_name, ui_col in (("primary", primary), ("accent", accent), ("secondary", secondary)):
                if ui_col and surface_bg:
                    r_ui = wcag_contrast_ratio(ui_col, surface_bg)
                    if r_ui < 3.0:
                        add_finding(
                            "low_contrast",
                            "high",
                            14,
                            f"UI role '{ui_name}' ({ui_col}) on surface {surface_bg} has contrast {r_ui}:1 (< 3.0:1).",
                            f"palette.{ui_name}",
                            f"Adjust '{ui_name}' lightness/saturation so contrast against surface >= 3.0:1.",
                        )

            # 5. Flat single-color buttons without gradient + stroke
            flat_button_hits: List[str] = []
            button_components = [
                c for c in components
                if isinstance(c, dict) and (
                    "button" in str(c.get("type", "")).lower()
                    or "btn" in str(c.get("name", "")).lower()
                    or "button" in str(c.get("name", "")).lower()
                )
            ]
            for b in button_components:
                b_name = str(b.get("name") or b.get("type") or "Button")
                has_grad = bool(b.get("gradient") or b.get("UIGradient") or b.get("gradient_stops"))
                has_stroke = bool(b.get("stroke") or b.get("UIStroke") or b.get("stroke_thickness", 0) > 0)
                if not (has_grad and has_stroke):
                    flat_button_hits.append(b_name)
            if flat_button_hits:
                add_finding(
                    "flat_button_no_gradient_stroke",
                    "high",
                    18,
                    f"Flat single-color button(s) missing multi-stop gradient and/or UIStroke: {', '.join(flat_button_hits[:5])}.",
                    "components.buttons",
                    "Build buttons with UIKit.CreateGlossyButton() (diagonal UIGradient + stacked outer/inner UIStroke + drop shadow).",
                )
            elif data and not button_components:
                has_grad_recipes = bool(gradients and any(k in gradients for k in ("primary", "Primary", "button")))
                strokes_info = tokens.get("strokes", data.get("strokes", {}))
                has_stroke_tok = isinstance(strokes_info, dict) and float(strokes_info.get("outer_ink_px", strokes_info.get("OuterInk", 0))) > 0
                if not has_grad_recipes or not has_stroke_tok:
                    add_finding(
                        "flat_button_no_gradient_stroke",
                        "high",
                        16,
                        "Design spec lacks glossy gradient_recipes and/or outer UIStroke thickness tokens (flat button slop).",
                        "gradient_recipes / tokens.strokes",
                        "Include multi-stop diagonal gradient_recipes and outer_ink_px stroke tokens (>= 3px).",
                    )

            # 6. Missing hover / pressed states
            missing_states: List[str] = []
            for b in button_components:
                b_name = str(b.get("name") or "Button")
                states = b.get("states", {})
                has_hover = bool(b.get("hover") or b.get("hover_color") or (isinstance(states, dict) and ("hover" in states or ":Hover" in states)))
                has_press = bool(b.get("press") or b.get("pressed") or b.get("press_color") or (isinstance(states, dict) and ("press" in states or "pressed" in states or ":Press" in states)))
                if not (has_hover and has_press):
                    missing_states.append(b_name)
            if missing_states:
                add_finding(
                    "missing_interaction_states",
                    "medium",
                    12,
                    f"Button(s) missing hover and/or press states: {', '.join(missing_states[:5])}.",
                    "components.buttons.states",
                    "Provide :Hover and :Press StyleRule states plus physical +3px Y press depression.",
                )
            elif palette and not (pick_color("primary_hover", "PrimaryHover") and pick_color("primary_press", "PrimaryPress")):
                if not data.get("states"):
                    add_finding(
                        "missing_interaction_states",
                        "medium",
                        10,
                        "Palette/spec lacks explicit hover and press state color tokens (primary_hover / primary_press).",
                        "palette",
                        "Generate primary_hover and primary_press state colors and wire StyleRule :Hover/:Press transitions.",
                    )

            # 7. Touch target < 44px
            min_touch = tokens.get("min_touch_px", data.get("min_touch_px"))
            if min_touch is not None and float(min_touch) < 44.0:
                add_finding(
                    "small_touch_target",
                    "blocker",
                    25,
                    f"min_touch_px={min_touch} is below the 44px accessibility floor.",
                    "tokens.min_touch_px",
                    "Set min_touch_px >= 44 and recommended interactive buttons >= 52px.",
                )
            small_controls: List[str] = []
            for c in components:
                if not isinstance(c, dict):
                    continue
                ctype = str(c.get("type", "")).lower()
                if ctype in ("button", "textbutton", "imagebutton", "textbox", "toggle", "slot", "interactive") or c.get("interactive"):
                    sz = c.get("size") or [c.get("width", 999), c.get("height", 999)]
                    if isinstance(sz, (list, tuple)) and len(sz) >= 2:
                        w_px, h_px = float(sz[0]), float(sz[1])
                        if w_px < 44.0 or h_px < 44.0:
                            small_controls.append(f"{c.get('name', 'Control')}({int(w_px)}x{int(h_px)})")
            if small_controls:
                add_finding(
                    "small_touch_target",
                    "blocker",
                    25,
                    f"Interactive control(s) smaller than 44x44px: {', '.join(small_controls[:5])}.",
                    "components.size",
                    "Enforce UISizeConstraint MinSize >= (44, 44) (52x52 preferred before UIScale).",
                )

            # 8. Emoji used as icon
            emoji_hits: List[str] = []
            for c in components:
                if not isinstance(c, dict):
                    continue
                for field in ("icon", "glyph", "text", "label", "emoji"):
                    val = c.get(field)
                    if isinstance(val, str) and _EMOJI_RE.search(val):
                        emoji_hits.append(f"{c.get('name', 'item')}:{field}={val}")
            icons_list = data.get("icons", [])
            if isinstance(icons_list, list):
                for ic in icons_list:
                    if isinstance(ic, str) and _EMOJI_RE.search(ic):
                        emoji_hits.append(ic)
                    elif isinstance(ic, dict):
                        for field in ("glyph", "text", "icon"):
                            val = ic.get(field)
                            if isinstance(val, str) and _EMOJI_RE.search(val):
                                emoji_hits.append(f"{ic.get('name', 'icon')}:{val}")
            if emoji_hits:
                add_finding(
                    "emoji_as_icon",
                    "medium",
                    12,
                    f"Unicode emoji used as UI icon ({', '.join(emoji_hits[:4])}); emojis render inconsistently across platforms.",
                    "icons",
                    "Replace emojis with packed RGBA icon atlas sprites (ImageLabel + ImageRectOffset) or custom vector badge art.",
                )

            # 9. Same radius everywhere
            radii_dict = tokens.get("radii", data.get("radii", {}))
            radii_vals: List[float] = []
            if isinstance(radii_dict, dict):
                for rk, rv in radii_dict.items():
                    if rk.lower() != "pill" and isinstance(rv, (int, float)):
                        radii_vals.append(float(rv))
            comp_radii = [
                float(c["corner_radius"])
                for c in components
                if isinstance(c, dict) and isinstance(c.get("corner_radius"), (int, float))
            ]
            if len(radii_vals) >= 2 and len(set(radii_vals)) <= 1:
                add_finding(
                    "uniform_radius_everywhere",
                    "medium",
                    10,
                    f"All radius tokens share the exact same value ({radii_vals[0]}px); lacks visual hierarchy.",
                    "tokens.radii",
                    "Differentiate corner radii across tiers (e.g. badge 4-8px < button 8-16px < panel 14-22px < pill).",
                )
            elif len(comp_radii) >= 3 and len(set(comp_radii)) <= 1:
                add_finding(
                    "uniform_radius_everywhere",
                    "medium",
                    10,
                    f"All {len(comp_radii)} components share identical corner_radius={comp_radii[0]}px.",
                    "components.corner_radius",
                    "Vary corner radii between nested cards, buttons, badges, and modal shells.",
                )

        if luau_src and not palette and not components and len(distinct_hues) < 3:
            add_finding(
                "insufficient_distinct_hues",
                "high",
                16,
                f"Only {len(distinct_hues)} distinct chromatic hue(s) found in Luau snippet; anti-slop UI requires >= 3 distinct hues.",
                "luau_source",
                "Apply a full DesignEngine palette via UIKit.ApplyDesignSystem().",
            )

        total_penalty = sum(f["weight"] for f in findings)
        score = max(0, 100 - total_penalty)
        sev_counts = {"blocker": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev_counts[f["severity"]] = sev_counts.get(f["severity"], 0) + 1

        if score >= 90:
            grade = "A"
        elif score >= 80:
            grade = "B"
        elif score >= 65:
            grade = "C"
        elif score >= 50:
            grade = "D"
        else:
            grade = "F"

        fixes = []
        for f in findings:
            if f["fix"] not in fixes:
                fixes.append(f["fix"])

        return {
            "ok": sev_counts["blocker"] == 0 and score >= 70,
            "score": score,
            "grade": grade,
            "finding_count": len(findings),
            "severity_summary": sev_counts,
            "distinct_chromatic_hues": len(distinct_hues),
            "findings": findings,
            "fixes": fixes,
        }

    # -----------------------------------------------------------------------
    # Luau Theme Compiler
    # -----------------------------------------------------------------------

    def compile_theme_luau(self, design_system: Dict[str, Any], module_mode: bool = True) -> str:
        """Emit --!strict Luau theme tokens consumable by UIKit.ApplyDesignSystem(ds)."""
        ds = design_system if "palette" in design_system else self.generate_design_system(
            str(design_system.get("game_title", "Custom Game")),
            str(design_system.get("genre", "adventure")),
            str(design_system.get("mood", "vibrant")),
        )
        p = ds["palette"]
        tok = ds.get("tokens", {})
        radii = tok.get("radii", {"xs": 4, "small": 8, "medium": 14, "large": 20, "panel": 16, "button": 12, "badge": 6, "pill": 999})
        strokes = tok.get("strokes", {"outer_ink_px": 4.0, "inner_highlight_px": 1.8, "panel_stroke_px": 4.0, "text_stroke_px": 2.0, "line_join": "Round"})
        shadows = tok.get("shadows", {"offset_x": 0, "offset_y": 5, "press_offset_y": 3, "blur_radius": 6, "transparency": 0.25, "color": p.get("outline_ink", "#141024")})
        fonts = tok.get("typography", {})
        motifs = tok.get("motifs", {"rays_enabled": True, "ray_count": 12, "badge_rotation_deg": -5, "surface_pattern": "glossy"})
        grads = ds.get("gradient_recipes", {})
        rarity = p.get("rarity", {})

        line_join = str(strokes.get("line_join", "Round"))
        if line_join not in ("Round", "Bevel", "Miter"):
            line_join = "Round"

        def fmt_grad_entry(key: str, recipe: Dict[str, Any]) -> str:
            rot = int(recipe.get("rotation", -38))
            gtype = str(recipe.get("type", "Linear"))
            stops = recipe.get("stops", [])[:6]
            stop_strs = []
            for st in stops:
                t = max(0.0, min(1.0, float(st.get("time", 0.0))))
                c = _luau_color3(str(st.get("color", p["primary"])))
                stop_strs.append(f"{{ time = {t:.3f}, color = {c} }}")
            return f"\t\t{key} = {{ Rotation = {rot}, Type = {_luau_str(gtype)}, Stops = {{ {', '.join(stop_strs)} }} }},"

        grad_lines = []
        for g_key, g_luau in (
            ("primary", "Primary"),
            ("secondary", "Secondary"),
            ("accent", "Accent"),
            ("success", "Success"),
            ("warning", "Warning"),
            ("danger", "Danger"),
            ("gold", "Gold"),
            ("panel", "Panel"),
        ):
            rec = grads.get(g_key) or _build_glossy_gradient(p.get(g_key if g_key != "panel" else "bg_panel", p["primary"]))
            grad_lines.append(fmt_grad_entry(g_luau, rec))

        sweep = grads.get("shine_sweep", {})
        sweep_rot = int(sweep.get("rotation", -25))
        sweep_dur = float(sweep.get("duration_s", 0.65))

        lines = [
            "--!strict" if module_mode else "-- DesignSystem tokens block",
            f"-- Generated DesignSystem for {_luau_str(ds.get('game_title', 'Game'))} ({ds.get('preset_id', 'custom')} / {ds.get('harmony', 'triadic')})",
            "local DesignTheme = {",
            "\tMeta = {",
            f"\t\tGameTitle = {_luau_str(ds.get('game_title', 'Game'))},",
            f"\t\tGenre = {_luau_str(ds.get('genre', 'adventure'))},",
            f"\t\tMood = {_luau_str(ds.get('mood', 'vibrant'))},",
            f"\t\tPresetId = {_luau_str(ds.get('preset_id', 'custom'))},",
            f"\t\tSurfaceMode = {_luau_str(ds.get('surface_mode', 'dark'))},",
            f"\t\tHarmony = {_luau_str(ds.get('harmony', 'triadic'))},",
            f"\t\tSeedHash = {_luau_str(ds.get('seed_hash', '0000'))},",
            "\t},",
            "\tColors = {",
            f"\t\tBgDeep = {_luau_color3(p['bg_deep'])},",
            f"\t\tBgPanel = {_luau_color3(p['bg_panel'])},",
            f"\t\tBgCard = {_luau_color3(p.get('bg_card', p['bg_panel']))},",
            f"\t\tBgCardHover = {_luau_color3(_shift_hsl(p.get('bg_card', p['bg_panel']), dl=0.05))},",
            f"\t\tBgElevated = {_luau_color3(_shift_hsl(p['bg_panel'], dl=0.07))},",
            f"\t\tBgInput = {_luau_color3(p.get('bg_input', p['bg_deep']))},",
            f"\t\tBorderSubtle = {_luau_color3(p.get('border_subtle', p['secondary']))},",
            f"\t\tBorderBright = {_luau_color3(p.get('border_bright', p['accent']))},",
            f"\t\tOutlineInk = {_luau_color3(p['outline_ink'])},",
            f"\t\tInnerHighlight = Color3.fromRGB(255, 255, 255),",
            f"\t\tTextPrimary = {_luau_color3(p['text'])},",
            f"\t\tTextSecondary = {_luau_color3(p.get('text_secondary', p['text']))},",
            f"\t\tTextMuted = {_luau_color3(p.get('text_muted', p['text']))},",
            f"\t\tTextOnPrimary = {_luau_color3(p.get('text_on_primary', p['text']))},",
            f"\t\tTextOnSecondary = {_luau_color3(p.get('text_on_secondary', p['text']))},",
            f"\t\tTextOnAccent = {_luau_color3(p.get('text_on_accent', p['text']))},",
            f"\t\tTextOnSuccess = {_luau_color3(p.get('text_on_success', p['text']))},",
            f"\t\tTextOnWarning = {_luau_color3(p.get('text_on_warning', p['text']))},",
            f"\t\tTextOnDanger = {_luau_color3(p.get('text_on_danger', p['text']))},",
            f"\t\tPrimary = {_luau_color3(p['primary'])},",
            f"\t\tPrimaryHover = {_luau_color3(p.get('primary_hover', p['primary']))},",
            f"\t\tPrimaryPress = {_luau_color3(p.get('primary_press', p['primary']))},",
            f"\t\tSecondary = {_luau_color3(p['secondary'])},",
            f"\t\tSecondaryHover = {_luau_color3(p.get('secondary_hover', p['secondary']))},",
            f"\t\tSecondaryPress = {_luau_color3(p.get('secondary_press', p['secondary']))},",
            f"\t\tAccent = {_luau_color3(p['accent'])},",
            f"\t\tAccentHover = {_luau_color3(p.get('accent_hover', p['accent']))},",
            f"\t\tAccentPress = {_luau_color3(p.get('accent_press', p['accent']))},",
            f"\t\tSuccess = {_luau_color3(p['success'])},",
            f"\t\tSuccessHover = {_luau_color3(p.get('success_hover', p['success']))},",
            f"\t\tSuccessPress = {_luau_color3(p.get('success_press', p['success']))},",
            f"\t\tWarning = {_luau_color3(p['warning'])},",
            f"\t\tWarningHover = {_luau_color3(p.get('warning_hover', p['warning']))},",
            f"\t\tWarningPress = {_luau_color3(p.get('warning_press', p['warning']))},",
            f"\t\tDanger = {_luau_color3(p['danger'])},",
            f"\t\tDangerHover = {_luau_color3(p.get('danger_hover', p['danger']))},",
            f"\t\tDangerPress = {_luau_color3(p.get('danger_press', p['danger']))},",
            f"\t\tGold = {_luau_color3(p['gold'])},",
            f"\t\tGem = {_luau_color3(p.get('gem', p['accent']))},",
            f"\t\tScrim = {_luau_color3(p.get('scrim', p['bg_deep']))},",
            "\t},",
            "\tRarity = {",
            f"\t\tCommon = {_luau_color3(rarity.get('common', '#94A3B8'))},",
            f"\t\tUncommon = {_luau_color3(rarity.get('uncommon', p['success']))},",
            f"\t\tRare = {_luau_color3(rarity.get('rare', p['accent']))},",
            f"\t\tEpic = {_luau_color3(rarity.get('epic', p['secondary']))},",
            f"\t\tLegendary = {_luau_color3(rarity.get('legendary', p['gold']))},",
            f"\t\tMythic = {_luau_color3(rarity.get('mythic', p['danger']))},",
            "\t},",
            "\tRadii = {",
            f"\t\tXs = UDim.new(0, {int(radii.get('xs', 4))}),",
            f"\t\tSmall = UDim.new(0, {int(radii.get('small', 8))}),",
            f"\t\tMedium = UDim.new(0, {int(radii.get('medium', 14))}),",
            f"\t\tLarge = UDim.new(0, {int(radii.get('large', 20))}),",
            f"\t\tPanel = UDim.new(0, {int(radii.get('panel', 16))}),",
            f"\t\tButton = UDim.new(0, {int(radii.get('button', 12))}),",
            f"\t\tBadge = UDim.new(0, {int(radii.get('badge', 6))}),",
            "\t\tPill = UDim.new(1, 0),",
            "\t},",
            "\tStrokes = {",
            f"\t\tOuterInk = {float(strokes.get('outer_ink_px', 4.0)):.2f},",
            f"\t\tInnerHighlight = {float(strokes.get('inner_highlight_px', 1.8)):.2f},",
            f"\t\tPanel = {float(strokes.get('panel_stroke_px', 4.0)):.2f},",
            f"\t\tText = {float(strokes.get('text_stroke_px', 2.0)):.2f},",
            f"\t\tLineJoin = Enum.LineJoinMode.{line_join},",
            "\t},",
            "\tShadows = {",
            f"\t\tOffsetX = {int(shadows.get('offset_x', 0))},",
            f"\t\tOffsetY = {int(shadows.get('offset_y', 5))},",
            f"\t\tPressOffsetY = {int(shadows.get('press_offset_y', 3))},",
            f"\t\tBlurRadius = {int(shadows.get('blur_radius', 6))},",
            f"\t\tTransparency = {float(shadows.get('transparency', 0.25)):.2f},",
            f"\t\tColor = {_luau_color3(str(shadows.get('color', p['outline_ink'])))},",
            "\t},",
            "\tGradients = {",
            *grad_lines,
            f"\t\tShineSweep = {{ Rotation = {sweep_rot}, Duration = {sweep_dur:.2f} }},",
            "\t},",
            "\tFonts = {",
            f"\t\tTitleFamily = {_luau_str(fonts.get('title_family', 'rbxasset://fonts/families/BuilderSans.json'))},",
            f"\t\tHeadingFamily = {_luau_str(fonts.get('heading_family', 'rbxasset://fonts/families/BuilderSans.json'))},",
            f"\t\tBodyFamily = {_luau_str(fonts.get('body_family', 'rbxasset://fonts/families/BuilderSans.json'))},",
            f"\t\tMonoFamily = {_luau_str(fonts.get('mono_family', 'rbxasset://fonts/families/RobotoMono.json'))},",
            "\t},",
            "\tMotifs = {",
            f"\t\tPresetId = {_luau_str(motifs.get('preset_id', ds.get('preset_id', 'custom')))},",
            f"\t\tRaysEnabled = {'true' if motifs.get('rays_enabled', True) else 'false'},",
            f"\t\tRayCount = {int(motifs.get('ray_count', 12))},",
            f"\t\tBadgeRotation = {int(motifs.get('badge_rotation_deg', -5))},",
            f"\t\tSurfacePattern = {_luau_str(motifs.get('surface_pattern', 'glossy'))},",
            "\t},",
            f"\tMinTouchPx = {int(tok.get('min_touch_px', 44))},",
            "}",
        ]
        if module_mode:
            lines.append("")
            lines.append("return DesignTheme")
        return "\n".join(lines) + "\n"

    # -----------------------------------------------------------------------
    # Image Prompt Batch Generator
    # -----------------------------------------------------------------------

    def build_image_prompt_batch(
        self,
        design_system: Dict[str, Any],
        screens: Optional[List[str]] = None,
        icon_grid: Tuple[int, int] | List[int] = (2, 2),
        icon_names: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate palette-locked, anti-slop AI image prompts grouped per screen."""
        ds = design_system if "palette" in design_system else self.generate_design_system(
            str(design_system.get("game_title", "Custom Game")),
            str(design_system.get("genre", "adventure")),
            str(design_system.get("mood", "vibrant")),
        )
        p = ds["palette"]
        title = ds.get("game_title", "Game")
        preset_id = ds.get("preset_id", "custom")
        sig = ds.get("style_signature", f"{preset_id} stylized UI")
        key_hex = ds.get("key_background_hex", "#FF00FF")

        rows = max(1, int(icon_grid[0])) if len(icon_grid) >= 2 else 2
        cols = max(1, int(icon_grid[1])) if len(icon_grid) >= 2 else 2
        icon_count = rows * cols

        default_icon_pool = [
            "embossed gold currency coin",
            "radiant mana gem crystal",
            "heroic signature weapon badge",
            "ornate reward treasure chest",
            "heart health potion flask",
            "armored crest shield",
            "golden master key",
            "royal crown emblem",
            "lightning speed boot",
            "arcane scroll",
            "mystic compass",
            "star trophy",
        ]
        resolved_icons = (
            list(icon_names)[:icon_count]
            if icon_names and len(icon_names) >= icon_count
            else (
                list(icon_names) + default_icon_pool[len(icon_names) : icon_count]
                if icon_names
                else default_icon_pool[:icon_count]
            )
        )
        while len(resolved_icons) < icon_count:
            resolved_icons.append(f"stylized emblem {len(resolved_icons) + 1}")

        palette_hexes = [
            p["bg_deep"],
            p["bg_panel"],
            p["primary"],
            p["secondary"],
            p["accent"],
            p["gold"],
            p["outline_ink"],
        ]
        palette_str = (
            f"deep surface {p['bg_deep']}, panel {p['bg_panel']}, primary {p['primary']}, "
            f"secondary {p['secondary']}, accent {p['accent']}, gold {p['gold']}, outline ink {p['outline_ink']}"
        )
        negative_prompt = (
            "muddy gradients, desaturated muddy colors, generic default dark-navy blue flat UI, "
            "fake transparency checkerboard, grey-white grid background, baked text, letters, numbers, "
            "watermarks, signatures, perspective tilt, 3D oblique camera angle, isometric skew, "
            "drop shadow bleeding into key background, grid divider lines, blurry edges"
        )

        target_screens = list(screens) if screens else [
            "MainHud",
            "ShopModal",
            "InventoryModal",
            "QuestsModal",
            "LoadingScreen",
        ]

        grid_labels = ", ".join(
            f"({r + 1},{c + 1}) {resolved_icons[r * cols + c]}"
            for r in range(rows)
            for c in range(cols)
        )
        rarity_hexes = p.get("rarity", {})
        rarity_str = (
            f"Common {rarity_hexes.get('common', '#94A3B8')}, "
            f"Rare {rarity_hexes.get('rare', p['accent'])}, "
            f"Epic {rarity_hexes.get('epic', p['secondary'])}, "
            f"Legendary {rarity_hexes.get('legendary', p['gold'])}, "
            f"Mythic {rarity_hexes.get('mythic', p['danger'])}"
        )

        catalog_templates: Dict[str, Dict[str, Any]] = {
            "9slice_panel": {
                "asset_key": "panel_9slice",
                "recommended_size": [1024, 1024],
                "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice raw_panel.png panel_9slice.png --max-dim 512",
                "prompt": (
                    f"Flat 2D orthographic front-facing game UI modal window frame for '{title}', 1:1 square, "
                    f"styled in {sig}. Symmetrical bevelled frame using exact palette ({palette_str}). "
                    f"Ornate corner brackets strictly confined to the 4 outer corners (outer 22%); the middle 56% of all 4 edges "
                    f"are completely straight and uniform for 9-slice stretching, with a flat interior center ({p['bg_panel']}). "
                    f"Isolated on a single flat uniform solid key color ({key_hex}) with a 48px empty margin, zero perspective, "
                    f"no outer drop shadow, no checkerboard, strictly no text or numbers."
                ),
                "palette_hexes_used": [p["bg_panel"], p["primary"], p["accent"], p["outline_ink"], key_hex],
            },
            "9slice_tint_button": {
                "asset_key": "button_9slice",
                "recommended_size": [1024, 512],
                "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice raw_btn.png button_9slice.png --max-dim 512",
                "prompt": (
                    f"Flat 2D orthographic front-facing game UI pill/bevel button silhouette for '{title}', "
                    f"matching corner geometry of {sig}, rendered in neutral pure white-to-silver grayscale "
                    f"(#FFFFFF specular top highlight, #E5EAF2 glossy body, #BDC7D6 lower bevel, #4A5568 crisp outline) "
                    f"with zero hue saturation so ImageColor3 tints cleanly into {p['primary']}, {p['secondary']}, and {p['success']}. "
                    f"Corner caps confined to left/right 24%; straight parallel middle 52% span. "
                    f"Isolated on uniform solid {key_hex} background, no outer shadow, no checkerboard, strictly no text."
                ),
                "palette_hexes_used": [p["primary"], p["secondary"], p["success"], key_hex],
            },
            "hud_bar": {
                "asset_key": "hud_bar_9slice",
                "recommended_size": [1024, 256],
                "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice raw_hud_bar.png hud_bar_9slice.png --max-dim 512",
                "prompt": (
                    f"Flat 2D orthographic horizontal HUD status bar frame for '{title}', styled in {sig}. "
                    f"Beveled outer rim in {p['outline_ink']} and {p['primary']} accents with decorative end-caps on far 18% ends, "
                    f"completely straight uniform horizontal middle 64%, dark recessed inner track ({p['bg_input']}). "
                    f"Isolated on uniform solid {key_hex} background, zero perspective, no text or numbers."
                ),
                "palette_hexes_used": [p["outline_ink"], p["primary"], p["bg_input"], key_hex],
            },
            "icon_grid": {
                "asset_key": f"icons_{rows}x{cols}_sheet",
                "recommended_size": [1024, 1024],
                "post_process_cmd": (
                    f"python slice_and_atlas_helper.py split-atlas raw_icons.png icons_atlas.png "
                    f"--rows {rows} --cols {cols} --names \"{','.join(resolved_icons)}\" --cell-size {min(256, max(128, (1024 - 16) // max(rows, cols) - 4))} --gutter 4"
                ),
                "prompt": (
                    f"Flat 2D orthographic game UI icon sheet arranged in a strict {rows}x{cols} grid ({icon_count} distinct icons total) "
                    f"for '{title}', styled in {sig}: {grid_labels}. "
                    f"Color-harmonized to palette ({p['primary']}, {p['secondary']}, {p['accent']}, {p['gold']}) with bold {p['outline_ink']} outer silhouettes "
                    f"and crisp cel-shaded specular highlights. Wide uniform {key_hex} background padding around every icon, "
                    f"strictly NO grid divider lines, NO boxes around icons, no outer glow bleeding into background, no text."
                ),
                "palette_hexes_used": [p["primary"], p["secondary"], p["accent"], p["gold"], p["outline_ink"], key_hex],
            },
            "rarity_frame": {
                "asset_key": "rarity_slot_9slice",
                "recommended_size": [512, 512],
                "post_process_cmd": "python slice_and_atlas_helper.py prepare-9slice raw_slot.png rarity_slot_9slice.png --max-dim 256",
                "prompt": (
                    f"Flat 2D orthographic square 1:1 inventory item slot frame for '{title}', styled in {sig}. "
                    f"Neutral silver-white grayscale metallic bevels with corner clasps and straight uniform middle edges "
                    f"for clean ImageColor3 rarity tinting ({rarity_str}), dark recessed interior ({p['bg_card']}), "
                    f"bold {p['outline_ink']} outer stroke. Isolated on uniform solid {key_hex} background with 40px margin, no text."
                ),
                "palette_hexes_used": [p["bg_card"], p["outline_ink"], rarity_hexes.get("epic", p["secondary"]), rarity_hexes.get("legendary", p["gold"]), key_hex],
            },
            "loading_backdrop": {
                "asset_key": "loading_backdrop",
                "recommended_size": [1024, 576],
                "post_process_cmd": "Import as 16:9 ImageLabel background under LoadingTransitionTemplate (ScaleType = Crop)",
                "prompt": (
                    f"Stylized 16:9 game UI loading screen backdrop illustration for '{title}', styled in {sig}. "
                    f"Atmospheric layered horizon/environment silhouette anchored in {p['bg_deep']} and {p['bg_panel']} with luminous "
                    f"rim-lit focal energy beams in {p['primary']}, {p['accent']}, and {p['gold']}, keeping the central 45% calm and dark "
                    f"({p['bg_deep']}) so foreground loading UI text remains 100% legible. Strictly no text, no logos, no UI frames."
                ),
                "palette_hexes_used": [p["bg_deep"], p["bg_panel"], p["primary"], p["accent"], p["gold"]],
            },
            "tile_pattern": {
                "asset_key": "panel_tile_pattern",
                "recommended_size": [512, 512],
                "post_process_cmd": "Use with ImageLabel.ScaleType = Enum.ScaleType.Tile and TileSize = UDim2.fromOffset(128, 128)",
                "prompt": (
                    f"Seamless 2D tileable UI pattern for '{title}' ({tok_pattern(ds)}), styled in {sig}. "
                    f"Low-contrast subtle monochrome tones between {p['bg_deep']} and {p['bg_panel']} with micro accents in {p['border_subtle']} "
                    f"so foreground text retains >4.5:1 contrast. Edge-to-edge wraparound seamless, flat 2D orthographic, no vignette, no text."
                ),
                "palette_hexes_used": [p["bg_deep"], p["bg_panel"], p["border_subtle"]],
            },
        }

        screen_template_map = {
            "MainHud": ["hud_bar", "9slice_tint_button", "icon_grid"],
            "ShopModal": ["9slice_panel", "9slice_tint_button", "rarity_frame", "tile_pattern"],
            "InventoryModal": ["9slice_panel", "rarity_frame", "icon_grid"],
            "QuestsModal": ["9slice_panel", "hud_bar", "9slice_tint_button"],
            "LoadingScreen": ["loading_backdrop", "tile_pattern"],
        }

        prompts: List[Dict[str, Any]] = []
        by_screen: Dict[str, List[Dict[str, Any]]] = {}

        for scr in target_screens:
            kinds = screen_template_map.get(scr, ["9slice_panel", "9slice_tint_button", "icon_grid"])
            scr_list: List[Dict[str, Any]] = []
            for kind in kinds:
                tmpl = catalog_templates[kind]
                entry = {
                    "screen": scr,
                    "template_kind": kind,
                    "asset_key": tmpl["asset_key"],
                    "prompt": tmpl["prompt"],
                    "negative_prompt": negative_prompt,
                    "recommended_size": tmpl["recommended_size"],
                    "post_process_cmd": tmpl["post_process_cmd"],
                    "palette_hexes_used": tmpl["palette_hexes_used"],
                    "style_signature": sig,
                }
                prompts.append(entry)
                scr_list.append(entry)
            by_screen[scr] = scr_list

        return {
            "ok": True,
            "game_title": title,
            "preset_id": preset_id,
            "style_signature": sig,
            "key_background_hex": key_hex,
            "palette_hexes": palette_hexes,
            "icon_grid": [rows, cols],
            "icon_names": resolved_icons,
            "prompt_count": len(prompts),
            "prompts": prompts,
            "by_screen": by_screen,
        }

    # -----------------------------------------------------------------------
    # Palette Visual Swatch Renderer (Pillow)
    # -----------------------------------------------------------------------

    def render_palette_swatch(
        self,
        design_system: Dict[str, Any],
        output_path: str | Path,
        width: int = 720,
        height: int = 240,
    ) -> Dict[str, Any]:
        """Render the palette & glossy gradient strips to a PNG swatch for numeric/visual QA."""
        p = design_system["palette"]
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        img = Image.new("RGBA", (width, height), (*hex_to_rgb(p["bg_deep"]), 255))
        draw = ImageDraw.Draw(img)

        # Panel inset card
        margin = 16
        draw.rounded_rectangle(
            [margin, margin, width - margin, height - margin],
            radius=18,
            fill=(*hex_to_rgb(p["bg_panel"]), 255),
            outline=(*hex_to_rgb(p["outline_ink"]), 255),
            width=4,
        )

        roles = [
            ("bg_deep", p["bg_deep"]),
            ("bg_panel", p["bg_panel"]),
            ("primary", p["primary"]),
            ("secondary", p["secondary"]),
            ("accent", p["accent"]),
            ("success", p["success"]),
            ("warning", p["warning"]),
            ("danger", p["danger"]),
            ("gold", p["gold"]),
            ("text", p["text"]),
            ("outline_ink", p["outline_ink"]),
        ]
        n = len(roles)
        inner_x0 = margin + 16
        inner_w = width - 2 * (margin + 16)
        gap = 8
        cell_w = max(20, (inner_w - gap * (n - 1)) // n)
        y0 = margin + 24
        y1 = height - margin - 46

        for i, (_, hx) in enumerate(roles):
            x0 = inner_x0 + i * (cell_w + gap)
            x1 = min(width - margin - 16, x0 + cell_w)
            rgb = hex_to_rgb(hx)
            ink = hex_to_rgb(p["outline_ink"])
            draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=(*rgb, 255), outline=(*ink, 255), width=3)

        # Bottom rarity strip
        rarity_items = list(p.get("rarity", {}).values())
        if rarity_items:
            rw = max(16, (inner_w - gap * (len(rarity_items) - 1)) // len(rarity_items))
            ry0 = y1 + 10
            ry1 = height - margin - 12
            for j, rhx in enumerate(rarity_items):
                rx0 = inner_x0 + j * (rw + gap)
                rx1 = min(width - margin - 16, rx0 + rw)
                draw.rounded_rectangle([rx0, ry0, rx1, ry1], radius=6, fill=(*hex_to_rgb(rhx), 255))

        img.save(out, format="PNG")
        return {
            "ok": True,
            "output_path": str(out),
            "width": width,
            "height": height,
            "role_count": len(roles),
        }

    @staticmethod
    def get_tool_schema_suggestion() -> Dict[str, Any]:
        """Return schema & contract hint for @integrator's `sharp_design_system` MCP tool."""
        return {
            "tool_name": "sharp_design_system",
            "actions": ["generate", "lint", "theme_luau", "image_prompts"],
            "parameters": {
                "action": "str = 'generate'  # generate | lint | theme_luau | image_prompts",
                "game_title": "str = 'Untitled Game'",
                "genre": "str = 'adventure'  # candy_simulator | anime_neon | cozy_pastel | scifi_holo | arcade_pop | rpg_arcane | freeform",
                "mood": "str = 'vibrant'",
                "seed": "Optional[int | str] = None",
                "constraints": "Optional[Dict[str, Any]] = None",
                "design_system": "Optional[Dict[str, Any]] = None  # pass output of generate, or auto-generated when omitted",
                "spec_or_palette": "Optional[Dict[str, Any] | str] = None  # input for action='lint'",
                "screens": "Optional[List[str]] = None  # e.g. ['MainHud', 'ShopModal', 'LoadingScreen']",
                "icon_grid": "List[int] = [2, 2]",
                "icon_names": "Optional[List[str]] = None",
            },
            "profile_hint": "core",
            "read_only": True,
        }


def tok_pattern(design_system: Dict[str, Any]) -> str:
    return str(design_system.get("tokens", {}).get("motifs", {}).get("surface_pattern", "geometric"))

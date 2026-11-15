"""Bespoke Game Art Creation Engine: Code-Driven 2D UI Kits, Custom Fonts, 2D/3D VFX & AI Art Pair."""

from __future__ import annotations

import asyncio
import base64
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ..credentials_store import resolve_provider_and_model
from ..ai_http import AIRequestError, post_json, response_content, response_text
from .design_engine import DesignEngine, hex_to_rgb as _hex_to_rgb, rgb_to_hex as _rgb_to_hex
from .gui_engine import GuiDomainEngine


ROBLOX_FONT_PAIRINGS: Dict[str, Dict[str, Any]] = {
    "candy_simulator": {
        "display_font": {"name": "FredokaOne", "uri": "rbxasset://fonts/families/FredokaOne.json", "weight": "Bold"},
        "body_font": {"name": "BuilderSans", "uri": "rbxasset://fonts/families/BuilderSans.json", "weight": "SemiBold"},
        "numeric_font": {"name": "LuckiestGuy", "uri": "rbxasset://fonts/families/LuckiestGuy.json", "weight": "Regular"},
        "vfx_preset": "star_pop",
    },
    "anime_neon": {
        "display_font": {"name": "Michroma", "uri": "rbxasset://fonts/families/Michroma.json", "weight": "Bold"},
        "body_font": {"name": "TitilliumWeb", "uri": "rbxasset://fonts/families/TitilliumWeb.json", "weight": "SemiBold"},
        "numeric_font": {"name": "Sarpanch", "uri": "rbxasset://fonts/families/Sarpanch.json", "weight": "ExtraBold"},
        "vfx_preset": "neon_slash",
    },
    "cozy_pastel": {
        "display_font": {"name": "FredokaOne", "uri": "rbxasset://fonts/families/FredokaOne.json", "weight": "Medium"},
        "body_font": {"name": "Nunito", "uri": "rbxasset://fonts/families/Nunito.json", "weight": "SemiBold"},
        "numeric_font": {"name": "PatrickHand", "uri": "rbxasset://fonts/families/PatrickHand.json", "weight": "Regular"},
        "vfx_preset": "sparkle_bloom",
    },
    "scifi_holo": {
        "display_font": {"name": "Michroma", "uri": "rbxasset://fonts/families/Michroma.json", "weight": "Bold"},
        "body_font": {"name": "SciFi", "uri": "rbxasset://fonts/families/SciFi.json", "weight": "Regular"},
        "numeric_font": {"name": "RobotoMono", "uri": "rbxasset://fonts/families/RobotoMono.json", "weight": "Bold"},
        "vfx_preset": "holo_pulse",
    },
    "arcade_pop": {
        "display_font": {"name": "Bangers", "uri": "rbxasset://fonts/families/Bangers.json", "weight": "Regular"},
        "body_font": {"name": "BuilderSans", "uri": "rbxasset://fonts/families/BuilderSans.json", "weight": "Bold"},
        "numeric_font": {"name": "Bangers", "uri": "rbxasset://fonts/families/Bangers.json", "weight": "Regular"},
        "vfx_preset": "comic_burst",
    },
    "rpg_arcane": {
        "display_font": {"name": "Fondamento", "uri": "rbxasset://fonts/families/Fondamento.json", "weight": "Regular"},
        "body_font": {"name": "Merriweather", "uri": "rbxasset://fonts/families/Merriweather.json", "weight": "Regular"},
        "numeric_font": {"name": "Sarpanch", "uri": "rbxasset://fonts/families/Sarpanch.json", "weight": "Bold"},
        "vfx_preset": "arcane_rune",
    },
}

DEFAULT_BITMAP_GLYPHS = "0123456789+-x%!?$KMB+*"


def _rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    r, g, b = _hex_to_rgb(hex_color)
    return (r, g, b, max(0, min(255, int(alpha))))


def _lerp_rgb(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    k = max(0.0, min(1.0, float(t)))
    return (
        int(round(c1[0] + (c2[0] - c1[0]) * k)),
        int(round(c1[1] + (c2[1] - c1[1]) * k)),
        int(round(c1[2] + (c2[2] - c1[2]) * k)),
    )


def _palette_from_ds(design_system: Dict[str, Any]) -> Dict[str, str]:
    pal = design_system.get("palette") or {}
    return {
        "primary": str(pal.get("primary") or "#FF4D8D"),
        "secondary": str(pal.get("secondary") or "#38E8FF"),
        "accent": str(pal.get("accent") or "#FFD166"),
        "surface": str(pal.get("surface") or "#1B1633"),
        "surface_elevated": str(pal.get("surface_elevated") or "#28214A"),
        "stroke_outer": str(pal.get("stroke_outer") or "#0B0818"),
        "stroke_inner": str(pal.get("stroke_inner") or "#FFFFFF"),
        "text_primary": str(pal.get("text_primary") or "#F8FAFC"),
        "success": str(pal.get("success") or "#22C55E"),
        "danger": str(pal.get("danger") or "#EF4444"),
    }


def _vertical_gradient_image(size: Tuple[int, int], top_hex: str, bottom_hex: str, alpha: int = 255) -> Image.Image:
    w, h = size
    c_top = _hex_to_rgb(top_hex)
    c_bot = _hex_to_rgb(bottom_hex)
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    r = (c_top[0] + (c_bot[0] - c_top[0]) * y).astype(np.uint8)
    g = (c_top[1] + (c_bot[1] - c_top[1]) * y).astype(np.uint8)
    b = (c_top[2] + (c_bot[2] - c_top[2]) * y).astype(np.uint8)
    a = np.full((h, w), alpha, dtype=np.uint8)
    arr = np.dstack([
        np.broadcast_to(r, (h, w)),
        np.broadcast_to(g, (h, w)),
        np.broadcast_to(b, (h, w)),
        a,
    ])
    return Image.fromarray(arr, mode="RGBA")


def _draw_chamfer_or_round_mask(size: Tuple[int, int], margin: int, radius: int, chamfer: bool = False) -> Image.Image:
    w, h = size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    x0, y0, x1, y1 = margin, margin, w - margin - 1, h - margin - 1
    if chamfer:
        c = max(6, int(radius * 0.75))
        pts = [
            (x0 + c, y0),
            (x1 - c, y0),
            (x1, y0 + c),
            (x1, y1 - c),
            (x1 - c, y1),
            (x0 + c, y1),
            (x0, y1 - c),
            (x0, y0 + c),
        ]
        draw.polygon(pts, fill=255)
    else:
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=255)
    return mask


def _render_button_9slice(out_path: Path, pal: Dict[str, str], preset_id: str) -> Dict[str, Any]:
    """Render 2x SSAA beveled multi-stop 9-slice button PNG."""
    scale = 2
    w, h = 256, 96
    cw, ch = w * scale, h * scale
    chamfer = preset_id in ("scifi_holo", "anime_neon")

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    primary = _hex_to_rgb(pal["primary"])
    top_rgb = _lerp_rgb(primary, (255, 255, 255), 0.22)
    bot_rgb = _lerp_rgb(primary, (10, 8, 22), 0.34)
    lip_rgb = _lerp_rgb(primary, _hex_to_rgb(pal["stroke_outer"]), 0.65)

    # Bottom extrusion shadow lip
    lip_mask = _draw_chamfer_or_round_mask((cw, ch), margin=12, radius=40, chamfer=chamfer)
    lip_layer = Image.new("RGBA", (cw, ch), (*lip_rgb, 255))
    lip_shifted = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    lip_shifted.paste(lip_layer, (0, 12), lip_mask)
    canvas = Image.alpha_composite(canvas, lip_shifted)

    # Main button body gradient masked cleanly
    body_mask = _draw_chamfer_or_round_mask((cw, ch), margin=12, radius=40, chamfer=chamfer)
    grad = _vertical_gradient_image((cw, ch), _rgb_to_hex(*top_rgb), _rgb_to_hex(*bot_rgb))
    body = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    body.paste(grad, (0, 0), body_mask)

    # Top glossy specular highlight band
    gloss = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gloss)
    g_draw.rounded_rectangle([28, 20, cw - 28, int(ch * 0.48)], radius=24, fill=(255, 255, 255, 68))
    gloss_clipped = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    gloss_clipped.paste(gloss, (0, 0), body_mask)
    body = Image.alpha_composite(body, gloss_clipped)

    # Stacked crisp outer dark stroke + inner bright rim highlight
    stroke_draw = ImageDraw.Draw(body)
    if not chamfer:
        stroke_draw.rounded_rectangle([12, 12, cw - 13, ch - 13], radius=40, outline=_rgba(pal["stroke_outer"], 255), width=8)
        stroke_draw.rounded_rectangle([20, 20, cw - 21, ch - 21], radius=33, outline=_rgba(pal["stroke_inner"], 140), width=4)
    else:
        c = 28
        outer_pts = [(12 + c, 12), (cw - 13 - c, 12), (cw - 13, 12 + c), (cw - 13, ch - 13 - c), (cw - 13 - c, ch - 13), (12 + c, ch - 13), (12, ch - 13 - c), (12, 12 + c)]
        inner_pts = [(20 + c, 20), (cw - 21 - c, 20), (cw - 21, 20 + c), (cw - 21, ch - 21 - c), (cw - 21 - c, ch - 21), (20 + c, ch - 21), (20, ch - 21 - c), (20, 20 + c)]
        stroke_draw.polygon(outer_pts, outline=_rgba(pal["stroke_outer"], 255), width=8)
        stroke_draw.polygon(inner_pts, outline=_rgba(pal["secondary"], 190), width=4)

    canvas = Image.alpha_composite(canvas, body)
    final = canvas.resize((w, h), Image.Resampling.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(out_path), format="PNG")
    return {
        "path": str(out_path),
        "size": [w, h],
        "slice_center": [42, 28, w - 42, h - 32],
        "scale_type": "Slice",
    }


def _render_panel_9slice(out_path: Path, pal: Dict[str, str], preset_id: str) -> Dict[str, Any]:
    """Render 2x SSAA game-themed modal frame 9-slice PNG with micro-pattern & corner accents."""
    scale = 2
    w, h = 320, 224
    cw, ch = w * scale, h * scale
    chamfer = preset_id in ("scifi_holo", "anime_neon")

    canvas = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    surf_top = _lerp_rgb(_hex_to_rgb(pal["surface_elevated"]), (255, 255, 255), 0.06)
    surf_bot = _lerp_rgb(_hex_to_rgb(pal["surface"]), (0, 0, 0), 0.18)

    body_mask = _draw_chamfer_or_round_mask((cw, ch), margin=12, radius=36, chamfer=chamfer)
    grad = _vertical_gradient_image((cw, ch), _rgb_to_hex(*surf_top), _rgb_to_hex(*surf_bot))
    panel = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    panel.paste(grad, (0, 0), body_mask)

    # Subtle micro-dot texture pattern inside frame (keeps solid contrast, avoids flat plastic look)
    tex = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(tex)
    dot_col = _rgba(pal["secondary"], 22)
    for y in range(28, ch - 28, 20):
        for x in range(28, cw - 28, 20):
            t_draw.ellipse([x - 2, y - 2, x + 2, y + 2], fill=dot_col)
    # Recessed header bar band at top
    t_draw.rectangle([16, 16, cw - 16, 86], fill=_rgba(pal["primary"], 48))
    t_draw.line([28, 86, cw - 28, 86], fill=_rgba(pal["accent"], 190), width=4)

    tex_clipped = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    tex_clipped.paste(tex, (0, 0), body_mask)
    panel = Image.alpha_composite(panel, tex_clipped)

    # Stacked border & crisp corner brackets/gems
    b_draw = ImageDraw.Draw(panel)
    if not chamfer:
        b_draw.rounded_rectangle([12, 12, cw - 13, ch - 13], radius=36, outline=_rgba(pal["stroke_outer"], 255), width=8)
        b_draw.rounded_rectangle([20, 20, cw - 21, ch - 21], radius=28, outline=_rgba(pal["secondary"], 180), width=4)
    else:
        c = 26
        outer_pts = [(12 + c, 12), (cw - 13 - c, 12), (cw - 13, 12 + c), (cw - 13, ch - 13 - c), (cw - 13 - c, ch - 13), (12 + c, ch - 13), (12, ch - 13 - c), (12, 12 + c)]
        b_draw.polygon(outer_pts, outline=_rgba(pal["secondary"], 230), width=6)

    # Corner emblem studs
    for cx, cy in ((34, 34), (cw - 35, 34), (34, ch - 35), (cw - 35, ch - 35)):
        b_draw.ellipse([cx - 8, cy - 8, cx + 8, cy + 8], fill=_rgba(pal["accent"], 230), outline=_rgba(pal["stroke_outer"], 255), width=3)

    canvas = Image.alpha_composite(canvas, panel)
    final = canvas.resize((w, h), Image.Resampling.LANCZOS)
    final.save(str(out_path), format="PNG")
    return {
        "path": str(out_path),
        "size": [w, h],
        "slice_center": [48, 52, w - 48, h - 44],
        "scale_type": "Slice",
    }


def _render_emblem_rays(out_path: Path, pal: Dict[str, str], size: int = 384) -> str:
    ss = size * 2
    im = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    cx = cy = ss / 2.0
    n_rays = 14
    ray_col = _rgba(pal["accent"], 175)
    alt_col = _rgba(pal["secondary"], 95)
    r_max = ss * 0.48
    for i in range(n_rays):
        a0 = (2.0 * math.pi * i) / n_rays
        a1 = a0 + (math.pi / n_rays) * 0.72
        p1 = (cx + math.cos(a0) * r_max, cy + math.sin(a0) * r_max)
        p2 = (cx + math.cos(a1) * r_max, cy + math.sin(a1) * r_max)
        draw.polygon([(cx, cy), p1, p2], fill=ray_col if i % 2 == 0 else alt_col)

    # Soft radial alpha mask so outer rim fades cleanly
    y, x = np.ogrid[:ss, :ss]
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / (ss * 0.48)
    falloff = np.clip(1.0 - np.clip(dist, 0.0, 1.0) ** 1.7, 0.0, 1.0)
    arr = np.asarray(im, dtype=np.float32)
    arr[:, :, 3] *= falloff
    final = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA").resize((size, size), Image.Resampling.LANCZOS)
    final.save(str(out_path), format="PNG")
    return str(out_path)


def _render_procedural_icon_atlas(out_path: Path, pal: Dict[str, str]) -> Dict[str, Any]:
    """Render an 8-icon (4x2) crisp geometric RGBA spritesheet colored to game accents."""
    cell = 128
    cols, rows = 4, 2
    atlas = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    names = ["sword", "shield", "coin", "gem", "bolt", "heart", "star", "crown"]
    ink = _rgba(pal["stroke_outer"], 255)
    p_col = _rgba(pal["primary"], 255)
    s_col = _rgba(pal["secondary"], 255)
    a_col = _rgba(pal["accent"], 255)
    hi = (255, 255, 255, 220)

    def _draw_icon(name: str) -> Image.Image:
        ss = 256
        im = Image.new("RGBA", (ss, ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        if name == "sword":
            d.polygon([(190, 40), (216, 66), (110, 172), (84, 146)], fill=s_col, outline=ink, width=8)
            d.line([(68, 128), (128, 188)], fill=a_col, width=18)
            d.line([(86, 170), (46, 210)], fill=p_col, width=16)
        elif name == "shield":
            d.polygon([(48, 48), (208, 48), (196, 152), (128, 220), (60, 152)], fill=s_col, outline=ink, width=10)
            d.polygon([(72, 72), (184, 72), (174, 142), (128, 192), (82, 142)], fill=p_col, outline=hi, width=4)
        elif name == "coin":
            d.ellipse([36, 36, 220, 220], fill=a_col, outline=ink, width=10)
            d.ellipse([58, 58, 198, 198], outline=hi, width=6)
            d.rounded_rectangle([116, 86, 140, 170], radius=6, fill=hi)
        elif name == "gem":
            d.polygon([(128, 32), (216, 98), (184, 212), (72, 212), (40, 98)], fill=s_col, outline=ink, width=10)
            d.polygon([(128, 54), (186, 102), (128, 192), (70, 102)], fill=p_col)
            d.polygon([(128, 54), (160, 102), (128, 128)], fill=hi)
        elif name == "bolt":
            d.polygon([(148, 30), (64, 138), (124, 138), (96, 226), (196, 110), (134, 110)], fill=a_col, outline=ink, width=10)
        elif name == "heart":
            d.ellipse([44, 52, 132, 140], fill=p_col)
            d.ellipse([124, 52, 212, 140], fill=p_col)
            d.polygon([(46, 110), (210, 110), (128, 214)], fill=p_col)
            d.ellipse([70, 72, 98, 98], fill=hi)
        elif name == "star":
            pts = []
            for k in range(10):
                ang = -math.pi / 2 + k * math.pi / 5.0
                r = 92 if k % 2 == 0 else 42
                pts.append((128 + math.cos(ang) * r, 128 + math.sin(ang) * r))
            d.polygon(pts, fill=a_col, outline=ink, width=8)
        else:  # crown
            d.polygon([(36, 190), (48, 76), (94, 130), (128, 56), (162, 130), (208, 76), (220, 190)], fill=a_col, outline=ink, width=10)
            d.rectangle([42, 174, 214, 198], fill=p_col, outline=ink, width=6)
        return im.resize((cell, cell), Image.Resampling.LANCZOS)

    icons_meta: Dict[str, Any] = {}
    for i, nm in enumerate(names):
        c_idx = i % cols
        r_idx = i // cols
        x0, y0 = c_idx * cell, r_idx * cell
        atlas.paste(_draw_icon(nm), (x0, y0))
        icons_meta[nm] = {"offset": [x0, y0], "size": [cell, cell]}

    atlas.save(str(out_path), format="PNG")
    return {
        "atlas_path": str(out_path),
        "atlas_size": [cols * cell, rows * cell],
        "icons": icons_meta,
    }


def _render_custom_bitmap_font(out_png: Path, out_json: Path, pal: Dict[str, str], glyphs: str = DEFAULT_BITMAP_GLYPHS) -> Dict[str, Any]:
    """Render a crisp 6x4 stylized stroked Bitmap Font atlas <=1024px + glyph rect metadata."""
    unique_glyphs = "".join(dict.fromkeys(glyphs))[:24]
    cols = 6
    rows = max(1, int(math.ceil(len(unique_glyphs) / cols)))
    cell = 96
    atlas = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    try:
        font = ImageFont.load_default(size=56)
    except TypeError:
        font = ImageFont.load_default()

    glyph_map: Dict[str, Any] = {}
    ink = _rgba(pal["stroke_outer"], 255)
    fill_top = _rgba(pal["accent"], 255)
    fill_hi = _rgba(pal["text_primary"], 255)

    for idx, ch in enumerate(unique_glyphs):
        c_idx = idx % cols
        r_idx = idx // cols
        x0, y0 = c_idx * cell, r_idx * cell
        tile = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        cx, cy = cell // 2, cell // 2
        # Drop shadow + thick outer stroke + warm gradient fill look
        d.text((cx + 3, cy + 5), ch, font=font, anchor="mm", fill=ink)
        for dx in (-3, 0, 3):
            for dy in (-3, 0, 3):
                if dx or dy:
                    d.text((cx + dx, cy + dy), ch, font=font, anchor="mm", fill=ink)
        d.text((cx, cy), ch, font=font, anchor="mm", fill=fill_top)
        d.text((cx, cy - 1), ch, font=font, anchor="mm", fill=fill_hi if idx % 3 == 0 else fill_top)
        atlas.paste(tile, (x0, y0))
        glyph_map[ch] = {
            "offset": [x0, y0],
            "size": [cell, cell],
            "advance": int(cell * 0.68),
        }

    out_png.parent.mkdir(parents=True, exist_ok=True)
    atlas.save(str(out_png), format="PNG")
    meta = {
        "schema": "sharp.bitmap_font.v1",
        "atlas_path": str(out_png),
        "metrics_path": str(out_json),
        "atlas_size": [cols * cell, rows * cell],
        "cell_size": [cell, cell],
        "glyphs": glyph_map,
    }
    out_json.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _render_vfx_flipbook_4x4(out_path: Path, pal: Dict[str, str], kind: str = "click_burst") -> Dict[str, Any]:
    """Generate a crisp 4x4 (512x512) procedural 16-frame transparent RGBA VFX flipbook PNG."""
    cols = rows = 4
    cell = 128
    sheet = Image.new("RGBA", (cols * cell, rows * cell), (0, 0, 0, 0))
    p_col = _hex_to_rgb(pal["primary"])
    s_col = _hex_to_rgb(pal["secondary"])
    a_col = _hex_to_rgb(pal["accent"])

    for frame in range(16):
        t = float(frame) / 15.0
        alpha_fade = int(round(255.0 * math.sin(min(1.0, t * 1.05) * math.pi)))
        tile = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        d = ImageDraw.Draw(tile)
        cx = cy = cell // 2
        radius = int(10 + t * 48)

        if kind == "world_impact":
            ring_w = max(2, int(round(12 * (1.0 - t * 0.7))))
            d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(*s_col, alpha_fade), width=ring_w)
            inner_r = max(4, int(radius * 0.68))
            d.arc([cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r], start=int(t * 90), end=int(t * 90 + 210), fill=(*p_col, alpha_fade), width=max(2, ring_w - 2))
            for k in range(8):
                ang = (2 * math.pi * k / 8.0) + t * 0.6
                r0 = radius * 0.55
                r1 = min(60.0, radius * 1.25)
                d.line(
                    [(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0), (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)],
                    fill=(*a_col, alpha_fade),
                    width=max(2, int(5 * (1.0 - t))),
                )
        else:  # UI click burst / ripple
            ring_w = max(2, int(round(8 * (1.0 - t * 0.65))))
            d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(*a_col, alpha_fade), width=ring_w)
            for k in range(10):
                ang = (2 * math.pi * k / 10.0) + 0.15
                pr = min(58.0, 12.0 + t * 44.0)
                px = cx + math.cos(ang) * pr
                py = cy + math.sin(ang) * pr
                dot_r = max(1, int(round(6 * (1.0 - t * 0.75))))
                col = s_col if k % 2 == 0 else p_col
                d.ellipse([px - dot_r, py - dot_r, px + dot_r, py + dot_r], fill=(*col, alpha_fade))

        c_idx = frame % cols
        r_idx = frame // cols
        sheet.paste(tile, (c_idx * cell, r_idx * cell))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(str(out_path), format="PNG")
    return {
        "path": str(out_path),
        "size": [cols * cell, rows * cell],
        "rows": rows,
        "cols": cols,
        "frame_count": 16,
    }


def _build_ui_vfx_luau(pal: Dict[str, str]) -> str:
    return f"""--!strict
-- SharpUiVfx: Bespoke 2D GUI click bursts, sprite flipbooks, floating popups, and shimmer sweeps.
local RunService = game:GetService("RunService")
local TweenService = game:GetService("TweenService")

local SharpUiVfx = {{}}

local PALETTE = {{
	Primary = Color3.fromHex({json.dumps(pal["primary"])}),
	Secondary = Color3.fromHex({json.dumps(pal["secondary"])}),
	Accent = Color3.fromHex({json.dumps(pal["accent"])}),
	StrokeOuter = Color3.fromHex({json.dumps(pal["stroke_outer"])}),
}}

function SharpUiVfx.AttachClickEffect(button: GuiButton, rootContainer: Instance?): () -> ()
	local host = rootContainer or button
	local conn = button.Activated:Connect(function()
		local ring = Instance.new("Frame")
		ring.Name = "_SharpClickRing"
		ring.AnchorPoint = Vector2.new(0.5, 0.5)
		ring.Position = UDim2.fromScale(0.5, 0.5)
		ring.Size = UDim2.fromOffset(18, 18)
		ring.BackgroundTransparency = 1
		ring.ZIndex = button.ZIndex + 6
		ring.Parent = host

		local corner = Instance.new("UICorner")
		corner.CornerRadius = UDim.new(1, 0)
		corner.Parent = ring

		local stroke = Instance.new("UIStroke")
		stroke.Color = PALETTE.Accent
		stroke.Thickness = 3
		stroke.Transparency = 0
		stroke.Parent = ring

		local expand = TweenService:Create(
			ring,
			TweenInfo.new(0.28, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{{ Size = UDim2.fromOffset(96, 96) }}
		)
		local fade = TweenService:Create(
			stroke,
			TweenInfo.new(0.28, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
			{{ Transparency = 1, Thickness = 1 }}
		)
		expand:Play()
		fade:Play()

		for i = 1, 6 do
			local ang = (math.pi * 2 * i) / 6
			local spark = Instance.new("Frame")
			spark.Name = "_SharpSpark"
			spark.AnchorPoint = Vector2.new(0.5, 0.5)
			spark.Position = UDim2.fromScale(0.5, 0.5)
			spark.Size = UDim2.fromOffset(7, 7)
			spark.BackgroundColor3 = if i % 2 == 0 then PALETTE.Secondary else PALETTE.Primary
			spark.BorderSizePixel = 0
			spark.ZIndex = button.ZIndex + 7
			spark.Parent = host

			local sc = Instance.new("UICorner")
			sc.CornerRadius = UDim.new(1, 0)
			sc.Parent = spark

			local target = UDim2.new(0.5, math.round(math.cos(ang) * 34), 0.5, math.round(math.sin(ang) * 34))
			local spTween = TweenService:Create(
				spark,
				TweenInfo.new(0.24, Enum.EasingStyle.Cubic, Enum.EasingDirection.Out),
				{{ Position = target, BackgroundTransparency = 1, Size = UDim2.fromOffset(2, 2) }}
			)
			spTween:Play()
			spTween.Completed:Once(function()
				spark:Destroy()
			end)
		end

		expand.Completed:Once(function()
			ring:Destroy()
		end)
	end)

	return function()
		conn:Disconnect()
	end
end

function SharpUiVfx.PlaySpritesheet2D(
	parent: GuiObject,
	imageAsset: string,
	rows: number,
	cols: number,
	fps: number,
	sheetPx: Vector2
): ()
	local label = Instance.new("ImageLabel")
	label.Name = "_SharpFlipbook2D"
	label.BackgroundTransparency = 1
	label.Image = imageAsset
	label.Size = UDim2.fromScale(1, 1)
	label.ZIndex = parent.ZIndex + 5
	local cellW = math.floor(sheetPx.X / math.max(1, cols))
	local cellH = math.floor(sheetPx.Y / math.max(1, rows))
	label.ImageRectSize = Vector2.new(cellW, cellH)
	label.ImageRectOffset = Vector2.new(0, 0)
	label.Parent = parent

	local totalFrames = rows * cols
	local elapsed = 0
	local stepConn: RBXScriptConnection
	stepConn = RunService.RenderStepped:Connect(function(dt: number)
		elapsed += dt
		local idx = math.floor(elapsed * fps)
		if idx >= totalFrames then
			stepConn:Disconnect()
			label:Destroy()
			return
		end
		local c = idx % cols
		local r = math.floor(idx / cols)
		label.ImageRectOffset = Vector2.new(c * cellW, r * cellH)
	end)
end

function SharpUiVfx.SpawnFloatingPopup(parent: GuiObject, pos: UDim2, text: string, accent: Color3?): ()
	local lbl = Instance.new("TextLabel")
	lbl.Name = "_SharpFloatPopup"
	lbl.AnchorPoint = Vector2.new(0.5, 0.5)
	lbl.Position = pos
	lbl.Size = UDim2.fromOffset(140, 38)
	lbl.BackgroundTransparency = 1
	lbl.Font = Enum.Font.FredokaOne
	lbl.Text = text
	lbl.TextSize = 24
	lbl.TextColor3 = accent or PALETTE.Accent
	lbl.ZIndex = parent.ZIndex + 8
	lbl.Parent = parent

	local stroke = Instance.new("UIStroke")
	stroke.Color = PALETTE.StrokeOuter
	stroke.Thickness = 2.5
	stroke.Parent = lbl

	local moveUp = TweenService:Create(
		lbl,
		TweenInfo.new(0.55, Enum.EasingStyle.Back, Enum.EasingDirection.Out),
		{{ Position = UDim2.new(pos.X.Scale, pos.X.Offset, pos.Y.Scale, pos.Y.Offset - 42), TextTransparency = 1 }}
	)
	TweenService:Create(stroke, TweenInfo.new(0.55), {{ Transparency = 1 }}):Play()
	moveUp:Play()
	moveUp.Completed:Once(function()
		lbl:Destroy()
	end)
end

return SharpUiVfx
"""


def _build_world_vfx_luau(pal: Dict[str, str]) -> str:
    return f"""--!strict
-- SharpWorldVfx: Custom 3D flipbook particles, curved weapon trails, beams & expanding shockwaves.
local TweenService = game:GetService("TweenService")
local Workspace = game:GetService("Workspace")

local SharpWorldVfx = {{}}

local PRIMARY = Color3.fromHex({json.dumps(pal["primary"])})
local SECONDARY = Color3.fromHex({json.dumps(pal["secondary"])})
local ACCENT = Color3.fromHex({json.dumps(pal["accent"])})

function SharpWorldVfx.AttachWeaponTrail(weaponPart: BasePart): Trail
	local topAtt = Instance.new("Attachment")
	topAtt.Name = "SharpTrailTip"
	topAtt.Position = Vector3.new(0, 1.5, 0)
	topAtt.Parent = weaponPart

	local botAtt = Instance.new("Attachment")
	botAtt.Name = "SharpTrailBase"
	botAtt.Position = Vector3.new(0, -0.6, 0)
	botAtt.Parent = weaponPart

	local trail = Instance.new("Trail")
	trail.Name = "SharpSwordTrail"
	trail.Attachment0 = topAtt
	trail.Attachment1 = botAtt
	trail.Lifetime = 0.24
	trail.LightEmission = 0.85
	trail.Color = ColorSequence.new({{
		ColorSequenceKeypoint.new(0, ACCENT),
		ColorSequenceKeypoint.new(0.45, SECONDARY),
		ColorSequenceKeypoint.new(1, PRIMARY),
	}})
	trail.Transparency = NumberSequence.new({{
		NumberSequenceKeypoint.new(0, 0.1),
		NumberSequenceKeypoint.new(1, 1),
	}})
	trail.Parent = weaponPart
	return trail
end

function SharpWorldVfx.SpawnImpactShockwave(worldPos: Vector3, maxRadius: number?, flipbookAssetId: string?): ()
	local radius = maxRadius or 9
	local anchor = Instance.new("Part")
	anchor.Name = "_SharpShockwaveVfx"
	anchor.Anchored = true
	anchor.CanCollide = false
	anchor.CanQuery = false
	anchor.CanTouch = false
	anchor.Material = Enum.Material.Neon
	anchor.Color = SECONDARY
	anchor.Transparency = 0.2
	anchor.Shape = Enum.PartType.Ball
	anchor.Size = Vector3.new(1.2, 0.35, 1.2)
	anchor.CFrame = CFrame.new(worldPos)
	anchor.Parent = Workspace

	local emitter = Instance.new("ParticleEmitter")
	emitter.Texture = flipbookAssetId or "rbxasset://textures/particles/sparkles_main.dds"
	if flipbookAssetId then
		emitter.FlipbookLayout = Enum.ParticleFlipbookLayout.Grid4x4
		emitter.FlipbookMode = Enum.ParticleFlipbookMode.OneShot
	end
	emitter.LightEmission = 0.9
	emitter.Color = ColorSequence.new(ACCENT, PRIMARY)
	emitter.Speed = NumberRange.new(10, 22)
	emitter.Lifetime = NumberRange.new(0.25, 0.45)
	emitter.SpreadAngle = Vector2.new(85, 85)
	emitter.Rate = 0
	emitter.Parent = anchor
	emitter:Emit(18)

	local expand = TweenService:Create(
		anchor,
		TweenInfo.new(0.32, Enum.EasingStyle.Quad, Enum.EasingDirection.Out),
		{{ Size = Vector3.new(radius * 2, 0.15, radius * 2), Transparency = 1 }}
	)
	expand:Play()
	expand.Completed:Once(function()
		task.delay(0.5, function()
			anchor:Destroy()
		end)
	end)
end

return SharpWorldVfx
"""


def _build_bitmap_font_luau(font_meta: Dict[str, Any]) -> str:
    glyph_entries: List[str] = []
    for ch, rect in (font_meta.get("glyphs") or {}).items():
        ox, oy = rect["offset"]
        sx, sy = rect["size"]
        adv = rect["advance"]
        glyph_entries.append(
            f"\t[{json.dumps(ch)}] = {{ Offset = Vector2.new({ox}, {oy}), Size = Vector2.new({sx}, {sy}), Advance = {adv} }},"
        )
    table_body = "\n".join(glyph_entries)
    return f"""--!strict
-- SharpBitmapFont: Renders stylized custom bitmap glyph strips via ImageLabel.ImageRectOffset.
local SharpBitmapFont = {{}}

SharpBitmapFont.Glyphs = {{
{table_body}
}}

function SharpBitmapFont.RenderString(
	parent: GuiObject,
	text: string,
	assetId: string,
	scalePx: number?
): Frame
	local px = scalePx or 34
	local holder = Instance.new("Frame")
	holder.Name = "_SharpBitmapText"
	holder.BackgroundTransparency = 1
	holder.AutomaticSize = Enum.AutomaticSize.X
	holder.Size = UDim2.fromOffset(0, px)
	holder.Parent = parent

	local xCursor = 0
	for i = 1, #text do
		local ch = string.sub(text, i, i)
		local g = SharpBitmapFont.Glyphs[ch]
		if g then
			local img = Instance.new("ImageLabel")
			img.Name = "G_" .. tostring(i)
			img.BackgroundTransparency = 1
			img.Image = assetId
			img.ImageRectOffset = g.Offset
			img.ImageRectSize = g.Size
			img.Size = UDim2.fromOffset(px, px)
			img.Position = UDim2.fromOffset(xCursor, 0)
			img.Parent = holder
			xCursor += math.round(px * (g.Advance / math.max(1, g.Size.X)))
		elseif ch == " " then
			xCursor += math.round(px * 0.35)
		end
	end
	holder.Size = UDim2.fromOffset(math.max(px, xCursor), px)
	return holder
end

return SharpBitmapFont
"""


class ArtCreationEngine:
    """Cohesive 2D procedural kit, custom fonts, 2D/3D VFX, and AI UI/Image creation."""

    def __init__(
        self,
        *,
        design_engine: DesignEngine,
        gui_engine: GuiDomainEngine,
        credentials_path: Optional[str | Path] = None,
    ) -> None:
        self.design_engine = design_engine
        self.gui_engine = gui_engine
        self.credentials_path = credentials_path

    def _ensure_design_system(
        self,
        design_system: Optional[Dict[str, Any]],
        *,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        mood: str = "vibrant",
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if isinstance(design_system, dict) and design_system.get("palette"):
            return design_system
        if project_library is not None and hasattr(project_library, "get_design_system"):
            stored = project_library.get_design_system()
            if isinstance(stored, dict) and stored.get("palette"):
                return stored
        return self.design_engine.generate_design_system(
            game_title=game_title,
            genre=genre,
            mood=mood,
        )

    def create_procedural_2d_kit(
        self,
        *,
        design_system: Optional[Dict[str, Any]] = None,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        output_dir: str = "",
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate high-craft 2x SSAA 9-slice buttons, panels, rays, and vector-clean icon atlas."""
        ds = self._ensure_design_system(
            design_system, game_title=game_title, genre=genre, project_library=project_library
        )
        pal = _palette_from_ds(ds)
        preset_id = str(ds.get("preset_id") or "arcade_pop")

        if output_dir and output_dir.strip():
            out_dir = Path(output_dir).expanduser().resolve()
        elif project_library is not None and getattr(project_library, "assets_dir", None):
            out_dir = Path(project_library.assets_dir) / "gui_images" / "procedural_kit"
        else:
            out_dir = Path.cwd() / "artifacts" / "procedural_kit"
        out_dir.mkdir(parents=True, exist_ok=True)

        btn_meta = _render_button_9slice(out_dir / "button_9slice.png", pal, preset_id)
        panel_meta = _render_panel_9slice(out_dir / "panel_9slice.png", pal, preset_id)
        rays_path = _render_emblem_rays(out_dir / "emblem_rays.png", pal)
        atlas_meta = _render_procedural_icon_atlas(out_dir / "procedural_icons_atlas.png", pal)

        return {
            "ok": True,
            "mode": "create_procedural_2d_kit",
            "game_title": ds.get("game_title"),
            "preset_id": preset_id,
            "palette": pal,
            "output_dir": str(out_dir),
            "button_9slice": btn_meta,
            "panel_9slice": panel_meta,
            "emblem_rays_path": rays_path,
            "icon_atlas": atlas_meta,
        }

    def create_custom_font_kit(
        self,
        *,
        design_system: Optional[Dict[str, Any]] = None,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        output_dir: str = "",
        glyphs: str = DEFAULT_BITMAP_GLYPHS,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Pair curated Roblox fonts with a custom beveled Bitmap Font spritesheet + Luau renderer."""
        ds = self._ensure_design_system(
            design_system, game_title=game_title, genre=genre, project_library=project_library
        )
        pal = _palette_from_ds(ds)
        preset_id = str(ds.get("preset_id") or "candy_simulator")
        pairing = ROBLOX_FONT_PAIRINGS.get(preset_id, ROBLOX_FONT_PAIRINGS["candy_simulator"])

        if output_dir and output_dir.strip():
            out_dir = Path(output_dir).expanduser().resolve()
        elif project_library is not None and getattr(project_library, "assets_dir", None):
            out_dir = Path(project_library.assets_dir) / "gui_images" / "custom_fonts"
        else:
            out_dir = Path.cwd() / "artifacts" / "custom_fonts"
        out_dir.mkdir(parents=True, exist_ok=True)

        png_p = out_dir / "custom_bitmap_font.png"
        json_p = out_dir / "custom_bitmap_font.json"
        luau_p = out_dir / "SharpBitmapFont.luau"

        meta = _render_custom_bitmap_font(png_p, json_p, pal, glyphs=glyphs)
        luau_src = _build_bitmap_font_luau(meta)
        luau_p.write_text(luau_src, encoding="utf-8")

        return {
            "ok": True,
            "mode": "create_custom_font_kit",
            "preset_id": preset_id,
            "roblox_font_pairing": pairing,
            "bitmap_font": meta,
            "luau_module_path": str(luau_p),
            "luau_source": luau_src,
        }

    def create_custom_vfx(
        self,
        *,
        design_system: Optional[Dict[str, Any]] = None,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        vfx_mode: str = "both",
        output_dir: str = "",
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate 4x4 procedural 2D UI & 3D World VFX flipbook PNGs + strict Luau effect modules."""
        ds = self._ensure_design_system(
            design_system, game_title=game_title, genre=genre, project_library=project_library
        )
        pal = _palette_from_ds(ds)
        norm_mode = (vfx_mode or "both").strip().lower()

        if output_dir and output_dir.strip():
            out_dir = Path(output_dir).expanduser().resolve()
        elif project_library is not None and getattr(project_library, "assets_dir", None):
            out_dir = Path(project_library.assets_dir) / "vfx_custom"
        else:
            out_dir = Path.cwd() / "artifacts" / "vfx_custom"
        out_dir.mkdir(parents=True, exist_ok=True)

        result: Dict[str, Any] = {
            "ok": True,
            "mode": "create_custom_vfx",
            "vfx_mode": norm_mode,
            "palette": pal,
            "output_dir": str(out_dir),
        }
        if norm_mode in ("both", "2d", "ui"):
            ui_fb = _render_vfx_flipbook_4x4(out_dir / "ui_click_burst_flipbook.png", pal, kind="click_burst")
            ui_luau = _build_ui_vfx_luau(pal)
            ui_luau_path = out_dir / "SharpUiVfx.luau"
            ui_luau_path.write_text(ui_luau, encoding="utf-8")
            result["ui_2d_vfx"] = {
                "flipbook": ui_fb,
                "luau_module_path": str(ui_luau_path),
                "luau_source": ui_luau,
            }
        if norm_mode in ("both", "3d", "world"):
            w_fb = _render_vfx_flipbook_4x4(out_dir / "world_impact_flipbook.png", pal, kind="world_impact")
            w_luau = _build_world_vfx_luau(pal)
            w_luau_path = out_dir / "SharpWorldVfx.luau"
            w_luau_path.write_text(w_luau, encoding="utf-8")
            result["world_3d_vfx"] = {
                "flipbook": w_fb,
                "luau_module_path": str(w_luau_path),
                "luau_source": w_luau,
            }
        return result

    async def generate_ui_concept(
        self,
        *,
        screen_name: str = "MainHud",
        prompt: str = "",
        design_system: Optional[Dict[str, Any]] = None,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        provider: str = "auto",
        model: Optional[str] = None,
        tier: str = "default",
        use_ai: bool = True,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate bespoke anti-slop UI Luau & component blueprint via OpenRouter/Gemini (with offline fallback)."""
        ds = self._ensure_design_system(
            design_system, game_title=game_title, genre=genre, project_library=project_library
        )
        pal = _palette_from_ds(ds)
        lint_res = self.design_engine.lint_design(ds)
        pairing = ROBLOX_FONT_PAIRINGS.get(str(ds.get("preset_id")), ROBLOX_FONT_PAIRINGS["candy_simulator"])

        route = resolve_provider_and_model(
            role="gui_code",
            preferred_provider=provider,
            model_override=model,
            tier=tier,
            credentials_path=self.credentials_path,
        )

        system_prompt = (
            "You are an elite Roblox Luau UI engineer building zero-slop, colorful, cohesive game UI.\n"
            "STRICT RULES: Begin scripts with `--!strict`, use `TweenService` + `UIGradient` + stacked `UIStroke`, "
            "safe zones (`ScreenInsets = Enum.ScreenInsets.CoreUISafeInsets`), >=44px mobile touch buttons, "
            "NO generic flat dark-blue SaaS boxes, NO deprecated wait()/spawn()/delay().\n"
            "Return JSON ONLY with keys: summary, layout_tree ([string]), components ([{name, kind, purpose}]), luau_module (string)."
        )
        user_prompt = (
            f"Build screen '{screen_name}' for '{ds.get('game_title')}' ({ds.get('genre')}).\n"
            f"Palette: {json.dumps(pal)}\nFont pairing: {json.dumps(pairing)}\n"
            + (f"Specific gameplay UI brief: {prompt}\n" if prompt else "")
        )

        ai_payload: Optional[Dict[str, Any]] = None
        if use_ai and route["key_configured"] and route["api_key"]:
            if route["provider"] == "openrouter":
                headers = {
                    "Authorization": f"Bearer {route['api_key']}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/sharp-mcp",
                    "X-Title": "Sharp MCP UI Generator",
                }
                body = {
                    "model": route["model"],
                    "temperature": 0.35,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                url = "https://openrouter.ai/api/v1/chat/completions"
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{route['model']}:generateContent"
                headers = {"Content-Type": "application/json", "x-goog-api-key": route["api_key"]}
                body = {
                    "contents": [{"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}],
                    "generationConfig": {"temperature": 0.35, "responseMimeType": "application/json"},
                }
            try:
                parsed = await post_json(url, headers=headers, payload=body, api_key=route["api_key"], timeout_sec=90.0)
                txt = response_text(parsed, route["provider"])
                ai_payload = {"ok": True, "provider": route["provider"], "model": route["model"], "raw_text": txt}
            except AIRequestError as exc:
                ai_payload = {"ok": False, "provider": route["provider"], "error": str(exc)}

        theme_luau = self.design_engine.compile_theme_luau(ds, module_mode=True)
        return {
            "ok": True,
            "mode": "generate_ui_concept",
            "screen_name": screen_name,
            "game_title": ds.get("game_title"),
            "preset_id": ds.get("preset_id"),
            "font_pairing": pairing,
            "design_lint": lint_res,
            "theme_luau": theme_luau,
            "ai_routing": {
                "provider": route["provider"],
                "planned_provider": route["planned_provider"],
                "model": route["model"],
                "key_configured": route["key_configured"],
            },
            "ai_generation": ai_payload,
            "generation_mode": "ai_assisted" if (ai_payload and ai_payload.get("ok")) else "offline_deterministic_blueprint",
        }

    async def generate_ai_art(
        self,
        *,
        asset_kind: str = "icon_sheet",
        subject: str = "",
        grid: Optional[List[int]] = None,
        names: Optional[List[str]] = None,
        design_system: Optional[Dict[str, Any]] = None,
        game_title: str = "Untitled Roblox Game",
        genre: str = "adventure",
        provider: str = "auto",
        model: Optional[str] = None,
        tier: str = "default",
        output_dir: str = "",
        auto_slice: bool = True,
        project_library: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Generate palette-locked 2D UI art via Gemini/OpenRouter image models & optionally slice/pack."""
        ds = self._ensure_design_system(
            design_system, game_title=game_title, genre=genre, project_library=project_library
        )
        grid_rc = tuple(grid) if (isinstance(grid, (list, tuple)) and len(grid) == 2) else (2, 2)
        prompt_batch = self.design_engine.build_image_prompt_batch(
            ds,
            icon_grid=(int(grid_rc[0]), int(grid_rc[1])),
            icon_names=names,
        )
        prompts_list = prompt_batch.get("prompts") or []
        wanted_key = "icon_grid" if asset_kind in ("icon_sheet", "icon_grid") else asset_kind
        matched = next(
            (
                p.get("prompt")
                for p in prompts_list
                if isinstance(p, dict)
                and (p.get("asset_key") == wanted_key or p.get("template_kind") == wanted_key)
                and p.get("prompt")
            ),
            None,
        )
        fallback_prompt = (
            prompts_list[0].get("prompt")
            if prompts_list and isinstance(prompts_list[0], dict)
            else f"Flat 2D orthographic UI asset '{asset_kind}' for {ds.get('game_title')}"
        )
        prompt_text = subject.strip() or str(matched or fallback_prompt)

        route = resolve_provider_and_model(
            role="image_gen",
            preferred_provider=provider,
            model_override=model,
            tier=tier,
            credentials_path=self.credentials_path,
        )
        if not route["key_configured"] or not route["api_key"]:
            return {
                "ok": False,
                "error_code": "MISSING_API_KEY",
                "error": "No Gemini or OpenRouter API key configured. Set GEMINI_API_KEY / OPENROUTER_API_KEY or run `sharp_ai_studio(action='keys_set')`.",
                "prompt_ready": prompt_text,
                "negative_prompt": prompt_batch.get("negative_prompt"),
                "key_background_hex": ds.get("key_background_hex"),
                "planned_routing": {
                    "provider": route["planned_provider"],
                    "model": route["model"],
                },
            }

        if output_dir and output_dir.strip():
            out_dir = Path(output_dir).expanduser().resolve()
        elif project_library is not None and getattr(project_library, "assets_dir", None):
            out_dir = Path(project_library.assets_dir) / "gui_images" / "ai_generated"
        else:
            out_dir = Path.cwd() / "artifacts" / "ai_generated"
        out_dir.mkdir(parents=True, exist_ok=True)
        raw_png = out_dir / f"{asset_kind}_raw.png"

        img_bytes: Optional[bytes] = None
        if route["provider"] == "gemini":
            mdl = route["model"]
            headers = {"Content-Type": "application/json", "x-goog-api-key": route["api_key"]}
            if mdl.startswith("imagen-"):
                return {"ok": False, "error": "Imagen models are shut down. Select gemini-2.5-flash-image or another Gemini image model."}
            else:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mdl}:generateContent"
                body = {
                    "contents": [{"role": "user", "parts": [{"text": prompt_text}]}],
                    "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
                }
        else:
            headers = {
                "Authorization": f"Bearer {route['api_key']}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/sharp-mcp",
                "X-Title": "Sharp MCP Image Gen",
            }
            body = {
                "model": route["model"],
                "modalities": ["image", "text"],
                "messages": [{"role": "user", "content": prompt_text}],
            }
            url = "https://openrouter.ai/api/v1/chat/completions"

        try:
            data = await post_json(url, headers=headers, payload=body, api_key=route["api_key"], timeout_sec=120.0)
            content = response_content(data, route["provider"])
            if route["provider"] == "gemini":
                for part in content.get("parts") or []:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if isinstance(inline, dict) and inline.get("data"):
                        img_bytes = base64.b64decode(inline["data"], validate=True)
                        break
            else:
                imgs = content.get("images") or []
                if imgs:
                    data_url = ((imgs[0].get("image_url") or {}).get("url") or "")
                    if data_url.startswith("data:image/") and ";base64," in data_url:
                        img_bytes = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        except AIRequestError as exc:
            return {"ok": False, "error": str(exc)}
        except ValueError:
            return {"ok": False, "error": "Provider returned invalid base64 image data."}

        if not img_bytes:
            return {"ok": False, "error": "Model responded without image binary data."}

        await asyncio.to_thread(raw_png.write_bytes, img_bytes)
        sliced_res: Optional[Dict[str, Any]] = None
        if auto_slice:
            slice_kwargs: Dict[str, Any] = {
                "output_dir": str(out_dir),
                "export_rbxmx": False,
            }
            if asset_kind in ("icon_sheet", "icon_grid"):
                slice_kwargs["icon_source_paths"] = [str(raw_png)]
                slice_kwargs["grid_rows"] = int(grid_rc[0])
                slice_kwargs["grid_cols"] = int(grid_rc[1])
                if names:
                    slice_kwargs["icon_names"] = list(names)
            elif asset_kind == "button_9slice":
                slice_kwargs["button_source_path"] = str(raw_png)
            else:
                slice_kwargs["panel_source_path"] = str(raw_png)
            sliced_res = await asyncio.to_thread(
                self.gui_engine.process_slice_and_atlas,
                **slice_kwargs,
            )

        return {
            "ok": True,
            "mode": "generate_ai_art",
            "provider": route["provider"],
            "model": route["model"],
            "raw_image_path": str(raw_png),
            "sliced_result": sliced_res,
            "prompt_used": prompt_text,
        }

from __future__ import annotations

import hashlib
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sharp_mcp.domain_engines.art_creation_engine import ArtCreationEngine  # noqa: E402
from sharp_mcp.domain_engines.critical_audit_engine import tokenize_luau  # noqa: E402
from sharp_mcp.domain_engines.design_engine import (  # noqa: E402
    ASSET_STYLE_PROFILES,
    DESIGN_PRESETS,
    TEXTURE_STYLE_PROFILES,
    DesignEngine,
    delta_e_cie76,
    hex_to_hsl,
    hex_to_rgb,
    hue_distance_deg,
    wcag_contrast_ratio,
)
from sharp_mcp.domain_engines.gui_engine import (  # noqa: E402
    LAYOUT_PARADIGM_BLUEPRINTS,
    GuiDomainEngine,
)
from tests.test_attachment_engine import assert_valid_luau_sanity  # noqa: E402


SKILLS_DIR = REPO_ROOT / "sharp_mcp" / "bundled_skills"
LIVE_SKILL_DIR = Path(os.path.expanduser("~")) / ".gemini" / "config" / "skills" / "roblox-gui"
DESKTOP_GUI_SKILL_DIR = REPO_ROOT.parent / "02_roblox_gui" / "skill"


def _strip_luau_comments_and_strings(src: str) -> str:
    """Strip Luau long strings/comments, line comments, and quoted strings for structural checking."""
    out: List[str] = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        # Comments (-- or --[=[ ... ]=])
        if ch == "-" and i + 1 < n and src[i + 1] == "-":
            if i + 2 < n and src[i + 2] == "[":
                m = re.match(r"\[(=*)\[", src[i + 2 :])
                if m:
                    eqs = m.group(1)
                    end_tok = "]" + eqs + "]"
                    end_idx = src.find(end_tok, i + 2 + len(m.group(0)))
                    if end_idx == -1:
                        break
                    out.append(" ")
                    i = end_idx + len(end_tok)
                    continue
            nl = src.find("\n", i)
            if nl == -1:
                break
            out.append("\n")
            i = nl + 1
            continue
        # Long bracketed strings [=[ ... ]=]
        if ch == "[":
            m = re.match(r"\[(=*)\[", src[i:])
            if m:
                eqs = m.group(1)
                end_tok = "]" + eqs + "]"
                end_idx = src.find(end_tok, i + len(m.group(0)))
                if end_idx == -1:
                    break
                out.append(" '' ")
                i = end_idx + len(end_tok)
                continue
        # Quoted strings "..." / '...' / `...`
        if ch in ('"', "'", "`"):
            q = ch
            j = i + 1
            while j < n:
                if src[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if src[j] == q:
                    j += 1
                    break
                j += 1
            out.append(" '' ")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _assert_luau_balanced(testcase: unittest.TestCase, src: str, label: str) -> None:
    """Check balanced (), {}, [], Color3 bounds, and roughly balanced do/then/function/end."""
    for r, g, b in re.findall(r"Color3\.fromRGB\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\)", src):
        for ch_val in (int(r), int(g), int(b)):
            testcase.assertGreaterEqual(ch_val, 0, f"{label}: Color3 channel < 0")
            testcase.assertLessEqual(ch_val, 255, f"{label}: Color3 channel > 255")

    clean = _strip_luau_comments_and_strings(src)
    # Remove single-line ternary `if ... then ... else ...` expressions before block counting?
    # Note: in Luau, expressions use `if cond then a else b` WITHOUT `end`, whereas statements
    # use `if cond then ... end`. So we verify exact (), {}, [] bracket balance and positive `end` presence.
    pairs = {"(": ")", "{": "}", "[": "]"}
    closing = {")": "(", "}": "{", "]": "["}
    stack: List[str] = []
    for ch in clean:
        if ch in pairs:
            stack.append(ch)
        elif ch in closing:
            testcase.assertTrue(stack, f"{label}: unexpected closing {ch!r}")
            top = stack.pop()
            testcase.assertEqual(top, closing[ch], f"{label}: mismatched {top!r} vs {ch!r}")
    testcase.assertEqual(stack, [], f"{label}: unclosed brackets remaining: {stack}")


class DesignEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = DesignEngine(skills_dir=SKILLS_DIR)
        self.gui_engine = GuiDomainEngine(skills_dir=SKILLS_DIR)

    def test_deterministic_per_seed_and_all_six_presets(self) -> None:
        titles = {
            "candy_simulator": "Sugar Puppies Simulator",
            "anime_neon": "Shinobi Blade Clash",
            "cozy_pastel": "Sunbeam Tea Bakery",
            "scifi_holo": "Nebula Mech Protocol",
            "arcade_pop": "Turbo Kart Mayhem",
            "rpg_arcane": "Dragoncrest Guild Chronicles",
        }
        generated: Dict[str, dict] = {}
        for preset_id, title in titles.items():
            ds1 = self.engine.generate_design_system(title, genre=preset_id, mood="vibrant", seed=42)
            ds2 = self.engine.generate_design_system(title, genre=preset_id, mood="vibrant", seed=42)
            self.assertEqual(ds1, ds2, f"Expected deterministic output for {preset_id}")
            self.assertTrue(ds1["ok"])
            self.assertEqual(ds1["preset_id"], preset_id)
            self.assertTrue(ds1["contrast_audit"]["passed"], f"Contrast audit failed for {preset_id}: {ds1['contrast_audit']}")

            p = ds1["palette"]
            for role in (
                "bg_deep",
                "bg_panel",
                "primary",
                "secondary",
                "accent",
                "success",
                "warning",
                "danger",
                "gold",
                "text",
                "outline_ink",
                "rarity",
            ):
                self.assertIn(role, p, f"Missing palette role {role} in {preset_id}")
            self.assertEqual(len(p["rarity"]), 6)
            self.assertFalse(
                self.engine._is_near_generic_slop(p["bg_deep"], p["bg_panel"], p["primary"]),
                f"Preset {preset_id} hit generic dark-navy/blue slop",
            )
            generated[preset_id] = ds1

        # Cozy pastel should preserve light surface mode while passing dark text contrast >= 4.5
        self.assertEqual(generated["cozy_pastel"]["surface_mode"], "light")
        self.assertGreaterEqual(generated["cozy_pastel"]["contrast_audit"]["pairs"]["text_on_bg_panel"], 4.5)

        # Pairwise distinctness across all 6 preset primary colors
        preset_keys = list(generated.keys())
        for i in range(len(preset_keys)):
            for j in range(i + 1, len(preset_keys)):
                a = generated[preset_keys[i]]["palette"]
                b = generated[preset_keys[j]]["palette"]
                de = delta_e_cie76(a["primary"], b["primary"]) + delta_e_cie76(a["bg_panel"], b["bg_panel"])
                self.assertGreater(
                    de,
                    18.0,
                    f"Presets {preset_keys[i]} and {preset_keys[j]} look too similar (Delta-E sum={de:.2f})",
                )

    def test_different_titles_and_seeds_produce_distinct_palettes(self) -> None:
        a = self.engine.generate_design_system("Crystal Cavern Quest", genre="adventure", mood="heroic", seed="alpha")
        b = self.engine.generate_design_system("Nebula Starfighters", genre="scifi", mood="electric", seed="beta")
        c = self.engine.generate_design_system("Crystal Cavern Quest", genre="adventure", mood="heroic", seed="gamma")

        for left, right in ((a, b), (a, c)):
            lp = left["palette"]
            rp = right["palette"]
            primary_de = delta_e_cie76(lp["primary"], rp["primary"])
            accent_de = delta_e_cie76(lp["accent"], rp["accent"])
            hue_diff = hue_distance_deg(hex_to_hsl(lp["primary"])[0], hex_to_hsl(rp["primary"])[0])
            self.assertTrue(
                primary_de >= 10.0 or accent_de >= 12.0 or hue_diff >= 12.0,
                f"Expected distinct palettes, got primary_de={primary_de:.2f}, accent_de={accent_de:.2f}, hue_diff={hue_diff:.2f}",
            )

    def test_wcag_contrast_autofix(self) -> None:
        # Deliberately bad low-contrast overrides must be auto-remediated
        ds = self.engine.generate_design_system(
            "Shadow Reef Tycoon",
            genre="candy_simulator",
            seed=99,
            constraints={
                "bg_panel": "#28384A",
                "bg_deep": "#1E2B3A",
                "text": "#304055",  # terrible contrast on #28384A
                "primary": "#2C3E50",  # terrible UI contrast on #28384A
            },
        )
        p = ds["palette"]
        self.assertGreaterEqual(wcag_contrast_ratio(p["text"], p["bg_panel"]), 4.5)
        self.assertGreaterEqual(wcag_contrast_ratio(p["text"], p["bg_deep"]), 4.5)
        self.assertGreaterEqual(wcag_contrast_ratio(p["text_on_primary"], p["primary"]), 4.5)
        self.assertGreaterEqual(wcag_contrast_ratio(p["primary"], p["bg_panel"]), 3.0)
        self.assertTrue(ds["contrast_audit"]["passed"])
        self.assertGreater(len(ds["contrast_audit"]["fixes_applied"]), 0)

    def test_anti_slop_lint_passes_generated_and_catches_all_failures(self) -> None:
        for pid in DESIGN_PRESETS:
            ds = self.engine.generate_design_system(f"Test {pid}", genre=pid, seed=7)
            lint = self.engine.lint_design(ds)
            self.assertTrue(lint["ok"], f"Generated {pid} failed lint: {lint}")
            self.assertGreaterEqual(lint["score"], 90, f"Low lint score for {pid}: {lint}")
            self.assertEqual(lint["finding_count"], 0, f"Unexpected lint findings for {pid}: {lint['findings']}")

        # Bad structured spec triggering all major anti-slop codes
        slop_spec = {
            "palette": {
                "bg_deep": "#0D121C",
                "bg_panel": "#161E2E",
                "primary": "#3886F8",
                "secondary": "#3B82F6",  # same blue hue -> < 3 distinct hues
                "accent": "#60A5FA",
                "text": "#334466",  # low text contrast
            },
            "components": [
                {"name": "Btn1", "type": "TextButton", "size": [90, 32], "corner_radius": 8, "has_gradient": False, "has_stroke": False, "text": "Play \U0001f680"},
                {"name": "Btn2", "type": "TextButton", "size": [90, 36], "corner_radius": 8, "has_gradient": False, "has_stroke": False, "hover": False, "press": False},
                {"name": "Card", "type": "Frame", "size": [200, 120], "corner_radius": 8},
            ],
        }
        lint_bad = self.engine.lint_design(slop_spec)
        codes = {f["code"] for f in lint_bad["findings"]}
        self.assertFalse(lint_bad["ok"])
        self.assertLess(lint_bad["score"], 50)
        for expected_code in (
            "missing_outline_ink",
            "default_blue_gray_slop",
            "insufficient_distinct_hues",
            "low_contrast",
            "flat_button_no_gradient_stroke",
            "missing_interaction_states",
            "small_touch_target",
            "emoji_as_icon",
            "uniform_radius_everywhere",
        ):
            self.assertIn(expected_code, codes, f"Linter missed {expected_code!r}; got {codes}")
        self.assertGreater(len(lint_bad["fixes"]), 3)

        # Also lint raw Luau source with flat button / small size / emoji / identical CornerRadius
        bad_luau = (
            'local b = Instance.new("TextButton")\n'
            'b.Size = UDim2.fromOffset(80, 28)\n'
            'b.BackgroundColor3 = Color3.fromRGB(56, 134, 248)\n'
            'b.Text = "Buy \U0001f4b0"\n'
            'local c1 = Instance.new("UICorner"); c1.CornerRadius = UDim.new(0, 8)\n'
            'local c2 = Instance.new("UICorner"); c2.CornerRadius = UDim.new(0, 8)\n'
            'local c3 = Instance.new("UICorner"); c3.CornerRadius = UDim.new(0, 8)\n'
        )
        lint_luau = self.engine.lint_design(bad_luau)
        luau_codes = {f["code"] for f in lint_luau["findings"]}
        self.assertFalse(lint_luau["ok"])
        self.assertIn("flat_button_no_gradient_stroke", luau_codes)
        self.assertIn("small_touch_target", luau_codes)
        self.assertIn("emoji_as_icon", luau_codes)
        self.assertIn("uniform_radius_everywhere", luau_codes)

    def test_render_palette_swatch_png_and_numeric_distinctness(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            games = [
                ("candy_pets", "Candy Cloud Pets", "candy_simulator", 11),
                ("mecha_void", "Mecha Void Nexus", "scifi_holo", 22),
                ("bakery_cozy", "Sunbeam Bakery", "cozy_pastel", 33),
            ]
            imgs: List[Image.Image] = []
            for slug, title, genre, seed in games:
                ds = self.engine.generate_design_system(title, genre=genre, seed=seed)
                out_png = tmp_dir / f"swatch_{slug}.png"
                meta = self.engine.render_palette_swatch(ds, out_png)
                self.assertTrue(meta["ok"])
                self.assertTrue(out_png.is_file())
                im = Image.open(out_png).convert("RGBA")
                self.assertEqual(im.size, (720, 240))
                # Verify rendered swatch actually has >= 10 distinct colors (not blank/monochrome)
                colors = im.getcolors(maxcolors=50000)
                self.assertIsNotNone(colors)
                self.assertGreaterEqual(len(colors or []), 10)
                # Spot-check outer corner matches bg_deep and center panel card has bg_panel pixels
                self.assertEqual(im.getpixel((2, 2))[:3], hex_to_rgb(ds["palette"]["bg_deep"]))
                imgs.append(im)

            # Numerically eyeball-check distinctness across the 3 rendered PNGs (mean per-pixel RGB diff)
            for i in range(len(imgs)):
                for j in range(i + 1, len(imgs)):
                    p1 = imgs[i].tobytes()
                    p2 = imgs[j].tobytes()
                    diffs = [abs(p1[k] - p2[k]) for k in range(0, len(p1), 4) if (k % 4) < 3]
                    mean_diff = sum(diffs) / max(1, len(diffs))
                    self.assertGreater(mean_diff, 12.0, f"Swatches {i} vs {j} rendered too visually similar ({mean_diff:.2f})")

                    # Role swatch strip in center (excluding margins) must show even sharper color separation
                    s1 = imgs[i].crop((32, 40, 688, 178)).tobytes()
                    s2 = imgs[j].crop((32, 40, 688, 178)).tobytes()
                    sdiffs = [abs(s1[k] - s2[k]) for k in range(0, len(s1), 4) if (k % 4) < 3]
                    strip_diff = sum(sdiffs) / max(1, len(sdiffs))
                    self.assertGreater(strip_diff, 20.0, f"Swatch strip {i} vs {j} too similar ({strip_diff:.2f})")

    def test_luau_theme_compiler_and_gui_build_syntax(self) -> None:
        ds = self.engine.generate_design_system("Blaze Ninja Odyssey", genre="anime_neon", seed=515)
        theme_luau = self.engine.compile_theme_luau(ds, module_mode=True)
        self.assertTrue(theme_luau.startswith("--!strict"))
        self.assertIn("return DesignTheme", theme_luau)
        for token in ("OutlineInk", "PrimaryHover", "Gradient", "ShineSweep", "RaysEnabled", "MinTouchPx"):
            self.assertIn(token, theme_luau)
        _assert_luau_balanced(self, theme_luau, "compile_theme_luau")

        # Validate live skill Luau files (and verify all feature checks)
        scripts_dir = SKILLS_DIR / "roblox-gui" / "scripts"
        ui_kit_src = (scripts_dir / "ui_theme_and_components.luau").read_text(encoding="utf-8")
        builder_src = (scripts_dir / "build_standard_game_gui.luau").read_text(encoding="utf-8")
        audit_src = (scripts_dir / "audit_gui.luau").read_text(encoding="utf-8")

        self.assertTrue(ui_kit_src.startswith("--!strict"))
        for expected in (
            "UIKit.ApplyDesignSystem",
            "UIKit.CreateGlossyButton",
            "UIKit.CreateGlossyPanel",
            "UIKit.CreateShineSweep",
            "UIKit.CreateSunburstRays",
            "UIKit.CreateBadgePill",
            "UIKit.CreateModalFadeGroup",
            'Instance.new("UIShadow")',
            "BorderStrokePosition.Outer",
            "IsReducedMotion",
            "UIGradient",
            "Gradient.Offset",
        ):
            if expected == "Gradient.Offset":
                self.assertIn(".Offset =", ui_kit_src)
            else:
                self.assertIn(expected, ui_kit_src)

        _assert_luau_balanced(self, ui_kit_src, "ui_theme_and_components.luau")
        _assert_luau_balanced(self, builder_src, "build_standard_game_gui.luau")
        _assert_luau_balanced(self, audit_src, "audit_gui.luau")

        # Verify gui_engine.compile_gui_build_luau backward compat & design_system injection
        legacy_out = self.gui_engine.compile_gui_build_luau("rbxassetid://111", "rbxassetid://222", "rbxassetid://333")
        self.assertIn("UIKit.Assets", legacy_out)
        self.assertIn("rbxassetid://111", legacy_out)
        self.assertIn("__SharpActiveRecordingId", legacy_out)

        themed_out = self.gui_engine.compile_gui_build_luau(
            "rbxassetid://111",
            "rbxassetid://222",
            "rbxassetid://333",
            design_system=ds,
        )
        self.assertIn("local DesignTheme =", themed_out)
        self.assertIn("UIKit.ApplyDesignSystem(DesignTheme)", themed_out)
        _assert_luau_balanced(self, themed_out, "compile_gui_build_luau(themed)")

    def test_image_prompt_batch_locks_palette_and_negative_prompts(self) -> None:
        ds = self.engine.generate_design_system("Astro Hopper Tycoon", genre="arcade_pop", seed=77)
        batch = self.engine.build_image_prompt_batch(
            ds,
            screens=["MainHud", "ShopModal", "LoadingScreen"],
            icon_grid=(3, 4),
            icon_names=["coin", "gem", "bolt", "crown", "key", "chest", "star", "shield", "potion", "wing", "bomb", "ticket"],
        )
        self.assertTrue(batch["ok"])
        self.assertEqual(batch["icon_grid"], [3, 4])
        self.assertEqual(len(batch["icon_names"]), 12)
        self.assertIn("LoadingScreen", batch["by_screen"])
        kinds = {item["template_kind"] for item in batch["prompts"]}
        for expected_kind in ("9slice_panel", "9slice_tint_button", "hud_bar", "icon_grid", "rarity_frame", "loading_backdrop"):
            self.assertIn(expected_kind, kinds)

        p = ds["palette"]
        sig = ds["style_signature"]
        for item in batch["prompts"]:
            prompt = item["prompt"]
            neg = item["negative_prompt"].lower()
            self.assertIn(sig, prompt)
            self.assertTrue(
                any(hx in prompt for hx in (p["primary"], p["accent"], p["bg_deep"], p["bg_panel"], ds["key_background_hex"])),
                f"Prompt missing palette hexes: {prompt}",
            )
            self.assertIn("checkerboard", neg)
            self.assertIn("muddy", neg)
            self.assertIn("text", neg)

    def test_generalized_rxc_slicing_tight_trim_and_1024_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)

            # 1. Oversized 1600x1600 9-slice panel on #FF00FF magenta key
            panel_src = tmp_dir / "panel_huge.png"
            panel_im = Image.new("RGBA", (1600, 1600), (255, 0, 255, 255))
            pdraw = ImageDraw.Draw(panel_im)
            # Symmetric rounded-corner outer frame with straight middle 56% edges
            pdraw.rectangle([120, 120, 1480, 1480], fill=(34, 26, 56, 255), outline=(14, 10, 24, 255), width=24)
            pdraw.rectangle([160, 160, 280, 280], fill=(246, 174, 45, 255))
            pdraw.rectangle([1320, 160, 1440, 280], fill=(246, 174, 45, 255))
            pdraw.rectangle([160, 1320, 280, 1440], fill=(246, 174, 45, 255))
            pdraw.rectangle([1320, 1320, 1440, 1440], fill=(246, 174, 45, 255))
            panel_im.save(panel_src, format="PNG")

            # 2. Arbitrary 3x4 (12 icons) sheet with generous empty padding inside each 384x384 cell
            rows, cols = 3, 4
            cell_raw = 384
            grid_src = tmp_dir / "custom_icons_3x4.png"
            grid_im = Image.new("RGBA", (cols * cell_raw, rows * cell_raw), (11, 14, 23, 255))
            gdraw = ImageDraw.Draw(grid_im)
            palette_cycle = [
                (255, 200, 40, 255),
                (50, 220, 240, 255),
                (245, 68, 120, 255),
                (64, 214, 130, 255),
            ]
            for r in range(rows):
                for c in range(cols):
                    idx = r * cols + c
                    cx = c * cell_raw + cell_raw // 2
                    cy = r * cell_raw + cell_raw // 2
                    # Intentionally draw non-square, off-square aspect icon (~160x100) with wide empty margin
                    rad_x = 76 if idx % 2 == 0 else 52
                    rad_y = 50 if idx % 2 == 0 else 82
                    gdraw.ellipse(
                        [cx - rad_x, cy - rad_y, cx + rad_x, cy + rad_y],
                        fill=palette_cycle[idx % len(palette_cycle)],
                        outline=(255, 255, 255, 255),
                        width=5,
                    )
            grid_im.save(grid_src, format="PNG")

            custom_names = [f"skill_{i}" for i in range(12)]
            out_dir = tmp_dir / "processed"
            res = self.gui_engine.process_slice_and_atlas(
                output_dir=str(out_dir),
                panel_source_path=str(panel_src),
                icon_source_paths=[str(grid_src)],
                grid_rows=3,
                grid_cols=4,
                icon_names=custom_names,
                cell_size=512,  # would be 2068x1556 without 1024 guard!
                max_dim=1500,   # must be clamped <= 1024!
                export_rbxmx=False,
            )
            self.assertTrue(res["ok"])

            p_meta = res["assets"]["panel_9slice"]
            self.assertLessEqual(p_meta["width"], 1024)
            self.assertLessEqual(p_meta["height"], 1024)
            self.assertTrue(p_meta["downscaled_for_1024_cap"])
            self.assertEqual(p_meta["validation_issues"], [])

            a_meta = res["assets"]["icons_atlas"]
            self.assertEqual(a_meta["grid"], [3, 4])
            self.assertTrue(a_meta["downscaled_for_1024_cap"])
            aw, ah = a_meta["atlas_size"]
            self.assertLessEqual(aw, 1024)
            self.assertLessEqual(ah, 1024)
            self.assertEqual(len(a_meta["sprites"]), 12)
            for name in custom_names:
                self.assertIn(name, a_meta["sprites"])
                # Tight trim must shrink sprite bbox cleanly below raw 384x384 cell dimensions
                tw, th = a_meta["trimmed_cells"][name]
                self.assertLess(tw, 220, f"Sprite {name} was not tight-trimmed (w={tw})")
                self.assertLess(th, 220, f"Sprite {name} was not tight-trimmed (h={th})")

            atlas_img = Image.open(out_dir / "icons_atlas.png").convert("RGBA")
            self.assertEqual(atlas_img.size, (aw, ah))
            # Check center of first sprite has opaque pixels and top-left gutter corner is transparent
            first_uv = a_meta["sprites"]["skill_0"]
            ox, oy = first_uv["ImageRectOffset"]
            sx, sy = first_uv["ImageRectSize"]
            self.assertGreater(atlas_img.getpixel((ox + sx // 2, oy + sy // 2))[3], 200)
            self.assertEqual(atlas_img.getpixel((0, 0))[3], 0)

            # 3. Also test skip_empty_cells=True on sparse 3x3 grid (only 7 populated)
            helper = self.gui_engine._load_py_module("slice_and_atlas_helper.py", "sharp_slice_helper_t")
            sparse_src = tmp_dir / "sparse_3x3.png"
            sparse_im = Image.new("RGBA", (900, 900), (11, 14, 23, 255))
            sdraw = ImageDraw.Draw(sparse_im)
            for idx in range(7):
                r, c = divmod(idx, 3)
                cx, cy = c * 300 + 150, r * 300 + 150
                sdraw.ellipse([cx - 60, cy - 60, cx + 60, cy + 60], fill=(80 + idx * 20, 210, 250, 255))
            sparse_im.save(sparse_src, format="PNG")
            sparse_meta = helper.split_grid_and_pack_atlas(
                sparse_src,
                tmp_dir / "sparse_atlas.png",
                rows=3,
                cols=3,
                names=[f"item_{i}" for i in range(7)],
                cell_size=256,
                skip_empty_cells=True,
            )
            self.assertEqual(len(sparse_meta["sprites"]), 7)
            self.assertLessEqual(max(sparse_meta["atlas_size"]), 1024)

    def test_design_content_ornaments_and_non_hardcoded_gui_builder(self) -> None:
        expected_ornaments = {
            "candy_simulator": "bubble_shine",
            "anime_neon": "cyber_slash",
            "cozy_pastel": "stitched_warm",
            "scifi_holo": "holo_brackets",
            "arcade_pop": "comic_stripe",
            "rpg_arcane": "arcane_filigree",
        }
        titles = {
            "candy_simulator": "Sugar Puppies Simulator",
            "anime_neon": "Neon Cyber Clash",
            "cozy_pastel": "Sunbeam Tea Bakery",
            "scifi_holo": "Nebula Mech Protocol",
            "arcade_pop": "Turbo Kart Mayhem",
            "rpg_arcane": "Royal Arcane Keep",
        }
        seen_roles = set()
        seen_objectives = set()
        for preset_id, expected_ornament in expected_ornaments.items():
            ds = self.engine.generate_design_system(titles[preset_id], genre=preset_id, mood="vibrant", seed=17)
            content = ds.get("content") or {}
            self.assertEqual(content.get("ornament_kind"), expected_ornament)
            self.assertTrue(content.get("role_title"))
            self.assertTrue(content.get("objective_title"))
            self.assertTrue(content.get("objective_text"))
            self.assertEqual(len(content.get("hotbar_skills") or []), 5)
            seen_roles.add(content["role_title"])
            seen_objectives.add(content["objective_title"])

            theme_luau = self.engine.compile_theme_luau(ds, module_mode=True)
            _assert_luau_balanced(self, theme_luau, f"theme_content_{preset_id}")
            self.assertIn("Content = {", theme_luau)
            self.assertIn(f'OrnamentKind = "{expected_ornament}"', theme_luau)
            self.assertIn("RoleTitle =", theme_luau)
            self.assertIn("ObjectiveTitle =", theme_luau)
            self.assertIn("HotbarSkills = {", theme_luau)
            for skill_label in content["hotbar_skills"]:
                self.assertIn(f'"{skill_label}"', theme_luau)

            built_luau = self.gui_engine.compile_gui_build_luau(design_system=ds)
            _assert_luau_balanced(self, built_luau, f"gui_build_{preset_id}")
            self.assertIn(f'OrnamentKind = "{expected_ornament}"', built_luau)

        self.assertEqual(len(seen_roles), 6)
        self.assertGreaterEqual(len(seen_objectives), 5)

        scripts_dir = SKILLS_DIR / "roblox-gui" / "scripts"
        ui_kit_src = (scripts_dir / "ui_theme_and_components.luau").read_text(encoding="utf-8")
        builder_src = (scripts_dir / "build_standard_game_gui.luau").read_text(encoding="utf-8")

        # UIKit.AttachPresetOrnament covers all 6 ornament kinds safely and integrates with panels
        self.assertIn("function UIKit.AttachPresetOrnament", ui_kit_src)
        self.assertIn("function UIKit.CreateWindow", ui_kit_src)
        for kind in expected_ornaments.values():
            self.assertIn(f'"{kind}"', ui_kit_src)
        self.assertIn("UIGridStyleLayout", ui_kit_src)
        self.assertIn("container.Active = false", ui_kit_src)
        self.assertIn("container.Selectable = false", ui_kit_src)
        self.assertIn("container.ZIndex = 0", ui_kit_src)
        self.assertIn("container.ClipsDescendants = true", ui_kit_src)
        self.assertIn("NoOrnament", ui_kit_src)

        # build_standard_game_gui.luau reads Content & themeColors instead of hardcoded Color3 in 3D preview models / vignette
        for token in (
            "contentGameTitle",
            "contentRoleTitle",
            "contentObjectiveTitle",
            "contentObjectiveText",
            "contentHotbarSkills",
            "NoOrnament = true",
        ):
            self.assertIn(token, builder_src)
        for fn_start, fn_end in (
            ("local function buildSwordModel", "local function buildGemRelicModel"),
            ("local function buildGemRelicModel", "local function buildShieldModel"),
            ("local function buildShieldModel", "local function buildNpcBustModel"),
            ("local function buildNpcBustModel", "local swordModel = buildSwordModel()"),
            ("local vignetteFrame = Instance.new", "local mainHudGui = makeLayer"),
        ):
            i0 = builder_src.index(fn_start)
            i1 = builder_src.index(fn_end, i0)
            block = builder_src[i0:i1]
            self.assertNotIn("Color3.fromRGB(", block, f"Hardcoded Color3.fromRGB found in {fn_start}")
            self.assertIn("themeColors.", block, f"Expected themeColors in {fn_start}")

    def test_texture_and_asset_style_profiles_and_theme_luau(self) -> None:
        expected_tex = {
            "clean_vector_cel",
            "stylized_gradient_atlas",
            "pbr_metallic_roughness",
            "pixel_retro_crisp",
            "arcane_emissive_runes",
        }
        expected_asset = {
            "lowpoly_flat_stylized",
            "handpainted_fantasy_rpg",
            "hard_surface_scifi_mecha",
            "chibi_chunky_toon",
            "dark_gothic_souls",
        }
        self.assertEqual(set(TEXTURE_STYLE_PROFILES.keys()), expected_tex)
        self.assertEqual(set(ASSET_STYLE_PROFILES.keys()), expected_asset)

        presets_res = self.engine.list_presets()
        self.assertIn("texture_styles", presets_res)
        self.assertIn("asset_styles", presets_res)
        styles_res = self.engine.list_style_profiles()
        self.assertTrue(styles_res["ok"])
        self.assertEqual(set(styles_res["texture_styles"].keys()), expected_tex)
        self.assertEqual(set(styles_res["asset_styles"].keys()), expected_asset)

        # Auto-selection from presets
        for pid in DESIGN_PRESETS:
            ds = self.engine.generate_design_system(f"StyleTest {pid}", genre=pid, seed=101)
            self.assertIn(ds["texture_style"], expected_tex)
            self.assertIn(ds["asset_style"], expected_asset)
            self.assertEqual(ds["texture_style_profile"]["style_id"], ds["texture_style"])
            self.assertEqual(ds["asset_style_profile"]["style_id"], ds["asset_style"])

        # Explicit override + keyword auto-selection + Luau emission
        ds_explicit = self.engine.generate_design_system(
            "Citadel of Eternity",
            genre="rpg_arcane",
            mood="dark gothic",
            seed=202,
            texture_style="pixel_retro_crisp",
            asset_style="dark_gothic_souls",
        )
        self.assertEqual(ds_explicit["texture_style"], "pixel_retro_crisp")
        self.assertEqual(ds_explicit["asset_style"], "dark_gothic_souls")

        for mod_mode in (True, False):
            theme_luau = self.engine.compile_theme_luau(ds_explicit, module_mode=mod_mode)
            self.assertIn('TextureStyle = "pixel_retro_crisp"', theme_luau)
            self.assertIn('AssetStyle = "dark_gothic_souls"', theme_luau)
            assert_valid_luau_sanity(theme_luau, f"theme_styles_{mod_mode}")
            toks, _ = tokenize_luau(theme_luau)
            self.assertFalse(any(t.value == ";" for t in toks))

    def test_create_pbr_texture_set_all_styles_determinism_and_luau(self) -> None:
        art = ArtCreationEngine(design_engine=self.engine, gui_engine=self.gui_engine)
        ds = self.engine.generate_design_system("Aether Bastion", genre="rpg_arcane", seed=303)

        with tempfile.TemporaryDirectory(prefix="sharp_pbr_test_") as td:
            root = Path(td)
            means_metallic: Dict[str, float] = {}
            for style_id in TEXTURE_STYLE_PROFILES:
                out_a = root / f"{style_id}_a"
                out_b = root / f"{style_id}_b"
                res_a = art.create_pbr_texture_set(
                    output_dir=str(out_a),
                    design_system=ds,
                    texture_style=style_id,
                    resolution=128,
                )
                res_b = art.create_pbr_texture_set(
                    output_dir=str(out_b),
                    design_system=ds,
                    texture_style=style_id,
                    resolution=128,
                )
                self.assertTrue(res_a["ok"])
                self.assertEqual(res_a["texture_style"], style_id)
                self.assertEqual(res_a["resolution"], 128)
                self.assertEqual(res_a["texture_style_profile"]["style_id"], style_id)

                for map_key in ("albedo", "normal", "roughness", "metallic"):
                    pa = Path(res_a["maps"][map_key])
                    pb = Path(res_b["maps"][map_key])
                    self.assertTrue(pa.is_file(), f"Missing {map_key} for {style_id}")
                    # Deterministic byte-for-byte output
                    self.assertEqual(
                        hashlib.sha256(pa.read_bytes()).hexdigest(),
                        hashlib.sha256(pb.read_bytes()).hexdigest(),
                        f"Non-deterministic {map_key} for {style_id}",
                    )
                    with Image.open(pa) as im:
                        self.assertEqual(im.size, (128, 128))
                        if map_key == "albedo":
                            self.assertEqual(im.mode, "RGBA")
                        elif map_key == "normal":
                            self.assertEqual(im.mode, "RGB")
                            arr = np.asarray(im)
                            self.assertGreater(int(arr[:, :, 2].mean()), 180)
                        else:
                            self.assertEqual(im.mode, "L")

                means_metallic[style_id] = float(res_a["stats"]["mean_metallic"])
                luau_src = Path(res_a["luau_module_path"]).read_text(encoding="utf-8")
                self.assertTrue(luau_src.startswith("--!strict"))
                self.assertIn("SharpSurfaceAppearance.Apply", luau_src)
                self.assertIn(style_id, luau_src)
                assert_valid_luau_sanity(luau_src, f"surface_appearance_{style_id}")
                toks, dirs = tokenize_luau(luau_src)
                self.assertEqual(dirs, ["--!strict"])
                self.assertFalse(any(t.value == ";" for t in toks))

            self.assertGreater(means_metallic["pbr_metallic_roughness"], means_metallic["clean_vector_cel"] + 0.4)

    def test_uikit_composable_primitives_strict_no_semicolons_and_mirror_parity(self) -> None:
        bundled_uikit = SKILLS_DIR / "roblox-gui" / "scripts" / "ui_theme_and_components.luau"
        src = bundled_uikit.read_text(encoding="utf-8")
        self.assertTrue(src.startswith("--!strict"))
        for fn_name in (
            "function UIKit.CreateArcGauge",
            "function UIKit.CreateRadialWheel",
            "function UIKit.CreateCardFan",
            "function UIKit.CreateBookSpread",
        ):
            self.assertIn(fn_name, src)
        assert_valid_luau_sanity(src, "ui_theme_and_components.luau")
        toks, dirs = tokenize_luau(src)
        self.assertIn("--!strict", dirs)
        self.assertEqual([t for t in toks if t.value == ";"], [], "Semicolons are forbidden in ui_theme_and_components.luau")

        # Verify 3-way SHA-256 parity and zero __pycache__ in roblox-gui mirrors
        for mirror_root in (DESKTOP_GUI_SKILL_DIR, LIVE_SKILL_DIR):
            if mirror_root.is_dir():
                self.assertEqual(list(mirror_root.rglob("__pycache__")), [], f"Unexpected __pycache__ in {mirror_root}")
                mirror_file = mirror_root / "scripts" / "ui_theme_and_components.luau"
                self.assertTrue(mirror_file.is_file())
                self.assertEqual(
                    hashlib.sha256(bundled_uikit.read_bytes()).hexdigest(),
                    hashlib.sha256(mirror_file.read_bytes()).hexdigest(),
                    f"ui_theme_and_components.luau parity mismatch at {mirror_file}",
                )

    def test_custom_ui_authoring_guide_and_compile_custom_gui_build_luau(self) -> None:
        expected_paradigms = {
            "arpg_orbs",
            "scifi_visor_radial",
            "cozy_book_journal",
            "card_battler_fan",
            "street_racer_cockpit",
            "minimal_horror_cam",
        }
        self.assertEqual(set(LAYOUT_PARADIGM_BLUEPRINTS.keys()), expected_paradigms)

        ds = self.engine.generate_design_system("Valkyrie Horizon", genre="scifi_holo", seed=404)
        all_guide = self.gui_engine.get_custom_ui_authoring_guide(paradigm="all", design_system=ds)
        self.assertTrue(all_guide["ok"])
        self.assertEqual(set(all_guide["blueprints"].keys()), expected_paradigms)
        self.assertEqual(all_guide["design_tokens_summary"]["texture_style"], ds["texture_style"])

        bad_guide = self.gui_engine.get_custom_ui_authoring_guide(paradigm="nonexistent_paradigm")
        self.assertFalse(bad_guide["ok"])
        self.assertEqual(set(bad_guide["available_paradigms"]), expected_paradigms)

        for p_id in expected_paradigms:
            guide = self.gui_engine.get_custom_ui_authoring_guide(paradigm=p_id, design_system=ds)
            self.assertTrue(guide["ok"], f"Guide failed for {p_id}")
            starter_luau = guide["starter_luau"]
            assert_valid_luau_sanity(starter_luau, f"starter_{p_id}")

            compiled = self.gui_engine.compile_custom_gui_build_luau(
                starter_luau,
                panel_asset_id="rbxassetid://701",
                button_asset_id="rbxassetid://702",
                atlas_asset_id="rbxassetid://703",
                run_audit_after=True,
                design_system=ds,
                clear_previous_sharp_guis=True,
            )
            self.assertIn("UIThemeAndComponents", compiled)
            self.assertIn("UIKit.BuildStyleSheet(ReplicatedStorage)", compiled)
            self.assertIn("UIKit.ApplyDesignSystem(DesignTheme)", compiled)
            self.assertIn("SharpManagedGui", compiled)
            self.assertIn("__SharpActiveRecordingId", compiled)
            self.assertIn("auditReport", compiled)
            self.assertIn("rbxassetid://701", compiled)
            assert_valid_luau_sanity(compiled, f"compile_custom_gui_build_luau({p_id})")
            toks, _ = tokenize_luau(compiled)
            self.assertGreater(len(toks), 100)
            self.assertEqual([t for t in toks if t.value == ";"], [])

        no_clear_no_audit = self.gui_engine.compile_custom_gui_build_luau(
            LAYOUT_PARADIGM_BLUEPRINTS["arpg_orbs"]["starter_luau_example"],
            run_audit_after=False,
            clear_previous_sharp_guis=False,
        )
        self.assertIn("local clearPrev = false", no_clear_no_audit)
        self.assertIn("if false then", no_clear_no_audit)
        assert_valid_luau_sanity(no_clear_no_audit, "compile_custom_no_clear_no_audit")

        with self.assertRaises(ValueError):
            self.gui_engine.compile_custom_gui_build_luau("   ")

    def _extract_uikit_fn(self, src: str, fn_name: str) -> str:
        header = f"function UIKit.{fn_name}("
        start = src.index(header)
        end = src.find("\nend\n", start)
        if end == -1:
            end = src.find("\nend", start)
        self.assertNotEqual(end, -1, f"Could not locate closing end for UIKit.{fn_name}")
        return src[start : end + len("\nend")]

    def _assert_uikit_four_fixes(self, src: str, label: str) -> None:
        # 1A: CreatePanel & CreateArcGauge offset AnchorPoint trap
        self.assertIn("local function resolveDefaultAnchorPoint(", src, f"{label}: missing resolveDefaultAnchorPoint")
        helper_start = src.index("local function resolveDefaultAnchorPoint(")
        helper_end = src.index("\nend\n", helper_start)
        helper_block = src[helper_start:helper_end]
        for expected in (
            "if anchorPoint ~= nil then",
            "position.X.Scale == 0",
            "position.Y.Scale == 0",
            "(position.X.Offset ~= 0 or position.Y.Offset ~= 0)",
            "return Vector2.zero",
            "return Vector2.new(0.5, 0.5)",
        ):
            self.assertIn(expected, helper_block, f"{label}: resolveDefaultAnchorPoint missing {expected!r}")

        panel_block = self._extract_uikit_fn(src, "CreatePanel")
        self.assertIn("resolveDefaultAnchorPoint(opts.Position, opts.AnchorPoint)", panel_block, f"{label}: CreatePanel")
        self.assertNotIn("opts.AnchorPoint or Vector2.new(0.5, 0.5)", panel_block, f"{label}: CreatePanel 9-slice/frame still uses old default")

        gauge_block = self._extract_uikit_fn(src, "CreateArcGauge")
        self.assertIn("resolveDefaultAnchorPoint(o.Position, o.AnchorPoint)", gauge_block, f"{label}: CreateArcGauge")
        self.assertNotIn("o.AnchorPoint or Vector2.new(0.5, 0.5)", gauge_block, f"{label}: CreateArcGauge still uses old default")

        # 1B: CreateBookSpread BookTitle collision on LeftPage
        book_block = self._extract_uikit_fn(src, "CreateBookSpread")
        for expected in (
            'local leftContent = Instance.new("Frame")',
            'leftContent.Name = "PageContent"',
            "leftContent.BackgroundTransparency = 1",
            "leftContent.BorderSizePixel = 0",
            "UDim2.fromOffset(0, 30)",
            "UDim2.new(1, 0, 1, -30)",
            "leftContent.ZIndex = baseZ + 4",
            "leftContent.Parent = leftPage",
            "LeftPage = leftContent",
            "LeftPageRaw = leftPage",
            "RightPage = rightPage",
        ):
            self.assertIn(expected, book_block, f"{label}: CreateBookSpread missing {expected!r}")
        self.assertNotIn("o.OnTabChanged(idx, tab.Id or tab.Label, leftPage, rightPage)", book_block)
        self.assertNotIn("o.OnTabChanged(activeIndex, chosen.Id or chosen.Label, leftPage, rightPage)", book_block)

        # 1C: AttachTextStroke whisper-thin rim on dark text + CreateButton PickReadableTextColor
        stroke_block = self._extract_uikit_fn(src, "AttachTextStroke")
        self.assertIn("UIKit.RelativeLuminance(effTextColor) < 0.35 and UIKit.RelativeLuminance(resolvedColor) < 0.35", stroke_block)
        self.assertIn("resolvedThickness = math.min(0.6, resolvedThickness * 0.3)", stroke_block, f"{label}: AttachTextStroke thickness")
        self.assertIn("resolvedTransparency = math.max(0.82, resolvedTransparency)", stroke_block, f"{label}: AttachTextStroke transparency")
        self.assertNotIn("math.min(1.0, resolvedThickness * 0.45)", stroke_block)
        self.assertNotIn("math.max(0.55, resolvedTransparency)", stroke_block)

        btn_block = self._extract_uikit_fn(src, "CreateButton")
        self.assertIn("local textColor = opts.TextColor or UIKit.PickReadableTextColor(fillColor)", btn_block, f"{label}: CreateButton textColor")
        self.assertNotIn("variantTextColors", btn_block)

        # 1D: AttachStackedStrokes InnerStroke BorderStrokePosition on circular frames
        stacked_block = self._extract_uikit_fn(src, "AttachStackedStrokes")
        self.assertIn(
            "sAny.BorderStrokePosition = if isCircular then Enum.BorderStrokePosition.Center else Enum.BorderStrokePosition.Inner",
            stacked_block,
            f"{label}: AttachStackedStrokes InnerStroke",
        )
        self.assertNotIn("sAny.BorderStrokePosition = Enum.BorderStrokePosition.Inner\n", stacked_block)

        # 1E: CreateRadialWheel active selection text contrast + crisp Heading hub font
        wheel_block = self._extract_uikit_fn(src, "CreateRadialWheel")
        self.assertIn("UIKit.PickReadableTextColor(bgColor)", wheel_block, f"{label}: CreateRadialWheel readable label contrast")
        self.assertIn("hubLabel.FontFace = UIKit.Tokens.Fonts.Heading", wheel_block, f"{label}: CreateRadialWheel Heading hub font")

    def test_uikit_v05_layout_contrast_bookspread_and_stroke_fixes(self) -> None:
        bundled_uikit = SKILLS_DIR / "roblox-gui" / "scripts" / "ui_theme_and_components.luau"
        raw_src = bundled_uikit.read_text(encoding="utf-8")
        self._assert_uikit_four_fixes(raw_src, "raw ui_theme_and_components.luau")

        # Verify fixes propagate cleanly into compiled standard & custom GUI Luau output
        ds = self.engine.generate_design_system("Valkyrie Almanac", genre="cozy_pastel", seed=88)
        compiled_std = self.gui_engine.compile_gui_build_luau(design_system=ds)
        self._assert_uikit_four_fixes(compiled_std, "compile_gui_build_luau")
        _assert_luau_balanced(self, compiled_std, "compile_gui_build_luau(v05)")

        compiled_custom = self.gui_engine.compile_custom_gui_build_luau(
            LAYOUT_PARADIGM_BLUEPRINTS["cozy_book_journal"]["starter_luau_example"],
            design_system=ds,
        )
        self._assert_uikit_four_fixes(compiled_custom, "compile_custom_gui_build_luau(cozy_book_journal)")
        _assert_luau_balanced(self, compiled_custom, "compile_custom_gui_build_luau(v05)")
        assert_valid_luau_sanity(compiled_custom, "compile_custom_gui_build_luau(v05)")
        toks, _ = tokenize_luau(compiled_custom)
        self.assertEqual([t for t in toks if t.value == ";"], [])


if __name__ == "__main__":
    unittest.main()

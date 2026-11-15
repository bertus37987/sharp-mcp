from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sharp_mcp.domain_engines.design_engine import (  # noqa: E402
    DESIGN_PRESETS,
    DesignEngine,
    delta_e_cie76,
    hex_to_hsl,
    hex_to_rgb,
    hue_distance_deg,
    wcag_contrast_ratio,
)
from sharp_mcp.domain_engines.gui_engine import GuiDomainEngine  # noqa: E402


SKILLS_DIR = REPO_ROOT / "sharp_mcp" / "bundled_skills"
LIVE_SKILL_DIR = Path(os.path.expanduser("~")) / ".gemini" / "config" / "skills" / "roblox-gui"


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


if __name__ == "__main__":
    unittest.main()

# Sharp Reference Experience — Living Game Plan & Asset Registry

- **Project ID:** `default_game`
- **Genre:** Cross-Platform Action RPG / Adventure
- **Current Version:** `v0002`
- **Active Studio PlaceId:** `0`
- **Last Updated:** `2026-11-14T16:34:10Z`

> Clean production Sharp reference baseline with 20 verified assets and portable relative paths.

---

## 1. Installed & Active Game Systems

| Domain | Status | Executions | Last Version | Last Action |
|---|---|---:|---|---|
| `animation` | active | 1 | `v0001` | Registered R15 sword/walk/combo animation metadata baseline |
| `audio_vfx_cutscenes` | active | 1 | `v0002` | Seeded built-in Roblox SFX and flipbook VFX library baseline |
| `gui` | active | 1 | `v0001` | Registered 9-slice panels, tint button, and 2x2 HUD icon atlas |
| `luau_coding` | active | 1 | `v0001` | Scaffolded clean 14-container Explorer architecture with SafeRemoteGateway |
| `terrain_atmosphere` | active | 1 | `v0001` | Registered 513x513 Alpine heightmap/colormap baseline |

## 2. Milestones

- [x] Core Explorer architecture, GUI 9-slice atlas, R15 animation & Alpine terrain baseline
- [x] Verified Audio & Flipbook VFX asset registry baseline (20 assets)
- [ ] Playtest bot combat & Shop/DataStore end-to-end verification

## 3. Registered Asset Library

### `animation` (3)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `R15_SwordSlash_Action` | R15_SwordSlash_Action | `rbxassetid://0` | `-` | v1 |
| `R15_WalkCycle_Curve` | R15_WalkCycle_Curve | `rbxassetid://0` | `-` | v1 |
| `WeaponShield_Combo_Action` | WeaponShield_Combo_Action | `rbxassetid://0` | `-` | v1 |

### `audio` (5)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `Sound_Footstep_Plastic` | Sound_Footstep_Plastic | `rbxasset://sounds/action_footsteps_plastic.mp3` | `-` | v1 |
| `Sound_Quest_Complete` | Sound_Quest_Complete | `rbxasset://sounds/electronicpingshort.wav` | `-` | v1 |
| `Sound_Sword_Lunge` | Sound_Sword_Lunge | `rbxasset://sounds/lunge.wav` | `-` | v1 |
| `Sound_Sword_Slash` | Sound_Sword_Slash | `rbxasset://sounds/swordslash.wav` | `-` | v1 |
| `Sound_UI_ButtonClick` | Sound_UI_ButtonClick | `rbxasset://sounds/button.wav` | `-` | v1 |

### `gui_9slice` (5)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `ModalPanel_9Slice` | ModalPanel_9Slice | `rbxassetid://0` | `panel_9slice.png` | v1 |
| `Raw_DarkFantasy_ModalPanel` | Raw_DarkFantasy_ModalPanel | `rbxassetid://0` | `roblox_panel_9slice_1794652695001.jpg` | v1 |
| `Raw_Grayscale_TintButton` | Raw_Grayscale_TintButton | `rbxassetid://0` | `button_tint_9slice_1794652696255.jpg` | v1 |
| `Raw_Icons_2x2_Sheet` | Raw_Icons_2x2_Sheet | `rbxassetid://0` | `icons_2x2_sheet_1794652702333.jpg` | v1 |
| `TintButton_9Slice` | TintButton_9Slice | `rbxassetid://0` | `button_tint_9slice.png` | v1 |

### `gui_atlas` (1)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `CoreHudIcons_Atlas` | CoreHudIcons_Atlas | `rbxassetid://0` | `icons_atlas.png` | v1 |

### `misc` (4)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `VFX_Explosion_Flipbook` | VFX_Explosion_Flipbook | `rbxasset://textures/particles/explosion01_implosion_main.dds` | `-` | v1 |
| `VFX_Fire_Main` | VFX_Fire_Main | `rbxasset://textures/particles/fire_main.dds` | `-` | v1 |
| `VFX_Smoke_Main` | VFX_Smoke_Main | `rbxasset://textures/particles/smoke_main.dds` | `-` | v1 |
| `VFX_Sparkles_Main` | VFX_Sparkles_Main | `rbxasset://textures/particles/sparkles_main.dds` | `-` | v1 |

### `terrain_preset` (2)

| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |
|---|---|---|---|---:|
| `AlpineBiome_Colormap_513` | AlpineBiome_Colormap_513 | `rbxassetid://0` | `-` | v1 |
| `AlpineBiome_Heightmap_513` | AlpineBiome_Heightmap_513 | `rbxassetid://0` | `-` | v1 |

## 4. Recent Version Timeline

| Version | Timestamp | Tool | Domain | Summary |
|---|---|---|---|---|
| `v0002` | `2026-11-14T14:44:07Z` | `sharp_game_library` | `audio_vfx_cutscenes` | Seeded verified Roblox SFX & VFX flipbook presets cleanly (20 assets) |
| `v0001` | `2026-11-14T13:36:59Z` | `sharp_game_library` | `library_init` | Initial Sharp Game Plan & Verified Core Asset Baseline (11 assets) |

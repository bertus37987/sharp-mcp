# `Sharp` MCP Server (`sharp-mcp` v0.5.0) & `SharpBridgePlugin.rbxmx`

> **License Notice (Private Non-Commercial Pre-Release):**
> All Rights Reserved — Non-Commercial Internal Evaluation Only (`LICENSE`, `"private": true`).
> Commercial use, SaaS hosting, public publishing, or third-party redistribution are prohibited without explicit written consent.

Cross-platform Model Context Protocol (MCP) server unifying **Roblox Studio (`SharpBridgePlugin.rbxmx`)**, an **Automatic Skill Distributor (`SkillRouter`)**, **Concept Intake & Micro-Step MVP Planner (`sharp_game_plan`)**, **Multimodal Playtest Video, Soundtest DSP & Vision GUI QA (`sharp_media_qa`)**, **Anti-Slop Procedural 2D Art, Custom Bitmap Fonts, 2D/3D VFX & AI Image Studio (`sharp_art_studio` + `sharp_ai_studio`)**, **3D Map Overlap/Glitch Auditor (`audit_overlaps`/`fix_overlaps`)**, **Surgical Live GUI Tools (`sharp_gui_inspect` / `sharp_gui_patch` / `sharp_visual_diff`)**, **Offline Game-Dev Toolchain Orchestration (`Rojo`, `Lune`, `Selene`, `StyLua`)**, and **Optional Auto-Installable Blender 3D/Animation Execution**.

---

## 1. Quick Start (`npx` / `uv` / Python CLI)

First-class target clients: **Antigravity**, **Claude (Claude Code & Claude Desktop)**, **OpenAI Codex CLI**, and **OpenCode (V2)**.

Requires Python `>=3.11` and `mcp>=1.7.0,<2`: 1.7 adds the tool annotations Sharp uses; MCP 2.x removed `mcp.server.fastmcp`. `doctor` checks actual server importability. For OpenCV-backed media QA, install the optional extra with `python -m pip install '.[media]'` (`opencv-python-headless`); video analysis falls back to `ffmpeg` on PATH when OpenCV is unavailable.

```bash
# Run doctor diagnostics without mutating your open Studio place
npx --yes ./06_sharp_mcp_server doctor
# Or via Python CLI:
python -m sharp_mcp.cli doctor

# Manage OpenRouter & Gemini API keys cleanly OUTSIDE version control (~/.sharp-mcp/credentials.json)
python -m sharp_mcp.cli keys status
python -m sharp_mcp.cli keys models
python -m sharp_mcp.cli keys set --provider openrouter --stdin
python -m sharp_mcp.cli keys set --provider gemini --stdin

# Register Sharp across Antigravity, Claude, Codex, and OpenCode (atomic JSON/TOML merge + .bak)
python -m sharp_mcp.cli register --client all --prune-legacy

# Install SharpBridgePlugin.rbxmx into Roblox Studio Plugins (%LOCALAPPDATA%\Roblox\Plugins or ~/Documents/Roblox/Plugins)
python -m sharp_mcp.cli install-plugin

# Check or auto-install Blender + mcp-for-blender addon (winget/brew + headless addon enable)
python -m sharp_mcp.cli install-blender --dry-run
```

---

## 2. Architecture Overview

| Component | Path | Description |
| :--- | :--- | :--- |
| **CLI & `npx` Wrapper** | `bin/sharp-mcp.mjs`, `sharp_mcp/cli.py`, `package.json`, `pyproject.toml` | Cross-platform Node ESM wrapper delegating cleanly to Python `>=3.11` / `uv` + subcommands `serve`, `install-plugin`, `install-blender`, `register`, `keys`, `doctor`, and `self-test`. |
| **External AI Keys Store** | `sharp_mcp/credentials_store.py` | Stores `GEMINI_API_KEY` / `OPENROUTER_API_KEY` outside repos (`~/.sharp-mcp/credentials.json` or `SHARP_CREDENTIALS_PATH`), prefers env vars, and never echoes raw secrets. Image presets use `gemini-2.5-flash-image` / `gemini-3-pro-image` (OpenRouter: `google/` prefix); Imagen is retired. Other presets include `google/gemini-2.5-flash-lite`, `qwen/qwen2.5-vl-72b-instruct` (vision), `anthropic/claude-sonnet-4.5`, and `qwen/qwen-2.5-coder-32b-instruct` (text-only GUI code). Run `keys models` for the full list. |
| **Client Registrar** | `sharp_mcp/client_registry.py` | Atomic config registration with `.bak` backups and legacy pruning for Antigravity, Claude Code (`~/.claude.json` / `.mcp.json`), Claude Desktop, Codex (`~/.codex/config.toml`), and OpenCode V2 (`mcp.servers` JSON/JSONC). |
| **Skill Router (`<3 KB`)** | `sharp_mcp/skill_router.py` | Indexes **13 local skills** (9 Roblox + 4 optional Blender), built-in Studio `rbx-*` hints, and role-scoped `subagent_delegations` in `detail="complete"`. Token-budgeted rule cards in `detail="summary"` (`<3 KB`) with progressive loading via `sharp_load_skill` or `sharp://skills/{name}/SKILL.md`. |
| **Effects, Annotations & Pagination** | `sharp_mcp/tool_effects.py` | Declarative `TOOL_EFFECT_AUDIT` generating MCP `ToolAnnotations` (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) for all **34 tools**, retained `SnapshotViewStore` cursor pagination (`sharp_inspect_snapshot_view`), and untrusted-content `_meta` framing. |
| **Security-Hardened Bridge** | `sharp_mcp/bridge_broker.py` | Async loopback broker (`127.0.0.1:58421`) with IPv4/IPv6 loopback verification, strict `Host` allowlist, `Sec-Fetch-*` & `Origin` rejection (`403`), `secrets.compare_digest` Bearer (`401`), `X-Sharp-Server-Epoch` (`409`), stale `placeId`/`studioSessionId` guards, 1-writer/4-reader mutex, UTF-8 chunking, and 5s `/v1/heartbeat` leases. |
| **Single-Use Transient HTTP** | `sharp_mcp/transient_http.py` | Ephemeral `127.0.0.1:0` server with `Host`/loopback/`Sec-Fetch-*`/`Origin` guards, `60s` default TTL, and strictly single-use `(token, filename)` binary URLs. |
| **Standalone Studio Plugin** | `studio_plugin/SharpBridgePlugin.rbxmx` | Built by `studio_plugin/build_plugin_rbxmx.py` with **29 embedded `--!strict` `ModuleScript`s** (`SharpUndo` with post-write readback rollback, `DockWidget` onboarding when `HttpEnabled=false`, `SharpGuiTools`, `SharpTreeTools` + GUID `SharpHandle`s + `ScriptEditorService:UpdateSourceAsync`, and 25 skill modules). |
| **Domain Engines** | `sharp_mcp/domain_engines/` | `art_creation_engine.py` (procedural 2x SSAA 9-slice/ray/icon kits, Roblox font pairings + custom stroked BitmapFonts, 4×4 2D UI & 3D World VFX flipbooks + `SharpUiVfx`/`SharpWorldVfx` Luau, AI UI/image gen), `multimodal_qa_engine.py` (`inspect_video` telemetry + contact sheet + `ffmpeg` audio extraction, `inspect_audio` DSP peak/RMS/clip/DC/silence, `inspect_gui_vision` anti-slop Gemini/OpenRouter QA), `design_engine.py`, `attachment_engine.py`, `game_planner.py` (`intake_questions`, `granularity="micro"` step-by-step MVP lock, `subagent_brief`), `critical_audit_engine.py` (incl. `WORLD-OVERLAP-001` / `WORLD-FLOAT-001`), `gui_engine.py`, `blender_engine.py`, `toolchain_engine.py`, `terrain_env_engine.py`, `rig_anim_engine.py`, `luau_audit_engine.py`, `gameplay_systems_engine.py`, and `upstream_multiplexer.py`. |
| **Game Plan & Asset Library** | `sharp_mcp/project_library.py` | Project-relative `GAME_PLAN.md`, `plan.json`, persisted `design_system`, snapshots `v0001..vNNNN`, relative-path `asset_manifest.json`, and generated `--!strict` `SharpAssetRegistry.luau` bound to `--project-dir` or active `placeId`. |

---

## 3. MCP Profiles, Tools (`34` / `30` / `11`), Resources (`4` fixed + `1` template) & Prompts (`5`)

* **`--profile full` (34 tools, default):** Full Roblox Studio + Design System + Art Studio + AI Studio + Multimodal Media QA + Equipment Attach + Micro-MVP Planner + Critical Audit + Toolchain + Blender suite.
* **`--profile core` (30 tools):** Studio + Design + Art + AI + Media QA + Planner + Audit + Toolchain (omits `sharp_blender_setup`, `sharp_blender_rig_and_anim`, `sharp_blender_asset_pipeline`, and `sharp_equipment_attach`).
* **`--profile blender` (11 tools):** Focused 3D asset, rigging, equipment attachment, animation, routing, and library subset.

### Active Tools
1. `sharp_route_task` — Token-budgeted task classifier (`detail="summary"` `<3 KB` or `"complete"` with `subagent_delegations`) and execution DAG planner.
2. `sharp_load_skill` — On-demand loader for the 13 domain skills, references, and scripts.
3. `sharp_studio_status` — Plugin bridge, `HttpEnabled`, Blender detection, and session skill status.
4. `sharp_blender_setup` — Detect or auto-install Blender (`winget`/`brew`) and the `mcp-for-blender` addon.
5. `sharp_terrain_build` — Chunked 4x4x4 voxel biome builder (`WriteVoxelChannels`) or offline heightmap/colormap PNGs.
6. `sharp_environment_apply` — 13 Lighting/Atmosphere/Clouds/ColorGrading presets + environment audit.
7. `sharp_gui_slice_and_pack` — Pillow 9-slice border detector, generalized RxC / trimmed icon atlas packer, and `.rbxmx` GUI exporter.
8. `sharp_gui_build` — Responsive cross-platform 11-layer `StarterGui` builder with `UIKit.Assets` injection & persisted `design_system` tokens.
9. `sharp_gui_inspect` — Semantic live `StarterGui`/`PlayerGui` inspector (`AbsoluteSize/Position`, `StyleRule`s, `IsPropertyModified`, GUID `SharpHandle`s).
10. `sharp_gui_patch` — Surgical non-destructive property/`StyleRule`/`ResetPropertyToDefault` patcher with readback diff + `SharpUndo`.
11. `sharp_visual_diff` — Deterministic Pillow + numpy RGBA screenshot pixel diff, bounding box delta, blank-frame check, and optional `StudioDeviceSimulatorService` QA.
12. `sharp_rig_and_animation` — Live rig prober, `KeyframeSequence`/`CurveAnimation` compiler, and `.rbxmx` exporter.
13. `sharp_blender_rig_and_anim` — Blender `bpy` rig/motion compiler with direct socket or headless execution.
14. `sharp_blender_asset_pipeline` — Modular 3D asset & Cycles PBR bake compiler with direct socket or headless execution.
15. `sharp_luau_scaffold` — Canonical Explorer containers, `SafeRemoteGateway`, tree search, and `ScriptEditorService` editing.
16. `sharp_audit_all` — Multi-domain static & live Studio auditor with `SnapshotViewStore` pagination.
17. `sharp_snapshot_and_undo` — Full-place `checkpoint`/`restore` zero-diff baseline engine and `ChangeHistoryService:Undo()`.
18. `sharp_combat_and_controllers` — Physics `ControllerManager`, `Motor6D` tools, and server-validated hitboxes/projectiles.
19. `sharp_audio_vfx_cutscenes` — Node-based Audio API bus graph, burst `ParticleEmitter` presets, 28-slot `Highlight` pool, and splines.
20. `sharp_data_economy_monetization` — Session-locked `DataStoreService:UpdateAsync` (with Studio mock fallback), economy, and `ProcessReceipt`.
21. `sharp_ai_and_gameplay_systems` — `CollectionService` NPC AI FSM + `PathfindingService`, `ProximityPrompt` dialogues, and wave directors.
22. `sharp_world_assembly_and_optimization` — Poisson scatter, socket snapping, OBB overlap/floating audits, and streaming optimization. `audit_overlaps` returns `overlapCount`, `floatingCount`, and `allClean`; `fix_overlaps` iteratively separates smaller eligible assets, grounds assets with raycast hits, and returns final remaining counts. `float_tolerance_studs=0.5` (clamped 0–512) and `max_iterations=8` (1–64) control repair. `SharpLocked=true` prevents movement; `SharpAllowFloating=true` opts out of floating checks, as do unanchored assets. Locked conflicts, voids, and iteration limits can leave `allClean=false`; feed the result as `world_stats` to `sharp_critical_audit`.
    Ground checks sample the center and four inset bottom-face corners of the OBB's projected footprint, using the smallest signed gap to preserve end-supported bridges; no hits means void. `floatingCount` also includes sunk assets (`kind="embedded"`, negative signed `gapStuds`); grounding raises these assets rather than hiding penetration below the support surface.
23. `sharp_game_library` — Project plan, version snapshots/diffs/rollbacks, relative asset registry, and Studio `SharpAssetRegistry.luau` sync.
24. `sharp_playtest_scenario` — Automated server-side gameplay smoke-test bot runner.
25. `sharp_toolchain` — Offline `Rojo` `default.project.json`, `StyLua`, `Selene`, `Lune`, `Wally`, and `Rokit` orchestrator.
26. `sharp_inspect_snapshot_view` — Paged inspection (`offset`, `limit`, `json_path`) of cached large snapshots/outputs.
27. `sharp_upstream_call` — Optional forwarder when external `Roblox_Studio` MCP is explicitly configured.
28. `sharp_design_system` — Bespoke per-game palette/typography/UI-token generator (`presets`, `generate` with auto-persistence, `get`, anti-slop `lint`, `compile_theme_luau`, `image_prompts`, `render_swatch`).
29. `sharp_equipment_attach` — R15 weapon/armor/IK attachment compiler (`attach`, `verify`, `catalog`, `validate`, `load_sidecar`, `generate_preset_clip`, `analyze_clip`, `compile_playback_test`, `blender_attach`; enabled in `full` + `blender`).
30. `sharp_game_plan` — Concept intake & MVP-first structured game planner (`intake_questions`, `create` with `granularity='standard'|'micro'`, `status`, `next_step`, `subagent_brief`, `complete_step`, `stages`, `cut_list`, `set_design_system`).
31. `sharp_critical_audit` — Skeptical release auditor & stage gate (`static`, `live`, `challenge`, `gate`) including `WORLD-OVERLAP-001` & `WORLD-FLOAT-001`, returning `SHIP`/`FIX_FIRST`/`REJECT`.
32. `sharp_ai_studio` — External Gemini & OpenRouter credentials (`keys_status`, `keys_set`, `keys_clear`, `model_presets`), bespoke UI concept generator (`generate_ui_concept`), and palette-locked AI art generator (`generate_image_art`).
33. `sharp_media_qa` — Multimodal QA engine (`inspect_video` for playtest/animation video telemetry + contact sheet + Gemini/OpenRouter analysis, `inspect_audio` soundtest DSP + Gemini audio check, `inspect_gui_vision` anti-slop screenshot QA, and `batch_check`).
34. `sharp_art_studio` — Code-driven 2D/3D game art & VFX suite (`create_2d_kit` 2x SSAA 9-slice/icons, `create_font_kit` Roblox fonts + custom stroked BitmapFont + `SharpBitmapFont.luau`, `create_vfx` 4×4 flipbooks + `SharpUiVfx.luau`/`SharpWorldVfx.luau`, and `generate_ai_art`).

### Resources (`4` fixed + `1` template) & Prompts (`5`)
* **Fixed resources:** `sharp://skills/catalog`, `sharp://game-library/plan`, `sharp://game-library/manifest`, `sharp://game-library/registry-luau`
* **Resource template:** `sharp://skills/{skill_name}/SKILL.md`
* **Prompts:** `sharp_new_game_workflow`, `sharp_fix_gui_loop`, `sharp_concept_intake_workflow`, `sharp_mvp_build_loop`, `sharp_ui_antislop_pass`

---

## 4. Rebuilding Plugin & Running Tests

Luau compile regression tests run when `luau-compile` is on PATH or `LUAU_COMPILE` points to its executable; otherwise they skip. They syntax-check plugin/skill sources and representative generated Luau.

```powershell
# Rebuild SharpBridgePlugin.rbxmx (29 embedded --!strict ModuleScripts) & install to Studio Plugins
python -m sharp_mcp.cli install-plugin

# Run isolated automated unit, security, wrapper, registration, plugin, and stdio MCP E2E suite
python -m unittest discover -s tests -p "test_*.py" -v
```

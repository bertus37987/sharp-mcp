"""MVP-First Staged Game Planner & Gate Enforcement Engine for Sharp MCP."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from .critical_audit_engine import CriticalAuditEngine, _score_and_verdict
from ..project_library import ProjectLibraryManager


VERDICT_RANK: Dict[str, int] = {"SHIP": 0, "FIX_FIRST": 1, "REJECT": 2}
_ROBLOX_ASSET_ID_RE = re.compile(r"^(?:rbxassetid://)?[1-9]\d*$", re.IGNORECASE)


STAGE_ORDER: Tuple[str, ...] = ("S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7")
STEP_EXECUTION_ORDER: Tuple[str, ...] = (
    "S0.1",
    "S1.1",
    "S2.1",
    "S4.1",
    "S3.1",
    "S4.2",
    "S5.1",
    "S6.1",
    "S7.1",
)
MVP_REQUIRED_STEPS: Tuple[str, ...] = ("S0.1", "S1.1", "S2.1", "S4.1")
MICRO_STEP_EXECUTION_ORDER: Tuple[str, ...] = (
    "S0.1",
    "S1.1",
    "S2.1",
    "S2.2",
    "S2.3",
    "S4.1",
    "S3.1",
    "S4.2",
    "S5.1",
    "S6.1",
    "S7.1",
)
MICRO_MVP_REQUIRED_STEPS: Tuple[str, ...] = ("S0.1", "S1.1", "S2.1", "S2.2", "S2.3", "S4.1")
POST_MVP_LOCKED_STAGES: Tuple[str, ...] = ("S3", "S5", "S6", "S7")

V05_WORKFLOW_DIRECTIVES: Dict[str, Any] = {
    "tool_first": (
        "TOOL-FIRST: Always construct Luau contracts, terrain, GUI, animations, and 3D equipment via Sharp MCP domain tools "
        "(sharp_luau_scaffold, sharp_terrain_build, sharp_gui_build, sharp_rig_and_animation, sharp_equipment_attach, "
        "sharp_blender_asset_pipeline, sharp_art_studio, sharp_critical_audit) rather than ad-hoc raw execute_luau scripts."
    ),
    "style_guided": (
        "STYLE-GUIDED: Lock cohesive per-game style profiles from TEXTURE_STYLE_PROFILES "
        "(clean_vector_cel | stylized_gradient_atlas | pbr_metallic_roughness | pixel_retro_crisp | arcane_emissive_runes), "
        "ASSET_STYLE_PROFILES (lowpoly_flat_stylized | handpainted_fantasy_rpg | hard_surface_scifi_mecha | chibi_chunky_toon | dark_gothic_souls), "
        "and ANIMATION_STYLE_PROFILES (heavy_souls | snappy_anime | stylized_cartoony | tactical_military | floaty_arcane)."
    ),
    "anti_template": (
        "ANTI-TEMPLATE: Never ship boilerplate layouts, flat baseplates, or robotic lockstep motion. "
        "Use sharp_gui_build(mode='custom') with composable UIKit primitives (ArcGauge/RadialWheel/CardFan/BookSpread), "
        "custom_terrain_spec (crater/river/ridge/terrace/plateau height_layers + material_rules) + custom_atmosphere, "
        "and compose_custom with explicit windup hold -> action arc -> impact hit-stop -> recovery."
    ),
    "three_tier_art_pipeline": {
        "tier_1_procedural_2d_pbr": "sharp_design_system(TEXTURE_STYLE_PROFILES, ASSET_STYLE_PROFILES) + sharp_art_studio(create_pbr_texture_set, create_custom_font_kit, create_custom_vfx) + sharp_gui_slice_and_pack",
        "tier_2_bespoke_3d_blender": "sharp_blender_asset_pipeline(custom_bmesh with 4 PBR slots, .fbx/.glb, _attachments.json, preview.png) + sharp_equipment_attach(inspect_attachment_fit)",
        "tier_3_ai_media_polish": "sharp_ai_studio (optional AI concept/texture art when keys configured) + sharp_media_qa (Vision/Video/Audio QA)",
    },
    "mandatory_vision_verification": (
        "MANDATORY VISION-VERIFICATION: Never accept JSON pass metrics without rendered visual inspection. "
        "Animations require pose_strip / pose_at_time + screen_capture; 3D attachments require inspect_attachment_fit + preview.png/viewport check; "
        "GUIs require multi-device capture + sharp_media_qa(inspect_gui_vision) + sharp_visual_diff; "
        "multi-script systems require SystemContracts + verify_contracts + pcall(require) smoke test."
    ),
    "style_profiles": {
        "TEXTURE_STYLE_PROFILES": [
            "clean_vector_cel",
            "stylized_gradient_atlas",
            "pbr_metallic_roughness",
            "pixel_retro_crisp",
            "arcane_emissive_runes",
        ],
        "ASSET_STYLE_PROFILES": [
            "lowpoly_flat_stylized",
            "handpainted_fantasy_rpg",
            "hard_surface_scifi_mecha",
            "chibi_chunky_toon",
            "dark_gothic_souls",
        ],
        "ANIMATION_STYLE_PROFILES": [
            "heavy_souls",
            "snappy_anime",
            "stylized_cartoony",
            "tactical_military",
            "floaty_arcane",
        ],
    },
}

STEP_SUBAGENT_ROLES: Dict[str, Dict[str, Any]] = {
    "S0.1": {
        "role": "Roblox Security, Architecture & SystemContracts Sub-Agent",
        "skills": ["roblox-luau-coding"],
        "tools": ["sharp_luau_scaffold", "sharp_critical_audit", "sharp_game_library"],
        "verification": (
            "Install ReplicatedStorage.Shared.SystemContracts + SafeRemoteGateway, run pcall(require) smoke test, "
            "and pass sharp_critical_audit(mode='static', verify_contracts=True) with 0 BLOCKER/CRITICAL."
        ),
        "directives": ["tool_first", "mandatory_vision_verification"],
    },
    "S1.1": {
        "role": "Custom Terrain, Atmosphere & Overlap QA Sub-Agent",
        "skills": ["roblox-terrain-atmosphere", "roblox-world-assembly-and-optimization"],
        "tools": ["sharp_terrain_build", "sharp_environment_apply", "sharp_world_assembly_and_optimization", "sharp_critical_audit"],
        "verification": (
            "Sculpt bespoke world with custom_terrain_spec (height_layers + material_rules) and custom_atmosphere, "
            "verify SpawnLocation >= 1, run audit_overlaps (`overlapCount == 0`), and visually capture terrain framing."
        ),
        "directives": ["tool_first", "anti_template", "mandatory_vision_verification"],
    },
    "S2.1": {
        "role": "Micro-Slice Combat/Action #1 Sub-Agent (compose_custom + Pose-Strip QA)",
        "skills": ["roblox-animation", "roblox-combat-and-controllers"],
        "tools": ["sharp_rig_and_animation", "sharp_equipment_attach", "sharp_combat_and_controllers", "sharp_media_qa"],
        "verification": (
            "Author single primary action using ANIMATION_STYLE_PROFILES + compose_custom (windup hold -> arc -> hit-stop -> recovery), "
            "verify analyze_clip >= 85, and visually verify pose_strip via screen_capture + sharp_media_qa."
        ),
        "directives": ["tool_first", "style_guided", "anti_template", "mandatory_vision_verification"],
    },
    "S2.2": {
        "role": "Micro-Slice Guard/Counter #2 Sub-Agent (Second Action Only)",
        "skills": ["roblox-animation", "roblox-combat-and-controllers"],
        "tools": ["sharp_rig_and_animation", "sharp_equipment_attach", "sharp_combat_and_controllers", "sharp_media_qa"],
        "verification": (
            "Author guard/counter clip via ANIMATION_STYLE_PROFILES + compose_custom with foot slide <= 0.1, "
            "and visually inspect pose_strip + Studio playtest video."
        ),
        "directives": ["tool_first", "style_guided", "anti_template", "mandatory_vision_verification"],
    },
    "S2.3": {
        "role": "Micro-Slice Target, Contracts & Soundtest QA Sub-Agent",
        "skills": ["roblox-ai-and-gameplay-systems", "roblox-audio-vfx-cutscenes"],
        "tools": ["sharp_playtest_scenario", "sharp_art_studio", "sharp_critical_audit", "sharp_media_qa"],
        "verification": (
            "Run verify_contracts across Server/Client/Shared scripts + pcall(require) smoke test, "
            "and pass full_slice_bot + sharp_media_qa(mode='inspect_audio'/'inspect_video')."
        ),
        "directives": ["tool_first", "mandatory_vision_verification"],
    },
    "S3.1": {
        "role": "3D Asset, Custom BMesh & Equipment Fit Sub-Agent",
        "skills": ["roblox-animation", "blender-game-assets", "blender-character-rigging"],
        "tools": ["sharp_blender_asset_pipeline", "sharp_equipment_attach", "sharp_rig_and_animation", "sharp_game_library", "sharp_media_qa"],
        "verification": (
            "Build Tier-2 hero equipment with custom_bmesh (ASSET_STYLE_PROFILES + TEXTURE_STYLE_PROFILES, <10k tris, _attachments.json, preview.png), "
            "verify rest + raised-arm clearance via inspect_attachment_fit, and confirm pose_strip + analyze_clip >= 85."
        ),
        "directives": ["tool_first", "style_guided", "three_tier_art_pipeline", "mandatory_vision_verification"],
    },
    "S4.1": {
        "role": "Game-Specific 2D Art, Style Profiles & Custom MVP HUD Sub-Agent",
        "skills": ["roblox-gui"],
        "tools": ["sharp_design_system", "sharp_art_studio", "sharp_gui_build", "sharp_media_qa"],
        "verification": (
            "Generate cohesive TEXTURE_STYLE_PROFILES + ASSET_STYLE_PROFILES design_system + Tier-1 PBR/font/VFX kit, "
            "author bespoke non-template HUD via sharp_gui_build(mode='custom'), and pass sharp_visual_diff + inspect_gui_vision."
        ),
        "directives": ["tool_first", "style_guided", "anti_template", "three_tier_art_pipeline", "mandatory_vision_verification"],
    },
    "S4.2": {
        "role": "Full Custom Menus, Art Pipeline & Multi-Device Vision QA Sub-Agent",
        "skills": ["roblox-gui"],
        "tools": ["sharp_art_studio", "sharp_gui_slice_and_pack", "sharp_gui_build", "sharp_gui_inspect", "sharp_media_qa"],
        "verification": (
            "Build custom paradigm menus via sharp_gui_build(mode='custom') + Tier-1/Tier-3 assets, "
            "verify desktop + mobile safe zones, <= 6 CanvasGroups, and Gemini Vision inspect_gui_vision SHIP/FIX_FIRST."
        ),
        "directives": ["tool_first", "style_guided", "anti_template", "three_tier_art_pipeline", "mandatory_vision_verification"],
    },
    "S5.1": {
        "role": "Economy, DataStore & SystemContracts Security Sub-Agent",
        "skills": ["roblox-data-economy-monetization", "roblox-luau-coding"],
        "tools": ["sharp_data_economy_monetization", "sharp_critical_audit"],
        "verification": (
            "Verify UpdateAsync session locking, BindToClose flush, idempotent ProcessReceipt, "
            "and sharp_critical_audit(verify_contracts=True) with zero CONTRACT-* or SEC-* defects."
        ),
        "directives": ["tool_first", "mandatory_vision_verification"],
    },
    "S6.1": {
        "role": "Audio/VFX/Polish & PBR Texture Sub-Agent",
        "skills": ["roblox-audio-vfx-cutscenes"],
        "tools": ["sharp_audio_vfx_cutscenes", "sharp_art_studio", "sharp_media_qa"],
        "verification": "Run sharp_media_qa soundtest + video QA, verify Highlight pool <= 31 and PBR texture/VFX coherence.",
        "directives": ["tool_first", "style_guided", "three_tier_art_pipeline", "mandatory_vision_verification"],
    },
    "S7.1": {
        "role": "Final Release, Cross-Script Contracts & Challenge Gate Sub-Agent",
        "skills": ["roblox-luau-coding", "roblox-gui", "roblox-world-assembly-and-optimization"],
        "tools": ["sharp_world_assembly_and_optimization", "sharp_media_qa", "sharp_critical_audit", "sharp_playtest_scenario"],
        "verification": (
            "Pass verify_contracts + pcall(require) smoke test, audit_overlaps (`overlapCount == 0`), "
            "100-player/phone/rejoin challenge probe, video/vision review, and final SHIP gate."
        ),
        "directives": ["tool_first", "mandatory_vision_verification"],
    },
}


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (text or "game").strip()).strip("_").lower()
    return cleaned or "game"


def _normalize_platforms(platforms: Optional[List[str] | str]) -> List[str]:
    if not platforms:
        return ["Desktop", "Mobile", "Console"]
    if isinstance(platforms, str):
        parts = [p.strip() for p in re.split(r"[,;/]+", platforms) if p.strip()]
        return parts or ["Desktop", "Mobile"]
    return [str(p).strip() for p in platforms if str(p).strip()] or ["Desktop", "Mobile"]


class GamePlanner:
    """Enforces MVP-first game planning, dependency DAGs, single-step pacing, and strict stage gates."""

    def __init__(
        self,
        project_library: ProjectLibraryManager,
        audit_engine: Optional[CriticalAuditEngine] = None,
    ) -> None:
        self.project_library = project_library
        self.audit_engine = audit_engine or CriticalAuditEngine(project_library=project_library)

    # ------------------------------------------------------------------
    # Plan Generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_stage_definitions(
        title: str,
        genre: str,
        platforms: List[str],
        *,
        granularity: str = "standard",
    ) -> List[Dict[str, Any]]:
        has_mobile = any("mobile" in p.lower() or "phone" in p.lower() for p in platforms)
        is_micro = (granularity or "standard").strip().lower() == "micro"

        if is_micro:
            s2_steps = [
                {
                    "step_id": "S2.1",
                    "stage_id": "S2",
                    "phase": "mvp",
                    "title": "Micro-Slice #1: Single primary attack animation (clip score >= 85) + 1 server hitbox, visually/video verified",
                    "tool": "sharp_equipment_attach",
                    "target_domain": "core_loop_attack",
                    "args_template": {"action": "generate_preset_clip", "preset_name": "sword_combo_3hit", "fps": 30},
                    "completed": False,
                    "completed_at": None,
                    "gate": {
                        "requires_audit": True,
                        "max_blocker": 0,
                        "max_critical": 0,
                        "max_major": 2,
                        "min_score": 70,
                        "required_verdicts": ["SHIP", "FIX_FIRST"],
                        "requires_playtest": False,
                        "requires_asset": False,
                        "requires_design_system": False,
                        "requires_spawn_bounds": False,
                        "requires_snapshot": True,
                    },
                },
                {
                    "step_id": "S2.2",
                    "stage_id": "S2",
                    "phase": "mvp",
                    "title": "Micro-Slice #2: Single block/guard stance (foot slide <= 0.1) + guard mitigation, tested before adding combos",
                    "tool": "sharp_equipment_attach",
                    "target_domain": "core_loop_block",
                    "args_template": {"action": "generate_preset_clip", "preset_name": "shield_block", "fps": 30},
                    "completed": False,
                    "completed_at": None,
                    "gate": {
                        "requires_audit": True,
                        "max_blocker": 0,
                        "max_critical": 0,
                        "max_major": 2,
                        "min_score": 70,
                        "required_verdicts": ["SHIP", "FIX_FIRST"],
                        "requires_playtest": False,
                        "requires_asset": False,
                        "requires_design_system": False,
                        "requires_spawn_bounds": False,
                        "requires_snapshot": True,
                    },
                },
                {
                    "step_id": "S2.3",
                    "stage_id": "S2",
                    "phase": "mvp",
                    "title": "Micro-Slice #3: Single target dummy + hit VFX/SFX + automated playtest & soundtest/video QA",
                    "tool": "sharp_playtest_scenario",
                    "target_domain": "core_loop",
                    "args_template": {"scenario": "full_slice_bot", "cleanup_after": True, "execute_in_studio": True},
                    "completed": False,
                    "completed_at": None,
                    "gate": {
                        "requires_audit": True,
                        "max_blocker": 0,
                        "max_critical": 0,
                        "max_major": 2,
                        "min_score": 70,
                        "required_verdicts": ["SHIP", "FIX_FIRST"],
                        "requires_playtest": True,
                        "requires_asset": False,
                        "requires_design_system": False,
                        "requires_spawn_bounds": False,
                        "requires_snapshot": True,
                    },
                },
            ]
        else:
            s2_steps = [
                {
                    "step_id": "S2.1",
                    "stage_id": "S2",
                    "phase": "mvp",
                    "title": "Implement single core playable loop and pass automated playtest bot",
                    "tool": "sharp_playtest_scenario",
                    "target_domain": "core_loop",
                    "args_template": {"scenario": "full_slice_bot", "cleanup_after": True, "execute_in_studio": True},
                    "completed": False,
                    "completed_at": None,
                    "gate": {
                        "requires_audit": True,
                        "max_blocker": 0,
                        "max_critical": 0,
                        "max_major": 2,
                        "min_score": 70,
                        "required_verdicts": ["SHIP", "FIX_FIRST"],
                        "requires_playtest": True,
                        "requires_asset": False,
                        "requires_design_system": False,
                        "requires_spawn_bounds": False,
                        "requires_snapshot": True,
                    },
                }
            ]

        return [
            {
                "stage_id": "S0",
                "name": "Foundation",
                "phase": "mvp",
                "status": "unlocked",
                "entry_gate": ["Structured plan.json created"],
                "exit_gate": [
                    "Canonical Explorer containers applied",
                    "SafeRemoteGateway schema + rate limit installed",
                    "Critical audit 0 BLOCKER / 0 CRITICAL",
                    "Version snapshot persisted",
                ],
                "acceptance_criteria": [
                    "ServerScriptService holds executable scripts; ServerStorage holds none",
                    "All new Luau modules begin with --!strict",
                    "Every RemoteEvent uses SafeRemoteGateway schema + token-bucket rate limit",
                ],
                "steps": [
                    {
                        "step_id": "S0.1",
                        "stage_id": "S0",
                        "phase": "mvp",
                        "title": "Scaffold Explorer containers, SafeRemoteGateway, and pass foundation security audit",
                        "tool": "sharp_luau_scaffold",
                        "target_domain": "luau_foundation",
                        "args_template": {"action": "apply", "install_safe_remote_gateway": True, "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 2,
                            "min_score": 70,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": False,
                            "requires_design_system": False,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
            {
                "stage_id": "S1",
                "name": "Greybox World",
                "phase": "mvp",
                "status": "locked",
                "entry_gate": ["S0.1 completed and audited"],
                "exit_gate": [
                    "Greybox playable terrain/bounds created",
                    "SpawnLocation verified above terrain",
                    "Environment + world critical audit clean",
                ],
                "acceptance_criteria": [
                    "At least 1 SpawnLocation placed inside playable bounds",
                    "Static world parts anchored; StreamingEnabled configured appropriately",
                ],
                "steps": [
                    {
                        "step_id": "S1.1",
                        "stage_id": "S1",
                        "phase": "mvp",
                        "title": "Build greybox terrain, playable bounds, and verified SpawnLocation",
                        "tool": "sharp_terrain_build",
                        "target_domain": "terrain_atmosphere",
                        "args_template": {"biome_preset": "RollingHills", "create_spawn_pad": True, "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 2,
                            "min_score": 70,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": False,
                            "requires_design_system": False,
                            "requires_spawn_bounds": True,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
            {
                "stage_id": "S2",
                "name": "Core Loop Vertical Slice",
                "phase": "mvp",
                "status": "locked",
                "entry_gate": ["S1.1 greybox world green"],
                "exit_gate": [
                    "Single playable loop implemented end-to-end",
                    "Automated playtest bot passes full_slice_bot",
                    "Critical audit 0 BLOCKER / 0 CRITICAL",
                ],
                "acceptance_criteria": [
                    f"Players can enter '{title}', trigger the single {genre} loop, win/lose, and reset cleanly",
                    "sharp_playtest_scenario(scenario='full_slice_bot') passes with zero errors",
                ],
                "steps": s2_steps,
            },
            {
                "stage_id": "S3",
                "name": "Characters, Animation & Equipment",
                "phase": "post_mvp",
                "status": "locked",
                "entry_gate": ["MVP-first lock cleared: S0.1, S1.1, S2.1, and minimal S4.1 HUD green & audited"],
                "exit_gate": [
                    "Character/equipment attachments + animations use Animator:LoadAnimation",
                    "Rig/animation/mesh assets registered in ProjectLibraryManager",
                    "Animation loop seam & priority audit clean",
                ],
                "acceptance_criteria": [
                    "Zero Humanoid:LoadAnimation usage; AnimationTracks cached and cleaned up",
                    "R15 attachments/Motor6Ds verified without scale mismatch or physics collisions",
                ],
                "steps": [
                    {
                        "step_id": "S3.1",
                        "stage_id": "S3",
                        "phase": "post_mvp",
                        "title": "Attach R15 equipment, compile non-robotic animations, and register rig/anim assets",
                        "tool": "sharp_equipment_attach",
                        "target_domain": "characters_animation",
                        "args_template": {"action": "attach", "mode": "motor6d_weapon", "slot": "RightHand", "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 2,
                            "min_score": 75,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": True,
                            "required_asset_categories": ["rig", "animation", "mesh"],
                            "requires_design_system": False,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
            {
                "stage_id": "S4",
                "name": "GUI & HUD with Design System",
                "phase": "mvp_and_post_mvp",
                "status": "locked",
                "entry_gate": ["S2.1 vertical slice green for S4.1 minimal HUD; S3.1 green for S4.2 full UI"],
                "exit_gate": [
                    "Per-game unique design_system saved on project",
                    "Anti-slop lint + >=44px touch + WCAG contrast + SafeInsets clean",
                    "GUI assets registered & multi-device visual diff verified",
                ],
                "acceptance_criteria": [
                    "ScreenInsets=CoreUISafeInsets/DeviceSafeInsets, ZIndexBehavior=Sibling, unique DisplayOrder",
                    "Touch targets >=44x44px" + (" and clear of mobile thumbstick/jump zones" if has_mobile else ""),
                    "Text contrast >=4.5:1, UITextSizeConstraint on TextScaled, CanvasGroups <= 6",
                ],
                "steps": [
                    {
                        "step_id": "S4.1",
                        "stage_id": "S4",
                        "phase": "mvp",
                        "title": "Generate unique per-game design palette and build minimal MVP HUD (completes MVP gate)",
                        "tool": "sharp_design_system",
                        "target_domain": "gui_mvp_hud",
                        "args_template": {"action": "generate", "game_title": title, "genre": genre, "save_to_project": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 2,
                            "min_score": 75,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": False,
                            "requires_design_system": True,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    },
                    {
                        "step_id": "S4.2",
                        "stage_id": "S4",
                        "phase": "post_mvp",
                        "title": "Build full design-system modals/menus, register GUI assets, and verify responsive layout",
                        "tool": "sharp_gui_build",
                        "target_domain": "gui",
                        "args_template": {"run_audit_after": True, "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 1,
                            "min_score": 80,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": True,
                            "required_asset_categories": ["gui_9slice", "gui_atlas", "texture", "script_module"],
                            "requires_design_system": True,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    },
                ],
            },
            {
                "stage_id": "S5",
                "name": "Economy & Persistence",
                "phase": "post_mvp",
                "status": "locked",
                "entry_gate": ["MVP unlocked + S3.1 & S4.2 green"],
                "exit_gate": [
                    "Session-locked DataStore with pcall + BindToClose flush",
                    "Idempotent ProcessReceipt deduplicating PurchaseId",
                    "Economy critical audit 0 BLOCKER / 0 CRITICAL",
                ],
                "acceptance_criteria": [
                    "Server-authoritative currency/inventory ledger; client never dictates prices or rewards",
                    "UpdateAsync session lock prevents item dupes across rejoin/server-hop",
                ],
                "steps": [
                    {
                        "step_id": "S5.1",
                        "stage_id": "S5",
                        "phase": "post_mvp",
                        "title": "Install session-locked DataStore, server economy ledger, and idempotent ProcessReceipt",
                        "tool": "sharp_data_economy_monetization",
                        "target_domain": "economy_data",
                        "args_template": {"install_datastore": True, "install_receipt_handler": True, "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 1,
                            "min_score": 80,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": False,
                            "requires_design_system": False,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
            {
                "stage_id": "S6",
                "name": "Polish, Audio & VFX",
                "phase": "post_mvp",
                "status": "locked",
                "entry_gate": ["S5.1 economy & data green"],
                "exit_gate": [
                    "Node-based Audio Wiring buses & spatial emitters installed",
                    "Pooled ParticleEmitters & <=31-cap Highlights verified",
                    "Audio/VFX assets registered & budget audit clean",
                ],
                "acceptance_criteria": [
                    "Zero unbounded Instance.new in loops or Debris abuse; audio/VFX respect asset budget",
                    "Lighting/Atmosphere/PostEffects verified without washing out UI readability",
                ],
                "steps": [
                    {
                        "step_id": "S6.1",
                        "stage_id": "S6",
                        "phase": "post_mvp",
                        "title": "Install Audio Wiring graph, pooled VFX/Highlights, and register audio/VFX assets",
                        "tool": "sharp_audio_vfx_cutscenes",
                        "target_domain": "polish_audio_vfx",
                        "args_template": {"install_audio_graph": True, "install_vfx_pool": True, "execute_in_studio": True},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 1,
                            "min_score": 80,
                            "required_verdicts": ["SHIP", "FIX_FIRST"],
                            "requires_playtest": False,
                            "requires_asset": True,
                            "required_asset_categories": ["sfx", "audio", "script_module", "texture"],
                            "requires_design_system": False,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
            {
                "stage_id": "S7",
                "name": "Release-Hardening",
                "phase": "post_mvp",
                "status": "locked",
                "entry_gate": ["S0..S6 all completed and audited"],
                "exit_gate": [
                    "Critical audit verdict == SHIP (0 BLOCKER, 0 CRITICAL, 0 MAJOR, score >= 85)",
                    "Challenge mode (100 players / phone / after rejoin) risks resolved",
                    "Playtest regression passed & final release version snapshot recorded",
                ],
                "acceptance_criteria": [
                    "sharp_critical_audit(mode='gate', stage_id='S7') returns gate_passed=True and verdict='SHIP'",
                    "Zero unresolved cross-check gaps between plan.json, game_state.json, and asset_manifest.json",
                ],
                "steps": [
                    {
                        "step_id": "S7.1",
                        "stage_id": "S7",
                        "phase": "post_mvp",
                        "title": "Pass release-hardening SHIP gate, challenge audit, and regression playtest",
                        "tool": "sharp_critical_audit",
                        "target_domain": "release_hardening",
                        "args_template": {"mode": "gate", "stage_id": "S7", "step_id": "S7.1"},
                        "completed": False,
                        "completed_at": None,
                        "gate": {
                            "requires_audit": True,
                            "max_blocker": 0,
                            "max_critical": 0,
                            "max_major": 0,
                            "min_score": 85,
                            "required_verdicts": ["SHIP"],
                            "requires_playtest": True,
                            "requires_asset": False,
                            "requires_design_system": False,
                            "requires_spawn_bounds": False,
                            "requires_snapshot": True,
                        },
                    }
                ],
            },
        ]

    def create_plan(
        self,
        title: str,
        genre: str = "Action RPG",
        pitch: str = "",
        audience: str = "Ages 13+ Roblox players",
        session_length_min: int | float = 12,
        monetization: str | Dict[str, Any] = "Cosmetics + Fair GamePasses",
        platforms: Optional[List[str] | str] = None,
        *,
        design_system: Optional[Dict[str, Any]] = None,
        granularity: str = "standard",
    ) -> Dict[str, Any]:
        """Create and persist a strict MVP-first structured game plan (`plan.json`, `GAME_PLAN.md`, `game_state.json`, snapshot)."""
        clean_title = (title or "").strip()
        if not clean_title:
            return {"ok": False, "error": "title is required to create a game plan."}

        try:
            session_mins = float(session_length_min)
        except (TypeError, ValueError):
            return {"ok": False, "error": "session_length_min must be a positive number."}
        if session_mins <= 0:
            return {"ok": False, "error": "session_length_min must be greater than 0."}

        norm_genre = (genre or "Action").strip()
        norm_pitch = (pitch or f"Focused {norm_genre} vertical slice built around one tight repeatable loop.").strip()
        norm_audience = (audience or "Ages 13+ Roblox players").strip()
        norm_platforms = _normalize_platforms(platforms)
        has_mobile = any("mobile" in p.lower() or "phone" in p.lower() for p in norm_platforms)
        norm_gran = "micro" if (granularity or "").strip().lower() == "micro" else "standard"
        step_order = list(MICRO_STEP_EXECUTION_ORDER if norm_gran == "micro" else STEP_EXECUTION_ORDER)
        mvp_required = list(MICRO_MVP_REQUIRED_STEPS if norm_gran == "micro" else MVP_REQUIRED_STEPS)

        existing_ds = design_system if isinstance(design_system, dict) else self.project_library.get_design_system()
        stages = self._build_stage_definitions(
            clean_title,
            norm_genre,
            norm_platforms,
            granularity=norm_gran,
        )

        pillars = [
            f"Single-Loop Mastery: Every mechanic serves '{clean_title}'s core {norm_genre} loop within {int(round(session_mins))}-minute sessions.",
            f"Zero-Trust Server Authority: All combat, progression, and {monetization} transactions execute server-side behind SafeRemoteGateway.",
            f"Distinct Visual Identity: Bespoke per-game design palette and glossy readable UI tailored for {', '.join(norm_platforms)}.",
            "MVP-First Discipline: S0-S2 and minimal S4 HUD pass automated playtest & critical audit before expanding scope.",
        ]

        cycle_sec = max(45, min(300, int(session_mins * 12)))
        core_loop = {
            "summary": f"Enter arena/world -> Trigger {norm_genre} objective -> Overcome primary obstacle/enemy -> Earn single MVP reward -> Spend/upgrade & replay",
            "steps": [
                f"1. Deploy into '{clean_title}' greybox hub with clear objective beacon and minimal HUD counter.",
                f"2. Engage the ONE core {norm_genre} action/challenge loop (~{cycle_sec}s per cycle).",
                "3. Resolve risk/fail state or complete objective via server-authoritative validation.",
                "4. Grant primary loop reward + update minimal HUD feedback, then offer instant replay.",
            ],
            "target_cycle_seconds": cycle_sec,
            "session_length_min": session_mins,
        }

        mvp_scope = {
            "single_playable_loop": f"One complete repeatable {norm_genre} run from Spawn -> Objective/Encounter -> Victory/Fail -> Replay",
            "in_scope_mvp_systems": [
                "luau_foundation (Explorer scaffold + SafeRemoteGateway)",
                "terrain_atmosphere (1 playable greybox zone + SpawnLocation + bounds)",
                "core_loop (1 primary gameplay loop + automated playtest bot)",
                "gui_mvp_hud (minimal HUD with design_system palette + safe touch zones)",
            ],
            "explicitly_excluded_from_mvp": [
                "Multiple maps, biomes, or open-world side quests",
                "Crafting trees, trading, clans/guilds, battle pass, or multi-currency shops",
                "Custom boss phases, cutscenes, or multi-slot cosmetic loadouts",
            ],
            "vertical_slice_target": f"Playable end-to-end {norm_genre} slice passing full_slice_bot and critical audit with 0 BLOCKER/CRITICAL.",
        }

        cut_list = [
            {
                "id": "CUT-01",
                "feature": "Secondary maps, dungeons, and procedural biome rotation",
                "reason_cut": "Dilutes vertical slice focus; validate ONE playable loop before adding content breadth.",
                "target_stage": "post_mvp_v2",
            },
            {
                "id": "CUT-02",
                "feature": "Player-to-player trading and auction house",
                "reason_cut": "High dupe/exploit surface requiring multi-server escrow; defer until S5 economy passes.",
                "target_stage": "post_mvp_v2",
            },
            {
                "id": "CUT-03",
                "feature": "Clans, leaderboards across universes, and seasonal battle pass",
                "reason_cut": "Retention meta-layers add zero value before the 12-minute core loop is fun.",
                "target_stage": "post_mvp_v3",
            },
            {
                "id": "CUT-04",
                "feature": "Cinematic multi-camera cutscenes and secondary weapon variants",
                "reason_cut": "Polish & content multiplication belong strictly in S3/S6 after MVP gates are green.",
                "target_stage": "S6",
            },
        ]

        systems_dag = [
            {
                "id": "luau_foundation",
                "name": "Explorer Scaffold & SafeRemoteGateway",
                "stage": "S0",
                "depends_on": [],
                "tool": "sharp_luau_scaffold",
                "system_domains": ["luau_foundation", "luau_scaffold"],
                "code_keywords": ["SafeRemoteGateway", "ReplicatedStorage"],
            },
            {
                "id": "terrain_atmosphere",
                "name": "Greybox World, Spawn & Playable Bounds",
                "stage": "S1",
                "depends_on": ["luau_foundation"],
                "tool": "sharp_terrain_build",
                "system_domains": ["terrain_atmosphere", "environment"],
                "code_keywords": ["SpawnLocation", "Terrain"],
            },
            {
                "id": "core_loop",
                "name": "Single Core Loop & Playtest Harness",
                "stage": "S2",
                "depends_on": ["luau_foundation", "terrain_atmosphere"],
                "tool": "sharp_playtest_scenario",
                "system_domains": ["core_loop", "ai_gameplay_systems", "combat_controllers", "playtest"],
                "code_keywords": ["Round", "Loop", "Playtest"],
            },
            {
                "id": "gui_mvp_hud",
                "name": "Minimal MVP HUD & Unique Design System",
                "stage": "S4",
                "depends_on": ["core_loop"],
                "tool": "sharp_design_system",
                "system_domains": ["gui_mvp_hud", "design_system", "gui"],
                "code_keywords": ["ScreenGui", "ScreenInsets"],
            },
            {
                "id": "characters_animation",
                "name": "R15 Equipment Attachments & Animator Clips",
                "stage": "S3",
                "depends_on": ["gui_mvp_hud"],
                "tool": "sharp_equipment_attach",
                "system_domains": ["characters_animation", "rig_animation", "equipment_attach"],
                "code_keywords": ["Animator", "RigidConstraint", "Motor6D"],
            },
            {
                "id": "gui_full",
                "name": "Full Design-System Modals & Multi-Device UI",
                "stage": "S4",
                "depends_on": ["gui_mvp_hud", "characters_animation"],
                "tool": "sharp_gui_build",
                "system_domains": ["gui"],
                "code_keywords": ["StyleRule", "UITextSizeConstraint"],
            },
            {
                "id": "economy_data",
                "name": "Session-Locked DataStore & Idempotent ProcessReceipt",
                "stage": "S5",
                "depends_on": ["gui_full"],
                "tool": "sharp_data_economy_monetization",
                "system_domains": ["economy_data", "data_economy_monetization"],
                "code_keywords": ["UpdateAsync", "BindToClose", "ProcessReceipt"],
            },
            {
                "id": "polish_audio_vfx",
                "name": "Spatial Audio Wiring & Pooled VFX",
                "stage": "S6",
                "depends_on": ["economy_data"],
                "tool": "sharp_audio_vfx_cutscenes",
                "system_domains": ["polish_audio_vfx", "audio_vfx_cutscenes"],
                "code_keywords": ["AudioPlayer", "ParticleEmitter"],
            },
            {
                "id": "release_hardening",
                "name": "Release-Hardening Gate & Challenge Audit",
                "stage": "S7",
                "depends_on": ["polish_audio_vfx"],
                "tool": "sharp_critical_audit",
                "system_domains": ["release_hardening"],
                "code_keywords": [],
            },
        ]

        risk_register = [
            {
                "id": "RISK-01",
                "risk": "Client-trusted RemoteEvents or unthrottled spam at 100 concurrent players",
                "severity": "BLOCKER",
                "likelihood": "High",
                "owner_stage": "S0",
                "mitigation": "Mandate SafeRemoteGateway schema + per-player token buckets on every RemoteEvent.",
            },
            {
                "id": "RISK-02",
                "risk": "Mobile touch controls <44px or occluded by virtual thumbstick/jump button" if has_mobile else "Responsive UI clipping across aspect ratios",
                "severity": "CRITICAL",
                "likelihood": "High",
                "owner_stage": "S4",
                "mitigation": "Enforce ScreenInsets, >=44x44 touch targets, UITextSizeConstraint, and mobile deviceSim visual diff.",
            },
            {
                "id": "RISK-03",
                "risk": "DataStore dupe or purchase loss from non-idempotent ProcessReceipt / missing BindToClose",
                "severity": "BLOCKER",
                "likelihood": "Medium",
                "owner_stage": "S5",
                "mitigation": "Use UpdateAsync session locks, BindToClose flush, and PurchaseId deduplication.",
            },
            {
                "id": "RISK-04",
                "risk": "StreamingEnabled nil-dereference & connection leaks across respawns/rejoins",
                "severity": "CRITICAL",
                "likelihood": "Medium",
                "owner_stage": "S2",
                "mitigation": "Guard streamed references with timeouts/nil checks and clean per-player connections via Maid/PlayerRemoving.",
            },
            {
                "id": "RISK-05",
                "risk": "Feature sprawl delaying playable vertical slice",
                "severity": "MAJOR",
                "likelihood": "High",
                "owner_stage": "S2",
                "mitigation": "Enforce hard MVP-first lock: S3/S5/S6 remain locked until S0-S2 + S4.1 HUD pass audit.",
            },
        ]

        asset_budget = {
            "max_workspace_parts": 8000 if has_mobile else 15000,
            "max_triangles_hero_prop": 6000,
            "max_triangles_character": 12000,
            "max_canvas_groups": 6,
            "max_texture_resolution": 1024 if has_mobile else 2048,
            "max_concurrent_particle_emitters": 24 if has_mobile else 48,
            "max_audio_voices": 24,
            "required_assets": [
                {"stage": "S3", "categories": ["rig", "animation", "mesh"], "description": "Primary R15 rig / attachment mesh / KeyframeSequence"},
                {"stage": "S4", "categories": ["gui_9slice", "gui_atlas", "texture", "script_module"], "description": "9-slice panel/button, UI atlas, or StyleSheet module"},
                {"stage": "S6", "categories": ["sfx", "audio", "script_module", "texture"], "description": "Core action SFX, spatial audio, or VFX texture asset"},
            ],
        }

        acceptance_criteria = {st["stage_id"]: st["acceptance_criteria"] for st in stages}
        plan_data: Dict[str, Any] = {
            "schema_version": 2,
            "granularity": norm_gran,
            "step_execution_order": step_order,
            "mvp_required_steps": mvp_required,
            "plan_id": f"{_slugify(clean_title)}_v1",
            "title": clean_title,
            "genre": norm_genre,
            "pitch": norm_pitch,
            "audience": norm_audience,
            "session_length_min": session_mins,
            "monetization": monetization,
            "platforms": norm_platforms,
            "pillars": pillars,
            "core_loop": core_loop,
            "mvp_scope": mvp_scope,
            "cut_list": cut_list,
            "systems_dependency_dag": systems_dag,
            "risk_register": risk_register,
            "design_system": existing_ds,
            "asset_budget": asset_budget,
            "acceptance_criteria": acceptance_criteria,
            "stages": stages,
        }

        planned_milestones = [
            f"[{step_id}] {self._find_step_in_stages(stages, step_id)['title']}"
            for step_id in step_order
            if self._find_step_in_stages(stages, step_id) is not None
        ]
        state_updates = {
            "current_stage": "S0",
            "mvp_unlocked": False,
            "planner_stages": copy.deepcopy(stages),
            "planned_milestones": planned_milestones,
            "completed_milestones": [],
        }
        save_res = self.project_library.save_plan(
            plan_data,
            state_updates=state_updates,
            snapshot_summary=f"Created MVP-first structured game plan for '{clean_title}' ({norm_genre})",
            tool_name="sharp_game_plan",
            target_domain="game_plan",
        )
        return {
            "ok": True,
            "plan_id": plan_data["plan_id"],
            "title": clean_title,
            "current_stage": "S0",
            "mvp_unlocked": False,
            "plan_json_path": save_res["plan_json_path"],
            "plan_md_path": save_res["plan_md_path"],
            "snapshot": save_res["snapshot"],
            "plan": plan_data,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_step_in_stages(stages: Sequence[Dict[str, Any]], step_id: str) -> Optional[Dict[str, Any]]:
        for st in stages:
            for step in st.get("steps") or []:
                if step.get("step_id") == step_id:
                    return step
        return None

    def _load_plan_and_stages(self) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any], List[Dict[str, Any]]]:
        plan = self.project_library.load_plan()
        state = self.project_library.load_state()
        stages = state.get("planner_stages") or (plan.get("stages") if isinstance(plan, dict) else None) or []
        return plan, state, stages

    @staticmethod
    def _completed_step_ids(stages: Sequence[Dict[str, Any]]) -> Set[str]:
        done: Set[str] = set()
        for st in stages:
            for step in st.get("steps") or []:
                if step.get("completed"):
                    done.add(str(step.get("step_id")))
        return done

    @staticmethod
    def _get_step_order(plan: Optional[Dict[str, Any]]) -> Tuple[str, ...]:
        if isinstance(plan, dict):
            custom = plan.get("step_execution_order")
            if isinstance(custom, list) and custom:
                return tuple(str(s) for s in custom)
            if str(plan.get("granularity", "")).lower() == "micro":
                return MICRO_STEP_EXECUTION_ORDER
        return STEP_EXECUTION_ORDER

    @staticmethod
    def _get_mvp_required(plan: Optional[Dict[str, Any]]) -> Tuple[str, ...]:
        if isinstance(plan, dict):
            custom = plan.get("mvp_required_steps")
            if isinstance(custom, list) and custom:
                return tuple(str(s) for s in custom)
            if str(plan.get("granularity", "")).lower() == "micro":
                return MICRO_MVP_REQUIRED_STEPS
        return MVP_REQUIRED_STEPS

    @classmethod
    def _is_mvp_unlocked(cls, done_steps: Set[str], plan: Optional[Dict[str, Any]] = None) -> bool:
        return all(req in done_steps for req in cls._get_mvp_required(plan))

    @staticmethod
    def build_intake_questions(
        *,
        title: str = "",
        genre: str = "Action RPG",
        pitch: str = "",
    ) -> Dict[str, Any]:
        """Generate structured concept-clarifying questions BEFORE planning or building code/art."""
        clean_title = (title or "Untitled Roblox Game").strip()
        clean_genre = (genre or "Action RPG").strip()
        questions = [
            {
                "id": "Q1_CORE_VERB",
                "topic": "Core Loop & Single MVP Action",
                "question": f"What is the ONE main 30-second verb players repeat in '{clean_title}' ({clean_genre})?",
                "why_it_matters": "Determines S2.1 (Action #1) vs S2.2 (Action #2) so we build and test one tiny mechanic at a time.",
                "examples": ["Sword slash vs dummy -> Block counter", "Collect orbs -> Upgrade pet", "Wall-jump checkpoint run"],
            },
            {
                "id": "Q2_ART_DIRECTION",
                "topic": "Unique Visual Identity, Texture/Asset Style & Anti-Template UI",
                "question": "Which distinct visual mood, TEXTURE_STYLE_PROFILES, ASSET_STYLE_PROFILES, and custom UI paradigm should set this game apart from generic dark-blue UIs?",
                "why_it_matters": "Feeds `sharp_design_system`, `sharp_art_studio(create_pbr_texture_set)`, `custom_bmesh`, and `sharp_gui_build(mode='custom')`.",
                "options": ["candy_simulator", "anime_neon", "cozy_pastel", "scifi_holo", "arcade_pop", "rpg_arcane"],
                "texture_style_profiles": V05_WORKFLOW_DIRECTIVES["style_profiles"]["TEXTURE_STYLE_PROFILES"],
                "asset_style_profiles": V05_WORKFLOW_DIRECTIVES["style_profiles"]["ASSET_STYLE_PROFILES"],
            },
            {
                "id": "Q3_ANIMATION_VFX",
                "topic": "First 2 Animations, Animation Style Profile & Pose-Strip Verification",
                "question": "Which ANIMATION_STYLE_PROFILES weight/tempo and first attack + defensive reaction should we author via `compose_custom` and visually inspect via `pose_strip`?",
                "why_it_matters": "Enforces slow micro-MVP verification with windup hold, hit-stop, and mandatory Vision verification before expanding combos.",
                "default_micro_pair": ["S2.1 Primary Attack Animation + Hitbox", "S2.2 Guard/Block Stance + Mitigation"],
                "animation_style_profiles": V05_WORKFLOW_DIRECTIVES["style_profiles"]["ANIMATION_STYLE_PROFILES"],
            },
            {
                "id": "Q4_AI_MODELS_KEYS",
                "topic": "AI Vision, Video QA & UI/Art Generation Providers",
                "question": "Should Sharp use Gemini (Video/Audio/Vision QA) and OpenRouter (cheap UI/Luau generation), or offline procedural code-art only?",
                "why_it_matters": "Checks `sharp_ai_studio(action='keys_status')` before delegating UI/Vision/Video steps.",
            },
            {
                "id": "Q5_CUT_LIST",
                "topic": "Explicit Post-MVP Cut List",
                "question": "Which secondary systems (trading, extra maps, battle pass, quests, shop tiers) are we explicitly cutting until MVP passes playtest?",
                "why_it_matters": "Prevents feature sprawl; deferred features move into `cut_list` and stay locked until S3/S5/S6.",
            },
        ]
        return {
            "ok": True,
            "action": "intake_questions",
            "title": clean_title,
            "genre": clean_genre,
            "pitch": pitch,
            "recommended_next_call": "After user answers, call `sharp_game_plan(action='create', granularity='micro', ...)` and delegate micro-steps + art creation to Sub-Agents.",
            "questions": questions,
        }

    def build_subagent_brief(
        self,
        *,
        step_id: Optional[str] = None,
        role_focus: str = "auto",
    ) -> Dict[str, Any]:
        """Build a concise, actionable sub-agent delegation brief with v0.5 rules, Sharp skills, and verification gates."""
        plan, _, stages = self._load_plan_and_stages()
        target_id = (step_id or "").strip().upper()
        if not target_id and isinstance(plan, dict) and stages:
            done = self._completed_step_ids(stages)
            for sid in self._get_step_order(plan):
                if sid not in done:
                    target_id = sid
                    break

        focus = (role_focus or "auto").strip().lower()
        if focus == "art_creation":
            spec = {
                "role": "Dedicated 3-Tier 2D/3D Game Art, PBR & Custom UI Sub-Agent",
                "skills": ["roblox-gui", "roblox-audio-vfx-cutscenes", "blender-game-assets"],
                "tools": [
                    "sharp_design_system",
                    "sharp_art_studio",
                    "sharp_gui_slice_and_pack",
                    "sharp_gui_build",
                    "sharp_blender_asset_pipeline",
                    "sharp_equipment_attach",
                    "sharp_media_qa",
                ],
                "verification": (
                    "Follow 3-Tier Art Pipeline (Tier-1 TEXTURE_STYLE_PROFILES/create_pbr_texture_set, "
                    "Tier-2 custom_bmesh + ASSET_STYLE_PROFILES + inspect_attachment_fit, Tier-3 sharp_ai_studio/sharp_media_qa); "
                    "build custom HUD via sharp_gui_build(mode='custom'), verify WCAG >=4.5:1, <=1024px atlases, and Gemini Vision pass."
                ),
                "directives": ["tool_first", "style_guided", "anti_template", "three_tier_art_pipeline", "mandatory_vision_verification"],
            }
        elif focus == "terrain_world":
            spec = STEP_SUBAGENT_ROLES["S1.1"]
        elif focus == "animation_3d":
            spec = STEP_SUBAGENT_ROLES["S3.1"]
        elif focus == "code_contracts":
            spec = STEP_SUBAGENT_ROLES["S0.1"]
        else:
            spec = STEP_SUBAGENT_ROLES.get(target_id, STEP_SUBAGENT_ROLES["S2.1"])

        ds = self.project_library.get_design_system() or (plan.get("design_system") if isinstance(plan, dict) else None)
        ds_dict = ds if isinstance(ds, dict) else {}
        selected_styles = {
            "texture_style": ds_dict.get("texture_style") or "stylized_gradient_atlas",
            "asset_style": ds_dict.get("asset_style") or "handpainted_fantasy_rpg",
            "animation_style": ds_dict.get("animation_style") or "heavy_souls",
        }
        active_directive_keys = list(spec.get("directives") or ["tool_first", "style_guided", "anti_template", "mandatory_vision_verification"])
        step_directives = {
            k: V05_WORKFLOW_DIRECTIVES[k]
            for k in active_directive_keys
            if k in V05_WORKFLOW_DIRECTIVES
        }

        return {
            "ok": True,
            "step_id": target_id or None,
            "subagent_role": spec["role"],
            "skills_to_load": list(spec["skills"]),
            "load_skill_calls": [{"tool": "sharp_load_skill", "args": {"skill_name": sk}} for sk in spec["skills"]],
            "allowed_tools": list(spec["tools"]),
            "verification_gate": spec["verification"],
            "game_title": (plan or {}).get("title") if isinstance(plan, dict) else None,
            "design_system_attached": bool(ds),
            "selected_style_profiles": selected_styles,
            "workflow_directives": {
                **step_directives,
                "three_tier_art_pipeline": V05_WORKFLOW_DIRECTIVES["three_tier_art_pipeline"],
                "style_profiles": V05_WORKFLOW_DIRECTIVES["style_profiles"],
                "tool_keywords": [
                    "sharp_gui_build(mode='custom')",
                    "TEXTURE_STYLE_PROFILES",
                    "ASSET_STYLE_PROFILES",
                    "ANIMATION_STYLE_PROFILES",
                    "compose_custom",
                    "pose_strip",
                    "custom_bmesh",
                    "inspect_attachment_fit",
                    "custom_terrain_spec",
                    "verify_contracts",
                ],
            },
            "micro_rule": (
                "Implement ONLY this single micro-step or art asset batch using Tool-First Sharp MCP workflows "
                "(sharp_gui_build(mode='custom'), custom_terrain_spec, compose_custom, custom_bmesh, SystemContracts/verify_contracts); "
                "run Mandatory Vision-Verification (pose_strip / inspect_attachment_fit / screen_capture) before returning to coordinator."
            ),
        }

    def _resolve_target_step_id(self, requested_id: str, stages: Sequence[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        norm = (requested_id or "").strip().upper()
        for st in stages:
            for step in st.get("steps") or []:
                if str(step.get("step_id", "")).upper() == norm:
                    return str(step["step_id"]), step
        # Allow passing a stage ID like "S0", "S1", "S3", "S4"
        for st in stages:
            if str(st.get("stage_id", "")).upper() == norm:
                steps = st.get("steps") or []
                for step in steps:
                    if not step.get("completed"):
                        return str(step["step_id"]), step
                if steps:
                    return str(steps[-1]["step_id"]), steps[-1]
        return None, None

    # ------------------------------------------------------------------
    # Public Actions: design_system, next_step, complete_step, status, stages, cut_list
    # ------------------------------------------------------------------

    def set_design_system(self, design_system: Dict[str, Any], *, snapshot: bool = True) -> Dict[str, Any]:
        """Validate and store @design-system palette/tokens under project key `design_system`."""
        if not isinstance(design_system, dict) or not (design_system.get("palette") or design_system.get("colors") or design_system.get("tokens")):
            return {
                "ok": False,
                "error": "design_system must be a dict containing 'palette', 'colors', or 'tokens'.",
            }
        return self.project_library.save_design_system(design_system, snapshot=snapshot)

    def next_step(self) -> Dict[str, Any]:
        """Return exactly ONE next actionable step with tool, args template, and expected evidence."""
        plan, state, stages = self._load_plan_and_stages()
        if not isinstance(plan, dict) or not stages:
            return {
                "ok": False,
                "error_code": "NO_PLAN",
                "error": "No structured plan exists yet. Call create_plan(...) first.",
            }

        done = self._completed_step_ids(stages)
        step_order = self._get_step_order(plan)
        mvp_unlocked = self._is_mvp_unlocked(done, plan)

        for step_id in step_order:
            if step_id not in done:
                step = self._find_step_in_stages(stages, step_id)
                if not step:
                    continue
                stage_obj = next((s for s in stages if s.get("stage_id") == step.get("stage_id")), {})
                gate = step.get("gate") or {}
                required_fields: List[str] = ["snapshot_taken (bool=True with existing snapshot file on disk) or snapshot_version"]
                if gate.get("requires_audit"):
                    required_fields.append(
                        "audit_report (signed CriticalAuditEngine dict with >=1 scanned domain/script, or raw luau_sources/world_stats/gui_spec/live_report)"
                    )
                if gate.get("requires_playtest"):
                    required_fields.append(
                        "playtest_report (dict with passed=True, scenario, and checks/assertions or Studio playtest telemetry)"
                    )
                if gate.get("requires_asset"):
                    cats = gate.get("required_asset_categories") or []
                    required_fields.append(
                        f"asset_registered (bool=True) with backed manifest asset (existing file or numeric rbxassetid) in categories {cats}"
                    )
                if gate.get("requires_design_system"):
                    required_fields.append("design_system stored on project (palette/colors/tokens with >=2 entries)")
                if gate.get("requires_spawn_bounds"):
                    required_fields.append("world_stats (spawn_location_count>=1 and part_count>=1) or live_report world telemetry")

                return {
                    "ok": True,
                    "completed": False,
                    "granularity": plan.get("granularity", "standard"),
                    "mvp_unlocked": mvp_unlocked,
                    "current_stage": state.get("current_stage", step["stage_id"]),
                    "step_id": step["step_id"],
                    "stage_id": step["stage_id"],
                    "stage_name": stage_obj.get("name", step["stage_id"]),
                    "phase": step.get("phase", stage_obj.get("phase", "mvp")),
                    "title": step["title"],
                    "tool": step["tool"],
                    "args_template": copy.deepcopy(step.get("args_template", {})),
                    "subagent_brief": self.build_subagent_brief(step_id=step["step_id"]),
                    "follow_up_audit_tool": "sharp_critical_audit",
                    "follow_up_audit_args": {
                        "mode": "gate",
                        "stage_id": step["stage_id"],
                        "step_id": step["step_id"],
                    },
                    "expected_evidence": {
                        "required_fields": required_fields,
                        "gate_thresholds": copy.deepcopy(gate),
                    },
                }

        return {
            "ok": True,
            "completed": True,
            "mvp_unlocked": True,
            "current_stage": "S7",
            "status": "ALL_STAGES_COMPLETE",
            "next_step": None,
        }

    @staticmethod
    def _has_recorded_system(state: Dict[str, Any], keywords: Tuple[str, ...]) -> bool:
        systems = state.get("systems")
        if not isinstance(systems, dict):
            return False
        for sys_name, entry in systems.items():
            if not isinstance(entry, dict):
                continue
            status = str(entry.get("status", "")).strip().lower()
            if status in ("failed", "error", "rejected"):
                continue
            hay = f"{sys_name} {entry.get('domain', '')} {entry.get('last_tool', '')}".lower()
            if any(kw in hay for kw in keywords):
                return True
        return False

    @staticmethod
    def _extract_live_world_counts(live_report: Any) -> Tuple[int, int]:
        decoded: Optional[Dict[str, Any]] = None
        if isinstance(live_report, dict):
            decoded = live_report
        elif isinstance(live_report, str) and live_report.strip():
            try:
                cand = json.loads(live_report)
                if isinstance(cand, dict):
                    decoded = cand
            except json.JSONDecodeError:
                decoded = None
        if not decoded:
            return 0, 0
        if isinstance(decoded.get("result"), str):
            try:
                inner = json.loads(decoded["result"])
                if isinstance(inner, dict):
                    decoded = inner
            except json.JSONDecodeError:
                pass
        telemetry = decoded.get("telemetry") if isinstance(decoded.get("telemetry"), dict) else {}
        world = (
            telemetry.get("world")
            or decoded.get("worldTelemetry")
            or decoded.get("world")
            or {}
        )
        if not isinstance(world, dict):
            return 0, 0
        try:
            spawns = int(world.get("spawnLocationCount", world.get("spawn_location_count", 0)) or 0)
        except (TypeError, ValueError):
            spawns = 0
        try:
            parts = int(world.get("partCount", world.get("part_count", 0)) or 0)
        except (TypeError, ValueError):
            parts = 0
        return spawns, parts

    def _is_valid_asset_entry(self, entry: Dict[str, Any]) -> bool:
        rid = str(entry.get("roblox_asset_id") or "").strip()
        if rid and _ROBLOX_ASSET_ID_RE.match(rid):
            return True
        lp = str(entry.get("local_path") or "").strip()
        if lp:
            abs_p = self.project_library.resolve_local_path(lp)
            if abs_p is not None and abs_p.is_file():
                try:
                    return abs_p.stat().st_size > 0
                except OSError:
                    return False
        return False

    @staticmethod
    def _design_system_has_tokens(ds: Any) -> bool:
        if not isinstance(ds, dict) or not ds:
            return False
        for key in ("palette", "colors", "tokens"):
            val = ds.get(key)
            if isinstance(val, dict) and len(val) >= 2:
                return True
            if isinstance(val, list) and len(val) >= 2:
                return True
        return False

    def _validate_gate_evidence(
        self,
        *,
        step: Dict[str, Any],
        evidence: Optional[Dict[str, Any]],
        plan: Dict[str, Any],
        state: Dict[str, Any],
    ) -> Tuple[bool, List[Dict[str, str]], Optional[Dict[str, Any]]]:
        """Adversarially verify gate evidence; never trusts bare pass booleans or unsigned reports."""
        failures: List[Dict[str, str]] = []
        if not isinstance(evidence, dict) or not evidence:
            return False, [{"code": "MISSING_EVIDENCE", "reason": "evidence dictionary is required and cannot be empty."}], None

        gate = step.get("gate") or {}
        step_id = str(step.get("step_id", ""))

        # 1. Design System check (accept inline save or pre-saved project key `design_system`)
        ds_inline = evidence.get("design_system")
        if isinstance(ds_inline, dict) and ds_inline:
            if not self._design_system_has_tokens(ds_inline):
                failures.append({"code": "INVALID_DESIGN_SYSTEM", "reason": "Provided design_system lacks palette/colors/tokens with >= 2 entries."})
        elif gate.get("requires_design_system"):
            saved_ds = self.project_library.get_design_system()
            if not self._design_system_has_tokens(saved_ds):
                failures.append(
                    {
                        "code": "MISSING_DESIGN_SYSTEM",
                        "reason": f"Step {step_id} requires project 'design_system' palette from @design-system before advancing.",
                    }
                )

        # 2. Spawn & Bounds check (S1.1) — require verifiable world telemetry or recorded terrain system
        if gate.get("requires_spawn_bounds"):
            world_stats = evidence.get("world_stats") if isinstance(evidence.get("world_stats"), dict) else None
            live_spawns, live_parts = self._extract_live_world_counts(evidence.get("live_report"))
            has_world_system = self._has_recorded_system(state, ("terrain_atmosphere", "sharp_terrain", "terrain", "world"))

            if world_stats is not None:
                try:
                    ws_spawns = int(world_stats.get("spawn_location_count", world_stats.get("spawnLocationCount", 0)) or 0)
                except (TypeError, ValueError):
                    ws_spawns = 0
                try:
                    ws_parts = int(world_stats.get("part_count", world_stats.get("partCount", 0)) or 0)
                except (TypeError, ValueError):
                    ws_parts = 0
                if ws_spawns < 1 or ws_parts < 1:
                    failures.append(
                        {
                            "code": "MISSING_SPAWN_OR_BOUNDS",
                            "reason": "S1.1 world_stats must confirm spawn_location_count >= 1 and part_count >= 1.",
                        }
                    )
            elif live_spawns >= 1 and live_parts >= 1:
                pass
            elif has_world_system and evidence.get("spawn_verified") is True and evidence.get("bounds_verified") is True:
                pass
            else:
                failures.append(
                    {
                        "code": "MISSING_WORLD_EVIDENCE",
                        "reason": (
                            "S1.1 refuses bare spawn_verified/bounds_verified booleans; provide verifiable world_stats "
                            "(spawn_location_count>=1, part_count>=1), Studio live_report telemetry, or recorded terrain build."
                        ),
                    }
                )

        # 3. Playtest check (S2.1, S7.1) — refuse bare `playtest_passed=True` + `"smoke"` without structured report
        if gate.get("requires_playtest"):
            pt_passed = evidence.get("playtest_passed")
            pt_rep = evidence.get("playtest_report")
            has_playtest_sys = self._has_recorded_system(state, ("sharp_playtest_scenario", "playtest", "core_loop"))

            if pt_passed is False:
                failures.append(
                    {
                        "code": "PLAYTEST_NOT_PASSED",
                        "reason": f"Step {step_id} playtest_passed is False.",
                    }
                )
            elif isinstance(pt_rep, dict):
                rep_failed = pt_rep.get("ok") is False or pt_rep.get("passed") is False
                errors_val = pt_rep.get("errors")
                has_errors = (isinstance(errors_val, list) and len(errors_val) > 0) or (isinstance(errors_val, int) and errors_val > 0)
                try:
                    failed_cnt = int(pt_rep.get("failed_checks", 0) or 0)
                except (TypeError, ValueError):
                    failed_cnt = 1
                if rep_failed or has_errors or failed_cnt > 0:
                    failures.append(
                        {
                            "code": "PLAYTEST_REPORT_FAILED",
                            "reason": "Provided playtest_report indicates failure or errors.",
                        }
                    )
                else:
                    rep_pass_flag = pt_rep.get("passed") is True or pt_rep.get("ok") is True
                    scenario_name = str(pt_rep.get("scenario") or evidence.get("playtest_scenario") or "").strip()
                    checks_val = pt_rep.get("checks") or pt_rep.get("assertions") or pt_rep.get("steps") or pt_rep.get("steps_passed")
                    has_checks = (
                        (isinstance(checks_val, list) and len(checks_val) >= 1)
                        or (isinstance(checks_val, dict) and len(checks_val) >= 1)
                        or (isinstance(checks_val, int) and checks_val >= 1)
                    )
                    try:
                        passed_cnt = int(pt_rep.get("checks_passed", 0) or 0)
                    except (TypeError, ValueError):
                        passed_cnt = 0
                    has_studio_exec = (
                        pt_rep.get("live_executed") is True
                        or pt_rep.get("executionMode") in ("Executed_In_Studio", "Executed_Via_Upstream")
                        or isinstance(pt_rep.get("bridgeResponse"), dict)
                    )
                    if not rep_pass_flag or not scenario_name or not (has_checks or passed_cnt >= 1 or has_studio_exec):
                        failures.append(
                            {
                                "code": "MISSING_PLAYTEST_REPORT",
                                "reason": (
                                    "playtest_report must include passed/ok=True, non-empty scenario, and structured "
                                    "checks/assertions/steps_passed or Studio playtest execution telemetry."
                                ),
                            }
                        )
            elif pt_passed is True and has_playtest_sys and (evidence.get("playtest_scenario") or evidence.get("playtest_summary")):
                pass
            else:
                failures.append(
                    {
                        "code": "MISSING_PLAYTEST_REPORT",
                        "reason": (
                            f"Step {step_id} refuses bare playtest_passed=True without a structured 'playtest_report' "
                            "(or recorded sharp_playtest_scenario execution in game_state)."
                        ),
                    }
                )

        # 4. Registered Asset check (cross-checked against asset_manifest.json with real file or numeric AssetId!)
        if gate.get("requires_asset"):
            manifest = self.project_library.load_manifest()
            assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
            req_cats = set(gate.get("required_asset_categories") or [])
            explicit_keys = evidence.get("registered_asset_keys") or evidence.get("asset_keys") or []
            if isinstance(explicit_keys, str):
                explicit_keys = [explicit_keys]

            if explicit_keys:
                missing_keys = [k for k in explicit_keys if k not in assets]
                unbacked = [
                    k for k in explicit_keys
                    if k in assets and not self._is_valid_asset_entry(assets[k])
                ]
                if missing_keys:
                    failures.append(
                        {
                            "code": "ASSET_KEY_NOT_FOUND",
                            "reason": f"Asset key(s) {missing_keys} are not registered in asset_manifest.json.",
                        }
                    )
                if unbacked:
                    failures.append(
                        {
                            "code": "ASSET_MISSING_LOCATION",
                            "reason": f"Registered asset key(s) {unbacked} lack a valid numeric roblox_asset_id or existing non-empty local_path file.",
                        }
                    )

            matching_cat_assets = [
                k for k, v in assets.items()
                if isinstance(v, dict)
                and (not req_cats or v.get("category") in req_cats)
                and self._is_valid_asset_entry(v)
            ]
            if not matching_cat_assets:
                failures.append(
                    {
                        "code": "ASSET_NOT_REGISTERED_IN_MANIFEST",
                        "reason": (
                            f"Step {step_id} requires at least one verified asset (existing local_path or valid rbxassetid) "
                            f"in categories {sorted(req_cats)} inside asset_manifest.json."
                        ),
                    }
                )
            elif evidence.get("asset_registered") is not True and not explicit_keys:
                failures.append(
                    {
                        "code": "MISSING_ASSET_CONFIRMATION",
                        "reason": "Evidence must confirm asset_registered=True or specify registered_asset_keys.",
                    }
                )

        # 5. Version Snapshot check (must verify an existing valid snapshot JSON file on disk)
        if gate.get("requires_snapshot"):
            snap_ver = evidence.get("snapshot_version") or evidence.get("version_tag")
            snap_taken = evidence.get("snapshot_taken") is True
            if snap_ver:
                ver_str = str(snap_ver).strip()
                m_ver = re.match(r"^v?(\d+)$", ver_str, re.IGNORECASE)
                if not m_ver:
                    failures.append({"code": "INVALID_SNAPSHOT_TAG", "reason": f"Invalid snapshot_version '{snap_ver}'."})
                else:
                    snap_file = self.project_library.snapshots_dir / f"v{int(m_ver.group(1)):04d}.json"
                    if not snap_file.is_file():
                        failures.append(
                            {
                                "code": "SNAPSHOT_NOT_FOUND",
                                "reason": f"Referenced snapshot '{snap_file.name}' does not exist in versions/snapshots/.",
                            }
                        )
                    else:
                        try:
                            snap_doc = json.loads(snap_file.read_text(encoding="utf-8"))
                            if not isinstance(snap_doc, dict):
                                raise ValueError("Snapshot payload is not a dict")
                        except (OSError, json.JSONDecodeError, ValueError):
                            failures.append(
                                {
                                    "code": "CORRUPT_SNAPSHOT",
                                    "reason": f"Snapshot '{snap_file.name}' is unreadable or invalid JSON.",
                                }
                            )
            elif not snap_taken:
                failures.append(
                    {
                        "code": "MISSING_SNAPSHOT_EVIDENCE",
                        "reason": "Gate requires snapshot_taken=True (with valid disk snapshot) or an existing snapshot_version tag.",
                    }
                )
            else:
                try:
                    cur_ver = int(state.get("current_version", 0) or 0)
                except (TypeError, ValueError):
                    cur_ver = 0
                latest_snap = self.project_library.snapshots_dir / f"v{cur_ver:04d}.json" if cur_ver >= 1 else None
                if cur_ver < 1 or latest_snap is None or not latest_snap.is_file():
                    failures.append(
                        {
                            "code": "SNAPSHOT_NOT_FOUND",
                            "reason": "snapshot_taken=True claimed, but no valid snapshot JSON exists on disk in versions/snapshots/.",
                        }
                    )
                else:
                    try:
                        snap_doc = json.loads(latest_snap.read_text(encoding="utf-8"))
                        if not isinstance(snap_doc, dict):
                            raise ValueError("Snapshot payload is not a dict")
                    except (OSError, json.JSONDecodeError, ValueError):
                        failures.append(
                            {
                                "code": "CORRUPT_SNAPSHOT",
                                "reason": f"Latest snapshot '{latest_snap.name}' is unreadable or invalid JSON.",
                            }
                        )

        # 6. Critical Audit verification (HMAC attestation OR live engine computation; NEVER overwrites REJECT)
        resolved_audit: Optional[Dict[str, Any]] = None
        if gate.get("requires_audit"):
            raw_rep = evidence.get("audit_report") or evidence.get("audit")
            live_rep_in = evidence.get("live_report")
            has_raw_inputs = any(
                evidence.get(k) is not None
                for k in ("luau_sources", "file_paths", "gui_spec", "design_lint", "anim_clips", "anim_analysis", "world_stats")
            )

            raw_valid_shape = False
            raw_attested = False
            att_reason = ""
            if raw_rep is not None:
                if not isinstance(raw_rep, dict) or not isinstance(raw_rep.get("findings"), list) or "verdict" not in raw_rep:
                    failures.append(
                        {
                            "code": "INVALID_AUDIT_REPORT",
                            "reason": "audit_report must be a structured CriticalAuditEngine output containing 'findings' list and 'verdict'.",
                        }
                    )
                else:
                    raw_valid_shape = True
                    raw_attested, att_reason = CriticalAuditEngine.verify_report_attestation(raw_rep)

            computed: Optional[Dict[str, Any]] = None
            if live_rep_in is not None:
                computed = self.audit_engine.audit_live(
                    live_report=live_rep_in,
                    luau_sources=evidence.get("luau_sources"),
                    gui_spec=evidence.get("gui_spec"),
                    design_lint=evidence.get("design_lint"),
                    anim_analysis=evidence.get("anim_analysis"),
                    project_library=self.project_library,
                )
            elif has_raw_inputs:
                computed = self.audit_engine.audit_static(
                    luau_sources=evidence.get("luau_sources"),
                    file_paths=evidence.get("file_paths"),
                    gui_spec=evidence.get("gui_spec"),
                    design_lint=evidence.get("design_lint"),
                    anim_clips=evidence.get("anim_clips"),
                    anim_analysis=evidence.get("anim_analysis"),
                    world_stats=evidence.get("world_stats"),
                    project_library=self.project_library,
                    plan_data=plan,
                    game_state=state,
                    check_plan=False,
                )

            if raw_valid_shape and computed is not None:
                raw_findings = list(raw_rep.get("findings") or [])
                comp_findings = list(computed.get("findings") or [])
                merged_findings = raw_findings + comp_findings
                recomp_score, recomp_verdict, recomp_counts = _score_and_verdict(merged_findings)
                raw_verdict = str(raw_rep.get("verdict", "REJECT")).strip().upper()
                if raw_verdict not in VERDICT_RANK:
                    raw_verdict = "REJECT"
                comp_verdict = str(computed.get("verdict", "REJECT")).strip().upper()
                if comp_verdict not in VERDICT_RANK:
                    comp_verdict = "REJECT"
                worst_verdict = max((raw_verdict, comp_verdict, recomp_verdict), key=lambda v: VERDICT_RANK[v])
                try:
                    raw_score = float(raw_rep.get("score", 0))
                except (TypeError, ValueError):
                    raw_score = 0.0
                worst_score = int(min(raw_score, float(computed.get("score", 0)), float(recomp_score)))
                resolved_audit = {
                    **computed,
                    "findings": merged_findings,
                    "summary": {**(computed.get("summary") or {}), **recomp_counts, "total": len(merged_findings)},
                    "score": worst_score,
                    "verdict": worst_verdict,
                }
            elif raw_valid_shape:
                if not raw_attested:
                    failures.append(
                        {
                            "code": "UNATTESTED_AUDIT_REPORT",
                            "reason": (
                                f"Self-written or tampered audit_report rejected ({att_reason}). "
                                "Supply an attested CriticalAuditEngine report or pass auditable luau_sources/world_stats/gui_spec/live_report."
                            ),
                        }
                    )
                resolved_audit = raw_rep
            elif computed is not None:
                resolved_audit = computed

            if resolved_audit is None:
                if raw_rep is None:
                    failures.append(
                        {
                            "code": "MISSING_AUDIT_EVIDENCE",
                            "reason": "Gate requires an attested 'audit_report' from CriticalAuditEngine (or auditable luau_sources/gui_spec/world_stats/live_report).",
                        }
                    )
            else:
                summary = resolved_audit.get("summary") if isinstance(resolved_audit.get("summary"), dict) else {}
                audited_domains = set(summary.get("domains_audited") or [])
                try:
                    scripts_scanned = int(summary.get("scripts_scanned", 0) or 0)
                except (TypeError, ValueError):
                    scripts_scanned = 0
                has_real_domain_scan = (
                    scripts_scanned >= 1
                    or bool(resolved_audit.get("live_executed"))
                    or bool(audited_domains & {"luau", "gui", "world", "animation"})
                )
                if not has_real_domain_scan:
                    failures.append(
                        {
                            "code": "EMPTY_AUDIT_SCOPE",
                            "reason": "Audit scanned 0 scripts and 0 domain artifacts (luau/gui/world/animation/live). Audit real artifacts before closing a gate.",
                        }
                    )

                findings_list = resolved_audit.get("findings") or []
                recomp_score, recomp_verdict, recomp_counts = _score_and_verdict(findings_list)
                blocker_cnt = recomp_counts["blocker"]
                critical_cnt = recomp_counts["critical"]
                major_cnt = recomp_counts["major"]

                raw_v = str(resolved_audit.get("verdict", "")).strip().upper()
                if raw_v not in VERDICT_RANK:
                    raw_v = "REJECT"
                verdict = max((raw_v, recomp_verdict), key=lambda v: VERDICT_RANK[v])
                try:
                    score_val = min(float(resolved_audit.get("score", 0)), float(recomp_score))
                except (TypeError, ValueError):
                    score_val = 0.0

                if blocker_cnt > int(gate.get("max_blocker", 0)):
                    failures.append(
                        {
                            "code": "AUDIT_BLOCKER_PRESENT",
                            "reason": f"Audit contains {blocker_cnt} BLOCKER finding(s); gate requires 0.",
                        }
                    )
                if critical_cnt > int(gate.get("max_critical", 0)):
                    failures.append(
                        {
                            "code": "AUDIT_CRITICAL_PRESENT",
                            "reason": f"Audit contains {critical_cnt} CRITICAL finding(s); gate requires 0.",
                        }
                    )
                max_major = int(gate.get("max_major", 2))
                if major_cnt > max_major:
                    failures.append(
                        {
                            "code": "AUDIT_MAJOR_EXCEEDED",
                            "reason": f"Audit contains {major_cnt} MAJOR finding(s), exceeding stage threshold {max_major}.",
                        }
                    )
                allowed_verdicts = set(gate.get("required_verdicts") or ["SHIP", "FIX_FIRST"])
                if verdict not in allowed_verdicts:
                    failures.append(
                        {
                            "code": "AUDIT_VERDICT_REJECTED",
                            "reason": f"Audit verdict '{verdict}' does not satisfy stage requirement {sorted(allowed_verdicts)}.",
                        }
                    )
                min_score = float(gate.get("min_score", 70))
                if score_val < min_score:
                    failures.append(
                        {
                            "code": "AUDIT_SCORE_TOO_LOW",
                            "reason": f"Audit score {score_val} is below stage minimum {min_score}.",
                        }
                    )

        return len(failures) == 0, failures, resolved_audit

    def complete_step(self, step_id: str, evidence: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Advance a step ONLY if hard ordering, MVP-first lock, and gate evidence checks all pass."""
        plan, state, stages = self._load_plan_and_stages()
        if not isinstance(plan, dict) or not stages:
            return {
                "ok": False,
                "error_code": "NO_PLAN",
                "error": "No structured plan exists yet. Call create_plan(...) first.",
            }

        resolved_id, target_step = self._resolve_target_step_id(step_id, stages)
        step_order = self._get_step_order(plan)
        mvp_required = self._get_mvp_required(plan)
        if not resolved_id or not target_step or resolved_id not in step_order:
            return {
                "ok": False,
                "error_code": "UNKNOWN_STEP",
                "error": f"Unknown step or stage ID '{step_id}'. Valid steps: {list(step_order)}.",
            }

        if target_step.get("completed"):
            return {
                "ok": False,
                "error_code": "STEP_ALREADY_COMPLETED",
                "error": f"Step '{resolved_id}' is already completed.",
                "step_id": resolved_id,
            }

        done_steps = self._completed_step_ids(stages)
        target_idx = step_order.index(resolved_id)
        target_stage_id = str(target_step["stage_id"])

        # Enforce MVP-first lock BEFORE S3/S5/S6/S7 (and S4.2) can unlock
        mvp_unlocked = self._is_mvp_unlocked(done_steps, plan=plan)
        if target_stage_id in POST_MVP_LOCKED_STAGES and not mvp_unlocked:
            blocking = [s for s in mvp_required if s not in done_steps]
            return {
                "ok": False,
                "error_code": "MVP_LOCKED",
                "error": (
                    f"MVP-first lock blocks '{resolved_id}' (stage {target_stage_id}): "
                    f"S0-S2 and minimal S4 HUD (S4.1) must all be green and audited first."
                ),
                "step_id": resolved_id,
                "blocking_steps": blocking,
            }

        # Enforce strict sequential step ordering
        missing_prereqs = [s for s in step_order[:target_idx] if s not in done_steps]
        if missing_prereqs:
            return {
                "ok": False,
                "error_code": "STAGE_ORDER_LOCKED",
                "error": f"Cannot complete '{resolved_id}' out of order; prerequisite step(s) {missing_prereqs} must pass first.",
                "step_id": resolved_id,
                "blocking_steps": missing_prereqs,
            }

        # Enforce gate evidence checks
        gate_ok, failed_checks, resolved_audit = self._validate_gate_evidence(
            step=target_step,
            evidence=evidence,
            plan=plan,
            state=state,
        )
        if not gate_ok:
            return {
                "ok": False,
                "error_code": "GATE_EVIDENCE_REJECTED",
                "error": f"Step '{resolved_id}' failed exit gate verification.",
                "step_id": resolved_id,
                "failed_checks": failed_checks,
            }

        # Persist inline design_system if supplied
        if isinstance(evidence, dict) and isinstance(evidence.get("design_system"), dict):
            self.project_library.save_design_system(evidence["design_system"], snapshot=False)
            plan["design_system"] = evidence["design_system"]

        # Transition state & snapshot version
        from ..project_library import _utc_now_iso

        ts = _utc_now_iso()
        target_step["completed"] = True
        target_step["completed_at"] = ts
        target_step["gate_verdict"] = (resolved_audit or {}).get("verdict")
        target_step["gate_score"] = (resolved_audit or {}).get("score")

        # Update stage statuses cleanly
        updated_done = self._completed_step_ids(stages)
        new_mvp_unlocked = self._is_mvp_unlocked(updated_done, plan=plan)
        next_pending_step_id: Optional[str] = next(
            (sid for sid in step_order if sid not in updated_done),
            None,
        )
        next_stage_id = (
            self._find_step_in_stages(stages, next_pending_step_id)["stage_id"]
            if next_pending_step_id
            else "S7"
        )

        for st in stages:
            sid = st["stage_id"]
            st_steps = st.get("steps") or []
            if all(s.get("completed") for s in st_steps):
                st["status"] = "completed"
            elif sid in POST_MVP_LOCKED_STAGES and not new_mvp_unlocked:
                st["status"] = "locked"
            elif next_pending_step_id and any(s.get("step_id") == next_pending_step_id for s in st_steps):
                st["status"] = "unlocked"
            elif any(s.get("completed") for s in st_steps):
                st["status"] = "in_progress"
            else:
                st["status"] = "locked"

        # Keep milestones synchronized
        milestone_label = f"[{resolved_id}] {target_step['title']}"
        completed_ms = list(state.get("completed_milestones") or [])
        if milestone_label not in completed_ms:
            completed_ms.append(milestone_label)
        planned_ms = [m for m in (state.get("planned_milestones") or []) if m != milestone_label]

        plan["stages"] = copy.deepcopy(stages)
        save_res = self.project_library.save_plan(
            plan,
            state_updates={
                "current_stage": next_stage_id,
                "mvp_unlocked": new_mvp_unlocked,
                "planner_stages": copy.deepcopy(stages),
                "completed_milestones": completed_ms,
                "planned_milestones": planned_ms,
            },
            snapshot_summary=f"Completed gate step {resolved_id}: {target_step['title']}",
            tool_name="sharp_game_plan",
            target_domain=str(target_step.get("target_domain") or "game_plan"),
        )

        return {
            "ok": True,
            "completed_step": resolved_id,
            "stage_id": target_stage_id,
            "mvp_unlocked": new_mvp_unlocked,
            "current_stage": next_stage_id,
            "next_step_id": next_pending_step_id,
            "snapshot": save_res["snapshot"],
        }

    def get_status(self, detail: str = "summary") -> Dict[str, Any]:
        """Return compact planner progress, MVP-lock status, and next step."""
        plan, state, stages = self._load_plan_and_stages()
        if not isinstance(plan, dict) or not stages:
            return {
                "ok": True,
                "has_plan": False,
                "project_id": self.project_library.project_id,
                "message": "No structured plan.json created yet.",
            }

        done = self._completed_step_ids(stages)
        step_order = self._get_step_order(plan)
        mvp_unlocked = self._is_mvp_unlocked(done, plan=plan)
        nxt = self.next_step()
        out: Dict[str, Any] = {
            "ok": True,
            "has_plan": True,
            "plan_id": plan.get("plan_id"),
            "title": plan.get("title"),
            "genre": plan.get("genre"),
            "granularity": plan.get("granularity", "standard"),
            "current_version": f"v{int(state.get('current_version', 0)):04d}",
            "current_stage": state.get("current_stage", "S0"),
            "mvp_unlocked": mvp_unlocked,
            "completed_steps": sorted(done),
            "total_steps": len(step_order),
            "has_design_system": bool(self.project_library.get_design_system()),
            "next_step": None if nxt.get("completed") else {
                "step_id": nxt.get("step_id"),
                "stage_id": nxt.get("stage_id"),
                "title": nxt.get("title"),
                "tool": nxt.get("tool"),
                "subagent_brief": nxt.get("subagent_brief"),
            },
        }
        if detail == "complete":
            out["plan"] = plan
            out["stages"] = stages
        return out

    def get_stages(self) -> Dict[str, Any]:
        """Return ordered stage definitions (`S0..S7`) with lock/completion state and gates."""
        plan, state, stages = self._load_plan_and_stages()
        if not isinstance(plan, dict) or not stages:
            return {"ok": False, "error_code": "NO_PLAN", "error": "No structured plan exists yet."}
        done = self._completed_step_ids(stages)
        step_order = self._get_step_order(plan)
        mvp_required = self._get_mvp_required(plan)
        return {
            "ok": True,
            "granularity": plan.get("granularity", "standard"),
            "stage_order": list(STAGE_ORDER),
            "step_order": list(step_order),
            "mvp_required_steps": list(mvp_required),
            "mvp_unlocked": self._is_mvp_unlocked(done, plan=plan),
            "current_stage": state.get("current_stage", "S0"),
            "stages": stages,
        }

    def get_cut_list(self) -> Dict[str, Any]:
        """Return the explicit post-MVP cut list and MVP single-loop scope."""
        plan = self.project_library.load_plan()
        if not isinstance(plan, dict):
            return {"ok": False, "error_code": "NO_PLAN", "error": "No structured plan exists yet."}
        return {
            "ok": True,
            "title": plan.get("title"),
            "mvp_scope": plan.get("mvp_scope", {}),
            "cut_list": plan.get("cut_list", []),
        }

    def dispatch_action(self, action: str = "status", **kwargs: Any) -> Dict[str, Any]:
        """Unified dispatcher for `sharp_game_plan(action=...)` MCP calls."""
        act = (action or "status").strip().lower()
        if act == "create":
            return self.create_plan(
                title=str(kwargs.get("title") or ""),
                genre=str(kwargs.get("genre") or "Action RPG"),
                pitch=str(kwargs.get("pitch") or ""),
                audience=str(kwargs.get("audience") or "Ages 13+ Roblox players"),
                session_length_min=kwargs.get("session_length_min") or 12,
                monetization=str(kwargs.get("monetization") or "Cosmetics + Fair GamePasses"),
                platforms=kwargs.get("platforms"),
                design_system=kwargs.get("design_system"),
                granularity=str(kwargs.get("granularity") or "standard"),
            )
        if act == "intake_questions":
            return self.build_intake_questions(
                title=str(kwargs.get("title") or ""),
                genre=str(kwargs.get("genre") or "Action RPG"),
                pitch=str(kwargs.get("pitch") or ""),
            )
        if act == "subagent_brief":
            return self.build_subagent_brief(
                step_id=kwargs.get("step_id"),
                role_focus=kwargs.get("role_focus"),
            )
        if act == "status":
            return self.get_status(detail=str(kwargs.get("detail") or "summary"))
        if act == "next_step":
            return self.next_step()
        if act == "complete_step":
            sid = str(kwargs.get("step_id") or "")
            if not sid:
                return {"ok": False, "error": "step_id is required for action='complete_step'."}
            return self.complete_step(sid, kwargs.get("evidence"))
        if act == "stages":
            return self.get_stages()
        if act == "cut_list":
            return self.get_cut_list()
        if act == "set_design_system":
            ds = kwargs.get("design_system")
            if not isinstance(ds, dict):
                return {"ok": False, "error": "design_system dict is required for action='set_design_system'."}
            return self.set_design_system(ds)
        return {"ok": False, "error": f"Unknown sharp_game_plan action '{action}'."}

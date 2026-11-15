"""Domain skill router and progressive-disclosure loader for Sharp MCP Server."""

from __future__ import annotations

import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


SERVER_ROOT = Path(__file__).resolve().parent.parent
BUNDLED_SKILLS_DIR = Path(__file__).resolve().parent / "bundled_skills"


def resolve_default_skills_dir(skills_dir: Optional[str | Path] = None) -> Path:
    """Resolve the active skills directory cleanly without hardcoded user paths."""
    candidates: List[Path] = []
    if skills_dir:
        candidates.append(Path(skills_dir).expanduser())
    env_skills = os.environ.get("SHARP_SKILLS_DIR", "").strip()
    if env_skills:
        candidates.append(Path(env_skills).expanduser())
    candidates.append(Path.home() / ".gemini" / "config" / "skills")
    if BUNDLED_SKILLS_DIR.exists():
        candidates.append(BUNDLED_SKILLS_DIR)
    server_skills = SERVER_ROOT / "skills"
    if server_skills.exists():
        candidates.append(server_skills)

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return candidates[0].resolve()


def resolve_default_archive_dir(archive_dir: Optional[str | Path] = None) -> Optional[Path]:
    """Resolve optional sibling research archive root if present."""
    candidates: List[Path] = []
    if archive_dir:
        candidates.append(Path(archive_dir).expanduser())
    env_archive = os.environ.get("SHARP_ARCHIVE_DIR", "").strip()
    if env_archive:
        candidates.append(Path(env_archive).expanduser())
    if (SERVER_ROOT.parent / "01_roblox_animation").exists():
        candidates.append(SERVER_ROOT.parent)

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


ARCHIVE_FALLBACK_MAP: Dict[str, str] = {
    "roblox-animation": "01_roblox_animation/skill",
    "roblox-gui": "02_roblox_gui/skill",
    "roblox-terrain-atmosphere": "03_roblox_terrain_atmosphere/skill",
    "roblox-luau-coding": "04_roblox_luau_coding/skill",
    "roblox-combat-and-controllers": "07_roblox_combat_and_controllers/skill",
    "roblox-audio-vfx-cutscenes": "08_roblox_audio_vfx_cutscenes/skill",
    "roblox-data-economy-monetization": "09_roblox_data_economy_monetization/skill",
    "roblox-ai-and-gameplay-systems": "10_roblox_ai_and_gameplay_systems/skill",
    "roblox-world-assembly-and-optimization": "11_roblox_world_assembly_and_optimization/skill",
}


@dataclass(frozen=True)
class SkillMetadata:
    name: str
    category: str  # "roblox" | "blender"
    summary: str
    keywords: List[str]
    recommended_tools: List[str]
    critical_rules: List[str]
    optional_toolchain: Optional[Dict[str, Any]] = None


BLENDER_OPTIONAL_TOOLCHAIN: Dict[str, Any] = {
    "tool": "blender",
    "optional": True,
    "auto_installable": True,
    "setup_tool": "sharp_blender_setup",
    "note": "Required only for offline 3D modeling/baking/rigging; Studio tools work without Blender.",
}


# 9 Roblox skills + 4 optional/auto-installable Blender skills.
DOMAIN_SKILL_SPECS: Dict[str, SkillMetadata] = {
    "roblox-luau-coding": SkillMetadata(
        name="roblox-luau-coding",
        category="roblox",
        summary=(
            "Production Luau architecture, MVP game planning, strict Studio Explorer boundaries, "
            "RemoteEvent validation, critical release auditing, and modern Luau APIs."
        ),
        keywords=[
            "luau", "script", "architecture", "scaffold", "remote", "remoteevent",
            "audit", "refactor", "bug", "error", "undo", "snapshot", "rojo", "lune",
            "selene", "stylua", "wally", "rokit", "toolchain", "network", "security",
            "streaming", "parallel", "ias", "inputaction", "explorer", "lint",
            "plan", "game plan", "mvp", "vertical slice", "roadmap", "cut list",
            "milestone", "critical audit", "gate", "release", "blocker", "risk register",
            "challenge", "intake", "questions", "micro-step", "subagent", "sub-agent",
            "api key", "gemini", "openrouter", "video",
        ],
        recommended_tools=[
            "sharp_luau_scaffold", "sharp_game_plan", "sharp_critical_audit",
            "sharp_audit_all", "sharp_snapshot_and_undo", "sharp_toolchain",
            "sharp_studio_status", "sharp_game_library", "sharp_ai_studio", "sharp_media_qa",
        ],
        critical_rules=[
            "Keep server logic in ServerScriptService, secrets in ServerStorage, shared contracts in ReplicatedStorage, and client code in StarterPlayerScripts/StarterGui.",
            "Wrap all Studio scene mutations in ChangeHistoryService:TryBeginRecording / FinishRecording.",
            "Validate every RemoteEvent/RemoteFunction client payload with runtime typeof checks and server authority.",
            "Use task.wait / task.spawn / task.delay instead of deprecated wait/spawn/delay.",
        ],
    ),
    "roblox-terrain-atmosphere": SkillMetadata(
        name="roblox-terrain-atmosphere",
        category="roblox",
        summary=(
            "Chunked procedural Workspace.Terrain generation, flattened hubs, "
            "Lighting/Atmosphere/Clouds/Sky/GlobalWind presets, and StreamingEnabled checks."
        ),
        keywords=[
            "terrain", "world", "biome", "mountain", "river", "ocean", "island",
            "valley", "canyon", "desert", "snow", "forest", "grass", "water",
            "lighting", "atmosphere", "sky", "fog", "cloud", "wind", "day",
            "night", "sunset", "golden hour", "weather", "rain", "cyberpunk",
        ],
        recommended_tools=["sharp_terrain_build", "sharp_environment_apply", "sharp_audit_all"],
        critical_rules=[
            "Align WriteVoxels / WriteVoxelChannels regions to 4-stud voxel grid multiples.",
            "Chunk large terrain writes with task.wait() yields to avoid Studio script timeouts.",
            "Use Enum.LightingStyle.Realistic for modern atmosphere scenes and check StreamingEnabled.",
        ],
    ),
    "roblox-gui": SkillMetadata(
        name="roblox-gui",
        category="roblox",
        summary=(
            "Bespoke per-game UI design systems, anti-slop style/contrast linting, cross-platform "
            "11-layer StarterGui hierarchies, 9-slice cutting, icon atlases, StyleSheets, and pixel visual diffing."
        ),
        keywords=[
            "gui", "ui", "hud", "menu", "shop", "inventory", "modal", "dialog",
            "button", "panel", "tooltip", "toast", "9-slice", "slice", "atlas",
            "stylesheet", "mobile", "console", "viewport", "screen", "startergui",
            "visual diff", "screenshot", "layout", "overlap", "clip",
            "palette", "color palette", "swatch", "design system", "theme",
            "ui style", "anti-slop", "antislop", "typography", "font", "bitmap font", "gradient",
            "prompt", "contrast", "wcag", "vision", "openrouter", "gemini",
            "2d art", "2d element", "custom ui", "click effect", "ui effect", "2d animation",
        ],
        recommended_tools=[
            "sharp_design_system",
            "sharp_art_studio",
            "sharp_gui_slice_and_pack",
            "sharp_gui_build",
            "sharp_gui_inspect",
            "sharp_gui_patch",
            "sharp_visual_diff",
            "sharp_media_qa",
            "sharp_ai_studio",
        ],
        critical_rules=[
            "Keep ScreenGui ZIndexBehavior=Sibling and SafeAreaCompatibility=FullscreenExtension with UIAspectRatioConstraint/UITextSizeConstraint.",
            "Use SliceCenter Rect margins matching actual 9-slice border pixels on ImageLabels/ImageButtons.",
            "Run sharp_gui_inspect, sharp_gui_patch, and sharp_visual_diff to verify desktop and mobile safe areas.",
        ],
    ),
    "roblox-animation": SkillMetadata(
        name="roblox-animation",
        category="roblox",
        summary=(
            "R15/R6/custom rigging, equipment/weapon/armor attachments & IK grips, JointInstances/Motor6Ds, "
            "procedural KeyframeSequences, locomotion Animate integration, and optional Blender rig/animation compilation."
        ),
        keywords=[
            "animation", "animate", "keyframe", "keyframesequence", "rig", "motor6d",
            "r15", "r6", "walk", "run", "idle", "jump", "attack", "slash", "door",
            "emote", "pose", "curveanimation", "weapon hold", "ik",
            "attachment", "attachments", "equip", "holster", "sheath", "scabbard",
            "armor", "shoulder pad", "pauldron", "helmet", "backpack",
            "two-handed", "foregrip", "ikcontrol", "rigidconstraint", "sidecar",
        ],
        recommended_tools=[
            "sharp_rig_and_animation",
            "sharp_equipment_attach",
            "sharp_blender_rig_and_anim",
            "sharp_blender_setup",
            "sharp_studio_status",
        ],
        critical_rules=[
            "Always build Motor6Ds cleanly and inspect existing rigs before authoring clips.",
            "Ensure humanoid Animate integration yields cleanly and preserves smooth fade weights.",
            "Keep animations Studio-native via KeyframeSequenceProvider / KeyframeSequence, using optional Blender tooling when authoring custom FBX motion.",
        ],
        optional_toolchain=BLENDER_OPTIONAL_TOOLCHAIN,
    ),
    "roblox-combat-and-controllers": SkillMetadata(
        name="roblox-combat-and-controllers",
        category="roblox",
        summary=(
            "Physics character controllers, InputActionSystem bindings, shapecast melee hitboxes, "
            "lag-compensated projectiles, dashes, and Motor6D weapon equip/holster state machines."
        ),
        keywords=[
            "combat", "sword", "melee", "gun", "projectile", "hitbox", "shapecast",
            "weapon", "dash", "controller", "controllermanager", "groundcontroller",
            "aircontroller", "walljump", "parry", "stamina", "damage", "pvp",
        ],
        recommended_tools=["sharp_combat_and_controllers", "sharp_playtest_scenario", "sharp_audit_all"],
        critical_rules=[
            "Perform authoritative hit validation on the server using workspace:Shapecast / RaycastParams.",
            "Bind inputs through InputActionSystem (InputContext/InputAction/InputBinding) rather than legacy hardcoded keys.",
            "Verify Motor6D weld offsets and weapon state transitions via playtest bots.",
        ],
    ),
    "roblox-audio-vfx-cutscenes": SkillMetadata(
        name="roblox-audio-vfx-cutscenes",
        category="roblox",
        summary=(
            "Modern node-based Audio Wiring graphs, flipbook ParticleEmitters, "
            "31-cap Highlight pools, trauma camera shake, and Catmull-Rom cutscenes."
        ),
        keywords=[
            "audio", "sound", "music", "audioplayer", "reverb", "spatial", "vfx",
            "particle", "explosion", "highlight", "outline", "camera shake", "cutscene",
            "spline", "cinematic", "trail", "beam",
            "soundtest", "sound test", "video", "playtest video", "flipbook", "2d effect", "3d effect", "click vfx",
        ],
        recommended_tools=["sharp_audio_vfx_cutscenes", "sharp_art_studio", "sharp_media_qa", "sharp_audit_all"],
        critical_rules=[
            "Enforce the strict Roblox engine cap of at most 31 simultaneous Highlight instances via a Highlight pool.",
            "Route sound effects through AudioPlayer -> AudioFader -> AudioEmitter / AudioDeviceOutput wiring.",
            "Wrap cutscene camera overrides with clean restore on skip/finish.",
        ],
    ),
    "roblox-data-economy-monetization": SkillMetadata(
        name="roblox-data-economy-monetization",
        category="roblox",
        summary=(
            "Session-locked DataStore profiles with Studio mock fallback, server-authoritative "
            "currency/inventory/quests/codes/loot, and idempotent ProcessReceipt monetization."
        ),
        keywords=[
            "datastore", "profile", "save", "load", "currency", "coins", "gems",
            "shop", "inventory", "quest", "code", "redeem", "loot", "monetization",
            "gamepass", "devproduct", "receipt", "processreceipt", "leaderstats", "economy",
        ],
        recommended_tools=["sharp_data_economy_monetization", "sharp_audit_all"],
        critical_rules=[
            "Use DataStoreService:UpdateAsync with session lock ownership and BindToClose flush.",
            "Provide automatic in-memory mock DataStore fallback in RunService:IsStudio() when API access is disabled.",
            "Deduplicate MarketplaceService.ProcessReceipt purchases idempotently before returning PurchaseGranted.",
        ],
    ),
    "roblox-ai-and-gameplay-systems": SkillMetadata(
        name="roblox-ai-and-gameplay-systems",
        category="roblox",
        summary=(
            "CollectionService NPC AI state machines with PathfindingService & Blocked recompute, "
            "ProximityPrompt branching dialogues, and round/wave/lobby directors."
        ),
        keywords=[
            "npc", "ai", "enemy", "mob", "boss", "patrol", "chase", "pathfinding",
            "dialogue", "quest giver", "proximityprompt", "wave", "round", "lobby",
            "arena", "obby", "checkpoint", "spawner", "bot", "playtest",
        ],
        recommended_tools=[
            "sharp_ai_and_gameplay_systems",
            "sharp_playtest_scenario",
            "sharp_audit_all",
        ],
        critical_rules=[
            "Always set SetNetworkOwner(nil) on server-driven NPC root parts and throttle PathfindingService recomputes on Path.Blocked.",
            "Drive NPC loops cleanly via CollectionService tags rather than cloning scripts per NPC.",
            "Include AgentRadius, AgentHeight, and AgentCanJump in CreatePath AgentParameters.",
        ],
    ),
    "roblox-world-assembly-and-optimization": SkillMetadata(
        name="roblox-world-assembly-and-optimization",
        category="roblox",
        summary=(
            "Poisson-disc raycast terrain scattering, Attachment socket modular snapping, "
            "and StreamingEnabled / CollisionFidelity / RenderFidelity optimization."
        ),
        keywords=[
            "scatter", "poisson", "tree", "rock", "foliage", "prop", "modular",
            "snap", "attachment", "socket", "building", "dungeon", "optimize",
            "streaming", "lod", "collisionfidelity", "renderfidelity", "fps", "drawcall",
            "map building", "interpenetration", "glitch", "asset overlap", "z-fighting", "floating",
        ],
        recommended_tools=["sharp_world_assembly_and_optimization", "sharp_critical_audit", "sharp_audit_all"],
        critical_rules=[
            "Snap modular pieces strictly by Attachment sockets: targetSocket.WorldCFrame * sourceSocket.CFrame:Inverse().",
            "Align scattered props using surface raycast normals, slope limits, and Enum.Material allowlists.",
            "Audit MeshPart CollisionFidelity, RenderFidelity, CastShadow, and ModelStreamingMode.",
        ],
    ),
    # 4 Blender skills (all optional + auto-installable via sharp_blender_setup)
    "blender-game-assets": SkillMetadata(
        name="blender-game-assets",
        category="blender",
        summary=(
            "Optional Blender pipeline: procedural 3D game props, weapons, armor, "
            "attachment sockets, LOD cleanup, and clean FBX/glTF export for Roblox Studio."
        ),
        keywords=[
            "blender", "3d model", "mesh", "prop", "sword mesh", "weapon mesh",
            "fbx", "glb", "gltf", "lowpoly", "polycount", "sculpt", "export",
            "holster", "armor", "helmet", "pauldron", "attachment", "shield", "staff",
        ],
        recommended_tools=["sharp_blender_asset_pipeline", "sharp_equipment_attach", "sharp_blender_setup"],
        critical_rules=[
            "Validate manifold geometry, applied scale/rotation, and Roblox triangle budgets before exporting FBX/glTF.",
            "Blender is optional and auto-installable via sharp_blender_setup(auto_install=True).",
        ],
        optional_toolchain=BLENDER_OPTIONAL_TOOLCHAIN,
    ),
    "blender-modular-architecture": SkillMetadata(
        name="blender-modular-architecture",
        category="blender",
        summary=(
            "Optional Blender pipeline: grid-aligned modular walls, arches, columns, "
            "buildings, and attachment-socket kits for Roblox assembly."
        ),
        keywords=[
            "modular kit", "arch", "wall", "column", "pillar", "temple", "castle",
            "bridge", "building kit", "blender architecture",
        ],
        recommended_tools=[
            "sharp_blender_asset_pipeline",
            "sharp_world_assembly_and_optimization",
            "sharp_blender_setup",
        ],
        critical_rules=[
            "Snap modular pivots to consistent integer grid increments and export with Y-up / Roblox unit scale.",
            "Pair exported modular kits with Attachment sockets for sharp_world_assembly_and_optimization snapping.",
        ],
        optional_toolchain=BLENDER_OPTIONAL_TOOLCHAIN,
    ),
    "blender-character-rigging": SkillMetadata(
        name="blender-character-rigging",
        category="blender",
        summary=(
            "Optional Blender pipeline: R15/custom skeleton building, bone weight painting, "
            "hand/belt/armor sockets, and FBX rig+motion export to Roblox."
        ),
        keywords=[
            "blender rig", "armature", "weight paint", "skinning", "socket",
            "bone", "skeleton", "retarget",
            "attachment", "holster", "sheath", "armor", "equipment", "pauldron", "ik", "sidecar",
        ],
        recommended_tools=[
            "sharp_blender_rig_and_anim",
            "sharp_equipment_attach",
            "sharp_rig_and_animation",
            "sharp_blender_setup",
        ],
        critical_rules=[
            "Keep R15 bone hierarchy naming exact (HumanoidRootPart -> LowerTorso -> UpperTorso -> ...) and limit weights <= 4 per vertex.",
            "Apply transforms cleanly and strip non-deforming helper bones before FBX export.",
        ],
        optional_toolchain=BLENDER_OPTIONAL_TOOLCHAIN,
    ),
    "blender-bake-and-materials": SkillMetadata(
        name="blender-bake-and-materials",
        category="blender",
        summary=(
            "Optional Blender pipeline: Cycles PBR normal/AO/albedo texture baking, "
            "UV unwrapping, and stylized texture atlases for SurfaceAppearance."
        ),
        keywords=[
            "bake", "normal map", "ambient occlusion", "ao", "uv", "texture atlas",
            "pbr", "surfaceappearance", "roughness", "metallic",
        ],
        recommended_tools=["sharp_blender_asset_pipeline", "sharp_blender_setup"],
        critical_rules=[
            "Bake high-to-low with cage/ray extrusion and clean UV island margins for SurfaceAppearance ColorMap/NormalMap/RoughnessMap.",
            "Register baked output paths as project-relative artifacts via sharp_game_library.",
        ],
        optional_toolchain=BLENDER_OPTIONAL_TOOLCHAIN,
    ),
}


STUDIO_RBX_SKILLS_CATALOG: Dict[str, Dict[str, Any]] = {
    "rbx-build": {
        "summary": "Building multi-part assemblies, structures, and level geometry cleanly in Studio.",
        "keywords": ["build", "house", "city", "castle", "tower", "bridge", "level", "map"],
    },
    "rbx-scripting": {
        "summary": "Core Studio scripting patterns, server/client separation, and debugging.",
        "keywords": ["script", "module", "server", "client", "code"],
    },
    "rbx-gameplay": {
        "summary": "General Studio gameplay mechanics, pickups, checkpoints, and interactive systems.",
        "keywords": ["gameplay", "mechanic", "pickup", "checkpoint", "door", "portal"],
    },
    "rbx-ui": {
        "summary": "Native Studio UI authoring complement to sharp_gui_build / sharp_gui_patch.",
        "keywords": ["ui", "gui", "hud", "menu", "screen", "billboard"],
    },
    "rbx-environment": {
        "summary": "Atmosphere, skyboxes, terrain materials, and ambient mood checks.",
        "keywords": ["atmosphere", "sky", "fog", "lighting", "terrain", "ambient"],
    },
    "rbx-character-animation": {
        "summary": "Rigging, character animation, and Roblox Animation Editor workflows.",
        "keywords": ["character", "avatar", "animation", "emote", "rig"],
    },
    "rbx-physics": {
        "summary": "Constraints, vehicles, assemblies, LinearVelocity, AlignOrientation, and collision groups.",
        "keywords": ["physics", "constraint", "vehicle", "car", "hinge", "spring", "collision"],
    },
    "rbx-vfx-audio": {
        "summary": "Particles, beams, trails, and spatial audio feedback.",
        "keywords": ["vfx", "particle", "sound", "audio", "trail", "beam"],
    },
    "rbx-test-verify": {
        "summary": "Runtime Studio playtest checks, output console validation, and smoke tests.",
        "keywords": ["test", "verify", "playtest", "console", "smoke"],
    },
}


class SessionSkillRegistry:
    """Tracks skill bundles inspected within the active MCP server session."""

    def __init__(self) -> None:
        self.session_id = f"sharp_sess_{uuid.uuid4().hex[:10]}"
        self.created_at = time.time()
        self.loaded_skills: Dict[str, Dict[str, Any]] = {}

    def mark_loaded(
        self,
        skill_name: str,
        *,
        include_references: bool = True,
        include_scripts: bool = True,
    ) -> None:
        self.loaded_skills[skill_name] = {
            "loaded_at": time.time(),
            "include_references": include_references,
            "include_scripts": include_scripts,
        }

    def is_loaded(self, skill_name: str) -> bool:
        return skill_name in self.loaded_skills

    def summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "loaded_count": len(self.loaded_skills),
            "loaded_skills": sorted(self.loaded_skills.keys()),
        }


class SkillRouter:
    """Routes tasks to Sharp skills with token-budgeted summaries and section-level loading."""

    def __init__(
        self,
        skills_dir: Optional[str | Path] = None,
        archive_dir: Optional[str | Path] = None,
        session_registry: Optional[SessionSkillRegistry] = None,
    ) -> None:
        self.skills_dir = resolve_default_skills_dir(skills_dir)
        self.archive_dir = resolve_default_archive_dir(archive_dir)
        self.session_registry = session_registry or SessionSkillRegistry()

    def _resolve_skill_roots(self, skill_name: str) -> List[Path]:
        roots: List[Path] = []
        primary = self.skills_dir / skill_name
        if primary.exists():
            roots.append(primary)
        bundled = BUNDLED_SKILLS_DIR / skill_name
        if bundled.exists() and bundled != primary:
            roots.append(bundled)
        if self.archive_dir and skill_name in ARCHIVE_FALLBACK_MAP:
            arch = self.archive_dir / ARCHIVE_FALLBACK_MAP[skill_name]
            if arch.exists():
                roots.append(arch)
        return roots

    def get_skill_root(self, skill_name: str) -> Optional[Path]:
        roots = self._resolve_skill_roots(skill_name)
        return roots[0] if roots else None

    def _read_skill_md(self, skill_name: str) -> tuple[str, Optional[str]]:
        for root in self._resolve_skill_roots(skill_name):
            candidate = root / "SKILL.md"
            if candidate.exists() and candidate.is_file():
                try:
                    return candidate.read_text(encoding="utf-8"), str(candidate)
                except Exception:
                    pass
        return "", None

    def _list_subfiles(self, skill_name: str, folder: str, extensions: tuple[str, ...]) -> Dict[str, Path]:
        found: Dict[str, Path] = {}
        for root in self._resolve_skill_roots(skill_name):
            sub = root / folder
            if not sub.exists() or not sub.is_dir():
                continue
            for entry in sorted(sub.iterdir()):
                if entry.is_file() and entry.suffix.lower() in extensions:
                    found.setdefault(entry.name, entry)
        return found

    @staticmethod
    def _extract_sections(markdown_text: str, max_sections: int = 16) -> List[str]:
        sections: List[str] = []
        for line in markdown_text.splitlines():
            match = re.match(r"^(#{1,3})\s+(.+?)\s*$", line)
            if match:
                heading = match.group(2).strip()
                if heading and heading not in sections:
                    sections.append(heading)
                if len(sections) >= max_sections:
                    break
        return sections

    @staticmethod
    def _extract_section_body(markdown_text: str, section_query: str) -> str:
        target = section_query.strip().lower()
        lines = markdown_text.splitlines()
        capturing = False
        capture_level = 0
        captured: List[str] = []
        for line in lines:
            match = re.match(r"^(#{1,4})\s+(.+?)\s*$", line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip().lower()
                if not capturing and (target == title or target in title):
                    capturing = True
                    capture_level = level
                    captured.append(line)
                    continue
                if capturing and level <= capture_level:
                    break
            if capturing:
                captured.append(line)
        return "\n".join(captured).strip()

    def list_available_skills(self) -> List[Dict[str, Any]]:
        """List all registered Sharp domain skills and their local resolution status."""
        items: List[Dict[str, Any]] = []
        for name, spec in DOMAIN_SKILL_SPECS.items():
            root = self.get_skill_root(name)
            md_text, md_path = self._read_skill_md(name)
            items.append(
                {
                    "name": name,
                    "category": spec.category,
                    "summary": spec.summary,
                    "optional_toolchain": spec.optional_toolchain,
                    "recommended_tools": spec.recommended_tools,
                    "has_skill_md": bool(md_text),
                    "skill_md_path": md_path,
                    "skill_root": str(root) if root else None,
                    "loaded_in_session": self.session_registry.is_loaded(name),
                }
            )
        return items

    def load_skill_bundle(
        self,
        skill_name: str,
        *,
        include_references: bool = True,
        include_scripts: bool = False,
        max_script_lines: int = 80,
        section: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Load SKILL.md (or a single section), reference docs, and script metadata for one skill."""
        if skill_name not in DOMAIN_SKILL_SPECS:
            return {
                "ok": False,
                "error": f"Unknown skill '{skill_name}'.",
                "available_skills": sorted(DOMAIN_SKILL_SPECS.keys()),
            }

        spec = DOMAIN_SKILL_SPECS[skill_name]
        md_text, md_path = self._read_skill_md(skill_name)
        sections = self._extract_sections(md_text)

        ref_map = self._list_subfiles(skill_name, "references", (".md", ".txt", ".json"))
        script_map = self._list_subfiles(skill_name, "scripts", (".py", ".luau", ".lua"))

        self.session_registry.mark_loaded(
            skill_name,
            include_references=include_references,
            include_scripts=include_scripts,
        )

        selected_md = md_text
        if section and md_text:
            extracted = self._extract_section_body(md_text, section)
            if extracted:
                selected_md = extracted

        references_out: Dict[str, str] = {}
        if include_references:
            for ref_name, ref_path in ref_map.items():
                try:
                    references_out[ref_name] = ref_path.read_text(encoding="utf-8")
                except Exception as exc:
                    references_out[ref_name] = f"<unreadable: {exc}>"

        scripts_out: Dict[str, str] = {}
        if include_scripts:
            for sc_name, sc_path in script_map.items():
                try:
                    lines = sc_path.read_text(encoding="utf-8").splitlines()
                    scripts_out[sc_name] = "\n".join(lines[:max_script_lines])
                except Exception as exc:
                    scripts_out[sc_name] = f"<unreadable: {exc}>"

        return {
            "ok": True,
            "skill_name": skill_name,
            "category": spec.category,
            "summary": spec.summary,
            "optional_toolchain": spec.optional_toolchain,
            "critical_rules": spec.critical_rules,
            "recommended_tools": spec.recommended_tools,
            "skill_md_path": md_path,
            "sections": sections,
            "section_filter": section,
            "skill_md": selected_md,
            "available_references": sorted(ref_map.keys()),
            "references": references_out,
            "available_scripts": sorted(script_map.keys()),
            "scripts": scripts_out,
            "resource_uri": f"sharp://skills/{skill_name}/SKILL.md",
        }

    def match_skills(
        self,
        task_description: str,
        *,
        target_domains: Optional[List[str]] = None,
        max_skills: int = 4,
    ) -> List[tuple[SkillMetadata, float, List[str]]]:
        """Score domain skills against ``task_description`` and optional ``target_domains``."""
        text = (task_description or "").lower()
        explicit = {d.strip().lower() for d in (target_domains or []) if d.strip()}
        scored: List[tuple[SkillMetadata, float, List[str]]] = []

        for name, spec in DOMAIN_SKILL_SPECS.items():
            score = 0.0
            hits: List[str] = []
            if name.lower() in explicit or name.replace("roblox-", "").replace("blender-", "") in explicit:
                score += 10.0
                hits.append(f"explicit:{name}")
            if spec.category in explicit:
                score += 3.0
            for kw in spec.keywords:
                if kw in text:
                    score += 2.0 if " " in kw else 1.2
                    hits.append(kw)
            if name == "roblox-luau-coding" and not hits and text:
                score += 0.5
            if score > 0:
                scored.append((spec, score, hits))

        scored.sort(key=lambda item: (-item[1], item[0].name))
        if not scored:
            default_spec = DOMAIN_SKILL_SPECS["roblox-luau-coding"]
            return [(default_spec, 0.5, ["fallback:core"])]
        return scored[: max(1, max_skills)]

    def _build_execution_dag(self, selected_names: List[str], task_lower: str, *, compact: bool = False) -> List[str]:
        if compact:
            steps: List[str] = ["Plan/Inspect: sharp_game_plan / studio_status / luau_scaffold"]
            if "roblox-terrain-atmosphere" in selected_names:
                steps.append("Terrain/Env: sharp_terrain_build -> sharp_environment_apply")
            if any(s.startswith("blender-") for s in selected_names):
                steps.append("Blender (opt): sharp_blender_setup -> asset/rig")
            if "roblox-animation" in selected_names:
                steps.append("Anim/Equip: sharp_rig_and_animation -> sharp_equipment_attach")
            if any(s in selected_names for s in (
                "roblox-combat-and-controllers",
                "roblox-audio-vfx-cutscenes",
                "roblox-data-economy-monetization",
                "roblox-ai-and-gameplay-systems",
                "roblox-world-assembly-and-optimization",
            )):
                steps.append("Systems: sharp_* domain tools")
            if "roblox-gui" in selected_names:
                steps.append("GUI: sharp_design_system -> slice_pack -> build -> inspect/diff")
            steps.append("Verify: sharp_critical_audit -> audit_all -> toolchain -> playtest")
            return steps

        dag: List[str] = []
        if "roblox-luau-coding" in selected_names or any(w in task_lower for w in ("inspect", "audit", "plan", "mvp", "scaffold", "gate")):
            dag.append("1. Plan & inspect via sharp_game_plan, sharp_studio_status, sharp_game_library & sharp_luau_scaffold")
        if "roblox-terrain-atmosphere" in selected_names:
            dag.append("2. Build terrain & atmosphere via sharp_terrain_build -> sharp_environment_apply")
        if any(s.startswith("blender-") for s in selected_names):
            dag.append("3. Optional Blender offline pass: sharp_blender_setup -> sharp_blender_asset_pipeline / sharp_blender_rig_and_anim")
        if "roblox-animation" in selected_names:
            dag.append("4. Studio rigging, animations & attachments via sharp_rig_and_animation -> sharp_equipment_attach")
        if "roblox-world-assembly-and-optimization" in selected_names:
            dag.append("5. Scatter/snap world assembly via sharp_world_assembly_and_optimization")
        if any(s.startswith("roblox-") and s in selected_names for s in (
            "roblox-combat-and-controllers",
            "roblox-audio-vfx-cutscenes",
            "roblox-data-economy-monetization",
            "roblox-ai-and-gameplay-systems",
        )):
            dag.append("6. Install gameplay/data/VFX modules via dedicated sharp_* domain tools")
        if "roblox-gui" in selected_names:
            dag.append("7. Design & verify GUI: sharp_design_system -> sharp_gui_slice_and_pack -> sharp_gui_build -> sharp_gui_inspect -> sharp_gui_patch -> sharp_visual_diff")
        dag.append("8. Verify with sharp_critical_audit, sharp_audit_all, sharp_toolchain, sharp_playtest_scenario & sharp_game_library(snapshot)")
        return dag

    def _match_native_rbx_skills(self, task_lower: str, limit: int = 3) -> List[Dict[str, str]]:
        hits: List[tuple[int, str, str]] = []
        for rbx_name, meta in STUDIO_RBX_SKILLS_CATALOG.items():
            score = sum(1 for kw in meta["keywords"] if kw in task_lower)
            if score > 0:
                hits.append((score, rbx_name, meta["summary"]))
        hits.sort(key=lambda item: (-item[0], item[1]))
        return [{"name": name, "summary": summary} for _, name, summary in hits[:limit]]

    def route_task(
        self,
        task_description: str,
        *,
        target_domains: Optional[List[str]] = None,
        detail: str = "summary",
        include_full_skill_md: Optional[bool] = None,
        max_skills: int = 4,
    ) -> Dict[str, Any]:
        """Route a Roblox/Blender task to compact Sharp skill cards or full skill documentation.

        Defaults to ``detail='summary'`` (< 3 KB typical) returning condensed rule cards and
        section indexes pointing to ``sharp_load_skill`` / ``sharp://skills/{name}/SKILL.md``.
        Pass ``detail='complete'`` to receive full ``SKILL.md`` bodies and reference docs.
        """
        effective_detail = "complete" if (detail == "complete" or include_full_skill_md is True) else "summary"
        matched = self.match_skills(
            task_description,
            target_domains=target_domains,
            max_skills=max_skills,
        )
        selected_names = [spec.name for spec, _, _ in matched]
        task_lower = (task_description or "").lower()

        skill_cards: List[Dict[str, Any]] = []
        for spec, score, hits in matched:
            md_text, _ = self._read_skill_md(spec.name)

            if effective_detail == "summary":
                sections = [s[:36] for s in self._extract_sections(md_text, max_sections=5)]
                card: Dict[str, Any] = {
                    "skill": spec.name,
                    "score": round(score, 1),
                    "rules": [r[:92] for r in spec.critical_rules[:2]],
                    "tools": spec.recommended_tools[:3],
                    "sections": sections,
                    "uri": f"sharp://skills/{spec.name}/SKILL.md",
                }
                if spec.optional_toolchain:
                    card["optional_tool"] = spec.optional_toolchain["setup_tool"]
            else:
                sections = self._extract_sections(md_text, max_sections=16)
                bundle = self.load_skill_bundle(
                    spec.name,
                    include_references=True,
                    include_scripts=True,
                )
                card = {
                    "skill": spec.name,
                    "category": spec.category,
                    "score": round(score, 2),
                    "matched_keywords": hits,
                    "summary": spec.summary,
                    "critical_rules": spec.critical_rules,
                    "recommended_tools": spec.recommended_tools,
                    "optional_toolchain": spec.optional_toolchain,
                    "sections": sections,
                    "bundle": bundle,
                }
            skill_cards.append(card)

        if effective_detail == "summary":
            return {
                "ok": True,
                "detail": "summary",
                "matched_skills": skill_cards,
                "execution_dag": self._build_execution_dag(selected_names, task_lower, compact=True),
                "native_rbx": [item["name"] for item in self._match_native_rbx_skills(task_lower)],
                "load_hint": "Use sharp_load_skill(skill_name, section=...) or sharp://skills/{name}/SKILL.md",
            }

        return {
            "ok": True,
            "detail": effective_detail,
            "task": task_description,
            "skills_dir": str(self.skills_dir),
            "matched_skills": skill_cards,
            "execution_dag": self._build_execution_dag(selected_names, task_lower, compact=False),
            "subagent_delegations": [
                {
                    "subagent_role": f"{spec.name} Specialist",
                    "skill_to_load": spec.name,
                    "load_command": f"sharp_load_skill(skill_name='{spec.name}')",
                    "primary_tools": spec.recommended_tools[:4],
                }
                for spec, _, _ in matched
            ],
            "native_rbx_skills": self._match_native_rbx_skills(task_lower),
            "session": self.session_registry.summary(),
        }

    def ensure_skill_context(self, required_skills: List[str], *, compact: bool = True) -> Dict[str, Any]:
        """Ensure required skill bundles are marked loaded for domain tools."""
        missing = [s for s in required_skills if not self.session_registry.is_loaded(s)]
        loaded_now: List[str] = []
        rules: Dict[str, List[str]] = {}
        for skill_name in required_skills:
            if skill_name in DOMAIN_SKILL_SPECS:
                self.session_registry.mark_loaded(
                    skill_name,
                    include_references=not compact,
                    include_scripts=False,
                )
                if skill_name in missing:
                    loaded_now.append(skill_name)
                rules[skill_name] = DOMAIN_SKILL_SPECS[skill_name].critical_rules[:3]
        return {
            "required": required_skills,
            "newly_marked": loaded_now,
            "critical_rules": rules,
        }

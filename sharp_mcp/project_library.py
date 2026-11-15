"""Portable Project Asset Library, Game Plan Memory, and Version Snapshot Manager for Sharp MCP."""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SERVER_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LIBRARY_ROOT = SERVER_ROOT / "game_library"

VALID_ASSET_CATEGORIES = {
    "mesh",
    "rig",
    "animation",
    "gui_9slice",
    "gui_atlas",
    "texture",
    "script_module",
    "terrain_preset",
    "scene_snapshot",
    "sfx",
    "audio",
    "misc",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sanitize_project_id(project_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "_", (project_id or "default_game").strip())
    return cleaned or "default_game"


def _bindings_file(library_root: Optional[Path] = None) -> Path:
    base = library_root or DEFAULT_LIBRARY_ROOT
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base / "place_bindings.json"
    except Exception:
        fallback = Path.home() / ".sharp" / "game_library"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / "place_bindings.json"


def resolve_project_directory(
    *,
    project_dir: Optional[str | Path] = None,
    library_root: Optional[str | Path] = None,
    project_id: str = "default_game",
    place_id: Optional[int] = None,
    cwd: Optional[str | Path] = None,
) -> Path:
    """Resolve active Sharp project directory portably with zero hardcoded user paths.

    Resolution order:
    1. Explicit ``project_dir`` argument
    2. ``SHARP_PROJECT_DIR`` environment variable
    3. Explicit ``library_root`` / ``project_id``
    4. Active ``place_id`` binding from ``place_bindings.json``
    5. Local workspace ``.sharp/<project_id>`` when ``.sharp/`` exists in ``cwd``
    6. Bundled/repo ``<server_root>/game_library/<project_id>``
    7. User fallback ``~/.sharp/game_library/<project_id>``
    """
    safe_id = _sanitize_project_id(project_id)

    if project_dir:
        return Path(project_dir).expanduser().resolve()

    env_proj = os.environ.get("SHARP_PROJECT_DIR", "").strip()
    if env_proj:
        return Path(env_proj).expanduser().resolve()

    if library_root:
        return (Path(library_root).expanduser().resolve() / safe_id).resolve()

    if place_id and int(place_id) > 0:
        for bfile in (_bindings_file(DEFAULT_LIBRARY_ROOT), _bindings_file(Path.home() / ".sharp" / "game_library")):
            if bfile.exists():
                try:
                    data = json.loads(bfile.read_text(encoding="utf-8"))
                    bound = data.get(str(int(place_id)))
                    if bound:
                        return Path(bound).expanduser().resolve()
                except Exception:
                    pass

    work_dir = Path(cwd).resolve() if cwd else Path.cwd().resolve()
    sharp_hidden = work_dir / ".sharp"
    if sharp_hidden.exists() and sharp_hidden.is_dir():
        return (sharp_hidden / safe_id).resolve()

    repo_target = DEFAULT_LIBRARY_ROOT / safe_id
    if repo_target.exists() or os.access(SERVER_ROOT, os.W_OK):
        return repo_target.resolve()

    return (Path.home() / ".sharp" / "game_library" / safe_id).resolve()


class ProjectLibraryManager:
    """Manages project assets, relative POSIX manifests, living plan markdown, and snapshots."""

    def __init__(
        self,
        library_root: Optional[str | Path] = None,
        project_id: str = "default_game",
        *,
        project_dir: Optional[str | Path] = None,
        place_id: Optional[int] = None,
    ) -> None:
        self.project_id = _sanitize_project_id(project_id)
        self.library_root = (
            Path(library_root).expanduser().resolve()
            if library_root
            else DEFAULT_LIBRARY_ROOT.resolve()
        )
        self.project_dir = resolve_project_directory(
            project_dir=project_dir,
            library_root=library_root,
            project_id=self.project_id,
            place_id=place_id,
        )
        self.assets_dir = self.project_dir / "assets"
        self.versions_dir = self.project_dir / "versions"
        self.snapshots_dir = self.versions_dir / "snapshots"

        self.manifest_path = self.assets_dir / "asset_manifest.json"
        self.luau_registry_path = self.assets_dir / "SharpAssetRegistry.luau"
        self.state_path = self.project_dir / "game_state.json"
        self.plan_json_path = self.project_dir / "plan.json"
        self.plan_md_path = self.project_dir / "GAME_PLAN.md"
        self.plan_history_path = self.versions_dir / "plan_history.json"

        self._init_or_load()

    def to_relative_posix(self, path_value: Optional[str | Path]) -> str:
        """Convert an on-disk path into a clean POSIX path relative to ``self.project_dir``."""
        if not path_value:
            return ""
        raw = str(path_value).strip().replace("\\", "/")
        if not raw:
            return ""
        p = Path(path_value)
        if not p.is_absolute():
            return p.as_posix().lstrip("./")
        try:
            resolved_p = p.expanduser().resolve()
            resolved_root = self.project_dir.resolve()
            return resolved_p.relative_to(resolved_root).as_posix()
        except Exception:
            try:
                rel = os.path.relpath(str(p.resolve()), str(self.project_dir.resolve()))
                return rel.replace("\\", "/")
            except Exception:
                return p.name

    def resolve_local_path(self, rel_or_abs: Optional[str | Path]) -> Optional[Path]:
        """Resolve a manifest relative path against ``self.project_dir``."""
        if not rel_or_abs:
            return None
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (self.project_dir / p).resolve()

    def bind_place_id(self, place_id: int) -> Dict[str, Any]:
        """Persist a ``place_id -> project_dir`` binding in ``place_bindings.json``."""
        if not place_id or int(place_id) <= 0:
            return {"ok": False, "error": "place_id must be a positive integer."}
        bfile = _bindings_file(self.library_root)
        bindings: Dict[str, str] = {}
        if bfile.exists():
            try:
                bindings = json.loads(bfile.read_text(encoding="utf-8"))
            except Exception:
                bindings = {}
        bindings[str(int(place_id))] = str(self.project_dir)
        self._write_json(bfile, bindings)
        return {
            "ok": True,
            "place_id": int(place_id),
            "project_dir": str(self.project_dir),
            "bindings_file": str(bfile),
        }

    def _init_or_load(self) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        for sub in (
            self.assets_dir,
            self.assets_dir / "gui_images" / "raw",
            self.assets_dir / "gui_images" / "sliced",
            self.assets_dir / "gui_images" / "atlases",
            self.assets_dir / "meshes",
            self.assets_dir / "rigs",
            self.assets_dir / "animations",
            self.assets_dir / "audio",
            self.project_dir / "artifacts",
            self.snapshots_dir,
        ):
            sub.mkdir(parents=True, exist_ok=True)

        if not self.manifest_path.exists():
            self._write_json(
                self.manifest_path,
                {
                    "project_id": self.project_id,
                    "schema_version": 2,
                    "updated_at": _utc_now_iso(),
                    "assets": {},
                },
            )

        if not self.state_path.exists():
            self._write_json(
                self.state_path,
                {
                    "project_id": self.project_id,
                    "game_title": self.project_id.replace("_", " ").title(),
                    "genre": "Roblox Experience",
                    "description": "Living Roblox game build tracked by Sharp MCP.",
                    "current_version": 0,
                    "active_studio_place_id": 0,
                    "updated_at": _utc_now_iso(),
                    "systems": {},
                    "planned_milestones": [],
                    "completed_milestones": [],
                    "recent_actions": [],
                },
            )

        if not self.plan_history_path.exists():
            self._write_json(self.plan_history_path, [])

        # Remove legacy ForgeAssetRegistry.luau if encountered during first load.
        legacy_registry = self.assets_dir / "ForgeAssetRegistry.luau"
        if legacy_registry.exists():
            try:
                legacy_registry.unlink()
            except Exception:
                pass

        if not self.plan_md_path.exists() or not self.luau_registry_path.exists():
            self._regenerate_markdown_and_luau()

    @staticmethod
    def _read_json(path: Path, default: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def load_manifest(self) -> Dict[str, Any]:
        return self._read_json(
            self.manifest_path,
            {"project_id": self.project_id, "schema_version": 2, "updated_at": _utc_now_iso(), "assets": {}},
        )

    def load_state(self) -> Dict[str, Any]:
        return self._read_json(
            self.state_path,
            {"project_id": self.project_id, "current_version": 0, "systems": {}, "recent_actions": []},
        )

    def load_plan_history(self) -> List[Dict[str, Any]]:
        return self._read_json(self.plan_history_path, [])

    def load_plan(self) -> Optional[Dict[str, Any]]:
        """Return parsed ``plan.json`` if created by ``GamePlanner``, otherwise ``None``."""
        if not self.plan_json_path.exists():
            return None
        data = self._read_json(self.plan_json_path, None)
        return data if isinstance(data, dict) else None

    def save_state(self, state: Dict[str, Any], *, regenerate: bool = True) -> Dict[str, Any]:
        """Persist updated ``game_state.json`` and optionally regenerate markdown/Luau."""
        state["updated_at"] = _utc_now_iso()
        self._write_json(self.state_path, state)
        if regenerate:
            self._regenerate_markdown_and_luau()
        return state

    def save_plan(
        self,
        plan_data: Dict[str, Any],
        *,
        state_updates: Optional[Dict[str, Any]] = None,
        snapshot_summary: Optional[str] = None,
        tool_name: str = "sharp_game_plan",
        target_domain: str = "game_plan",
    ) -> Dict[str, Any]:
        """Persist ``plan.json`` + ``game_state.json``, regenerate ``GAME_PLAN.md``, and optionally snapshot."""
        self._write_json(self.plan_json_path, plan_data)
        state = self.load_state()
        if plan_data.get("title"):
            state["game_title"] = str(plan_data["title"])
        if plan_data.get("genre"):
            state["genre"] = str(plan_data["genre"])
        if plan_data.get("pitch"):
            state["description"] = str(plan_data["pitch"])
        if "design_system" in plan_data and plan_data["design_system"] is not None:
            state["design_system"] = plan_data["design_system"]
        if state_updates:
            for k, v in state_updates.items():
                state[k] = v
        self.save_state(state, regenerate=not bool(snapshot_summary))

        snapshot_info: Optional[Dict[str, Any]] = None
        if snapshot_summary:
            snapshot_info = self.record_tool_execution(
                tool_name=tool_name,
                action_summary=snapshot_summary,
                target_domain=target_domain,
                parameters={"plan_id": plan_data.get("plan_id"), "stage": state.get("current_stage")},
                result_summary={"current_stage": state.get("current_stage"), "mvp_unlocked": state.get("mvp_unlocked")},
            )
        return {
            "ok": True,
            "plan_json_path": self.to_relative_posix(self.plan_json_path),
            "plan_md_path": self.to_relative_posix(self.plan_md_path),
            "snapshot": snapshot_info,
        }

    def save_design_system(self, design_system: Dict[str, Any], *, snapshot: bool = False) -> Dict[str, Any]:
        """Store design-system tokens under project key ``design_system`` in state and plan."""
        state = self.load_state()
        state["design_system"] = design_system
        plan = self.load_plan()
        if isinstance(plan, dict):
            plan["design_system"] = design_system
            self._write_json(self.plan_json_path, plan)
        self.save_state(state, regenerate=not snapshot)
        snap = None
        if snapshot:
            snap = self.record_tool_execution(
                tool_name="sharp_design_system",
                action_summary="Saved project design_system palette and tokens",
                target_domain="design_system",
                result_summary={"palette_id": design_system.get("seed"), "harmony": design_system.get("harmony")},
            )
        return {"ok": True, "design_system": design_system, "snapshot": snap}

    def get_design_system(self) -> Optional[Dict[str, Any]]:
        """Retrieve stored ``design_system`` from project state or ``plan.json``."""
        state = self.load_state()
        ds = state.get("design_system")
        if isinstance(ds, dict) and ds:
            return ds
        plan = self.load_plan()
        if isinstance(plan, dict) and isinstance(plan.get("design_system"), dict) and plan.get("design_system"):
            return plan["design_system"]
        return None

    def register_asset(
        self,
        *,
        name: str,
        category: str,
        roblox_asset_id: Optional[str] = None,
        local_path: Optional[str] = None,
        description: str = "",
        prompt_used: str = "",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        asset_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register or update a generated, local, or published Roblox asset using relative paths."""
        cat = category if category in VALID_ASSET_CATEGORIES else "misc"
        manifest = self.load_manifest()
        assets = manifest.setdefault("assets", {})

        slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
        key = asset_key or f"{cat}_{slug}"

        existing = assets.get(key, {})
        version_num = int(existing.get("version", 0)) + 1

        rel_local = self.to_relative_posix(local_path) if local_path else existing.get("local_path", "")
        sha = existing.get("sha256")
        if rel_local:
            abs_p = self.resolve_local_path(rel_local)
            if abs_p and abs_p.exists() and abs_p.is_file():
                sha = _sha256_file(abs_p)

        entry = {
            "key": key,
            "name": name,
            "category": cat,
            "roblox_asset_id": roblox_asset_id if roblox_asset_id is not None else existing.get("roblox_asset_id", ""),
            "local_path": rel_local,
            "sha256": sha,
            "description": description or existing.get("description", ""),
            "prompt_used": prompt_used or existing.get("prompt_used", ""),
            "tags": sorted(set((tags or []) + existing.get("tags", []))),
            "metadata": {**existing.get("metadata", {}), **(metadata or {})},
            "version": version_num,
            "created_at": existing.get("created_at") or _utc_now_iso(),
            "updated_at": _utc_now_iso(),
        }
        assets[key] = entry
        manifest["updated_at"] = _utc_now_iso()
        manifest["schema_version"] = 2
        self._write_json(self.manifest_path, manifest)

        self._regenerate_markdown_and_luau()
        return {"ok": True, "asset_key": key, "asset": entry}

    def find_assets(
        self,
        *,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        query: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        manifest = self.load_manifest()
        out: List[Dict[str, Any]] = []
        q = (query or "").strip().lower()
        for entry in manifest.get("assets", {}).values():
            if category and entry.get("category") != category:
                continue
            if tag and tag not in entry.get("tags", []):
                continue
            if q and q not in json.dumps(entry).lower():
                continue
            out.append(entry)
        return sorted(out, key=lambda x: x.get("key", ""))

    def seed_existing_verified_assets(self) -> Dict[str, Any]:
        """Scan ``assets/`` for on-disk project files and register relative paths without user-specific paths."""
        candidates = [
            {
                "asset_key": "gui_9slice_panel_raw",
                "name": "Dark Sci-Fi Panel Raw",
                "category": "gui_9slice",
                "rel": "assets/gui_images/raw/roblox_panel_9slice_1794652695001.jpg",
                "description": "Raw generated fantasy/sci-fi dark bevel GUI panel.",
                "tags": ["gui", "panel", "raw"],
            },
            {
                "asset_key": "gui_9slice_button_raw",
                "name": "Button Tint Raw",
                "category": "gui_9slice",
                "rel": "assets/gui_images/raw/button_tint_9slice_1794652696255.jpg",
                "description": "Raw generated interactive GUI button base.",
                "tags": ["gui", "button", "raw"],
            },
            {
                "asset_key": "gui_icons_2x2_raw",
                "name": "Icons 2x2 Sheet Raw",
                "category": "gui_atlas",
                "rel": "assets/gui_images/raw/icons_2x2_sheet_1794652702333.jpg",
                "description": "Raw 2x2 generated game UI icon grid (coin, sword, shield, gem).",
                "tags": ["gui", "icons", "raw"],
            },
            {
                "asset_key": "gui_9slice_panel_sliced",
                "name": "Clean 9-Slice Panel Frame",
                "category": "gui_9slice",
                "rel": "assets/gui_images/sliced/panel_9slice.png",
                "roblox_asset_id": "rbxassetid://80876207713837",
                "description": "Sliced transparent RGBA panel ready for ImageLabel ScaleType=Slice.",
                "tags": ["gui", "panel", "9slice", "sliced"],
            },
            {
                "asset_key": "gui_9slice_button_sliced",
                "name": "Clean 9-Slice Button Frame",
                "category": "gui_9slice",
                "rel": "assets/gui_images/sliced/button_tint_9slice.png",
                "roblox_asset_id": "rbxassetid://81663401292241",
                "description": "Sliced transparent RGBA white-tint button ready for ImageButton ScaleType=Slice.",
                "tags": ["gui", "button", "9slice", "sliced"],
            },
            {
                "asset_key": "gui_icons_atlas_packed",
                "name": "Packed 2x2 Icons Atlas",
                "category": "gui_atlas",
                "rel": "assets/gui_images/atlases/icons_atlas.png",
                "roblox_asset_id": "rbxassetid://138800051672133",
                "description": "Transparent packed 512x512 2x2 icon spritesheet (coin, sword, shield, gem).",
                "tags": ["gui", "atlas", "icons"],
            },
        ]

        seeded: List[str] = []
        for item in candidates:
            target = self.project_dir / item["rel"]
            if target.exists() and target.is_file():
                self.register_asset(
                    asset_key=item["asset_key"],
                    name=item["name"],
                    category=item["category"],
                    roblox_asset_id=item.get("roblox_asset_id", ""),
                    local_path=item["rel"],
                    description=item["description"],
                    tags=item["tags"],
                )
                seeded.append(item["asset_key"])

        return {"ok": True, "seeded_count": len(seeded), "seeded_keys": seeded}

    def record_tool_execution(
        self,
        *,
        tool_name: str,
        action_summary: str,
        target_domain: str,
        studio_place_id: Optional[int] = None,
        luau_source: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        result_summary: Optional[Dict[str, Any]] = None,
        milestone_completed: Optional[str] = None,
        asset_keys_touched: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Record an action into ``game_state.json`` and save versioned snapshot ``vNNNN.json``."""
        state = self.load_state()
        manifest = self.load_manifest()

        new_ver = int(state.get("current_version", 0)) + 1
        version_tag = f"v{new_ver:04d}"
        ts = _utc_now_iso()

        if studio_place_id:
            state["active_studio_place_id"] = studio_place_id

        systems = state.setdefault("systems", {})
        sys_entry = systems.setdefault(
            target_domain,
            {"status": "active", "executions": 0, "last_updated": ts, "last_summary": ""},
        )
        sys_entry["status"] = "active"
        sys_entry["executions"] = int(sys_entry.get("executions", 0)) + 1
        sys_entry["last_updated"] = ts
        sys_entry["last_summary"] = action_summary
        sys_entry["last_version"] = version_tag

        if milestone_completed:
            done = state.setdefault("completed_milestones", [])
            if milestone_completed not in done:
                done.append(milestone_completed)
            planned = state.setdefault("planned_milestones", [])
            if milestone_completed in planned:
                planned.remove(milestone_completed)

        snapshot_id = f"{version_tag}_{uuid.uuid4().hex[:6]}"
        snapshot_file = self.snapshots_dir / f"{version_tag}.json"
        luau_hash = hashlib.sha256((luau_source or "").encode("utf-8")).hexdigest()[:16] if luau_source else None

        state_snap_payload: Dict[str, Any] = {
            "game_title": state.get("game_title"),
            "systems": systems,
            "completed_milestones": state.get("completed_milestones", []),
        }
        for planner_key in ("current_stage", "mvp_unlocked", "planner_stages", "design_system"):
            if planner_key in state:
                state_snap_payload[planner_key] = state[planner_key]

        snapshot_payload = {
            "version": new_ver,
            "version_tag": version_tag,
            "snapshot_id": snapshot_id,
            "timestamp": ts,
            "tool_name": tool_name,
            "target_domain": target_domain,
            "action_summary": action_summary,
            "parameters": parameters or {},
            "result_summary": result_summary or {},
            "luau_sha256_prefix": luau_hash,
            "luau_source": luau_source,
            "asset_keys_touched": asset_keys_touched or [],
            "state_snapshot": state_snap_payload,
            "manifest_snapshot": manifest,
        }
        self._write_json(snapshot_file, snapshot_payload)

        state["current_version"] = new_ver
        state["updated_at"] = ts
        recent = state.setdefault("recent_actions", [])
        recent.append(
            {
                "version": new_ver,
                "version_tag": version_tag,
                "timestamp": ts,
                "tool": tool_name,
                "domain": target_domain,
                "summary": action_summary,
                "snapshot_file": self.to_relative_posix(snapshot_file),
            }
        )
        state["recent_actions"] = recent[-50:]
        self._write_json(self.state_path, state)

        history = self.load_plan_history()
        history.append(
            {
                "version": new_ver,
                "version_tag": version_tag,
                "timestamp": ts,
                "tool_name": tool_name,
                "target_domain": target_domain,
                "summary": action_summary,
                "snapshot_path": self.to_relative_posix(snapshot_file),
                "asset_count": len(manifest.get("assets", {})),
            }
        )
        self._write_json(self.plan_history_path, history)

        self._regenerate_markdown_and_luau()
        return {
            "ok": True,
            "version": new_ver,
            "version_tag": version_tag,
            "snapshot_path": self.to_relative_posix(snapshot_file),
        }

    def update_plan_metadata(
        self,
        *,
        game_title: Optional[str] = None,
        genre: Optional[str] = None,
        description: Optional[str] = None,
        add_milestones: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        state = self.load_state()
        if game_title:
            state["game_title"] = game_title
        if genre:
            state["genre"] = genre
        if description:
            state["description"] = description
        if add_milestones:
            planned = state.setdefault("planned_milestones", [])
            done = set(state.get("completed_milestones", []))
            for m in add_milestones:
                if m not in planned and m not in done:
                    planned.append(m)
        state["updated_at"] = _utc_now_iso()
        self._write_json(self.state_path, state)
        self._regenerate_markdown_and_luau()
        return {"ok": True, "state": state}

    def list_versions(self, limit: int = 20) -> List[Dict[str, Any]]:
        history = self.load_plan_history()
        return history[-limit:][::-1]

    def get_snapshot(self, version: int) -> Optional[Dict[str, Any]]:
        snap_path = self.snapshots_dir / f"v{int(version):04d}.json"
        if not snap_path.exists():
            return None
        return self._read_json(snap_path, None)

    def diff_versions(self, from_version: Optional[int] = None, to_version: Optional[int] = None) -> Dict[str, Any]:
        """Compare asset manifest, active systems, and completed milestones between two snapshots."""
        state = self.load_state()
        cur = int(state.get("current_version", 0))
        if cur < 1:
            return {"ok": False, "error": "No version snapshots recorded yet."}
        v_to = to_version or cur
        v_from = from_version or max(1, v_to - 1)

        snap_a = self.get_snapshot(v_from)
        snap_b = self.get_snapshot(v_to)
        if not snap_a or not snap_b:
            return {"ok": False, "error": f"Snapshot not found for v{v_from:04d} or v{v_to:04d}."}

        assets_a = snap_a.get("manifest_snapshot", {}).get("assets", {})
        assets_b = snap_b.get("manifest_snapshot", {}).get("assets", {})

        added_assets = [k for k in assets_b if k not in assets_a]
        removed_assets = [k for k in assets_a if k not in assets_b]
        updated_assets = [
            k for k in assets_b
            if k in assets_a and (
                assets_b[k].get("version") != assets_a[k].get("version")
                or assets_b[k].get("roblox_asset_id") != assets_a[k].get("roblox_asset_id")
            )
        ]

        sys_a = snap_a.get("state_snapshot", {}).get("systems", {})
        sys_b = snap_b.get("state_snapshot", {}).get("systems", {})
        changed_systems = {
            k: sys_b[k]
            for k in sys_b
            if k not in sys_a or sys_b[k].get("last_version") != sys_a[k].get("last_version")
        }

        return {
            "ok": True,
            "from_version": f"v{v_from:04d}",
            "to_version": f"v{v_to:04d}",
            "assets_added": added_assets,
            "assets_removed": removed_assets,
            "assets_updated": updated_assets,
            "systems_changed": list(changed_systems.keys()),
            "to_action_summary": snap_b.get("action_summary"),
            "to_tool_name": snap_b.get("tool_name"),
        }

    def rollback_version(self, target_version: int, apply_to_studio_files: bool = True) -> Dict[str, Any]:
        """Restore manifest/state snapshot to ``target_version`` and record an audit rollback entry."""
        snap = self.get_snapshot(target_version)
        if not snap:
            return {"ok": False, "error": f"Version v{int(target_version):04d} does not exist."}

        manifest_restored = snap.get("manifest_snapshot")
        state_snap = snap.get("state_snapshot", {})
        current_state = self.load_state()

        if apply_to_studio_files and manifest_restored:
            self._write_json(self.manifest_path, manifest_restored)

        current_state["systems"] = state_snap.get("systems", current_state.get("systems", {}))
        current_state["completed_milestones"] = state_snap.get("completed_milestones", [])
        for planner_key in ("current_stage", "mvp_unlocked", "planner_stages", "design_system"):
            if planner_key in state_snap:
                current_state[planner_key] = state_snap[planner_key]
        current_state["updated_at"] = _utc_now_iso()
        self._write_json(self.state_path, current_state)

        rec = self.record_tool_execution(
            tool_name="sharp_game_library",
            action_summary=f"Rolled back library/state to snapshot v{int(target_version):04d}",
            target_domain="library_rollback",
            luau_source=snap.get("luau_source"),
            parameters={"target_version": target_version},
        )
        return {
            "ok": True,
            "rolled_back_to": f"v{int(target_version):04d}",
            "new_audit_version": rec["version_tag"],
            "luau_replay_available": bool(snap.get("luau_source")),
            "luau_source": snap.get("luau_source"),
        }

    def _regenerate_markdown_and_luau(self) -> None:
        state = self.load_state()
        manifest = self.load_manifest()
        history = self.load_plan_history()

        assets = manifest.get("assets", {})
        by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for entry in assets.values():
            by_cat.setdefault(entry.get("category", "misc"), []).append(entry)

        lines: List[str] = [
            f"# {state.get('game_title', self.project_id)} — Living Game Plan & Asset Registry",
            "",
            f"- **Project ID:** `{self.project_id}`",
            f"- **Genre:** {state.get('genre', 'Roblox Experience')}",
            f"- **Current Version:** `v{int(state.get('current_version', 0)):04d}`",
            f"- **Active Studio PlaceId:** `{state.get('active_studio_place_id', 0)}`",
            f"- **Last Updated:** `{_utc_now_iso()}`",
            "",
            f"> {state.get('description', '')}",
            "",
            "---",
            "",
            "## 1. Installed & Active Game Systems",
            "",
            "| Domain | Status | Executions | Last Version | Last Action |",
            "|---|---|---:|---|---|",
        ]

        systems = state.get("systems", {})
        if not systems:
            lines.append("| *(none yet)* | - | 0 | - | Use Sharp domain tools to build |")
        else:
            for dom, info in sorted(systems.items()):
                lines.append(
                    f"| `{dom}` | {info.get('status', 'active')} | {info.get('executions', 0)} | "
                    f"`{info.get('last_version', '-')}` | {info.get('last_summary', '')} |"
                )

        lines.extend(["", "## 2. Milestones", ""])
        for m in state.get("completed_milestones", []):
            lines.append(f"- [x] {m}")
        for m in state.get("planned_milestones", []):
            lines.append(f"- [ ] {m}")
        if not state.get("completed_milestones") and not state.get("planned_milestones"):
            lines.append("- [ ] Initial world, core gameplay loop, UI, and economy verification")

        lines.extend(["", "## 3. Registered Asset Library", ""])
        if not assets:
            lines.append("_No assets registered yet._")
        else:
            for cat in sorted(by_cat.keys()):
                lines.append(f"### `{cat}` ({len(by_cat[cat])})")
                lines.append("")
                lines.append("| Key | Name | Roblox Asset ID | Local Path (Relative) | Ver |")
                lines.append("|---|---|---|---|---:|")
                for a in sorted(by_cat[cat], key=lambda x: x.get("key", "")):
                    rid = a.get("roblox_asset_id") or "-"
                    lpath = a.get("local_path") or "-"
                    lines.append(
                        f"| `{a['key']}` | {a.get('name', '')} | `{rid}` | `{lpath}` | v{a.get('version', 1)} |"
                    )
                lines.append("")

        lines.extend(["## 4. Recent Version Timeline", ""])
        lines.append("| Version | Timestamp | Tool | Domain | Summary |")
        lines.append("|---|---|---|---|---|")
        for h in history[-15:][::-1]:
            lines.append(
                f"| `{h.get('version_tag', '')}` | `{h.get('timestamp', '')}` | `{h.get('tool_name', '')}` | "
                f"`{h.get('target_domain', '')}` | {h.get('summary', '')} |"
            )

        plan_doc = self.load_plan()
        design_sys = state.get("design_system") or (plan_doc.get("design_system") if isinstance(plan_doc, dict) else None)
        if isinstance(plan_doc, dict):
            lines.extend(["", "---", "", "## 5. Structured Game Plan & MVP Architecture", ""])
            pillars = plan_doc.get("pillars") or []
            if pillars:
                lines.append("### Design Pillars")
                for p in pillars:
                    lines.append(f"- {p}")
                lines.append("")

            core_loop = plan_doc.get("core_loop") or {}
            if isinstance(core_loop, dict) and core_loop:
                lines.append("### Core Loop")
                lines.append(f"- **Summary:** {core_loop.get('summary', '')}")
                for idx, step in enumerate(core_loop.get("steps", []), start=1):
                    lines.append(f"  {idx}. {step}")
                lines.append(f"- **Target Session Length:** {plan_doc.get('session_length_min', 10)} min")
                lines.append("")

            mvp = plan_doc.get("mvp_scope") or {}
            if isinstance(mvp, dict) and mvp:
                lines.append("### MVP Scope (Strict: ONE Playable Loop)")
                lines.append(f"- **Single Playable Loop:** {mvp.get('single_playable_loop', '')}")
                lines.append(f"- **In-Scope Systems:** {', '.join(mvp.get('in_scope_mvp_systems', []))}")
                lines.append(f"- **Vertical Slice Target:** {mvp.get('vertical_slice_target', '')}")
                lines.append("")

            cut_list = plan_doc.get("cut_list") or []
            if cut_list:
                lines.append("### Cut List (Deferred Post-MVP)")
                for item in cut_list:
                    if isinstance(item, dict):
                        lines.append(
                            f"- `{item.get('id', 'CUT')}` **{item.get('feature', '')}** -> "
                            f"Target: `{item.get('target_stage', 'post_mvp')}` — {item.get('reason_cut', '')}"
                        )
                lines.append("")

            dag = plan_doc.get("systems_dependency_dag") or []
            if dag:
                lines.append("### Systems Dependency DAG")
                lines.append("| System | Stage | Depends On | Tool |")
                lines.append("|---|---|---|---|")
                for node in dag:
                    if isinstance(node, dict):
                        deps = ", ".join(node.get("depends_on") or []) or "-"
                        lines.append(
                            f"| `{node.get('id', '')}` ({node.get('name', '')}) | `{node.get('stage', '')}` | `{deps}` | `{node.get('tool', '')}` |"
                        )
                lines.append("")

            risks = plan_doc.get("risk_register") or []
            if risks:
                lines.append("### Risk Register")
                lines.append("| ID | Severity | Stage | Risk | Mitigation |")
                lines.append("|---|---|---|---|---|")
                for r in risks:
                    if isinstance(r, dict):
                        lines.append(
                            f"| `{r.get('id', '')}` | {r.get('severity', 'MAJOR')} | `{r.get('owner_stage', '')}` | "
                            f"{r.get('risk', '')} | {r.get('mitigation', '')} |"
                        )
                lines.append("")

            budget = plan_doc.get("asset_budget") or {}
            if isinstance(budget, dict) and budget:
                lines.append("### Asset & Performance Budget")
                for k, v in budget.items():
                    lines.append(f"- **{k}:** `{json.dumps(v) if isinstance(v, (dict, list)) else v}`")
                lines.append("")

            stages = state.get("planner_stages") or plan_doc.get("stages") or []
            if stages:
                lines.append("### Stage Gates & Acceptance Criteria (MVP-First Lock)")
                lines.append("| Stage | Phase | Status | Gate Steps | Acceptance Criteria |")
                lines.append("|---|---|---|---|---|")
                for st in stages:
                    if isinstance(st, dict):
                        ac = "; ".join(st.get("acceptance_criteria") or [])
                        steps_desc = ", ".join(
                            f"{s.get('step_id')}:{'DONE' if s.get('completed') else 'PENDING'}"
                            for s in (st.get("steps") or [])
                        )
                        lines.append(
                            f"| `{st.get('stage_id')}` {st.get('name', '')} | {st.get('phase', '')} | "
                            f"{st.get('status', 'locked')} | `{steps_desc}` | {ac} |"
                        )
                lines.append("")

        if isinstance(design_sys, dict) and design_sys:
            lines.extend(["", "### Design System Slot (`design_system`)", ""])
            palette = design_sys.get("palette") or design_sys.get("colors") or {}
            lines.append(f"- **Harmony:** `{design_sys.get('harmony', 'custom')}` (seed `{design_sys.get('seed', '-')}`)")
            if isinstance(palette, dict):
                swatches = ", ".join(f"`{k}: {v}`" for k, v in list(palette.items())[:12])
                lines.append(f"- **Palette:** {swatches}")
            lines.append("")

        self.plan_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        luau_code = self._build_luau_registry_source(state, manifest)
        self.luau_registry_path.write_text(luau_code, encoding="utf-8")

    def _build_luau_registry_source(self, state: Dict[str, Any], manifest: Dict[str, Any]) -> str:
        assets = manifest.get("assets", {})
        entries_lines: List[str] = []
        for k in sorted(assets.keys()):
            a = assets[k]
            rid = json.dumps(a.get("roblox_asset_id") or "", ensure_ascii=False)
            cat = json.dumps(a.get("category") or "misc", ensure_ascii=False)
            name = json.dumps(a.get("name") or k, ensure_ascii=False)
            local_p = json.dumps(a.get("local_path") or "", ensure_ascii=False)
            entries_lines.append(
                f"\t[{json.dumps(k, ensure_ascii=False)}] = {{ Name = {name}, Category = {cat}, AssetId = {rid}, LocalPath = {local_p}, Version = {int(a.get('version', 1))} }},"
            )

        systems_luau = "{ " + ", ".join(json.dumps(key, ensure_ascii=False) for key in sorted(state.get("systems", {}))) + " }"
        ver_str = f"v{int(state.get('current_version', 0)):04d}"

        return (
            "--!strict\n"
            "-- Auto-generated by Sharp MCP ProjectLibraryManager\n"
            "-- Mirror inside ReplicatedStorage/Shared/SharpAssetRegistry.luau\n\n"
            "export type RegisteredAsset = {\n"
            "\tName: string,\n"
            "\tCategory: string,\n"
            "\tAssetId: string,\n"
            "\tLocalPath: string,\n"
            "\tVersion: number,\n"
            "}\n\n"
            "local SharpAssetRegistry = {}\n\n"
            f"SharpAssetRegistry.ProjectId = {json.dumps(self.project_id, ensure_ascii=False)}\n"
            f"SharpAssetRegistry.Version = {json.dumps(ver_str)}\n"
            f"SharpAssetRegistry.Systems = {systems_luau}\n\n"
            "SharpAssetRegistry.Assets = {\n"
            + ("\n".join(entries_lines) + "\n" if entries_lines else "")
            + "} :: { [string]: RegisteredAsset }\n\n"
            "function SharpAssetRegistry.GetAssetId(key: string): string?\n"
            "\tlocal item = SharpAssetRegistry.Assets[key]\n"
            "\tif item and item.AssetId ~= \"\" then\n"
            "\t\treturn item.AssetId\n"
            "\tend\n"
            "\treturn nil\n"
            "end\n\n"
            "return SharpAssetRegistry\n"
        )

    def compile_studio_sync_luau(self) -> str:
        """Compile a Luau snippet mirroring SharpAssetRegistry & GAME_PLAN into Studio."""
        luau_src = self.luau_registry_path.read_text(encoding="utf-8")
        md_src = self.plan_md_path.read_text(encoding="utf-8")
        state = self.load_state()
        ver_tag = f"v{int(state.get('current_version', 0)):04d}"

        return f"""local ChangeHistoryService = game:GetService("ChangeHistoryService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local ServerStorage = game:GetService("ServerStorage")

local activePluginRec = ChangeHistoryService:GetAttribute("__SharpActiveRecordingId")
local recId = if activePluginRec then nil else ChangeHistoryService:TryBeginRecording("SharpLibrarySync", "Sharp MCP: Sync Project AssetRegistry & Game Plan")

local ok, err = pcall(function()
    local sharedFolder = ReplicatedStorage:FindFirstChild("Shared")
    if not sharedFolder then
        sharedFolder = Instance.new("Folder")
        sharedFolder.Name = "Shared"
        sharedFolder.Parent = ReplicatedStorage
    end

    local mod = sharedFolder:FindFirstChild("SharpAssetRegistry")
    if not mod or not mod:IsA("ModuleScript") then
        if mod then mod:Destroy() end
        mod = Instance.new("ModuleScript")
        mod.Name = "SharpAssetRegistry"
        mod.Parent = sharedFolder
    end
    (mod :: ModuleScript).Source = {json.dumps(luau_src, ensure_ascii=False)}

    local libFolder = ServerStorage:FindFirstChild("_SharpProjectLibrary")
    if not libFolder then
        libFolder = Instance.new("Folder")
        libFolder.Name = "_SharpProjectLibrary"
        libFolder.Parent = ServerStorage
    end

    local planDoc = libFolder:FindFirstChild("GAME_PLAN")
    if not planDoc or not planDoc:IsA("StringValue") then
        if planDoc then planDoc:Destroy() end
        planDoc = Instance.new("StringValue")
        planDoc.Name = "GAME_PLAN"
        planDoc.Parent = libFolder
    end
    (planDoc :: StringValue).Value = {json.dumps(md_src, ensure_ascii=False)}
    libFolder:SetAttribute("ProjectId", {json.dumps(self.project_id, ensure_ascii=False)})
    libFolder:SetAttribute("Version", {json.dumps(ver_tag)})
end)

if recId then
    ChangeHistoryService:FinishRecording(recId, if ok then Enum.FinishRecordingOperation.Commit else Enum.FinishRecordingOperation.Cancel)
end
assert(ok, "SharpLibrarySync failed: " .. tostring(err))
print(string.format("[SharpLibrarySync] Synced SharpAssetRegistry & GAME_PLAN (%s) cleanly.", {json.dumps(ver_tag)}))
"""

    def generate_image_prompt(
        self,
        *,
        subject: str,
        style: str = "stylized PBR fantasy-sci-fi Roblox game asset",
        asset_type: str = "ui_icon",
        aspect_ratio: str = "1:1",
    ) -> Dict[str, Any]:
        """Construct a structured prompt recipe ready for external 2D image generators."""
        type_rules = {
            "9slice_panel": "centered symmetrical rounded rectangular UI panel frame, solid black background for transparency keying, uniform outer rim bevel, flat dark matte interior",
            "9slice_button": "centered symmetrical rounded pill UI button frame, pure white/neutral grayscale tintable fill, soft highlight top edge, solid black outer backdrop",
            "ui_icon": "clean bold game UI icon centered in square tile, crisp silhouette, thick outline, zero text, solid flat backdrop",
            "icon_grid_2x2": "exact 2x2 grid of 4 centered game UI icons separated by wide clear margins, crisp silhouettes, zero text, dark solid backdrop",
            "texture": "seamless tileable 2D PBR surface texture, flat orthographic lighting, zero perspective distortion, zero watermark",
        }
        rule_hint = type_rules.get(asset_type, type_rules["ui_icon"])
        prompt = f"{subject}, {style}, {rule_hint}, aspect ratio {aspect_ratio}, high contrast, game production asset"
        return {
            "ok": True,
            "asset_type": asset_type,
            "aspect_ratio": aspect_ratio,
            "prompt": prompt,
            "negative_prompt": "blurry, watermark, signature, text labels, cropped edges, noisy clutter, photorealistic perspective",
            "suggested_next_step": "Save generated image inside assets/gui_images/raw/ and call sharp_gui_slice_and_pack -> sharp_game_library(action='register_asset').",
        }

    def get_status_summary(self, *, detail: str = "summary") -> Dict[str, Any]:
        """Return compact library status by default, or complete asset inventory when ``detail='complete'``."""
        state = self.load_state()
        manifest = self.load_manifest()
        assets = manifest.get("assets", {})
        by_category: Dict[str, int] = {}
        for item in assets.values():
            c = item.get("category", "misc")
            by_category[c] = by_category.get(c, 0) + 1

        base: Dict[str, Any] = {
            "ok": True,
            "detail": detail,
            "project_id": self.project_id,
            "project_dir": str(self.project_dir),
            "game_title": state.get("game_title"),
            "current_version": f"v{int(state.get('current_version', 0)):04d}",
            "active_studio_place_id": state.get("active_studio_place_id", 0),
            "total_assets": len(assets),
            "assets_by_category": by_category,
            "systems_count": len(state.get("systems", {})),
            "active_systems": sorted(state.get("systems", {}).keys()),
            "has_structured_plan": self.plan_json_path.exists(),
            "has_design_system": bool(state.get("design_system")),
            "current_stage": state.get("current_stage"),
            "mvp_unlocked": bool(state.get("mvp_unlocked", False)),
            "plan_md_path": self.to_relative_posix(self.plan_md_path),
            "luau_registry_path": self.to_relative_posix(self.luau_registry_path),
            "recent_versions": self.list_versions(limit=5),
        }
        if detail == "complete":
            base["manifest"] = manifest
            base["state"] = state
        return base

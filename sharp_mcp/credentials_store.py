"""Unified OpenRouter & Gemini API Credentials Store and Model Router for Sharp MCP.

Stores keys strictly outside version control (default: ``~/.sharp-mcp/credentials.json`` or
``SHARP_CREDENTIALS_PATH`` / ``SHARP_HOME``), prefers explicit environment variables when set,
never echoes raw secrets in responses, and curates affordable high-craft default models.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SUPPORTED_PROVIDERS: Tuple[str, ...] = ("gemini", "openrouter")

ENV_KEY_NAMES: Dict[str, Tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
}

# Curated defaults emphasizing low-cost, high-speed, anti-slop vision/UI/code capable models.
MODEL_PRESETS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "gemini": {
        "video": {
            "default": "gemini-2.5-flash",
            "budget": "gemini-2.5-flash-lite",
            "flagship": "gemini-2.5-pro",
            "notes": "Native video + audio stream inspection via Gemini v1beta Files/inline API.",
        },
        "audio": {
            "default": "gemini-2.5-flash",
            "budget": "gemini-2.5-flash-lite",
            "flagship": "gemini-2.5-pro",
            "notes": "Native audio timbre, SFX punch, distortion, and music loop inspection.",
        },
        "vision": {
            "default": "gemini-2.5-flash",
            "budget": "gemini-2.5-flash-lite",
            "flagship": "gemini-2.5-pro",
            "notes": "Roblox GUI screenshot critique for safe zones, contrast, alignment, and anti-slop.",
        },
        "gui_code": {
            "default": "gemini-2.5-flash",
            "budget": "gemini-2.5-flash-lite",
            "flagship": "gemini-2.5-pro",
            "notes": "Bespoke game-specific Luau UI layout & styling generation.",
        },
        "image_gen": {
            "default": "gemini-2.5-flash-image",
            "budget": "gemini-2.5-flash-image",
            "flagship": "gemini-3-pro-image",
            "notes": "Palette-locked 2D UI panels, icon grids, and game textures.",
        },
    },
    "openrouter": {
        "vision": {
            "default": "google/gemini-2.5-flash",
            "budget": "qwen/qwen2.5-vl-72b-instruct",
            "flagship": "anthropic/claude-sonnet-4.5",
            "notes": "Affordable multimodal OpenRouter models for GUI screenshot inspection.",
        },
        "gui_code": {
            "default": "google/gemini-2.5-flash",
            "budget": "qwen/qwen-2.5-coder-32b-instruct",
            "flagship": "anthropic/claude-sonnet-4.5",
            "notes": "Cheap, sharp OpenRouter models tuned for anti-slop Luau GUI components.",
        },
        "video": {
            "default": "google/gemini-2.5-flash",
            "budget": "google/gemini-2.5-flash-lite",
            "flagship": "google/gemini-2.5-pro",
            "notes": "Contact-sheet keyframe sequence vision analysis over OpenRouter.",
        },
        "image_gen": {
            "default": "google/gemini-2.5-flash-image",
            "budget": "google/gemini-2.5-flash-image",
            "flagship": "google/gemini-3-pro-image",
            "notes": "OpenRouter multimodal image generation for custom 2D UI assets.",
        },
    },
}


def resolve_credentials_path(credentials_path: Optional[str | Path] = None) -> Path:
    """Resolve the outside-repo credential JSON file location."""
    if credentials_path:
        return Path(credentials_path).expanduser().resolve()
    env_path = os.environ.get("SHARP_CREDENTIALS_PATH", "").strip()
    if env_path:
        return Path(env_path).expanduser().resolve()
    sharp_home = os.environ.get("SHARP_HOME", "").strip()
    if sharp_home:
        return (Path(sharp_home).expanduser().resolve() / "credentials.json")
    return (Path.home() / ".sharp-mcp" / "credentials.json").resolve()


def mask_api_key(raw_key: Optional[str]) -> Optional[str]:
    """Return a non-recoverable masked preview of an API key."""
    if not raw_key:
        return None
    s = str(raw_key).strip()
    if not s:
        return None
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]} (len={len(s)})"


def _read_store(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"schema": "sharp.credentials.v1", "providers": {}, "model_preferences": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("schema", "sharp.credentials.v1")
            data.setdefault("providers", {})
            data.setdefault("model_preferences", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema": "sharp.credentials.v1", "providers": {}, "model_preferences": {}}


def _write_store(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_api_key(
    provider: str,
    *,
    explicit_key: Optional[str] = None,
    credentials_path: Optional[str | Path] = None,
) -> Optional[str]:
    """Resolve raw API key from explicit override -> env vars -> local credentials file."""
    prov = (provider or "").strip().lower()
    if prov not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider '{provider}'. Expected one of {SUPPORTED_PROVIDERS}.")
    if explicit_key and explicit_key.strip():
        return explicit_key.strip()
    for env_name in ENV_KEY_NAMES[prov]:
        val = os.environ.get(env_name, "").strip()
        if val:
            return val
    store = _read_store(resolve_credentials_path(credentials_path))
    stored_val = (store.get("providers") or {}).get(prov, "")
    if isinstance(stored_val, dict):
        stored_val = stored_val.get("api_key", "")
    return str(stored_val).strip() or None


def get_credentials_status(credentials_path: Optional[str | Path] = None) -> Dict[str, Any]:
    """Return provider configuration state with strictly masked previews (never raw keys)."""
    store_path = resolve_credentials_path(credentials_path)
    store = _read_store(store_path)
    providers_out: Dict[str, Dict[str, Any]] = {}
    for prov in SUPPORTED_PROVIDERS:
        env_hit: Optional[str] = None
        env_val: Optional[str] = None
        for env_name in ENV_KEY_NAMES[prov]:
            v = os.environ.get(env_name, "").strip()
            if v:
                env_hit = env_name
                env_val = v
                break
        stored_entry = (store.get("providers") or {}).get(prov)
        stored_val = ""
        if isinstance(stored_entry, dict):
            stored_val = str(stored_entry.get("api_key", "")).strip()
        elif isinstance(stored_entry, str):
            stored_val = stored_entry.strip()

        active_source = "env" if env_val else ("credentials_file" if stored_val else "none")
        active_val = env_val or stored_val or None
        providers_out[prov] = {
            "configured": bool(active_val),
            "source": active_source,
            "env_var_names": list(ENV_KEY_NAMES[prov]),
            "active_env_var": env_hit,
            "masked_preview": mask_api_key(active_val),
        }

    return {
        "ok": True,
        "credentials_file": str(store_path),
        "credentials_file_exists": store_path.is_file(),
        "providers": providers_out,
        "model_preferences": dict(store.get("model_preferences") or {}),
        "recommended_presets": MODEL_PRESETS,
    }


def set_credentials(
    *,
    gemini_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    model_preferences: Optional[Dict[str, str]] = None,
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Persist API keys and/or preferred models to the outside-repo credentials store."""
    store_path = resolve_credentials_path(credentials_path)
    store = _read_store(store_path)
    providers = store.setdefault("providers", {})
    updated: List[str] = []

    if gemini_api_key is not None and gemini_api_key.strip():
        providers["gemini"] = {"api_key": gemini_api_key.strip()}
        updated.append("gemini")
    if openrouter_api_key is not None and openrouter_api_key.strip():
        providers["openrouter"] = {"api_key": openrouter_api_key.strip()}
        updated.append("openrouter")
    if model_preferences:
        prefs = store.setdefault("model_preferences", {})
        for k, v in model_preferences.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                prefs[k.strip()] = v.strip()
        updated.append("model_preferences")

    _write_store(store_path, store)
    status = get_credentials_status(store_path)
    status["updated"] = updated
    return status


def clear_credentials(
    provider: str = "all",
    *,
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Remove stored credentials for a specific provider or all providers."""
    store_path = resolve_credentials_path(credentials_path)
    store = _read_store(store_path)
    providers = store.setdefault("providers", {})
    norm = (provider or "all").strip().lower()
    cleared: List[str] = []
    if norm == "all":
        for p in list(providers.keys()):
            providers.pop(p, None)
            cleared.append(p)
        store["model_preferences"] = {}
    elif norm in SUPPORTED_PROVIDERS:
        if norm in providers:
            providers.pop(norm, None)
            cleared.append(norm)
    else:
        raise ValueError(f"Unsupported provider '{provider}'. Expected 'gemini', 'openrouter', or 'all'.")

    _write_store(store_path, store)
    status = get_credentials_status(store_path)
    status["cleared"] = cleared
    return status


def resolve_provider_and_model(
    *,
    role: str,
    preferred_provider: str = "auto",
    model_override: Optional[str] = None,
    tier: str = "default",
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Select the active provider ('gemini' or 'openrouter') and model for a task role."""
    norm_role = (role or "vision").strip().lower()
    norm_prov = (preferred_provider or "auto").strip().lower()
    norm_tier = (tier or "default").strip().lower()
    if norm_tier not in ("default", "budget", "flagship"):
        norm_tier = "default"

    gem_key = get_api_key("gemini", credentials_path=credentials_path)
    or_key = get_api_key("openrouter", credentials_path=credentials_path)
    store = _read_store(resolve_credentials_path(credentials_path))
    prefs = store.get("model_preferences") or {}

    selected_provider: Optional[str] = None
    if norm_prov in SUPPORTED_PROVIDERS:
        selected_provider = norm_prov if (gem_key if norm_prov == "gemini" else or_key) else None
    else:
        # Auto preference: native Gemini for video/audio, OpenRouter/Gemini flexibly for gui_code/vision/image_gen.
        if norm_role in ("video", "audio"):
            selected_provider = "gemini" if gem_key else ("openrouter" if or_key else None)
        elif norm_role in ("gui_code",):
            selected_provider = "openrouter" if or_key else ("gemini" if gem_key else None)
        else:
            selected_provider = "gemini" if gem_key else ("openrouter" if or_key else None)

    pref_key = f"{selected_provider}:{norm_role}" if selected_provider else ""
    fallback_prov = selected_provider or ("openrouter" if norm_role == "gui_code" else "gemini")
    preset_bucket = MODEL_PRESETS.get(fallback_prov, {}).get(norm_role) or MODEL_PRESETS.get(fallback_prov, {}).get("vision", {})
    chosen_model = (
        (model_override or "").strip()
        or str(prefs.get(pref_key) or prefs.get(norm_role) or "").strip()
        or preset_bucket.get(norm_tier)
        or preset_bucket.get("default")
        or "gemini-2.5-flash"
    )
    return {
        "provider": selected_provider,
        "planned_provider": fallback_prov,
        "model": chosen_model,
        "tier": norm_tier,
        "key_configured": selected_provider is not None,
        "api_key": (gem_key if selected_provider == "gemini" else or_key) if selected_provider else None,
        "gemini_configured": bool(gem_key),
        "openrouter_configured": bool(or_key),
    }

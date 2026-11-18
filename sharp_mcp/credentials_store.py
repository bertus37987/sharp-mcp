"""Unified Gemini, OpenRouter & Roblox Open Cloud API Credentials Store for Sharp MCP.

Stores keys strictly outside version control (default: ``~/.sharp-mcp/credentials.json`` or
``SHARP_CREDENTIALS_PATH`` / ``SHARP_HOME``), prefers explicit environment variables when set,
never echoes raw secrets in responses, curates affordable high-craft default models, and
provides a local browser setup prompt (`async_prompt_credentials_in_browser`).
"""

from __future__ import annotations

import asyncio
import hmac
import html
import ipaddress
import json
import os
import secrets
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from aiohttp import web


AI_MODEL_PROVIDERS: Tuple[str, ...] = ("gemini", "openrouter")
SUPPORTED_PROVIDERS: Tuple[str, ...] = ("gemini", "openrouter", "roblox_open_cloud")

ENV_KEY_NAMES: Dict[str, Tuple[str, ...]] = {
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openrouter": ("OPENROUTER_API_KEY",),
    "roblox_open_cloud": ("ROBLOX_OPEN_CLOUD_API_KEY", "ROBLOX_API_KEY"),
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
    payload_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    tmp = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd: Optional[int] = None
    try:
        fd = os.open(str(tmp), flags, 0o600)
        if os.name != "nt":
            try:
                os.fchmod(fd, 0o600)
            except (AttributeError, OSError):
                pass
        with os.fdopen(fd, "wb") as f:
            fd = None
            f.write(payload_bytes)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(path))
        if os.name != "nt":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
    except BaseException:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise


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

    creator_env = os.environ.get("ROBLOX_CREATOR_ID", "").strip() or os.environ.get("ROBLOX_USER_ID", "").strip() or None
    creator_stored = str(store.get("roblox_creator_id") or "").strip() or None

    return {
        "ok": True,
        "credentials_file": str(store_path),
        "credentials_file_exists": store_path.is_file(),
        "roblox_creator_id": creator_env or creator_stored,
        "providers": providers_out,
        "model_preferences": dict(store.get("model_preferences") or {}),
        "recommended_presets": MODEL_PRESETS,
    }


def set_credentials(
    *,
    gemini_api_key: Optional[str] = None,
    openrouter_api_key: Optional[str] = None,
    roblox_open_cloud_api_key: Optional[str] = None,
    roblox_creator_id: Optional[str] = None,
    model_preferences: Optional[Dict[str, str]] = None,
    credentials_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Persist API keys, Roblox creator ID, and/or preferred models to the outside-repo credentials store."""
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
    if roblox_open_cloud_api_key is not None and roblox_open_cloud_api_key.strip():
        providers["roblox_open_cloud"] = {"api_key": roblox_open_cloud_api_key.strip()}
        updated.append("roblox_open_cloud")
    if roblox_creator_id is not None and str(roblox_creator_id).strip():
        store["roblox_creator_id"] = str(roblox_creator_id).strip()
        updated.append("roblox_creator_id")
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
        store.pop("roblox_creator_id", None)
        store["model_preferences"] = {}
    elif norm in SUPPORTED_PROVIDERS:
        if norm in providers:
            providers.pop(norm, None)
            cleared.append(norm)
    else:
        raise ValueError(
            f"Unsupported provider '{provider}'. Expected one of {SUPPORTED_PROVIDERS} or 'all'."
        )

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
    if norm_prov in AI_MODEL_PROVIDERS:
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


def _is_loopback_peer(request: web.Request) -> bool:
    peer_ip: Optional[str] = None
    transport = getattr(request, "transport", None)
    if transport is not None:
        peer = transport.get_extra_info("peername")
        if isinstance(peer, tuple) and len(peer) >= 1 and isinstance(peer[0], str) and peer[0].strip():
            peer_ip = peer[0].strip()
        elif isinstance(peer, str) and peer.strip():
            peer_ip = peer.strip()
    if not peer_ip:
        remote_val = getattr(request, "remote", None)
        if isinstance(remote_val, str) and remote_val.strip():
            peer_ip = remote_val.strip()
    if not peer_ip:
        return False
    cleaned_ip = peer_ip.split("%", 1)[0]
    try:
        addr = ipaddress.ip_address(cleaned_ip)
    except ValueError:
        return False
    return addr.is_loopback or (
        isinstance(addr, ipaddress.IPv6Address)
        and addr.ipv4_mapped is not None
        and addr.ipv4_mapped.is_loopback
    )


def _resolve_active_port(request: web.Request, expected_port: Optional[int] = None) -> Optional[int]:
    active_port = expected_port
    transport = getattr(request, "transport", None)
    if transport is not None:
        sockname = transport.get_extra_info("sockname")
        if (
            isinstance(sockname, tuple)
            and len(sockname) >= 2
            and isinstance(sockname[1], int)
            and sockname[1] > 0
        ):
            active_port = sockname[1]
    return active_port


def _is_valid_loopback_host(request: web.Request, expected_port: Optional[int] = None) -> bool:
    active_port = _resolve_active_port(request, expected_port)
    host_hdr = (request.headers.get("Host") or "").strip().lower()
    if active_port is not None and active_port > 0:
        allowed_hosts = {
            f"127.0.0.1:{active_port}",
            f"localhost:{active_port}",
            f"[::1]:{active_port}",
        }
        return host_hdr in allowed_hosts
    return host_hdr in {"127.0.0.1", "localhost", "[::1]"}


def _is_valid_loopback_origin(request: web.Request, expected_port: Optional[int] = None) -> bool:
    origin_hdr = (request.headers.get("Origin") or "").strip().lower()
    if not origin_hdr:
        return True
    active_port = _resolve_active_port(request, expected_port)
    if active_port is not None and active_port > 0:
        allowed_origins = {
            f"http://127.0.0.1:{active_port}",
            f"http://localhost:{active_port}",
            f"http://[::1]:{active_port}",
        }
        return origin_hdr in allowed_origins
    return origin_hdr in {"http://127.0.0.1", "http://localhost", "http://[::1]"}


def _render_credentials_setup_html(
    *,
    token: str,
    status: Dict[str, Any],
    default_creator_id: str = "",
) -> str:
    provs = status.get("providers") or {}
    cred_path_esc = html.escape(str(status.get("credentials_file") or "~/.sharp-mcp/credentials.json"))
    creator_val = str(status.get("roblox_creator_id") or default_creator_id or "").strip()
    creator_esc = html.escape(creator_val)

    def _badge(pname: str) -> str:
        info = provs.get(pname) or {}
        if info.get("configured"):
            preview = html.escape(str(info.get("masked_preview") or "configured"))
            src = html.escape(str(info.get("source") or "stored"))
            return f'<span class="badge ok">Configured: {preview} ({src})</span>'
        return '<span class="badge empty">Not configured</span>'

    token_js = json.dumps(token)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Sharp MCP — API Key Setup</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #0f131a;
    --card: #181e29;
    --border: #2c3648;
    --text: #eef2f7;
    --muted: #98a6bd;
    --accent: #3ea86b;
    --accent-hover: #4cc27d;
    --danger: #d9534f;
    --input-bg: #0c1016;
  }}
  * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{
    margin: 0; padding: 28px 16px; background: var(--bg); color: var(--text);
    display: flex; justify-content: center; align-items: flex-start; min-height: 100vh;
  }}
  .card {{
    width: 100%; max-width: 580px; background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 24px 26px; box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
  }}
  h1 {{ margin: 0 0 6px 0; font-size: 20px; font-weight: 700; }}
  p.sub {{ margin: 0 0 18px 0; color: var(--muted); font-size: 13px; line-height: 1.45; }}
  .field {{ margin-bottom: 16px; }}
  .label-row {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }}
  label {{ font-size: 13px; font-weight: 600; }}
  .badge {{
    font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border);
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  }}
  .badge.ok {{ background: rgba(62, 168, 107, 0.16); border-color: rgba(62, 168, 107, 0.55); color: #8be0ad; }}
  .badge.empty {{ background: rgba(152, 166, 189, 0.10); color: var(--muted); }}
  .input-wrap {{ display: flex; gap: 8px; }}
  input {{
    flex: 1; background: var(--input-bg); color: var(--text); border: 1px solid var(--border);
    border-radius: 8px; padding: 10px 12px; font-size: 13px;
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  }}
  input:focus {{ outline: none; border-color: var(--accent); }}
  .toggle-btn {{
    background: #222b3a; color: var(--muted); border: 1px solid var(--border);
    border-radius: 8px; padding: 0 12px; cursor: pointer; font-size: 12px; font-weight: 600;
  }}
  .toggle-btn:hover {{ color: var(--text); }}
  .hint {{ font-size: 11.5px; color: var(--muted); margin-top: 4px; line-height: 1.35; }}
  .actions {{ display: flex; gap: 10px; margin-top: 20px; align-items: center; }}
  button.primary {{
    flex: 1; background: var(--accent); color: #08150d; border: none; border-radius: 8px;
    padding: 11px 18px; font-size: 14px; font-weight: 700; cursor: pointer;
  }}
  button.primary:hover {{ background: var(--accent-hover); }}
  button.secondary {{
    background: transparent; color: var(--muted); border: 1px solid var(--border);
    border-radius: 8px; padding: 11px 14px; font-size: 13px; cursor: pointer;
  }}
  button.secondary:hover {{ color: var(--text); }}
  .status-box {{
    margin-top: 16px; padding: 12px 14px; border-radius: 8px; font-size: 13px; display: none;
  }}
  .status-box.ok {{ display: block; background: rgba(62, 168, 107, 0.16); border: 1px solid rgba(62, 168, 107, 0.6); color: #a3f0c0; }}
  .status-box.err {{ display: block; background: rgba(217, 83, 79, 0.16); border: 1px solid rgba(217, 83, 79, 0.6); color: #f6b3b0; }}
  code {{ background: #0c1016; padding: 2px 5px; border-radius: 4px; font-size: 11.5px; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Sharp MCP — API Keys &amp; Open Cloud Setup</h1>
    <p class="sub">
      Keys are stored locally outside any Git repository at <code>{cred_path_esc}</code> (mode <code>0600</code>).
      Leave a field empty to keep its existing value unchanged.
    </p>
    <form id="credsForm" method="post" action="/save">
      <input type="hidden" name="token" value="{html.escape(token)}" />

      <div class="field">
        <div class="label-row">
          <label for="gemini_api_key">Gemini API Key</label>
          {_badge("gemini")}
        </div>
        <div class="input-wrap">
          <input id="gemini_api_key" name="gemini_api_key" type="password" placeholder="AIza..." autocomplete="off" />
          <button type="button" class="toggle-btn" onclick="toggleVis('gemini_api_key', this)">Show</button>
        </div>
        <div class="hint">Used for video/audio QA, GUI vision inspection, and AI UI/image generation.</div>
      </div>

      <div class="field">
        <div class="label-row">
          <label for="openrouter_api_key">OpenRouter API Key</label>
          {_badge("openrouter")}
        </div>
        <div class="input-wrap">
          <input id="openrouter_api_key" name="openrouter_api_key" type="password" placeholder="sk-or-v1-..." autocomplete="off" />
          <button type="button" class="toggle-btn" onclick="toggleVis('openrouter_api_key', this)">Show</button>
        </div>
        <div class="hint">Multi-provider fallback &amp; routing for Luau GUI generation and screenshot critique.</div>
      </div>

      <div class="field">
        <div class="label-row">
          <label for="roblox_open_cloud_api_key">Roblox Open Cloud API Key</label>
          {_badge("roblox_open_cloud")}
        </div>
        <div class="input-wrap">
          <input id="roblox_open_cloud_api_key" name="roblox_open_cloud_api_key" type="password" placeholder="Open Cloud key (asset:read, asset:write)..." autocomplete="off" />
          <button type="button" class="toggle-btn" onclick="toggleVis('roblox_open_cloud_api_key', this)">Show</button>
        </div>
        <div class="hint">Optional: Uploads real 3D <code>.fbx</code>/<code>.glb</code> &amp; 2D assets directly via Open Cloud API without folder whitelists. Leave empty to use Roblox Studio MCP (<code>open_cloud_invoke</code>).</div>
      </div>

      <div class="field">
        <div class="label-row">
          <label for="roblox_creator_id">Roblox Creator User ID (optional)</label>
          <span class="badge empty">UserId for Open Cloud uploads</span>
        </div>
        <div class="input-wrap">
          <input id="roblox_creator_id" name="roblox_creator_id" type="text" value="{creator_esc}" placeholder="e.g. 4990516523 (auto-detected from Studio if blank)" autocomplete="off" />
        </div>
      </div>

      <div class="actions">
        <button id="saveBtn" type="submit" class="primary">Save Keys</button>
        <button id="cancelBtn" type="button" class="secondary">Cancel</button>
      </div>
    </form>
    <div id="statusBox" class="status-box"></div>
  </div>
<script>
const TOKEN = {token_js};
if (window.location.search && window.history && window.history.replaceState) {{
  try {{
    window.history.replaceState({{}}, document.title, window.location.pathname);
  }} catch (_e) {{}}
}}
function toggleVis(id, btn) {{
  const el = document.getElementById(id);
  if (!el) return;
  const show = el.type === "password";
  el.type = show ? "text" : "password";
  btn.textContent = show ? "Hide" : "Show";
}}
function showStatus(msg, ok) {{
  const box = document.getElementById("statusBox");
  box.textContent = msg;
  box.className = "status-box " + (ok ? "ok" : "err");
}}
document.getElementById("credsForm").addEventListener("submit", async (ev) => {{
  ev.preventDefault();
  const saveBtn = document.getElementById("saveBtn");
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving...";
  try {{
    const payload = {{
      token: TOKEN,
      gemini_api_key: document.getElementById("gemini_api_key").value,
      openrouter_api_key: document.getElementById("openrouter_api_key").value,
      roblox_open_cloud_api_key: document.getElementById("roblox_open_cloud_api_key").value,
      roblox_creator_id: document.getElementById("roblox_creator_id").value
    }};
    const resp = await fetch("/save", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json", "Accept": "application/json" }},
      body: JSON.stringify(payload)
    }});
    const data = await resp.json();
    if (data && data.ok) {{
      const updated = (data.updated && data.updated.length) ? data.updated.join(", ") : "no changes";
      showStatus("Saved (" + updated + ")! You can close this browser tab and return to your AI client.", true);
      saveBtn.textContent = "Saved";
    }} else {{
      showStatus("Save failed: " + ((data && data.error) || resp.statusText), false);
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Keys";
    }}
  }} catch (err) {{
    showStatus("Request error: " + err, false);
    saveBtn.disabled = false;
    saveBtn.textContent = "Save Keys";
  }}
}});
document.getElementById("cancelBtn").addEventListener("click", async () => {{
  try {{
    await fetch("/cancel", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ token: TOKEN }})
    }});
  }} catch (_e) {{}}
  showStatus("Closed without changes. You can close this tab.", false);
}});
</script>
</body>
</html>
"""


_BACKGROUND_PROMPT_TASKS: List[asyncio.Task[Any]] = []


async def async_prompt_credentials_in_browser(
    *,
    timeout_sec: float = 180.0,
    open_browser: bool = True,
    wait_for_save: bool = True,
    credentials_path: Optional[str | Path] = None,
    default_creator_id: str = "",
    announce_url: bool = False,
) -> Dict[str, Any]:
    """Start a localhost browser UI prompt for Gemini, OpenRouter & Roblox Open Cloud API keys."""
    token = secrets.token_urlsafe(16)
    done_event = asyncio.Event()
    result_box: Dict[str, Any] = {"saved": False, "cancelled": False, "status": get_credentials_status(credentials_path)}
    bound_port_box: List[int] = [0]
    setup_cookie_name = "sharp_setup_token"

    def _valid_token(candidate: Optional[str]) -> bool:
        return isinstance(candidate, str) and bool(candidate) and hmac.compare_digest(candidate, token)

    async def handle_setup(request: web.Request) -> web.Response:
        expected_port = bound_port_box[0] or None
        if not _is_loopback_peer(request):
            return web.Response(status=403, text="Forbidden: loopback peer required")
        if not _is_valid_loopback_host(request, expected_port=expected_port):
            return web.Response(status=403, text="Forbidden: invalid Host header")
        supplied_token = request.query.get("token") or request.cookies.get(setup_cookie_name)
        if not _valid_token(supplied_token):
            return web.Response(status=403, text="Forbidden: invalid or missing session token")
        cur_status = get_credentials_status(credentials_path)
        body = _render_credentials_setup_html(
            token=token,
            status=cur_status,
            default_creator_id=default_creator_id,
        )
        resp = web.Response(
            text=body,
            content_type="text/html",
            headers={
                "Cache-Control": "no-store",
                "Referrer-Policy": "no-referrer",
            },
        )
        resp.set_cookie(
            setup_cookie_name,
            token,
            httponly=True,
            samesite="Strict",
            path="/",
            max_age=max(60, int(timeout_sec)),
        )
        return resp

    async def _parse_payload(request: web.Request) -> Dict[str, Any]:
        ctype = (request.content_type or "").lower()
        raw_text = await request.text()
        if "application/json" in ctype:
            parsed = json.loads(raw_text) if raw_text.strip() else {}
            return parsed if isinstance(parsed, dict) else {}
        parsed_qs = parse_qs(raw_text, keep_blank_values=True)
        return {k: (v[0] if isinstance(v, list) and v else "") for k, v in parsed_qs.items()}

    async def handle_save(request: web.Request) -> web.Response:
        expected_port = bound_port_box[0] or None
        if not _is_loopback_peer(request):
            return web.json_response({"ok": False, "error": "Loopback peer required"}, status=403)
        if not _is_valid_loopback_host(request, expected_port=expected_port):
            return web.json_response({"ok": False, "error": "FORBIDDEN_HOST_HEADER"}, status=403)
        if not _is_valid_loopback_origin(request, expected_port=expected_port):
            return web.json_response({"ok": False, "error": "FORBIDDEN_ORIGIN_HEADER"}, status=403)
        try:
            data = await _parse_payload(request)
        except Exception:
            return web.json_response({"ok": False, "error": "Invalid request payload"}, status=400)

        if not _valid_token(str(data.get("token") or request.cookies.get(setup_cookie_name) or "")):
            return web.json_response({"ok": False, "error": "Invalid or missing session token"}, status=403)

        status = set_credentials(
            gemini_api_key=data.get("gemini_api_key"),
            openrouter_api_key=data.get("openrouter_api_key"),
            roblox_open_cloud_api_key=data.get("roblox_open_cloud_api_key"),
            roblox_creator_id=data.get("roblox_creator_id"),
            credentials_path=credentials_path,
        )
        result_box["saved"] = True
        result_box["status"] = status
        done_event.set()

        accept = (request.headers.get("Accept") or "").lower()
        if "application/json" in accept or "application/json" in (request.content_type or "").lower():
            return web.json_response(
                {"ok": True, "saved": True, "updated": status.get("updated", []), "status": status},
                headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
            )
        return web.Response(
            text="<html><body style='font-family:sans-serif;background:#0f131a;color:#eef2f7;padding:32px;'><h2>Keys saved!</h2><p>You can close this browser tab.</p></body></html>",
            content_type="text/html",
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )

    async def handle_cancel(request: web.Request) -> web.Response:
        expected_port = bound_port_box[0] or None
        if not _is_loopback_peer(request):
            return web.json_response({"ok": False, "error": "Loopback peer required"}, status=403)
        if not _is_valid_loopback_host(request, expected_port=expected_port):
            return web.json_response({"ok": False, "error": "FORBIDDEN_HOST_HEADER"}, status=403)
        if not _is_valid_loopback_origin(request, expected_port=expected_port):
            return web.json_response({"ok": False, "error": "FORBIDDEN_ORIGIN_HEADER"}, status=403)
        try:
            data = await _parse_payload(request)
        except Exception:
            data = {}
        if not _valid_token(str(data.get("token") or request.cookies.get(setup_cookie_name) or "")):
            return web.json_response({"ok": False, "error": "Invalid session token"}, status=403)
        result_box["cancelled"] = True
        done_event.set()
        return web.json_response({"ok": True, "cancelled": True})

    app = web.Application()
    app.router.add_get("/setup", handle_setup)
    app.router.add_post("/save", handle_save)
    app.router.add_post("/cancel", handle_cancel)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    bound_port = 0
    if site._server and site._server.sockets:
        bound_port = int(site._server.sockets[0].getsockname()[1])
    bound_port_box[0] = bound_port
    setup_url = f"http://127.0.0.1:{bound_port}/setup?token={token}"
    if announce_url:
        print(f"Sharp MCP Setup URL: {setup_url}", file=sys.stderr, flush=True)

    browser_opened = False
    if open_browser:
        try:
            browser_opened = bool(webbrowser.open(setup_url, new=2))
        except Exception:
            browser_opened = False

    async def _cleanup_after_wait() -> None:
        try:
            await asyncio.wait_for(done_event.wait(), timeout=max(1.0, float(timeout_sec)))
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                await runner.cleanup()
            except Exception:
                pass

    if not wait_for_save:
        bg_task = asyncio.create_task(_cleanup_after_wait())
        _BACKGROUND_PROMPT_TASKS.append(bg_task)
        bg_task.add_done_callback(
            lambda t: _BACKGROUND_PROMPT_TASKS.remove(t) if t in _BACKGROUND_PROMPT_TASKS else None
        )
        return {
            "ok": True,
            "opened": browser_opened,
            "listening": True,
            "saved": False,
            "url": setup_url,
            "port": bound_port,
            "expires_in_sec": float(timeout_sec),
            "status": result_box["status"],
        }

    timed_out = False
    try:
        await asyncio.wait_for(done_event.wait(), timeout=max(0.1, float(timeout_sec)))
    except asyncio.TimeoutError:
        timed_out = True
    finally:
        await runner.cleanup()

    final_status = result_box["status"]
    return {
        "ok": bool(result_box["saved"]),
        "opened": browser_opened,
        "saved": bool(result_box["saved"]),
        "cancelled": bool(result_box["cancelled"]),
        "timed_out": timed_out,
        "url": setup_url,
        "port": bound_port,
        **final_status,
    }


def prompt_credentials_in_browser(
    *,
    timeout_sec: float = 180.0,
    open_browser: bool = True,
    wait_for_save: bool = True,
    credentials_path: Optional[str | Path] = None,
    default_creator_id: str = "",
    announce_url: bool = False,
) -> Dict[str, Any]:
    """Synchronous CLI wrapper around `async_prompt_credentials_in_browser`."""
    return asyncio.run(
        async_prompt_credentials_in_browser(
            timeout_sec=timeout_sec,
            open_browser=open_browser,
            wait_for_save=wait_for_save,
            credentials_path=credentials_path,
            default_creator_id=default_creator_id,
            announce_url=announce_url,
        )
    )

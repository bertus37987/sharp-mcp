"""Open-source Roblox toolchain engine: Rojo, Lune, Selene, StyLua, Wally & Rokit."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..process_utils import detached_subprocess_kwargs


TOOLCHAIN_SPECS: Dict[str, Dict[str, str]] = {
    "rojo": {
        "purpose": "Sync filesystem Luau sources & SharpAssetRegistry.luau to Roblox Studio (.rbxl/.rbxm/serve)",
        "rokit_pkg": "rojo-rbx/rojo",
    },
    "lune": {
        "purpose": "Standalone headless Luau runtime for offline unit/logic tests",
        "rokit_pkg": "lune-org/lune",
    },
    "selene": {
        "purpose": "Static Luau linter catching correctness, shadowing & deprecated APIs",
        "rokit_pkg": "Kampfkarren/selene",
    },
    "stylua": {
        "purpose": "Deterministic Luau code formatter (--check / format)",
        "rokit_pkg": "JohnnyMorganz/StyLua",
    },
    "wally": {
        "purpose": "Roblox Luau package manager (wally.toml)",
        "rokit_pkg": "UpliftGames/wally",
    },
    "rokit": {
        "purpose": "Modern cross-platform Roblox toolchain manager (rokit.toml)",
        "rokit_pkg": "rojo-rbx/rokit",
    },
}


class ToolchainEngine:
    """Detects and executes external Roblox developer toolchain binaries cleanly."""

    def _candidate_bin_dirs(self) -> List[Path]:
        home = Path.home()
        dirs = [
            home / "bin",
            home / ".rokit" / "bin",
            home / ".aftman" / "bin",
            home / ".cargo" / "bin",
            home / ".local" / "bin",
        ]
        if os.name == "nt":
            userprofile = os.environ.get("USERPROFILE", "").strip()
            if userprofile:
                up = Path(userprofile)
                dirs.extend([up / "bin", up / ".rokit" / "bin", up / ".aftman" / "bin", up / ".cargo" / "bin"])
            local_app = os.environ.get("LOCALAPPDATA", "").strip()
            if local_app:
                dirs.append(Path(local_app) / "Programs")
        seen: List[Path] = []
        for d in dirs:
            if d not in seen and d.is_dir():
                seen.append(d)
        return seen

    def _augmented_path_env(self) -> str:
        existing = os.environ.get("PATH", "")
        extra = [str(d) for d in self._candidate_bin_dirs()]
        parts = [p for p in extra + existing.split(os.pathsep) if p]
        return os.pathsep.join(parts)

    def resolve_binary(self, tool_name: str) -> Optional[str]:
        """Locate ``tool_name`` executable via PATH + standard Rokit/Aftman/Cargo/User bin directories."""
        return shutil.which(tool_name, path=self._augmented_path_env())

    @staticmethod
    def _probe_version(binary_path: str) -> Optional[str]:
        try:
            proc = subprocess.run(
                [binary_path, "--version"],
                capture_output=True,
                text=True,
                timeout=4.0,
                check=False,
                **detached_subprocess_kwargs(),
            )
            out = (proc.stdout or proc.stderr or "").strip()
            return out.splitlines()[0].strip() if out else None
        except Exception:
            return None

    def detect_toolchain(self, *, probe_versions: bool = True) -> Dict[str, Any]:
        """Detect installation status and optional versions for Rojo, Lune, Selene, StyLua, Wally & Rokit."""
        tools_status: Dict[str, Dict[str, Any]] = {}
        installed_names: List[str] = []
        missing_names: List[str] = []

        for tool_name, spec in TOOLCHAIN_SPECS.items():
            resolved = self.resolve_binary(tool_name)
            installed = resolved is not None
            if installed:
                installed_names.append(tool_name)
            else:
                missing_names.append(tool_name)
            version = self._probe_version(resolved) if (resolved and probe_versions) else None
            tools_status[tool_name] = {
                "installed": installed,
                "path": resolved,
                "version": version,
                "purpose": spec["purpose"],
                "rokit_package": spec["rokit_pkg"],
            }

        return {
            "ok": True,
            "searched_bin_dirs": [str(d) for d in self._candidate_bin_dirs()],
            "installed_tools": installed_names,
            "missing_tools": missing_names,
            "tools": tools_status,
        }

    def generate_rojo_project(
        self,
        project_root: str | Path,
        *,
        project_name: Optional[str] = None,
        create_source_dirs: bool = True,
        registry_rel_path: str = "assets/SharpAssetRegistry.luau",
        overwrite_project_json: bool = False,
    ) -> Dict[str, Any]:
        """Generate or merge a valid Rojo ``default.project.json`` under ``project_root``."""
        root = Path(project_root).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        name = (project_name or root.name or "SharpRobloxProject").strip()

        if create_source_dirs:
            for sub in ("src/shared", "src/server", "src/client", "src/gui"):
                (root / sub).mkdir(parents=True, exist_ok=True)

        reg_rel = registry_rel_path.replace("\\", "/").lstrip("./")
        project_file = root / "default.project.json"
        if project_file.is_file() and not overwrite_project_json:
            try:
                doc = json.loads(project_file.read_text(encoding="utf-8"))
                action = "updated"
            except Exception:
                doc = {}
                action = "created"
        else:
            doc = {}
            action = "created"

        doc.setdefault("name", name)
        tree = doc.setdefault("tree", {"$className": "DataModel"})
        if not isinstance(tree, dict):
            tree = {"$className": "DataModel"}
            doc["tree"] = tree
        tree["$className"] = "DataModel"

        rep_storage = tree.setdefault("ReplicatedStorage", {"$className": "ReplicatedStorage"})
        if isinstance(rep_storage, dict):
            rep_storage.setdefault("$className", "ReplicatedStorage")
            shared = rep_storage.setdefault("Shared", {"$path": "src/shared"})
            if isinstance(shared, dict):
                shared.setdefault("$path", "src/shared")
                shared["SharpAssetRegistry"] = {"$path": reg_rel}

        sss = tree.setdefault("ServerScriptService", {"$className": "ServerScriptService"})
        if isinstance(sss, dict):
            sss.setdefault("$className", "ServerScriptService")
            sss.setdefault("Server", {"$path": "src/server"})

        sp = tree.setdefault("StarterPlayer", {"$className": "StarterPlayer"})
        if isinstance(sp, dict):
            sp.setdefault("$className", "StarterPlayer")
            sps = sp.setdefault("StarterPlayerScripts", {"$className": "StarterPlayerScripts"})
            if isinstance(sps, dict):
                sps.setdefault("$className", "StarterPlayerScripts")
                sps.setdefault("Client", {"$path": "src/client"})

        sg = tree.setdefault("StarterGui", {"$className": "StarterGui", "$path": "src/gui"})
        if isinstance(sg, dict):
            sg.setdefault("$className", "StarterGui")
            if "$path" not in sg:
                sg["$path"] = "src/gui"

        project_file.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "action": action,
            "project_name": doc["name"],
            "project_file": str(project_file),
            "registry_path": reg_rel,
            "tree_services": sorted(k for k in tree.keys() if not k.startswith("$")),
            "project_config": doc,
        }

    def _run_tool_cmd(
        self,
        tool_name: str,
        args: List[str],
        *,
        cwd: Optional[str | Path] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        binary = self.resolve_binary(tool_name)
        if not binary:
            pkg = TOOLCHAIN_SPECS.get(tool_name, {}).get("rokit_pkg", tool_name)
            return {
                "ok": False,
                "installed": False,
                "tool": tool_name,
                "code": "TOOL_NOT_INSTALLED",
                "message": f"'{tool_name}' executable was not found in PATH or standard user bin dirs.",
                "install_hint": f"rokit add {pkg}",
            }

        work_dir = str(Path(cwd).expanduser().resolve()) if cwd else None
        env = dict(os.environ)
        env["PATH"] = self._augmented_path_env()
        try:
            proc = subprocess.run(
                [binary] + args,
                cwd=work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
                **detached_subprocess_kwargs(),
            )
            stdout = (proc.stdout or "").strip()
            stderr = (proc.stderr or "").strip()
            return {
                "ok": proc.returncode == 0,
                "installed": True,
                "tool": tool_name,
                "executable": binary,
                "command": [binary] + args,
                "cwd": work_dir,
                "exit_code": proc.returncode,
                "passed": proc.returncode == 0,
                "stdout": stdout[-8000:],
                "stderr": stderr[-8000:],
            }
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "installed": True,
                "tool": tool_name,
                "code": "TOOL_TIMEOUT",
                "message": f"'{tool_name}' timed out after {timeout_sec}s.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "installed": True,
                "tool": tool_name,
                "code": "TOOL_EXEC_ERROR",
                "message": str(exc),
            }

    def run_stylua(
        self,
        target_path: str | Path,
        *,
        check_only: bool = True,
        extra_args: Optional[List[str]] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        """Run ``stylua --check`` (or format) against a file or directory."""
        target = Path(target_path).expanduser().resolve()
        if not target.exists():
            return {"ok": False, "tool": "stylua", "error": f"Target path not found: {target}"}
        cmd_args: List[str] = []
        if check_only:
            cmd_args.append("--check")
        if extra_args:
            cmd_args.extend(extra_args)
        cmd_args.append(str(target))
        cwd = target if target.is_dir() else target.parent
        return self._run_tool_cmd("stylua", cmd_args, cwd=cwd, timeout_sec=timeout_sec)

    def run_selene(
        self,
        target_path: str | Path,
        *,
        config_path: Optional[str | Path] = None,
        extra_args: Optional[List[str]] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        """Run ``selene`` static analysis on a file or directory."""
        target = Path(target_path).expanduser().resolve()
        if not target.exists():
            return {"ok": False, "tool": "selene", "error": f"Target path not found: {target}"}
        cmd_args: List[str] = []
        if config_path:
            cmd_args.extend(["--config", str(Path(config_path).expanduser().resolve())])
        if extra_args:
            cmd_args.extend(extra_args)
        cmd_args.append(str(target))
        cwd = target if target.is_dir() else target.parent
        return self._run_tool_cmd("selene", cmd_args, cwd=cwd, timeout_sec=timeout_sec)

    def run_lune(
        self,
        script_path: str | Path,
        *,
        script_args: Optional[List[str]] = None,
        cwd: Optional[str | Path] = None,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        """Run a headless Luau script via ``lune run``."""
        target = Path(script_path).expanduser().resolve()
        if not target.is_file():
            return {"ok": False, "tool": "lune", "error": f"Lune script not found: {target}"}
        cmd_args = ["run", str(target)]
        if script_args:
            cmd_args.extend(script_args)
        return self._run_tool_cmd("lune", cmd_args, cwd=cwd or target.parent, timeout_sec=timeout_sec)

    def run_rojo_build(
        self,
        project_root: str | Path,
        *,
        output_file: str = "build.rbxl",
        timeout_sec: float = 45.0,
    ) -> Dict[str, Any]:
        """Build a Roblox place/model binary from ``default.project.json`` using ``rojo build``."""
        root = Path(project_root).expanduser().resolve()
        proj = root / "default.project.json"
        if not proj.is_file():
            return {"ok": False, "tool": "rojo", "error": f"Missing default.project.json in {root}"}
        out_path = Path(output_file)
        if not out_path.is_absolute():
            out_path = root / out_path
        res = self._run_tool_cmd("rojo", ["build", str(proj), "-o", str(out_path)], cwd=root, timeout_sec=timeout_sec)
        res["output_file"] = str(out_path)
        return res

    def run_action(
        self,
        action: str = "detect",
        *,
        project_root: Optional[str | Path] = None,
        target_path: Optional[str | Path] = None,
        project_name: Optional[str] = None,
        output_file: str = "build.rbxl",
        check_only: bool = True,
        script_args: Optional[List[str]] = None,
        overwrite_project_json: bool = False,
    ) -> Dict[str, Any]:
        """Unified dispatcher called by ``sharp_toolchain``."""
        act = (action or "detect").strip().lower()
        root = Path(project_root).expanduser().resolve() if project_root else Path.cwd().resolve()
        target = Path(target_path).expanduser().resolve() if target_path else root

        if act == "detect":
            return self.detect_toolchain()
        if act in ("init_rojo", "rojo_init", "generate_rojo_project"):
            return self.generate_rojo_project(
                root,
                project_name=project_name,
                overwrite_project_json=overwrite_project_json,
            )
        if act in ("rojo_build", "build_rojo"):
            return self.run_rojo_build(root, output_file=output_file)
        if act in ("stylua", "stylua_check"):
            return self.run_stylua(target, check_only=check_only)
        if act == "selene":
            return self.run_selene(target)
        if act in ("lune", "lune_run"):
            return self.run_lune(target, script_args=script_args, cwd=root)
        if act in ("lint_all", "check_all"):
            return {
                "ok": True,
                "action": "check_all",
                "detect": self.detect_toolchain(probe_versions=False),
                "stylua": self.run_stylua(target, check_only=True),
                "selene": self.run_selene(target),
            }
        return {
            "ok": False,
            "error": f"Unsupported toolchain action '{action}'.",
            "supported_actions": ["detect", "init_rojo", "rojo_build", "stylua_check", "selene", "lune_run", "check_all"],
        }

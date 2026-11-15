#!/usr/bin/env node
import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const SCRIPT_PATH = decodeURIComponent(
  new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")
);
const REAL_SCRIPT_PATH = fs.existsSync(SCRIPT_PATH)
  ? fs.realpathSync(SCRIPT_PATH)
  : SCRIPT_PATH;
const PACKAGE_ROOT = path.resolve(path.dirname(REAL_SCRIPT_PATH), "..");

const IS_WINDOWS = os.platform() === "win32";
const VENV_PY_REL = IS_WINDOWS
  ? path.join("Scripts", "python.exe")
  : path.join("bin", "python");
const VENV_PY_ALT_REL = IS_WINDOWS
  ? path.join("Scripts", "python.exe")
  : path.join("bin", "python3");

const DEPS_PROBE_CODE =
  "import sys; assert sys.version_info >= (3, 11); import mcp, aiohttp, PIL, numpy; print(sys.executable)";

function isExecutable(filePath) {
  if (!filePath) return false;
  try {
    if (!fs.existsSync(filePath)) return false;
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) return false;
    if (!IS_WINDOWS) {
      fs.accessSync(filePath, fs.constants.X_OK);
    }
    return true;
  } catch {
    return false;
  }
}

function runProbe(command, args, cwd = PACKAGE_ROOT, timeout = 8000) {
  try {
    const stdout = execFileSync(command, args, {
      cwd,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout,
      windowsHide: true,
    });
    return { ok: true, stdout: (stdout || "").trim() };
  } catch (err) {
    return {
      ok: false,
      stderr: err?.stderr ? String(err.stderr).trim() : String(err?.message || err),
    };
  }
}

function probePythonCandidate(command, baseArgs = []) {
  const verProbe = runProbe(command, [
    ...baseArgs,
    "-c",
    "import sys; assert sys.version_info >= (3, 11); print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
  ]);
  if (!verProbe.ok) {
    return { exists: false, versionOk: false, depsOk: false };
  }
  const depsProbe = runProbe(command, [...baseArgs, "-c", DEPS_PROBE_CODE]);
  return {
    exists: true,
    versionOk: true,
    version: verProbe.stdout,
    depsOk: depsProbe.ok,
    resolvedExecutable: depsProbe.ok ? depsProbe.stdout : command,
  };
}

function findVenvPython(venvDir) {
  const primary = path.join(venvDir, VENV_PY_REL);
  if (isExecutable(primary)) return primary;
  const alt = path.join(venvDir, VENV_PY_ALT_REL);
  if (isExecutable(alt)) return alt;
  return null;
}

function findSystemPython311() {
  const candidates = IS_WINDOWS
    ? [
        { cmd: "python", baseArgs: [] },
        { cmd: "python3", baseArgs: [] },
        { cmd: "py", baseArgs: ["-3.13"] },
        { cmd: "py", baseArgs: ["-3.12"] },
        { cmd: "py", baseArgs: ["-3.11"] },
        { cmd: "py", baseArgs: ["-3"] },
      ]
    : [
        { cmd: "python3", baseArgs: [] },
        { cmd: "python", baseArgs: [] },
        { cmd: "python3.13", baseArgs: [] },
        { cmd: "python3.12", baseArgs: [] },
        { cmd: "python3.11", baseArgs: [] },
      ];

  let fallbackVersionOnly = null;
  for (const cand of candidates) {
    const res = probePythonCandidate(cand.cmd, cand.baseArgs);
    if (res.versionOk && res.depsOk) {
      return { ...cand, ...res };
    }
    if (res.versionOk && !fallbackVersionOnly) {
      fallbackVersionOnly = { ...cand, ...res };
    }
  }
  return fallbackVersionOnly;
}

function detectUv() {
  const probe = runProbe("uv", ["--version"]);
  return probe.ok ? { available: true, version: probe.stdout } : { available: false };
}

function detectLaunchStrategy(rawArgs) {
  const envPython = (process.env.SHARP_PYTHON || "").trim();
  const dotVenvDir = path.join(PACKAGE_ROOT, ".venv");
  const sharpVenvDir = path.join(PACKAGE_ROOT, ".sharp-venv");

  // 1. SHARP_PYTHON override
  if (envPython) {
    const res = probePythonCandidate(envPython);
    if (res.versionOk && res.depsOk) {
      return {
        mode: "SHARP_PYTHON",
        command: envPython,
        args: ["-m", "sharp_mcp.cli", ...rawArgs],
        pythonExecutable: res.resolvedExecutable,
        pythonVersion: res.version,
        needsBootstrap: false,
      };
    }
    return {
      mode: "SHARP_PYTHON_INVALID",
      error: `SHARP_PYTHON='${envPython}' is missing Python >=3.11 or required packages (mcp, aiohttp, Pillow, numpy).`,
      needsBootstrap: false,
    };
  }

  // 2. <root>/.venv
  const dotVenvPy = findVenvPython(dotVenvDir);
  if (dotVenvPy) {
    const res = probePythonCandidate(dotVenvPy);
    if (res.versionOk && res.depsOk) {
      return {
        mode: ".venv",
        command: dotVenvPy,
        args: ["-m", "sharp_mcp.cli", ...rawArgs],
        pythonExecutable: res.resolvedExecutable,
        pythonVersion: res.version,
        needsBootstrap: false,
      };
    }
  }

  // 3. <root>/.sharp-venv
  const sharpVenvPy = findVenvPython(sharpVenvDir);
  if (sharpVenvPy) {
    const res = probePythonCandidate(sharpVenvPy);
    if (res.versionOk && res.depsOk) {
      return {
        mode: ".sharp-venv",
        command: sharpVenvPy,
        args: ["-m", "sharp_mcp.cli", ...rawArgs],
        pythonExecutable: res.resolvedExecutable,
        pythonVersion: res.version,
        needsBootstrap: false,
      };
    }
  }

  // 4. uv (with `uv run --directory <root> --no-sync sharp-mcp` when deps are ready)
  const uvInfo = detectUv();
  if (uvInfo.available) {
    const uvReady = runProbe(
      "uv",
      ["run", "--directory", PACKAGE_ROOT, "--no-sync", "python", "-c", DEPS_PROBE_CODE],
      PACKAGE_ROOT,
      12000
    );
    const uvEntryReady = uvReady.ok
      ? runProbe(
          "uv",
          ["run", "--directory", PACKAGE_ROOT, "--no-sync", "sharp-mcp", "--version"],
          PACKAGE_ROOT,
          12000
        )
      : { ok: false };
    if (uvReady.ok && uvEntryReady.ok) {
      return {
        mode: "uv-no-sync",
        command: "uv",
        args: ["run", "--directory", PACKAGE_ROOT, "--no-sync", "sharp-mcp", ...rawArgs],
        pythonExecutable: uvReady.stdout,
        uvVersion: uvInfo.version,
        needsBootstrap: false,
      };
    }
  }

  // 5. System python / python3 >=3.11 with mcp/aiohttp/PIL/numpy
  const sysPy = findSystemPython311();
  if (sysPy && sysPy.depsOk) {
    return {
      mode: "system-python",
      command: sysPy.cmd,
      args: [...sysPy.baseArgs, "-m", "sharp_mcp.cli", ...rawArgs],
      pythonExecutable: sysPy.resolvedExecutable,
      pythonVersion: sysPy.version,
      needsBootstrap: false,
    };
  }

  // 6. Auto-bootstrap plan for <root>/.sharp-venv
  const bootstrapMethod = uvInfo.available ? "uv" : sysPy ? "pip" : "unavailable";
  return {
    mode: "bootstrap-.sharp-venv",
    needsBootstrap: true,
    bootstrapMethod,
    targetVenvDir: sharpVenvDir,
    systemPython: sysPy || null,
    uvAvailable: uvInfo.available,
  };
}

function buildChildEnv() {
  const existingPyPath = process.env.PYTHONPATH || "";
  const mergedPyPath = existingPyPath
    ? `${PACKAGE_ROOT}${path.delimiter}${existingPyPath}`
    : PACKAGE_ROOT;

  return {
    ...process.env,
    PYTHONPATH: mergedPyPath,
    PYTHONIOENCODING: "utf-8",
    PYTHONUNBUFFERED: "1",
  };
}

function bootstrapSharpVenv(strategy) {
  const venvDir = strategy.targetVenvDir;
  process.stderr.write(
    `[sharp-mcp] Bootstrapping isolated runtime at ${venvDir} via ${strategy.bootstrapMethod}...\n`
  );

  if (strategy.bootstrapMethod === "uv") {
    execFileSync("uv", ["venv", "--python", ">=3.11", venvDir], {
      cwd: PACKAGE_ROOT,
      stdio: ["ignore", "pipe", "inherit"],
      windowsHide: true,
    });
    const venvPy = findVenvPython(venvDir);
    if (!venvPy) {
      throw new Error(`uv created ${venvDir}, but Python executable was not found.`);
    }
    execFileSync("uv", ["pip", "install", "--python", venvPy, "-e", PACKAGE_ROOT], {
      cwd: PACKAGE_ROOT,
      stdio: ["ignore", "pipe", "inherit"],
      windowsHide: true,
    });
    return venvPy;
  }

  if (strategy.bootstrapMethod === "pip" && strategy.systemPython) {
    const sysPy = strategy.systemPython;
    execFileSync(sysPy.cmd, [...sysPy.baseArgs, "-m", "venv", venvDir], {
      cwd: PACKAGE_ROOT,
      stdio: ["ignore", "pipe", "inherit"],
      windowsHide: true,
    });
    const venvPy = findVenvPython(venvDir);
    if (!venvPy) {
      throw new Error(`venv created ${venvDir}, but Python executable was not found.`);
    }
    execFileSync(venvPy, ["-m", "pip", "install", "--disable-pip-version-check", "-e", PACKAGE_ROOT], {
      cwd: PACKAGE_ROOT,
      stdio: ["ignore", "pipe", "inherit"],
      windowsHide: true,
    });
    return venvPy;
  }

  throw new Error(
    "Neither `uv` nor a Python >=3.11 interpreter was found to bootstrap `.sharp-venv`. " +
      "Install Python 3.11+ or uv, or set SHARP_PYTHON."
  );
}

function main() {
  const rawArgs = process.argv.slice(2);
  const dryRunRequested = rawArgs.includes("--dry-run");
  const noInstallEnv = /^(1|true|yes|on)$/i.test(
    (process.env.SHARP_NPX_NO_INSTALL || "").trim()
  );
  const launcherInfoRequested = rawArgs.includes("--launcher-info");

  const strategy = detectLaunchStrategy(rawArgs);

  if (launcherInfoRequested) {
    const info = {
      ok: strategy.mode !== "SHARP_PYTHON_INVALID" && strategy.bootstrapMethod !== "unavailable",
      packageRoot: PACKAGE_ROOT,
      nodeVersion: process.version,
      platform: os.platform(),
      detectionOrder: [
        "SHARP_PYTHON",
        "<root>/.venv",
        "<root>/.sharp-venv",
        "uv (uv run --directory <root> --no-sync sharp-mcp)",
        "system python/python3 >=3.11 with mcp/aiohttp/PIL/numpy",
        "auto-bootstrap <root>/.sharp-venv via uv or pip",
      ],
      selectedStrategy: strategy,
      noInstallRequested: dryRunRequested || noInstallEnv,
      envOverrides: {
        PYTHONPATH: buildChildEnv().PYTHONPATH,
        PYTHONIOENCODING: "utf-8",
        PYTHONUNBUFFERED: "1",
      },
    };
    process.stdout.write(`${JSON.stringify(info, null, 2)}\n`);
    process.exit(info.ok ? 0 : 1);
  }

  if (strategy.mode === "SHARP_PYTHON_INVALID") {
    process.stderr.write(`[sharp-mcp] Error: ${strategy.error}\n`);
    process.exit(1);
  }

  let command = strategy.command;
  let childArgs = strategy.args;

  if (strategy.needsBootstrap) {
    if (dryRunRequested || noInstallEnv) {
      process.stderr.write(
        `[sharp-mcp] Missing Python >=3.11 runtime with mcp/aiohttp/Pillow/numpy and bootstrap is disabled (${
          dryRunRequested ? "--dry-run" : "SHARP_NPX_NO_INSTALL"
        }). Would bootstrap ${strategy.targetVenvDir} using ${strategy.bootstrapMethod}.\n`
      );
      process.exit(1);
    }
    try {
      const venvPy = bootstrapSharpVenv(strategy);
      command = venvPy;
      childArgs = ["-m", "sharp_mcp.cli", ...rawArgs];
    } catch (err) {
      process.stderr.write(`[sharp-mcp] Bootstrap failed: ${err?.message || err}\n`);
      process.exit(1);
    }
  }

  const child = spawn(command, childArgs, {
    cwd: process.cwd(),
    env: buildChildEnv(),
    stdio: "inherit",
    windowsHide: true,
  });

  const forwardSignal = (sig) => {
    if (!child.killed) {
      try {
        child.kill(sig);
      } catch {
        // Ignore if child already exited
      }
    }
  };

  process.on("SIGINT", () => forwardSignal("SIGINT"));
  process.on("SIGTERM", () => forwardSignal("SIGTERM"));
  if (!IS_WINDOWS) {
    process.on("SIGHUP", () => forwardSignal("SIGHUP"));
  }

  child.on("error", (err) => {
    process.stderr.write(`[sharp-mcp] Failed to spawn '${command}': ${err.message}\n`);
    process.exit(1);
  });

  child.on("exit", (code, signal) => {
    if (typeof code === "number") {
      process.exit(code);
    }
    if (signal) {
      process.exit(1);
    }
    process.exit(0);
  });
}

main();

#!/usr/bin/env node
/**
 * reza postinstall — automatically installs the Python reza package via pip.
 *
 * Runs after `npm install -g reza`. Checks for Python 3.8+, then calls
 * `pip install reza`. If pip fails, prints clear instructions.
 */

"use strict";

const { execFileSync, spawnSync } = require("child_process");
const os = require("os");

const PYPI_PACKAGE = "reza";
const MIN_PYTHON_MAJOR = 3;
const MIN_PYTHON_MINOR = 8;

// ─── Helpers ───────────────────────────────────────────────────────────────

function log(msg)  { process.stdout.write(`\x1b[36m[reza]\x1b[0m ${msg}\n`); }
function warn(msg) { process.stdout.write(`\x1b[33m[reza]\x1b[0m ${msg}\n`); }
function err(msg)  { process.stderr.write(`\x1b[31m[reza]\x1b[0m ${msg}\n`);  }

/** Return the first executable found in PATH, or null. */
function findExecutable(names) {
  const isWin = os.platform() === "win32";
  for (const name of names) {
    try {
      const cmd  = isWin ? "where"  : "which";
      const result = spawnSync(cmd, [name], { encoding: "utf8" });
      if (result.status === 0 && result.stdout.trim()) return name;
    } catch (_) {}
  }
  return null;
}

/** Run a command synchronously; return { ok, stdout, stderr }. */
function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts,
  });
  return {
    ok: result.status === 0,
    stdout: (result.stdout || "").trim(),
    stderr: (result.stderr || "").trim(),
  };
}

// ─── Python discovery ──────────────────────────────────────────────────────

function findPython() {
  // Windows: py launcher first (respects virtual envs and version ranges)
  if (os.platform() === "win32") {
    const py = findExecutable(["py"]);
    if (py) {
      const v = run("py", ["-3", "--version"]);
      if (v.ok) return { cmd: "py", args: ["-3"] };
    }
  }
  const python = findExecutable(["python3", "python"]);
  return python ? { cmd: python, args: [] } : null;
}

function getPythonVersion(pythonInfo) {
  const r = run(pythonInfo.cmd, [...pythonInfo.args, "--version"]);
  if (!r.ok) return null;
  const m = (r.stdout || r.stderr).match(/Python (\d+)\.(\d+)/);
  return m ? [parseInt(m[1], 10), parseInt(m[2], 10)] : null;
}

// ─── pip discovery ─────────────────────────────────────────────────────────

function findPip(pythonInfo) {
  // Prefer running pip as a Python module — avoids PATH confusion
  const pipModule = run(pythonInfo.cmd, [...pythonInfo.args, "-m", "pip", "--version"]);
  if (pipModule.ok) return { cmd: pythonInfo.cmd, args: [...pythonInfo.args, "-m", "pip"] };

  // Fallback: look for pip3 / pip in PATH
  const pipBin = findExecutable(["pip3", "pip"]);
  if (pipBin) return { cmd: pipBin, args: [] };

  return null;
}

// ─── Check if reza is already installed ────────────────────────────────────

function rezaAlreadyInstalled(pythonInfo) {
  const r = run(pythonInfo.cmd, [...pythonInfo.args, "-c", "import reza"]);
  return r.ok;
}

// ─── Install ───────────────────────────────────────────────────────────────

function installReza(pipInfo) {
  log(`Installing Python package '${PYPI_PACKAGE}' via pip…`);
  const result = spawnSync(
    pipInfo.cmd,
    [...pipInfo.args, "install", "--upgrade", PYPI_PACKAGE],
    { stdio: "inherit", encoding: "utf8" }
  );
  return result.status === 0;
}

// ─── Main ──────────────────────────────────────────────────────────────────

function main() {
  // Skip in CI environments that manage Python separately
  if (process.env.REZA_SKIP_POSTINSTALL === "1") {
    log("REZA_SKIP_POSTINSTALL=1 — skipping pip install.");
    return;
  }

  log("Checking for Python 3.8+…");

  const pythonInfo = findPython();
  if (!pythonInfo) {
    err("Python not found. Please install Python 3.8+ from https://python.org");
    err("Then run:  pip install reza");
    err("reza's npm shim is installed but the Python backend is missing.");
    // Don't fail postinstall — the shim will give a helpful error on first use
    return;
  }

  const version = getPythonVersion(pythonInfo);
  if (!version) {
    warn("Could not determine Python version. Proceeding anyway…");
  } else {
    const [major, minor] = version;
    if (major < MIN_PYTHON_MAJOR || (major === MIN_PYTHON_MAJOR && minor < MIN_PYTHON_MINOR)) {
      err(`Python ${major}.${minor} found — reza requires Python 3.8+.`);
      err(`Please upgrade Python, then run: pip install reza`);
      return;
    }
    log(`Found Python ${major}.${minor} ✓`);
  }

  if (rezaAlreadyInstalled(pythonInfo)) {
    log("reza Python package is already installed ✓");
    log("Run 'reza --version' to confirm.");
    return;
  }

  const pipInfo = findPip(pythonInfo);
  if (!pipInfo) {
    err("pip not found. Install pip, then run: pip install reza");
    return;
  }

  const ok = installReza(pipInfo);
  if (ok) {
    log("reza installed successfully ✓");
    log("Run 'reza init' in any project to get started.");
  } else {
    err("pip install failed. Try manually: pip install reza");
    err("See https://github.com/swebreza/reza for help.");
  }
}

main();

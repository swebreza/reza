#!/usr/bin/env node
/**
 * reza CLI shim — delegates every call to the Python `reza` command.
 *
 * Installed globally via: npm install -g reza
 * The postinstall script installs the Python backend automatically.
 *
 * If the Python backend is missing, this shim prints a clear error
 * instead of crashing with a confusing Node.js stack trace.
 */

"use strict";

const { spawnSync } = require("child_process");
const os   = require("os");
const path = require("path");

// ─── Find the Python reza binary ──────────────────────────────────────────

/**
 * Try to find the `reza` Python executable.
 * Returns { cmd, args } that together invoke reza, or null if not found.
 *
 * Strategy (in order):
 *  1. `reza` directly in PATH (happy path after pip install)
 *  2. `python -m reza.cli` (fallback — works even if PATH is misconfigured)
 *  3. `py -3 -m reza.cli` (Windows py launcher)
 */
function findReza() {
  const isWin = os.platform() === "win32";

  // 1. Direct binary
  const directNames = isWin ? ["reza.exe", "reza.cmd", "reza"] : ["reza"];
  for (const name of directNames) {
    const probe = spawnSync(name, ["--version"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
      shell: isWin,   // needed for .cmd files on Windows
    });
    if (probe.status === 0) return { cmd: name, args: [], shell: isWin };
  }

  // 2. python -m reza.cli
  const pythonNames = isWin
    ? ["py", "python3", "python"]
    : ["python3", "python"];

  for (const pyName of pythonNames) {
    // For Windows `py`, add -3 flag
    const pyArgs = (isWin && pyName === "py") ? ["-3"] : [];

    const probe = spawnSync(pyName, [...pyArgs, "-m", "reza.cli", "--version"], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
    if (probe.status === 0) {
      return { cmd: pyName, args: [...pyArgs, "-m", "reza.cli"], shell: false };
    }
  }

  return null;
}

// ─── Error helpers ─────────────────────────────────────────────────────────

function printMissingError() {
  const lines = [
    "",
    "\x1b[31m[reza]\x1b[0m Python backend not found.",
    "",
    "The npm package installs the CLI shim, but the Python backend",
    "must also be installed. Fix this with ONE of:",
    "",
    "  \x1b[36mpip install reza\x1b[0m              (recommended)",
    "  \x1b[36mpip3 install reza\x1b[0m",
    "  \x1b[36mpython -m pip install reza\x1b[0m    (if pip not in PATH)",
    "",
    "Requires Python 3.8+. Get it at \x1b[4mhttps://python.org\x1b[0m",
    "",
    "After installing, run \x1b[1mreza init\x1b[0m in your project.",
    "",
  ];
  process.stderr.write(lines.join("\n"));
}

// ─── Main ──────────────────────────────────────────────────────────────────

function main() {
  const rezaInfo = findReza();

  if (!rezaInfo) {
    printMissingError();
    process.exit(1);
  }

  // Pass all CLI arguments through unchanged
  const userArgs = process.argv.slice(2);
  const result = spawnSync(
    rezaInfo.cmd,
    [...rezaInfo.args, ...userArgs],
    {
      stdio: "inherit",   // inherit stdin/stdout/stderr — full TTY passthrough
      shell: rezaInfo.shell,
    }
  );

  // Mirror the Python process exit code exactly
  if (result.error) {
    process.stderr.write(`[reza] Failed to launch: ${result.error.message}\n`);
    process.exit(1);
  }

  process.exit(result.status ?? 1);
}

main();

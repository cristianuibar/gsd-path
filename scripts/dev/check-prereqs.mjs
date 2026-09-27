#!/usr/bin/env node
// Verify toolchain prerequisites for the GSD Path test harness.
// Exit 0 when required tools meet minimum versions; nonzero with a clear message otherwise.
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { findPython } from "./py.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const windows = process.platform === "win32";

function fail(message) {
  console.error(`check-prereqs: ${message}`);
  process.exit(1);
}

function versionAtLeast(current, required) {
  const a = current.split(".").map(Number);
  const b = required.split(".").map(Number);
  for (let index = 0; index < 3; index += 1) {
    const difference = (a[index] || 0) - (b[index] || 0);
    if (difference) return difference > 0;
  }
  return true;
}

function output(command, args, options = {}) {
  const result = spawnSync(command, args, { cwd: root, encoding: "utf8", ...options });
  return result.status === 0 ? result.stdout.trim() : null;
}

console.log("GSD Path test prerequisites");
console.log(`  repo: ${root}\n`);

const nodeVersion = process.versions.node;
// npm is npm.cmd on Windows, which only runs through a shell.
const npmVersion = windows ? output("npm --version", [], { shell: true }) : output("npm", ["--version"]);
if (!npmVersion) fail("missing required command: npm");
const python = findPython();
if (!python) fail("missing Python 3.9+ (tried python3, python, py -3; set GSD_PATH_PYTHON)");
const pythonVersion = output(python[0], [...python.slice(1), "-c",
  "import sys; print('.'.join(map(str, sys.version_info[:3])))"]);
const gitVersion = output("git", ["--version"]);
if (!gitVersion) fail("missing required command: git");

console.log(`  node:    ${nodeVersion} (required >= 18.17)`);
console.log(`  npm:     ${npmVersion}`);
console.log(`  python:  ${pythonVersion} via \`${python.join(" ")}\` (required >= 3.9; CI uses 3.12)`);
console.log(`  git:     ${gitVersion.split(" ")[2]} (required; 2.30+ recommended for worktree tests)`);

if (!versionAtLeast(nodeVersion, "18.17")) fail(`node ${nodeVersion} is below 18.17`);

if (windows) {
  // Verify commands and git hooks need Git for Windows' bash, never the WSL launcher.
  const bash = output(python[0], [...python.slice(1), "-c",
    "import sys; sys.path.insert(0, 'scripts'); import _common; print(_common.find_bash())"]);
  if (!bash) fail("missing Git for Windows bash.exe (install Git for Windows or set GSD_PATH_BASH)");
  console.log(`  bash:    ${bash}`);
  if (output("git", ["config", "core.longpaths"]) !== "true") {
    console.log("  note: git core.longpaths is not true; deep worktree paths may exceed MAX_PATH");
  }
}
console.log();

if (!existsSync(path.join(root, "package-lock.json"))) {
  fail("package-lock.json is missing; run npm install from a release checkout");
}
const packageJson = JSON.parse(readFileSync(path.join(root, "package.json"), "utf8"));
if (Object.keys(packageJson.dependencies || {}).length && !existsSync(path.join(root, "node_modules"))) {
  console.log("  note: node_modules/ is absent — run 'make install' or 'npm ci' before tests");
}
if (!output("git", ["config", "user.email"]) || !output("git", ["config", "user.name"])) {
  console.log("  note: git user.name/user.email are unset; many tests set these in temp repos,");
  console.log("        but configuring them globally avoids surprises in manual git work.");
}

console.log("\nRequired prerequisites satisfied.");

#!/usr/bin/env node
// Run a repository Python command with a portable interpreter (development only).
//
//   node scripts/dev/py.mjs [--path DIR]... ARGS...
//
// npm runs package scripts through cmd.exe on Windows, where `python3` is
// usually absent and `PYTHONPATH=dir cmd` is not valid syntax. This finds
// python3, python, or the `py -3` launcher (GSD_PATH_PYTHON overrides) and
// prepends each --path directory, relative to the repository, to PYTHONPATH.
import { spawnSync } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const CANDIDATES = [["python3"], ["python"], ["py", "-3"]];
const PROBE = "import sys; raise SystemExit(sys.version_info < (3, 9))";

// The first interpreter that runs Python 3.9+. The Microsoft Store `python`
// alias stubs exit nonzero, so the probe skips them.
export function findPython(env = process.env) {
  const candidates = env.GSD_PATH_PYTHON ? [[env.GSD_PATH_PYTHON]] : CANDIDATES;
  for (const [command, ...args] of candidates) {
    const result = spawnSync(command, [...args, "-c", PROBE], { stdio: "ignore", env });
    if (result.status === 0) return [command, ...args];
  }
  return null;
}

function main(argv) {
  const paths = [];
  while (argv[0] === "--path") {
    paths.push(path.resolve(root, argv[1]));
    argv = argv.slice(2);
  }
  const python = findPython();
  if (!python) {
    console.error("py.mjs: no Python 3.9+ found as python3, python, or py -3 (set GSD_PATH_PYTHON)");
    return 1;
  }
  const env = { ...process.env };
  if (paths.length) {
    env.PYTHONPATH = [...paths, env.PYTHONPATH].filter(Boolean).join(path.delimiter);
  }
  // Tests compare checked-out bytes. A developer's global core.autocrlf=true
  // (the Git for Windows default) would check fixtures out as CRLF; CI runs
  // with it off, so match that without touching any git config file.
  const count = Number(env.GIT_CONFIG_COUNT || 0);
  env[`GIT_CONFIG_KEY_${count}`] = "core.autocrlf";
  env[`GIT_CONFIG_VALUE_${count}`] = "false";
  env.GIT_CONFIG_COUNT = String(count + 1);
  // No repository script run here may reach a real GitHub account: tests fake
  // gh, and a fake that fails to shadow the real one must fail unauthenticated.
  // (On Windows an extensionless fake was once skipped for the real gh.exe.)
  for (const name of ["GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"]) {
    delete env[name];
  }
  env.GH_CONFIG_DIR = mkdtempSync(path.join(tmpdir(), "gsd-path-no-gh-"));
  const [command, ...args] = python;
  const result = spawnSync(command, [...args, ...argv], { stdio: "inherit", env });
  if (result.error) {
    console.error(`py.mjs: ${result.error.message}`);
    return 1;
  }
  return result.status ?? 1;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exit(main(process.argv.slice(2)));
}

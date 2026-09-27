#!/usr/bin/env node
// Run every tests/*.test.mjs file. cmd.exe does not expand globs and
// `node --test` only expands them itself from Node 21, so list them here.
// Extra arguments (for example --test-name-pattern) pass through to node.
import { spawnSync } from "node:child_process";
import { readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const directory = path.dirname(fileURLToPath(import.meta.url));
const files = readdirSync(directory)
  .filter((name) => name.endsWith(".test.mjs"))
  .sort()
  .map((name) => path.join(directory, name));
const result = spawnSync(process.execPath, ["--test", ...process.argv.slice(2), ...files], {
  stdio: "inherit",
});
process.exit(result.status ?? 1);

import { describe, expect, it } from "vitest";
import { isNewer, opOutcome, updatePlan, updateRows } from "./settingsUpdates";
import type { PluginStatus } from "./settingsUpdates";

const plugin: PluginStatus = {
  latest: "1.4.0", update_available: true,
  hosts: {
    codex: { installed: true, version: "1.4.0", root: "/home/me/.agents/skills" },
    claude: { installed: true, version: "1.3.2", root: "/home/me/.claude/skills" },
    zed: { installed: true, version: "1.4.0", root: "/home/me/.agents/skills" },
    cursor: { installed: false, version: null, root: "/home/me/.cursor/skills" },
    kiro: { installed: true, version: null, root: "/home/me/.kiro/skills" },
  },
  projects: [
    { root: "/work/gsd-path", runtime: true, runtime_version: "1.3.2" },
    { root: "/work/atlas", runtime: true, runtime_version: "1.4.0" },
    { root: "/work/notes", runtime: false, runtime_version: null },
    { root: "/work/old", runtime: true, runtime_version: "unknown" },
  ],
};
const names = { "/work/gsd-path": "gsd-path", "/work/atlas": "atlas" };

describe("isNewer", () => {
  it("compares version parts as numbers", () => {
    expect(isNewer("1.10.0", "1.9.9")).toBe(true);
    expect(isNewer("1.4.0", "1.4.0")).toBe(false);
    expect(isNewer("1.3.9", "1.4.0")).toBe(false);
    expect(isNewer("1.4.1", "1.4")).toBe(true);
  });
  it("is false when a version is missing or not numeric", () => {
    expect(isNewer(null, "1.0.0")).toBe(false);
    expect(isNewer("1.4.0", null)).toBe(false);
    expect(isNewer("1.4.0", "unknown")).toBe(false);
  });
});

describe("updateRows", () => {
  const rows = updateRows(plugin, names);
  it("lists one row per installed skills folder, then one per project runtime", () => {
    expect(rows.map((row) => row.name)).toEqual([
      "Skills in Codex and Zed", "Skills in Claude Code", "Skills in Kiro",
      "Runtime in gsd-path", "Runtime in atlas", "Runtime in old",
    ]);
  });
  it("gives a pending row its versions and its own action", () => {
    expect(rows[1]).toEqual({
      key: "skills:/home/me/.claude/skills", name: "Skills in Claude Code", sub: "/home/me/.claude/skills",
      version: "1.3.2 → 1.4.0", state: "pending", note: "", group: "global",
      step: { id: "global", label: "Skills in every agent folder", body: { scope: "global" } },
    });
    expect(rows[3]).toMatchObject({
      version: "1.3.2 → 1.4.0", state: "pending", sub: "/work/gsd-path", group: "project:/work/gsd-path",
      step: { id: "project:/work/gsd-path", label: "Runtime in gsd-path", body: { scope: "project", root: "/work/gsd-path" } },
    });
  });
  it("gives a current row no action", () => {
    expect(rows[0]).toMatchObject({ version: "1.4.0", state: "current", step: null, group: "global" });
    expect(rows[4]).toMatchObject({ version: "1.4.0", state: "current", step: null });
  });
  it("says so when a version is not known, and offers no action", () => {
    expect(rows[2]).toMatchObject({ version: "—", state: "unknown", note: "Version unknown", step: null });
    expect(rows[5]).toMatchObject({ version: "—", state: "unknown", note: "Version unknown", step: null });
  });
  it("marks every row unknown when the latest release is not known", () => {
    const blind = updateRows({ ...plugin, latest: null }, names);
    expect(blind.map((row) => row.state)).toEqual(Array(6).fill("unknown"));
    expect(blind[1]).toMatchObject({ version: "1.3.2", note: "Latest release unknown", step: null });
  });
  it("shows the folder name of a project the board does not name", () => {
    expect(rows[5].name).toBe("Runtime in old");
  });
  it("groups every skills row under the one skills action, and each runtime under its own", () => {
    expect(rows.map((row) => row.group)).toEqual(["global", "global", "global", "project:/work/gsd-path", "project:/work/atlas", "project:/work/old"]);
  });
  it("is empty when nothing is installed", () => {
    expect(updateRows({ latest: "1.4.0" }, {})).toEqual([]);
  });
});

describe("updatePlan", () => {
  it("runs the skills update once, then each pending project", () => {
    const both = updateRows({ ...plugin, hosts: { ...plugin.hosts, kiro: { installed: true, version: "1.2.0", root: "/k" } } }, names);
    expect(updatePlan(both).map((step) => step.id)).toEqual(["global", "project:/work/gsd-path"]);
  });
  it("is empty when everything is up to date", () => {
    const current = updateRows({ latest: "1.4.0", hosts: { codex: plugin.hosts!.codex }, projects: [plugin.projects![1]] }, names);
    expect(updatePlan(current)).toEqual([]);
  });
});

describe("opOutcome", () => {
  it("passes a good result with its output", () => {
    expect(opOutcome({ ok: true, argv: ["x"], stdout_tail: "would update 2 files\n", error: null }))
      .toEqual({ ok: true, output: "would update 2 files", error: "" });
  });
  it("turns a refused result into an error, and keeps the output", () => {
    expect(opOutcome({ ok: false, argv: [], stdout_tail: "step 1", error: "git fetch failed" }))
      .toEqual({ ok: false, output: "step 1", error: "git fetch failed" });
    expect(opOutcome({ ok: false, argv: [], stdout_tail: "", error: null }).error).toBe("The installer failed. See the output.");
  });
  it("adds the source notice to the output", () => {
    expect(opOutcome({ ok: true, argv: [], stdout_tail: "done", error: null, source_notice: "Using local plugin source." }).output)
      .toBe("Using local plugin source.\ndone");
  });
});

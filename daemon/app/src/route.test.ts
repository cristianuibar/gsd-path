import { describe, expect, it } from "vitest";
import { SETTINGS_TABS, envHash, filesHash, parseRoute, projectHash, settingsHash, statsHash } from "./route";

describe("routes", () => {
  it("opens the board by default", () => {
    for (const hash of ["", "#", "#/projects", "#/unknown"]) expect(parseRoute(hash)).toEqual({ page: "projects" });
  });
  it("opens the tray popover", () => {
    expect(parseRoute("#/tray")).toEqual({ page: "tray" });
  });
  it("round-trips a project folder with slashes, spaces and non-ASCII letters", () => {
    for (const root of ["/work/gsd-path", "C:\\Users\\me\\my app", "/home/zoë/a#b?c%d"]) {
      expect(parseRoute(projectHash(root))).toEqual({ page: "project", root, file: null });
    }
  });
  it("opens a file of a project, STATE.md by default", () => {
    expect(parseRoute(filesHash("/work/a b", ".project/plan/PLAN.md"))).toEqual({ page: "project", root: "/work/a b", file: ".project/plan/PLAN.md" });
    expect(parseRoute(filesHash("/work/a"))).toEqual({ page: "project", root: "/work/a", file: ".project/STATE.md" });
  });
  it("opens the Skills page", () => {
    expect(parseRoute("#/skills")).toEqual({ page: "skills" });
  });
  it("opens Stats for all projects or for one project", () => {
    expect(parseRoute("#/stats")).toEqual({ page: "stats", root: null });
    expect(parseRoute(statsHash("/work/a b"))).toEqual({ page: "stats", root: "/work/a b" });
    expect(parseRoute(statsHash(null))).toEqual({ page: "stats", root: null });
  });
  it("opens a Settings tab, Updates by default or for an unknown tab", () => {
    expect(parseRoute("#/settings")).toEqual({ page: "settings", tab: "updates" });
    for (const tab of SETTINGS_TABS) expect(parseRoute(settingsHash(tab))).toEqual({ page: "settings", tab });
    expect(parseRoute("#/settings/nope")).toEqual({ page: "settings", tab: "updates" });
  });
  it("opens the environment editor of a project", () => {
    expect(parseRoute(envHash("/work/a b"))).toEqual({ page: "env", root: "/work/a b" });
  });
  it("falls back to the board for a broken link", () => {
    expect(parseRoute("#/project/")).toEqual({ page: "projects" });
    expect(parseRoute("#/project/%E0%A4%A")).toEqual({ page: "projects" });
  });
});

import { describe, expect, it } from "vitest";
import { filesHash, parseRoute, projectHash } from "./route";

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
  it("falls back to the board for a broken link", () => {
    expect(parseRoute("#/project/")).toEqual({ page: "projects" });
    expect(parseRoute("#/project/%E0%A4%A")).toEqual({ page: "projects" });
  });
});

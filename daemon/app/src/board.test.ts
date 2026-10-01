import { describe, expect, it } from "vitest";
import { boardRow, filterCounts, visibleProjects } from "./board";
import { asking, blocked, building, shipped, status } from "./fixtures";
import { nameOf } from "./status";

const NOW = Date.parse(status.generated_at!);
const names = (filter: string, query = "") => visibleProjects(status.projects, filter, query).map(nameOf);

describe("filters", () => {
  it("counts projects per state", () => {
    expect(filterCounts(status.projects)).toEqual([
      { key: "all", label: "All", count: 4 }, { key: "active", label: "In progress", count: 2 },
      { key: "blocked", label: "Blocked", count: 1 }, { key: "shipped", label: "Shipped", count: 1 },
    ]);
  });
  it("lists Unverified only when a project is unverified", () => {
    const old = { ...building, workflow: undefined };
    expect(filterCounts([old, blocked]).map((f) => [f.key, f.count])).toEqual([
      ["all", 2], ["active", 0], ["blocked", 1], ["shipped", 0], ["unverified", 1]]);
  });
  it("shows only the projects in the chosen state, in board order", () => {
    expect(names("all")).toEqual(["atlas", "field-notes", "gsd-path", "done-thing"]);
    expect(names("active")).toEqual(["field-notes", "gsd-path"]);
    expect(names("blocked")).toEqual(["atlas"]);
    expect(names("shipped")).toEqual(["done-thing"]);
  });
  it("searches name, folder and milestone without case", () => {
    expect(names("all", "  ATLAS ")).toEqual(["atlas"]);
    expect(names("all", "/work/notes")).toEqual(["field-notes"]);
    expect(names("all", "daemon")).toEqual(["gsd-path"]);
    expect(names("all", "gsd path")).toEqual(["gsd-path"]); // the project state name
    expect(names("shipped", "atlas")).toEqual([]);
    expect(names("all", "zzz")).toEqual([]);
  });
});

describe("boardRow", () => {
  it("shows the milestone, phase, tasks and usage of a project in build", () => {
    expect(boardRow(building, NOW)).toEqual({
      root: "/work/gsd-path", name: "gsd-path", tone: "warn", path: "/work/gsd-path",
      number: "M004", slug: "daemon", cells: ["done", "done", "done", "done", "done", "done", "now", "todo"], phase: "build",
      state: "active", label: "In build", note: "no activity for 2d", ago: "2d ago",
      tasks: "2/3", cost: "$26.10", turns: "90 turns",
    });
  });
  it("shows a blocked project with its reason and no invented usage", () => {
    expect(boardRow(blocked, NOW)).toMatchObject({
      tone: "bad", state: "blocked", label: "Blocked", note: ".project/review/FINAL.md — reject", ago: "3h ago",
      tasks: "—", cost: "—", turns: "No matched sessions",
    });
  });
  it("has no note for a healthy project and says when no phase is recorded", () => {
    expect(boardRow(shipped, NOW)).toMatchObject({ note: "", label: "Shipped", ago: "28d ago" });
    expect(boardRow({ ...asking, phase: null }, NOW).phase).toBe("No phase recorded");
  });
  it("names the worktree next to the project folder", () => {
    expect(boardRow({ ...building, worktree_root: "/work/wt/a" }, NOW).path).toBe("/work/gsd-path · Worktree: /work/wt/a");
  });
});

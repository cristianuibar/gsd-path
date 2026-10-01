import { describe, expect, it } from "vitest";
import { asking, blocked, building, shipped, status } from "./fixtures";
import { facts, milestoneRows, nowBox, phaseTrack, usageTiles } from "./project";

const NOW = Date.parse(status.generated_at!);

describe("facts", () => {
  it("lists state, health, git and usage", () => {
    expect(facts(building, NOW)).toEqual([
      ["State", "In build"], ["Health", "amber · no activity for 2d"], ["Milestone", "M004"],
      ["Branch", "gsd-path/M004"], ["Head", "0e9a3b1 · dirty"], ["Integration", "direct"],
      ["Updated", "2d ago"], ["Cost", "$26.10"], ["Turns", "90"],
    ]);
  });
  it("leaves out an unknown integration and shows dashes for missing git and usage", () => {
    expect(facts({ ...asking, git: null, branch: null }, NOW)).toEqual([
      ["State", "In research"], ["Health", "amber · Which search index do we ship?"], ["Milestone", "now"],
      ["Branch", "—"], ["Head", "—"], ["Updated", "1h ago"], ["Cost", "—"], ["Turns", "—"],
    ]);
  });
});

describe("phaseTrack", () => {
  it("dates each phase from the log", () => {
    expect(phaseTrack(building)).toEqual([
      { label: "inspect", date: "", state: "done" }, { label: "define", date: "09-09", state: "done" },
      { label: "research", date: "09-09", state: "done" }, { label: "decide", date: "", state: "done" },
      { label: "roadmap", date: "09-09", state: "done" }, { label: "plan", date: "09-09", state: "done" },
      { label: "build", date: "09-10", state: "now" }, { label: "ship", date: "", state: "todo" },
    ]);
  });
  it("uses the last entry of the current phase and the first entry of an earlier one", () => {
    const again = { ...building, phase_log: [
      { phase: "plan", date: "2026-09-01" }, { phase: "build", date: "2026-09-02" },
      { phase: "plan", date: "2026-09-03" }, { phase: "build", date: "2026-09-04" }] };
    const dates = Object.fromEntries(phaseTrack(again).map((step) => [step.label, step.date]));
    expect([dates.plan, dates.build]).toEqual(["09-01", "09-04"]);
  });
});

describe("nowBox", () => {
  it("shows progress, waves, criteria and the last verify of the current milestone", () => {
    expect(nowBox(building)).toEqual({
      blocked: false, title: "M004 daemon", line: "build · wave 2",
      goal: "Native tray and dashboard for the daemon.", intent: "One window for every project.",
      percent: 67, count: "2 of 3 tasks · entered build 2026-09-10 · 2d 3h",
      waves: [{ state: "done", text: "wave 1 parsers" }, { state: "now", text: "wave 2 watcher" }, { state: "todo", text: "wave 3 tray" }],
      criteria: "1 of 2 criteria met", verify: { result: "pass", at: "03:58:11" }, reason: null,
    });
  });
  it("shows the blocked reason and no progress bar without tasks", () => {
    expect(nowBox(blocked)).toMatchObject({
      blocked: true, title: "M002 api-v2", line: "ship", percent: null, count: "no tasks yet", waves: [],
      criteria: null, verify: null, reason: "The final review has not passed.",
    });
  });
  it("is hidden for a shipped project", () => {
    expect(nowBox(shipped)).toBeNull();
  });
  it("marks every wave done when all tasks are done and no wave is current", () => {
    const finished = { ...building, current_wave: null, tasks_done: 3 };
    expect(nowBox(finished)!.waves.map((wave) => wave.state)).toEqual(["done", "done", "done"]);
    expect(nowBox({ ...building, current_wave: null })!.waves.map((wave) => wave.state)).toEqual(["todo", "todo", "todo"]);
  });
});

describe("milestoneRows", () => {
  it("lists done, current and planned milestones with their usage", () => {
    expect(milestoneRows(building)).toEqual([
      { kind: "done", blocked: false, number: "M003", slug: "core", goal: "Parsers and the status endpoint.",
        meta: "5 of 5 tasks · 2 waves · integrated 91be44a", status: "shipped 2026-09-06", tasks: "5", usage: "$1.50 · 6 turns", tokens: "500k tokens" },
      { kind: "now", blocked: false, number: "M004", slug: "daemon", goal: "Native tray and dashboard for the daemon.",
        meta: "", status: "In build", tasks: "3", usage: "$24.60 · 84 turns", tokens: "8.9M tokens" },
      { kind: "todo", blocked: false, number: "M005", slug: "notify", goal: "Desktop notifications.",
        meta: "after M004", status: "pending", tasks: "—", usage: "—", tokens: null },
    ]);
  });
  it("marks the current milestone of a blocked project and never shows zero usage", () => {
    expect(milestoneRows(blocked)).toMatchObject([{ kind: "now", blocked: true, status: "Blocked", tasks: "—", usage: "—", tokens: null }]);
  });
  it("shows a shipped current milestone as done", () => {
    expect(milestoneRows(shipped)).toMatchObject([{ kind: "done", status: "shipped 2026-09-03", tasks: "4" }]);
  });
});

describe("usageTiles", () => {
  it("is empty when no host session matched", () => {
    expect(usageTiles(blocked)).toBeNull();
    expect(usageTiles({ ...blocked, spend: { turns: 0 } })).toBeNull();
  });
  it("totals cost, tokens, cache hit and time", () => {
    expect(usageTiles(building)).toEqual([
      ["Cost", "$26.10"], ["Turns", "90"], ["Prompts", "31"], ["Tokens in", "6.0M"], ["Cached", "3.0M"],
      ["Tokens out", "412k"], ["Cache hit", "33%"], ["Agent time", "1h 30m"], ["Cost / turn", "$0.29"], ["Time / turn", "60s"],
    ]);
  });
  it("shows dashes for values the logs do not carry", () => {
    const bare = usageTiles({ ...building, spend: { turns: 3, cost: null, priced_turns: 0, timed_turns: 0 } })!;
    expect(Object.fromEntries(bare)).toMatchObject({
      Cost: "—", Turns: "3", "Cache hit": "—", "Agent time": "—", "Cost / turn": "—", "Time / turn": "—" });
  });
});

// Development only: answers for the Stats page's daemon routes in the browser mock.
// Return undefined for a path this page does not own.
const day = (date: string, tokens: number, turns: number, cost: number | null) => ({ date, tokens, turns, cost });
// Sep 21 has no sessions (a blank slot). Sep 30 ran only a model without a price (no cost bar).
const DAYS = [
  day("2026-09-18", 1_750_000, 31, 1.5), day("2026-09-19", 2_400_000, 40, 2.2), day("2026-09-20", 1_100_000, 18, 1.0),
  day("2026-09-22", 3_600_000, 61, 3.2), day("2026-09-23", 2_000_000, 35, 1.5), day("2026-09-24", 900_000, 12, 0.6),
  day("2026-09-25", 2_750_000, 44, 2.5), day("2026-09-26", 4_000_000, 70, 3.7), day("2026-09-27", 3_300_000, 52, 2.9),
  day("2026-09-28", 2_250_000, 39, 1.9), day("2026-09-29", 4_200_000, 77, 3.8), day("2026-09-30", 3_500_000, 58, null),
  day("2026-10-01", 2_900_000, 49, 2.3)];
const run = (project: string, at: string, result: string) =>
  ({ project, recorded_at: at, result, command: "python -m unittest", commit: "0e9a3b1c55d2" });
const VERIFY = [..."pppppfpppppppfpppppppppfppppfp"].map((mark, index) =>
  run("gsd-path", `2026-09-${String(index + 1).padStart(2, "0")}T03:58:11+00:00`, mark === "p" ? "pass" : "fail"));
const PHASES = [{ phase: "build", seconds: 50_400 }, { phase: "research", seconds: 10_800 }, { phase: "plan", seconds: 9_000 },
  { phase: "define", seconds: 4_320 }, { phase: "roadmap", seconds: 3_600 }, { phase: "decide", seconds: 2_880 }, { phase: "inspect", seconds: 1_800 }];

const ANSWERS: Record<string, unknown> = {
  "": { scope: null, days: DAYS, unpriced: ["claude-sonnet-5"], phases: PHASES, waves: null, verify: VERIFY,
    missing: { waves: "Choose a project to see its waves." } },
  "/work/gsd-path": { scope: "/work/gsd-path", days: DAYS.slice(3), unpriced: ["claude-sonnet-5"], phases: PHASES,
    waves: [{ wave: 1, total: 3, done: 3 }, { wave: 2, total: 4, done: 3 }, { wave: 3, total: 2, done: 0 }], verify: VERIFY, missing: {} },
  "/work/atlas": { scope: "/work/atlas", days: null, unpriced: [], phases: null, waves: null,
    verify: [run("atlas", "2026-09-30T10:00:00+00:00", "pass"), run("atlas", "2026-10-01T01:00:00+00:00", "fail")],
    missing: { days: "No host sessions matched. Check the session folders in Settings.",
      phases: "No phase change recorded yet. The monitor records one when it sees it happen.",
      waves: "The current milestone has no tasks in waves." } },
  "/work/done": { scope: "/work/done", days: null, unpriced: [], phases: null, waves: null, verify: null,
    missing: { days: "No host sessions matched. Check the session folders in Settings.",
      phases: "No phase change recorded yet. The monitor records one when it sees it happen.",
      waves: "The current milestone has no tasks in waves.", verify: "No verify run recorded." } },
};

export function mockStats(method: string, url: URL, _body: unknown): unknown {
  if (method !== "GET" || url.pathname !== "/api/stats") return undefined;
  const answer = ANSWERS[url.searchParams.get("root") ?? ""];
  // Any other root (for example /work/notes) shows the failure state.
  if (!answer) throw new Error("root is not a watched project");
  return answer;
}

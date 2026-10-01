// The project page: facts strip, phase bar, current milestone, milestones and usage.
// The same mapping as projectPage() in the daemon dashboard (serve.py).
import {
  ago, DASH, duration, healthOf, int, milestoneStack, money, phaseCells, PHASES, reasons, shortTime, spendCell,
  stateLabel, stateOf, tokens,
} from "./status";
import type { Cell, Milestone, Project } from "./status";

export function facts(p: Project, now: number): [string, string][] {
  const git = p.git ?? {};
  const matched = !!p.spend?.turns;
  return [
    ["State", stateLabel(p)],
    ["Health", [healthOf(p), reasons(p)].filter(Boolean).join(" · ")],
    ["Milestone", milestoneStack(p).cur.number],
    ["Branch", git.branch || p.branch || DASH],
    ["Head", git.head ? git.head.slice(0, 7) + (git.dirty ? " · dirty" : "") : DASH],
    ...(p.integration ? [["Integration", p.integration] as [string, string]] : []),
    ["Updated", ago(p.last_activity_iso, now)],
    ["Cost", matched ? money(p.spend!.cost) : DASH],
    ["Turns", matched ? int(p.spend!.turns!) : DASH],
  ];
}

/** The 8-step bar. A phase entered twice shows its first date; the current phase shows its last. */
export function phaseTrack(p: Project): { label: string; date: string; state: Cell }[] {
  const log = p.phase_log ?? [];
  const cells = phaseCells(p);
  return PHASES.map((label, k) => {
    const entries = log.filter((entry) => entry.phase === label);
    const entry = label === p.phase ? entries[entries.length - 1] : entries[0];
    return { label, date: (entry?.date ?? "").slice(5), state: cells[k] };
  });
}

export type NowBox = {
  blocked: boolean; title: string; line: string; goal: string | null; intent: string | null;
  percent: number | null; count: string; waves: { state: Cell; text: string }[];
  criteria: string | null; verify: { result: string; at: string } | null; reason: string | null;
};

/** The current milestone card. A shipped project has none. */
export function nowBox(p: Project): NowBox | null {
  const state = stateOf(p);
  if (state === "shipped") return null;
  const { cur } = milestoneStack(p);
  const done = p.tasks_done ?? 0, total = p.tasks_total ?? 0;
  const entered = (p.phase_log ?? []).filter((entry) => entry.phase === p.phase).pop();
  const when = [entered ? `entered ${entered.phase} ${entered.date}` : null, duration(p.time_in_phase_s)].filter(Boolean).join(" · ");
  const allDone = total > 0 && done >= total;
  const waves = Object.entries(p.waves ?? {}).map(([n, name]) => [Number(n), name] as const).sort((a, b) => a[0] - b[0]);
  const criteria = p.criteria ?? [];
  const last = p.ledger?.[0];
  return {
    blocked: state === "blocked",
    title: `${cur.number} ${cur.slug}`,
    line: [p.phase || "no phase", p.current_wave != null ? `wave ${p.current_wave}` : null].filter(Boolean).join(" · "),
    goal: cur.goal ?? null,
    intent: p.intent ?? null,
    percent: total ? Math.round((100 * done) / total) : null,
    count: total ? `${done} of ${total} tasks${when ? " · " + when : ""}` : `${when ? when + " · " : ""}no tasks yet`,
    waves: waves.map(([n, name]) => ({
      state: p.current_wave != null ? (n < p.current_wave ? "done" : n === p.current_wave ? "now" : "todo") : allDone ? "done" : "todo",
      text: `wave ${n} ${name}`,
    })),
    criteria: criteria.length ? `${criteria.filter((c) => c.verdict === "met").length} of ${criteria.length} criteria met` : null,
    verify: last ? { result: last.result || "unknown", at: shortTime(last.recorded_at) } : null,
    reason: state === "blocked" ? p.workflow?.reason || null : null,
  };
}

export type MilestoneRow = {
  kind: "done" | "now" | "todo"; blocked: boolean; number: string; slug: string; goal: string | null; meta: string;
  status: string; tasks: string; usage: string; tokens: string | null;
};

const manifestMeta = (m: Milestone) => {
  const mf = m.manifest ?? {};
  return [
    mf.tasks_total != null ? `${mf.tasks_done} of ${mf.tasks_total} tasks` : null,
    mf.waves != null ? `${mf.waves} waves` : null,
    mf.cycles_avg != null ? `${mf.cycles_avg} review cycles avg` : null,
    m.integrated ? "integrated " + m.integrated.slice(0, 7) : null,
    mf.carried ? `${mf.carried} rulings carried` : null,
    mf.verdict || null,
  ];
};
const shippedOn = (m: Milestone) => (m.manifest?.shipped ? "shipped " + m.manifest.shipped : m.status || "shipped");

export function milestoneRows(p: Project): MilestoneRow[] {
  const { before, cur, after } = milestoneStack(p), state = stateOf(p);
  const slots = p.spend?.milestones ?? {};
  const row = (m: Milestone, kind: MilestoneRow["kind"], status: string): MilestoneRow => {
    const slot = slots[m.number];
    const tasks = m.manifest?.tasks_total ?? (kind === "now" && p.tasks_total ? p.tasks_total : null);
    const spend = spendCell(slot);
    return {
      kind, blocked: kind === "now" && state === "blocked", number: m.number, slug: m.slug, goal: m.goal ?? null,
      meta: [...(kind === "done" ? manifestMeta(m) : []), m.depends?.length ? `after ${m.depends.join(", ")}` : null].filter(Boolean).join(" · "),
      status, tasks: tasks != null ? String(tasks) : DASH,
      usage: slot?.turns ? [slot.cost != null ? spend.cost : null, spend.turns].filter(Boolean).join(" · ") : DASH,
      tokens: slot?.turns && slot.tokens != null ? `${tokens(slot.tokens)} tokens` : null,
    };
  };
  return [
    ...before.map((m) => row(m, "done", shippedOn(m))),
    state === "shipped" ? row(cur, "done", shippedOn(cur)) : row(cur, "now", stateLabel(p)),
    ...after.map((m) => row(m, "todo", [m.phase, m.status || "planned"].filter(Boolean).join(" · "))),
  ];
}

/** Totals from matched host sessions, or null when none matched. */
export function usageTiles(p: Project): [string, string][] | null {
  const sp = p.spend;
  if (!sp?.turns) return null;
  const cached = sp.tokens_cached ?? 0, inputs = (sp.tokens_in ?? 0) + cached;
  const timed = sp.timed_turns ? sp.duration_s ?? 0 : null;
  return [
    ["Cost", money(sp.cost)], ["Turns", int(sp.turns)], ["Prompts", int(sp.prompts ?? 0)],
    ["Tokens in", tokens(sp.tokens_in ?? 0)], ["Cached", tokens(cached)], ["Tokens out", tokens(sp.tokens_out ?? 0)],
    ["Cache hit", inputs ? Math.round((100 * cached) / inputs) + "%" : DASH],
    ["Agent time", duration(timed) ?? DASH],
    ["Cost / turn", sp.cost != null && sp.priced_turns ? money(sp.cost / sp.priced_turns) : DASH],
    ["Time / turn", timed != null ? Math.round(timed / sp.timed_turns!) + "s" : DASH],
  ];
}

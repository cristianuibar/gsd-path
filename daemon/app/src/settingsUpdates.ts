// Settings → Updates: the rows and the "Update all" plan, from GET /api/plugin/status.
import { DASH } from "./status";

export type PluginStatus = {
  latest?: string | null;
  update_available?: boolean;
  error?: string;
  hosts?: Record<string, { installed: boolean; version: string | null; root?: string; skill_dirs?: string[] }>;
  projects?: { root: string; runtime?: boolean; runtime_version?: string | null; hooks?: boolean; contracts?: boolean; local_skills?: string[] }[];
  releases?: unknown;
};
/** The answer of POST /api/plugin/update. */
export type OpResult = { ok: boolean; argv: string[]; stdout_tail: string; error: string | null; source_notice?: string };
export type UpdateStep = { id: string; label: string; body: { scope: "global" } | { scope: "project"; root: string } };
export type UpdateRow = {
  key: string; name: string; sub: string; version: string;
  state: "pending" | "current" | "unknown";
  /** Why the state is unknown. */
  note: string;
  step: UpdateStep | null;
  /** The id of the action that updates this row, pending or not: its preview and result show under the first row of the group. */
  group: string;
};

const AGENTS: Record<string, string> = {
  codex: "Codex", claude: "Claude Code", grok: "Grok", opencode: "OpenCode", copilot: "GitHub Copilot", qwen: "Qwen Code",
  antigravity: "Antigravity", cursor: "Cursor", zed: "Zed", kiro: "Kiro", kimi: "Kimi Code",
};
// One update refreshes the skills in every agent folder (install.py --update).
const GLOBAL: UpdateStep = { id: "global", label: "Skills in every agent folder", body: { scope: "global" } };

const parts = (version: string | null | undefined) => {
  const numbers = (version ?? "").trim().split(".").map((part) => (/^\d+$/.test(part) ? Number(part) : NaN));
  return version && !numbers.some(Number.isNaN) ? numbers : null;
};

/** The same rule as `_is_newer` in the daemon: numeric parts, left to right. */
export function isNewer(latest: string | null | undefined, installed: string | null | undefined): boolean {
  const a = parts(latest), b = parts(installed);
  if (!a || !b) return false;
  for (let index = 0; index < Math.max(a.length, b.length); index++) {
    if (a[index] === undefined) return false; // equal so far and `latest` is shorter
    if (b[index] === undefined) return true;
    if (a[index] !== b[index]) return a[index] > b[index];
  }
  return false;
}

const list = (names: string[]) => (names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`);

function row(key: string, name: string, sub: string, version: string | null, latest: string | null, step: UpdateStep): UpdateRow {
  const group = step.id;
  const known = parts(version) ? version! : null;
  if (!known) return { key, name, sub, version: DASH, state: "unknown", note: "Version unknown", step: null, group };
  if (!parts(latest)) return { key, name, sub, version: known, state: "unknown", note: "Latest release unknown", step: null, group };
  return isNewer(latest, known)
    ? { key, name, sub, version: `${known} → ${latest}`, state: "pending", note: "", step, group }
    : { key, name, sub, version: known, state: "current", note: "", step: null, group };
}

/** Skills per agent folder (agents that share a folder are one row), then the runtime of each project. */
export function updateRows(plugin: PluginStatus, names: Record<string, string>): UpdateRow[] {
  const latest = plugin.latest ?? null;
  const folders = new Map<string, { agents: string[]; version: string | null }>();
  for (const [host, entry] of Object.entries(plugin.hosts ?? {})) {
    if (!entry.installed) continue;
    const root = entry.root ?? host;
    const folder = folders.get(root) ?? { agents: [], version: entry.version };
    folder.agents.push(AGENTS[host] ?? host);
    folders.set(root, folder);
  }
  const rows = [...folders].map(([root, folder]) =>
    row("skills:" + root, "Skills in " + list(folder.agents), root, folder.version, latest, GLOBAL));
  for (const project of plugin.projects ?? []) {
    if (!project.runtime) continue;
    const name = "Runtime in " + (names[project.root] ?? project.root.split(/[\\/]/).filter(Boolean).pop() ?? project.root);
    rows.push(row("project:" + project.root, name, project.root, project.runtime_version ?? null, latest,
      { id: "project:" + project.root, label: name, body: { scope: "project", root: project.root } }));
  }
  return rows;
}

/** "Update all": each pending action once, in list order. */
export function updatePlan(rows: UpdateRow[]): UpdateStep[] {
  const steps = new Map<string, UpdateStep>();
  for (const item of rows) if (item.step) steps.set(item.step.id, item.step);
  return [...steps.values()];
}

/** A refused update answers with ok: false, not with a failed request. */
export function opOutcome(result: OpResult): { ok: boolean; output: string; error: string } {
  const output = [result.source_notice, result.stdout_tail?.trim()].filter(Boolean).join("\n");
  return { ok: result.ok, output, error: result.ok ? "" : result.error || "The installer failed. See the output." };
}

// Development only: answers for the Settings page's daemon routes in the browser mock.
// Return undefined for a path this page does not own. The state lives until the page reloads.
import type { Config } from "../settingsConfig";
import type { PathData } from "../settingsPath";
import type { PluginStatus } from "../settingsUpdates";

const LATEST = "1.4.0";
const plugin: PluginStatus = {
  latest: LATEST, update_available: true, releases: { latest: LATEST, selected: null, versions: [LATEST, "1.3.2"] },
  hosts: {
    codex: { installed: true, version: LATEST, root: "/Users/me/.agents/skills" },
    claude: { installed: true, version: "1.3.2", root: "/Users/me/.claude/skills" },
    cursor: { installed: true, version: "1.3.2", root: "/Users/me/.cursor/skills" },
    zed: { installed: true, version: LATEST, root: "/Users/me/.agents/skills" },
    kiro: { installed: false, version: null, root: "/Users/me/.kiro/skills" },
  },
  projects: [
    { root: "/work/atlas", runtime: true, runtime_version: LATEST, hooks: true },
    { root: "/work/done", runtime: true, runtime_version: "1.3.0", hooks: false },
    { root: "/work/gsd-path", runtime: true, runtime_version: "1.3.2", hooks: true },
    { root: "/work/notes", runtime: false, runtime_version: null, hooks: false },
  ],
};

let config: Config = {
  parents: ["/Users/me/work"], excludes: ["/Users/me/work/archive"], max_depth: 6, poll_seconds: 5, notify: true, history: true,
  session_dirs: ["~/.codex/sessions", "~/.claude/projects"],
  prices: { "gpt-5.5": { input: 1.25, cached: 0.125, output: 10 } },
};

const USER_FILE = "/Users/me/.gsd-path/config.json";
const user: { integration?: string; review_panel?: string; models: Record<string, string> } = {
  review_panel: "detected", models: { "models.roles.coder.model": "gpt-5.5", "models.roles.coder.effort": "high" },
};
const local: Record<string, { integration: string; review_panel?: string; models: Record<string, string> }> = {
  "/work/gsd-path": { integration: "direct", models: { "models.roles.reviewer.model": "claude-sonnet-5" } },
  "/work/atlas": { integration: "pull-request", models: {} },
  "/work/done": { integration: "direct", models: {} },
};
// The same lock rules as scripts/path_config.py: shipping mode at build, everything at ship.
const BUILD = ["/work/gsd-path"], SHIP = ["/work/atlas", "/work/done"];

function pathData(root: string | null): PathData {
  const from = (file: string, models: Record<string, string>) =>
    Object.fromEntries(Object.entries(models).map(([key, value]) => [key, { value, source: file }]));
  const data: PathData = {
    scope: root ? "project" : "user", locked: null, approved_review_panel: null,
    settings: {
      integration: { value: user.integration ?? "direct", source: user.integration ? USER_FILE : "built-in" },
      review_panel: { value: user.review_panel ?? "off", source: user.review_panel ? USER_FILE : "built-in" },
    },
    models: from(USER_FILE, user.models),
    roles: ["coder", "reviewer", "review_panel", "skeptic", "inspect_codebase", "inspect_docs", "docs_audit", "research", "decide", "roadmap", "plan", "plan_patch"],
    hosts: ["codex", "claude", "grok", "opencode", "copilot", "qwen", "antigravity", "cursor", "zed", "kiro", "kimi"],
  };
  if (!root) return data;
  const project = local[root];
  if (!project) throw new Error("Update this project runtime before editing Path settings.");
  const locked = BUILD.includes(root) || SHIP.includes(root);
  data.settings.integration = { value: project.integration, source: root + "/.project/STATE.md", current: project.integration,
    current_source: "project default", locked: locked ? "Shipping mode is locked when build starts." : null };
  if (project.review_panel) data.settings.review_panel = { value: project.review_panel, source: root + "/.project/config.json" };
  Object.assign(data.models, from(root + "/.project/model-policy.json", project.models));
  if (SHIP.includes(root)) data.locked = "Project settings are locked during ship and after shipment.";
  data.approved_review_panel = { value: "off", source: "default" };
  return data;
}

function writePath(body: { scope?: string; root?: string; action?: string; key?: string; value?: string }): PathData {
  const root = body.scope === "project" ? body.root ?? "" : null;
  const current = pathData(root);
  if (current.locked) throw new Error(current.locked);
  const key = body.key ?? "", reset = body.action === "reset";
  if (key === "review_panel" && body.value === "bad") throw new Error("unknown model family: bad");
  const target = root ? local[root] : user;
  if (key === "integration" || key === "review_panel") {
    if (root && key === "integration" && reset) throw new Error("choose an explicit project shipping mode");
    if (reset) delete (target as typeof user)[key];
    else (target as typeof user)[key] = body.value;
  } else if (reset) delete target.models[key];
  else target.models[key] = body.value!;
  return pathData(root);
}

function writeConfig(body: Partial<Config>): Config {
  for (const key of ["max_depth", "poll_seconds"] as const) {
    const value = body[key];
    if (value !== undefined && (!Number.isInteger(value) || value < 1)) throw new Error(`${key} must be a whole number of 1 or more`);
  }
  // One refusal to try: the daemon cannot read this folder.
  if (body.parents?.includes("/forbidden")) throw new Error("parents must be a list of non-empty strings");
  config = { ...config, ...body };
  return config;
}

const later = <T>(answer: () => T) => new Promise<T>((resolve, reject) => setTimeout(() => {
  try { resolve(answer()); } catch (error) { reject(error); }
}, 700));

function update(body: { scope?: string; root?: string; dry_run?: boolean }) {
  const argv = ["python3", "/Users/me/.gsd-path/src/scripts/install.py",
    ...(body.scope === "project" ? ["--runtime-upgrade", "--project", body.root!] : ["--update"]), ...(body.dry_run ? ["--dry-run"] : [])];
  if (body.scope === "project") {
    const project = plugin.projects!.find((item) => item.root === body.root);
    if (!project) throw new Error("root is not a watched project");
    if (body.dry_run) return { ok: true, argv, error: null, stdout_tail: `DRY RUN\nwould upgrade runtime ${project.runtime_version} -> ${LATEST} in ${body.root}/.gsd-path\nwould keep guard hooks` };
    // One failure to try: this project refuses the upgrade.
    if (body.root === "/work/done") {
      return { ok: false, argv, error: "installer exited 2: /work/done/.gsd-path/runtime.json is not writable. Run `chmod u+w /work/done/.gsd-path/runtime.json`, then try again.",
        stdout_tail: "checking /work/done\nerror: runtime.json is not writable" };
    }
    project.runtime_version = LATEST;
    return { ok: true, argv, error: null, stdout_tail: `upgraded runtime to ${LATEST} in ${body.root}/.gsd-path\nhealth check: ok` };
  }
  const stale = Object.entries(plugin.hosts!).filter(([, host]) => host.installed && host.version !== LATEST);
  if (body.dry_run) return { ok: true, argv, error: null, stdout_tail: "DRY RUN\n" + stale.map(([, host]) => `would update ${host.root}/gsd-path ${host.version} -> ${LATEST}`).join("\n") };
  for (const [, host] of stale) host.version = LATEST;
  plugin.update_available = false;
  return { ok: true, argv, error: null, stdout_tail: stale.map(([, host]) => `updated ${host.root}/gsd-path`).join("\n") + "\nhealth check: ok" };
}

export function mockSettings(method: string, url: URL, body: unknown): unknown {
  const post = method === "POST";
  switch (url.pathname) {
    case "/api/plugin/status": return post ? undefined : structuredClone(plugin);
    case "/api/plugin/update": return post ? later(() => update(body as Parameters<typeof update>[0])) : undefined;
    case "/api/config": return post ? writeConfig(body as Partial<Config>) : config;
    case "/api/path-config":
      return post ? later(() => writePath(body as Parameters<typeof writePath>[0]))
        : pathData(url.searchParams.get("scope") === "project" ? url.searchParams.get("root") : null);
    case "/api/diagnostics":
      return { daemon_version: "0.2.0", python_version: "3.12.4", platform: "macOS-15.6-arm64", config, projects: 4,
        plugin: { latest: plugin.latest, update_available: plugin.update_available }, logs: { "stderr.log": "", "stdout.log": "serving on 127.0.0.1:8765" } };
    default: return undefined;
  }
}

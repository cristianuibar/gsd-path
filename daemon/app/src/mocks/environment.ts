// Development only: answers for the Environment page's daemon routes in the browser mock.
// Return undefined for a path this page does not own. The rules follow the daemon's env_files.py.
// Add `&notoken` to the page address to see the monitor refuse every env route.
// `.env.production` of /work/atlas is a link: a file the daemon does not open.
type Body = { root: string; file: string; name?: string; dry_run?: boolean; changes?: { name: string; value?: string; remove?: boolean }[] };

const GIT: Record<string, string> = { ".env": "tracked", ".env.local": "ignored", ".env.development": "tracked", ".env.production": "untracked" };
const START: Record<string, [string, string][]> = {
  ".env": [["APP_ENV", "development"], ["LOG_LEVEL", "info"], ["OPTIONAL_FLAG", ""]],
  ".env.local": [["TYPESAFE_API_KEY", "tsk_mock_8f3a91c2d7"], ["DATABASE_URL", "postgres://app:pw@localhost:5432/app"]],
  ".env.development": [["LOG_LEVEL", "debug"]],
};
// One set of files per project root; a file that is not in the map does not exist.
const projects = new Map<string, Map<string, Map<string, string>>>();
const filesOf = (root: string) => {
  if (!projects.has(root)) projects.set(root, new Map(Object.entries(START).map(([file, vars]) => [file, new Map(vars)])));
  return projects.get(root)!;
};

export function mockEnvironment(method: string, url: URL, body: unknown): unknown {
  if (method !== "POST" || !url.pathname.startsWith("/api/env/")) return undefined;
  if (new URLSearchParams(location.search).has("notoken")) throw new Error("This monitor runs without the app's write token, so env files stay closed. Restart the monitor from the app.");
  const { root, file, name, changes = [], dry_run } = body as Body;
  if (!(file in GIT)) throw new Error("the file must be one of: .env, .env.local, .env.development, .env.production");
  if (root === "/work/atlas" && file === ".env.production") throw new Error(`${file} is a link or not a regular file; it is not opened`);
  const files = filesOf(root);
  const vars = files.get(file);

  if (url.pathname === "/api/env/list") {
    return { file, exists: !!vars, git: GIT[file], vars: [...(vars ?? [])].map(([key, value]) => ({ name: key, empty: value === "" })) };
  }
  if (url.pathname === "/api/env/reveal") {
    if (!vars?.has(name!)) throw new Error(`${file} has no variable with that name`);
    return { value: vars.get(name!) };
  }
  if (url.pathname === "/api/env/save") {
    const next = new Map(vars ?? []);
    const diff: { name: string; change: string }[] = [];
    if (new Set(changes.map((change) => change.name)).size !== changes.length) throw new Error("a variable is named more than once");
    for (const change of changes) {
      if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(change.name)) throw new Error("a variable name has letters, digits, and _ only, and does not start with a digit");
      if (change.remove) {
        if (!next.delete(change.name)) throw new Error(`${file} has no variable ${change.name} to remove`);
        diff.push({ name: change.name, change: "remove" });
      } else if (next.get(change.name) !== change.value) {
        diff.push({ name: change.name, change: next.has(change.name) ? "change" : "add" });
        next.set(change.name, change.value ?? "");
      }
    }
    if (dry_run || !diff.length) return { written: false, diff };
    files.set(file, next);
    return { written: true, diff };
  }
  return undefined;
}

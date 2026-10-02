// Pages live in location.hash: #/projects, #/project/<folder>, #/project/<folder>/files/<path>,
// #/project/<folder>/env, #/skills, #/stats[/<folder>], #/settings[/<tab>], #/tray.
export const SETTINGS_TABS = ["updates", "path", "monitoring", "usage", "app"] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];

export type Route =
  | { page: "projects" }
  | { page: "tray" }
  | { page: "skills" }
  | { page: "stats"; root: string | null }
  | { page: "settings"; tab: SettingsTab }
  | { page: "env"; root: string }
  | { page: "project"; root: string; file: string | null };

export const projectHash = (root: string) => "#/project/" + encodeURIComponent(root);
export const filesHash = (root: string, path = ".project/STATE.md") =>
  `${projectHash(root)}/files/${encodeURIComponent(path)}`;
export const envHash = (root: string) => `${projectHash(root)}/env`;
export const statsHash = (root: string | null) => "#/stats" + (root ? "/" + encodeURIComponent(root) : "");
export const settingsHash = (tab: SettingsTab) => "#/settings/" + tab;

export function parseRoute(hash: string): Route {
  const [page, first, second, third] = hash.replace(/^#\/?/, "").split("/");
  try {
    if (page === "tray" || page === "skills") return { page };
    if (page === "stats") return { page, root: first ? decodeURIComponent(first) : null };
    if (page === "settings") {
      return { page, tab: SETTINGS_TABS.find((tab) => tab === first) ?? "updates" };
    }
    if (page === "project" && first) {
      const root = decodeURIComponent(first);
      if (second === "env") return { page: "env", root };
      return { page: "project", root, file: second === "files" && third ? decodeURIComponent(third) : null };
    }
  } catch { /* a broken link: show the board */ }
  return { page: "projects" };
}

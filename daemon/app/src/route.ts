// Pages live in location.hash: #/projects, #/project/<folder>, #/project/<folder>/files/<path>, #/tray.
export type Route =
  | { page: "projects" }
  | { page: "tray" }
  | { page: "project"; root: string; file: string | null };

export const projectHash = (root: string) => "#/project/" + encodeURIComponent(root);
export const filesHash = (root: string, path = ".project/STATE.md") =>
  `${projectHash(root)}/files/${encodeURIComponent(path)}`;

export function parseRoute(hash: string): Route {
  const [page, root, files, file] = hash.replace(/^#\/?/, "").split("/");
  if (page === "tray") return { page: "tray" };
  if (page === "project" && root) {
    try {
      return { page: "project", root: decodeURIComponent(root), file: files === "files" && file ? decodeURIComponent(file) : null };
    } catch { /* a broken link: show the board */ }
  }
  return { page: "projects" };
}

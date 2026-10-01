// Setup, step 4: the folders the monitor watches.
import { useEffect, useState } from "react";
import { api, pickFolder } from "../shell";
import { message } from "../skillsApi";
import type { Status } from "../status";

type Config = { parents?: string[] };
// A change waits for its confirm: the new list and what the user sees.
type Ask = { parents: string[]; text: string; label: string; danger: boolean };

export function SetupFolders() {
  const [parents, setParents] = useState<string[] | null>(null);
  const [projects, setProjects] = useState<number | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const count = () => api<Status>("GET", "/status").then((status) => setProjects(status.projects.length), () => setProjects(null));
  useEffect(() => {
    api<Config>("GET", "/api/config").then((config) => setParents(config.parents ?? []), (failed) => setError(message(failed)));
    count();
  }, []);

  const save = async (change: Ask) => {
    setBusy(true); setError(null);
    try {
      setParents((await api<Config>("POST", "/api/config", { parents: change.parents })).parents ?? []);
      setAsk(null);
      count();
    } catch (failed) { setError(message(failed)); }
    setBusy(false);
  };
  const add = async () => {
    setError(null);
    try {
      const folder = await pickFolder();
      if (!folder || !parents) return;
      if (parents.includes(folder)) return setError(`${folder} is already watched.`);
      setAsk({ parents: [...parents, folder], text: `Watch ${folder}? The monitor looks for Git repositories under it.`, label: "Watch folder", danger: false });
    } catch (failed) { setError(message(failed)); }
  };
  const stop = (folder: string) => { setError(null); setAsk({
    parents: parents!.filter((item) => item !== folder), label: "Stop watching", danger: true,
    text: `Stop watching ${folder}? Its projects leave the board. No file is changed in them.`,
  }); };

  return <>
    <h1 className="title">Folders to watch</h1>
    <p className="lead setup-lead">The app looks for Git repositories under these folders and shows the ones that use Path on the board.</p>
    <div className="card sk-folders">
      {parents === null && !error && <div className="sk-folder sub">Loading folders…</div>}
      {parents?.length === 0 && <div className="sk-folder sub">No folder is watched yet.</div>}
      {parents?.map((folder) => (
        <div key={folder} className="sk-folder">
          <span className="mono grow">{folder}</span>
          <button className="btn small sk-danger" disabled={busy} onClick={() => stop(folder)}>Stop watching</button>
        </div>
      ))}
      <div className="sk-folder"><button className="btn" disabled={busy || parents === null} onClick={add}>Add folder…</button></div>
    </div>
    {ask && (
      <div className="sk-ask-box">
        <span className="grow">{ask.text}</span>
        <button className={ask.danger ? "btn small sk-danger" : "btn small primary"} disabled={busy} onClick={() => save(ask)}>{ask.label}</button>
        <button className="btn small" disabled={busy} onClick={() => setAsk(null)}>Cancel</button>
      </div>
    )}
    {error && <p className="error" role="alert">{error}</p>}
    {projects != null && (
      <div className="card sk-folder-count"><b>{projects}</b><span>{projects === 1 ? "project already uses Path" : "projects already use Path"}</span></div>
    )}
    <p className="note">Excluded folders and scan depth are in Settings → Monitoring.</p>
  </>;
}

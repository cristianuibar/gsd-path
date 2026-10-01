// The monitor runs. Slice A1c replaces this page with the project board.
import { useEffect, useState } from "react";
import { api, openUrl } from "../shell";
import type { Shell } from "../shell";
import { Logo } from "../ui";

type Status = { projects: unknown[] };

export function Ready({ shell, onStart }: { shell: Shell; onStart: () => void }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [offlineSince, setOfflineSince] = useState<string | null>(null);
  const [updated, setUpdated] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const poll = async () => {
      try {
        const next = await api<Status>("GET", "/status");
        if (!live) return;
        setStatus(next);
        setUpdated(new Date().toLocaleTimeString());
        setOfflineSince(null);
      } catch {
        if (live) setOfflineSince((since) => since ?? new Date().toLocaleTimeString());
      }
    };
    poll();
    const timer = setInterval(poll, 5000); // the daemon's own default poll interval
    return () => { live = false; clearInterval(timer); };
  }, [shell.port]);

  return (
    <>
      {offlineSince && (
        <div className="offline" role="status">
          <i className="dot bad" />
          <span className="grow"><b>Offline.</b> {updated ? `Showing the last update from ${updated}.` : "The monitor does not answer."}</span>
          <button className="btn small" onClick={onStart}>Start monitor</button>
        </div>
      )}
      <div className="center">
        <div className="column">
          <Logo size={26} label={false} />
          <div>
            <h1 className="title">{offlineSince ? "The monitor is stopped" : "The monitor is running"}</h1>
            <p className="lead">
              {offlineSince ? "Start it to see your projects. " : ""}
              {status ? `${status.projects.length} ${status.projects.length === 1 ? "project" : "projects"} watched.` : offlineSince ? "" : "Reading projects…"}
              {updated && !offlineSince ? ` Updated ${updated}.` : ""}
            </p>
          </div>
          <div className="actions">
            <button className="btn primary" onClick={() => openUrl(`http://127.0.0.1:${shell.port}/`)}>Open dashboard in browser</button>
          </div>
        </div>
      </div>
    </>
  );
}

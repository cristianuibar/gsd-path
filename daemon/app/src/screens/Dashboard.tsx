// The monitor runs: the header, the offline banner and the page the route names.
import type { Route } from "../route";
import type { Shell } from "../shell";
import { clock } from "../status";
import { Logo } from "../ui";
import { useStatus } from "../useStatus";
import { Board } from "./Board";
import { Files } from "./Files";
import { ProjectPage } from "./Project";

export function Dashboard({ shell, route, onStart }: { shell: Shell; route: Route; onStart: () => void }) {
  const { status, offline, refresh } = useStatus(shell.port);
  const updated = clock(status?.generated_at);
  const now = Date.parse(status?.generated_at ?? "") || Date.now();
  // A project that is no longer watched falls back to the board, as in the daemon dashboard.
  const project = route.page === "project" ? status?.projects.find((p) => p.root === route.root) : undefined;

  return (
    <>
      <header className="top">
        <Logo />
        <nav className="nav" aria-label="Main"><a href="#/projects" aria-current="page">Projects</a></nav>
        <span className="grow" />
        <button className="btn tall" onClick={refresh}>Refresh</button>
        <span className="updated" role="status">
          <i className={offline ? "dot bad" : status ? "dot ok" : "dot"} />
          {offline ? "Offline" : updated ? `Updated ${updated}` : "Connecting…"}
        </span>
      </header>
      {offline && (
        <div className="offline" role="status">
          <i className="dot bad" />
          <span className="grow"><b>Offline.</b> {updated ? `Showing the last update from ${updated}.` : "The monitor does not answer."}</span>
          <button className="btn small" onClick={onStart}>Start monitor</button>
        </div>
      )}
      {!project ? <Board status={status} offline={offline} now={now} />
        : route.page === "project" && route.file ? <Files project={project} path={route.file} />
        : <ProjectPage project={project} now={now} stamp={status!.generated_at} />}
    </>
  );
}

// The Projects board: one row per project, with filters and search.
import { useState } from "react";
import { boardRow, filterCounts, visibleProjects } from "../board";
import { projectHash } from "../route";
import type { Status } from "../status";
import { Cells } from "../ui";

export function Board({ status, offline, now }: { status: Status | null; offline: boolean; now: number }) {
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const projects = status?.projects ?? [];
  const shown = visibleProjects(projects, filter, query);
  const empty = !status ? (offline ? "Cannot load projects. Start the monitor." : "Loading projects…")
    : !projects.length ? "No projects yet. Projects in your watched folders appear here."
    : "No projects match this filter.";

  return (
    <main className="page" aria-label="Projects">
      <div className="board-head">
        <h1 className="title">Projects</h1>
        <p>What shipped. Where things stand. What’s ahead.</p>
      </div>
      <div className="filters">
        {filterCounts(projects).map((item) => (
          <button key={item.key} className="filter" aria-pressed={filter === item.key} onClick={() => setFilter(item.key)}>
            {item.label}<span>{item.count}</span>
          </button>
        ))}
        <label className="search">
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="m10.5 10.5 3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <input type="search" placeholder="Find a project…" aria-label="Find a project" value={query}
            onChange={(event) => setQuery(event.target.value)} />
        </label>
      </div>
      {shown.length ? (
        <div className="scroll-x"><div className="board">
          <div className="board-th">
            <span>Project</span><span>Current milestone</span><span>Status</span><span className="num">Tasks</span><span className="num">Usage</span>
          </div>
          {shown.map((project) => boardRow(project, now)).map((row) => (
            <div key={row.root} className="board-row" onClick={() => { location.hash = projectHash(row.root); }}>
              <div>
                <a className="pname" href={projectHash(row.root)}><i className={`dot small ${row.tone}`} />{row.name}</a>
                <div className="ppath">{row.path}</div>
              </div>
              <div>
                <div className="ms-name"><span className="mono">{row.number}</span> {row.slug}</div>
                <div className="ms-phase"><Cells cells={row.cells} />{row.phase}</div>
              </div>
              <div>
                <span className={`state ${row.state}`}>{row.label}</span>
                {row.note && <div className="state-note">{row.note}</div>}
                <div className="meta">{row.ago}</div>
              </div>
              <div className="num">{row.tasks}</div>
              <div className="num">{row.cost}<div className="meta">{row.turns}</div></div>
            </div>
          ))}
        </div></div>
      ) : <div className="empty">{empty}</div>}
      <div className="board-foot">
        <span>{shown.length} of {projects.length} projects</span><span>Usage reflects matched host sessions</span>
      </div>
    </main>
  );
}

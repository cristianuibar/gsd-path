// Settings → Updates: skills per agent folder and the runtime of each project. Each update is previewed first.
import { Fragment, useEffect, useState } from "react";
import { allCurrent, opOutcome, updatePlan, updateRows } from "../settingsUpdates";
import type { OpResult, PluginStatus, UpdateStep } from "../settingsUpdates";
import { api } from "../shell";
import { nameOf } from "../status";
import type { Shell } from "../shell";
import { AppUpdateRow } from "./AppUpdate";
import type { Status } from "../status";
import { FixText } from "../ui";

type Op = { step: UpdateStep; phase: "checking" | "preview" | "running" | "done" | "failed"; output: string; error: string };

export function UpdatesTab({ shell, status }: { shell: Shell; status: Status | null }) {
  const [plugin, setPlugin] = useState<PluginStatus | null>(null);
  const [error, setError] = useState("");
  const [ops, setOps] = useState<Record<string, Op>>({});
  /** "Update all" waits for one confirmation for every preview. */
  const [all, setAll] = useState<"" | "confirm" | "stopped">("");

  const load = () => api<PluginStatus>("GET", "/api/plugin/status").then(
    (next) => { setPlugin(next); setError(next.error ?? ""); }, (reason) => setError(String(reason)));
  useEffect(() => { load(); }, []);

  const names = Object.fromEntries((status?.projects ?? []).map((project) => [project.root, nameOf(project)]));
  const rows = plugin ? updateRows(plugin, names) : [];
  const plan = updatePlan(rows);
  const busy = Object.values(ops).some((op) => op.phase === "checking" || op.phase === "running");
  const setOp = (id: string, op: Op | null) => setOps((old) => {
    const { [id]: _gone, ...rest } = old;
    return op ? { ...rest, [id]: op } : rest;
  });

  /** One request to the installer. Returns true when it worked. */
  const send = async (step: UpdateStep, dryRun: boolean) => {
    setAll((old) => (old === "stopped" ? "" : old));
    setOp(step.id, { step, phase: dryRun ? "checking" : "running", output: "", error: "" });
    try {
      const result = opOutcome(await api<OpResult>("POST", "/api/plugin/update", { ...step.body, ...(dryRun ? { dry_run: true } : {}) }));
      setOp(step.id, { ...result, step, phase: !result.ok ? "failed" : dryRun ? "preview" : "done" });
      return result.ok;
    } catch (reason) {
      setOp(step.id, { step, phase: "failed", output: "", error: String(reason) });
      return false;
    }
  };
  const run = async (step: UpdateStep) => { await send(step, false); await load(); };
  const previewAll = async () => {
    setAll("");
    for (const step of plan) if (!(await send(step, true))) return;
    setAll("confirm");
  };
  const runAll = async () => {
    setAll("");
    for (const step of plan) {
      if (await send(step, false)) continue;
      setAll("stopped");
      break;
    }
    await load();
  };
  const cancelAll = () => { setAll(""); setOps({}); };

  // The preview and result of an action show under the last row it updates.
  const last = Object.fromEntries(rows.map((row) => [row.group, row.key]));
  return (
    <>
      <div className="set-head">
        <h2>Updates</h2>
        <button className="btn primary" disabled={busy || !plan.length || all === "confirm"} onClick={previewAll}>Update all</button>
      </div>
      <AppUpdateRow shell={shell} />
      {error && <div className="error" role="alert">Cannot read the update status. <FixText text={error} /></div>}
      {all === "confirm" && (
        <div className="set-confirm" role="status">
          <span className="grow"><b>{plan.length === 1 ? "1 update is" : `${plan.length} updates are`} ready.</b> Nothing has changed yet. Check each preview below.</span>
          <button className="btn small primary" onClick={runAll}>Update all now</button>
          <button className="btn small" onClick={cancelAll}>Cancel</button>
        </div>
      )}
      {all === "stopped" && <div className="error" role="alert">An update failed. The updates after it did not run.</div>}
      {!plugin ? (!error && <p className="note">Reading the installed versions…</p>) : (
        <>
          {allCurrent(rows) && !busy && (
            <p className="set-fine" role="status">
              <i className="dot ok" />Everything is up to date.{!rows.length && " No skills or project runtimes are installed."}
            </p>
          )}
          {rows.length > 0 && (
            <div className="card">
              {rows.map((row) => {
                const op = last[row.group] === row.key ? ops[row.group] : undefined;
                return (
                  <Fragment key={row.key}>
                    <div className="set-update">
                      <div><b>{row.name}</b><div className="set-path">{row.sub}</div></div>
                      <span className="set-version">{row.version}</span>
                      {row.state === "current" ? <span className="pill ok">Up to date</span>
                        : row.state === "unknown" ? <span className="pill mute">{row.note}</span>
                        : <button className="btn small" disabled={busy || all === "confirm" || !!ops[row.group]}
                            onClick={() => send(row.step!, true)}>{row.note || "Update"}</button>}
                    </div>
                    {op && <OpPanel op={op} solo={all !== "confirm"} busy={busy}
                      onRun={() => run(op.step)} onRetry={() => send(op.step, true)} onClose={() => setOp(row.group, null)} />}
                  </Fragment>
                );
              })}
            </div>
          )}
          {plugin.latest == null && !error && (
            <p className="note">The latest release is not known yet. Use “Check for updates” on the <a href="#/skills">Skills</a> page.</p>
          )}
          <p className="note">The skills and each project runtime update separately. One skills update writes every agent folder.</p>
        </>
      )}
    </>
  );
}

/** The preview, progress and result of one update, under its row. */
function OpPanel({ op, solo, busy, onRun, onRetry, onClose }: {
  op: Op; solo: boolean; busy: boolean; onRun: () => void; onRetry: () => void; onClose: () => void;
}) {
  const output = op.output ? <pre className="code set-output">{op.output}</pre> : null;
  return (
    <div className="set-op" aria-live="polite">
      {op.phase === "checking" && <span className="sub">Preparing the preview…</span>}
      {op.phase === "running" && <span className="sub">Updating… Do not close the app.</span>}
      {op.phase === "preview" && (
        <>
          <div><b>Preview: {op.step.label}.</b> <span className="sub">Nothing has changed yet.</span></div>
          {output ?? <span className="sub">The installer printed no preview.</span>}
          {solo && (
            <div className="actions">
              <button className="btn small primary" disabled={busy} onClick={onRun}>Update now</button>
              <button className="btn small" disabled={busy} onClick={onClose}>Cancel</button>
            </div>
          )}
        </>
      )}
      {op.phase === "done" && (
        <>
          <div className="line"><span className="pill ok">Updated</span><span className="sub grow">{op.step.label}</span>
            <button className="link" onClick={onClose}>Hide</button></div>
          {output}
        </>
      )}
      {op.phase === "failed" && (
        <>
          <div className="error" role="alert"><b>The update did not finish.</b> <FixText text={op.error} /></div>
          {output}
          <div className="actions">
            <button className="btn small" disabled={busy} onClick={onRetry}>Try again</button>
            <button className="btn small" disabled={busy} onClick={onClose}>Close</button>
          </div>
        </>
      )}
    </div>
  );
}

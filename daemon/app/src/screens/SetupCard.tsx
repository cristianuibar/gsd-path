// The project page's right column: "Setup in this project", member repositories, and the removal of Path.
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { doctorReport, memberRows, setupRows } from "../project";
import type { Member, SetupRow } from "../project";
import { envHash, projectHash } from "../route";
import { api } from "../shell";
import type { OpResult, UninstallPlan } from "../skills";
import { applyUninstall, message, planUninstall, projectOp, usePlugin } from "../skillsApi";
import type { Project } from "../status";
import { CopyButton } from "../ui";
import { Output, PlanBox } from "./SkillsParts";
import "./setup.css";
import "./skills.css";

type Members = { ok: boolean; members?: Member[]; error: string | null };
// One write waits for its confirm: the dry-run output (or a text for an action without one) and the real call.
type Ask = { at: string; label: string; text: string; output: boolean; apply: () => Promise<OpResult> };
type Note = { at: string; ok: boolean; text: string; output?: string };

/** `children` (usage and activity) sit between the cards and the removal link. */
export function SetupCard({ project: p, children }: { project: Project; children: ReactNode }) {
  const { plugin, hosts, error, reload } = usePlugin(p.root);
  const [members, setMembers] = useState<Members | null>(null);
  const [doctor, setDoctor] = useState<OpResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // the row or member that works now
  const [ask, setAsk] = useState<Ask | null>(null);
  const [note, setNote] = useState<Note | null>(null);
  const [removal, setRemoval] = useState<UninstallPlan | null>(null);

  const loadMembers = () => projectOp<Members>(p.root, "members").then(setMembers, (failed) => setMembers({ ok: false, error: message(failed) }));
  useEffect(() => {
    setMembers(null); setDoctor(null); setAsk(null); setNote(null); setRemoval(null);
    loadMembers();
  }, [p.root]);

  const setup = plugin?.projects.find((item) => item.root === p.root);
  const names = Object.fromEntries(hosts.map((host) => [host.id, host.name]));
  const rows = setupRows(setup, plugin?.latest ?? null, doctor, names);
  const report = doctor && doctorReport(doctor);

  /** Run one call for the row or member `at`. A rejected call shows its message there. */
  const guard = async (at: string, work: () => Promise<void>) => {
    setBusy(at); setNote(null);
    try { await work(); } catch (failed) { setNote({ at, ok: false, text: message(failed) }); }
    setBusy(null);
  };
  /** Dry run first; the confirm then runs the same call for real. */
  const propose = (at: string, label: string, call: (dry_run: boolean) => Promise<OpResult>) => guard(at, async () => {
    setAsk(null);
    const plan = await call(true);
    if (!plan.ok) throw new Error(plan.error || "The dry run failed.");
    setAsk({ at, label, text: plan.stdout_tail ?? "", output: true, apply: () => call(false) });
  });
  const confirm = (pending: Ask) => guard(pending.at, async () => {
    setAsk(null);
    const result = await pending.apply();
    setNote({ at: pending.at, ok: result.ok, text: result.ok ? "Done." : result.error || "The operation failed.",
      output: [result.source_notice, result.stdout_tail].filter(Boolean).join("\n") });
    setDoctor(null); // the last health check is about the old state
    reload();
    loadMembers();
  });

  const act = (row: SetupRow) => {
    const run = row.action!.run, label = row.action!.label;
    if (run === "doctor") return guard(row.key, async () => setDoctor(await projectOp(p.root, "doctor")));
    if (run === "update") {
      return propose(row.key, label, (dry_run) => api<OpResult>("POST", "/api/plugin/update", { scope: "project", root: p.root, dry_run }));
    }
    return propose(row.key, label, (dry_run) => projectOp(p.root, run, { dry_run }));
  };
  const memberHooks = (member: string) =>
    propose(member, "Install hooks", (dry_run) => projectOp(p.root, "member-hooks", { member, dry_run }));
  // Repair has no dry run in the daemon, so the text says what it does.
  const repair = (at: string) => {
    setNote(null);
    setAsk({ at, label: "Repair", output: false, apply: () => projectOp(p.root, "member-repair"),
      text: "Repair rewrites the member markers that are missing or stale, for every member of this project. It changes no other file." });
  };
  const planRemoval = () => guard("remove", async () => setRemoval((await planUninstall({ scope: "project", root: p.root })).plan));
  const remove = () => guard("remove", async () => {
    const result = await applyUninstall({ scope: "project", root: p.root });
    setRemoval(null);
    setNote(result.ok ? { at: "remove", ok: true, text: "Path was removed from this project.", output: result.applied.join("\n") }
      : { at: "remove", ok: false, text: result.errors.map((item) => `${item.path}: ${item.error}`).join("\n") });
    setDoctor(null);
    reload();
  });

  /** The confirm box and the result of the row or member `at`. */
  const under = (at: string): ReactNode => <>
    {ask?.at === at && (
      <div className="sk-ask">
        {ask.output ? <Output text={ask.text} /> : <div className="sub">{ask.text}</div>}
        <div className="actions">
          <button className="btn small primary" disabled={!!busy} onClick={() => confirm(ask)}>{ask.label}</button>
          <button className="btn small" onClick={() => setAsk(null)}>Cancel</button>
        </div>
      </div>
    )}
    {busy === at && <div className="sk-ask sub" role="status">Working…</div>}
    {note?.at === at && (
      <div className="sk-ask">
        <div className={note.ok ? "sk-done-line" : "error"} role={note.ok ? "status" : "alert"}>{note.ok && <i className="dot ok" />}{note.text}</div>
        {note.output && <Output text={note.output} />}
      </div>
    )}
  </>;

  const list = members?.ok ? memberRows(members.members ?? [], plugin?.projects.map((item) => item.root) ?? []) : [];

  return <>
    <div className="card setup-card">
      <div className="setup-card-head">Setup in this project</div>
      {error && <div className="setup-row"><p className="error" role="alert">{error} <button className="link" onClick={reload}>Try again</button></p></div>}
      {!setup && !error && <div className="setup-row sub">{plugin ? "The monitor does not report the setup of this project." : "Loading setup…"}</div>}
      {rows.map((row) => (
        <div key={row.key} className="setup-row">
          <div className="grow">
            <div className="setup-label">{row.label}</div>
            <div className="setup-value">{row.value}</div>
            <div className="sub">{row.sub}</div>
          </div>
          {row.action?.run === "env" ? <a className="btn small" href={envHash(p.root)}>{row.action.label}</a>
            : row.action ? <button className={row.action.primary ? "btn small primary" : "btn small"} disabled={!!busy} onClick={() => act(row)}>{row.action.label}</button>
            : row.ok ? <span className="pill ok">Up to date</span> : null}
          {under(row.key)}
          {row.key === "doctor" && report && busy !== "doctor" && (
            <ul className="sk-doctor">
              {report.lines.map((line, index) => <li key={index} className={line.kind === "error" ? "sk-finding" : undefined}>{line.text}</li>)}
              {!report.lines.length && <li>The health check printed nothing.</li>}
            </ul>
          )}
        </div>
      ))}
    </div>

    {members && (!members.ok || list.length > 0) && (
      <div className="card setup-card">
        <div className="setup-card-head">Member repositories <span>coordinator · .project/MEMBERS.md</span></div>
        {!members.ok && (
          <div className="setup-row">
            <div className="grow"><div className="error" role="alert">{members.error}</div></div>
            <button className="btn small" disabled={!!busy} onClick={() => repair("members")}>Repair</button>
            {under("members")}
          </div>
        )}
        {list.map((member) => (
          <div key={member.checkout} className="setup-row">
            <div className="grow">
              {member.watched ? <a className="member-name" href={projectHash(member.checkout)}>{member.name}</a> : <b>{member.name}</b>}
              <div className="mono setup-path">{member.checkout}</div>
              <div className="sk-pills">
                <span className={`pill ${member.marker.tone}`}>{member.marker.label}</span>
                <span className={`pill ${member.hooks.tone}`}>{member.hooks.label}</span>
                <span className="pill mute">{member.integration}</span>
              </div>
              {member.reason && <div className="member-reason mono">{member.reason}</div>}
            </div>
            <span className="actions">
              {member.actions.includes("repair") && <button className="btn small" disabled={!!busy} onClick={() => repair(member.checkout)}>Repair</button>}
              {member.actions.includes("hooks") && <button className="btn small" disabled={!!busy} onClick={() => memberHooks(member.checkout)}>Install hooks</button>}
            </span>
            {under(member.checkout)}
          </div>
        ))}
        <div className="setup-foot-note">
          <span className="grow">Joining a repository happens in your agent: <span className="mono">/path</span> then <span className="mono">members add</span>.</span>
          <CopyButton text="/path" label="Copy /path" className="btn tiny" />
        </div>
      </div>
    )}

    {children}

    <div className="sk-remove">
      <button className="link quiet" disabled={!!busy} aria-expanded={!!removal} onClick={() => (removal ? setRemoval(null) : planRemoval())}>
        Remove Path from this project
      </button>
      {removal && <PlanBox plan={removal} confirm="Remove" busy={busy === "remove"} onConfirm={remove} onCancel={() => setRemoval(null)} />}
      {under("remove")}
    </div>
  </>;
}

// Setup, step 3: install Path skills into the selected agents.
import { useEffect, useState } from "react";
import { agentsWord, installTargets } from "../setup";
import { failure, targetVersion } from "../skills";
import type { Failure, HostInfo, PluginStatus } from "../skills";
import { installSkills, message } from "../skillsApi";
import { FailureCard, Output, ReleasePicker } from "./SkillsParts";

type Phase =
  | { kind: "idle" } | { kind: "preview"; text: string } | { kind: "running"; text: string }
  | { kind: "done"; text: string } | { kind: "failed"; failure: Failure; output: string };

export function SetupSkills({ hosts, selected, plugin, reload, onBusy }: {
  hosts: HostInfo[]; selected: string[]; plugin: PluginStatus | null; reload: () => void; onBusy: (busy: boolean) => void;
}) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const targets = installTargets(hosts, selected), ids = targets.flatMap((target) => target.ids);
  const labels = hosts.filter((host) => ids.includes(host.id)).map((host) => host.name), count = agentsWord(ids.length);
  const version = targetVersion(plugin), git = plugin?.releases?.source === "git";
  const running = phase.kind === "running";
  useEffect(() => onBusy(running), [running]);

  const fail = (error: string, output = "") => setPhase({ kind: "failed", failure: failure("installed", labels, error), output });
  const preview = async () => {
    setPhase({ kind: "running", text: "Reading the plan…" });
    try {
      const result = await installSkills(ids, true);
      if (result.ok) setPhase({ kind: "preview", text: result.stdout_tail ?? "" });
      else fail(result.error || "The dry run failed.", result.stdout_tail);
    } catch (failed) { fail(message(failed)); }
  };
  const install = async () => {
    setPhase({ kind: "running", text: `Installing into ${count}…` });
    try {
      const result = await installSkills(ids, false);
      if (result.ok) setPhase({ kind: "done", text: `Installed ${version ?? "Path skills"} in ${count}.` });
      else fail(result.error || "The installer failed.", result.stdout_tail);
    } catch (failed) { fail(message(failed)); }
    reload();
  };

  return <>
    <h1 className="title">Install Path skills</h1>
    <p className="lead setup-lead">
      Skills go into the global skills folder of each selected agent,
      {git ? " from the repository set in daemon.json." : " from a verified npm release."}
    </p>
    <div className="card setup-install">
      {!git && (
        <div className="line wrap">
          <ReleasePicker releases={plugin?.releases} disabled={running} onChanged={() => { setPhase({ kind: "idle" }); reload(); }} />
          <span className="sub sk-field-side">sha512 checked before anything is written</span>
        </div>
      )}
      {targets.length ? (
        <div className="sk-targets">
          {targets.map((target) => <div key={target.path}><b>{target.label}</b><span className="mono">{target.path}</span></div>)}
        </div>
      ) : <div className="sub">No agent is selected. Go back to choose agents, or continue without skills.</div>}
      {phase.kind === "preview" && <Output text={phase.text} />}
      {phase.kind === "running" && <div role="status"><div className="bar busy"><i /></div><div className="sub">{phase.text}</div></div>}
      {phase.kind === "done" && <div className="sk-done-line" role="status"><i className="dot ok" />{phase.text}</div>}
      {phase.kind === "failed" && <FailureCard failure={phase.failure} output={phase.output} onRetry={install} />}
      {(phase.kind === "idle" || phase.kind === "preview") && targets.length > 0 && (
        <div className="actions">
          <button className="btn primary" onClick={install}>Install in {count}</button>
          {phase.kind === "idle" && <button className="btn" onClick={preview}>Preview first</button>}
        </div>
      )}
    </div>
  </>;
}

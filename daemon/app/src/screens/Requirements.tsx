// Setup, step 1. Later steps (Agents, Skills, Watch folders) join the rail in slice A4.
import { requirementRows } from "../screen";
import type { Shell } from "../shell";
import { ActionButton, Logo } from "../ui";

const STEPS = ["Requirements"];
const TONE = { ok: "ok", warn: "warn", miss: "bad" } as const;

export function Requirements({ shell, onRetry, onDone }: { shell: Shell; onRetry: () => void; onDone: () => void }) {
  const { rows, blocked } = requirementRows(shell);
  const waiting = blocked || shell.phase !== "ready";
  return (
    <div className="setup">
      <aside className="rail">
        <Logo size={20} />
        {STEPS.map((label, index) => (
          <div key={label} className="step current" aria-current="step">
            <span className="step-mark">{index + 1}</span>{label}
          </div>
        ))}
        <div className="rail-foot">Nothing is installed or written until you click it. Every step can be redone from Settings.</div>
      </aside>
      <div className="setup-main">
        <div className="setup-body">
          <div className="eyebrow">Step 1 of {STEPS.length}</div>
          <h1 className="title">What this computer needs</h1>
          <p className="lead" style={{ marginBottom: 26 }}>
            Path runs on Python and Git. The app checks for both and offers a fix when one is missing.
          </p>
          <div className="card">
            {rows.map((row) => (
              <div className="req" key={row.id}>
                <div className="grow">
                  <div className="line" style={{ gap: 8, flexWrap: "wrap" }}>
                    <i className={`dot ${row.tone === "miss" && !row.required ? "" : TONE[row.tone]}`} />
                    <b>{row.name}</b>
                    <span className={`pill ${row.tone === "miss" && !row.required ? "mute" : TONE[row.tone]}`}>{row.pill}</span>
                  </div>
                  <div className="req-detail">{row.detail}</div>
                  <div className="req-hint">{row.hint}</div>
                </div>
                {row.action && <ActionButton action={row.action} />}
              </div>
            ))}
          </div>
          {shell.os === "windows" && (
            <p className="note">The app window also needs the WebView2 runtime. The installer adds it when missing, so there is nothing to do here.</p>
          )}
          {blocked && <p className="note danger">Install the required items, then choose Check again.</p>}
        </div>
        <div className="setup-foot">
          <span style={{ marginLeft: "auto" }} />
          <button className="btn" onClick={onRetry}>Check again</button>
          <button className="btn primary" disabled={waiting} onClick={onDone}>Open dashboard</button>
        </div>
      </div>
    </div>
  );
}

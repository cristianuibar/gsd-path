// Shown once when the launch check found startup entries from the old tray apps.
import type { LegacyEntry, Shell } from "../shell";
import { Logo } from "../ui";

// Names come from legacy_registrations() in daemon/gsd_daemon/launch.py.
const ENTRY: Record<string, [string, string]> = {
  "launch-agent": ["LaunchAgent", "org.gsd-path.daemon"],
  "tray-app": ["Swift tray app", "~/Applications/GSDPathTray.app"],
  "login-item": ["Swift tray app login item", "GSDPathTray in Login Items"],
  "login-item-unknown": ["Login items could not be read", "System Events access was not allowed"],
  "startup-shortcut": ["Startup shortcut", "gsd-path-daemon.lnk in the Startup folder"],
  "systemd-unit": ["systemd user unit", "gsd-path-daemon.service"],
};

function monitorLine(shell: Shell): [string, string, string, "ok" | "warn"] {
  const launch = shell.launch!;
  if (shell.phase !== "ready") return ["Not started yet", "Fix the items the app reports, then check again.", "Waiting", "warn"];
  if (launch.replaced) {
    return [`Version ${launch.replaced} was running`,
      `The app bundles ${launch.version}, so it stopped the old one and started its own.`, "Replaced", "ok"];
  }
  if (launch.action === "reuse") {
    return [`Version ${launch.version} is running`, "It is current, so the app uses it and leaves it running on quit.", "Kept", "ok"];
  }
  return [`Version ${launch.version} started`, "The app runs its own monitor and stops it on quit.", "Started", "ok"];
}

function Entry({ entry }: { entry: LegacyEntry }) {
  const [name, detail] = ENTRY[entry.name] ?? [entry.name, ""];
  return (
    <div className="row">
      <div className="line">
        <i className={`dot ${entry.removed ? "ok" : "bad"}`} />
        <div className="grow"><b>{name}</b><div className="mono sub" style={{ fontSize: 12 }}>{detail}</div></div>
        <span className={`pill ${entry.removed ? "ok" : "bad"}`}>{entry.removed ? "Removed" : "Still present"}</span>
      </div>
      {!entry.removed && (
        <div className="manual"><div style={{ fontWeight: 600, marginBottom: 4 }}>Remove it by hand</div>
          <div className="mono" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{entry.fix}</div></div>
      )}
    </div>
  );
}

export function FirstLaunch({ shell, onRetry, onDone }: { shell: Shell; onRetry: () => void; onDone: () => void }) {
  const launch = shell.launch!;
  const failed = launch.legacy.some((entry) => !entry.removed);
  const [title, text, label, tone] = monitorLine(shell);
  return (
    <div className="center">
      <div className="column">
        <div>
          <Logo size={26} label={false} />
          <h1 className="title" style={{ marginTop: 14 }}>Moving to the new app</h1>
          <p className="lead">An earlier setup is still registered to start at login. The app removes it first so only one monitor runs.</p>
        </div>
        <div className="card">
          <div className="row-head">1 · Old startup entries</div>
          {launch.legacy.map((entry) => <Entry key={entry.name} entry={entry} />)}
          <div className="row-head">2 · Background monitor</div>
          <div className="row line">
            <i className={`dot ${tone}`} />
            <div className="grow"><b>{title}</b><div className="sub">{text}</div></div>
            <span className={`pill ${tone}`}>{label}</span>
          </div>
          <div className="row-head">3 · Launch at login</div>
          <div className="row line">
            <div className="grow" style={{ fontSize: 13, color: "var(--dim)" }}>
              {failed ? "Stays off until the old entry above is removed, so two monitors never start."
                : shell.autostart ? "Turned on. The app starts at login and keeps the monitor running."
                : "Off. Turn it on in Settings."}
            </div>
            <span className={`pill ${failed ? "warn" : shell.autostart ? "ok" : "mute"}`}>
              {failed ? "Waiting" : shell.autostart ? "On" : "Off"}
            </span>
          </div>
        </div>
        <div className="actions">
          {failed ? (
            <>
              <button className="btn primary" onClick={onRetry}>Check again</button>
              <button className="btn" onClick={onDone}>Continue without launch at login</button>
            </>
          ) : <button className="btn primary" onClick={onDone}>Open dashboard</button>}
        </div>
      </div>
    </div>
  );
}

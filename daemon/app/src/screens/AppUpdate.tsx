// The app's own update: the "ready" dialog, the refused state, and the row in Settings → Updates.
import { useState } from "react";
import { appUpdateRow, refusedText } from "../appUpdate";
import { checkUpdate, installUpdate } from "../shell";
import type { Shell } from "../shell";
import { CopyButton } from "../ui";

/** Settings and the tray ask the main window to show the dialog with this event. */
export const SHOW_UPDATE = "gsd-path:show-update";

export function AppUpdateDialog({ shell, onClose }: { shell: Shell; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const row = appUpdateRow(shell);
  if (!row || row.state === "check-failed" || !shell.update) return null;
  // A refused install comes back as shell.update_error through the shell event.
  const install = () => { setBusy(true); installUpdate().catch(() => undefined).finally(() => setBusy(false)); };
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="update-title">
      <div className="modal-card">
        {row.state === "refused" ? (
          <>
            <b id="update-title">Update {shell.update.version} was not installed</b>
            <span>{refusedText(shell)}</span>
            <div className="modal-actions">
              <CopyButton text={refusedText(shell)} label="Copy details" />
              <button className="btn" onClick={onClose}>Close</button>
              <button className="btn primary" disabled={busy} onClick={install}>{busy ? "Trying…" : "Try again"}</button>
            </div>
          </>
        ) : (
          <>
            <b id="update-title">OpenGSD Path {shell.update.version} is ready</b>
            <span>The app restarts to finish. Running projects and agents are not affected.{row.notes ? ` ${row.notes}` : ""}</span>
            <div className="modal-actions">
              <button className="btn" disabled={busy} onClick={onClose}>Later</button>
              <button className="btn primary" disabled={busy} onClick={install}>{busy ? "Updating…" : "Restart and update"}</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** The app's row at the top of Settings → Updates. */
export function AppUpdateRow({ shell }: { shell: Shell }) {
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState(false);
  const row = appUpdateRow(shell);
  const check = () => { setChecking(true); checkUpdate().catch(() => undefined).finally(() => { setChecking(false); setChecked(true); }); };
  return (
    <div className="card app-update">
      <div className="set-update">
        <div><b>OpenGSD Path app</b>
          <div className="set-path">
            {row?.state === "check-failed" ? `The update check failed: ${shell.update_error}`
              : row?.state === "refused" ? refusedText(shell)
              : checked && !row ? "This is the newest version." : "Updates are signed; the app refuses one that does not match."}
          </div>
        </div>
        <span className="set-version">{row?.text ?? shell.version}</span>
        {row && row.state !== "check-failed"
          ? <button className="btn small primary" onClick={() => dispatchEvent(new Event(SHOW_UPDATE))}>{row.state === "refused" ? "Details" : "Update…"}</button>
          : <button className="btn small" disabled={checking} onClick={check}>{checking ? "Checking…" : "Check for updates"}</button>}
      </div>
    </div>
  );
}

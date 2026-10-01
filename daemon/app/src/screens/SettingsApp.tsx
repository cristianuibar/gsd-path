// Settings → App: launch at login, appearance, setup, diagnostics.
import { useEffect, useState } from "react";
import { api, openLogs, setAutostart } from "../shell";
import type { Shell } from "../shell";
import { setTheme, storedTheme } from "../theme";
import type { Theme } from "../theme";
import { Field, Toggle } from "./SettingsParts";

const THEMES: [Theme, string][] = [["system", "System"], ["light", "Light"], ["dark", "Dark"]];
type Diagnostics = { daemon_version?: string; [key: string]: unknown };

export function AppTab({ shell }: { shell: Shell }) {
  // The shell event updates `shell.autostart`; the answer of the call shows first.
  const [login, setLogin] = useState(shell.autostart);
  const [loginBusy, setLoginBusy] = useState(false);
  const [theme, setChoice] = useState(storedTheme);
  const [version, setVersion] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const fail = (key: string) => (reason: unknown) => setErrors((old) => ({ ...old, [key]: String(reason) }));
  const clear = (key: string) => setErrors((old) => ({ ...old, [key]: "" }));

  useEffect(() => setLogin(shell.autostart), [shell.autostart]);
  useEffect(() => {
    api<Diagnostics>("GET", "/api/diagnostics").then((report) => setVersion(report.daemon_version ?? null), fail("version"));
  }, [shell.port]);

  const toggleLogin = async (enabled: boolean) => {
    setLoginBusy(true); clear("login");
    await setAutostart(enabled).then((next) => setLogin(next.autostart), fail("login"));
    setLoginBusy(false);
  };
  const choose = (choice: Theme) => { setTheme(choice); setChoice(choice); };
  const again = () => { localStorage.removeItem("gsd-path.setup-done"); location.reload(); };
  const copyReport = async () => {
    clear("report");
    try {
      await navigator.clipboard.writeText(JSON.stringify(await api<Diagnostics>("GET", "/api/diagnostics"), null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (reason) { fail("report")(reason); }
  };
  const problem = (key: string, lead: string) => errors[key] && <div className="error set-problem" role="alert">{lead} {errors[key]}</div>;

  return (
    <>
      <h2 className="set-h2">App</h2>
      <div className="card set-card">
        <Field name="Launch at login" hint="Starts the app and its background monitor when you sign in.">
          <Toggle on={login} label="Launch at login" disabled={loginBusy} onChange={toggleLogin} />
        </Field>
        {problem("login", "Launch at login did not change.")}
        <Field name="Appearance" hint="Follows the system by default.">
          <div className="seg" role="group" aria-label="Appearance">
            {THEMES.map(([value, label]) => <button key={value} aria-pressed={theme === value} onClick={() => choose(value)}>{label}</button>)}
          </div>
        </Field>
        <Field name="Setup" hint="Run the first-launch steps again: requirements, agents, skills, folders.">
          <button className="btn small" onClick={again}>Run setup again</button>
        </Field>
        <Field name="Diagnostics" hint="Logs and a copyable report for support.">
          <button className="btn small" onClick={() => { clear("logs"); openLogs().catch(fail("logs")); }}>Open logs</button>
          <button className="btn small" onClick={copyReport}>{copied ? "Copied" : "Copy report"}</button>
        </Field>
        {problem("logs", "Cannot open the logs folder.")}
        {problem("report", "Cannot copy the report.")}
      </div>
      <p className="note">
        {version ? <>Monitor version <span className="mono">{version}</span></>
          : errors.version ? `Monitor version unavailable: ${errors.version}` : "Reading the monitor version…"}
        {" · "}port <span className="mono">{shell.port}</span>
      </p>
    </>
  );
}

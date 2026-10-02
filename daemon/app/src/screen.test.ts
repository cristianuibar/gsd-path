import { describe, expect, it } from "vitest";
import { heldByDaemon, pickScreen, requirementRows } from "./screen";
import type { Launch, Shell } from "./shell";

const launch = (over: Partial<Launch> = {}): Launch => ({
  action: "start", port: 8765, version: "0.2.0", autostart_ok: true, problems: [], legacy: [],
  replaced: null,
  requirements: [
    { id: "python", required: true, state: "ready", detail: "3.12.6" },
    { id: "git", required: true, state: "ready", detail: "2.39.5 (Apple Git-154)" },
    { id: "gh", required: false, state: "missing", detail: null },
  ],
  ...over,
});
const shell = (over: Partial<Shell> = {}): Shell => ({
  phase: "ready", os: "macos", port: 8765, python_missing: false, launch: launch(), error: null,
  autostart: true, owned: true, version: "0.1.0", update: null, update_error: null, ...over,
});
const blocked = (kind: string) =>
  shell({ phase: "blocked", launch: launch({ action: "setup", problems: [{ kind, message: "m", fix: "f", blocking: true }] }) });
const done = { setupDone: true, firstLaunchSeen: false };

describe("pickScreen", () => {
  it("waits while the launch check runs", () => {
    expect(pickScreen(shell({ phase: "checking", launch: null }), done)).toBe("checking");
  });
  it("shows setup until the user finishes it, then the dashboard", () => {
    expect(pickScreen(shell(), { setupDone: false, firstLaunchSeen: false })).toBe("requirements");
    expect(pickScreen(shell(), done)).toBe("ready");
  });
  it("shows the migration once when old startup entries were found", () => {
    const migrated = shell({ launch: launch({ legacy: [{ name: "launch-agent", removed: true, fix: "x" }] }) });
    expect(pickScreen(migrated, done)).toBe("first-launch");
    expect(pickScreen(migrated, { setupDone: true, firstLaunchSeen: true })).toBe("ready");
  });
  it("after setup, missing Python and a taken port get their own screens", () => {
    expect(pickScreen(shell({ phase: "blocked", python_missing: true, launch: null }), done)).toBe("python");
    expect(pickScreen(blocked("port"), done)).toBe("port");
    expect(pickScreen(blocked("install"), done)).toBe("problem");
    expect(pickScreen(shell({ phase: "blocked", launch: null, error: "boom" }), done)).toBe("problem");
  });
  it("during setup, a missing requirement stays on the Requirements step", () => {
    const fresh = { setupDone: false, firstLaunchSeen: false };
    expect(pickScreen(shell({ phase: "blocked", python_missing: true, launch: null }), fresh)).toBe("requirements");
    expect(pickScreen(blocked("git"), fresh)).toBe("requirements");
    expect(pickScreen(blocked("python-venv"), fresh)).toBe("requirements");
    expect(pickScreen(blocked("port"), fresh)).toBe("port");
  });
  it("a non-blocking problem does not hide the dashboard", () => {
    const noted = shell({ launch: launch({ autostart_ok: false, problems: [{ kind: "autostart", message: "m", fix: "f", blocking: false }] }) });
    expect(pickScreen(noted, done)).toBe("ready");
  });
});

describe("the port screen", () => {
  const port = (detail?: object) => ({ kind: "port", message: "m", fix: "f", blocking: true, detail });

  it("tells a stuck GSD Path daemon from another program", () => {
    expect(heldByDaemon(port({ owner: "daemon", pid: 7 }))).toBe(true);
    expect(heldByDaemon(port({ owner: "other", pid: 7 }))).toBe(false);
    expect(heldByDaemon(port())).toBe(false);
  });
});

describe("requirementRows", () => {
  const byId = (s: Shell) => Object.fromEntries(requirementRows(s).rows.map((row) => [row.id, row]));

  it("blocks only on a missing required item", () => {
    expect(requirementRows(shell()).blocked).toBe(false); // gh missing is optional
    const noGit = shell({ launch: launch({ requirements: [{ id: "git", required: true, state: "missing", detail: null }] }) });
    expect(requirementRows(noGit).blocked).toBe(true);
    expect(byId(noGit).git).toMatchObject({ tone: "miss", pill: "Required" });
  });
  it("shows only the Python row when Python is missing, with the fix for this OS", () => {
    const mac = requirementRows(shell({ phase: "blocked", python_missing: true, launch: null }));
    expect(mac.blocked).toBe(true);
    expect(mac.rows.map((row) => row.id)).toEqual(["python"]);
    expect(mac.rows[0].action).toEqual({ label: "Open download page", url: "https://www.python.org/downloads/" });
    const win = requirementRows(shell({ os: "windows", phase: "blocked", python_missing: true, launch: null }));
    expect(win.rows[0].action).toEqual({ label: "Copy winget command", copy: "winget install Python.Python.3.12" });
  });
  it("recommends a newer Python for 3.9 and does not block", () => {
    const old = shell({ launch: launch({ requirements: [{ id: "python", required: true, state: "ready", detail: "3.9.6" }] }) });
    expect(byId(old).python).toMatchObject({ tone: "warn", pill: "Recommended fix", detail: "3.9.6" });
    expect(requirementRows(old).blocked).toBe(false);
    expect(byId(shell()).python).toMatchObject({ tone: "ok", pill: "Ready", action: null });
  });
  it("tells a signed-out GitHub CLI from a missing one", () => {
    expect(byId(shell()).gh).toMatchObject({ tone: "miss", pill: "Optional", detail: "Not installed" });
    const out = shell({ launch: launch({ requirements: [{ id: "gh", required: false, state: "signed-out", detail: null }] }) });
    expect(byId(out).gh).toMatchObject({ tone: "warn", action: { label: "Copy sign-in command", copy: "gh auth login" } });
  });
  it("names the Linux venv package", () => {
    const linux = shell({ os: "linux", launch: launch({ requirements: [{ id: "python-venv", required: true, state: "missing", detail: null }] }) });
    expect(byId(linux)["python-venv"].action).toEqual({ label: "Copy command", copy: "sudo apt install python3-venv" });
  });
});

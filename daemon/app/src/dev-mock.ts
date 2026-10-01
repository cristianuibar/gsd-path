// Development only: lets `npm run dev` show every screen in a plain browser,
// without the Rust shell. Pick a state with ?state=<name>. Never part of a build.
import { mockIPC } from "@tauri-apps/api/mocks";
import type { Launch, Shell } from "./shell";

const launch = (over: Partial<Launch> = {}): Launch => ({
  action: "start", port: 8765, version: "0.2.0", autostart_ok: true, problems: [], legacy: [], replaced: null,
  requirements: [
    { id: "python", required: true, state: "ready", detail: "3.9.6" },
    { id: "git", required: true, state: "ready", detail: "2.39.5 (Apple Git-154)" },
    { id: "gh", required: false, state: "missing", detail: null },
  ],
  ...over,
});
const shell = (over: Partial<Shell> = {}): Shell => ({
  phase: "ready", os: "macos", port: 8765, python_missing: false, launch: launch(), error: null, autostart: true, ...over,
});
const blocked = (kind: string, message: string, fix: string, detail?: object): Shell =>
  shell({ phase: "blocked", launch: launch({ action: "setup", problems: [{ kind, message, fix, blocking: true, detail }] }) });

const STATES: Record<string, Shell> = {
  ready: shell(),
  "no-python": shell({ phase: "blocked", python_missing: true, launch: null }),
  "no-python-windows": shell({ os: "windows", phase: "blocked", python_missing: true, launch: null }),
  "no-git": blocked("git", "Git is not installed.", "Run `xcode-select --install`, or install Git from https://git-scm.com/download/mac."),
  port: blocked("port", "Another program is using port 8765.", "Quit it, then choose Retry.", { pid: 4412, command: "node" }),
  install: blocked("install", "The daemon could not be installed into ~/.gsd-path/venv.", "Check your network connection, then choose Retry."),
  migrated: shell({ launch: launch({ replaced: "0.0.9", legacy: [
    { name: "launch-agent", removed: true, fix: "" }, { name: "login-item", removed: true, fix: "" },
    { name: "tray-app", removed: true, fix: "" }] }) }),
  "migrate-failed": shell({ autostart: false, launch: launch({ autostart_ok: false, replaced: "0.0.9", legacy: [
    { name: "launch-agent", removed: false, fix: "launchctl bootout gui/501/org.gsd-path.daemon" },
    { name: "login-item", removed: true, fix: "" }, { name: "tray-app", removed: true, fix: "" }] }) }),
};

const query = new URLSearchParams(location.search);
const state = STATES[query.get("state") ?? "ready"] ?? STATES.ready;
if (query.has("done")) localStorage.setItem("gsd-path.setup-done", "1");
else localStorage.removeItem("gsd-path.setup-done");

mockIPC((command, args) => {
  if (command === "api") {
    if (query.has("offline")) throw new Error("connection refused");
    return { projects: [{}, {}, {}, {}] };
  }
  if (command === "open_url") return void window.open((args as { url: string }).url);
  return state; // shell_state, boot_command, use_port
}, { shouldMockEvents: true });

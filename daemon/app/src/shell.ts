// The contract with the Rust shell (src-tauri/src/main.rs). `launch` is the JSON
// object that `python -m gsd_daemon launch` prints; Rust passes it through.
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export type Problem = {
  kind: string;
  message: string;
  fix: string;
  blocking: boolean;
  /** On a `port` problem: who holds the port (`name` is the program's name). `daemon` is an older GSD Path daemon that could not be stopped. */
  detail?: { owner?: "daemon" | "other"; pid?: number | null; name?: string | null; command?: string | null };
};
export type Requirement = {
  id: string;
  required: boolean;
  state: "ready" | "missing" | "signed-out";
  detail: string | null;
};
export type LegacyEntry = { name: string; removed: boolean; fix: string };
export type Launch = {
  action: "setup" | "start" | "reuse";
  port: number;
  version: string | null;
  autostart_ok: boolean;
  problems: Problem[];
  requirements: Requirement[];
  legacy: LegacyEntry[];
  replaced: string | null;
};
export type Shell = {
  phase: "checking" | "blocked" | "ready";
  os: "macos" | "windows" | "linux";
  port: number;
  python_missing: boolean;
  launch: Launch | null;
  /** The launch check itself failed, or the daemon did not start. */
  error: string | null;
  /** Launch at login is on. */
  autostart: boolean;
  /** This app started the monitor, so it can stop and restart it. */
  owned: boolean;
};

export const getShell = () => invoke<Shell>("shell_state");
/** Run the launch check again and act on it. */
export const boot = () => invoke<Shell>("boot_command");
export const usePort = (port: number) => invoke<Shell>("use_port", { port });
export const openUrl = (url: string) => invoke<void>("open_url", { url });
/** One request to the daemon. Rust adds the write token; it never reaches this page. */
export const api = <T>(method: "GET" | "POST", path: string, body?: unknown) =>
  invoke<T>("api", { method, path, body: body ?? null });
/** A tray popover button; the ids of the native tray menu. With `root`, "open" shows that project. */
export const trayAction = (action: "open" | "start" | "restart" | "quit", root?: string) =>
  invoke<void>("tray_action", { action, root: root ?? null });
export const onShellChange = (handler: (shell: Shell) => void) =>
  listen<Shell>("shell", (event) => handler(event.payload));

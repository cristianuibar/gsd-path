# Native dashboard app — work plan

Design: [ADR 0005](adr/0005-native-dashboard-app.md).

## Contract

A user downloads one app for macOS, Windows, or Linux. From it they can:

- see which hosts have GSD Path skills, at which version, and install or
  update them;
- see each watched project's runtime version, guard hooks, and multi-repo
  member health, and install, update, or repair them;
- update the plugin and the app itself;
- see project progress and usage as charts.

No `npx` flags are needed for these tasks. The CLI installer stays for scripts.
Background monitoring stays read-only; only explicit user actions write, and
they write through the existing installer and helpers.

## Slices

| Slice | Contract |
|---|---|
| A0 Same-origin writes | Every daemon POST route (`/api/plugin/*`, `/api/config/parents`, `/api/refresh`) refuses a foreign Host, a cross-site Origin, and a non-JSON body, like `/api/path-config`. Tracked as its own task; it lands before any app build is published. |
| A1 Shell and backend | Tauri 2 project in `daemon/app/`. On first run the app checks Python 3.9+ and Git and shows a static setup page with the fix when one is missing. Otherwise it creates or reuses `~/.gsd-path/venv`, installs the bundled daemon package (with its wheels, so first run works offline), starts `gsd_daemon serve`, and loads the dashboard. It stops the daemon on quit, and a daemon that is already running on the port is reused, not duplicated. Tray menu matches the Swift app: project count and attention count, Open dashboard, Open in browser, Start, Stop, Restart, Quit, update notice. Launch at login uses Tauri autostart. |
| A2 Builds | CI builds the app on macOS (arm64 and x64), Windows, and Linux, and attaches `.dmg`, `.msi`, `.deb`, and AppImage files to a GitHub Release tagged `app-v<version>`. macOS builds are ad-hoc signed. No OS code signing yet. |
| A3 Self-update | The Tauri updater reads a static `latest.json` from GitHub Releases. CI signs update artifacts with the owner's updater key, stored as a repository secret. The app checks on launch and from the tray, and asks before installing. |
| A4 Install view | One page: hosts × installed skill version × latest, with Install and Update. Per project: runtime version, guard hooks present, and Update. For a coordinator with `.project/MEMBERS.md`: each member's marker, member hooks, and `origin/main`, with **Install hooks** (`install.py --member-of`) and **Repair** (`members.py repair`). Each failed check shows the exact fix. All data comes from installer and helper output; the daemon adds no rule of its own. |
| A5 Stats | Charts from data the daemon already records: tokens and cost over time, time per phase, task throughput per wave, verify pass and fail history. Missing data shows as missing, never as zero. |
| A6 Retire Swift | Remove `daemon/macos` and the autostart code in `gsd_daemon install` that the app replaces. README, `daemon/README.md`, and the npm installer's final message point to the app download. |

A0 and A1 come first. A2 needs A1. A3 needs A2. A4 and A5 need only A1 and
can run in parallel. A6 comes last.

## Proof

- A0: daemon tests send a cross-site Origin, a foreign Host, and a text/plain
  body to each write route and see a refusal with no installer call; a
  same-origin JSON request still works.
- A1: on each OS, a first run with no Python shows the setup page and starts
  no daemon; a first run with Python starts the daemon and shows the
  dashboard; quitting stops the daemon; a second launch reuses a running
  daemon.
- A2: the release workflow produces all listed files, and each installs and
  launches on a clean machine or VM for that OS.
- A3: an app at version N updates to N+1 from a test release; an update with
  a bad signature is refused.
- A4: a two-repo fixture with one member missing hooks shows that member as
  unguarded; **Install hooks** fixes it; a moved coordinator shows a stale
  marker and **Repair** fixes it.
- A5: a sample project renders every chart; a project without a usage ledger
  shows the missing state.
- A6: after removal, no doc or script refers to `daemon/macos` or the removed
  autostart paths.

## Decisions

- Shell: Tauri 2 (owner ruling 2026-09-29).
- The Swift app is replaced once the new app matches it (owner ruling
  2026-09-29).
- Unsigned builds first; OS code signing before a public release (owner
  ruling 2026-09-29).
- The daemon runs from a venv, not a frozen binary; see the ADR.
- The app has its own version and `app-v*` release tags, separate from the
  npm package (owner ruling 2026-09-29). The npm release workflow triggers
  on `v*` tags only, so `app-v*` tags never publish to npm.
- Linux ships `.deb` and AppImage only (owner ruling 2026-09-29).

## Out of scope

- Joining a member from the app (the router owns joining).
- Advancing any pipeline phase from the app.
- A mobile or web-hosted dashboard.

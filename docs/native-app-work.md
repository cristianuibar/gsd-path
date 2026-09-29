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
| A0 Same-origin writes | Every daemon POST route (`/api/plugin/*`, `/api/config/parents`, `/api/refresh`) refuses a foreign Host, a cross-site Origin, and a non-JSON body, like `/api/path-config`. Update the dashboard's bodyless `/api/refresh` POST to send JSON. Tracked as its own task; it lands before any app build is published. |
| A1 Shell and backend | Tauri 2 project in `daemon/app/`. On first run the app checks Python 3.9+ and Git and shows a static setup page with the fix when one is missing. Otherwise it creates or reuses `~/.gsd-path/venv`, installs the bundled daemon package, starts `gsd_daemon serve` when needed, and loads the dashboard. Before replacing any daemon, use existing `gsd_daemon uninstall` cleanup to retire the old LaunchAgent, Startup shortcut, systemd unit, and Swift login item. Check each registration is gone, regardless of the uninstall exit status; if one remains, show the manual fix and do not enable app autostart. Add the daemon version to `/status` and bump the package version whenever daemon code changes in an app build. Compare a running daemon's version with the bundled one: stop and replace it if older or missing, otherwise reuse it. A replaced daemon is app-owned; a reused daemon keeps running on quit. On quit, the app stops only a process it launched. Tray menu matches the Swift app: project count and attention count, Open dashboard, Open in browser, Start, Stop, Restart, Quit, update notice. Launch at login uses Tauri autostart. |
| A2 Builds | CI builds the app on macOS (arm64 and x64), Windows, and Linux, and attaches `.dmg`, `.msi`, `.deb`, and AppImage files to a GitHub pre-release tagged `app-v<version>` for testers. macOS builds are ad-hoc signed. OS code signing is required before the first non-prerelease app release. |
| A3 Self-update | The Tauri updater reads `latest.json` from the fixed `app-latest` GitHub pre-release at `https://github.com/open-gsd/gsd-path/releases/download/app-latest/latest.json`. CI replaces that asset after each `app-v*` release and signs update artifacts with the owner's updater key, stored as a repository secret. The app checks on launch and from the tray, and asks before installing. |
| A4 Install view | One page: hosts × installed skill version × latest, with Install and Update. Per project: runtime version, guard hooks present, and Update. For a coordinator with `.project/MEMBERS.md`: each member's marker, member hooks, and `origin/main`, with **Install hooks** (`install.py --member-of`) and **Repair** (`members.py repair`). Each failed check shows the exact fix. All data comes from installer and helper output; the daemon adds no rule of its own. |
| A5 Stats | Charts from data the daemon already records: tokens and cost over time, time per phase, task throughput per wave, verify pass and fail history. Missing data shows as missing, never as zero. |
| A6 Retire Swift | Remove `daemon/macos` and the autostart code in `gsd_daemon install` that the app replaces. Keep the legacy uninstall cleanup used by A1. README, `daemon/README.md`, and the npm installer's final message point to the app download. |

A0 and A1 come first. A1 retires old autostart before A2 publishes an app
build. A3 needs A2. A4 and A5 need only A1 and can run in parallel. A6 comes
last.

## Proof

- A0: daemon tests send a cross-site Origin, a foreign Host, and a text/plain
  body to each write route and see a refusal with no installer call; a
  same-origin JSON request still works. The dashboard sends a JSON body and
  content type to `/api/refresh`, and refresh still succeeds.
- A1: on each OS, a first run with no Python shows the setup page and starts
  no daemon; a first run with Python starts the daemon and shows the
  dashboard; quitting stops the process the app started. Upgrade an old daemon
  install on each OS, including the Swift app on macOS: old startup entries
  are gone before daemon replacement, and only the new app starts at login.
  Simulate failed cleanup and see the manual fix with no app autostart. Build
  two apps with distinct daemon versions: the newer app replaces the older
  daemon. A pre-A0 daemon without a version is also replaced; a current daemon
  is reused and keeps running on quit.
- A2: the release workflow produces all listed files, and each installs and
  launches on a clean machine or VM for that OS. Unsigned builds are available
  only through pre-releases; the first non-prerelease build has OS signing.
- A3: after a newer npm `v*` release exists, an app at N updates to N+1
  through `app-latest`; an update with a bad signature is refused.
- A4: a two-repo fixture with one member missing hooks shows that member as
  unguarded; **Install hooks** fixes it; a moved coordinator shows a stale
  marker and **Repair** fixes it.
- A5: a sample project renders every chart; a project without a usage ledger
  shows the missing state.
- A6: after retirement, install and launch the new app; run
  `gsd_daemon install` and confirm it no longer registers autostart. Separately
  review active docs and install messages for correct app download and startup
  instructions.

## Decisions

- Shell: Tauri 2 (owner ruling 2026-09-29).
- The Swift app is replaced once the new app matches it (owner ruling
  2026-09-29).
- Unsigned `app-v*` builds are GitHub pre-releases for testers only; OS code
  signing is required before the first non-prerelease app release (owner
  ruling 2026-09-29).
- Remove autostart from `gsd_daemon install` in A6. Scripted installs lose
  startup behavior; the app becomes the only autostart path (owner ruling
  2026-09-29).
- Check `/status` before reuse: replace a daemon older than the bundled version
  or missing a version; reuse a daemon at least as new and leave it running on
  quit (owner ruling 2026-09-29).
- Retire old autostart on first app launch before daemon replacement, and bump
  the bundled daemon package version when its code changes (owner ruling
  2026-09-29).
- App updates use the fixed `app-latest` GitHub pre-release asset
  `https://github.com/open-gsd/gsd-path/releases/download/app-latest/latest.json`;
  CI replaces it on each `app-v*` release (owner ruling 2026-09-29).
- The daemon runs from a venv, not a frozen binary; see the ADR.
- The app has its own version and `app-v*` release tags, separate from the
  npm package (owner ruling 2026-09-29). The npm release workflow triggers
  on `v*` tags only, so `app-v*` tags never publish to npm.
- Linux ships `.deb` and AppImage only (owner ruling 2026-09-29).

## Open questions

- A1: How will the app compare the running daemon version before changing the
  shared venv and ensure it never downgrades a newer installed package? The
  installer uses `pip install --upgrade`, which can replace it.
- A1: How will the app identify a process on the port as a GSD Path daemon
  before stopping it, and what happens when another service holds the port?

## Out of scope

- Joining a member from the app (the router owns joining).
- Advancing any pipeline phase from the app.
- A mobile or web-hosted dashboard.

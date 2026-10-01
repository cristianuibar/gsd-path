# OpenGSD Path app

One Tauri 2 app for macOS, Windows, and Linux. Design: [ADR 0005](../../docs/adr/0005-native-dashboard-app.md).
Slices: [native-app-work.md](../../docs/native-app-work.md). Screens: [design handoff](../../docs/design/native-app/README.md).

- `src-tauri/` — the Rust shell. It finds Python, runs `python -m gsd_daemon launch`, acts on the JSON
  result, starts the daemon with `--require-token`, and stops only a daemon it started. The `api` command
  carries frontend requests to the daemon and adds the write token.
- `src/` — the React + Vite frontend. `shell.ts` is the contract with the shell; `screen.ts` picks the screen.
  When the monitor runs, `route.ts` picks the page from `location.hash`: `#/projects` (the board),
  `#/project/<folder>` (one project), `#/project/<folder>/files/<path>` (History & files), and `#/tray`
  (the tray popover, a second window). `status.ts`, `board.ts`, `project.ts`, and `tray.ts` turn the
  daemon's `/status` payload into what the pages show.

## Develop

```bash
npm install
npm test          # frontend logic
npm run dev       # frontend in a browser, with a mock shell: http://localhost:1420/?state=ready
npm run build     # type check and bundle
(cd src-tauri && cargo test)
```

`src/dev-mock.ts` lists the mock states (`?state=no-python`, `port`, `port-daemon`, `migrated`, `migrate-failed`, …).
Add `&done` to skip setup and `&offline` to stop the mock monitor. The mock serves the sample projects in
`src/fixtures.ts`: `http://localhost:1420/?state=ready&done#/projects`, and `#/tray` for the popover.

## Run the real app safely

`npm run tauri dev` runs the launch check, which removes old startup entries and replaces an older
daemon. **Do not run it against your own login.** A temporary `HOME` is not enough on macOS:
`launchctl` reads the real login session. Use all of these:

```bash
export HOME="$(mktemp -d)"                                   # the venv, token, and logs go here
mkdir -p "$HOME/.gsd-path/app"
echo guard > "$HOME/.gsd-path/app/legacy-autostart-retired"  # skips the old-startup cleanup
export GSD_PATH_APP_PORT=8801                                # a free port, not 8765
npm run tauri dev
```

Only one copy of the app runs per identifier; a second start only focuses the first.

## Release a tester build

Set the same version in `src-tauri/tauri.conf.json`, `src-tauri/Cargo.toml`, and `package.json`, merge, then
push the tag `app-v<version>`. The `App release` workflow builds the `.dmg` (arm64 and x64), `.msi`, `.deb`,
and AppImage files and attaches them to a GitHub pre-release. The builds are unsigned.

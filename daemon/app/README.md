# OpenGSD Path app

One Tauri 2 app for macOS, Windows, and Linux. Design: [ADR 0005](../../docs/adr/0005-native-dashboard-app.md).
Slices: [native-app-work.md](../../docs/native-app-work.md). Screens: [design handoff](../../docs/design/native-app/README.md).

- `src-tauri/` — the Rust shell. It finds Python, runs `python -m gsd_daemon launch`, acts on the JSON
  result, starts the daemon with `--require-token`, and stops only a daemon it started. The `api` command
  carries frontend requests to the daemon and adds the write token.
- `src/` — the React + Vite frontend. `shell.ts` is the contract with the shell; `screen.ts` picks the screen.
  When the monitor runs, `route.ts` picks the page from `location.hash`; the comment at its top lists
  every route (the board, one project, its files and environment, Skills, Stats, Settings, and the tray
  popover, a second window). Each page keeps its logic in a tested `.ts` module next to `screens/`
  (`board.ts`, `project.ts`, `skills.ts`, `stats.ts`, `env.ts`, `settings*.ts`, `tray.ts`, …).

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
`src/mocks/` holds the mock daemon routes of the Skills, Stats, Settings, and Environment pages
(`#/skills`, `#/stats`, `#/settings`, `#/project/<folder>/env`).

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
and AppImage files and attaches them to a GitHub pre-release. When the Apple secrets are set, the macOS builds are
signed with the Developer ID certificate and notarized ([guide](../../docs/app-macos-signing-guide.md)); without
them they keep an ad-hoc signature. Windows and Linux builds are unsigned.

## Updates

The app updates itself with the Tauri updater. It reads
`https://github.com/open-gsd/gsd-path/releases/download/app-latest/latest.json`, checks at start and from
Settings → Updates, and asks before it installs. Each update file is signed with the owner's updater key
(repository secrets `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`); the public key is in
`src-tauri/tauri.conf.json`. An update whose signature does not match is refused and nothing changes.

The `App release` workflow signs one update file per platform (`updater-<platform>.<ext>` and its `.sig`; Linux
has two, the AppImage and the `.deb`, because an app installed from the `.deb` can install only a `.deb`) and,
only when every platform built, writes `latest.json` with `scripts/latest-json.mjs` and replaces it on the
`app-latest` pre-release. A local build makes no update files, because it has no signing key. If the private
key or its password is lost, installed apps can accept no more updates.

# Handoff: OpenGSD Path native app (Tauri dashboard + tray)

## Overview
Design for the native desktop app described in `docs/adr/0005-native-dashboard-app.md` and `docs/native-app-work.md` (one Tauri app on macOS, Windows and Linux that bundles the daemon and is the dashboard). It covers first-run setup, the project board, project pages (including coordinator/member repositories), skills management, stats, settings, a per-project environment editor, first-launch migration from the old tray apps, the tray popover, and error/update states. Every option in `option-map.html` marked "In app" or "Planned" is placed in one of these screens.

## About the Design Files
`prototype.dc.html` is a **design reference built in HTML**: a clickable prototype with sample data. It is not production code. Recreate it in the real app as the React + Vite frontend in `daemon/app/` (owner ruling 2026-10-01, see ADR 0005). Do not ship the HTML.

The prototype has a dark strip at the top that jumps between screens. That strip is a review tool, not part of the product. The `theme` (light/dark) and `os` (macOS/Windows) props switch the theme and the window chrome.

## Scope
The slices and their order are in [native-app-work.md](../../native-app-work.md). Two parts of this design are **Later** and are not built until the owner rules them in:

- **A4b Add project**: wizard steps "Add project" and "Start /path", "Open in agent", and the board sections "Git repositories without Path" and "Workspace detected". Until then the wizard has 4 steps and ends with "Open dashboard".
- **A7 Remove everything**: the Settings → App action.

## Fidelity
**High fidelity** for layout, color, type and copy. The visual language is copied from the current dashboard CSS (graphite surfaces, blue accent, system font, flat 8px cards, hairline dividers). Keep it as is. Values below are exact.

## Screens
All pages sit under a 64px header (logo, nav: Projects, Skills, Stats, Settings, Refresh, "Updated hh:mm:ss"), except Setup, First launch, Tray and Errors, which have none. The Skills nav item carries a count badge while skills updates are pending.

1. **Setup (6 steps)** — left rail 260px (`--chrome`), steps: Requirements, Agents, Skills, Watch folders, Add project, Start /path. Footer: Back, "Skip for now" (steps 4 and 5 only), Continue ("Open dashboard" on the last step). Nothing is written until the user clicks an action. Rerunnable from Settings → App → "Run setup again".
   - *Requirements*: Python 3.9+ and Git are required (Continue disabled while missing). Optional: GitHub CLI (all OS), long paths (Windows). Each row: status dot, name, pill (Ready / Recommended fix / Required / Optional), detected version or path, reason, one action (macOS: "Install newer Python", "Install GitHub CLI"; Windows: "Install with winget", "Copy admin command" for long paths). Windows note: WebView2 is installed by the installer. Linux (not drawn): `python3-venv` hint, `.deb` vs AppImage differences.
   - *Agents*: 11 agents in an auto-fill grid (min 230px). Checkbox cards; detected ones say "Found on this computer", others "Not found" with an "Install page" link (URL per agent still to be supplied). Undetected agents can still be selected.
   - *Skills*: release picker (Latest, older), per-folder target list, "Preview first" (dry run output) then "Install in N agents", progress, success line with health check. Codex and Zed share `~/.agents/skills` and appear as one row.
   - *Watch folders*: list with "Stop watching", "Add folder…", counts of projects using Path and Git repos without Path. Excluded folders and depth live in Settings → Monitoring.
   - *Add project*: checkbox list of repositories, toggles for Guard hooks and "Install skills inside the project", AGENTS.md note, "Set up N projects", result line with health check. Shows a "workspace holds N repositories" note when sibling repos look like one product.
   - *Start /path*: project and agent pickers, "Open in agent", `/path` with Copy. Approvals and rulings stay in the agent.
2. **First launch (migration)** — for users with the old LaunchAgent, Startup shortcut or Swift tray app. Three sections: old startup entries (each Removed / Still present with the exact manual removal command), background monitor replaced, launch at login (On / Waiting). On failure: "Check again" and "Continue without launch at login". macOS entries: LaunchAgent `org.gsd-path.daemon`, Swift login item, `~/Applications/GSDPathTray.app`. Windows: Startup `.lnk`.
3. **Projects (board)** — update banner (lists only pending updates, "Review updates" → Settings → Updates), title, filters (All / In progress / Blocked / Shipped with counts), search, "Add project". Table columns: Project, Current milestone (phase cells + phase name), Status, Tasks, Usage, Setup. Coordinators show a chevron and a "3 repos" pill and expand to indented member rows on `--chrome`. Setup pills: Up to date, Runtime update, No guards, No member hooks, Stale marker. Footer: "N of M projects · K member repositories". Below the table: "Git repositories without Path" (Set up) and "Workspace detected" (folder with related repos but no coordinator; linking is done in the agent via `/path` then `members add`, shown as text and Copy).
4. **Project** — breadcrumb (Projects / coordinator for members) and, for members, a "Member of X" banner with "Open coordinator". Title with health dot, project folder path, facts strip (State, Health, Milestone, Branch, Head, Integration, Cost, Turns). Left: 8-step phase bar, current milestone card (blocked state in danger tint), milestones list. Right: "Setup in this project" rows (Runtime with Update to 1.4.0; Guard hooks with Refresh / Add guards / Install member hooks; Skills; Health check with Run again; Environment with Edit…; Open in agent), "Member repositories" table for coordinators (marker, hooks, origin pills; Install hooks / Repair), Usage tiles, "See charts", "Remove Path from this project" (shows a plan, then Remove / Cancel).
5. **Environment** — per project. Tabs `.env`, `.env.local`, `.env.development`, `.env.production`. Git pill (Tracked by Git warns; Ignored by Git for `.env.local`). Table Name / Value / Show·Hide / Remove; secrets masked with 12 bullets. "Add variable". Jev screening toggle writes `GSD_PATH_JEV=1` to the file chosen in "Write the flag to"; the key `TYPESAFE_API_KEY` belongs in `.env.local`. Save shows a diff first and rewrites only that file.
6. **Skills** — table Agent / Skills folder / Version / Status / actions (Update to x, Preview, Install, Uninstall). Release picker and "Check for updates". Preview prints a dry-run block. Footer lists agents not detected.
7. **Stats** — scope switch (All projects / project). Cards: Tokens per day, Cost per day (bar charts with peak label), Time per phase, Tasks per wave, Verify history (pass/fail squares with legend). Missing data uses a hatched blank with a reason, never zero. Models without a price are counted in tokens and left out of cost, with an "Add a price" link.
8. **Settings** — left tabs: Updates, Path settings, Monitoring, Usage and prices, App.
   - *Updates*: one list for the app, skills per agent, runtime per project; each row has its own action; "Update all". The app row opens the update dialog.
   - *Path settings*: User defaults vs project scope, shipping mode, review panel, models and effort per role, Save / Discard. Project scope is locked once build starts.
   - *Monitoring*: watched folders, excluded folders, scan depth, refresh interval, notifications, activity history.
   - *Usage and prices*: price per million tokens (input, cached, output), missing prices highlighted; session folders.
   - *App*: Launch at login, Appearance (System / Light / Dark), Run setup again, Diagnostics (Open logs, Copy report), "Remove everything" (shows a plan first; keeps projects and `.project/`).
9. **Tray popover** (380px) — status line (dot + "4 projects · 3 members" or "Stopped"), "Needs attention" cards first, then Projects (members indented under the coordinator; click a row to reveal Open in Codex / Details / Copy /path), update strip ("App 0.1.1 is ready · 2 more updates", Review), footer: Open dashboard, In browser, Restart, Quit. Stopped state dims the list and shows "Start".
10. **Errors / states** — Python missing (command + Check again), monitor stopped (offline banner, last update time, Start monitor), port in use (names the process, Use another port), skills install failed (what failed, what was not changed, exact fix, Try again, Installer output), update ready dialog (Restart and update / Later), update refused (signature mismatch, nothing changed).

## Interactions & Behavior
- Setup Continue is blocked while a required item is missing; fix buttons flip the row to Ready.
- Install and Add project show idle → (optional preview) → progress → done. Progress is simulated in the prototype; wire to the real installer.
- Any action that writes shows a plan or dry run first (skills preview, remove, env diff).
- Router-only actions (join a member, approvals, rulings) are never buttons; show the `/path` command with Copy.
- Row hover on tables and tray rows uses `--hover`. Toggles are 36×22, knob 18px.
- Coordinator rows expand and collapse; state is local.
- Cost and usage values only count matched host sessions; blanks stay blank.

## State Management
Per-screen UI state: setup step, host and repo selections, install phase, board filter, expanded coordinator, current project id, environment file, revealed secrets, Jev flag and target file, stats scope, settings tab and config scope, tray state and open row, update-dialog visibility, first-launch failure flag.
Data needed from the daemon: projects (with `parent`/member relation from `.project/MEMBERS.md`), phases, milestones, tasks, usage, setup status (runtime version, hooks, marker, origin), update availability, host detection and skills versions per folder, env file contents (secrets masked server-side where possible), monitor status and port.
Env contract (confirmed, owner ruling 2026-10-01): Path edits env files; the Path pipeline itself reads only `GSD_PATH_*` keys. The editor can show and reveal any key to the user, through a daemon route that is a POST and needs the app token. Secrets are written and masked, never logged or put in reports.

## Design Tokens
Light / dark:
- bg `#fbfcfd` / `#101214`; chrome `#eef0f3` / `#171a1d`; card `#ffffff` / `#141619`; hover `#f0f4f7` / `#1d1f23`; segmented track `#e0e3e6` / `#2b2e32`
- text `#1a1d22` / `#e9ebee`; dim `#595e64` / `#a7abb1`; faint `#71757a` / `#82878c`; done `#51565c` / `#a0a5ab`; line `#e1e3e6` / `#292c2f`
- accent text `#0062cc` / `#4da3ff`; accent fill `#007aff` / `#0a84ff`; accent soft `#e5f1ff` / `#0f2640`
- danger `#c9302d` / `#ef675c`, soft `#ffe7e4` / `#47211d`; warn `#8d5e00` / `#e4ac59`, soft `#fdf1dc` / `#3a2a12`; ok dot `#34c759` / `#30d158`, ok ink `#1f7a3a` / `#5ad17e`, soft `#e3f5e8` / `#13301c`
- Shadow `0 1px 2px rgb(26 29 34/.08), 0 0 0 1px rgb(26 29 34/.06)`
- Fonts: `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif`; mono `ui-monospace, "SF Mono", "JetBrains Mono", Menlo, Consolas, monospace`
- Type: page title 28px/1.25, weight 650, letter-spacing -0.025em; section title 12.5px weight 650; body 14px/1.5; controls 12.5px; table headers 11px uppercase weight 600; paths and versions in mono 11–12.5px
- Radius: cards 8px, buttons 7px, inputs 6px, pills 10px, popover 12px; tap height 36–40px (32px in dense rows, 28px in the tray)
- Spacing: page padding 32–36px; card padding 14–18px; grid gaps 10–18px; board row padding 18px
- Phase cell: 9×9px, radius 2px, gap 2px; 8 cells (inspect, define, research, decide, roadmap, plan, build, ship)

## Assets
- Logo mark: the three-chevron SVG from `serve.py` (`ICON.mark`), copied inline.
- Search icon: inline SVG, 16px.
- No photos or other images. Window chrome (traffic lights, Windows title bar) is drawn for context only; the real app uses native chrome.
- `reference/` holds screenshots of the current dashboard and macOS menu bar.

## Open items
- URL for each agent's "Install page" link.
- App and runtime version numbers (0.1.0 / 0.1.1 are placeholders; skills 1.4.0 comes from `package.json`).
- Decide items left out: creating a GitHub repo from the app, Jev beyond the env flag.
- Linux setup text and distro differences are not drawn.

## Files
- `prototype.dc.html` — the prototype (all screens, sample data, state logic). It loads `./support.js`, which is not in the handoff, so it does not run standalone; read it as source.
- `option-map.html` — source map of options and where each lives.
- `screenshots/` — one capture per screen of the prototype in light theme, macOS chrome: `01-setup`, `02-first-launch`, `03-projects`, `04-project`, `05-environment`, `06-skills`, `07-stats`, `08-settings`, `09-tray`, `10-errors`. Setup shows step 1 only; open the prototype to see the other steps.
- `reference/dashboard-board.png`, `reference/dashboard-project.png`, `reference/macos-menu-bar.png` — current UI.

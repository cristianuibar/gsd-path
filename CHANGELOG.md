# Changelog

All notable changes to [@opengsd/gsd-path](https://www.npmjs.com/package/@opengsd/gsd-path)
are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

This file covers the npm package: the skills, the installer, the pipeline
scripts and project runtime, the guard hooks, and their documentation. Until
1.4.0 it also lists changes to the monitor daemon and its dashboard, which are
in this repository but not in the npm package. From October 2026 the desktop
app and the daemon have their own file,
[daemon/app/CHANGELOG.md](daemon/app/CHANGELOG.md). Release bookkeeping and
test-only changes are not listed; the Git history has them.

## [1.4.0] - 2026-09-30

### Added
- **Multi-repo milestones.** One coordinator project can plan, build, review,
  and ship tasks in other repositories (members). A task names its repository
  with `repo:`. Each member gets a marker, guard hooks
  (`--member-of`), a Path-owned checkout for its tasks, and a bound branch at
  build start. Landings in two repositories are journaled so an interrupted
  one can be finished. Members integrate by direct merge or pull request, and
  a member landing can be undone.
- **Native Windows support.** The installer, hooks, state locking, dispatch,
  Verify commands, and the project runtime run on Windows with Git for
  Windows (Git Bash). A Windows job in CI now blocks a merge.
- **Managed `AGENTS.md` block.** The installer adds a marked Path block to an
  existing `AGENTS.md` and keeps the owner's text, on update and on uninstall.
  The block is smaller; phase rules moved into the skills.
- **Pre-approved gates.** `--pre-approve intent,plan` grants the intent and
  plan approvals for one milestone, for unattended quick-lane runs (#150).
  Ship approval stays manual.
- **Native retry.** A failed task that was dispatched natively can be retried
  and finished, also for a member task.

### Changed
- The verify ledger records the repository of each row, and a build stops when
  a member repository changed outside Path.
- The monitor daemon refuses POST requests from other websites and requests
  that are not JSON.
- The dashboard and the tray show the project folder beside the worktree and
  wrap long paths.
- The list of project runtime files has one source for the Python and Node
  installers.

### Fixed
- An ignored `.DS_Store` inside `.project` no longer blocks setup, landings, or
  the ship check (#149).
- A landing is refused when ignore rules hide `.project` state (#145).
- `finish` lands parallel tasks that were dispatched natively (#142).
- `retire` recovers a task worktree that was only half retired (#143).
- Empty host `.claude` folders are removed before `.project` gates (#144).
- The docs audit keeps `Repo root` on the primary repository (#148).
- A build checkpoint commits a verify ledger that old ignore rules hid (#158).
- The decide phase can run the research handoff check.
- The installer names a working path when `--project` finds an existing
  contract, and warns about legacy Codex skill backups.
- The update notice says that local edits to skills are not carried forward
  (#151).
- Nested projects and bare-backed worktrees keep the right identity and paths,
  and dashboard search finds a project by repository name.

### Security
- Guard bypasses through Git Bash paths and directory junctions on Windows are
  closed.
- A member repository accepts a push only with an authorization for that ref,
  and member hooks need the coordinator's managed guard.
- Symlinked member lock, marker, and task copy paths are refused.

## [1.3.1] - 2026-09-22

### Fixed
- The legacy runtime migration keeps older runtime folders that Git does not
  track, and the installer help describes this case.

### Changed
- Clearer guidance for the legacy runtime migration and its backup.

## [1.3.0] - 2026-09-21

### Added
- An upgrade moves a legacy in-repository runtime out of the project and
  leaves a backup to review (`--runtime-migrate`).

### Fixed
- Host recovery keeps review cycles that are already closed.
- Release evidence refuses verification worktrees and branches that were not
  retired.

## [1.2.0] - 2026-09-20

### Added
- **Path settings.** Set the shipping mode, the review panel, and the model and
  effort per role, for the user or for one project, in the dashboard or with
  `path_config.py`.
- **Project history in the dashboard.** Browse project files and archived
  milestones, read a file at any Git commit, and load the full recorded
  evidence.
- **Optional Jev evidence screening.** Reviewers can ask for an advisory check
  of chosen criteria and evidence. It is off by default and never replaces a
  recorded review or Verify.
- **External worktrees and pinned runtimes.** Task, verification, and
  integration worktrees live outside the project checkout. A project pins its
  runtime version by content digest, with upgrade and restore commands.
- **One model policy.** User, project, host, and task choices for sub-agent
  models go through one resolver. A recorded assignment stays pinned.

### Changed
- npm releases are automated: release notes, package verification, and
  provenance.
- The release gate validates only the hosts a change affects and reuses
  unchanged host receipts.

### Fixed
- The dashboard shows project runtime updates and their results.
- After verified integration, ordinary branches can take product work again
  while archived milestones stay protected.
- A pinned runtime is used for routing and guard checks.
- A review cycle recovers after a partial review completion.
- Relative links in the history viewer keep the selected commit.

## [1.1.0] - 2026-09-18

### Added
- Scoped npm package `@opengsd/gsd-path` with trusted publishing.
- Release trust evidence validation and the host matrix.

### Changed
- Release workflow and maintainer documentation for npm publication.

## [1.0.0] - 2026-09-15

### Added
- First public release of the disk-backed GSD Path pipeline.
- Multi-host installer, skills package, and project contracts.

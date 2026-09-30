# Changelog

All notable changes to [@opengsd/gsd-path](https://www.npmjs.com/package/@opengsd/gsd-path)
are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.1.0] - 2026-09-18

### Added
- Scoped npm package `@opengsd/gsd-path` with trusted publishing workflow
- Release trust evidence validation and host matrix documentation

### Changed
- Release workflow and maintainer documentation for npm publication

## [1.0.0] - 2026-09-15

### Added
- Initial public release of the disk-backed GSD Path pipeline
- Multi-host installer, skills package, and project contracts

## [1.2.0] - 2026-09-20

### Added
- add Path settings and project history dashboard
- add optional Jev evidence screening
- store worktrees and pinned runtimes outside project checkouts
- centralize sub-agent model selection policy

### Changed
- Correct stale release guidance and consolidate scope references
- record passing eight-host release gate
- validate corrected OpenCode release evidence
- validate recovered Claude release evidence
- record affected release gate results
- preserve blocked host evaluations without receipt fallback
- record passing Antigravity Kimi and Grok release runs
- record remaining 1.2.0 release gate failures
- record Kimi receipt and complete offline recheck
- preserve 1.2.0 host receipts and release blockers
- record v1.3.0 live release evidence and blockers
- bump version to v1.3.0
- Align release documentation with risk-based host validation
- bump version to v1.2.0
- Automate npm release docs, pack verification, and provenance (#133)
- refresh README changes and dashboard screenshots
- Refresh dashboard navigation and file history documentation
- Clarify Jev receipt fields and consolidate documentation
- Refresh dashboard update and guard documentation
- Correct runtime installation, update, guard, and uninstall documentation
- Correct model policy and dispatch documentation

### Fixed
- reuse unchanged host receipts for releases
- verify prepared releases without advancing failed versions
- scope release evidence to affected hosts
- show project runtime updates and release completed milestone guards

### Other
- Fixed tests/package.test.mjs to invoke git_guard.py with pre-commit in a temporary Git repository instead of unsupported --help. The focused test failed before the fix and during restored-original sabotage. All 6 package tests now pass; resource sync and diff checks pass. Verified locally on Node 26; Node 18/20 CI reruns remain with the outer executor
- Preserve historical commit selection across relative document links
- Validate Jev probability normalization with CLI regression coverage
- Record passing focused checks and isolation violation
- Fix integration guard and runtime installer regression coverage
- Fixed stale runtime paths in tests/test_git_guard.py using the installed runtime resolver. Both CI failures reproduced before the fix; all 38 Git guard tests now pass. Both corrected tests also caught a temporarily disabled native guard, which was restored. git diff --check passed. Only the test file changed; remote CI remains for the outer executor
- Fix pinned runtime routing, guard blocking, and launcher bytes
- Restore same-cycle recovery after partial review completion
- Isolate assignment rejections and align native panel exclusions
- Fix dispatch isolation, legacy pinning, and independent panel selection

## [1.3.0] - 2026-09-21

### Added
- migrate legacy runtimes during upgrades

### Changed
- Clarify receipt reuse and consolidate release policy guidance
- Clarify legacy upgrade guidance and verify syntax
- update release notes for v1.2.0

### Fixed
- validate installer changes without live host reruns
- preserve closed review cycles in host recovery
- clarify owner gates and accept serial task release evidence

### Other
- Clarify reviewer ownership; live verification remains pending
- Reject unretired verification worktrees and branches in release evidence

## [1.3.1] - 2026-09-22

### Changed
- Clarify legacy runtime backup guidance
- Consolidate legacy runtime migration guidance
- prepare 1.3.1 patch candidate
- Clarify legacy runtime migration documentation
- update release notes for v1.3.0

### Fixed
- describe untracked legacy migration in help
- preserve older untracked runtimes during migration

## [1.4.0] - 2026-09-30

### Added
- key verify ledger rows by repo and fail closed on member drift (S3d)
- guard coders in member sidecars with coordinator host hooks (S3c3b2)
- dispatch and land member tasks in build rounds (S3c3b1)
- activate member tasks with a live copy in the member sidecar (S3c3a)
- prove landed member tasks from record and member landing (S3c2b)
- land member tasks with a journaled two-repo landing (S3c2a)
- isolate member tasks in Path-owned member checkouts (S3c1)
- shrink the AGENTS.md block and move phase rules into skills
- install AGENTS.md as a managed gsd-path block
- lock members and create member bound branches at build start (S3b)
- plan member tasks with repo: (S3a)
- pre-approve intent and plan gates for unattended quick lanes (#150)
- hold member writes to the coordinator phase (S2d)
- install member git hooks with --member-of (S2c)
- add member mode to git guard with push authorization (S2b)
- add multi-repo member role marker (S2a)
- add multi-repo member contract (S1)

### Changed
- Reflow Copilot exclusion wording in trust-validation docs
- record 1.4.0 live release evidence
- prepare 1.4.0 minor candidate
- Note invalid-copy rejection evidence in multi-repo S5d
- multi-repo: native retry for a failed member task
- Refresh multi-repo activation docs and host guidance
- multi-repo: native member task dispatch
- evaluate_host: keep the release addendum on the quick scenario only
- multi-repo S5d: two-repo host scenario
- Clarify optional hooks and remove obsolete gate note
- multi-repo S5c: activate member execution and document it
- Correct S5b member documentation
- record app release tags and Linux formats
- daemon: refuse cross-site and non-JSON POSTs
- plan a native dashboard app for every OS
- multi-repo S5b: greenfield members and member detect
- Make ReplaceTests portable to POSIX Python 3.9
- Align two-repo proof documentation with test coverage
- multi-repo S5a: two-repo full-cycle proof
- Point lookahead drift guidance to S4d
- multi-repo S4d: member lookahead drift check
- Clarify active milestone member status documentation
- multi-repo S4c3: member plan check, status, and diagnose
- Document member undo safeguards
- multi-repo S4c2: undo a member landing
- Document member retirement guards and correct proof scope
- multi-repo S4c1: retire member bound branches at bind-next
- Exercise core.autocrlf=true in the attributes test under the dev runner
- Keep .project LF under core.autocrlf=true with a local attributes rule
- Port the member-close changes from main to native Windows
- Patch only the probe module's os in the Windows retry test
- Port the multi-repo member tests to native Windows
- Run the native Windows gate in CI and make it blocking
- Never skip an archive check because resolve() raised on Windows
- Decode test subprocess output as UTF-8
- Use the directory mutex for the discussion lock outside git on Windows
- Make member-isolation and release-receipt tests portable to Windows
- Decode archive and projection test output as UTF-8
- Lock discussions outside git on Windows and report sync paths with slashes
- Type guard-test helper paths the way Git Bash agents do
- Retry installer lock and skill-directory moves on Windows
- Make installer and core-migration tests portable to Windows
- Keep doctor running when git is not on PATH on Windows
- Make the runtime lifecycle tests portable to Windows
- Retry runtime directory renames on Windows and copy the launcher exactly
- Expect native paths in the Zed and Grok host command tests
- Close OpenCode session-store connections so Windows can delete them
- Read dispatch briefs as UTF-8 in the fake children
- Send native Windows relative paths to git with forward slashes
- Make daemon tests platform-correct on Windows
- Write plugin-managed files as UTF-8 bytes
- Keep discovered project roots in their original case on Windows
- Compare lookahead layout as POSIX paths on Windows
- Resolve codex through PATHEXT in the Codex evaluation harness
- Shadow the real codex in the evaluate_codex test on Windows
- Keep tests from ever reaching a real GitHub account
- Send subprocess input to git byte-exact on Windows
- Document native Windows requirements
- Make the Node suite and dev runner portable to Windows
- Make test fixtures portable to Windows
- Update member ship documentation and sync skill copies
- multi-repo S4b2b: post-commit member ship checks
- tests: hold and reap dispatch wrappers started in-process
- Align multi-repo work plan with S4b2a
- Reuse a final-scope wave review whose Surface field carries detail
- tests: keep git auto-maintenance in the foreground
- multi-repo S4b2a: member close and ship body lines
- tests: finish git housekeeping before trust-evidence temp cleanup
- Clarify member PR integration documentation
- multi-repo S4b1b: member pull-request integration
- Document member integration recovery and refresh rules
- multi-repo S4b1a: member direct integration
- Split child commands with POSIX quoting and write runtime output as UTF-8
- Install hooks and wrap Core hooks correctly on Windows
- Close Windows guard bypasses and decode text as UTF-8
- Run dispatch, verify, and loop processes portably on Windows
- Create STATE.md on Windows through pinned handles
- Lock pipeline state on Windows and write product files as LF bytes
- Leave the Windows CI job to the PR where Windows passes
- Isolate USERPROFILE with HOME in tests
- Pick the lock implementation by what imports, and split Windows CI suites
- Write test fixtures as exact UTF-8 LF bytes
- Write package.json as LF bytes in the skill-resource sync
- Add Windows platform helpers, portable dev runners, and a Windows CI job
- Clarify member head binding documentation
- multi-repo S4a2: member reviewed heads in the final review
- Point workflow to member Verify contract
- multi-repo S4a1: member sidecars for project Verify
- Correct S3d ledger and drift guidance
- Clarify member sidecar hook documentation
- Refresh member dispatch documentation and generated comments
- Document member activation safeguards and recovery
- Document member landing proof and archive recovery
- Correct member landing documentation and hook details
- merge: preserve validated dashboard fixes after publication timeout
- Refresh dashboard and tray documentation
- Clarify native retry finish documentation
- Align S3c documentation with member execution timing
- dispatch_driver: finish a native retry after a blocked driver attempt
- Drop the Node copy of the project runtime file list
- Correct managed AGENTS.md guidance and ADR context
- Document ignored .DS_Store setup behavior
- Document S3b build-start lock and recovery
- Sync generated GSD Path scripts
- Clarify Finder junk handling in pipeline docs
- Document pre-approval scope and reconcile gate guidance
- Correct stale multi-repo planning documentation
- Document legacy ledger checkpoint behavior
- Document ignored .project artifact handling
- Clarify local skill edit recovery guidance
- Correct stale S2d work plan guidance
- Clarify research transition gate documentation
- propose ADR 0003 managed AGENTS.md block
- Clarify first-install contract collision guidance
- Clarify half-retire recovery documentation and verify formatting
- Document Claude staging cleanup during shipment
- Document ignored pipeline state recovery
- Correct S2c member hook work plan
- Document native parallel finish recovery
- Clarify member guard documentation and authorization lifetime
- Clarify member marker documentation and verify formatting
- Update S1 plan and remove stale allowlist entry
- Clarify member delete authorization and close recovery proof
- close multi-repo plan open items R23-R24
- Clarify member documentation and correct S5 doc targets
- close multi-repo plan open items R17-R20
- add multi-repo coordinator ADR and work plan
- update release notes for v1.3.1

### Fixed
- Fix three Windows races and identity mismatches found on the rebased stack
- Fix the member-build-start path regex
- Fix the Windows CI-only test failures and a Python 3.9 guard crash
- Fix the last native Windows test failures
- show actual project folders in toolbar rows
- group tray status progress and usage on separate lines
- keep tray folder paths in tooltips
- show project identity and wrap tray panel details
- wrap full project paths on dashboard board
- show main project folder alongside dashboard worktree
- keep runtime module identity independent of test order
- detect legacy marker as a whole line; keep distribution layout in AGENTS.md
- match AGENTS.md markers as whole lines; doctor flags a cut block
- harden AGENTS.md block install and uninstall
- ignored .DS_Store in .project no longer orphans project setup (#149)
- skip ignored .DS_Store inside .project subdirectories (#149)
- keep DOCS-AUDIT Repo root on the primary repo, not the sidecar (#148)
- commit a legacy ignored verify ledger in build checkpoints
- skip ignored untracked .project entries in ship allowlist checks (#149)
- say local skill edits are not carried forward (#151)
- let decide run the research handoff check at decide/active
- name a working path when --project finds an existing contract
- prune empty host .claude dirs before .project gates
- let retire recover a half-retired task worktree
- refuse landings when ignore rules hide .project state
- let finish land natively dispatched parallel tasks

### Other
- Align Copilot exclusion docs with persistent validator exclusion
- Let forced member retire proceed on invalid task copy
- Correct native member diff instructions and track retry gap
- Record Claude and Codex two-repo host proof
- Fix native member routing and isolate host scenario
- Align activation host proof with pre-merge gate
- Correct S5d host proof and release timing
- Synced the canonical Windows checkout-path fix into 11 generated skill copies. Before the change, the resource sync check failed and caused the reported test failures. Afterward, the sync check, four affected Node tests, and 66 focused Python tests passed. Windows CI still needs to rerun
- Fixed the Windows checkout-path comparison and replaced three test-fixture deletions that fail on read-only Git objects. The regression test failed before the fix and passed after; 66 focused tests pass locally. Windows CI still needs to rerun. The ponytail skill was unavailable in this environment
- Record A1 daemon version and port ownership questions
- Move legacy cleanup into A1 and require version bumps
- Gate daemon reuse by bundled version
- Specify app update index and verify migration cleanup
- Plan legacy autostart cleanup during app upgrade
- Resolve native app plan review findings
- Fixed the Windows test fixtures in tests/test_member_create.py: Git now gets a forward-slash temporary path, and the gh test uses a platform-independent fake process. All 22 focused tests pass locally; both fixes failed sensitivity checks when deliberately undone. Windows CI still needs to rerun
- Pin GitHub host and verify remote main
- Verify checkout history and resume partial clones
- Honor configured origins and prevent repository recreation
- Reject invalid checkouts and stale clone reuse
- Fix member creation recovery and validation
- Prove member hook denials and branch retirement
- Fixed two Windows daemon test races in tests/test_daemon_serve.py. The activity test now counts events for its own project. The poll test stages STATE.md outside the watched directory and retries a transient replacement lock. The activity failure was reproduced locally before the fix; all 15 daemon serve tests pass after it, including a simulated file-lock check. PR #230 remains open; CI has not been rerun in this phase
- Reuse linted member base for lookahead approval
- Detect member rename drift and fix done-task test
- Filter done member drift; focused test remains failing
- Scope member status to the active milestone
- Block member undo while landing journals are pending
- Guard member undo against publication and concurrent landings
- Harden member undo journaling, recovery, and locking
- Guard member retirement against moved refs and team checkouts
- Sync member status fix to generated skill copies
- Keep member status validation read-only
- Read staged member lock in ship guard
- Repair merged member PR body before tagging
- Validate member PR provenance and repair reused bodies
- Set Git identity in the temporary member test repository to fix the CI merge failures. The focused test reproduced the failure before the change; all 11 member integration tests passed after it, and a sabotage check reproduced the failure. Ponytail review found no smaller fix. CI has not rerun
- Fixed the test fixture in tests/test_member_integration.py by setting the bare remote’s HEAD to main. The CI-style Git setting reproduced the 4 failures and 5 errors before the fix; all 11 focused tests passed after it. Skipping the new line caused the original error again. Ponytail review found no smaller fix. CI has not rerun
- Guard member merges, resume interrupted branches, and refresh validation
- Ignore commented member heads in review headers
- Retire switched member sidecars without changing bound branches
- Retire detached sidecars and retain member Verify output
- Refuse colliding members and clean up rejected Verify
- Fix member Verify sidecars and final review reuse
- Fix member drift detection and document Verify output policy
- Report untracked host config collisions during activation
- Restore and validate member hooks before every launch
- Both CI jobs failed because the temporary member repository had no Git author identity. I set its identity in the test fixture. The member-round suite passed (9 tests) with automatic identity discovery disabled; removing the fixture setting reproduced the failure. `git diff --check` passed. The ponytail skill was unavailable. An earlier diagnostic command created an empty `/tmp/ci-verify-18.log` outside the worktree; I made no other out-of-worktree changes
- Retire recovered members and clarify locked brief bases
- Recover partial and stale member isolates
- Fix member task resume, retirement, and contract drift
- Reject tracked and symlinked member copy paths
- Reject missing member task agents
- Unify member task contract field checks
- Fix member recovery, activation, and retirement safeguards
- Reject changed member task contracts after landing
- Harden member landing proof across archival and status
- Serialize coordinator landings and block pending member journals
- Serialize member landings with per-member locks
- Guard member landing with STATE branch checks
- Fix member landing recovery and contract checks
- Preserve bare-backed worktree identity and paths
- Fix nested project identity and worktree paths
- Fix dashboard search by repository name
- Guard member checkout reuse and retirement ownership
- Fix member isolation placement, lock guidance, and retirement
- Preserve AGENTS.md owner text across updates and uninstall
- Reject symlinked member lock paths
- Remove stale member lock when tasks drop members
- Preflight member build starts before creating refs
- Preserve tracked .DS_Store in archive manifests
- Resolve landed member bases during plan approval
- Honor canonical lane and Config during preauthorization
- Fix staged legacy ledger checkpoint retries
- Validate docs audit rulings before preapproval
- Warn on legacy Codex skill backups
- Clarify block cutoff and release evaluation scope
- Reference PR #161 in rejected option
- Clarify managed block size and migration exceptions
- Skip unreadable listed checkouts when checking foreign members
- Resume blocked decide before the research recheck
- Fix stale member markers, symlinks, and Git inspection failures
- Suppress unsafe move when contract backup exists
- Probe plan and archived ledger ignore rules
- Probe fixed-name project files before landing
- Require managed coordinator guard before installing member hooks
- Harden member hook staging and worktree path checks
- Require origin/main baseline for member joins and pushes
- Reject nonfile member markers until manual removal
- Preserve marker directory errors in validation
- Reject redirected member marker directories
- Write member marker before recording membership
- Skip valid markers during member repair
- Fix member marker recovery and coordinator ownership
- Fix member validation and duplicate repository detection
- Authorize direct member bound branch publication
- Specify per-ref member push authorization for close
- Fix member branch, landing, and ship recovery plan
- Revise multi-repo plan for accepted design reviews
- Align multi-repo plan with member binding decisions

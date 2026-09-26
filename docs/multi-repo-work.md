# Multi-repo milestones — work plan

Design: [ADR 0002](adr/0002-multi-repo-coordinator.md).

## Contract

One milestone can define, plan, build, and ship changes across several Git
repositories, for new repositories (greenfield) and existing ones
(brownfield). A project without `.project/MEMBERS.md` keeps today's behavior and
output.

## Where Path assumes one repository

Function names, not line numbers, because main moves.

| Area | Assumption |
| --- | --- |
| Root | `pipeline_state._repo_root`, `build_state._repo_root`, `pipeline_git._require_worktree_root`, `isolation.worktree_root`: `--repo` must be the Git top level. `_track_root`: `.project` stays inside it. |
| STATE | `pipeline_state.STATE_FIELDS` has one `branch`. The parser rejects unknown fields. `git_guard` and `guard_hook` parse their own copies. |
| Binding | `.project/REPOSITORY.md` holds one remote, default, SHA, checkout, and worktree in a fixed format. It has no member list. |
| Tasks | Frontmatter `files:` is repo-relative with no repo field. `check_task_briefs` checks paths at one `--base`. `build_state._overlap` compares plain paths. |
| Landing | `isolation.land` writes product files and the task file in one commit and refuses a worktree from another repository. `git_guard.product_commit_violations` requires both in the same commit. |
| Ledgers | The verify ledger key is (command, SHA). The dispatch budget ledger is in the one common Git directory. |
| Ship | `integration.integrate`, `integrate_pull_request`, `validate_integrated`: one `origin`, default must be `main`, one tag. `archive_milestone.find_ship_commit`: one ship commit. |
| Guards | `guard_hook.path_kind` returns `external` for writes outside the guard's own repository, and those are always allowed. `git_guard` protects only a tree with `.project/STATE.md`. |
| Install | Git hooks run `$(git rev-parse --show-toplevel)/.gsd-path/git_guard.py`, one project per install. |
| Undo, diagnose | `pipeline_undo.classify_undo`, `pipeline_diagnose._leftover_worktrees`: one branch, one repository. |

## Slices

Each slice ships as its own PR, and the single-repo output must stay the same.

| Slice | Change |
| --- | --- |
| S0 | This ADR and plan. |
| S1 Binding | New `scripts/members.py`: read `.project/MEMBERS.md`; `list`, `add`, `validate`. `add` creates that file if absent, including for an existing Path project, without changing `REPOSITORY.md`. It checks: clean worktree, default branch, GitHub `origin`, not nested, not a submodule, no active milestone of its own, no branch or tag collision. Members change only at a milestone boundary. Build locks the participating members in their `MEMBERS.md` order in STATE `repos:` for this milestone. Add Coordinator and Member to `CONTEXT.md`. |
| S2 Tasks | Task `repo:` field. Brief checks run at each member's base. `_overlap` compares `(repo, path)`. A dispatch round stores a base per member. Plan checks reject a `repo` outside `STATE.repos`. |
| S3 Landing | Member landing: product commit in the member (Task, Base, Files, `Coordinator:`), then a coordinator record commit (`Member-Commit: <repo>@<sha>`), with a resumable journal in the coordinator Git directory. Verify ledger key becomes (command, repo, SHA). One task changes one repo, but milestone Verify may test repos together, such as web tests against sdk. Its sidecars sit side by side per member so `../<member>` paths resolve. |
| S4 Guards | `guard_hook` classifies writes in member worktrees and sidecars as member product and applies phase rules to them. `git_guard` member mode reads a marker in the member Git directory: commits on the member bound branch need a valid Task trailer; `gsd-path/*` pushes need ship authorization. `install.py --member-of <coordinator>` writes only hooks and that marker into the member Git directory, and keeps existing hooks. The marker stores the absolute coordinator path; member hooks run the coordinator's `.gsd-path/git_guard.py` through that path. Joining adds no new tracked Path files and leaves any existing member `.project/` untouched. |
| S5 Ship | Final review covers each member. Then, in the participating members' `MEMBERS.md` order locked in STATE `repos:` at build start, integrate, tag, and record each member. Resume uses that same order. Then the coordinator ship commit (`Member: <name> <integrate-sha> <tag>`) and its integration. `validate-integrated` checks every repository. A failure leaves the milestone partially shipped; resume continues from the journal. In pull-request mode, member k+1's PR opens only after member k merges. |
| S6 Operate | Undo, diagnose, and status run per member. Undo blocks when a member branch is already an ancestor of that member's `origin/main`. |
| S7 Greenfield | The router asks one repository or several. Bootstrap creates the coordinator, then `members add --create` reuses the bootstrap stages per repository (one journal each). STATE is written after every member verifies. |
| S8 Docs | Update README, GUIDE, OPERATE, and SHIP.md. Regenerate all 11 host receipts before any release. |

## Brownfield and greenfield

| Case | Handling |
| --- | --- |
| All repositories new | S7. |
| Existing Path project adds repositories | S1 `members add` creates `.project/MEMBERS.md` at a milestone boundary. Past milestones stay single-repo. |
| Member has its own `.project/` | Allowed only with no active milestone. Joining leaves its `.project/` untouched and adds no new tracked Path files. While bound, its router refuses to start one. Namespaced branches and tags prevent collisions. |
| Member is a GSD Core project | Run `gsd-path-migrate` in that repository first. |
| Member has branch protection | Set that member's integration mode to `pull-request` (decision 2). |

## Proof

Each slice uses temp repositories with bare remotes. Required cases:

- Single-repo regression: no `.project/MEMBERS.md` gives unchanged output.
- A two-repo quick-lane run, end to end.
- A crash between the member commit and the coordinator record, then resume.
- Ship fails on the second member: partially shipped, then resume.
- A member with its own shipped M004 joins with no collision; a member with an active milestone is refused.
- The guard refuses a member write in the wrong phase.

## Decisions

1. A member's remote default must be `main`. `members add` refuses any other
   default with a clear message. Support for other defaults is separate work.
2. Each member may set its own integration mode (`direct` or `pull-request`)
   in `.project/MEMBERS.md`. The milestone mode is the default. This supports members
   with branch protection.
3. The greenfield coordinator can be a product repository or a dedicated
   program repository. The router suggests a program repository when no
   single repository owns the work.

## Out of scope

Submodules, nested repositories, one task across two repositories, remotes
other than GitHub, an atomic close across repositories, and `.project/`
outside Git.

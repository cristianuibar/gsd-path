# Multi-repo milestones — work plan

Design: [ADR 0002](adr/0002-multi-repo-coordinator.md).

## Contract

One milestone can define, plan, build, and ship work across several Git repos,
both new (greenfield) and existing (brownfield). One task changes one repo.
Every CLI takes one `--repo`, the coordinator. Joining a member adds no new
tracked Path files there and leaves an existing member `.project/` untouched.
Without `.project/MEMBERS.md`, behavior and output stay single-repo. Member
execution remains disabled until S5 proves it end to end.

## Where Path assumes one repo

Function names, not line numbers, because main moves.

| Area | Current contract to change |
| --- | --- |
| Root and binding | `pipeline_state._repo_root`, `build_state._repo_root`, `pipeline_git._require_worktree_root`, and `isolation.worktree_root` use one Git root. `REPOSITORY.md` has a fixed single-repo format. |
| Strict STATE parsers | `pipeline_state._state_from_text`, `git_guard.strict_ship_state`, `guard_hook.valid_status_state`, and `install._valid_status_state` reject unknown fields. Do not add STATE `repos:`. |
| Branch pattern | `_common.BOUND_BRANCH_RE` accepts only `gsd-path/M00N`. Its users include `pipeline_state`, `pipeline_git`, `isolation.require_bound`, `dispatch_driver.milestone_slug` and its budget ledger, `integration.is_bound_branch`, `pipeline_undo.classify_undo`, `git_guard.pre_push_violations`, `guard_hook`, `install`, `archive_milestone`, and `bootstrap_repository`. |
| Tasks and dispatch | `check_handoffs` and `check_task_briefs` assume one base. `build_state._overlap` compares paths without a repo. `build_state._validate_ready_metadata` checks a base in the coordinator; `dispatch_driver.finish_task` reads the task file in the product worktree. |
| Landing proof | `isolation._landing_state`, `git_guard.product_commit_violations`, and `build_state.LANDED_VERDICTS` expect product paths and the task file in one commit. |
| Verify ledger | `_common.latest_verify_entry`, `build_state.verify_lookup`, `isolation._verify_ledger_pass`, and `lean_verification.verify_project` use (command, SHA). |
| Sidecar placement | `worktree_paths._workspace` gives each repo a separate hashed root; `../<member>` does not resolve across them. |
| Guards and install | `guard_hook.path_kind` calls member writes `external` and allows them. `git_guard.head_frontmatter` reads the member's own STATE. `install` hooks call a guard under their own worktree. |
| Artifact allowlists | `isolation.PROJECT_ENTRIES` and `lean_verification._require_ship_inputs` reject a new `.project/MEMBERS.md`. |
| Ship body | `git_guard.ship_contract_violations`, `archive_milestone.require_canonical_commit_body`, and `pipeline_undo._archive_metadata_error` require the current exact ship body. |
| Lookahead drift | `state_checkpoint._classify_plan_drift` compares the approved plan against one repo. |
| Close and retirement | `integration.integrate`, `integrate_pull_request`, and `validate_integrated` close one repo. They need a STATE, archive, and ship commit in that repo, require the ship commit as the merge's second parent, and name the tag `milestone/<archive-name>`. `pipeline_git.bind_next_milestone_branch` and `retire_previous_branch` retire one branch. |

## Slices

Each slice ships in its own PR. Every slice changes all readers of any contract
it changes. S1–S4 leave the no-`MEMBERS.md` path and output unchanged and keep
member execution disabled.

| Slice | Work |
| --- | --- |
| S0 | This ADR and plan. |
| S1 Member contract | Add `scripts/members.py` with `add` and `validate`. `add` creates `.project/MEMBERS.md` if absent, including for a brownfield coordinator, without changing `REPOSITORY.md`. Validate clean worktree, GitHub `origin`, remote default `main`, no nested repo or submodule, no active member milestone, and no branch or tag collision. Allow `MEMBERS.md` in `isolation.PROJECT_ENTRIES` and `lean_verification._require_ship_inputs`. Define member identity and Coordinator/Member terms in `CONTEXT.md`. At build start, lock the participating members in their `MEMBERS.md` order in a file under `.project/build/`. Ship and resume read that lock. Membership changes only at a milestone boundary. |
| S2 Binding and guards | Change `_common`, `pipeline_git`, `isolation`, `git_guard`, `guard_hook`, `install`, and `worktree_paths` together. Add a member branch pattern for a verified member role and update every branch-pattern user named above, including `pipeline_state`, `dispatch_driver`, `integration`, `pipeline_undo`, `archive_milestone`, and `bootstrap_repository`. Namespace every member-side Path branch: bound `gsd-path/<coord>-M00N`, task `gsd-path-task/<coord>-<id>`, verify `gsd-path-verify/<coord>-<name>`, and integrate `gsd-path-integrate/<coord>-M00N`. Store a marker under `$(git rev-parse --git-common-dir)/gsd-path/`, shared by linked worktrees, with the absolute coordinator path. Validate it on every call and fail closed with `install.py --member-of <coordinator> --repair` as the named repair command. Member hooks call the coordinator's `.gsd-path/git_guard.py`; install preserves other hooks and records ownership so `--update` composes. In member mode, `git_guard` ignores the member's own STATE. `isolation` writes untracked member sidecar host-hook configs, excluded by `.git/info/exclude`, that use the coordinator guard. `guard_hook.path_kind` treats member worktrees and sidecars as member product. Before each member push, the coordinator records one authorization per (ref, exact SHA or tag object) in durable member Git metadata; member pre-push accepts only a matching ref and object, including the direct-mode bound branch push. A branch deletion needs a separate authorization for the ref and expected remote SHA; pre-push checks the remote SHA it reports. `worktree_paths` pins a shared per-milestone sidecar layout and receipt for the coordinator verify sidecar beside one sidecar per member, so milestone Verify can use `../<member>` (for example, web tests against sdk). |
| S3 Tasks and landing proof | Change `check_handoffs`, `check_task_briefs`, `state_checkpoint`, `build_state`, `dispatch_driver`, `isolation`, `build_recovery`, `_common` ledger, and `lean_verification` together. Add task `repo:` (default coordinator); check briefs and `(repo, path)` overlap against the named repo and its base. Read task metadata from the coordinator; resolve Git base and product worktree in the member. A member task lands only when its coordinator record exists and its product landing exists on the member bound branch. Prove the source commit against its recorded Base, then prove the landing commit against its actual parent on that branch; parallel tasks may share a Base. Journal member product commit then coordinator record for resume. Change the Verify ledger key to (command, repo, SHA) across all four readers, while accepting old single-repo rows. `state_checkpoint._classify_plan_drift` compares approved member paths with each member's recorded base and current tip. Plan checks reject a task for a member already integrated in this milestone. |
| S4 Close and recovery | Change `integration`, `archive_milestone`, `git_guard`, `pipeline_state`, `pipeline_undo`, `pipeline_diagnose`, `status_runtime`, and `pipeline_git` together. Final review binds a reviewed HEAD for each member. The exact ship body keeps the coordinator's `Reviewed-HEAD` and adds `Member-Reviewed-HEAD: <member>@<sha>` and `Member: <name> <integrate-sha> <tag>` for each member; update all three parsers together. Close participating members in the locked order, then the coordinator. Member close creates no STATE, archive, or ship commit for this milestone; it uses the reviewed HEAD and evidence held by the coordinator. `integration.integrate`, `integrate_pull_request`, and `validate_integrated` gain a member path that checks the merge's second parent against that member's `Member-Reviewed-HEAD`, where they check the ship commit today. In `direct` mode, the merge subject is `integrate: <coord> M00N — merge gsd-path/<coord>-M00N into main`. In `pull-request` mode, the GitHub merge of the member bound branch must be a two-parent merge whose second parent is that reviewed HEAD. In both modes, authorize `refs/heads/gsd-path/<coord>-M00N` at the reviewed HEAD before publishing the bound branch. In direct mode, also authorize `refs/heads/main` at the integration merge SHA, whose second parent is the reviewed HEAD. In either mode, authorize `refs/tags/milestone/<coord>-<archive-name>` at its annotated tag object SHA before pushing the tag. A member tag is `milestone/<coord>-<archive-name>`, an annotated tag on the member merge, built by the same member path in place of `milestone/<archive-name>`. `validate-integrated` checks, for each member: the merge is in the first-parent history of its `origin/main`, its second parent is the recorded reviewed HEAD, and its tag points at that merge. The ship journal records each member as `pending` or `integrated`. Resume verifies integrated members and checks a pending entry against the exact remote merge and tag before retrying. In direct mode, the member path publishes the bound branch before it pushes the merge to `main`, then pushes the tag; today `integration.integrate` pushes `main` first. On resume, if the merge matches, publish only the missing authorized refs (bound branch, tag); if all three match, mark it integrated; a mismatch blocks. Never integrate a member twice. Each member uses its own `direct` or `pull-request` mode; member k+1's PR opens only after member k merges. `validate-integrated` checks all repos. Undo of member landing journals a reset to that landing's proven parent in the member, then reconciles only that task's coordinator record; it refuses once that member commit is an ancestor of its `origin/main`. `bind_next_milestone_branch` and `retire_previous_branch` journal and validate member branch retirement after integration. Retirement deletes the remote member bound branch only with a delete authorization for that ref, tied to its expected remote SHA (the reviewed HEAD); member pre-push accepts a delete only when the remote SHA it reports matches. |
| S5 Activation | Bootstrap writes coordinator STATE first, then the router runs `members add --create` per new member. Each member journal keeps its approved target and resume step. Update `README.md`, `GUIDE.md`, and `skills/gsd-path/SHIP.md`. Run the two-repo cases below before enabling member execution. Regenerate host receipts in `tests/hosts/*`; those single-repo receipts alone do not prove multi-repo behavior. |

## Brownfield and greenfield

| Case | Handling |
| --- | --- |
| All repos new | S5 creates the coordinator, then adds each member with its own resumable bootstrap journal. |
| Existing Path project adds repos | S1 `members add` creates `.project/MEMBERS.md` at a milestone boundary. Past milestones stay single-repo. |
| Member has its own `.project/` | Allowed only without an active milestone. Joining leaves it untouched; its router refuses a new milestone while bound. Namespaced branches and tags avoid collisions. |
| Member is a GSD Core project | Joins like any repo. Its `.planning/` stays untouched. `gsd-path-migrate` is not part of joining. |
| Member has branch protection | Choose `pull-request` for that member. |

## Proof

Use temp repos with bare remotes. Prove each changed contract through its
executable interface; do not infer multi-repo behavior from host receipts.

- No `MEMBERS.md`: existing single-repo commands and output stay unchanged.
- Brownfield `members add` creates `MEMBERS.md`; ship input validation accepts it, `REPOSITORY.md` stays fixed, and non-`main` defaults are refused.
- A two-repo quick-lane run covers task dispatch, cross-repo milestone Verify from the coordinator sidecar with `../<member>`, final review, ordered ship, and next-milestone branch retirement.
- Namespaced member bound, task, verify, and integrate branches work without colliding with retained member branches or being accepted as coordinator branches.
- Member writes are denied in the wrong phase, including a coordinator-session write into a member outside build. Sidecar host configs stay untracked and compose with existing hooks.
- A missing or invalid common-Git-dir marker fails closed and names the repair command. Member pre-push refuses an unauthorized ref or SHA, accepts the pull-request bound branch at the reviewed HEAD, and accepts direct-mode pushes of the authorized merge to `main`, bound branch at the reviewed HEAD, and annotated tag object to the member tag ref. Each ref accepts only its authorized object. A bound-branch delete is accepted only with a delete authorization whose expected remote SHA matches, and refused otherwise.
- A member with shipped M004 and a missing local tag joins and lands a task without applying its own STATE; an active member milestone is refused.
- A crash between member product commit and coordinator record resumes. Deleting the member commit after the record makes the task not landed. Two parallel tasks sharing Base land in order, with the second landing proved against its actual parent.
- A member Verify ledger row resolves by (command, repo, SHA); older single-repo rows still resolve.
- Lookahead plan drift in a member is detected against that member's recorded base and tip.
- Ship fails on the second member: the journal records the first as integrated, resume verifies and skips it, then completes the milestone. A crash after a member merge or tag but before the journal update reconciles that pending entry without another integration. A direct close stopped after the bound-branch push resumes with the merge and tag; one stopped after the merge push publishes the missing tag. Branch retirement then succeeds. A new task for an integrated member is refused.
- Ship-body validation binds each member's reviewed HEAD to final review and rejects missing or changed member lines.
- A member closes in `direct` and in `pull-request` mode with no STATE, archive, or ship commit in the member. `validate-integrated` rejects a member merge whose second parent is not the recorded reviewed HEAD.
- A member tag `milestone/<coord>-<archive-name>` does not collide with the member's own `milestone/<archive-name>` tag for the same milestone number.
- Undoing the second of two landings that shared Base keeps the first landing, reconciles only the second task's coordinator record, resumes after interruption, and refuses an integrated member commit.
- Greenfield bootstrap resumes each member from its approved target; a two-repo host proof passes before activation. Single-repo host receipts alone do not count.

## Decisions

1. Member remote default must be `main`; `members add` refuses others.
2. Each member may set `direct` or `pull-request` in `.project/MEMBERS.md`.
   The milestone mode is the default.
3. The coordinator may be a product repo or a dedicated program repo.

## Out of scope

Submodules, nested repos, one task across two repos, non-GitHub remotes, an
atomic close across repos, and `.project/` outside Git.

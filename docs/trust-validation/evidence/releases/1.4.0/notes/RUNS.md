# Live release evidence — 1.4.0

Candidate: `6d3e38ed525831217cf7d4790674feebd8afc75f` (main after PRs #240 and #241).

Raw native runs, owner replies, oracle records and guard references are local
and not committed: `~/orca/evaluations/gsd-path-release-1.4.0-6d3e38ed/`.

## Scope

Seven hosts were evaluated: Codex, Claude Code, Grok, OpenCode, Antigravity,
Cursor, and Kimi. Each has a validated receipt, zero invalid attempts, and a
6/6 external counter oracle from a fresh clone of its local origin `main`.

GitHub Copilot CLI was not evaluated. Its first attempt stopped after 41 seconds
with HTTP 402 `quota_exceeded`; probes with `gpt-5-mini`, `gpt-5.4-mini`, and
`claude-haiku-4.5` returned the same error, so the quota block was account-wide.
The maintainer excluded Copilot from the live-check scope, first for 1.4.0; it
stays excluded until the maintainer restores it by removing it from
`EXCLUDED_EVALUATION_HOSTS` before the next release's evaluation. Qwen, Kiro,
and Zed stay excluded for API cost. Exclusion is not a live-test pass.

## Owner gates

Every host stopped at each owner gate; no host recorded pre-approval. All
hosts except Codex and Claude ran with a hard-stop prompt addendum. Every
first INTENT missed some required criteria (all `int()` input forms, exact
output bytes, or failure on unknown flags and extra positionals) and was
corrected once before approval. The Cursor and OpenCode plans were also
corrected once (Cursor: JSON bytes differed between PLAN and task; OpenCode:
a Verify prefix `cd "$(dirname "$0")/.."` that leaves the repository under
`sh -c`).

## Output tokens (native fields, owner ruling: recorded, not blocking)

| Host | Parent session output | Notes |
|---|---|---|
| Codex | 22,145 | cumulative thread total |
| Claude Code | 47,971 (66,919 with children) | no single run over 30,000 |
| Grok | 198,399 | turn 1 62,805; turn 4 87,694; review child 37,831 |
| OpenCode | 27,490 (+13,477 reasoning) | all sessions under 30,000 |
| Antigravity | 96,668 | running conversation total; initial run 35,655 |
| Cursor | 45,767 | no single run over 30,000 |
| Kimi | 99,468 (main 66,037) | initial and build invocations over 30,000 with children |

## Hardening gaps and oddities (none is a candidate defect)

- Cursor's parent edited the reviewer's `wave-1.cycle1.md` to restore bold SC
  headings after `check_handoffs.py wave` refused a heading mismatch; verdicts
  did not change (same as the valid 1.3.1 Cursor run). The heading check is
  markup-sensitive and review files are not edit-protected.
- The plan gate does not check a Verify command's working directory (OpenCode).
- The native Bash guard over-blocks some read-only commands that touch archive
  paths with redirects, or `&&` compounds after integration (Claude).
- The harness prompt tells hosts to use the evaluator `activity` wrapper, which
  conflicts with the evaluator rule against it for Verify and sidecar work;
  hosts used it only for inspect/define helpers or read-only commands.
- Several hosts reported the wrong session id at the archive checkpoint
  (inherited evaluator environment or host worker ids); receipts use the real
  ids from the host streams.
- The serial Task Verify record names the primary checkout as `worktree` while
  `location` names the sidecar.
- Docs disagree on task-name case (`build_T001` vs `build_t001`).
- The Git pre-commit guard refuses any commit in a repository without a
  staged `.project/STATE.md` ("inspection failed"); evaluator reference repos
  needed `--no-verify` for their setup commit.

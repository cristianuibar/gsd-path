# Path owns a managed block in AGENTS.md, not the whole file

Status: accepted. Tracked in #160.

`AGENTS.md` is a shared file. Repo owners, Codex, Cursor and gsd-core write
it. Path now installs its whole 26 KB contract as `AGENTS.md`, once, and
never updates it. This causes three defects:

- A brownfield repo with its own `AGENTS.md` is refused (#147).
- `--update` keeps `AGENTS.md`, so every template change is a manual merge
  (UPDATE.md "Update project contracts").
- Codex reads only the first 32 KiB of project docs (`project_doc_max_bytes`
  default 32768). Path alone uses about 80% of that budget.

**Decision:** Path owns one marked region of `AGENTS.md`:

    <!-- gsd-path:begin -->
    ...Path contract...
    <!-- gsd-path:end -->

The owner owns everything outside the markers. `--project` inserts the block
into a new or existing `AGENTS.md`. `--update --project` replaces only the
block. Uninstall removes only the block. Doctor checks the block, not the
whole file. A file with more than one block, or unmatched markers, is
refused. The block goes first, so Codex truncates owner text added after it
before Path rules. Owner text added above the block can push Path rules past
the 32 KiB cutoff; the install/update size check cannot catch this between runs.

The block holds only rules every turn needs: authority order, plain-prompt
re-entry, gates, evidence. Phase and role detail moves into the skills that
load on demand. Candidates: "Stay in role" (9.0 KB), "Files are the only
memory" (5.2 KB), "New GitHub repositories" (1.9 KB), "Distribution layout"
(1.2 KB). Implemented: the first three moved to the bundled
`references/operating-rules.md` (every skill reads it before phase work);
"Distribution layout" moved to the source repo's `CLAUDE.md`. The block fell
from 26.0 KB to about 10.9 KB. No byte budget is set; only the 32 KiB merged
limit is enforced.
Install and update refuse a merged `AGENTS.md` over 32 KiB. This is the one
exception to brownfield installs without rename: silent truncation is worse
than a refusal. The error prints the file and block sizes, the merged size,
and the path to rename the existing file.

`WORKFLOW.md` stays Path-owned (no host reads it natively). `.claude/CLAUDE.md`
stays a bridge.

**Considered options:** rename the existing file aside (#147 short-term fix in PR #161;
keeps the manual merge and the size problem); append the owner's file under
Path's contract with an opt-in flag (works only for owner files under about
6.7 KB, makes upgrades harder); move Path's contract to its own file and
point to it from `AGENTS.md` (Codex has no import, so the pointer depends on
the model following it).

**Consequences:** existing installs need a one-time migration. A file equal
to a released template becomes a block. An edited whole-file install is
refused with a diff and manual steps because Path cannot tell its text from
owner edits. After migration, `--update` replaces only the block without a
manual merge. Skills that name `AGENTS.md` sections must point at the new
skill location when a section moves. The contract every host reads changes,
so every release evaluation host must be rerun per the live-check scope in
[TRUST-VALIDATION-SPEC.md](../trust-validation/TRUST-VALIDATION-SPEC.md).

# Multi-repo milestones use a coordinator repo

Status: accepted.

One milestone may change several Git repositories. One **coordinator** holds
`.project/`: state, tasks, review, archive, and the ship commit. Its
`.project/MEMBERS.md` lists the **members**; `members add` creates the file for
new or existing Path projects. The fixed `REPOSITORY.md` format stays unchanged.
Every CLI keeps one `--repo` (the coordinator). Without `MEMBERS.md`, Path keeps
its single-repo behavior and output.

One task changes one repo (`repo:` defaults to the coordinator). A member task
lands a product commit in the member and a record commit in the coordinator;
a journal makes the pair resumable. Build locks the participating members in
their `MEMBERS.md` order under `.project/build/`, not in STATE. Ship integrates
and tags those members in that order, then closes the coordinator. It records
each member's reviewed HEAD and integration. Git cannot merge repos atomically,
so a failed close remains partially shipped until resume or a patch plan.

**Considered options:** a workspace folder outside Git holds `.project/` (the
ship commit and archive leave Git); linked peer projects each hold `.project/`
(no shared milestone or close); open every PR and merge all at the end
(pull-request mode only).

**Consequences:** member branches and tags include the coordinator name
(`gsd-path/<coord>-M00N`, `milestone/<coord>-NNN-slug`). All branch checks must
accept this pattern only for verified members. Joining adds no new tracked Path
files and leaves a member's existing `.project/` untouched. Its shared Git
directory holds a validated coordinator marker and exact push authorization;
member hooks call the coordinator guard. Member sidecars get untracked host
guard configs and a shared, pinned layout for cross-repo Verify. Ship records a
`Reviewed-HEAD` for each member. Member execution stays disabled until the
two-repo proof passes. A member's remote default must be `main`; each member
may choose its integration mode. The coordinator may be a product repo or a
dedicated program repo. Submodules, nested repos, and one task across two repos
stay out of scope. The work plan is [multi-repo-work.md](../multi-repo-work.md).

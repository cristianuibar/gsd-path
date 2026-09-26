# Multi-repo milestones use a coordinator repo

Status: accepted.

One milestone may change several Git repositories. One repository, the
**coordinator**, holds `.project/`: STATE, tasks, the verify ledger, the
archive, and the ship commit. The other repositories are **members**, listed in
a `Members:` section of the coordinator's `.project/REPOSITORY.md`. A milestone
names the members it changes; only those get a bound branch. Every CLI keeps
one `--repo` (the coordinator) and reads members from that binding. A project
without a `Members:` section behaves exactly as before.

One task changes one repository (`repo:` in the task frontmatter, default the
coordinator). A change across repositories is two tasks with a dependency. A
member task lands as a product commit in the member plus a record commit in
the coordinator; a journal makes the pair resumable.

Ship closes members in a fixed order, then the coordinator. The coordinator
ship commit records each member's integration. Git cannot merge across
repositories atomically, so a failure after some members merge leaves the
milestone **partially shipped** until resume or a patch plan completes it.

**Considered options:** a workspace folder outside Git holds `.project/` (all
repositories equal, but the ship commit and archive leave Git); linked peer
projects, each with its own `.project/` and cross-repo ordering (small change,
but no shared milestone or close); open every pull request and merge all at
the end (smaller failure window, pull-request mode only).

**Consequences:** member branches and tags carry the coordinator's name
(`gsd-path/<coord>-M00N`, `milestone/<coord>-NNN-slug`) so they cannot collide
with a member's own Path history. Member repositories get no tracked Path
files; their hooks and coordinator marker live in the member's Git directory.
The guard hook must gate writes into member worktrees; today it allows every
write outside its own repository. A member's remote default must be `main`.
A member may set its own integration mode for branch protection. The
coordinator may be a product repository or a dedicated program repository.
Submodules, nested repositories, and one
task across two repositories stay out of scope. The work plan is
[multi-repo-work.md](../multi-repo-work.md).

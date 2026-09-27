## Agent skills

Repository-only: `docs/agents/` configures this source repository and is not installed into consumer projects.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Distribution layout

This section describes the GSD Path source checkout. These source paths and
the sync command do not apply to an application that only installs GSD Path.
In a consuming project, resolve roles, templates, and helpers from the active
installed skill's absolute paths; the application need not contain this layout.

| Path | Purpose |
|------|---------|
| `plugin.json` | Agent Plugins manifest (`agent-plugins.org` 1.0.0 schema) |
| `skills/` | Skills and aliases declared in `scripts/skill-resources.json` |
| `skills/gsd-path/templates/` | Required artifact formats |
| `skills/gsd-path/references/` | Agent role and dispatch contracts |
| `WORKFLOW.md` | Phase-by-phase SOP |

Edit canonical resources only: `skills/gsd-path/` templates and references,
each per-skill `SKILL.md`, `scripts/`, and
`platforms/shared-agents/dispatch.md`. Every per-skill `references/`,
`templates/`, and `scripts/` copy is generated — run `python3
scripts/sync_skill_resources.py` after editing a canonical source. Sync
overwrites divergent generated copies and warns when a divergent copy is
newer than its canonical source (the wrong-direction-edit signature); treat
that warning as a lost edit and re-apply it to the canonical path.

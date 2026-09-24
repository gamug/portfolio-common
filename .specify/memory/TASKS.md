# TASKS.md — `portfolio-common`

Discrete, checkable task breakdown for `.specify/memory/PLAN.md`. Each
task references the plan work item and the `SPEC.md` section it closes.
Check a box only when its acceptance criterion (in `PLAN.md`) is actually
met — not when the code is merely written.

**Closed work items live in `.specify/memory/CHANGELOG.md`**, moved there verbatim
(task IDs unchanged) once every task in them is done, superseded, or moved elsewhere —
see constitution AI behavior #10. This file carries only open work items.

Task IDs are stable, same rule as `SPEC.md`'s `FR-0xx`/`NR-0xx`: don't
renumber; mark a cancelled/superseded task in place instead.

## Work item 5 — Spec-driven-development scaffolding (this pass)

Adopting the spec-kit workflow in this repo, mirroring `portfolio-nlp`'s
`.specify/memory/` set. Recorded here so the scaffolding itself is traceable
like any other change.

- [x] **T-040** Write `.specify/memory/constitution.md` — principles adapted
      to a zero-dependency shared library (public names are cross-repo
      contracts; the git tag is the release artifact; tags are immutable; no
      env reads; no AI component). (Done 2026-09-12, this pass.)
- [x] **T-041** Write `.specify/memory/SPEC.md` — FR-001–FR-012 /
      NR-001–NR-007 against the **current** `master` (`v1.2.1`: `Dialect`
      seam, `connect_url`, `Row`/`RowLike`, `two_store`, `news_export`), with
      the shared general sections (thesis header, ID conventions, §1
      dataflow, §14 preamble, §15 sign-off) kept as they are in every repo's
      copy. (Done 2026-09-12, this pass.)
- [x] **T-042** Write `.specify/memory/PLAN.md` and this `TASKS.md` from
      `SPEC.md` §13's actionable items. (Done 2026-09-12, this pass.)
- [x] **T-043** Exclude agent artifacts from version control per constitution
      Code & Git #8 — `CLAUDE.md`, `.claude/`, `.superpowers/` git-ignored,
      with `.specify/` called out as the deliberate tracked exception.
      (Done 2026-09-12, this pass.)
- [x] **T-044** Create `CLAUDE.md` (untracked) carrying references to both
      `.specify/memory/constitution.md` and `.specify/memory/SPEC.md`, per
      constitution AI behavior #6. (Done 2026-09-12, this pass.)
- [ ] **T-045** Review and ratify: the constitution is `Version 1.0.0`,
      ratified 2026-09-12, and `SPEC.md` is `Version 1.0.0` — both pending
      the maintainer's actual read-through. Until then, treat §13's nine
      items as this agent's reading of the repo, not an agreed backlog.

## Status

**Work items 1–4 are done (2026-09-12, one PR, branch
`chore/spec-backlog-cleanup`).** `business_folders/` is deleted; CI builds
and verifies the wheel and runs the test suite on a `windows-latest` +
`ubuntu-latest` matrix; the Windows test failure is fixed (79 passed, 0
failed); `README.md`'s pin is current; both architecture artifacts were
checked and the one that needed it (`Portfolio Common`) was already
reconciled in the same session, the other (`Portfolio Thesis`) needed no
change. `SPEC.md` bumped to `1.1.0` to record the five §13 items this
closed (1, 2, 3, 8, and the README half of 9).

Work item 5 (the spec-kit scaffolding) is done except **T-045**, the
maintainer's review — which is also the gate on treating `SPEC.md` §13 as an
agreed backlog rather than a proposal.

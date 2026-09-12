# TASKS.md — `portfolio-common`

Discrete, checkable task breakdown for `.specify/memory/PLAN.md`. Each
task references the plan work item and the `SPEC.md` section it closes.
Check a box only when its acceptance criterion (in `PLAN.md`) is actually
met — not when the code is merely written.

Task IDs are stable, same rule as `SPEC.md`'s `FR-0xx`/`NR-0xx`: don't
renumber; mark a cancelled/superseded task in place instead.

## Work item 1 — Delete `business_folders/` (no blockers)

All three owning repos have adopted their folder (`portfolio-nlp` →
`src/news_nlp/`, `portfolio-financial-analysis` → `src/kg_schema/`,
`portfolio-data-mining` → `src/data_mining/`) and **every** staged file has
since diverged from the adopted version. FR-012's expiry condition is met;
the deletion is what's outstanding. → `PLAN.md` Work item 1, `SPEC.md` §13
item 1 / FR-012.

- [ ] **T-001** Re-verify adoption before deleting: for each of the three
      owning repos, confirm its `origin/master` carries the adopted tree and
      its `[tool.uv.sources]` pin is a `v1.2.x` tag. Don't rely on
      `PLAN.md`'s table as the evidence. → `PLAN.md` Work item 1, step 1.
- [ ] **T-002** Delete `business_folders/` in full — the three domain
      folders, their `tests/`, every `README.md` (including
      `business_folders/README.md`), and
      `business_folders/news_nlp/ruff.toml`. → step 2.
- [ ] **T-003** Update `README.md`'s `## business_folders/` section to a
      short historical note (where each domain lives now + a pointer to
      `CHANGELOG.md` v1.0.0), replacing the present-tense "staged for
      relocation" framing. → step 3.
- [ ] **T-004** Update `src/portfolio_common/__init__.py`'s module docstring,
      which still tells the reader the business code "has moved to
      `business_folders/` in this repo, staged for relocation into the repo
      that owns it" — point at the owning repos instead. → step 3.
- [ ] **T-005** Add a `CHANGELOG.md` **Unreleased** entry recording the
      deletion and naming where each of the three domains now lives. No
      version bump — nothing packaged changes (constitution: Code & Git #4).
      → step 4.
- [ ] **T-006** Verify: `git ls-files business_folders` is empty;
      `uv run pytest` / `ruff check .` / `ruff format --check .` /
      `mypy --config-file=.code_quality/mypy.ini src` all still green;
      `grep -rn "business_folders" --exclude-dir=.git .` returns only
      historical mentions (`CHANGELOG.md`, the `README.md` note,
      `.specify/`). → `PLAN.md` Work item 1 acceptance criteria.
- [ ] **T-007** Annotate `SPEC.md` FR-012 (acceptance satisfied, retired) and
      §13 item 1 (resolved) in place — keep both IDs. → step 5. Artifact
      reconciliation for this change is **T-031** (do it there, not twice).

## Work item 2 — Assert the packaged surface + fix the README pin (no blockers)

`business_folders/` stayed out of the wheel only because it sits outside
`src/` and `packages = ["src/portfolio_common"]` — nothing asserts it, so a
`pyproject.toml` edit could ship three repos' business logic to four
consumers with no test failing. Separately, `README.md`'s adoption snippet
still pins `v1.2.0` while `v1.2.1` is current. → `PLAN.md` Work item 2,
`SPEC.md` §13 items 2 and 9.

- [ ] **T-010** Add a wheel-contents assertion: build with `uv build --wheel`
      and assert every path in the archive starts with `portfolio_common/`
      **and** that `py.typed` is present (NR-005). Stdlib only — no new
      dependency, no build plugin. → `PLAN.md` Work item 2, step 1.
- [ ] **T-011** Wire it into `.github/workflows/ci.yml` after the existing
      four gates (ruff check → ruff format → mypy → pytest), so a packaging
      regression fails the PR that causes it. → step 2.
- [ ] **T-012** Prove the check gates: temporarily add `business_folders` (or
      any non-`src/` path) to `[tool.hatch.build.targets.wheel].packages`,
      confirm CI **fails**, then revert. A check that only ever passes hasn't
      been tested. → first acceptance criterion.
- [ ] **T-013** Bump `README.md`'s `[tool.uv.sources]` example to the current
      release tag, and add a one-line pointer that `CHANGELOG.md` is the
      authority on what the current release is. → step 3.
- [ ] **T-014** Annotate `SPEC.md` §13 item 2 (resolved) and item 9 (README
      half resolved; the tag-split half stays accepted per §14). → step 4.

## Work item 3 — Green on Windows + a Windows CI leg (no blockers)

`uv run pytest` is **78 passed, 1 failed** on the development platform:
`test_engine_agnostic.py::test_split_url_accepts_pathlike` asserts
`_split_url(Path("/x/y.db")) == ("sqlite", "/x/y.db")`, but `os.fspath`
yields `\x\y.db` on Windows. The library is correct (`connect_url`
normalizes via `Path(target).as_posix()`); the assertion is POSIX-only. CI is
`ubuntu-latest`-only, so the one platform-sensitive area of this library —
path/URI construction, including the documented Windows-drive-letter case in
`_split_url` (FR-003) — is the one area CI can't see. → `PLAN.md` Work item
3, `SPEC.md` §13 item 3 / NR-007.

- [ ] **T-020** Fix the assertion to test the invariant rather than the
      pass-through: prefer asserting that `connect_url` produces a
      POSIX-normalized `file:` target on both platforms, over comparing
      `_split_url`'s raw `os.fspath` output. → `PLAN.md` Work item 3, step 1.
- [ ] **T-021** Sweep the rest of `tests/` for the same assumption — any
      other literal POSIX path string in an assertion will fail the moment a
      Windows runner exists. → step 2.
- [ ] **T-022** Add `windows-latest` to `.github/workflows/ci.yml` as a
      matrix entry for the **test** step only; leave ruff/ruff-format/mypy on
      `ubuntu-latest` (platform-independent here — running them twice buys
      nothing). → step 3.
- [ ] **T-023** Verify: `uv run pytest` is **79 passed, 0 failed** locally on
      Windows, and a CI run shows the test job green on both
      `ubuntu-latest` and `windows-latest`. → `PLAN.md` Work item 3
      acceptance criteria.
- [ ] **T-024** Update `SPEC.md` NR-007's acceptance criterion (drop the
      "currently unmet" note), §10's "Known gap: the suite is not green on
      Windows" subsection, and §13 item 3. → step 4.

## Work item 4 — Reconcile the repository artifact with itself (do last)

The repo artifact ([Portfolio
Common](https://claude.ai/code/artifact/a1a5f985-a6b9-4dd1-8e2d-cc1f0d939e2b))
was updated for `v1.2.1` in its header and engine-seam section but not in its
diagram or gaps list, so it contradicts itself: the diagram still reads
`v1.0.0 · breaking · PR #7 open` with three "adoption pending" arrows, and
the gaps list still claims "zero of three repos have adopted it" and that the
`v1.0.0` tag sits ahead of `master` — all untrue since 2026-09-05. Sequenced
last because Work items 1-3 change what the artifact should say. → `PLAN.md`
Work item 4, `SPEC.md` §13 item 8, constitution AI behavior #9.

- [ ] **T-030** Update the "Where the business logic goes next" diagram:
      adoption is complete on the consumer side, and (once T-002 lands)
      `business_folders/` is gone rather than pending. → `PLAN.md` Work item
      4, step 1.
- [ ] **T-031** Replace the four gap cards with the live set from `SPEC.md`
      §13 — drop "Zero of three repos have adopted it" and the
      `v1.0.0`-tag-ahead-of-`master` card; mark the accepted items
      (§13 items 4, 5, 6, 7) as accepted rather than open. → step 2.
- [ ] **T-032** Reconcile the system-wide [Portfolio
      Thesis](https://claude.ai/code/artifact/d3865a63-2894-4e20-b38a-7e50cf0d4040)
      artifact in the same pass for anything it says about this repo. →
      step 3.
- [ ] **T-033** Confirm **neither** artifact's `<title>` / gallery name
      changed — content only (constitution AI behavior #9: renaming is an
      explicit, separate, user-directed action, never a side effect). →
      step 4 / second acceptance criterion.

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

Nothing in Work items 1-4 has started. T-001–T-007 (delete
`business_folders/`) and T-020–T-024 (Windows green + CI leg) are the two
unblocked, independent starting points; T-010–T-014 reads better after
T-002 lands; T-030–T-033 is deliberately last, since the first three work
items change what the artifact should say.

Work item 5 (the spec-kit scaffolding) is done except **T-045**, the
maintainer's review — which is also the gate on treating `SPEC.md` §13 as an
agreed backlog rather than a proposal.

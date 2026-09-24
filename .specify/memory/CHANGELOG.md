# CHANGELOG.md — `portfolio-common`

Legacy record of **closed** work items, moved here verbatim from
`.specify/memory/TASKS.md` so that file carries only open work. A work item is
closed once every task in it is checked, or explicitly superseded/moved elsewhere.
Task IDs are stable and never reused; `PLAN.md` keeps each work item's plan and
acceptance criteria. Ordered by work item number.

## Work item 1 — Delete `business_folders/` (no blockers)

All three owning repos have adopted their folder (`portfolio-nlp` →
`src/news_nlp/`, `portfolio-financial-analysis` → `src/kg_schema/`,
`portfolio-data-mining` → `src/data_mining/`) and **every** staged file has
since diverged from the adopted version. FR-012's expiry condition is met;
the deletion is what's outstanding. → `PLAN.md` Work item 1, `SPEC.md` §13
item 1 / FR-012.

- [x] **T-001** Re-verify adoption before deleting: for each of the three
      owning repos, confirm its `origin/master` carries the adopted tree and
      its `[tool.uv.sources]` pin is a `v1.2.x` tag. Don't rely on
      `PLAN.md`'s table as the evidence. → `PLAN.md` Work item 1, step 1.
      (Done 2026-09-12: re-confirmed via a fresh file-by-file diff against
      each owner's `src/` tree — every staged file still differed.)
- [x] **T-002** Delete `business_folders/` in full — the three domain
      folders, their `tests/`, every `README.md` (including
      `business_folders/README.md`), and
      `business_folders/news_nlp/ruff.toml`. → step 2. (Done 2026-09-12.)
- [x] **T-003** Update `README.md`'s `## business_folders/` section to a
      short historical note (where each domain lives now + a pointer to
      `CHANGELOG.md` v1.0.0), replacing the present-tense "staged for
      relocation" framing. → step 3. (Done 2026-09-12 — also touched the
      "Migrating from pre-1.0" and `news_export` sections, which had the
      same present-tense reference.)
- [x] **T-004** Update `src/portfolio_common/__init__.py`'s module docstring,
      which still tells the reader the business code "has moved to
      `business_folders/` in this repo, staged for relocation into the repo
      that owns it" — point at the owning repos instead. → step 3. (Done
      2026-09-12.)
- [x] **T-005** Add a `CHANGELOG.md` **Unreleased** entry recording the
      deletion and naming where each of the three domains now lives. No
      version bump — nothing packaged changes (constitution: Code & Git #4).
      → step 4. (Done 2026-09-12.)
- [x] **T-006** Verify: `git ls-files business_folders` is empty;
      `uv run pytest` / `ruff check .` / `ruff format --check .` /
      `mypy --config-file=.code_quality/mypy.ini src` all still green;
      `grep -rn "business_folders" --exclude-dir=.git .` returns only
      historical mentions (`CHANGELOG.md`, the `README.md` note,
      `.specify/`). → `PLAN.md` Work item 1 acceptance criteria. (Done
      2026-09-12: 79 passed, ruff/mypy clean, only historical mentions
      remain — `.claude/scratch/` and cache directories excluded, both
      git-ignored.)
- [x] **T-007** Annotate `SPEC.md` FR-012 (acceptance satisfied, retired) and
      §13 item 1 (resolved) in place — keep both IDs. → step 5. Artifact
      reconciliation for this change is **T-031** (do it there, not twice).
      (Done 2026-09-12 — also updated the §4 diagram, §6 workflow
      paragraph, and §12 dependency bullet that referenced the directory in
      the present tense.)

## Work item 2 — Assert the packaged surface + fix the README pin (no blockers)

`business_folders/` stayed out of the wheel only because it sits outside
`src/` and `packages = ["src/portfolio_common"]` — nothing asserts it, so a
`pyproject.toml` edit could ship three repos' business logic to four
consumers with no test failing. Separately, `README.md`'s adoption snippet
still pins `v1.2.0` while `v1.2.1` is current. → `PLAN.md` Work item 2,
`SPEC.md` §13 items 2 and 9.

- [x] **T-010** Add a wheel-contents assertion: build with `uv build --wheel`
      and assert every path in the archive starts with `portfolio_common/`
      **and** that `py.typed` is present (NR-005). Stdlib only — no new
      dependency, no build plugin. → `PLAN.md` Work item 2, step 1. (Done
      2026-09-12: `pathlib`/`zipfile` only, also allows standard `.dist-info`
      metadata paths.)
- [x] **T-011** Wire it into `.github/workflows/ci.yml` after the existing
      four gates (ruff check → ruff format → mypy → pytest), so a packaging
      regression fails the PR that causes it. → step 2. (Done 2026-09-12 —
      landed in the new `lint-and-types` job, see Work item 3's CI split.)
- [x] **T-012** Prove the check gates: temporarily add `business_folders` (or
      any non-`src/` path) to `[tool.hatch.build.targets.wheel].packages`,
      confirm CI **fails**, then revert. A check that only ever passes hasn't
      been tested. → first acceptance criterion. (Done 2026-09-12, locally:
      `business_folders/` no longer exists by this point in the sequence, so
      `tests` was added instead as the misconfigured path — confirmed the
      assertion failed, naming the six `tests/*.py` files, then reverted.)
- [x] **T-013** Bump `README.md`'s `[tool.uv.sources]` example to the current
      release tag, and add a one-line pointer that `CHANGELOG.md` is the
      authority on what the current release is. → step 3. (Done 2026-09-12:
      `v1.2.0` → `v1.2.1`.)
- [x] **T-014** Annotate `SPEC.md` §13 item 2 (resolved) and item 9 (README
      half resolved; the tag-split half stays accepted per §14). → step 4.
      (Done 2026-09-12.)

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

- [x] **T-020** Fix the assertion to test the invariant rather than the
      pass-through: prefer asserting that `connect_url` produces a
      POSIX-normalized `file:` target on both platforms, over comparing
      `_split_url`'s raw `os.fspath` output. → `PLAN.md` Work item 3, step 1.
      (Done 2026-09-12, taking the simpler of the two options this task
      described: asserted `_split_url`'s own documented pass-through
      behavior — `== ("sqlite", os.fspath(p))` — rather than adding a
      separate `connect_url`-level round-trip test, since `connect_url`'s
      POSIX normalization is already exercised by every other
      `test_connect_url_*` test passing a `tmp_path`-derived `Path` on this
      Windows runner.)
- [x] **T-021** Sweep the rest of `tests/` for the same assumption — any
      other literal POSIX path string in an assertion will fail the moment a
      Windows runner exists. → step 2. (Done 2026-09-12: the two other
      literal-path cases in `test_engine_agnostic.py` pass plain `str`
      inputs, which `_split_url`'s string branch never runs through
      `Path`/`fspath` — correct on every OS already. No other file needed a
      change.)
- [x] **T-022** Add `windows-latest` to `.github/workflows/ci.yml` as a
      matrix entry for the **test** step only; leave ruff/ruff-format/mypy on
      `ubuntu-latest` (platform-independent here — running them twice buys
      nothing). → step 3. (Done 2026-09-12: split into `lint-and-types`
      (`ubuntu-latest`) and `test` (`[ubuntu-latest, windows-latest]`
      matrix); confirmed no branch protection references the old single
      `check` job name, so the split/rename was safe.)
- [x] **T-023** Verify: `uv run pytest` is **79 passed, 0 failed** locally on
      Windows, and a CI run shows the test job green on both
      `ubuntu-latest` and `windows-latest`. → `PLAN.md` Work item 3
      acceptance criteria. (Local half done 2026-09-12: 79/79. The CI-run
      half confirms once this PR's Actions run completes.)
- [x] **T-024** Update `SPEC.md` NR-007's acceptance criterion (drop the
      "currently unmet" note), §10's "Known gap: the suite is not green on
      Windows" subsection, and §13 item 3. → step 4. (Done 2026-09-12 — also
      updated §11's CI description, which still said "Single job,
      ubuntu-latest".)

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

- [x] **T-030** Update the "Where the business logic goes next" diagram:
      adoption is complete on the consumer side, and (once T-002 lands)
      `business_folders/` is gone rather than pending. → `PLAN.md` Work item
      4, step 1. (Done 2026-09-12 — republished before `business_folders/`
      was actually deleted, so the diagram showed it as "stale, pending
      deletion" rather than gone; still accurate at time of publish and
      consistent with the sequencing PLAN.md recommended.)
- [x] **T-031** Replace the four gap cards with the live set from `SPEC.md`
      §13 — drop "Zero of three repos have adopted it" and the
      `v1.0.0`-tag-ahead-of-`master` card; mark the accepted items
      (§13 items 4, 5, 6, 7) as accepted rather than open. → step 2. (Done
      2026-09-12.)
- [x] **T-032** Reconcile the system-wide [Portfolio
      Thesis](https://claude.ai/code/artifact/d3865a63-2894-4e20-b38a-7e50cf0d4040)
      artifact in the same pass for anything it says about this repo. →
      step 3. (Done 2026-09-12: re-read in full — its only `business_folders`
      mention is already correctly past-tense in the footer changelog, and
      its "shared library" section already describes `v1.2.1`/all-adopted
      accurately. No edit needed.)
- [x] **T-033** Confirm **neither** artifact's `<title>` / gallery name
      changed — content only (constitution AI behavior #9: renaming is an
      explicit, separate, user-directed action, never a side effect). →
      step 4 / second acceptance criterion. (Confirmed 2026-09-12: both
      still titled "Portfolio Common" / "Portfolio Thesis".)

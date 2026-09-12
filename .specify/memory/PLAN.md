# PLAN.md — `portfolio-common`

The implementation plan for the live backlog identified in
`.specify/memory/SPEC.md`. Where the constitution is principles and
`SPEC.md` is the requirements/architecture contract, this document is the
"how, and in what order" for the work that contract still leaves open.

**This plan is deliberately small, and that is the finding.** `SPEC.md` §13
(Open Questions & Risks) lists nine items; §14 (Scope Boundaries) disposes of
five of them as **accepted** — permanent characteristics of a shared library
at this project's scope (the engine name leaking through type signatures, a
seam with one implementation, an unversioned `news_export` contract, a
hand-enforced no-`sqlite3` rule, and staggered consumer pins). The four that
remain are all **hygiene on work already finished**: the `v1.0.0`→`v1.2.1`
refactor landed, all four consumers adopted it, and what's left is cleaning up
after it. None of the items below adds a feature, changes a public name, or
needs a MAJOR release. Three of the four are one-commit changes.

What this plan does *not* do is invent library work to look busy: no second
`Dialect`, no cursor wrapper, no ORM. `SPEC.md` §14 closes those, and closing
them is a finding too — this repo is, by design, close to done.

## Goal

Close the four actionable items in `SPEC.md` §13 without expanding this
repo's scope:

1. Delete `business_folders/` — all three owning repos have adopted it and
   every staged file has since diverged, so it is now a stale second copy of
   three repos' domain code living inside the dependency all of them pin
   (SPEC.md §13 item 1, FR-012). — Work item 1.
2. Make the wheel's exclusion of non-`src/` content an actual CI assertion
   rather than a property that happens to hold (SPEC.md §13 item 2). — Work
   item 2.
3. Get `uv run pytest` green on Windows and give CI a Windows leg, so the one
   platform-sensitive area of this library is actually covered (SPEC.md §13
   item 3, NR-007). — Work item 3.
4. Reconcile the repository artifact, which currently contradicts itself
   (header says `v1.2.1`, all adopted; diagram and gaps sections still say
   "PR #7 open", "zero of three repos have adopted") (SPEC.md §13 item 8,
   constitution AI behavior #9). — Work item 4.
5. Fix `README.md`'s consumer-pin example, which still shows `v1.2.0` while
   `v1.2.1` is the current release (SPEC.md §13 item 9, the actionable half).
   — folded into Work item 2 (same release-hygiene commit).

## Non-goals

Everything else in `SPEC.md` §13 stays exactly as §14 disposed of it —
**not** part of this plan:

- Item 4 — the engine name leaking through `execute() -> sqlite3.Cursor`,
  `.raw`, `Row`, `DatabaseError`: accepted; wrapping cursor and connection
  would add a wider public surface than the one it hides, and it only becomes
  load-bearing if a real second engine lands.
- Item 5 — the `Dialect` seam having exactly one implementation: accepted; an
  abstraction validated against one implementation is the honest state of it,
  and writing a throwaway second `Dialect` to "prove" the first is not a
  research goal here.
- Item 6 — `news_export`'s unversioned column contract: accepted; the module
  is deliberately narrow and both its consumers are in the same hands.
- Item 7 — NR-002 ("no consumer imports `sqlite3`") enforced by hand-grep:
  accepted *here*; automating it belongs in each consumer's own CI, which is
  that repo's call.
- Item 9's other half — consumers split across `v1.2.0` and `v1.2.1`:
  accepted; staggered adoption is normal and additive releases are compatible
  by construction (NR-004). Only the stale README pin is fixed (Work item 2).
- Any new public name, runtime dependency, or release: none of the four work
  items changes `portfolio_common`'s API, so none of them needs a version
  bump (constitution: Code & Git #4 — `business_folders/` is unpackaged, so
  deleting it is not a public-API change).

## Work item 1 — Delete `business_folders/`

**Why**: FR-012 gave this directory one job and an expiry condition: stage a
domain's code until its owning repo adopts it, then be deleted. The first half
is done everywhere and the second half nowhere:

| `business_folders/` | Owning repo | Adopted as | Divergence today |
|---|---|---|---|
| `data_mining/` | `portfolio-data-mining` | `src/data_mining/` | **all 7 files differ** |
| `financial_analysis/` | `portfolio-financial-analysis` | `src/kg_schema/` | **all 11 files differ** |
| `news_nlp/` | `portfolio-nlp` | `src/news_nlp/` | **all 10 files differ**, plus `news_nlp/eval/` exists only in `portfolio-nlp` |

Every consumer is pinned to a `v1.2.x` tag and running its own copy. So this
directory is no longer a handoff payload — it is a second, stale copy of three
repos' business logic sitting inside the library all of them depend on, where
nothing marks it as not-current. The exact risk `SPEC.md` §13 item 1 names: a
reader (human or agent) who finds `business_folders/news_nlp/news_nlp/db.py`
has no way to know it isn't `portfolio-nlp`'s `db.py`.

**Approach**:

1. Confirm adoption per domain before deleting anything — for each of the
   three owning repos, check that its own `master` carries the adopted tree
   and that its `portfolio-common` pin is a `v1.2.x` tag. (Don't take this
   plan's table as the evidence; re-verify at deletion time.)
2. Delete `business_folders/` entirely — all three domain folders, their
   `tests/`, their `README.md`s, `business_folders/README.md`, and
   `business_folders/news_nlp/ruff.toml`.
3. Update the two places that describe it as a live staging area:
   `README.md`'s `## business_folders/` section (replace with a short
   historical note pointing at `CHANGELOG.md` v1.0.0 and each owning repo),
   and `src/portfolio_common/__init__.py`'s module docstring (which currently
   tells the reader the business code "has moved to `business_folders/` in
   this repo, staged for relocation" — it hasn't been *in* this repo's plan
   since the owners adopted).
4. Add a `CHANGELOG.md` entry under an **Unreleased** heading recording the
   deletion and naming where each domain now lives. No version bump: nothing
   packaged changes, so SemVer has nothing to say (constitution: Code & Git
   #4). A reader of the tag history should still be able to find out where
   `kg_schema` went.
5. Update `SPEC.md` FR-012 and §13 item 1 in the same PR — FR-012's
   acceptance criterion becomes "satisfied and retired", annotated in place
   (keep the ID, per this document's no-renumbering convention).

**Acceptance criteria**:

- `business_folders/` does not exist; `git ls-files business_folders` is
  empty.
- `uv run pytest`, `ruff check .`, `ruff format --check .` and `mypy … src`
  are all still green (they should be unaffected — `tests/` never imported
  `business_folders/`, and `pytest.ini`'s `testpaths = tests` never collected
  its tests).
- No remaining reference to `business_folders/` describes it as current:
  `grep -rn "business_folders" --exclude-dir=.git .` returns only the
  historical mentions in `CHANGELOG.md`, `README.md`'s note, and `.specify/`.
- `SPEC.md` FR-012 and §13 item 1 annotated as resolved; both architecture
  artifacts reconciled (constitution AI behavior #9 — and Work item 4 is
  where the artifact's own staleness gets fixed).

**Out of scope for this work item**: reconciling the *content* differences
between a staged copy and its adopted version. Those diffs are each owning
repo's own subsequent work (`portfolio-nlp` adding `news_nlp/eval/`, the
`v1.2.x` seam adoptions, and so on) — the adopted tree is authoritative by
definition. Nothing here gets merged back.

## Work item 2 — Assert the packaged surface, and fix the README pin

**Why**: Two small release-hygiene defects, both one-line-ish, both
invisible until they bite someone else.

`business_folders/` stayed out of the wheel only because it sits outside
`src/` and `[tool.hatch.build.targets.wheel].packages` names exactly
`src/portfolio_common` — nothing *asserts* it. A future `pyproject.toml` edit
could start shipping three repos' business logic to all four consumers with no
test failing. Work item 1 removes today's payload; this item is what stops the
class of problem recurring (and it generalizes: the assertion is really "the
wheel contains `portfolio_common` and nothing else").

Separately, `README.md`'s "Use it from another repo" snippet pins
`tag = "v1.2.0"` while `v1.2.1` is current — so the documented way to adopt
this library installs a release behind, silently.

**Approach**:

1. Add a CI step (or a test, if it can stay hermetic and fast) that builds the
   wheel and asserts its contents: every path inside starts with
   `portfolio_common/`, and `py.typed` is present. `uv build --wheel` plus a
   `python -c` over `zipfile.ZipFile(...).namelist()` is enough — no new
   dependency (NR-001 applies to runtime, but don't add a build plugin for
   this either).
2. Place it in `.github/workflows/ci.yml` after the existing four gates so a
   packaging regression fails the same PR that causes it.
3. Bump `README.md`'s example pin to the current release tag, and add a short
   "the current release is in `CHANGELOG.md`" pointer so the next bump doesn't
   depend on remembering to edit two places.
4. Update `SPEC.md` §13 items 2 and 9 (the README half) in the same PR.

**Acceptance criteria**:

- CI fails on a deliberately-broken `pyproject.toml` (e.g. temporarily adding
  `business_folders` to `packages`) and passes on `master` — proving the check
  actually checks, not just runs.
- `py.typed` presence is asserted, not assumed (NR-005).
- `README.md`'s pin matches the latest tag.
- `SPEC.md` §13 items 2 and 9 annotated.

## Work item 3 — Green on Windows, and a CI leg that proves it

**Why**: `uv run pytest` on the development platform is **78 passed, 1
failed**. `test_engine_agnostic.py::test_split_url_accepts_pathlike` asserts

```python
_split_url(Path("/x/y.db")) == ("sqlite", "/x/y.db")
```

but `_split_url` returns `os.fspath(url)`, which is `\x\y.db` on Windows. The
library is correct — `connect_url` normalizes with `Path(target).as_posix()`
before handing the target to SQLite — so this is a POSIX-only assertion, not
an engine defect. Two things follow, and the second matters more:

- A maintainer's local suite is red, which trains people to ignore a red
  suite.
- CI runs `ubuntu-latest` only, so the one area where this library is
  genuinely platform-sensitive (path/URI construction — Windows drive letters
  are a documented special case in `_split_url`, FR-003) is the one area CI
  can't see. NR-007 says both platforms must work; today only one is tested.

**Approach**:

1. Fix the assertion to be platform-correct rather than platform-specific —
   compare against `os.fspath(Path("/x/y.db"))`, or assert the round-trip
   property that actually matters (`connect_url` yields a POSIX-normalized
   `file:` target on both platforms). Prefer the second: it tests the
   invariant `connect_url` documents, rather than an implementation detail of
   `_split_url`'s pass-through.
2. While there, check the rest of the suite for the same assumption — any
   other test asserting a literal POSIX path string will fail the same way
   once a Windows runner exists.
3. Add `windows-latest` to `.github/workflows/ci.yml` as a matrix entry for
   the **test** step. Keep lint/format/type-check on `ubuntu-latest` only:
   ruff and mypy are platform-independent here, and running them twice buys
   nothing but minutes.
4. Update `SPEC.md` NR-007's acceptance criterion (it currently records the
   failure) and §13 item 3.

**Acceptance criteria**:

- `uv run pytest` is **79 passed, 0 failed** on Windows *and* on Linux.
- A CI run shows the test job passing on both `ubuntu-latest` and
  `windows-latest`.
- NR-007 no longer carries a "currently unmet" note; §13 item 3 annotated as
  resolved.

## Work item 4 — Reconcile the repository artifact with itself

**Why**: Constitution AI behavior #9 requires both architecture artifacts to
be reconciled at the close of every development effort. The repo artifact
([Portfolio
Common](https://claude.ai/code/artifact/a1a5f985-a6b9-4dd1-8e2d-cc1f0d939e2b))
was updated for `v1.2.1` in its header and engine-seam section but **not** in
its diagram or its gaps list, so it now contradicts itself:

| Artifact section | Says | Reality |
|---|---|---|
| Header / engine-seam table | `v1.2.1` merged & tagged, 5/5 consumers adopted, 0 `import sqlite3` outside this repo | correct |
| "Where the business logic goes next" diagram | `v1.0.0 · breaking · PR #7 open`; three dashed "migration plan pushed · adoption pending" arrows | PR #7 merged 2026-09-04; all three adopted |
| Gaps & risks | "Zero of three repos have adopted it"; "the `v1.0.0` tag sits ahead of `master`" | both untrue since 2026-09-05 |

A half-updated artifact is worse than a stale one: the header reassures a
reader that it's current, so the contradicting sections read as fact.

**Approach**:

1. Update the diagram to show what the `business_folders/` arrows actually
   are now: adoption **complete** on the consumer side, deletion pending here
   (or, if Work item 1 has landed first, gone entirely — preferred ordering,
   see Sequencing).
2. Replace the four gap cards with the live set from `SPEC.md` §13 (the
   actionable four, and the accepted ones marked as accepted) — in particular
   drop "zero of three repos have adopted" and the `v1.0.0`-tag-ahead-of-
   `master` card, both of which describe 2026-09-04.
3. Reconcile the system-wide [Portfolio
   Thesis](https://claude.ai/code/artifact/d3865a63-2894-4e20-b38a-7e50cf0d4040)
   artifact in the same pass for anything it says about this repo.
4. **Never rename either artifact** — no `<title>` change, no gallery-name
   change, content only (constitution AI behavior #9).

**Acceptance criteria**:

- No section of the repo artifact describes the `business_folders/` rollout
  as pending, and no gap card restates a gap closed in 2026-09-04/05.
- Both artifacts' titles are byte-identical to what they were before the
  update.
- The gaps list matches `SPEC.md` §13 — one source of truth, two renderings.

## Sequencing

Work items 1 and 3 are independent of each other and of everything else;
either can land first. Work item 2 is independent in substance but **reads
better after Work item 1** — the wheel assertion's motivating example
disappears with the directory, so landing 1 first lets 2 be written as the
general invariant ("the wheel is `portfolio_common` and nothing else") rather
than as a fix for a specific payload. Work item 4 should land **last**: the
artifact is supposed to describe what the code does, and items 1-3 change
that, so reconciling it first would just mean reconciling it twice.

Suggested order: **1 → 3 → 2 → 4**, or 1 and 3 in parallel if two branches
are in flight. None of them needs a release; if a release is cut afterwards
anyway (e.g. bundling the CHANGELOG's Unreleased section), it is a PATCH —
no public name changes in any of the four.

See `TASKS.md` for the discrete, checkable task breakdown.

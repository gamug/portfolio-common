# Project Constitution

Governing principles for `portfolio-common` under a spec-driven ("spec
coding") workflow: specs and plans are written before implementation, and
this document is the fixed reference they must not contradict. A spec or
plan that conflicts with a rule below must change the rule here first (see
Governance) rather than override it silently.

## Technological stock

`portfolio-common` is a **library, not a service** — no HTTP layer, no CLI,
no models, no scheduler, no data of its own; every rule below assumes the
stack actually pinned in `pyproject.toml`.

1. **Runtime**: Python `>=3.12,<3.13`, dependency-managed with `uv`
   (lockfile `uv.lock`, committed). Do not add a second package manager
   (pip/poetry/conda) — all installs go through `uv sync` / `uv add`.
2. **Zero runtime dependencies, as a constraint rather than a coincidence.**
   `[project].dependencies` is `[]` and stays `[]`: `v1.0.0` dropped
   `httpx`, `beautifulsoup4` and `pandas` along with the business code that
   needed them. Four repos pin this library, so a dependency added here is a
   dependency forced on all of them at once, transitively, with no say in
   the version. Adding one is a constitution-level change (see item 7), not
   a PR-level one.
3. **Stdlib `sqlite3` is the only engine binding, and it is confined.** It
   is imported in exactly two files — `src/portfolio_common/db/engine.py`
   and `src/portfolio_common/db/two_store.py`. `dialect.py`, `safety.py`
   and `news_export.py` name no engine at all, and neither does any
   consumer repo. That confinement *is* the product this repo ships (see
   `CHANGELOG.md` v1.2.0); a new `import sqlite3` anywhere else in `src/`
   is a defect, not a detail.
4. **Build & distribution**: `hatchling`, src-layout
   (`[tool.hatch.build.targets.wheel].packages = ["src/portfolio_common"]`),
   shipping `py.typed` so consumers type-check against it. **Not published
   to PyPI** — every consumer depends on it as a git dependency pinned by
   tag under `[tool.uv.sources]`, so the **git tag is the release
   artifact**. Don't introduce a publish step or a floating `main`/`master`
   dependency as a shortcut.
5. **Dev group only**: `pytest>=8.2`, `pre-commit>=4.0`, `ruff==0.16.3`,
   `mypy>=1.13` under `[dependency-groups].dev`. Pin ruff exactly
   (reproducible CI/pre-commit); range-pin the rest. There is no second
   dependency group and no optional extra — a library whose whole point is
   having no dependencies has nothing to make optional.
6. **SQLite is the only implemented backend**, and `SqliteDialect` is the
   only `Dialect`. Adding a second engine means a new `Dialect`
   implementation plus a registered `connect_url` scheme **in this repo**
   and nothing changed in any consumer — that is the contract `v1.2.0`
   bought, and it must not be paid back by leaking a second engine's name
   into a consumer. Note the one documented dent: a non-SQLite row factory
   must satisfy `RowLike` (mapping **and** positional **and** `dict(row)`
   access).
7. **Adopting a new library/framework is a constitution-level change**: add
   it to `pyproject.toml` with a rationale in the PR, and if it changes a
   rule above, amend this section (see Governance). For a *runtime*
   dependency the bar is higher still — item 2 treats `dependencies = []`
   as load-bearing, so expect the answer to be no.

## Project structure

1. **`src/portfolio_common/` is the only packaged tree.** `db/` holds the
   four engine modules — `engine.py` (connection lifecycle, pragma policy,
   ATTACH, introspection/DDL), `dialect.py` (per-engine SQL fragments),
   `safety.py` (`in_clause`/`Allowlist`), `two_store.py` (writable primary +
   read-only attached secondary) — and `news_export.py` is the single
   domain-shaped module at top level. It is also the **only** one: adding a
   second needs the argument its own docstring makes (a read genuinely
   shared by two repos that interoperate through it), not "this is DB code
   and DB code lives here."
2. **`business_folders/` is staging, not a fourth module.** It sits outside
   `src/` so `hatchling` never packages it, each subfolder is owned by
   exactly one consumer repo, and each is meant to be copied into that repo
   and then **deleted from here**. Nothing in `src/` may import from it,
   and it must never be added to the wheel's `packages` list.
3. **Tests are flat in `tests/`, one file per module**
   (`test_engine.py`, `test_dialect.py`, `test_safety.py`,
   `test_two_store.py`, `test_news_export.py`) plus `test_engine_agnostic.py`
   for the seam itself. `pytest.ini`'s `pythonpath = src` +
   `testpaths = tests` is what makes `import portfolio_common` resolve
   without an editable install — don't add `sys.path` hacks inside test
   files to route around it. `tests/` is the only place outside
   `db/engine.py` / `db/two_store.py` allowed to `import sqlite3` (it is
   testing the engine binding itself).
4. **There is no `docs/` directory, by choice.** This repo's prose lives in
   `README.md` (the public-API table and the consumer-pin instructions),
   `CHANGELOG.md` (the release and compatibility record — the thing
   consumers read before bumping a tag), each
   `business_folders/*/README.md` (per-domain adoption steps), and
   `.specify/` (spec-kit artifacts: this constitution, `SPEC.md`,
   `PLAN.md`, `TASKS.md`). A new explanation belongs in whichever of those
   already owns the topic; don't start a `docs/` tree for one file.
5. **Config lives where its tool expects it, not duplicated.** Ruff:
   `.code_quality/ruff.toml` (root `ruff.toml` only `extend`s it so plain
   `ruff check .` from the repo root resolves the same config `pre-commit`
   uses, and so the relative `per-file-ignores` globs resolve against
   `.code_quality/`). Mypy: `.code_quality/mypy.ini`. Pytest: root
   `pytest.ini`. Don't fork a second config file for a tool that has one.
6. **No `.env`, and no environment reads at all.** This library never reads
   an environment variable — resolving `DATABASE_URL` (or any other) is the
   consumer's job, and the path/URL arrives here as an argument to
   `Database.connect_url`. Don't add an `os.environ` read, a `load_dotenv`,
   or a module-level default path; that would put env-resolution policy in
   four repos' shared dependency.
7. **Naming follows the seam.** Connection mechanics → `engine.py`;
   per-engine SQL *text* → `dialect.py`; identifier/placeholder safety →
   `safety.py`; attach topology → `two_store.py`. A helper that builds SQL
   strings does not belong on `Database`, and a helper that touches a
   connection does not belong on `Dialect`.

## AI behavior

*This package runs no models:*

1. **There is no AI component in `portfolio-common`** — no model, no
   inference, no prompt, no LLM call, and no heuristic presented as one.
   Model work belongs in the consumer that owns the domain (`portfolio-nlp`
   for NLP stages, `portfolio-financial-analysis` for scoring); proposing
   one here would also mean a runtime dependency, which Technological
   stock #2 treats as load-bearing. This item exists so the absence reads
   as deliberate rather than as an omission.

*Claude Code / coding-agent conduct on this repo:*

2. **Every public name is a cross-repo contract.** Anything in
   `portfolio_common.__all__` or `portfolio_common.db.__all__` is pinned by
   tag in four other repos. Adding, changing or removing one requires a
   `CHANGELOG.md` entry that states compatibility explicitly (additive vs.
   breaking), a version bump per Code & Git #4, and — for a removal or
   redefinition — a migration note for each consumer. Never adjust a public
   signature "while in there" for a change that didn't need it.
3. **Match existing structure before introducing new structure** — check
   where a file's siblings live and follow that placement, naming, and
   import style (`from portfolio_common.db import ...`, re-export through
   `__all__`) rather than a generic layout.
4. **This constitution and `.specify/memory/SPEC.md` are the binding
   reference for planning and review** — read both before drafting a
   spec/plan, and resolve any conflict between a request and a stated
   principle or requirement by surfacing it or proposing an amendment, not
   by quietly overriding either. A local, untracked `CLAUDE.md` may carry
   situational/session notes, but it is never authoritative and must not be
   treated as a source of fact for anything either document already states.
5. **Prefer the smallest change consistent with the existing pattern**; no
   opportunistic refactors, renames, or new abstractions outside what the
   spec/task calls for. In a library four repos pin, a gratuitous rename is
   four PRs, not one.
6. **`CLAUDE.md` must always exist on disk and must never be deleted**,
   even though it is intentionally untracked (see Code & Git #8), and it
   must always carry a reference to both this constitution
   (`.specify/memory/constitution.md`) and `.specify/memory/SPEC.md`. If
   `CLAUDE.md` is missing at the start of a session, run `/init` to
   regenerate it before doing anything else; if it exists but is missing
   either reference (freshly `/init`-generated or otherwise edited), add it
   before proceeding — don't treat the reference as a one-time
   regeneration step.
7. **Ask before expanding scope this constitution doesn't cover** — a new
   public name, a runtime dependency, a second `Dialect` or `connect_url`
   scheme, a new top-level module, an environment read, or any change that
   makes an already-pinned tag behave differently for a consumer.
8. **Never move, re-point, or delete a published tag** (also Code & Git
   #10). Consumers pin to tags; a moved tag changes code under a repo that
   didn't ask for it and can't see the change. Ship a new patch release
   instead.
9. **Reconcile the architecture artifacts at the close of every
   development effort** — when a PR/feature/fix is done (merged, or ready
   to merge), update both:
   - the general, system-wide artifact — [Portfolio
     Thesis](https://claude.ai/code/artifact/d3865a63-2894-4e20-b38a-7e50cf0d4040)
     (the six-repo integrated architecture overview); and
   - the repository-specific artifact — [Portfolio
     Common](https://claude.ai/code/artifact/a1a5f985-a6b9-4dd1-8e2d-cc1f0d939e2b)
     (this repo's engine seam, module table, rollout state, gaps, and plan).

   to close whatever gaps the effort closed and reconcile the artifact's
   prose with what the code now actually does — an artifact describing a gap
   that was just fixed, or a rollout step that was just completed, is now
   wrong and must be corrected in the same pass, not left stale. A
   *partially* updated artifact is the specific failure mode to watch for
   here: one section rewritten for the current release while another still
   describes an earlier one contradicts itself (see `SPEC.md` §13 item 8).
   **Never** rename either artifact when doing this — **NEVER** change its
   title (the `<title>` tag / the name shown in the artifact gallery).
   Content, diagrams, gap lists, and plans update freely; the name is
   stable forever, independent of content changes. (See `Artifact` tool
   guidance: title changes are an explicit, separate, user-directed action,
   never a side effect of a content update.)

## Executable cmds

Canonical commands — a spec/plan should reference these, not invent new
ad-hoc invocations:

```bash
uv sync                                     # install deps (dev group)
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push

uv run pytest                               # full hermetic suite (no network, no server)
uv run pytest -q                            # as run in CI

uv run ruff check .                          # lint (config: .code_quality/ruff.toml via root pointer)
uv run ruff format --check .                 # format check
uv run mypy --config-file=.code_quality/mypy.ini src   # types (src only, as CI runs it)

uv run pre-commit run --all-files            # all of the above hooks, plus hygiene checks

# release (the tag IS the distribution channel -- see Code & Git #4/#10)
#   1. bump [project].version in pyproject.toml
#   2. add the CHANGELOG.md section, stating compatibility explicitly
#   3. merge the PR, then tag the merge commit and push the tag:
git tag vX.Y.Z && git push origin vX.Y.Z
#   4. bump [tool.uv.sources] in each consumer repo that should adopt it
```

1. **CI (`.github/workflows/ci.yml`) is the source of truth for the required
   gate order**: `uv sync` → `ruff check .` → `ruff format --check .` →
   `mypy --config-file=.code_quality/mypy.ini src` → `pytest -q`. Run the
   same four checks locally before opening a PR; don't rely on CI to catch a
   lint/type/test failure first.
2. **Note the asymmetry with consumer repos**: mypy here runs against `src`
   only, not the whole graph (`tests/` is not type-checked), and CI runs on
   `ubuntu-latest` only — there is no Windows leg today even though
   development happens on Windows (`SPEC.md` §13 item 3, `NR-007`). A local
   `uv run pytest` is therefore a *stronger* signal than CI on
   platform-sensitive code, not a weaker one.
3. **Don't hardcode a different Python/uv invocation** (bare `python`,
   `pip install`, `pytest` without `uv run`) in docs or CI — every command
   goes through `uv run` so it resolves the locked environment.

## Code & Git

1. **Formatting/linting/types are enforced, not advisory**: `ruff-check
   --fix` + `ruff-format` + `mypy` all run via `pre-commit` and again in CI.
   A `# noqa` / `# type: ignore` needs a comment saying why the finding is
   wrong for this code, not just silence — the `# noqa: S608` in
   `news_export.py` (schema name `Allowlist`-checked, `limit` bound) is the
   shape to copy.
2. **Commit messages are Conventional Commits**, enforced by the
   `commitizen` pre-commit/pre-push hooks — `type(scope): summary`, matching
   the existing history (`feat(db): ...`, `refactor!: ...`,
   `fix(financial_analysis): ...`, `chore: ...`). A `!` (or a
   `BREAKING CHANGE:` footer) is mandatory for a change that removes or
   redefines a public name.
3. **Branch off `master`, never commit to it directly.** `master` is the
   integration branch (`origin/HEAD -> origin/master`); feature/fix/docs
   work happens on a descriptively-named branch (`feat/...`, `fix/...`,
   `docs/...`, `chore/...`, `refactor/...`) opened as a PR. Keep local
   `master` fast-forwarded from `origin/master` rather than rewriting it.
4. **SemVer governs the public API of the `portfolio_common` package** — not
   a schema (schema ownership left with the repo that owns the domain at
   `v1.0.0`), and not `business_folders/` (unpackaged staging; changing or
   deleting it is not a public-API change). **MAJOR** for a removed or
   redefined public name, **MINOR** for an additive one, **PATCH** for a
   fix that changes no signature. `v1.0.0` is the reference case for a
   MAJOR done deliberately: a clean break with no compatibility shim, so a
   consumer bumping the tag gets an immediate `ImportError` rather than
   half-migrated behavior.
5. **`CHANGELOG.md` is part of the release, not documentation debt.** Every
   version gets a section that says what was added/changed/removed **and**
   states compatibility explicitly ("Additive. Every v1.2.0 signature still
   works" / "This is a clean break"). A release PR without its CHANGELOG
   section is incomplete.
6. **Pre-commit hooks are mandatory, not optional**: `check-yaml`,
   `check-case-conflict`, `debug-statements`, `detect-private-key`,
   `check-merge-conflict`, `check-added-large-files` run alongside
   ruff/mypy/commitizen — install them (see Executable cmds) rather than
   relying on remembering to run checks manually.
7. **CI must be green before merge**: the `check` job in
   `.github/workflows/ci.yml` (ruff check, ruff format --check, mypy,
   `pytest -q`) gates every push to `master` and every PR. A PR that turns
   this red does not merge until it's fixed, not suppressed.
8. **No secrets committed, and Claude/agent artifacts stay untracked.**
   `CLAUDE.md`, `.claude/`, `.superpowers/` and any other agent scratch
   output are git-ignored (`.gitignore`) — they are local session context,
   not repository content. `.specify/` is the deliberate exception: it holds
   the spec-kit constitution/specs this project versions as its source of
   truth, so it stays tracked. `detect-private-key` is a backstop, not the
   first line of defense.
9. **Leave the working tree checked out on the branch just pushed/PR'd.**
   After opening a PR, don't switch back to `master` (or anywhere else) —
   the local checkout stays on that branch so the user can review the
   actual working tree immediately. Only move off it (per item 3, always to
   a fresh branch off up-to-date `master`) when starting genuinely new work,
   or when asked to.
10. **A pushed tag is immutable.** Never `git tag -f`, never delete and
    re-push a tag, never re-point one at a new commit — four repos resolve
    their dependency through those tags and `uv` caches by tag. If a
    release was wrong, release `vX.Y.Z+1`. (The one historical wrinkle to
    know about: `v1.0.0` was tagged at the PR #7 branch tip *before* the PR
    merged, so for a while it wasn't reachable from `master`; it is now.
    Tagging ahead of a merge is not the normal path.)

## Governance

This constitution supersedes ad-hoc convention when the two conflict. A
spec or plan may not silently contradict a rule above; instead:

1. Propose the amendment as its own change (state which section, what
   changes, and why).
2. Get it reviewed the same way a code PR would be (this repo's normal
   review path) before relying on it.
3. Bump the version below per semver: **MAJOR** for a removed/redefined
   principle, **MINOR** for a new principle or materially expanded
   guidance, **PATCH** for wording/typo fixes.
4. Record the change under "Last Amended" with the date.

Compliance is expected to be checked the same way lint/type/test gates
are — a reviewer (human or agent) rejecting a PR that violates a principle
above should cite the section by name.

**Version**: 1.0.0 | **Ratified**: 2026-09-12 | **Last Amended**: 2026-09-12

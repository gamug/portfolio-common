"""Tests for portfolio_common.db.engine.Database -- the one connection
factory every domain in this project's ecosystem uses.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from portfolio_common.db import Database
from portfolio_common.db import engine as engine_module


def test_connect_always_sets_row_factory_and_busy_timeout(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        assert db.raw.row_factory is sqlite3.Row
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 30_000
    finally:
        db.close()


def test_connect_custom_busy_timeout(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", busy_timeout_ms=5_000)
    try:
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 5_000
    finally:
        db.close()


def test_connect_defaults_leave_wal_and_fk_off(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 0
    finally:
        db.close()


def test_connect_wal_true_enables_wal_and_normal_sync(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", wal=True)
    try:
        assert db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    finally:
        db.close()


def test_connect_foreign_keys_true_enforces_fk(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", foreign_keys=True)
    try:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        db.close()


def test_connect_check_same_thread_false_is_accepted(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db", wal=True, check_same_thread=False)
    try:
        db.execute("SELECT 1")
    finally:
        db.close()


def test_connect_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "t.db"
    db = Database.connect(path)
    try:
        assert path.parent.is_dir()
    finally:
        db.close()


def test_connect_create_parents_false_does_not_create(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "t.db"
    with pytest.raises(sqlite3.OperationalError):
        Database.connect(path, create_parents=False)


def test_read_only_opens_existing_file_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    setup = Database.connect(path)
    setup.execute("CREATE TABLE t (id INTEGER)")
    setup.commit()
    setup.close()

    db = Database.connect(path, read_only=True)
    try:
        assert db.raw.row_factory is sqlite3.Row
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO t (id) VALUES (1)")
    finally:
        db.close()


def test_read_only_does_not_create_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        Database.connect(path, read_only=True)


def test_execute_executemany_executescript(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER, name TEXT)")
        db.executemany("INSERT INTO t (id, name) VALUES (?, ?)", [(1, "a"), (2, "b")])
        db.commit()
        rows = db.execute("SELECT id, name FROM t ORDER BY id").fetchall()
        assert [tuple(r) for r in rows] == [(1, "a"), (2, "b")]
    finally:
        db.close()


def test_transaction_commits_on_success(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER)")
        with db.transaction():
            db.execute("INSERT INTO t (id) VALUES (1)")
        assert db.execute("SELECT id FROM t").fetchone()[0] == 1
    finally:
        db.close()


def test_transaction_rolls_back_on_exception(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "t.db")
    try:
        db.executescript("CREATE TABLE t (id INTEGER)")
        db.execute("INSERT INTO t (id) VALUES (1)")
        db.commit()
        with pytest.raises(ValueError, match="boom"), db.transaction():
            db.execute("INSERT INTO t (id) VALUES (2)")
            raise ValueError("boom")
        assert [r[0] for r in db.execute("SELECT id FROM t")] == [1]
    finally:
        db.close()


def test_subclass_connect_returns_subclass_instance(tmp_path: Path) -> None:
    class MyDatabase(Database):
        extra: str = "default"

    db = MyDatabase.connect(tmp_path / "t.db")
    try:
        assert isinstance(db, MyDatabase)
        db.extra = "custom"
        assert db.extra == "custom"
    finally:
        db.close()


# -- attach / detach ----------------------------------------------------------


def test_attach_read_only_makes_second_schema_visible(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    setup = Database.connect(other_path)
    setup.executescript("CREATE TABLE t (id INTEGER)")
    setup.execute("INSERT INTO t (id) VALUES (42)")
    setup.commit()
    setup.close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "other" in schemas
        assert db.execute("SELECT id FROM other.t").fetchone()[0] == 42
        with pytest.raises(sqlite3.OperationalError):
            db.execute("INSERT INTO other.t (id) VALUES (1)")
    finally:
        db.close()


def test_attach_then_detach_removes_schema(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    Database.connect(other_path).close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)
        db.detach("other")
        schemas = {row[1] for row in db.execute("PRAGMA database_list")}
        assert "other" not in schemas
    finally:
        db.close()


def test_attach_rejects_invalid_alias(tmp_path: Path) -> None:
    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        with pytest.raises(ValueError, match="invalid ATTACH alias"):
            db.attach(tmp_path / "other.db", "not a valid alias!")
    finally:
        db.close()


def test_attach_rejects_wal_copied_without_shm(tmp_path: Path) -> None:
    """The narrow shape this preflight actually catches: a backup/`rsync`
    that copied the database + `-wal` but not `-shm` (SQLite's own docs call
    `-shm` disposable, so tools commonly skip it) while the source was quiet
    in between writes -- a plain sequential copy, no concurrent checkpoint.
    Rejected because nothing here *proves* the two files are one consistent
    instant, even though a quiescent copy like this one happens to be fine.
    See `test_attach_does_not_catch_a_checkpoint_torn_copy` below for the
    copy shape that actually is unsafe -- and that this check misses."""
    source_path = tmp_path / "source.db"
    writer = Database.connect(source_path, wal=True)
    writer.execute("CREATE TABLE t (id INTEGER)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()
    try:
        assert Path(f"{source_path}-wal").stat().st_size > 0

        # Simulate the backup: copy the db + -wal, deliberately not -shm.
        copy_path = tmp_path / "other.db"
        shutil.copyfile(source_path, copy_path)
        shutil.copyfile(f"{source_path}-wal", f"{copy_path}-wal")
        assert not Path(f"{copy_path}-shm").exists()

        db = Database.connect(tmp_path / "main.db", uri=True)
        try:
            with pytest.raises(RuntimeError, match="wal_checkpoint"):
                db.attach(copy_path, "other", read_only=True)
        finally:
            db.close()
    finally:
        writer.close()


def test_attach_does_not_catch_a_checkpoint_torn_copy(tmp_path: Path) -> None:
    """Known limitation, documented rather than silently assumed away: this
    preflight only ever looks at `-wal` size and `-shm` presence, so it has
    no way to catch a copy that tears the **main `.db` file itself** by
    racing a checkpoint on the source -- and a checkpoint truncates `-wal`
    to empty, so the one check this function does run doesn't even fire.

    Built deterministically (no timing/sleeps, no flakiness risk): copy the
    main db file's bytes from *before* a checkpoint, force the checkpoint
    (which rewrites the whole file), then copy the bytes from *after* --
    producing a file whose header still claims the pre-checkpoint page
    count while its body is the post-checkpoint layout. That is exactly
    what an unlucky plain `cp`/`rsync` mid-checkpoint would produce.

    The result: `PRAGMA integrity_check` reports "ok", `attach()` raises
    nothing, and the attached schema has **no tables** -- silent, wrong,
    and unflagged. This is not a bug introduced by this fix; it is a gap
    in what a `-wal`/`-shm`-only heuristic can ever catch, which is why the
    docstring on `attach()` does not claim this preflight is a backup-safety
    guarantee. A caller that needs a safe copy of a live database should use
    SQLite's own backup API (`.backup` / `VACUUM INTO`), not a plain file
    copy -- this preflight cannot stand in for that."""
    source_path = tmp_path / "source.db"
    writer = Database.connect(source_path, wal=True)
    writer.execute("CREATE TABLE t (id INTEGER)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()
    try:
        pre_checkpoint_bytes = source_path.read_bytes()  # header-only page(s)

        writer.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # rewrites the whole file
        post_checkpoint_bytes = source_path.read_bytes()
        assert Path(f"{source_path}-wal").stat().st_size == 0

        # The torn copy a mid-checkpoint `cp`/`rsync` would have produced:
        # old header, new body.
        copy_path = tmp_path / "other.db"
        copy_path.write_bytes(
            pre_checkpoint_bytes + post_checkpoint_bytes[len(pre_checkpoint_bytes) :]
        )
    finally:
        writer.close()

    probe = sqlite3.connect(f"file:{copy_path.as_posix()}?mode=ro", uri=True)
    try:
        assert probe.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert probe.execute("SELECT name FROM sqlite_master").fetchall() == []
    finally:
        probe.close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(copy_path, "other", read_only=True)  # does not raise
        assert db.execute("SELECT name FROM other.sqlite_master").fetchall() == []
    finally:
        db.close()


def test_attach_allows_wal_database_held_open_by_live_writer(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    writer = Database.connect(other_path, wal=True)
    writer.execute("CREATE TABLE t (id INTEGER)")
    writer.execute("INSERT INTO t VALUES (1)")
    writer.commit()
    writer.execute("INSERT INTO t VALUES (2)")  # open write transaction
    try:
        assert Path(f"{other_path}-wal").stat().st_size > 0

        db = Database.connect(tmp_path / "main.db", uri=True)
        try:
            db.attach(other_path, "other", read_only=True)
            assert db.execute("SELECT count(*) FROM other.t").fetchone()[0] == 1
        finally:
            db.close()
    finally:
        writer.rollback()
        writer.close()


def test_attach_allows_wal_left_by_a_hard_killed_writer(tmp_path: Path) -> None:
    """`-shm` surviving is not proof a writer is still live -- a writer that
    is killed outright (OOM-killed container, `kill -9`, the real failure
    mode for the collector this fix exists for) leaves `-shm` behind too,
    same as a clean live writer does. This is deliberately *not* mocked:
    a real child process opens the database in WAL mode, commits one row,
    leaves a second row uncommitted, and is killed without ever closing --
    no checkpoint, no WAL/SHM cleanup, nothing graceful.

    `attach()` treats the survived `-shm` as "a writer has this open" and
    skips the orphaned-WAL preflight (same code path as the live-writer
    test above). That is only safe because SQLite's own read-only WAL
    recovery (3.22+) handles a genuinely orphaned WAL correctly on its own
    -- this asserts that it actually does, against this project's pinned
    Python/SQLite, rather than assuming it.
    """
    other_path = tmp_path / "other.db"
    script = (
        "import sqlite3, sys, time\n"
        "conn = sqlite3.connect(sys.argv[1], timeout=30)\n"
        "conn.execute('PRAGMA journal_mode=WAL')\n"
        "conn.execute('CREATE TABLE t (id INTEGER)')\n"
        "conn.execute('INSERT INTO t VALUES (1)')\n"
        "conn.commit()\n"
        "conn.execute('INSERT INTO t VALUES (2)')\n"  # left uncommitted
        "print('READY', flush=True)\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen(  # noqa: S603 -- fixed literal script, not untrusted input
        [sys.executable, "-c", script, str(other_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "READY"
        deadline = time.monotonic() + 5
        wal = Path(f"{other_path}-wal")
        while time.monotonic() < deadline and not (wal.exists() and wal.stat().st_size > 0):
            time.sleep(0.05)
        assert wal.stat().st_size > 0
    finally:
        proc.kill()  # no sqlite3_close, no checkpoint -- simulates a hard crash
        proc.wait(timeout=10)

    shm = Path(f"{other_path}-shm")
    assert shm.exists(), "this test's premise: a hard-killed writer leaves -shm behind"

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)
        rows = db.execute("SELECT id FROM other.t ORDER BY id").fetchall()
        assert [r[0] for r in rows] == [1]
    finally:
        db.close()


def test_attach_tolerates_wal_disappearing_during_the_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The preflight's `wal.stat()` and the writer's own checkpoint (which
    removes/empties `-wal`) can race: the writer finishes between this
    process seeing `-wal` and actually `stat()`-ing it. That should be
    treated the same as "no orphaned WAL", not raise `FileNotFoundError`."""
    other_path = tmp_path / "other.db"
    sqlite3.connect(other_path).close()

    real_stat = Path.stat

    def flaky_stat(self: Path, *args: object, **kwargs: object) -> object:
        if self.name == f"{other_path.name}-wal":
            raise FileNotFoundError(self)
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(engine_module.Path, "stat", flaky_stat)

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=True)  # must not raise
    finally:
        db.close()


def test_attach_read_write_does_not_require_uri_scheme_on_alias(tmp_path: Path) -> None:
    other_path = tmp_path / "other.db"
    Database.connect(other_path).close()

    db = Database.connect(tmp_path / "main.db", uri=True)
    try:
        db.attach(other_path, "other", read_only=False)
        db.execute("CREATE TABLE other.t (id INTEGER)")
        db.execute("INSERT INTO other.t (id) VALUES (7)")
        db.commit()
        assert db.execute("SELECT id FROM other.t").fetchone()[0] == 7
    finally:
        db.close()

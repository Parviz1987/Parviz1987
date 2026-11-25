"""2026-11-25: a long job holding the writer lock must not freeze the site's reads (the owner saw the site stop)."""
import threading
import time

from app.db import DB


def test_reads_do_not_wait_for_the_writer_lock(tmp_path):
    db = DB(tmp_path / "t.sqlite3")
    db.put("a", "1")
    held = threading.Event()

    def long_writer():
        with db.lock:                     # a long write / report holding the shared lock
            held.set()
            time.sleep(1.5)

    t = threading.Thread(target=long_writer)
    t.start()
    held.wait()
    t0 = time.time()
    assert db.get("a") == "1"             # a read goes through its own connection
    assert time.time() - t0 < 0.5
    t.join()
    db.put("a", "2")
    assert db.get("a") == "2"             # a read sees the latest committed write at once
    assert db.execute("SELECT COUNT(*) n FROM kv").fetchone()["n"] >= 1
    res = db.execute("UPDATE kv SET v='3' WHERE k='a'")
    assert res.rowcount == 1 and db.get("a") == "3"


def test_reads_from_another_thread_see_commits(tmp_path):
    db = DB(tmp_path / "t.sqlite3")
    out = []
    th = threading.Thread(target=lambda: out.append(db.get("x")))
    th.start(); th.join()
    db.put("x", "y")
    th = threading.Thread(target=lambda: out.append(db.get("x")))
    th.start(); th.join()
    assert out == [None, "y"]

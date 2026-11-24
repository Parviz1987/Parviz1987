import threading

from app.db import DB


def test_reads_from_many_threads_never_mix(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    db.execute("CREATE TABLE a (x INTEGER, y TEXT)")
    db.executemany("INSERT INTO a VALUES(?,?)", [(i, str(i)) for i in range(2000)])
    errors = []

    def reader():
        try:
            for _ in range(200):
                rows = db.execute("SELECT x, y FROM a WHERE x < 50 ORDER BY x").fetchall()
                assert [r["x"] for r in rows] == list(range(50)) and rows[3]["y"] == "3"
        except Exception as e:      # noqa: BLE001
            errors.append(repr(e))

    def writer():
        for i in range(200):
            db.execute("SELECT COUNT(*) n FROM a").fetchone()
            db.execute("INSERT INTO a VALUES(?,?)", (10_000 + i, "w"))
    ts = [threading.Thread(target=reader) for _ in range(4)] + [threading.Thread(target=writer)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errors == []
    assert sum(1 for _ in db.iterate("SELECT x FROM a")) == 2200
    assert db.execute("INSERT INTO a VALUES(1, 'z')").rowcount == 1

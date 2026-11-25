from app import trust
from app.db import DB


def test_lights():
    assert trust.light(0.91, 22, 0.48)["light"] == "yellow"
    assert trust.light(0.54, 56, 0.67)["light"] == "red"
    assert trust.light(0.52, 100, 0.50)["light"] == "white"
    assert trust.light(0.9, 5, 0.5)["light"] == "wait"
    assert trust.light(0.5, 500, 0.5, proven=True)["light"] == "green"


def test_build_empty(tmp_path):
    d = trust.build(DB(str(tmp_path / "t.db")))
    assert "etibarlı" in d["head"] and isinstance(d["items"], list)

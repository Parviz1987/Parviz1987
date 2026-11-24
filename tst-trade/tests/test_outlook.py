from app import outlook
from app.db import DB


def test_outlook_empty_db_is_honest(tmp_path):
    db = DB(str(tmp_path / "t.db"))
    d = outlook.all_metals(db)
    assert len(d["metals"]) == 4
    m = d["metals"][0]
    assert m["lean"] == "aydın deyil" and m["vote"] == {"up": 0, "down": 0, "up_names": [], "down_names": []}
    assert "strateq" not in m and "range" not in m

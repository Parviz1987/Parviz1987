"""The agents hub: one place every agent reports to; the panel reads it (snapshot, events, live WebSocket)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app import auth
from app.activity import NODES, Hub, Stages
from tests.test_core import _app, mem


def test_report_updates_state_and_store():
    hub = Hub(mem())
    hub.report("history", "working", "W1 Capital", 0.3, "XAU")
    hub.report("nope", "working")            # not on the map: ignored
    hub.report("judge", "bogus")             # unknown status: ignored
    snap = hub.snapshot()
    assert snap["state"]["history"]["stage"] == "W1 Capital" and snap["state"]["history"]["progress"] == 0.3
    assert len(snap["nodes"]) == len(NODES)
    with Stages(hub, "strateq") as s:
        s.stage("W2 Beyin", 0.5)
    assert hub.snapshot()["state"]["strateq"]["status"] == "done"
    with pytest.raises(ValueError):
        with Stages(hub, "reader"):
            raise ValueError("x")
    assert hub.snapshot()["state"]["reader"]["status"] == "error"
    evs = hub.events(0)
    assert [e["task"] for e in evs][:1] == ["history"] and len(evs) == 6


def test_every_parent_is_on_the_map():
    for k, (_, _, parent, _, _) in NODES.items():
        assert parent is None or parent in NODES


def _owner(tmp_path):
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    return c


def test_agents_page_api_and_websocket(tmp_path):
    anon = TestClient(_app(tmp_path))
    assert anon.get("/api/agents/events").status_code == 401
    with pytest.raises(WebSocketDisconnect):
        with anon.websocket_connect("/ws/agents") as ws:
            ws.receive_text()
    c = _owner(tmp_path)
    assert c.get("/agents").status_code == 200
    d = c.get("/api/agents/events?hours=1").json()
    assert len(d["nodes"]) == len(NODES) and isinstance(d["events"], list)
    top = c.get("/api/agents/top").json()
    assert "Qiymət" in top["sync"] and isinstance(top["limits"], list)
    with c.websocket_connect("/ws/agents", headers={"origin": "http://testserver"}) as ws:
        snap = ws.receive_json()
        assert snap["type"] == "snapshot" and "orch" in snap["state"]
    with pytest.raises(WebSocketDisconnect):          # a foreign page cannot open the owner's stream
        with c.websocket_connect("/ws/agents", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_text()


def test_analysts_api_lists_every_desk_with_weights(tmp_path):
    c = _owner(tmp_path)
    d = c.get("/api/analysts?symbol=XAG").json()
    assert {x["horizon"] for x in d["desks"]} >= {"1h", "1mo"}
    one = next(x for x in d["desks"] if x["horizon"] == "1mo")
    assert {"fundamental", "terazi"} <= {r["method"] for r in one["rows"]}
    assert not {"season", "jewel"} & {r["method"] for r in one["rows"]}          # retired 27.11 (plan 3.2)
    assert all("weight" in r for r in one["rows"]) and d["brains"] == []
    assert c.get("/api/analysts?symbol=BTC").status_code == 400

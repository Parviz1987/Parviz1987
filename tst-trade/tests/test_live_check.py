"""Databento live right (owner 27.11 23:00: «payment did not go through, it gives $125 credit»): asked at the live
gateway with its challenge handshake; the answer «success=0|error=…» is shown in Databento's own words."""
import asyncio
import hashlib

from app import orderflow

KEY = "db-ABCDEFGHIJKLMNOPQRSTUVWXYZ12"


class _R:
    def __init__(self, lines):
        self.lines = [l.encode() for l in lines]

    async def readline(self):
        return self.lines.pop(0) if self.lines else b""


class _W:
    def __init__(self):
        self.sent = b""

    def write(self, b):
        self.sent += b

    async def drain(self):
        pass

    def close(self):
        pass


def _run(monkeypatch, reply):
    w = _W()

    async def fake_open(host, port):
        assert host == "glbx-mdp3.lsg.databento.com" and port == 13000
        return _R(["lsg_version=0.9.0\n", "cram=abc123\n", reply]), w
    monkeypatch.setattr(orderflow.asyncio, "open_connection", fake_open)
    return asyncio.run(orderflow.live_check(KEY)), w.sent.decode()


def test_the_handshake_answer_and_a_granted_live_right(monkeypatch):
    (ok, text), sent = _run(monkeypatch, "success=1|session_id=42\n")
    want = hashlib.sha256(f"abc123|{KEY}".encode()).hexdigest() + "-" + KEY[-5:]
    assert ok is True and "VAR" in text
    assert sent == f"auth={want}|dataset=GLBX.MDP3|encoding=dbn|ts_out=0\n" and KEY not in sent


def test_a_refused_live_right_is_shown_in_databentos_words(monkeypatch):
    (ok, text), _ = _run(monkeypatch, "success=0|error=No live license for dataset GLBX.MDP3\n")
    assert ok is False and "YOXDUR" in text and "No live license" in text


def test_an_unreachable_gateway_is_not_called_refused(monkeypatch):
    async def fail(host, port):
        raise OSError("no route")
    monkeypatch.setattr(orderflow.asyncio, "open_connection", fail)
    ok, text = asyncio.run(orderflow.live_check(KEY))
    assert ok is None and "çatmaq olmadı" in text

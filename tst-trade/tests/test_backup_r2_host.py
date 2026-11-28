"""R2 (owner 27.11 21:05): Cloudflare shows a «HTTPS» link, the form asked for account_id — the link pasted there gave
«ConnectError». Both the link and the bare id now give the same address; a wrong value is named in plain words."""
import asyncio

import httpx

from app import backup

REAL_CLIENT = httpx.AsyncClient

ID = "0123456789abcdef0123456789abcdef"


def test_the_link_and_the_bare_id_give_the_same_address():
    for v in (ID, f"https://{ID}.r2.cloudflarestorage.com", f"https://{ID}.r2.cloudflarestorage.com/tst-backup",
              f" {ID}.r2.cloudflarestorage.com "):
        assert backup._host(v) == f"{ID}.r2.cloudflarestorage.com"
    assert backup._host(f"https://{ID}.eu.r2.cloudflarestorage.com") == f"{ID}.eu.r2.cloudflarestorage.com"
    url, _ = backup._headers({"account_id": f"https://{ID}.r2.cloudflarestorage.com", "access_key_id": "a",
                              "secret_access_key": "b", "bucket": "x"}, "HEAD", "/x", "e")
    assert url == f"https://{ID}.r2.cloudflarestorage.com/x"


def test_a_wrong_account_id_is_named_without_a_network_call():
    ok, msg = asyncio.run(backup.check({"account_id": "some-token-value", "access_key_id": "a",
                                        "secret_access_key": "b", "bucket": "x"}))
    assert ok is False and "account_id" in msg and "some-token" not in msg
    assert backup._id_problem(f"https://{ID}.eu.r2.cloudflarestorage.com") is None


def _fake(monkeypatch, answers):
    """answers: {(method, path): (status, text)}; every call is recorded."""
    calls = []

    def handler(req):
        key = (req.method, req.url.path)
        calls.append(key)
        st, text = answers.get(key, (404, ""))
        return httpx.Response(st, text=text)
    monkeypatch.setattr(backup.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=httpx.MockTransport(handler)))
    return calls


CREDS = {"access_key_id": "test-access-key-0001", "secret_access_key": "test-secret-key-0002", "account_id": f"https://{ID}.r2.cloudflarestorage.com"}


def test_an_empty_bucket_box_uses_the_only_bucket_the_key_sees(monkeypatch):
    _fake(monkeypatch, {("GET", "/"): (200, "<ListAllMyBucketsResult><Buckets><Bucket><Name>my-copies</Name>"
                                           "</Bucket></Buckets></ListAllMyBucketsResult>"),
                        ("PUT", "/my-copies/backups/yoxlama.txt"): (200, "")})
    ok, msg, bucket = asyncio.run(backup.check_fix({**CREDS, "bucket": ""}))
    assert ok and bucket == "my-copies" and "yeganə" in msg


def test_a_missing_bucket_is_created_and_a_forbidden_one_is_explained(monkeypatch):
    calls = _fake(monkeypatch, {("GET", "/"): (200, "<ListAllMyBucketsResult><Buckets/></ListAllMyBucketsResult>"),
                                ("PUT", "/tst-backup"): (200, ""), ("PUT", "/tst-backup/backups/yoxlama.txt"): (200, "")})
    ok, msg, bucket = asyncio.run(backup.check_fix({**CREDS, "bucket": "tst-backup"}))
    assert ok and bucket == "tst-backup" and "yaratdı" in msg and ("HEAD", "/tst-backup") in calls
    _fake(monkeypatch, {("GET", "/"): (403, ""), ("PUT", "/tst-backup"): (403, "")})
    ok, msg, bucket = asyncio.run(backup.check_fix(CREDS))
    assert not ok and bucket is None and "Create bucket" in msg


def test_admin_keeps_the_bucket_the_check_found(monkeypatch):
    from app.db import DB
    from app.keys import KeyStore, check
    db = DB(":memory:")
    ks = KeyStore(db, "s" * 64)
    ks.set("r2", {**CREDS, "bucket": ""})                              # the bucket box may stay empty
    _fake(monkeypatch, {("GET", "/"): (200, "<Name>tst-backup</Name><Name>other</Name>"),
                        ("PUT", "/tst-backup/backups/yoxlama.txt"): (200, "")})
    res = asyncio.run(check(ks, "r2"))
    assert res["ok"] and "tst-backup" in res["message"] and ks.get("r2")["bucket"] == "tst-backup"


def test_values_pasted_into_the_wrong_boxes_are_put_in_their_own(monkeypatch):
    """27.11 22:00: the 64-character Secret Access Key was pasted into the HTTPS box."""
    sec, acc = "f" * 64, "a" * 32
    mixed = {"access_key_id": f"https://{ID}.r2.cloudflarestorage.com", "secret_access_key": acc, "account_id": sec,
             "bucket": ""}
    n = backup.normalize(mixed)
    assert n["account_id"].startswith("https://") and n["secret_access_key"] == sec and n["access_key_id"] == acc
    same = {"access_key_id": acc, "secret_access_key": "short", "account_id": sec}
    assert backup.normalize(same) == same                          # cannot be told apart: left as it is
    _fake(monkeypatch, {("HEAD", "/tst-backup"): (200, ""), ("PUT", "/tst-backup/backups/yoxlama.txt"): (200, "")})
    from app.db import DB
    from app.keys import KeyStore, check
    ks = KeyStore(DB(":memory:"), "s" * 64)
    ks.set("r2", {**mixed, "bucket": "tst-backup"})
    res = asyncio.run(check(ks, "r2"))
    assert res["ok"] and ks.get("r2")["account_id"].startswith("https://") and ks.get("r2")["secret_access_key"] == sec


def test_a_read_only_token_is_not_called_working(monkeypatch):
    """27.11: the owner's token was «Object Read only»: the bucket is visible but the night copy could not be written."""
    calls = _fake(monkeypatch, {("HEAD", "/tst-backup"): (200, ""), ("PUT", "/tst-backup/backups/yoxlama.txt"): (403, "")})
    ok, msg, bucket = asyncio.run(backup.check_fix({**CREDS, "bucket": "tst-backup"}))
    assert not ok and "yalnız oxuya" in msg and "Read & Write" in msg and bucket == "tst-backup"
    _fake(monkeypatch, {("HEAD", "/tst-backup"): (200, ""), ("PUT", "/tst-backup/backups/yoxlama.txt"): (200, ""),
                        ("DELETE", "/tst-backup/backups/yoxlama.txt"): (204, "")})
    ok, msg, _ = asyncio.run(backup.check_fix({**CREDS, "bucket": "tst-backup"}))
    assert ok and "yazma sınağı" in msg

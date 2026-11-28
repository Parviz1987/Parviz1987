"""R2 (owner 27.11 21:05): Cloudflare shows a «HTTPS» link, the form asked for account_id — the link pasted there gave
«ConnectError». Both the link and the bare id now give the same address; a wrong value is named in plain words."""
import asyncio

from app import backup

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

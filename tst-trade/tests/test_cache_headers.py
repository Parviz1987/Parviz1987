from fastapi.testclient import TestClient

from app import auth
from tests.test_core import _app


def test_pages_and_static_files_are_revalidated_so_a_deploy_is_seen_at_once(tmp_path):
    # seen 2026-11-26: the server ran the new layout, the owner's browser kept showing the old one: static files and
    # pages had no Cache-Control, so the browser reused its copy for hours without asking the server
    c = TestClient(_app(tmp_path))
    r = c.post("/login", data={"password": "pw"}, follow_redirects=False)
    c.cookies.set(auth.COOKIE, r.cookies[auth.COOKIE])
    for path in ("/static/app.css", "/static/nav.js", "/static/panel.js", "/", "/fundamental", "/admin", "/login"):
        h = c.get(path).headers
        assert "no-cache" in h.get("cache-control", ""), path
    assert "no-cache" in c.get("/sw.js").headers.get("cache-control", "")
    # unchanged files still answer 304 to a revalidation: no-cache costs a short request, not the whole file
    first = c.get("/static/app.css")
    again = c.get("/static/app.css", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304

"""Nəticə izi: if this test fails, a change altered how results are computed. That is not a bug by itself — it is a
decision for the owner: explain what changes and why, get his «okey» in the chat, then update tests/fingerprint.json
(a protected file: its commit needs the line «Sahib-təsdiqi: ...»). Regenerate with:
    python -c "import json,tests.fingerprint_lib as f; d=f.compute(); print(json.dumps({'digest': f.digest(d), 'values': d}, indent=1, sort_keys=True, default=str))" > tests/fingerprint.json
"""
import json
from pathlib import Path

from tests import fingerprint_lib as fp


def test_results_fingerprint_is_unchanged():
    want = json.loads((Path(__file__).parent / "fingerprint.json").read_text())
    got = fp.compute()
    if fp.digest(got) != want["digest"]:
        diff = {k: {"indi": got.get(k), "əvvəl": want["values"].get(k)} for k in set(got) | set(want["values"])
                if json.dumps(got.get(k), sort_keys=True, default=str) != json.dumps(want["values"].get(k), sort_keys=True,
                                                                                     default=str)}
        raise AssertionError("NƏTİCƏ İZİ DƏYİŞDİ — sahibdən izahla soruş: " + json.dumps(diff, ensure_ascii=False,
                                                                                         default=str)[:1500])

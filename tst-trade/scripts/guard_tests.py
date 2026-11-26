"""Testlərin qoruyucusu (owner 2026-11-26, plan step 3): a change between two commits is RED when it weakens the
tests or touches the guarded numbers — unless one of its commits carries a line «Sahib-təsdiqi: ...» (written only
after the owner's «okey» in the chat). Run by GitHub Actions on every push; also usable by hand:
    python scripts/guard_tests.py <base-commit> [<head-commit>]
Red when: a test file is deleted; the number of tests falls; a skip / xfail is added; a test file loses assert lines;
a guarded constant changes (Judge-adjacent learning rates and floors, router limits, the conductor's fixed settings,
the cost-to-trade table); the results fingerprint file changes."""
import re
import subprocess
import sys

GUARDED = {   # file -> constant names whose value must not change without the owner
    "tst-trade/app/learning.py": ["ETA", "FLOOR", "LESSONS_OFF", "BANDS"],
    "tst-trade/app/llmrouter.py": ["MAX_CALLS", "OFF_RETRY"],
    "tst-trade/app/conductor.py": ["ETA_C", "ALPHA", "SHRINK_N", "ABSTAIN", "STATES", "SHOCK_PCT", "TREND_Z"],
    "tst-trade/app/unified.py": ["LR", "L2", "SCALE"],
    "tst-trade/app/brains.py": ["SPARE"],
}
FINGERPRINT = "tst-trade/tests/fingerprint.json"


def git(*a) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=False).stdout


def show(rev: str, path: str) -> str:
    return git("show", f"{rev}:{path}")


def consts(src: str, names: list[str]) -> dict:
    out = {}
    for n in names:
        m = re.search(rf"^(?:{n}(?:\s*,\s*\w+)*|\w+(?:\s*,\s*\w+)*,\s*{n}(?:\s*,\s*\w+)*)\s*(?::[^=]+)?=\s*(.+)$", src, re.M)
        out[n] = m.group(0).strip() if m else None
    return out


def main(base: str, head: str = "HEAD") -> int:
    if not base or set(base) == {"0"}:
        print("no base commit: nothing to compare")
        return 0
    msgs = git("log", "--format=%B", f"{base}..{head}")
    approved = bool(re.search(r"^Sahib-təsdiqi:", msgs, re.M))
    red = []
    files = [x for x in git("diff", "--name-status", base, head).splitlines() if x.strip()]
    for line in files:
        st, *paths = line.split("\t")
        path = paths[-1]
        if st.startswith("D") and re.search(r"tests/test_.*\.py$", paths[0]):
            red.append(f"test faylı silinib: {paths[0]}")
        if not path.endswith(".py") or "/tests/" not in path or st.startswith("D"):
            continue
        old, new = show(base, paths[0]), show(head, path)
        n_old, n_new = len(re.findall(r"^def test_", old, re.M)), len(re.findall(r"^def test_", new, re.M))
        if n_new < n_old:
            red.append(f"testlərin sayı azalıb: {path} ({n_old} → {n_new})")
        for pat in (r"pytest\.mark\.skip", r"pytest\.mark\.xfail", r"pytest\.skip\(", r"pytest\.xfail\("):
            if len(re.findall(pat, new)) > len(re.findall(pat, old)):
                red.append(f"test atlanır ({pat.replace(chr(92), '')}): {path}")
        if len(re.findall(r"^\s*assert\b", new, re.M)) < len(re.findall(r"^\s*assert\b", old, re.M)):
            red.append(f"yoxlama sətirləri azalıb: {path}")
    changed = {x.split("\t")[-1] for x in files}
    for path, names in GUARDED.items():
        if path in changed:
            a, b = consts(show(base, path), names), consts(show(head, path), names)
            for n in names:
                if a.get(n) != b.get(n):
                    red.append(f"qorunan rəqəm dəyişib: {path} {n}: {a.get(n)} → {b.get(n)}")
    if FINGERPRINT in changed:
        red.append("nəticə izi dəyişib (tests/fingerprint.json)")
    if not red:
        print("qoruyucu: yaşıl")
        return 0
    print("\n".join(("ℹ️ " if approved else "❌ ") + r for r in red))
    if approved:
        print("sahib təsdiqi var («Sahib-təsdiqi:»): keçir")
        return 0
    print("Sahibin çatdakı «okey»i olmadan bu dəyişiklik qəbul olunmur.")
    return 1


if __name__ == "__main__":
    sys.exit(main(*(sys.argv[1:3])))

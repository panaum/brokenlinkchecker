"""Single-enqueue enforcement (ARCHITECTURE.md v7 §8.1 / Gate 0B): nothing but
jobs.py may create rows in the `jobs` table. Business logic enqueues via one
function; it never touches the table directly. This test fails the build if any
other module inserts/upserts into `jobs`."""
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ALLOWED = {"jobs.py"}

PATTERNS = [
    re.compile(r"""\.table\(\s*["']jobs["']\s*\)\s*\.\s*(insert|upsert)\b"""),
    re.compile(r"""insert\s+into\s+jobs\b""", re.I),
]


def test_only_jobs_module_writes_new_jobs():
    offenders = []
    for py in BACKEND.glob("*.py"):
        if py.name in ALLOWED:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for pat in PATTERNS:
            for m in pat.finditer(text):
                offenders.append(f"{py.name}: {m.group(0)!r}")
    assert not offenders, (
        "Only jobs.enqueue() may create rows in `jobs` (v7 §8.1). Offenders: "
        + "; ".join(offenders))

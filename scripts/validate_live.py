#!/usr/bin/env python
"""
Live validation of builder detection + dead-CTA classification against real,
production pages.

Run by hand — NOT in CI. Live sites change without notice, rate-limit headless
browsers, and would make the suite flaky.

    pip install -r scripts/requirements.txt && playwright install chromium

    python scripts/validate_live.py                 # full pipeline (scrape + HTTP check)
    python scripts/validate_live.py --skip-http     # scrape + detect only (fast)
    python scripts/validate_live.py --url https://example.com

Success criteria (printed at the end, and reflected in the exit code):
  1. The expected builder is detected on every URL that declares one.
  2. HIGH-confidence dead CTAs are ~0 on these known-good production pages.
     Each one found is listed with its reason for human review. Some may be
     genuinely dead — that is fine — but any page with >3 is treated as a
     false-positive flood and fails the run.
"""
import argparse
import asyncio
import os
import sys
import traceback

# The report uses box-drawing characters and scraped anchor text; a Windows
# console defaults to cp1252 and would raise UnicodeEncodeError mid-table.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Make backend/ importable (scraper, checker, dead_cta_detector, models …).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "backend"))

import yaml  # noqa: E402

from scraper import _scrape_sync  # noqa: E402
from checker import check_all_links  # noqa: E402

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

URLS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validation_urls.yaml")

NO_EXPECTATION = "_no_expectation"
FLOOD_THRESHOLD = 3
MAX_BROKEN_SHOWN = 15


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline
# ─────────────────────────────────────────────────────────────────────────────
# checker.SEMAPHORE and checker._domain_locks are module-level asyncio
# primitives: they bind to the first event loop that touches them. The app has
# exactly one loop, but this script scans many URLs, so it must reuse a single
# loop for every check — asyncio.run() per URL would bind the semaphore to a
# dead loop and fail every URL after the first.
_LOOP = None


def _get_loop():
    global _LOOP
    if _LOOP is None:
        _LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_LOOP)
    return _LOOP


def _check_links(links):
    """Run the async HTTP checker over the scraped links; return LinkResults."""
    async def run():
        out = []
        async for _, result in check_all_links(links):
            out.append(result)
        return out

    # Playwright's sync API cannot run inside a running loop, so the loop is
    # only ever driven here, between scrapes.
    return _get_loop().run_until_complete(run())


def scan(url: str, skip_http: bool) -> dict:
    """Full Playwright scrape + detection (+ optional HTTP check) for one URL."""
    links, builders = _scrape_sync(url)
    placements = sum(l.occurrences for l in links)

    # With HTTP on, classify from the checked results: that folds in both the
    # detector's dead CTAs and links whose #fragment is missing on the target
    # page. With HTTP off, only the detector's verdict is available.
    rows = links if skip_http else _check_links(links)

    high = [r for r in rows if r.bucket == "dead_cta" and r.confidence == "high"]
    medium = [r for r in rows if r.bucket == "dead_cta" and r.confidence == "medium"]
    unverifiable = [r for r in rows if r.bucket == "unverifiable"]
    broken = [r for r in rows if r.bucket == "broken"] if not skip_http else []

    return {
        "url": url,
        "builders": builders,
        "total_links": len(links),
        "placements": placements,
        "broken": broken,
        "high": high,
        "medium": medium,
        "unverifiable": unverifiable,
        "skip_http": skip_http,
        "error": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Reporting
# ─────────────────────────────────────────────────────────────────────────────
def _truncate(s: str, n: int) -> str:
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def print_table(rows: list) -> None:
    header = f"{'URL':<34} {'DETECTED BUILDER(S)':<26} {'BROKEN':>6} {'DEAD CTA (H/M)':>15} {'UNVERIF':>8}"
    print("\n" + "=" * len(header))
    print(header)
    print("=" * len(header))
    for r in rows:
        if r["error"]:
            print(f"{_truncate(r['url'], 33):<34} {'!! ' + _truncate(r['error'], 22):<26} {'-':>6} {'-':>15} {'-':>8}")
            continue
        builders = ", ".join(r["builders"]) or "(none)"
        broken = "-" if r["skip_http"] else str(len(r["broken"]))
        dead = f"{len(r['high'])}/{len(r['medium'])}"
        print(
            f"{_truncate(r['url'], 33):<34} {_truncate(builders, 25):<26} "
            f"{broken:>6} {dead:>15} {len(r['unverifiable']):>8}"
        )
    print("=" * len(header))


def print_details(rows: list) -> None:
    for r in rows:
        if r["error"]:
            continue
        flagged = r["high"] + r["medium"] + r["broken"]
        if not flagged:
            continue
        print(f"\n── {r['url']}  ({r['total_links']} unique links, {r['placements']} placements)")
        for l in r["high"]:
            why = l.reason or getattr(l, "error", "") or ""
            print(f"   [HIGH  dead_cta] {_truncate(l.anchor_text, 40):<42} {_truncate(why, 90)}")
        for l in r["medium"]:
            why = l.reason or getattr(l, "error", "") or ""
            print(f"   [MED   dead_cta] {_truncate(l.anchor_text, 40):<42} {_truncate(why, 90)}")
        for l in r["broken"][:MAX_BROKEN_SHOWN]:
            status = l.status_code if l.status_code is not None else "—"
            print(f"   [BROKEN {str(status):>3}   ] {_truncate(l.anchor_text, 40):<42} {_truncate(l.url, 90)}")
        # Never truncate silently — a hidden cap reads as "that was all of them".
        hidden = len(r["broken"]) - MAX_BROKEN_SHOWN
        if hidden > 0:
            print(f"   ... and {hidden} more broken link(s) not shown")


def evaluate(rows: list, expectations: dict) -> bool:
    """Print success criteria; return True if the run passes."""
    print("\n" + "─" * 78)
    print("SUCCESS CRITERIA")
    print("─" * 78)

    ok = True

    # 1. Builder detection
    print("\n1) Builder detected where expected")
    for r in rows:
        expected = expectations.get(r["url"])
        if not expected:
            continue
        if r["error"]:
            print(f"   ?  {r['url']}: could not scan ({r['error']})")
            ok = False
            continue
        # Profile names may be more specific than the expectation
        # (e.g. "HubSpot" is expected, "HubSpot CMS" is the profile name).
        hit = any(b == expected or b.startswith(expected) for b in r["builders"])
        mark = "OK" if hit else "!!"
        if not hit:
            ok = False
        print(f"   {mark} {r['url']}: expected {expected!r}, detected {r['builders'] or '(none)'}")

    # 2. High-confidence dead CTAs on known-good production pages
    print("\n2) HIGH-confidence dead CTAs on known-good production pages (want ~0)")
    total_high = 0
    for r in rows:
        if r["error"]:
            continue
        n = len(r["high"])
        total_high += n
        if n == 0:
            continue
        flood = n > FLOOD_THRESHOLD
        if flood:
            ok = False
        tag = "!! FLOOD" if flood else "review"
        print(f"   {tag}: {r['url']} -> {n} high-confidence flag(s)")
        for l in r["high"]:
            why = l.reason or getattr(l, "error", "") or ""
            print(f"        - {_truncate(l.anchor_text, 40):<42} {_truncate(why, 88)}")
        if flood:
            print(f"        ^ >{FLOOD_THRESHOLD} high-confidence flags. Treat as a bug: add the")
            print("          offending pattern as a fixture + test, extend the profile hints.")

    if total_high == 0:
        print("   OK  no high-confidence dead CTAs anywhere")

    print("\n" + "─" * 78)
    print("RESULT:", "PASS" if ok else "FAIL")
    print("─" * 78)
    return ok


# ─────────────────────────────────────────────────────────────────────────────
def load_targets(path: str) -> tuple:
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    targets, expectations = [], {}
    for builder, urls in data.items():
        for url in urls or []:
            targets.append(url)
            if builder != NO_EXPECTATION:
                expectations[url] = builder
    return targets, expectations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", help="scan this URL instead of the YAML targets")
    ap.add_argument("--skip-http", action="store_true", help="skip HTTP checking of links (fast)")
    ap.add_argument("--urls-file", default=URLS_FILE)
    args = ap.parse_args()

    if args.url:
        targets, expectations = args.url, {}
    else:
        targets, expectations = load_targets(args.urls_file)

    if not targets:
        print("No targets configured.")
        return 1

    print(f"Validating {len(targets)} URL(s){' (scrape + detect only)' if args.skip_http else ''}…")

    rows = []
    for i, url in enumerate(targets, 1):
        print(f"  [{i}/{len(targets)}] {url}", flush=True)
        try:
            rows.append(scan(url, args.skip_http))
        except Exception as e:  # live sites: never let one bad page kill the run
            traceback.print_exc(limit=1)
            rows.append({
                "url": url, "builders": [], "total_links": 0, "broken": [],
                "high": [], "medium": [], "unverifiable": [],
                "skip_http": args.skip_http, "error": f"{type(e).__name__}: {e}",
            })

    print_table(rows)
    print_details(rows)
    passed = evaluate(rows, expectations)

    if _LOOP is not None:
        _LOOP.close()
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

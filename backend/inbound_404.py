"""Inbound-404 triage — re-rank dead-URL triage by MEASURED visitor demand.

Import real hit data (GSC crawl errors = Googlebot demand, or server 404 logs =
human demand), normalize + dedupe-sum, then rank the measured tier ABOVE the
synthetic (estimated) tier. Never blends the two into one opaque number.

Honest numbers (absolute): hit language applies ONLY to URLs the import covers.
A site with no import ranks byte-identical to before (rerank returns findings in
their original order).

Reuses the existing URL normalizer (diffing.normalize_url — strips tracking
params, preserves meaningful query strings) and the defensive CSV helpers
(ads_import).
"""
from datetime import datetime, timezone

from diffing import normalize_url
from ads_import import _sniff_rows, _norm as _hnorm

# ── Demand bands — the ONE documented place. Measured hits → tier. ──
CRITICAL_DEMAND = 100      # ≥100 measured hits
HIGH_DEMAND = 20          # 20–99
STALE_DAYS = 60

# Column synonyms (fuzzy, lower-cased contains).
_URL_KEYS = ("url", "page", "address", "not found", "final url", "path", "request")
_HITS_KEYS = ("hits", "count", "requests", "pageviews", "page views", "sessions", "visits", "occurrences")
_REF_KEYS = ("referrer", "referer", "source", "from", "referring")
_DATE_KEYS = ("last crawled", "last crawl", "discovered", "date", "detected")


def _match_col(headers, keys):
    normed = [_hnorm(h) for h in headers]
    for i, h in enumerate(normed):
        if h in keys:
            return i
    for i, h in enumerate(normed):
        if any(k in h for k in keys):
            return i
    return -1


def _parse_hits(raw):
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    try:
        return max(0, int(float(s)))
    except ValueError:
        return None


def parse_404_csv(text, source_hint=""):
    """Parse a GSC crawl-errors export OR a server 404-log export. Returns
    {records, source, count, total_hits, skipped, warnings}. Deduped by
    normalized URL, hits summed, referrers merged."""
    if not text or not str(text).strip():
        return _empty("The file is empty.")
    rows = list(_sniff_rows(text))
    if not rows:
        return _empty("No readable rows found.")

    header_idx, url_col = -1, -1
    for i, row in enumerate(rows[:15]):
        c = _match_col(row, _URL_KEYS)
        if c != -1:
            header_idx, url_col = i, c
            break
    if header_idx == -1:
        return _empty("Couldn't find a URL column. Export with the dead-URL/page column included.")

    headers = rows[header_idx]
    hits_col = _match_col(headers, _HITS_KEYS)
    ref_col = _match_col(headers, _REF_KEYS)
    date_col = _match_col(headers, _DATE_KEYS)

    # Source: an explicit hit/count column → server log (human demand); otherwise
    # a crawl-errors export → Googlebot demand (each row = one crawl error).
    source = source_hint or ("server_log" if hits_col != -1 else "gsc")

    merged = {}
    skipped = 0
    for row in rows[header_idx + 1:]:
        if url_col >= len(row):
            skipped += 1
            continue
        raw_url = (row[url_col] or "").strip().strip('"')
        if not raw_url or raw_url in ("-", "--"):
            skipped += 1
            continue
        if not raw_url.lower().startswith(("http://", "https://")):
            if "." in raw_url and "/" in raw_url:
                raw_url = "https://" + raw_url
            elif raw_url.startswith("/"):
                # a path-only log line — keep as a relative key
                pass
            else:
                skipped += 1
                continue
        key = normalize_url(raw_url) if raw_url.startswith("http") else raw_url.rstrip("/")
        hits = _parse_hits(row[hits_col]) if 0 <= hits_col < len(row) else None
        if hits is None:
            hits = 1                      # GSC crawl-error row = one bot hit
        ref = (row[ref_col].strip() if 0 <= ref_col < len(row) else "")
        rec = merged.setdefault(key, {"url_normalized": key, "hits": 0, "top_referrers": [], "last_seen": None})
        rec["hits"] += hits
        if ref and ref not in rec["top_referrers"] and len(rec["top_referrers"]) < 5:
            rec["top_referrers"].append(ref)
        if 0 <= date_col < len(row) and row[date_col].strip():
            rec["last_seen"] = row[date_col].strip()

    records = sorted(merged.values(), key=lambda r: -r["hits"])
    warnings = []
    if source == "gsc":
        warnings.append("No hit counts found — treating this as Googlebot crawl demand (bot, not human visits).")
    if not records:
        warnings.append("No valid dead URLs found in the file.")
    return {"records": records, "source": source, "count": len(records),
            "total_hits": sum(r["hits"] for r in records), "skipped": skipped, "warnings": warnings}


def _empty(msg):
    return {"records": [], "source": "", "count": 0, "total_hits": 0, "skipped": 0, "warnings": [msg]}


def demand_tier(hits):
    if hits >= CRITICAL_DEMAND:
        return "critical-demand"
    if hits >= HIGH_DEMAND:
        return "high-demand"
    return "noted"


def _sev_from_hits(hits):
    if hits >= CRITICAL_DEMAND:
        return "critical"
    if hits >= HIGH_DEMAND:
        return "high"
    return "medium"


def is_stale(imported_at, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        d = datetime.fromisoformat(str(imported_at).replace("Z", "+00:00"))
        d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        return (now - d).days >= STALE_DAYS
    except Exception:
        return False


def _get(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def rerank(findings, demand_records, source="server_log", impact_of=None):
    """Join findings with measured demand and split into three populations:
      measured  — findings covered by the import, tiered by hits (above synthetic)
      estimated — findings NOT covered, synthetic priority UNTOUCHED
      ghosts    — imported dead URLs with NO finding (the "Inbound 404" class)
    No import → measured/ghosts empty, estimated = findings in original order
    (byte-identical to before). Never blends measured + synthetic into one number.
    """
    findings = list(findings or [])
    demand = {r["url_normalized"]: r for r in (demand_records or [])}

    if not demand:
        return {"has_import": False, "measured": [], "estimated": findings, "ghosts": [],
                "source": None, "verdict": None, "measured_count": 0, "ghost_count": 0,
                "top3_pct": 0, "total_hits": 0}

    def fkey(f):
        return normalize_url(_get(f, "url") or "")

    matched_urls = set()
    measured = []
    estimated = []
    for f in findings:
        rec = demand.get(fkey(f))
        if rec:
            matched_urls.add(rec["url_normalized"])
            measured.append({**(f if isinstance(f, dict) else f.__dict__),
                             "hits": rec["hits"], "tier": demand_tier(rec["hits"]),
                             "source": source, "top_referrers": rec.get("top_referrers", []),
                             "evidence": "measured"})
        else:
            estimated.append(f)

    # Ghosts: imported URLs with no finding — real demand, zero internal links.
    ghosts = []
    for url, rec in demand.items():
        if url in matched_urls:
            continue
        ghosts.append({"url": url, "hits": rec["hits"], "tier": demand_tier(rec["hits"]),
                       "severity": _sev_from_hits(rec["hits"]), "source": source,
                       "top_referrers": rec.get("top_referrers", []),
                       "finding_class": "inbound_404",
                       "consequence": (f"No link on your site points here, but {rec['hits']} "
                                       f"{'crawl hit' + ('s' if rec['hits'] != 1 else '') + ' from Googlebot' if source == 'gsc' else 'visitor' + ('s' if rec['hits'] != 1 else '') + ' tried to reach it'} — "
                                       "likely old backlinks or campaigns.")})
    # measured: hit-desc, impact tiebreak; ghosts: hit-desc
    measured.sort(key=lambda m: (-m["hits"], -(impact_of(m) if impact_of else 0)))
    ghosts.sort(key=lambda g: -g["hits"])

    all_demand = [m["hits"] for m in measured] + [g["hits"] for g in ghosts]
    total = sum(all_demand)
    top3 = sum(sorted(all_demand, reverse=True)[:3])
    top3_pct = round(top3 / total * 100) if total else 0
    n_dead = len(measured) + len(ghosts)
    who = "Googlebot crawled" if source == "gsc" else "Real visitors hit"
    verdict = (f"{who} {n_dead} dead URL{'s' if n_dead != 1 else ''} in the imported window — "
               f"the top 3 account for {top3_pct}% of the demand.") if n_dead else None

    return {"has_import": True, "measured": measured, "estimated": estimated, "ghosts": ghosts,
            "source": source, "verdict": verdict, "measured_count": len(measured),
            "ghost_count": len(ghosts), "top3_pct": top3_pct, "total_hits": total}

"""Google Ads final-URL export → clean list of ad destinations.

Pure, defensive parsing: the export a client hands over is messy — quoted URLs
with commas, locale decimal commas ("1.234,56"), a preamble/total row Google
staples on, blank rows, BOMs, and wildly varying column headers across locales
and report types. This module turns that into a validated destination list and
NEVER raises on junk — bad rows are skipped and counted, not fatal.

No network, no I/O: trivially testable, and the numbers trace to the file.
"""
import csv
import io
import re

# Header synonyms (lower-cased, stripped). Google localises and renames these a
# lot; we match by fuzzy contains so "Final URL", "Final url", "Landing page",
# "Ad final URL" all resolve.
_FINAL_URL_KEYS = ("final url", "final mobile url", "landing page", "destination url", "url")
_CAMPAIGN_KEYS = ("campaign",)
_ADGROUP_KEYS = ("ad group", "adgroup", "ad group name")
_COST_KEYS = ("cost", "spend", "cost / day", "daily budget", "budget")

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def _norm(s):
    return (s or "").strip().lstrip("﻿").lower()


def _match_col(headers, keys):
    """Index of the first header that contains any key. -1 if none."""
    normed = [_norm(h) for h in headers]
    # Prefer exact, then contains.
    for i, h in enumerate(normed):
        if h in keys:
            return i
    for i, h in enumerate(normed):
        if any(k in h for k in keys):
            return i
    return -1


def _parse_cost(raw):
    """Tolerant money parse → float or None. Handles '$1,234.56', '1.234,56',
    '1 234,56', currency codes, and junk. Never raises."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    # strip everything but digits, separators, minus
    s = re.sub(r"[^\d.,\-]", "", s)
    if not s or s in ("-", ".", ","):
        return None
    has_dot, has_comma = "." in s, "," in s
    if has_dot and has_comma:
        # The rightmost separator is the decimal point.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # 1.234,56 -> 1234.56
        else:
            s = s.replace(",", "")                       # 1,234.56 -> 1234.56
    elif has_comma:
        # Comma is decimal iff it looks like ",dd" at the end, else thousands.
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    try:
        v = float(s)
        return v if v >= 0 else None
    except ValueError:
        return None


def _clean_url(raw):
    """A usable http(s) URL or None. Trims tracking wrappers' surrounding quotes
    and whitespace; rejects anything not http(s)."""
    if not raw:
        return None
    u = str(raw).strip().strip('"').strip()
    if not u:
        return None
    # Google sometimes exports "{lpurl}" templates or "--" for none.
    if u.startswith("{") or u in ("--", "-"):
        return None
    if not _URL_RE.match(u):
        # try prefixing bare domains like "example.com/x"
        if re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", u, re.IGNORECASE):
            u = "https://" + u
        else:
            return None
    return u


def _sniff_rows(text):
    """Yield row-lists, skipping Google's preamble. csv handles quoted commas."""
    # Normalise newlines; drop a UTF-8 BOM.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("﻿"):
        text = text[1:]
    # Detect delimiter from the densest of the first lines.
    sample = "\n".join(text.split("\n")[:20])
    delim = ","
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
    except Exception:
        for d in (",", ";", "\t"):
            if d in sample:
                delim = d
                break
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    for row in reader:
        if any((c or "").strip() for c in row):   # skip blank rows
            yield row


def parse_ads_csv(text, default_currency=""):
    """Parse a Google Ads final-URL export.

    Returns {destinations, campaigns, count, has_cost, skipped, warnings}.
    Each destination: {campaign, ad_group, final_url, cost_per_day|None}.
    Deduped by (campaign, ad_group, final_url).
    """
    if not text or not str(text).strip():
        return {"destinations": [], "campaigns": [], "count": 0,
                "has_cost": False, "skipped": 0, "warnings": ["The file is empty."]}

    rows = list(_sniff_rows(text))
    if not rows:
        return {"destinations": [], "campaigns": [], "count": 0,
                "has_cost": False, "skipped": 0, "warnings": ["No readable rows found."]}

    # Find the header row: the first row that contains a final-URL-like column.
    header_idx, url_col = -1, -1
    for i, row in enumerate(rows[:15]):
        c = _match_col(row, _FINAL_URL_KEYS)
        if c != -1:
            header_idx, url_col = i, c
            break
    warnings = []
    if header_idx == -1:
        return {"destinations": [], "campaigns": [], "count": 0, "has_cost": False,
                "skipped": len(rows),
                "warnings": ["Couldn't find a Final URL column. Export the "
                             "Campaigns or Ads report with the 'Final URL' column included."]}

    headers = rows[header_idx]
    camp_col = _match_col(headers, _CAMPAIGN_KEYS)
    ag_col = _match_col(headers, _ADGROUP_KEYS)
    cost_col = _match_col(headers, _COST_KEYS)

    seen = set()
    destinations = []
    skipped = 0
    for row in rows[header_idx + 1:]:
        if url_col >= len(row):
            skipped += 1
            continue
        url = _clean_url(row[url_col])
        if not url:
            skipped += 1
            continue
        campaign = (row[camp_col].strip() if 0 <= camp_col < len(row) else "") or "Ungrouped"
        ad_group = (row[ag_col].strip() if 0 <= ag_col < len(row) else "")
        cost = _parse_cost(row[cost_col]) if 0 <= cost_col < len(row) else None
        key = (campaign.lower(), ad_group.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)
        destinations.append({"campaign": campaign, "ad_group": ad_group,
                             "final_url": url, "cost_per_day": cost})

    has_cost = any(d["cost_per_day"] is not None for d in destinations)
    campaigns = sorted({d["campaign"] for d in destinations})
    if not destinations:
        warnings.append("No valid ad destinations found in the file.")
    if cost_col == -1:
        warnings.append("No cost column found — spend figures will be hidden (honest numbers).")

    return {
        "destinations": destinations,
        "campaigns": campaigns,
        "count": len(destinations),
        "has_cost": has_cost,
        "skipped": skipped,
        "warnings": warnings,
    }

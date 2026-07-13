"""The Intent Map — orchestration. Joins existing scan data into promises and
their fulfillment. Deterministic; no new probes.

Evidence sourcing (honest about granularity):
 • The promise link's OWN bucket is the strongest signal — a promise that leads
   to a broken/dead destination is a broken promise, full stop.
 • Form / integration presence is read at SITE level (the scan's integration
   inventory + whether the site has any audited form) — an approximation we
   label as such, never dressed up as per-destination certainty.
 • File / tel / maps / ATS are read from the link itself (url, kind).
"""
from urllib.parse import urlparse

from promise_classifier import classify, severity_for_zone
from fulfillment_verifier import verify

_FILE_EXTS = (".pdf", ".zip", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
              ".csv", ".dmg", ".pkg", ".epub", ".mp3", ".mp4", ".mov")
_MAPS_HOSTS = ("google.com/maps", "maps.google", "goo.gl/maps", "maps.apple.com", "waze.com")
_ATS_HOSTS = ("greenhouse.io", "lever.co", "workable.com", "bamboohr.com", "ashbyhq.com",
              "smartrecruiters.com", "jobvite.com", "recruitee.com")


def _get(o, k, d=None):
    return o.get(k, d) if isinstance(o, dict) else getattr(o, k, d)


def _primary_zone(link):
    zones = _get(link, "zones") or []
    if zones:
        return zones[0]
    return _get(link, "category") or ""


def _is_file(url, final_url, resource_type):
    u = (final_url or url or "").lower().split("?")[0]
    if any(u.endswith(ext) for ext in _FILE_EXTS):
        return True
    return resource_type in ("media", "image", "file")


def _redirect_to_home(link):
    chain = _get(link, "redirect_chain") or []
    if len(chain) < 2:
        return False
    final = str(_get(chain[-1], "url") or "")
    path = urlparse(final).path.strip("/")
    return path == ""            # ended at the site root


def compute_intent_map(links, integration_categories=None, chat_healthy=None,
                       has_site_form=False):
    """links: list of LinkResult dicts. integration_categories: set of category
    strings present on the site. Returns the map payload."""
    cats = set(integration_categories or [])
    promises = []
    for link in (links or []):
        anchor = _get(link, "anchor_text") or ""
        zone = _primary_zone(link)
        p = classify(anchor, zone)
        if not p:
            continue
        url = _get(link, "url") or ""
        final_url = _get(link, "final_url") or ""
        host_blob = f"{url} {final_url}".lower()
        bucket = _get(link, "bucket") or ("ok" if _get(link, "label") == "ok" else _get(link, "label"))
        if bucket in ("ok", "redirect", None):
            bucket = "ok"

        evidence = {
            "link_bucket": bucket,
            "integrations": cats,
            "has_form": has_site_form,
            "is_file": _is_file(url, final_url, _get(link, "resource_type")),
            "redirect_to_home": _redirect_to_home(link),
            "is_tel": (_get(link, "link_kind") == "contact" and url.lower().startswith("tel:")),
            "has_phone": url.lower().startswith("tel:"),
            "is_maps": any(h in host_blob for h in _MAPS_HOSTS),
            "is_ats": any(h in host_blob for h in _ATS_HOSTS),
            "anchor_says_free": "free" in anchor.lower(),
            "chat_healthy": chat_healthy,
        }
        v = verify(p, evidence)
        promises.append({
            "type": p["type"], "tier": p["tier"], "label": p["label"],
            "anchor": anchor.strip()[:120], "zone": zone, "zone_class": p["zone_class"],
            "url": url, "final_url": final_url or url,
            "verdict": v["verdict"], "evidence": v["evidence"],
            "severity": v.get("severity") or (severity_for_zone(p["zone_class"]) if v["verdict"] == "broken" else None),
            "weight": p["weight"],
        })

    # Broken first, then by weight desc — the map promotes problems.
    order = {"broken": 0, "unverified": 1, "honored": 2}
    promises.sort(key=lambda x: (order.get(x["verdict"], 3), -x["weight"]))

    conv = [p for p in promises if p["tier"] == 1]
    honored = sum(1 for p in conv if p["verdict"] == "honored")
    broken = sum(1 for p in conv if p["verdict"] == "broken")
    unverified = sum(1 for p in conv if p["verdict"] == "unverified")

    return {
        "verdict": _verdict(len(conv), honored, broken, unverified),
        "all_clear": len(conv) > 0 and broken == 0,
        "counts": {"conversion_total": len(conv), "honored": honored, "broken": broken,
                   "unverified": unverified, "functional_total": len(promises) - len(conv)},
        "promises": promises,
    }


def _verdict(total, honored, broken, unverified):
    if total == 0:
        return "No conversion promises detected on this site yet."
    if broken == 0:
        n = f"{total} conversion promise" + ("s" if total != 1 else "")
        tail = f" ({unverified} unverified)" if unverified else ""
        return f"All {n} on this site are honored.{tail}"
    return (f"{total} conversion promises · {honored} honored · "
            f"{broken} broken" + (f" · {unverified} unverified" if unverified else ""))

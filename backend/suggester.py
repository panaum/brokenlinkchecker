"""
Suggestion engine for broken links.

1. Checks Wayback Machine for archived versions
2. Finds similar live URLs via difflib + BM25
3. Scores candidates and returns best suggestion
4. Classifies intent of the broken link
"""

import asyncio
import re
import httpx
from difflib import SequenceMatcher
from urllib.parse import urlparse, urljoin
from typing import Optional
from rank_bm25 import BM25Okapi


# ─── Wayback Machine ──────────────────────────────────────────────────────────

async def check_wayback(url: str) -> dict:
    """
    Query Wayback Machine for a broken URL.
    Returns:
      {
        "existed": bool,
        "last_seen": str | None,
        "redirect_url": str | None,
      }
    """
    api_url = f"https://archive.org/wayback/available?url={url}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            r = await client.get(api_url)
            if r.status_code != 200:
                return {"existed": False, "last_seen": None, "redirect_url": None}

            data = r.json()
            snapshot = data.get("archived_snapshots", {}).get("closest")
            if not snapshot:
                return {"existed": False, "last_seen": None, "redirect_url": None}

            existed = snapshot.get("available", False)
            last_seen = snapshot.get("timestamp")  # e.g. "20231015120000"
            wayback_url = snapshot.get("url")

            # Format timestamp nicely
            formatted_ts = None
            if last_seen and len(last_seen) >= 8:
                formatted_ts = f"{last_seen[:4]}-{last_seen[4:6]}-{last_seen[6:8]}"

            return {
                "existed": existed,
                "last_seen": formatted_ts,
                "redirect_url": wayback_url,
            }
    except Exception:
        return {"existed": False, "last_seen": None, "redirect_url": None}


# ─── URL similarity (difflib) ─────────────────────────────────────────────────

def url_similarity(a: str, b: str) -> float:
    """Compute similarity ratio between two URL strings."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ─── Directory structure matching ──────────────────────────────────────────────

def directory_similarity(broken_url: str, candidate_url: str) -> float:
    """Compare directory structure of two URLs."""
    try:
        broken_parts = urlparse(broken_url).path.strip("/").split("/")
        candidate_parts = urlparse(candidate_url).path.strip("/").split("/")
    except Exception:
        return 0.0

    if not broken_parts or not candidate_parts:
        return 0.0

    matching = 0
    for bp, cp in zip(broken_parts, candidate_parts):
        if bp.lower() == cp.lower():
            matching += 1
        else:
            break

    max_depth = max(len(broken_parts), len(candidate_parts))
    return matching / max_depth if max_depth > 0 else 0.0


# ─── BM25 keyword matching ────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple tokenizer for URLs and titles."""
    # Replace common URL separators with spaces
    text = re.sub(r'[/\-_\.?&=#+]', ' ', text.lower())
    tokens = text.split()
    # Filter out very short tokens and common noise
    return [t for t in tokens if len(t) > 1 and t not in {"www", "com", "org", "net", "html", "htm", "php", "http", "https"}]


def keyword_match_score(broken_url: str, candidate_urls: list[str], candidate_titles: list[str]) -> list[float]:
    """
    Use BM25 to score candidates based on keyword relevance to the broken URL.
    Returns a list of scores (0-1 normalized) for each candidate.
    """
    if not candidate_urls:
        return []

    # Build corpus from candidate URLs + titles
    corpus = []
    for url, title in zip(candidate_urls, candidate_titles):
        tokens = _tokenize(url) + _tokenize(title)
        corpus.append(tokens if tokens else [""])

    # Query from broken URL
    query_tokens = _tokenize(broken_url)
    if not query_tokens:
        return [0.0] * len(candidate_urls)

    try:
        bm25 = BM25Okapi(corpus)
        scores = bm25.get_scores(query_tokens)

        # Normalize to 0-1
        max_score = max(scores) if max(scores) > 0 else 1.0
        return [s / max_score for s in scores]
    except Exception:
        return [0.0] * len(candidate_urls)


# ─── Intent classification ────────────────────────────────────────────────────

def classify_intent(
    status_code: Optional[int],
    wayback_existed: bool,
    url: str,
) -> str:
    """
    Rule-based intent classification for broken links.
    Returns one of: "intentionally_deleted", "never_existed", "likely_expired", "moved_or_renamed"
    """
    # 410 Gone = intentionally deleted
    if status_code == 410:
        return "intentionally_deleted"

    # Wayback says it never existed
    if not wayback_existed:
        return "never_existed"

    # URL contains year pattern like /2019/ or /2022/
    if re.search(r'/20\d{2}/', url):
        return "likely_expired"

    return "moved_or_renamed"


# ─── Candidate scoring ────────────────────────────────────────────────────────

def score_candidate(
    broken_url: str,
    candidate_url: str,
    url_sim: float,
    kw_score: float,
    wayback_redirect: Optional[str],
    dir_sim: float,
) -> int:
    """
    Score a candidate URL (0-100) based on weighted criteria:
      url_similarity:    30% weight
      keyword_match:     30% weight
      wayback_redirect:  25% weight
      directory_match:   15% weight
    """
    # Wayback redirect bonus: if wayback redirect matches candidate, full score
    wayback_bonus = 0.0
    if wayback_redirect:
        wayback_sim = url_similarity(candidate_url, wayback_redirect)
        wayback_bonus = wayback_sim

    total = (
        url_sim * 30 +
        kw_score * 30 +
        wayback_bonus * 25 +
        dir_sim * 15
    )

    return min(100, max(0, int(total)))


# ─── Main suggestion function ─────────────────────────────────────────────────

async def get_suggestion(
    broken_url: str,
    status_code: Optional[int],
    all_working_urls: list[str],
    all_working_titles: list[str],
) -> Optional[dict]:
    """
    Generate a suggestion for a broken link.
    Returns a suggestion dict if confidence >= 60, else None.
    """
    # Check Wayback Machine
    wayback = await check_wayback(broken_url)

    # Classify intent
    intent = classify_intent(status_code, wayback["existed"], broken_url)

    # If intentionally deleted, return special response
    if intent == "intentionally_deleted":
        return {
            "suggested_url": None,
            "confidence": 0,
            "reasoning": "This page was intentionally removed (HTTP 410 Gone).",
            "intent": intent,
            "wayback_existed": wayback["existed"],
            "wayback_last_seen": wayback["last_seen"],
            "can_auto_fix": False,
        }

    # No candidates to compare against
    if not all_working_urls:
        # Still return useful wayback info if it existed
        if wayback["existed"] and wayback["redirect_url"]:
            return {
                "suggested_url": wayback["redirect_url"],
                "confidence": 40,
                "reasoning": f"Found in Wayback Machine (last seen: {wayback['last_seen']}). No live replacement found on site.",
                "intent": intent,
                "wayback_existed": wayback["existed"],
                "wayback_last_seen": wayback["last_seen"],
                "can_auto_fix": False,
            }
        return None

    # Score all working URLs as candidates
    url_sims = [url_similarity(broken_url, c) for c in all_working_urls]
    kw_scores = keyword_match_score(broken_url, all_working_urls, all_working_titles)
    dir_sims = [directory_similarity(broken_url, c) for c in all_working_urls]

    best_score = 0
    best_idx = 0

    for i in range(len(all_working_urls)):
        score = score_candidate(
            broken_url,
            all_working_urls[i],
            url_sims[i],
            kw_scores[i],
            wayback.get("redirect_url"),
            dir_sims[i],
        )
        if score > best_score:
            best_score = score
            best_idx = i

    # Only return suggestion if confidence >= 60
    if best_score < 60:
        # Still return intent/wayback info for lower confidence
        if wayback["existed"]:
            return {
                "suggested_url": all_working_urls[best_idx] if best_score >= 40 else None,
                "confidence": best_score,
                "reasoning": f"Best match has low confidence ({best_score}%). Page was last seen in Wayback Machine on {wayback['last_seen'] or 'unknown date'}.",
                "intent": intent,
                "wayback_existed": wayback["existed"],
                "wayback_last_seen": wayback["last_seen"],
                "can_auto_fix": False,
            }
        return None

    # Build reasoning string
    candidate = all_working_urls[best_idx]
    reasons = []
    if url_sims[best_idx] > 0.6:
        reasons.append("URL structure is very similar")
    elif url_sims[best_idx] > 0.3:
        reasons.append("URL structure is somewhat similar")
    if kw_scores[best_idx] > 0.5:
        reasons.append("keywords match strongly")
    if dir_sims[best_idx] > 0.5:
        reasons.append("same directory path")
    if wayback.get("redirect_url"):
        reasons.append("Wayback Machine confirms page existed")

    reasoning = ". ".join(reasons).capitalize() + "." if reasons else "Pattern-based match."

    return {
        "suggested_url": candidate,
        "confidence": best_score,
        "reasoning": reasoning,
        "intent": intent,
        "wayback_existed": wayback["existed"],
        "wayback_last_seen": wayback["last_seen"],
        "can_auto_fix": best_score >= 90,
    }


# ─── Batch processor ──────────────────────────────────────────────────────────

async def process_suggestions(results: list) -> list:
    """
    For every broken link in results, run get_suggestion in parallel.
    Returns the same results list with suggestions attached.
    Runs AFTER link checking completes — does not slow down the main scan.
    """
    # Collect working URLs and their titles for candidate matching
    working_urls = []
    working_titles = []
    for r in results:
        if r.label == "ok":
            working_urls.append(r.url)
            working_titles.append(r.anchor_text or "")

    # Find broken links that need suggestions
    broken_indices = [
        i for i, r in enumerate(results)
        if r.label == "broken"
    ]

    if not broken_indices:
        return results

    # Create suggestion tasks
    async def suggest_for(idx: int):
        r = results[idx]
        suggestion = await get_suggestion(
            broken_url=r.url,
            status_code=r.status_code,
            all_working_urls=working_urls,
            all_working_titles=working_titles,
        )
        if suggestion:
            results[idx].suggestion = suggestion

    # Run all suggestion lookups in parallel
    tasks = [suggest_for(i) for i in broken_indices]
    await asyncio.gather(*tasks, return_exceptions=True)

    return results

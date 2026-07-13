"""The Intent Map — promise classifier (deterministic, versioned).

Reads EXISTING link data (anchor_text + zone) and classifies each link into a
machine-verifiable "promise". No model, no guessing: an anchor either matches a
rule or it makes no promise. Adding a promise type later is one row here, not a
refactor.

Only promises we can VERIFY by joining existing data live here. Semantic promises
("Learn more", "Why us") are permanently out of scope — never classified.
"""
import re

RULES_VERSION = 3

# Tier 1 = conversion promises (highest weight, feed tracer enrollment).
# Tier 2 = functional promises (same verification rigor, weighted below).
# FR/ES equivalents are the trivially-safe ones for the client base.
PROMISE_RULES = (
    # ── Tier 1 ──
    {"type": "BOOK", "tier": 1, "label": "Book / schedule",
     "keywords": ("book", "schedule", "consultation", "book a demo", "demo", "appointment",
                  "reserve", "réserver", "reservar", "agendar")},
    {"type": "DOWNLOAD", "tier": 1, "label": "Download",
     "keywords": ("download", "get the guide", "free ebook", "ebook", "pdf", "whitepaper",
                  "template", "télécharger", "descargar")},
    {"type": "CONTACT", "tier": 1, "label": "Contact",
     "keywords": ("contact", "get in touch", "request a quote", "quote", "talk to us",
                  "reach out", "contacto", "contactez", "contáctanos")},
    {"type": "PURCHASE", "tier": 1, "label": "Purchase / pricing",
     "keywords": ("buy", "pricing", "plans", "order now", "order", "subscribe", "checkout",
                  "comprar", "acheter", "precios", "tarifs")},
    {"type": "SIGNUP", "tier": 1, "label": "Sign up",
     "keywords": ("sign up", "signup", "register", "start free", "free trial", "trial",
                  "get started", "s'inscrire", "registrarse")},
    # ── Tier 2 ──
    {"type": "WATCH", "tier": 2, "label": "Watch",
     "keywords": ("watch", "see the video", "watch the video", "view demo video", "play video")},
    {"type": "CALL", "tier": 2, "label": "Call",
     "keywords": ("call us", "call now", "phone us", "give us a call", "llamar", "appelez")},
    {"type": "DIRECTIONS", "tier": 2, "label": "Directions",
     "keywords": ("directions", "get directions", "find us", "visit us", "our location",
                  "store locator", "cómo llegar", "nous trouver")},
    {"type": "APPLY", "tier": 2, "label": "Apply / careers",
     "keywords": ("apply now", "apply", "careers", "join the team", "we're hiring",
                  "open positions", "postuler", "empleo")},
    {"type": "CHAT", "tier": 2, "label": "Chat",
     "keywords": ("live chat", "chat with us", "chat now", "message us", "start a chat")},
)

# Zones where a promise is unambiguous. Body copy is allowed too, but only for a
# tight CTA-shaped anchor (guarded below) — a keyword buried in prose is NOT a
# promise ("...you can book a room at our partner hotel...").
_CTA_ZONES = ("cta", "button", "hero", "footer-cta")
_NAV_ZONES = ("nav", "header", "menu")
_BODY_MAX_WORDS = 3


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _has_kw(text, kw):
    """kw present as a word/phrase (word-boundary so 'call' ≠ 'recall')."""
    if " " in kw:
        return kw in text
    return re.search(rf"\b{re.escape(kw)}\b", text) is not None


def _zone_class(zone):
    z = (zone or "").lower()
    if any(c in z for c in _CTA_ZONES):
        return "cta"
    if any(c in z for c in _NAV_ZONES):
        return "nav"
    return "body"


def classify(anchor_text, zone=""):
    """Return the promise for this anchor, or None. Deterministic."""
    text = _norm(anchor_text)
    if not text:
        return None
    words = len(text.split())
    if words > 8:                    # a whole-sentence link is never a CTA
        return None
    zc = _zone_class(zone)

    for rule in PROMISE_RULES:
        for kw in rule["keywords"]:
            if not _has_kw(text, kw):
                continue
            # Body-prose guard: in body, only a tight anchor that LEADS with the
            # keyword counts — otherwise it's incidental prose, not a promise.
            if zc == "body":
                if words > _BODY_MAX_WORDS or not text.startswith(kw.split()[0]):
                    return None
            weight = _weight(rule["tier"], zc)
            return {
                "type": rule["type"], "tier": rule["tier"], "label": rule["label"],
                "keyword": kw, "zone": zone or "", "zone_class": zc,
                "weight": weight,
                "confidence": "high" if zc in ("cta", "nav") else "medium",
                "rules_version": RULES_VERSION,
            }
    return None


def _weight(tier, zone_class):
    """CTA/Nav weigh highest; Tier 2 sits a step below Tier 1 everywhere."""
    base = {"cta": 100, "nav": 80, "body": 50}[zone_class]
    return base - (25 if tier == 2 else 0)


def severity_for_zone(zone_class):
    """Broken-promise severity by zone (feeds the finding pipeline)."""
    return {"cta": "critical", "nav": "high", "body": "medium"}.get(zone_class, "medium")

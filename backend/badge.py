"""Embeddable status badge — a tiny, cacheable SVG of a site's health score.

Pure string building, no I/O, so it is trivially testable. The colors match the
mission-control signal system: teal healthy, amber needs-attention, red broken,
gray when a site has never been scanned.
"""

# Health palette (kept in sync with the frontend status tokens). The badge
# shows a health score, so it uses the HEALTH colors (green/amber/red), not the
# violet brand accent.
_GREEN = "#34d399"
_AMBER = "#fbbf24"
_RED = "#f87171"
_GRAY = "#9aa0b4"
_INK = "#1c1a27"       # left "LinkSpy" plate (warm slate)


def score_color(score) -> str:
    if score is None:
        return _GRAY
    if score >= 90:
        return _GREEN
    if score >= 70:
        return _AMBER
    return _RED


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def build_badge_svg(score, label: str = "LinkSpy") -> str:
    """A two-plate badge: dark label plate + score-colored value plate.

    score is an int 0-100 or None (never scanned -> "--", gray).
    Approximate 7px/char widths — good enough for a fixed-content badge.
    """
    label = _esc(label)[:16]
    value = "--" if score is None else str(int(score))
    color = score_color(score)

    label_w = round(12 + len(label) * 6.5)
    value_w = round(20 + len(value) * 8)
    total_w = label_w + value_w
    h = 20

    label_mid = label_w / 2
    value_mid = label_w + value_w / 2
    font = "Verdana,DejaVu Sans,Geneva,sans-serif"

    # Both plates are clipped to one rounded rectangle, so the colored plate's
    # corners follow the badge outline (no square edge poking out).
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{h}" '
        f'role="img" aria-label="{label}: {value}">'
        f'<title>{label}: {value}</title>'
        f'<clipPath id="r"><rect width="{total_w}" height="{h}" rx="4"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_w}" height="{h}" fill="{_INK}"/>'
        f'<rect x="{label_w}" width="{value_w}" height="{h}" fill="{color}"/>'
        f'</g>'
        f'<g font-family="{font}" font-size="11">'
        f'<text x="{label_mid:.0f}" y="14" text-anchor="middle" fill="#e9f4f1">{label}</text>'
        f'<text x="{value_mid:.0f}" y="14" text-anchor="middle" fill="#ffffff" font-weight="bold">{value}</text>'
        f'</g>'
        f'</svg>'
    )

"""Embeddable status badge — a tiny, cacheable SVG of a site's health score.

Pure string building, no I/O, so it is trivially testable. The colors match the
mission-control signal system: teal healthy, amber needs-attention, red broken,
gray when a site has never been scanned.
"""

# Signal palette (kept in sync with the frontend design tokens).
_SIGNAL = "#22d3aa"
_AMBER = "#f6c445"
_RED = "#ff6b6b"
_GRAY = "#8b9ba0"
_INK = "#0d1417"       # left "LinkSpy" plate (near-black, blue-green cast)


def score_color(score) -> str:
    if score is None:
        return _GRAY
    if score >= 90:
        return _SIGNAL
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

    label_w = 12 + len(label) * 6.5
    value_w = 20 + len(value) * 8
    total_w = label_w + value_w
    h = 20

    label_mid = label_w / 2
    value_mid = label_w + value_w / 2

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w:.0f}" height="{h}" '
        f'role="img" aria-label="{label}: {value}">'
        f'<title>{label}: {value}</title>'
        f'<rect width="{total_w:.0f}" height="{h}" rx="4" fill="{_INK}"/>'
        f'<rect x="{label_w:.0f}" width="{value_w:.0f}" height="{h}" fill="{color}"/>'
        # re-clip corners of the right plate under the rounded container
        f'<rect x="{label_w:.0f}" width="{value_w - 4:.0f}" height="{h}" fill="{color}"/>'
        f'<g fill="#e9f4f1" font-family="Verdana,DejaVu Sans,Geneva,sans-serif" font-size="11">'
        f'<text x="{label_mid:.0f}" y="14" text-anchor="middle">{label}</text>'
        f'</g>'
        f'<g fill="{_INK}" font-family="Verdana,DejaVu Sans,Geneva,sans-serif" '
        f'font-size="11" font-weight="bold">'
        f'<text x="{value_mid:.0f}" y="14" text-anchor="middle">{value}</text>'
        f'</g>'
        f'</svg>'
    )

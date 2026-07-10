"""
Fix Pack: a zip a human opens and works through.

Contains
  fixes.csv            one row per finding, with the suggested fix
  instructions.md      the same, grouped by page then issue, written to be read
  redirects/*          the collapsed redirect ruleset, if there is one
  README.txt           what the pack is and how to use it

SECURITY. Everything in here derives from scanned page content.

  CSV injection: a cell beginning with = + - @ (or a tab/CR that a spreadsheet
  strips back to one) is executed as a formula by Excel, Sheets and LibreOffice.
  `=HYPERLINK("http://evil","click")` in an anchor text becomes a live link in
  the client's spreadsheet. Every field is neutralised.

  Markdown injection: anchor text can contain backticks, pipes and raw HTML.
  Values are escaped and URLs are wrapped in <> so they cannot close a fence or
  open a tag.
"""
import csv
import io
import zipfile
from datetime import datetime, timezone

from fix_engine import build_fix_suggestion
from redirect_rules import FORMATS, render as render_rules, sanitize_rules

# Characters a spreadsheet treats as the start of a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@")
# Leading whitespace a spreadsheet strips before looking at the first character.
_STRIPPED = ("\t", "\r", "\n", "\x00")


def csv_safe(value) -> str:
    """Neutralise a cell so no spreadsheet executes it.

    Prefixing with an apostrophe is the standard defence: Excel and Sheets treat
    the rest as literal text and do not display the quote.
    """
    if value is None:
        return ""
    text = str(value)
    for ch in _STRIPPED:
        text = text.replace(ch, " ")
    text = text.strip()
    if text and text[0] in _FORMULA_PREFIXES:
        return "'" + text
    return text


_MD_ESCAPE = str.maketrans({
    "\\": r"\\", "`": r"\`", "*": r"\*", "_": r"\_",
    "[": r"\[", "]": r"\]", "<": r"\<", ">": r"\>",
    "|": r"\|", "#": r"\#",
})


def md_safe(value) -> str:
    """Escape a value so it cannot break out of the markdown it sits in."""
    if value is None:
        return ""
    return str(value).replace("\r", " ").replace("\n", " ").translate(_MD_ESCAPE)


def md_url(url: str) -> str:
    """Autolink form. <...> keeps parentheses and spaces from breaking the link."""
    if not url:
        return "(none)"
    cleaned = str(url).replace("\n", "").replace("\r", "").replace(">", "%3E")
    return f"<{cleaned}>"


CSV_COLUMNS = [
    "page", "issue_type", "element", "current_value", "proposed_value",
    "confidence", "requires_dev", "est_time_minutes", "status_code",
    "resource_type", "builder", "fix_type", "template_source",
]


def _get(finding, field, default=None):
    if isinstance(finding, dict):
        return finding.get(field, default)
    return getattr(finding, field, default)


def build_rows(findings, builder: str, page_url: str,
               page_fragments=(), site_urls=()) -> list:
    """(finding, suggestion) for every finding, in a stable order."""
    rows = []
    for finding in findings or []:
        suggestion = build_fix_suggestion(
            finding, builder, page_url=_get(finding, "page_url", "") or page_url,
            page_fragments=page_fragments, site_urls=site_urls,
        )
        rows.append((finding, suggestion))
    rows.sort(key=lambda pair: (pair[1].issue_type, _get(pair[0], "url", "") or ""))
    return rows


def fixes_csv(rows) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS, lineterminator="\n",
                            quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for finding, fix in rows:
        writer.writerow({
            "page": csv_safe(_get(finding, "page_url", "")),
            "issue_type": csv_safe(fix.issue_type),
            "element": csv_safe(_get(finding, "anchor_text", "")),
            "current_value": csv_safe(_get(finding, "url", "")),
            "proposed_value": csv_safe(fix.proposed_value or ""),
            "confidence": csv_safe(fix.confidence),
            "requires_dev": csv_safe("yes" if fix.requires_dev else "no"),
            "est_time_minutes": csv_safe(fix.est_time_minutes),
            "status_code": csv_safe(_get(finding, "status_code", "")),
            "resource_type": csv_safe(_get(finding, "resource_type", "")),
            "builder": csv_safe(fix.builder),
            "fix_type": csv_safe(fix.fix_type),
            "template_source": csv_safe(fix.template_source),
        })
    return out.getvalue()


_ISSUE_HEADINGS = {
    "broken_link": "Broken links",
    "dead_cta": "Buttons that go nowhere",
    "redirect_chain": "Slow redirect chains",
    "mixed_content": "Content blocked by the browser",
    "missing_asset": "Missing files",
    "external_down": "External sites not responding",
}


def instructions_md(rows, *, site_url: str, builder: str, generated_at: str = "") -> str:
    generated_at = generated_at or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_minutes = sum(fix.est_time_minutes for _, fix in rows)
    dev_needed = sum(1 for _, fix in rows if fix.requires_dev)

    lines = [
        f"# Fix Pack — {md_safe(site_url)}",
        "",
        f"Generated {md_safe(generated_at)} · detected builder: **{md_safe(builder or 'unknown')}**",
        "",
        f"**{len(rows)} item(s)** · roughly **{total_minutes} minutes** of work · "
        f"**{dev_needed}** need a developer.",
        "",
        "Every instruction below was written by hand for this platform. Where a",
        "replacement value is suggested, it was matched by similarity — read it",
        "before you apply it. Nothing here was generated by a language model.",
        "",
    ]

    if not rows:
        lines += ["## Nothing to fix", "", "No actionable findings in this scan."]
        return "\n".join(lines) + "\n"

    # Group by page, then by issue type: a person fixes one page at a time.
    by_page = {}
    for finding, fix in rows:
        by_page.setdefault(_get(finding, "page_url", "") or site_url, []).append((finding, fix))

    for page in sorted(by_page):
        lines += [f"## {md_safe(page)}", ""]
        by_issue = {}
        for finding, fix in by_page[page]:
            by_issue.setdefault(fix.issue_type, []).append((finding, fix))

        for issue_type in sorted(by_issue):
            heading = _ISSUE_HEADINGS.get(issue_type, issue_type)
            lines += [f"### {md_safe(heading)}", ""]

            for finding, fix in by_issue[issue_type]:
                anchor = _get(finding, "anchor_text", "") or "(no text)"
                lines += [
                    f"#### {md_safe(fix.title)}",
                    "",
                    f"- **Element:** {md_safe(anchor)}",
                    f"- **Current value:** {md_url(_get(finding, 'url', ''))}",
                ]
                if fix.proposed_value:
                    lines.append(
                        f"- **Suggested replacement:** {md_url(fix.proposed_value)} "
                        f"_(confidence: {md_safe(fix.confidence)} — confirm before applying)_"
                    )
                else:
                    lines.append("- **Suggested replacement:** none — this one needs a human decision")
                lines += [
                    f"- **Estimated time:** {fix.est_time_minutes} min"
                    + (" · needs a developer" if fix.requires_dev else ""),
                    "",
                    "**Steps**",
                    "",
                ]
                lines += [f"{i}. {md_safe(step)}" for i, step in enumerate(fix.steps, 1)]
                lines += ["", f"_Source: {md_safe(fix.template_source)}_", ""]

    return "\n".join(lines) + "\n"


README = """LinkSpy Fix Pack
================

fixes.csv        One row per finding, with the suggested fix. Open in a
                 spreadsheet. Values that a spreadsheet would treat as a
                 formula are prefixed with an apostrophe on purpose.

instructions.md  The same findings, grouped by page, written to be read and
                 followed. Start here.

redirects/       Ready-made redirect rules, if this scan found any chains worth
                 collapsing. Apply the file that matches your host.

Suggested replacement values were matched by text similarity against real URLs
and element ids on your own site. They are suggestions. Read them before you
apply them.

No part of this pack was written by a language model.
"""


def build_fix_pack(rows, *, site_url: str, builder: str, redirect_rules=None) -> bytes:
    """The zip, as bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", README)
        zf.writestr("fixes.csv", fixes_csv(rows))
        zf.writestr("instructions.md", instructions_md(rows, site_url=site_url, builder=builder))

        clean = sanitize_rules(redirect_rules or [])
        if clean:
            for fmt in FORMATS:
                _media, filename, body = render_rules(fmt, clean)
                zf.writestr(f"redirects/{filename}", body)

    return buffer.getvalue()

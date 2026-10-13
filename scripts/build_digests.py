#!/usr/bin/env python3
"""Generate the Anode governance digest pages, RSS feeds, sitemap and llms.txt entries.

Stdlib only (Python 3.13). Reads public digest editions (markdown with YAML-style
front matter) from content/digests/<feed>/<date>.md and writes:

  digests/index.html                     hub: both feeds, latest summary each
  digests/<feed>/index.html              latest digest in full + dated archive list
  digests/<feed>/<date>/index.html       permalink per day
  digests/<feed>/feed.xml                RSS 2.0, latest 30 entries
  sitemap.xml / llms.txt                 updated only inside marker blocks this script owns

Idempotent: output depends only on content dates, never on wall-clock time.
"""

from __future__ import annotations

import argparse
import email.utils
import html
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

SITE = "https://www.anode.gg"
FEED_NAMES = {"reserve": "Reserve Protocol", "rootstock": "Rootstock Collective"}
FEED_DOMAINS = {"reserve": "forum.reserve.org", "rootstock": "gov.rootstockcollective.xyz"}
FEED_KEYS = ("reserve", "rootstock")

QUIET_LINE = "No new topics or posts on the forum in this window."
SECTION_ORDER = ("Proposals and RFCs", "New topics", "Discussion by topic", "Sentiment", "What to watch")
REQUIRED_SECTIONS = ("New topics", "Discussion by topic", "Sentiment", "What to watch")

DISCLAIMER = (
    "Independent daily summary of public forum activity, compiled by Anode Research. "
    "Not an official communication of Reserve or Rootstock Collective. Anode participates in both as a delegate."
)

HUB_TITLE = "Governance digests | Anode"
HUB_DESCRIPTION = (
    "Independent daily summaries of public forum activity in the Reserve Protocol and "
    "Rootstock Collective, compiled by Anode Research."
)

# Deterministic publication time (UTC) used for RSS pubDate values.
RSS_PUB_HOUR, RSS_PUB_MINUTE = 9, 40

SITEMAP_START = "<!-- digests:start -->"
SITEMAP_END = "<!-- digests:end -->"
LLMS_HEADING = "## Governance digests"
LLMS_SECTION = (
    "## Governance digests\n"
    "\n"
    "Independent daily summaries of public forum activity, compiled by Anode Research. Anode is a\n"
    "delegate in Reserve and Rootstock Collective; these summaries are not official communications\n"
    "of either DAO.\n"
    "\n"
    "- [Governance digests](https://www.anode.gg/digests/): Hub for both feeds, with the latest editions.\n"
    "- [Reserve Protocol digest](https://www.anode.gg/digests/reserve/): Daily digest of the Reserve Protocol forum, with archive and RSS.\n"
    "- [Rootstock Collective digest](https://www.anode.gg/digests/rootstock/): Daily digest of the Rootstock Collective forum, with archive and RSS.\n"
    "\n"
)

HEADER = (
    '      <header class="site-header"><a class="wordmark" href="/" aria-label="Anode home">'
    '<span class="wordmark-mark" aria-hidden="true"><span></span><span></span><span></span></span>'
    '<span class="wordmark-name">ANODE</span><span class="wordmark-sub">RESEARCH</span></a>'
    '<nav class="desktop-nav" aria-label="Primary navigation">'
    '<a href="/research/">Research</a><a href="/decision-systems/">Practice</a>'
    '<a href="/about/">About</a><a href="/digests/">Digests</a><a href="/#method">Method</a></nav>'
    '<a class="header-cta" href="mailto:hello@anode.gg"><span>Start a conversation</span>'
    '<span class="arrow">\u2197</span></a></header>'
)

FOOTER = (
    '      <footer class="site-footer"><div class="footer-mark">'
    '<span class="wordmark-mark" aria-hidden="true"><span></span><span></span><span></span></span>'
    '<span>ANODE</span></div><p>Decision systems, incentive design &amp; coordination research.</p>'
    '<div class="footer-links"><a href="mailto:hello@anode.gg">Email</a><a href="/digests/">Digests</a>'
    '<a href="/privacy/">Privacy</a><a href="/">Home \u2197</a></div></footer>'
)

# Unicode characters and ranges forbidden in digest editions.
FORBIDDEN_SINGLE = {0x2013: "en dash", 0x2014: "em dash"}
FORBIDDEN_RANGES = (
    (0x2018, 0x201F, "curly quote"),
    (0x2190, 0x21FF, "arrow symbol"),
    (0x2300, 0x23FF, "technical symbol"),
    (0x2600, 0x27BF, "emoji or symbol"),
    (0x2B00, 0x2BFF, "emoji or symbol"),
    (0x1F000, 0x1FAFF, "emoji"),
    (0xFE00, 0xFE0F, "variation selector"),
)
BANNED_PHRASES = re.compile(
    r"\byou\b|\byour\b|\byours\b|\byourself\b|\byourselves\b|\bthe user\b|\bfacilitator\b",
    re.IGNORECASE,
)
LINK_RE = re.compile(r"\[([^\]]+)\]\((https://[^)\s]+)\)")
H2_RE = re.compile(r"^## (.+)$")
H3_RE = re.compile(r"^### (.+)$")


class DigestError(Exception):
    """Build or validation failure; the message names the file and reason."""


@dataclass
class Edition:
    feed: str
    date: date
    window: str
    quiet: bool
    summary: str
    body_html: str
    path: Path


def esc(text: str) -> str:
    return html.escape(text, quote=True)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def find_forbidden(text: str) -> list[str]:
    problems: list[str] = []
    for i, ch in enumerate(text):
        cp = ord(ch)
        label = FORBIDDEN_SINGLE.get(cp)
        if label is None:
            for lo, hi, name in FORBIDDEN_RANGES:
                if lo <= cp <= hi:
                    label = name
                    break
        if label:
            problems.append(f"{label} {ch!r} at char {i}")
            if len(problems) >= 5:
                break
    return problems


def find_banned(text: str) -> list[str]:
    return [f'banned phrase "{m.group(0).lower()}" at char {m.start()}' for m in BANNED_PHRASES.finditer(text)]


def validate_body(body: str, quiet: bool) -> list[str]:
    errors: list[str] = []
    lines = body.splitlines()

    # Markdown subset checks, line by line.
    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped:
            continue
        if raw[:1] in (" ", "\t"):
            errors.append(f"line {lineno}: indented line (nesting beyond one bullet level is not allowed)")
        if stripped.startswith("```") or "`" in stripped:
            errors.append(f"line {lineno}: code blocks and inline code are not allowed")
        if re.search(r"<[a-zA-Z/!]", stripped):
            errors.append(f"line {lineno}: raw HTML is not allowed")
        if stripped.startswith("|"):
            errors.append(f"line {lineno}: tables are not allowed")
        if stripped.startswith(">"):
            errors.append(f"line {lineno}: block quotes are not allowed")
        if re.match(r"^\d+[.)]\s", stripped):
            errors.append(f"line {lineno}: numbered lists are not allowed (use - bullets)")
        if re.match(r"^#\s", stripped):
            errors.append(f"line {lineno}: h1 headings are not allowed (the page supplies the h1)")
        if "![" in stripped:
            errors.append(f"line {lineno}: images are not allowed")
        for m in re.finditer(r"\]\(([^)]+)\)", stripped):
            if not m.group(1).startswith("https://"):
                errors.append(f"line {lineno}: link target must start with https:// (got {m.group(1)[:60]!r})")
            elif not LINK_RE.search(stripped):
                errors.append(f"line {lineno}: malformed link (use [text](https://...))")
        if len(errors) > 20:
            errors.append("too many errors, stopping line checks")
            return errors

    # Section structure.
    h2_names: list[tuple[int, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        m = H2_RE.match(raw.strip())
        if m:
            h2_names.append((lineno, m.group(1).strip()))

    if quiet:
        if "\n".join(lines).strip() != QUIET_LINE:
            errors.append(f'quiet editions must have a body of exactly: "{QUIET_LINE}"')
        return errors

    for lineno, name in h2_names:
        if name not in SECTION_ORDER:
            errors.append(f'line {lineno}: unexpected section heading "## {name}"')

    known = [n for _, n in h2_names if n in SECTION_ORDER]
    if len(set(known)) != len(known):
        errors.append("duplicate section headings are not allowed")
    positions = [SECTION_ORDER.index(n) for n in known]
    if positions != sorted(positions):
        errors.append(f"sections out of order; required order is: {', '.join(SECTION_ORDER)}")
    present = set(known)
    for required in REQUIRED_SECTIONS:
        if required not in present:
            errors.append(f'missing required section "## {required}"')

    # Empty section bodies.
    for idx, (lineno, name) in enumerate(h2_names):
        end = h2_names[idx + 1][0] - 1 if idx + 1 < len(h2_names) else len(lines) + 1
        between = [l for l in lines[lineno:end] if l.strip()]
        if not between:
            errors.append(f'line {lineno}: section "## {name}" is empty; omit it')

    # No subheadings outside a section.
    first_h2 = h2_names[0][0] if h2_names else None
    for lineno, raw in enumerate(lines, start=1):
        if H3_RE.match(raw.strip()) and first_h2 is not None and lineno < first_h2:
            errors.append(f"line {lineno}: subheading before any section heading")
    return errors


def parse_edition(path: Path, expected_feed: str) -> Edition:
    label = str(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise DigestError(f"{label}: file is not valid UTF-8")
    except OSError as exc:
        raise DigestError(f"{label}: cannot read file ({exc})")

    problems: list[str] = []
    problems += find_forbidden(raw)
    problems += find_banned(raw)
    if problems:
        raise DigestError(label + ": " + "; ".join(problems))

    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    if not m:
        raise DigestError(f"{label}: missing front matter block (start the file with ---)")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(": ")
        if not sep:
            raise DigestError(f"{label}: malformed front matter line: {line!r}")
        meta[key.strip()] = value.strip()

    missing = [k for k in ("feed", "date", "window", "quiet", "summary") if k not in meta]
    if missing:
        raise DigestError(f"{label}: missing front matter fields: {', '.join(missing)}")
    unknown = [k for k in meta if k not in ("feed", "date", "window", "quiet", "summary")]
    if unknown:
        raise DigestError(f"{label}: unknown front matter fields: {', '.join(unknown)}")
    if meta["feed"] != expected_feed:
        raise DigestError(f'{label}: front matter feed is "{meta["feed"]}", expected "{expected_feed}"')
    if meta["quiet"] not in ("true", "false"):
        raise DigestError(f'{label}: quiet must be true or false (got "{meta["quiet"]}")')
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} to \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$", meta["window"]):
        raise DigestError(f'{label}: window must look like "YYYY-MM-DD HH:MM to YYYY-MM-DD HH:MM UTC"')
    summary = meta["summary"]
    if not summary:
        raise DigestError(f"{label}: summary must not be empty")
    if len(summary) > 200:
        raise DigestError(f"{label}: summary is {len(summary)} chars (max 200)")

    try:
        d = date.fromisoformat(meta["date"])
    except ValueError:
        raise DigestError(f'{label}: invalid date "{meta["date"]}" (expected YYYY-MM-DD)')
    if meta["date"] != path.stem:
        raise DigestError(f'{label}: date "{meta["date"]}" does not match filename "{path.stem}"')

    body = m.group(2)
    if meta["quiet"] == "true":
        # Quiet-day generators sometimes emit the standard empty headings.
        # Remove only those known headings; substantive content must still fail.
        body = "\n".join(
            line for line in body.splitlines()
            if line.strip() not in ({"## " + title for title in SECTION_ORDER}
                                    | {"Nothing scheduled in this window."})
        ).strip()
    body_errors = validate_body(body, meta["quiet"] == "true")
    if body_errors:
        raise DigestError(label + ": " + "; ".join(body_errors[:10]))

    return Edition(
        feed=expected_feed,
        date=d,
        window=meta["window"],
        quiet=meta["quiet"] == "true",
        summary=summary,
        body_html=markdown_to_html(body),
        path=path,
    )


# ---------------------------------------------------------------------------
# Markdown subset to HTML
# ---------------------------------------------------------------------------

def inline_html(raw: str) -> str:
    text = html.escape(raw, quote=True)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = LINK_RE.sub(r'<a href="\2">\1</a>', text)
    return text


def markdown_to_html(md: str) -> str:
    out: list[str] = []
    para: list[str] = []
    bullets: list[str] = []

    def flush_para() -> None:
        if para:
            out.append(f"<p>{inline_html(' '.join(para))}</p>")
            para.clear()

    def flush_bullets() -> None:
        if bullets:
            out.append("<ul>")
            out.extend(f"<li>{inline_html(b)}</li>" for b in bullets)
            out.append("</ul>")
            bullets.clear()

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            flush_para()
            flush_bullets()
            continue
        if line == "---":
            flush_para()
            flush_bullets()
            out.append('<hr class="article-rule" />')
            continue
        m = re.match(r"^(##|###) (.+)$", line)
        if m:
            flush_para()
            flush_bullets()
            tag = "h2" if m.group(1) == "##" else "h3"
            out.append(f"<{tag}>{inline_html(m.group(2))}</{tag}>")
            continue
        if line.startswith("- "):
            flush_para()
            bullets.append(line[2:].strip())
            continue
        if bullets:
            flush_bullets()
        para.append(line)
    flush_para()
    flush_bullets()
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

def feed_page_url(feed: str) -> str:
    return f"/digests/{feed}/"


def day_page_url(feed: str, d: date) -> str:
    return f"/digests/{feed}/{d.isoformat()}/"


def render_head(title: str, description: str, canonical: str, og_type: str,
                rss_links: str, extra_meta: str, jsonld: dict) -> str:
    body = json.dumps(jsonld, separators=(",", ": "))
    return (
        f'    <meta charset="UTF-8" />\n'
        f'    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f'    <meta name="description" content="{esc(description)}" />\n'
        f'    <meta name="robots" content="index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1" />\n'
        f'    <meta name="theme-color" content="#0a0d0c" />\n'
        f'    <link rel="canonical" href="{esc(canonical)}" /><link rel="icon" href="/favicon.svg" type="image/svg+xml" />\n'
        f"{rss_links}"
        f"{extra_meta}"
        f'    <meta property="og:type" content="{og_type}" /><meta property="og:site_name" content="Anode" />'
        f'<meta property="og:url" content="{esc(canonical)}" />\n'
        f'    <meta property="og:title" content="{esc(title)}" /><meta property="og:description" content="{esc(description)}" />'
        f'<meta property="og:image" content="{SITE}/og-image.png" />\n'
        f'    <meta name="twitter:card" content="summary_large_image" /><meta name="twitter:title" content="{esc(title)}" />'
        f'<meta name="twitter:description" content="{esc(description)}" /><meta name="twitter:image" content="{SITE}/og-image.png" />\n'
        f"    <title>{esc(title)}</title>\n"
        f'    <script type="application/ld+json">\n      {body}\n    </script>\n'
        f'    <link rel="stylesheet" href="/styles.css" /><link rel="stylesheet" href="/pages.css" />'
        f'<link rel="stylesheet" href="/digests.css" />\n'
    )


def render_page(title: str, description: str, canonical: str, og_type: str,
                rss_links: str, extra_meta: str, jsonld: dict, hero: str, main: str) -> str:
    head = render_head(title, description, canonical, og_type, rss_links, extra_meta, jsonld)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        f"{head}  </head>\n"
        '  <body class="page-body">\n'
        '    <div class="site-shell">\n'
        f"{HEADER}\n"
        "      <main>\n"
        f"{hero}\n{main}\n"
        "      </main>\n"
        f"{FOOTER}\n"
        "    </div>\n"
        "  </body>\n"
        "</html>\n"
    )


def hero_block(kicker: str, h1_html: str, deck: str, meta_left: str, meta_right: str) -> str:
    return (
        '        <section class="page-hero" aria-labelledby="page-title"><div class="page-hero-inner">'
        f'<p class="page-kicker">{esc(kicker)}</p>'
        f'<h1 id="page-title">{h1_html}</h1>'
        f'<p class="page-deck">{esc(deck)}</p>'
        f'<div class="page-meta"><span>{esc(meta_left)}</span><span>{esc(meta_right)}</span></div>'
        "</div></section>"
    )


def rss_link_tags(feed_keys: tuple[str, ...]) -> str:
    return "".join(
        f'    <link rel="alternate" type="application/rss+xml" '
        f'title="{esc(FEED_NAMES[f])} governance digest RSS" href="/digests/{f}/feed.xml" />\n'
        for f in feed_keys
    )


def breadcrumb(*items: tuple[str, str]) -> dict:
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(items)
        ],
    }


def build_hub_page(editions: dict[str, list[Edition]]) -> str:
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/digests/#webpage",
                "url": f"{SITE}/digests/",
                "name": HUB_TITLE,
                "description": HUB_DESCRIPTION,
                "isPartOf": {"@id": f"{SITE}/#website"},
                "about": {"@id": f"{SITE}/#organization"},
                "inLanguage": "en",
            },
            breadcrumb(("Anode", f"{SITE}/"), ("Digests", f"{SITE}/digests/")),
        ],
    }
    hero = hero_block(
        "Anode Research / Governance digests",
        'Governance<br /><em>digests.</em>',
        HUB_DESCRIPTION + " Anode participates in both DAOs as a delegate.",
        "Reserve Protocol / Rootstock Collective",
        "New editions daily",
    )
    cards = "\n            ".join(hub_card(f, editions.get(f, [])) for f in FEED_KEYS)
    main = (
        '        <section class="page-content" aria-label="Digest feeds"><div class="page-content-inner">\n'
        f'          <p class="digest-note">{esc(DISCLAIMER)}</p>\n'
        '          <div class="index-grid">\n'
        f"            {cards}\n"
        "          </div>\n"
        '          <p class="digest-rss">'
        f'<a href="/digests/reserve/feed.xml">Reserve RSS \u2197</a>'
        f'<a href="/digests/rootstock/feed.xml">Rootstock RSS \u2197</a></p>\n'
        "        </div></section>"
    )
    return render_page(HUB_TITLE, HUB_DESCRIPTION, f"{SITE}/digests/", "website",
                       rss_link_tags(FEED_KEYS), "", jsonld, hero, main)


def hub_card(feed: str, editions: list[Edition]) -> str:
    name = FEED_NAMES[feed]
    if editions:
        latest = editions[-1]
        paragraph = f"<strong>{latest.date.isoformat()}.</strong> {esc(latest.summary)}"
        link_label = "Read the latest edition"
    else:
        paragraph = "No editions published yet. The first digest appears here after the next daily window."
        link_label = "Open the feed"
    return (
        f'<a class="index-card" href="{feed_page_url(feed)}">'
        f'<div class="index-card-top"><span>Daily digest / {esc(name)}</span><span>\u2197</span></div>'
        f"<h3>{esc(name)}, summarized daily.</h3>"
        f"<p>{paragraph}</p>"
        f'<span class="card-link">{link_label} \u2197</span></a>'
    )


def build_feed_page(feed: str, editions: list[Edition]) -> str:
    name = FEED_NAMES[feed]
    title = f"{name} governance digest | Anode"
    description = (
        f"Independent daily summary of public activity on the {FEED_DOMAINS[feed]} forum: "
        f"proposals, new topics, discussion and sentiment, compiled by Anode Research."
    )
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/digests/{feed}/#webpage",
                "url": f"{SITE}{feed_page_url(feed)}",
                "name": title,
                "description": description,
                "isPartOf": {"@id": f"{SITE}/#website"},
                "about": {"@id": f"{SITE}/#organization"},
                "inLanguage": "en",
            },
            breadcrumb(("Anode", f"{SITE}/"), ("Digests", f"{SITE}/digests/"), (name, f"{SITE}{feed_page_url(feed)}")),
        ],
    }
    latest_iso = editions[-1].date.isoformat() if editions else "no editions yet"
    hero = hero_block(
        f"Governance digests / {name}",
        f"{esc(name)}<br /><em>digest.</em>",
        description,
        "Daily digest of public forum activity",
        f"Latest edition: {latest_iso}",
    )

    article_lines: list[str] = []
    if editions:
        latest = editions[-1]
        article_lines.append(f"<h2>Latest edition: {latest.date.isoformat()}</h2>")
        article_lines.append(latest.body_html)
        article_lines.append(
            f'<p><a href="{day_page_url(feed, latest.date)}">Permalink to this edition \u2197</a></p>'
        )
        article_lines.append('<hr class="article-rule" />')
        article_lines.append("<h2>Archive</h2>")
        article_lines.append('<ul class="digest-archive">')
        for ed in reversed(editions):
            article_lines.append(
                f'<li><a href="{day_page_url(feed, ed.date)}">'
                f'<span class="digest-archive-date">{ed.date.isoformat()}</span>'
                f'<span class="digest-archive-summary">{esc(ed.summary)}</span></a></li>'
            )
        article_lines.append("</ul>")
    else:
        article_lines.append("<h2>No editions yet</h2>")
        article_lines.append(
            "<p>Daily editions appear here after the first published window. "
            "The RSS feed updates with each new edition.</p>"
        )
    article = "\n".join(article_lines)

    main = (
        '        <section class="page-content" aria-label="Digest content"><div class="page-content-inner">\n'
        f'          <p class="digest-note">{esc(DISCLAIMER)}</p>\n'
        f'          <div class="article-copy digest-body">\n'
        f"{article}\n"
        "          </div>\n"
        f'          <p class="digest-rss"><a href="/digests/{feed}/feed.xml">RSS feed \u2197</a></p>\n'
        "        </div></section>"
    )
    return render_page(title, description, f"{SITE}{feed_page_url(feed)}", "website",
                       rss_link_tags((feed,)), "", jsonld, hero, main)


def build_day_page(feed: str, ed: Edition, prev_ed: Edition | None, next_ed: Edition | None) -> str:
    name = FEED_NAMES[feed]
    iso = ed.date.isoformat()
    title = f"{name} governance digest: {iso} | Anode"
    description = ed.summary
    canonical = f"{SITE}{day_page_url(feed, ed.date)}"
    jsonld = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "@id": f"{canonical}#article",
                "url": canonical,
                "headline": f"{name} governance digest: {iso}",
                "description": description,
                "datePublished": iso,
                "inLanguage": "en",
                "author": {"@type": "Organization", "@id": f"{SITE}/#organization", "name": "Anode"},
                "publisher": {"@id": f"{SITE}/#organization"},
                "isPartOf": {"@id": f"{SITE}/digests/{feed}/#webpage"},
                "image": f"{SITE}/og-image.png",
            },
            breadcrumb(
                ("Anode", f"{SITE}/"),
                ("Digests", f"{SITE}/digests/"),
                (name, f"{SITE}{feed_page_url(feed)}"),
                (iso, canonical),
            ),
        ],
    }
    hero = hero_block(
        f"Governance digest / {name}",
        f"{esc(name)} digest,<br /><em>{iso}.</em>",
        description,
        f"Window: {ed.window}",
        f"Published {iso} UTC",
    )
    prev_html = f'<a href="{day_page_url(feed, prev_ed.date)}">Previous: {prev_ed.date.isoformat()}</a>' if prev_ed else ""
    next_html = f'<a href="{day_page_url(feed, next_ed.date)}">Next: {next_ed.date.isoformat()}</a>' if next_ed else ""
    main = (
        '        <section class="page-content" aria-label="Digest content"><div class="page-content-inner">\n'
        f'          <p class="digest-note">{esc(DISCLAIMER)}</p>\n'
        f'          <div class="article-copy digest-body">\n'
        f"{ed.body_html}\n"
        "          </div>\n"
        f'          <nav class="digest-pager" aria-label="Digest navigation">'
        f'{prev_html}<a href="{feed_page_url(feed)}">All {esc(name)} digests</a>{next_html}</nav>\n'
        "        </div></section>"
    )
    extra_meta = f'    <meta property="article:published_time" content="{iso}" />\n'
    return render_page(title, description, canonical, "article", rss_link_tags((feed,)), extra_meta,
                       jsonld, hero, main)


def build_rss(feed: str, editions: list[Edition]) -> str:
    items: list[str] = []
    for ed in reversed(editions[-30:]):
        iso = ed.date.isoformat()
        link = f"{SITE}{day_page_url(feed, ed.date)}"
        pub = email.utils.format_datetime(
            datetime(ed.date.year, ed.date.month, ed.date.day, RSS_PUB_HOUR, RSS_PUB_MINUTE, tzinfo=timezone.utc)
        )
        items.append(
            "    <item>\n"
            f"      <title>{esc(f'{FEED_NAMES[feed]} governance digest: {iso}')}</title>\n"
            f"      <link>{esc(link)}</link>\n"
            f'      <guid isPermaLink="true">{esc(link)}</guid>\n'
            f"      <pubDate>{pub}</pubDate>\n"
            f"      <description>{esc(ed.summary)}</description>\n"
            "    </item>"
        )
    channel_description = (
        f"Independent daily summary of public forum activity in the {FEED_NAMES[feed]}, "
        f"compiled by Anode Research."
    )
    feed_url = f"{SITE}/digests/{feed}/feed.xml"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">\n'
        "  <channel>\n"
        f"    <title>{esc(FEED_NAMES[feed])} governance digest</title>\n"
        f"    <link>{esc(SITE)}{feed_page_url(feed)}</link>\n"
        f"    <description>{esc(channel_description)}</description>\n"
        "    <language>en</language>\n"
        f'    <atom:link href="{esc(feed_url)}" rel="self" type="application/rss+xml" />\n'
        + ("\n".join(items) + "\n" if items else "")
        + "  </channel>\n"
        "</rss>\n"
    )


# ---------------------------------------------------------------------------
# sitemap.xml and llms.txt
# ---------------------------------------------------------------------------

def sitemap_entry(loc: str, lastmod: str | None) -> str:
    lm = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
    return f"  <url><loc>{esc(loc)}</loc>{lm}</url>"


def update_sitemap(repo: Path, editions: dict[str, list[Edition]], changed: list[str]) -> None:
    path = repo / "sitemap.xml"
    text = path.read_text(encoding="utf-8")
    all_dates = [ed.date for eds in editions.values() for ed in eds]
    entries: list[str] = []
    entries.append(sitemap_entry(f"{SITE}/digests/", max(all_dates).isoformat() if all_dates else None))
    for feed in FEED_KEYS:
        eds = editions.get(feed, [])
        entries.append(sitemap_entry(f"{SITE}{feed_page_url(feed)}", eds[-1].date.isoformat() if eds else None))
        for ed in eds:
            entries.append(sitemap_entry(f"{SITE}{day_page_url(feed, ed.date)}", ed.date.isoformat()))
    block = f"  {SITEMAP_START}\n" + "\n".join(entries) + f"\n  {SITEMAP_END}"
    pattern = re.compile(r"[ \t]*" + re.escape(SITEMAP_START) + r".*?[ \t]*" + re.escape(SITEMAP_END), re.S)
    if pattern.search(text):
        new_text = pattern.sub(lambda m: block, text, count=1)
    elif "</urlset>" in text:
        new_text = text.replace("</urlset>", block + "\n</urlset>", 1)
    else:
        raise DigestError(f"{path}: no {SITEMAP_START} markers and no </urlset> to anchor the digest block")
    if write_if_changed(path, new_text):
        changed.append(str(path))


def update_llms(repo: Path, changed: list[str]) -> None:
    path = repo / "llms.txt"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(r"^## Governance digests\n.*?(?=^## |\Z)", re.S | re.M)
    if pattern.search(text):
        new_text = pattern.sub(lambda m: LLMS_SECTION, text, count=1)
    elif "\n## Contact\n" in text:
        new_text = text.replace("\n## Contact\n", "\n" + LLMS_SECTION + "## Contact\n", 1)
    else:
        new_text = text.rstrip("\n") + "\n\n" + LLMS_SECTION
    if write_if_changed(path, new_text):
        changed.append(str(path))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_if_changed(path: Path, content: str) -> bool:
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == content:
                return False
        except UnicodeDecodeError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def load_editions(content_dir: Path) -> dict[str, list[Edition]]:
    if not content_dir.is_dir():
        raise DigestError(f"content directory not found: {content_dir}")
    editions: dict[str, list[Edition]] = {}
    errors: list[str] = []
    for feed in FEED_KEYS:
        feed_dir = content_dir / feed
        if not feed_dir.is_dir():
            errors.append(f"missing feed directory: {feed_dir}")
            continue
        found = sorted(feed_dir.glob("*.md"))
        if not found:
            # No editions yet is a valid state (initial repo, all-quiet publishing run):
            # the hub and feed pages render an empty state instead of failing.
            editions[feed] = []
            continue
        parsed: list[Edition] = []
        for md in found:
            try:
                parsed.append(parse_edition(md, feed))
            except DigestError as exc:
                errors.append(str(exc))
        editions[feed] = sorted(parsed, key=lambda e: e.date)
    if errors:
        raise DigestError("\n".join(errors))
    return editions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--content-dir",
        default=None,
        help="directory of public editions (default: <repo>/content/digests)",
    )
    parser.add_argument("--repo-root", default=None, help="repository root (default: parent of this script)")
    args = parser.parse_args(argv)

    repo = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parent.parent
    content_dir = Path(args.content_dir).resolve() if args.content_dir else repo / "content" / "digests"

    try:
        editions = load_editions(content_dir)
        changed: list[str] = []
        if write_if_changed(repo / "digests" / "index.html", build_hub_page(editions)):
            changed.append("digests/index.html")
        for feed in FEED_KEYS:
            eds = editions.get(feed, [])
            if write_if_changed(repo / "digests" / feed / "index.html", build_feed_page(feed, eds)):
                changed.append(f"digests/{feed}/index.html")
            if write_if_changed(repo / "digests" / feed / "feed.xml", build_rss(feed, eds)):
                changed.append(f"digests/{feed}/feed.xml")
            for idx, ed in enumerate(eds):
                prev_ed = eds[idx - 1] if idx > 0 else None
                next_ed = eds[idx + 1] if idx + 1 < len(eds) else None
                day_path = repo / "digests" / feed / ed.date.isoformat() / "index.html"
                if write_if_changed(day_path, build_day_page(feed, ed, prev_ed, next_ed)):
                    changed.append(f"digests/{feed}/{ed.date.isoformat()}/index.html")
        update_sitemap(repo, editions, changed)
        update_llms(repo, changed)
    except DigestError as exc:
        print(f"build_digests: {exc}", file=sys.stderr)
        return 1

    for name in changed:
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

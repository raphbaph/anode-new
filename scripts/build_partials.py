#!/usr/bin/env python3
"""Keep the shared site header and footer identical on every page.

Stdlib only (Python 3.13). partials/header.html and partials/footer.html are the
single source of truth. Every *.html file in the repo that contains the marker pairs

  <!-- partial:header --> ... <!-- /partial:header -->
  <!-- partial:footer --> ... <!-- /partial:footer -->

gets whatever sits between the markers replaced with the partial. The primary
nav link for the page's section gets aria-current="page".

Usage:
  python3 scripts/build_partials.py           rewrite out-of-date pages
  python3 scripts/build_partials.py --check   exit 1 if any page is out of date

Idempotent: output depends only on the partials and the page's path.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PARTIAL_NAMES = ("header", "footer")
SKIP_DIRS = {"tmp", "node_modules", ".git", "partials"}

# URL path prefix -> nav link href that is "current" for it. First match wins.
SECTIONS = (
    ("/decision-systems/", "/practice/"),
    ("/incentive-design/", "/practice/"),
    ("/coordination-architecture/", "/practice/"),
    ("/practice/", "/practice/"),
    ("/research/", "/research/"),
    ("/tools/", "/tools/"),
    ("/simulators/", "/tools/"),
    ("/digests/", "/digests/"),
    ("/about/", "/about/"),
)


class PartialsError(Exception):
    """Build failure; the message names the file and reason."""


def marker_re(name: str) -> re.Pattern[str]:
    return re.compile(
        r"(?P<indent>[ \t]*)<!-- partial:" + name + r" -->\n?.*?<!-- /partial:" + name + r" -->",
        re.S,
    )


def load_partials(repo: Path) -> dict[str, str]:
    partials: dict[str, str] = {}
    for name in PARTIAL_NAMES:
        path = repo / "partials" / f"{name}.html"
        try:
            partials[name] = path.read_text(encoding="utf-8").strip("\n")
        except OSError as exc:
            raise PartialsError(f"{path}: cannot read partial ({exc})")
    return partials


def url_path_for(rel: Path) -> str:
    """repo-relative file path -> URL path ("digests/a/index.html" -> "/digests/a/")."""
    parts = list(rel.parts)
    if parts and parts[-1] == "index.html":
        parts = parts[:-1]
    return "/" + "/".join(parts) + ("/" if parts else "")


def section_href(url_path: str) -> str | None:
    for prefix, href in SECTIONS:
        if url_path.startswith(prefix):
            return href
    return None


def render_block(name: str, partial: str, indent: str, current_href: str | None) -> str:
    body = partial
    if name == "header" and current_href:
        needle = f'<a href="{current_href}">'
        if needle not in body:
            raise PartialsError(f"partials/header.html has no nav link {needle}")
        body = body.replace(needle, f'<a href="{current_href}" aria-current="page">', 1)
    lines = [(indent + line) if line.strip() else "" for line in body.split("\n")]
    return (
        f"{indent}<!-- partial:{name} -->\n"
        + "\n".join(lines)
        + f"\n{indent}<!-- /partial:{name} -->"
    )


def has_markers(text: str) -> bool:
    return all(marker_re(name).search(text) for name in PARTIAL_NAMES)


def apply_partials(text: str, url_path: str, partials: dict[str, str]) -> str:
    """Return text with both marker blocks regenerated for the page at url_path."""
    current = section_href(url_path)
    for name in PARTIAL_NAMES:
        pattern = marker_re(name)
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise PartialsError(f"expected exactly one partial:{name} block, found {len(matches)}")
        text = pattern.sub(
            lambda m, name=name: render_block(name, partials[name], m.group("indent"), current),
            text,
            count=1,
        )
    return text


def find_pages(repo: Path) -> list[Path]:
    pages: list[Path] = []
    for path in sorted(repo.rglob("*.html")):
        rel = path.relative_to(repo)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        pages.append(path)
    return pages


def build(repo: Path, check: bool = False) -> tuple[list[str], list[str]]:
    """Return (changed_or_stale files, files missing markers)."""
    partials = load_partials(repo)
    changed: list[str] = []
    missing: list[str] = []
    for path in find_pages(repo):
        rel = path.relative_to(repo)
        text = path.read_text(encoding="utf-8")
        if not has_markers(text):
            missing.append(str(rel))
            continue
        try:
            new_text = apply_partials(text, url_path_for(rel), partials)
        except PartialsError as exc:
            raise PartialsError(f"{rel}: {exc}")
        if new_text != text:
            changed.append(str(rel))
            if not check:
                path.write_text(new_text, encoding="utf-8")
    return changed, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="exit non-zero if any page is out of date")
    parser.add_argument("--repo-root", default=None, help="repository root (default: parent of this script)")
    args = parser.parse_args(argv)
    repo = Path(args.repo_root).resolve() if args.repo_root else Path(__file__).resolve().parent.parent

    try:
        changed, missing = build(repo, check=args.check)
    except PartialsError as exc:
        print(f"build_partials: {exc}", file=sys.stderr)
        return 1

    for name in missing:
        print(f"build_partials: {name}: no partial markers", file=sys.stderr)
    if args.check:
        for name in changed:
            print(f"out of date: {name}")
        if changed or missing:
            return 1
        print("partials up to date")
        return 0
    for name in changed:
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

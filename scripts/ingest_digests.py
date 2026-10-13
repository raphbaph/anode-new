#!/usr/bin/env python3
"""Validate editions independently and catch up all unpublished dates."""
from pathlib import Path
from datetime import datetime, timezone
from build_digests import parse_edition, DigestError


def ingest(roots, target, today):
    copied, errors = [], []
    for feed, root in roots.items():
        dest = target / feed
        dest.mkdir(parents=True, exist_ok=True)
        for source in sorted(root.glob('????-??-??.md')):
            if source.stem > today:
                continue
            out = dest / source.name
            try:
                data = source.read_bytes()
                if out.exists() and out.read_bytes() == data:
                    continue
                parse_edition(source, feed)
                out.write_bytes(data)
                copied.append(str(out))
            except (DigestError, OSError) as exc:
                errors.append(str(exc))
    return copied, errors


if __name__ == '__main__':
    roots = {f: Path('/opt/data') / directory / 'public' for f, directory in
             [('reserve', 'reserve_forum_monitor'), ('rootstock', 'rootstock_monitor')]}
    copied, errors = ingest(roots, Path('content/digests'), datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    Path('/opt/data/digest_publisher/ingest_errors.txt').write_text('\n'.join(errors))
    for path in copied:
        print('Imported ' + path)
    for error in errors:
        print('Skipped invalid edition: ' + error)

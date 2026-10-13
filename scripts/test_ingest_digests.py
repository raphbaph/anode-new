import tempfile
import unittest
from pathlib import Path
from ingest_digests import ingest

class IngestTests(unittest.TestCase):
    def test_invalid_feed_does_not_block_valid_backlog(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            roots = {f: base / f for f in ('reserve', 'rootstock')}
            for p in roots.values(): p.mkdir()
            target = base / 'content'
            (roots['reserve'] / '2026-10-12.md').write_text('invalid')
            (roots['rootstock'] / '2026-10-12.md').write_text('---\nfeed: rootstock\ndate: 2026-10-12\nwindow: 2026-10-11 09:00 to 2026-10-12 09:00 UTC\nquiet: true\nsummary: No activity.\n---\nNo new topics or posts on the forum in this window.')
            copied, errors = ingest(roots, target, '2026-10-13')
            self.assertEqual(len(copied), 1)
            self.assertEqual(len(errors), 1)
            self.assertTrue((target / 'rootstock/2026-10-12.md').exists())
            self.assertFalse((target / 'reserve/2026-10-12.md').exists())
            copied, errors = ingest(roots, target, '2026-10-13')
            self.assertEqual(copied, [])

if __name__ == '__main__': unittest.main()

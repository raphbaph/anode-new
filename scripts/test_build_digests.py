import unittest
import tempfile
from pathlib import Path
from build_digests import parse_edition, DigestError, QUIET_LINE

class QuietEditionTests(unittest.TestCase):
    def parse(self, body):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / '2026-10-11.md'
            p.write_text('---\nfeed: reserve\ndate: 2026-10-11\nwindow: 2026-10-10 09:15 to 2026-10-11 09:15 UTC\nquiet: true\nsummary: No new forum activity.\n---\n\n' + body)
            return parse_edition(p, 'reserve')

    def test_quiet_empty_section_headings_are_ignored(self):
        edition = self.parse('## Proposals and RFCs\n## New topics\n## Discussion by topic\n## Sentiment\n## What to watch\n\n' + QUIET_LINE)
        self.assertIn(QUIET_LINE, edition.body_html)
        self.assertNotIn('<h2', edition.body_html)

    def test_quiet_substantive_content_is_rejected(self):
        with self.assertRaises(DigestError):
            self.parse('## New topics\n- A new proposal appeared.\n' + QUIET_LINE)

    def test_canonical_quiet_edition_still_works(self):
        self.assertIn(QUIET_LINE, self.parse(QUIET_LINE).body_html)

if __name__ == '__main__':
    unittest.main()

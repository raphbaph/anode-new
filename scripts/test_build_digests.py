import unittest
import tempfile
from pathlib import Path
from datetime import date
from build_digests import (parse_edition, DigestError, QUIET_LINE, Edition, build_latest_block,
                           build_hub_page, build_day_page, update_homepage, LATEST_START, LATEST_END, DISCLAIMER)
import build_partials

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

    def test_quiet_no_schedule_note_is_ignored(self):
        edition = self.parse(QUIET_LINE + '\n\n## What to watch\nNothing scheduled in this window.')
        self.assertEqual(edition.body_html, self.parse(QUIET_LINE).body_html)

    def test_quiet_substantive_content_is_rejected(self):
        with self.assertRaises(DigestError):
            self.parse('## New topics\n- A new proposal appeared.\n' + QUIET_LINE)

    def test_canonical_quiet_edition_still_works(self):
        self.assertIn(QUIET_LINE, self.parse(QUIET_LINE).body_html)

def make_edition(feed, iso, summary):
    return Edition(feed=feed, date=date.fromisoformat(iso), window='w', quiet=False, summary=summary,
                   body_html='<p>x</p>', path=Path(iso + '.md'))


class LatestDigestsTests(unittest.TestCase):
    editions = {
        'reserve': [make_edition('reserve', '2026-10-18', 'Old.'), make_edition('reserve', '2026-10-19', 'Newest reserve.')],
        'rootstock': [],
    }

    def test_block_uses_latest_edition_and_empty_state(self):
        block = '\n'.join(build_latest_block(self.editions))
        self.assertIn('Newest reserve.', block)
        self.assertIn('/digests/reserve/2026-10-19/', block)
        self.assertNotIn('Old.', block)
        self.assertIn('No editions published yet', block)
        self.assertIn('/digests/rootstock/', block)
        self.assertIn(DISCLAIMER, block)

    def test_update_homepage_rewrites_only_the_marked_block_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            page = repo / 'index.html'
            page.write_text(f'<main>\n  <p>keep</p>\n  {LATEST_START}\n  stale\n  {LATEST_END}\n  <p>keep too</p>\n</main>\n')
            changed = []
            update_homepage(repo, self.editions, changed)
            first = page.read_text()
            self.assertEqual(changed, ['index.html'])
            self.assertNotIn('stale', first)
            self.assertIn('Newest reserve.', first)
            self.assertIn('<p>keep</p>', first)
            self.assertIn('<p>keep too</p>', first)
            changed.clear()
            update_homepage(repo, self.editions, changed)
            self.assertEqual(changed, [])
            self.assertEqual(page.read_text(), first)

    def test_update_homepage_requires_markers(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'index.html').write_text('<main></main>')
            with self.assertRaises(DigestError):
                update_homepage(Path(d), self.editions, [])


class SharedPartialsTests(unittest.TestCase):
    def test_generated_pages_carry_the_shared_partials(self):
        repo = Path(__file__).resolve().parent.parent
        partials = build_partials.load_partials(repo)
        pages = {
            '/digests/': build_hub_page(self.eds()),
            '/digests/reserve/2026-10-19/': build_day_page('reserve', self.eds()['reserve'][-1], None, None),
        }
        for url_path, html_text in pages.items():
            self.assertEqual(html_text.count('<!-- partial:header -->'), 1)
            self.assertEqual(html_text.count('<!-- partial:footer -->'), 1)
            self.assertIn('<a href="/digests/" aria-current="page">Digests</a>', html_text)
            self.assertEqual(build_partials.apply_partials(html_text, url_path, partials), html_text)

    def eds(self):
        return {'reserve': [make_edition('reserve', '2026-10-19', 'Newest reserve.')], 'rootstock': []}


if __name__ == '__main__':
    unittest.main()

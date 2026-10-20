import contextlib
import io
import re
import tempfile
import unittest
from pathlib import Path

import build_partials as bp

HEADER = '<header class="site-header">\n  <nav>\n    <a href="/practice/">Practice</a>\n    <a href="/research/">Research</a>\n    <a href="/tools/">Tools</a>\n    <a href="/digests/">Digests</a>\n    <a href="/about/">About</a>\n  </nav>\n</header>\n'
FOOTER = '<footer class="site-footer"><p>Footer</p></footer>\n'
PAGE = (
    "<body>\n"
    "  <div>\n"
    "    <!-- partial:header -->\n"
    "    stale header\n"
    "    <!-- /partial:header -->\n"
    "    <main></main>\n"
    "    <!-- partial:footer -->\n"
    "    <!-- /partial:footer -->\n"
    "  </div>\n"
    "</body>\n"
)


class SectionTests(unittest.TestCase):
    def test_section_mapping(self):
        cases = {
            "/decision-systems/": "/practice/",
            "/incentive-design/": "/practice/",
            "/coordination-architecture/": "/practice/",
            "/practice/": "/practice/",
            "/research/": "/research/",
            "/research/eusd-economics-lab/": "/research/",
            "/tools/": "/tools/",
            "/simulators/irv/": "/tools/",
            "/digests/reserve/2026-10-10/": "/digests/",
            "/about/": "/about/",
            "/": None,
            "/privacy/": None,
        }
        for path, expected in cases.items():
            self.assertEqual(bp.section_href(path), expected, path)

    def test_url_path_for(self):
        self.assertEqual(bp.url_path_for(Path("index.html")), "/")
        self.assertEqual(bp.url_path_for(Path("research/index.html")), "/research/")
        self.assertEqual(bp.url_path_for(Path("digests/reserve/2026-10-10/index.html")), "/digests/reserve/2026-10-10/")


class ApplyTests(unittest.TestCase):
    partials = {"header": HEADER.strip("\n"), "footer": FOOTER.strip("\n")}

    def test_replaces_between_markers_with_indent(self):
        out = bp.apply_partials(PAGE, "/", self.partials)
        self.assertNotIn("stale header", out)
        self.assertIn('    <header class="site-header">\n      <nav>', out)
        self.assertIn('    <footer class="site-footer"><p>Footer</p></footer>\n    <!-- /partial:footer -->', out)
        self.assertEqual(out.count("<!-- partial:header -->"), 1)

    def test_aria_current_only_on_matching_section(self):
        out = bp.apply_partials(PAGE, "/simulators/irv/", self.partials)
        self.assertEqual(out.count('aria-current="page"'), 1)
        self.assertIn('<a href="/tools/" aria-current="page">Tools</a>', out)
        self.assertNotIn("aria-current", bp.apply_partials(PAGE, "/", self.partials))

    def test_idempotent(self):
        once = bp.apply_partials(PAGE, "/research/", self.partials)
        self.assertEqual(bp.apply_partials(once, "/research/", self.partials), once)

    def test_missing_or_duplicate_block_is_an_error(self):
        with self.assertRaises(bp.PartialsError):
            bp.apply_partials("<body></body>", "/", self.partials)
        with self.assertRaises(bp.PartialsError):
            bp.apply_partials(PAGE + PAGE, "/", self.partials)


def run_main(args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return bp.main(args)


class BuildTests(unittest.TestCase):
    def make_repo(self, base: Path) -> None:
        (base / "partials").mkdir()
        (base / "partials" / "header.html").write_text(HEADER)
        (base / "partials" / "footer.html").write_text(FOOTER)
        (base / "about").mkdir()
        (base / "about" / "index.html").write_text(PAGE)
        (base / "tmp").mkdir()
        (base / "tmp" / "scratch.html").write_text("<p>ignored</p>")

    def test_build_check_and_idempotence(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.make_repo(base)
            self.assertEqual(run_main(["--repo-root", d, "--check"]), 1)
            self.assertEqual(run_main(["--repo-root", d]), 0)
            page = (base / "about" / "index.html").read_text()
            self.assertIn('<a href="/about/" aria-current="page">About</a>', page)
            self.assertEqual((base / "tmp" / "scratch.html").read_text(), "<p>ignored</p>")
            self.assertEqual(run_main(["--repo-root", d, "--check"]), 0)
            self.assertEqual(bp.build(base)[0], [])

    def test_page_without_markers_fails_check(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.make_repo(base)
            (base / "orphan.html").write_text("<p>no markers</p>")
            run_main(["--repo-root", d])
            self.assertEqual(run_main(["--repo-root", d, "--check"]), 1)


class RepoTests(unittest.TestCase):
    def test_real_repo_is_up_to_date(self):
        repo = Path(__file__).resolve().parent.parent
        changed, missing = bp.build(repo, check=True)
        self.assertEqual((changed, missing), ([], []))

    def test_real_partials_use_root_absolute_links(self):
        repo = Path(__file__).resolve().parent.parent
        for name in bp.PARTIAL_NAMES:
            text = (repo / "partials" / f"{name}.html").read_text()
            for href in re.findall(r'(?:href|src)="([^"]+)"', text):
                self.assertTrue(href.startswith(("/", "mailto:")), href)


if __name__ == "__main__":
    unittest.main()

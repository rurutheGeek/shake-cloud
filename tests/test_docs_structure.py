"""Keep the documentation set navigable: front matter, the map, and the nav agree.

A page without front matter drops out of the generated map and out of Obsidian's
property search; a page missing from mkdocs' nav is unreachable on the site.
Both failures are invisible when reading the page itself, so they are checked here.
"""
from pathlib import Path
import re
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
# Shipped with the theme's JavaScript, not a page of the handbook.
EXCLUDED = {'assets/js/README.md'}
REQUIRED = ('title', 'updated', 'section', 'audience', 'tags')


def pages():
    for path in sorted(DOCS.rglob('*.md')):
        rel = path.relative_to(DOCS).as_posix()
        if rel not in EXCLUDED:
            yield rel, path


def nav_targets(node, found):
    if isinstance(node, dict):
        for value in node.values():
            nav_targets(value, found)
    elif isinstance(node, list):
        for value in node:
            nav_targets(value, found)
    elif isinstance(node, str):
        found.add(node)
    return found


class DocsStructureTests(unittest.TestCase):
    def test_every_page_carries_front_matter(self):
        for rel, path in pages():
            with self.subTest(page=rel):
                text = path.read_text(encoding='utf-8')
                self.assertTrue(text.startswith('---\n'), 'front matter is missing')
                meta = yaml.safe_load(text.split('\n---\n', 1)[0][4:])
                for key in REQUIRED:
                    self.assertIn(key, meta)
                self.assertRegex(str(meta['updated']), r'^\d{4}-\d{2}-\d{2}$')
                self.assertTrue(meta['tags'], 'at least one tag is needed for the graph')

    def test_every_page_shows_the_same_meta_line(self):
        # The date has to be readable on the published site too, not only in Obsidian.
        for rel, path in pages():
            with self.subTest(page=rel):
                text = path.read_text(encoding='utf-8')
                meta = yaml.safe_load(text.split('\n---\n', 1)[0][4:])
                self.assertIn(f"> **更新日** {meta['updated']} ・ **区分** {meta['section']}", text)

    def test_every_page_is_reachable_from_the_nav(self):
        config = yaml.safe_load(
            re.sub(r'!!\S+', '', (ROOT / 'mkdocs.yml').read_text(encoding='utf-8')))
        listed = nav_targets(config['nav'], set())
        self.assertEqual(sorted({rel for rel, _ in pages()} - listed), [])

    def test_the_generated_map_is_up_to_date(self):
        result = subprocess.run(
            ['python3', str(ROOT / 'tools/docs-map.py'), '--check'],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

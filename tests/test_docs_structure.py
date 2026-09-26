"""Keep the documentation set navigable: front matter, the map, and the nav agree.

A page without front matter drops out of the generated map and out of Obsidian's
property search; a page missing from mkdocs' nav is unreachable on the site.
Both failures are invisible when reading the page itself, so they are checked here.
"""
import os
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

    def test_every_anchor_link_points_at_something(self):
        # MkDocs validates page links but not fragments, so a link to a section
        # that was split out into another page stays silently broken.
        link = re.compile(r'\]\(([^)\s]*)#([^)\s]+)\)')
        heading = re.compile(r'^#{1,6}\s+(.*)$', re.M)
        explicit = re.compile(r'<a id="([^"]+)"')
        anchors = {}

        def slug(text):
            # mkdocs' toc extension: lowercase, drop anything but word chars,
            # spaces and hyphens, then join on hyphens.
            text = re.sub(r'<[^>]+>', '', text)
            text = re.sub(r'[`*_\[\]()]', '', text).strip().lower()
            return re.sub(r'[^\w\- ]', '', text).strip().replace(' ', '-')

        for rel, path in pages():
            text = path.read_text(encoding='utf-8')
            found = set(explicit.findall(text))
            found.update(slug(m) for m in heading.findall(text))
            anchors[rel] = {a for a in found if a}

        broken = []
        for rel, path in pages():
            here = Path(rel).parent
            for target, fragment in link.findall(path.read_text(encoding='utf-8')):
                if target.startswith(('http://', 'https://', 'mailto:')):
                    continue
                page = rel if not target else (here / target).as_posix()
                page = Path(page).as_posix().replace('/./', '/')
                page = Path(os.path.normpath(page)).as_posix()
                if page not in anchors:
                    continue  # the page link itself is mkdocs --strict's job
                if fragment not in anchors[page]:
                    broken.append(f'{rel} -> {page}#{fragment}')
        self.assertEqual(broken, [])

    def test_every_page_is_reachable_from_its_section_hub(self):
        # mkdocs' nav is not the only way in: each section's index.md is the
        # curated entry point a reader actually lands on. A page added to the
        # nav but not to its hub is invisible to anyone browsing the handbook.
        link = re.compile(r'\]\(([^)\s#]+)')
        for section in sorted({Path(rel).parent.as_posix()
                               for rel, _ in pages() if '/' in rel}):
            hub = DOCS / section / 'index.md'
            if not hub.exists():
                continue
            members = {rel for rel, _ in pages()
                       if Path(rel).parent.as_posix() == section
                       and Path(rel).name != 'index.md'}
            reached, frontier = set(), [(section + '/index.md')]
            while frontier:
                current = frontier.pop()
                path = DOCS / current
                if not path.exists():
                    continue
                for target in link.findall(path.read_text(encoding='utf-8')):
                    if target.startswith(('http://', 'https://', 'mailto:')):
                        continue
                    rel = Path(
                        os.path.normpath(str(Path(current).parent / target))).as_posix()
                    if rel in members and rel not in reached:
                        reached.add(rel)
                        frontier.append(rel)
            with self.subTest(section=section):
                self.assertEqual(sorted(members - reached), [])

    def test_the_generated_map_is_up_to_date(self):
        result = subprocess.run(
            ['python3', str(ROOT / 'tools/docs-map.py'), '--check'],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()

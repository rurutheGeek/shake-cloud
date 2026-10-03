import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'cloud/api/internal/server/web'

# Created by portal.js at runtime (list status lines and the empty-filter note),
# so it is not expected in index.html.
RUNTIME_IDS = {'instance-filter-empty'}


class PortalAssetsTests(unittest.TestCase):
    def setUp(self):
        self.html = (WEB / 'index.html').read_text()
        self.portal = (WEB / 'static/portal.js').read_text()
        self.ui = (WEB / 'static/portal-ui.js').read_text()

    def test_template_conditionals_are_balanced(self):
        depth = 0
        for tag in re.findall(r'\{\{-?\s*(if|else|end)\b', self.html):
            if tag == 'if':
                depth += 1
            elif tag == 'end':
                depth -= 1
                self.assertGreaterEqual(depth, 0, 'an {{end}} appears before its {{if}}')
        self.assertEqual(depth, 0, 'a template conditional is not closed')

    def test_the_shared_ui_loads_before_the_portal(self):
        self.assertLess(self.html.index('/static/portal-ui.js'), self.html.index('/static/portal.js'))

    def test_every_id_used_by_the_scripts_exists_in_the_template(self):
        ids = set(re.findall(r'id="([^"{}]+)"', self.html))
        refs = set(re.findall(r"\$\('([^']+)'\)", self.portal + self.ui))
        self.assertEqual(refs - ids - RUNTIME_IDS, set())

    def test_every_view_is_reachable_from_the_menu(self):
        # One view is shown at a time, so a section the menu cannot reach is
        # a section nobody can open.
        navigation = self.html[self.html.index('<nav id="navigation"'):self.html.index('</nav>')]
        linked = set(re.findall(r'href="#([^"]+)"', navigation))
        for match in re.finditer(r'<section id="([^"]+)" data-view(?: data-nav="([^"]+)")?', self.html):
            view, parent = match.group(1), match.group(2)
            self.assertIn(parent or view, linked, view)
        # Everything linked from the menu exists.
        ids = set(re.findall(r'id="([^"{}]+)"', self.html))
        self.assertEqual(linked - ids, set())

    def test_the_menu_is_grouped(self):
        navigation = self.html[self.html.index('<nav id="navigation"'):self.html.index('</nav>')]
        self.assertEqual(re.findall(r'class="nav-heading">([^<]+)<', navigation), ['計算', 'データ', 'アカウント'])
        # The script switches views; without it every section stays visible.
        self.assertIn("section[data-view]", self.ui)
        self.assertIn("aria-current", self.ui)

    def test_the_shared_ui_is_initialised(self):
        # onAction's locking and the dirty-form guard live in PortalUI.init().
        self.assertIn('window.PortalUI.init()', self.portal)

    def test_the_instance_list_has_only_the_basic_columns(self):
        # ID, image, disk, groups and tags belong to the detail view: the list
        # must not grow back into a nine-column table.
        section = re.search(r'<section id="instances-view".*?</section>', self.html, re.S).group(0)
        headings = re.findall(r'<th[^>]*>(.*?)</th>', section, re.S)
        cleaned = [re.sub(r'<[^>]+>', '', heading).strip() for heading in headings]
        self.assertEqual(cleaned, ['選択', '名前', '状態', 'IP', '構成', '所有者'])

    def test_the_bulk_buttons_start_disabled(self):
        # Without a selection, or before the script loads, they must not act.
        section = re.search(r'<section id="instances-view".*?</section>', self.html, re.S).group(0)
        for button in ('instance-start', 'instance-stop', 'instance-reboot', 'instance-delete'):
            tag = re.search(rf'<button id="{button}"[^>]*>', section).group(0)
            self.assertIn('disabled', tag)

    def test_no_table_header_is_empty(self):
        # axe-core flags an action column with an empty <th> (empty-table-header).
        self.assertNotRegex(self.html, r'<th>\s*</th>')

    def test_credentials_are_not_written_to_browser_storage(self):
        for source in (self.portal, self.ui):
            self.assertNotRegex(source, r'\b(localStorage|sessionStorage)\.[A-Za-z]')
            self.assertNotIn('document.cookie', source)


if __name__ == '__main__':
    unittest.main()

"""Every registry image a stack runs is pinned by a digest that Git reviews.

`manage.py lock` は lock が無ければ配備先で pull して digest を決める。lock が
リポジトリに無いスタックは、どの digest が動いているかをGitで追えず、再配備の
たびに `:latest` の中身が変わりうる。ここでは全スタックの lock がリポジトリに
あり、compose のサービスを漏れなく覆っていることを確かめる。
"""
import re
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DIGEST = re.compile(r'@sha256:[0-9a-f]{64}$')

# まだ lock をリポジトリへ入れられていないスタック。理由が解けたら行を消す。
# 増やさない。
UNPINNED = {
    # game1（Bazzite）へ構成管理の鍵で入れず、稼働中の digest を読めていない。
    'stacks/romm/compose.yaml',
    # 配備先を確認できておらず、稼働中の digest を読めていない。
    'stacks/pokemon-ai/ollama/compose.yaml',
}


def compose_files():
    names = subprocess.check_output(
        ['git', 'ls-files', 'stacks/**/compose.yaml', 'stacks/compose.yaml', 'cloud/compose.yaml'],
        cwd=ROOT, text=True).split()
    return sorted(names)


def default_image(image):
    """`${NAME:-default}` を既定値へ展開する。"""
    return re.sub(r'\$\{[A-Z0-9_]+:-([^}]*)\}', r'\1', image)


def needs_a_lock(service):
    image = default_image(service.get('image', ''))
    if not image or 'build' in service or image.endswith(':local'):
        return False
    return not DIGEST.search(image)


class ImageLockTests(unittest.TestCase):
    def test_every_registry_image_is_pinned_in_the_repository(self):
        for name in compose_files():
            if name in UNPINNED:
                continue
            path = ROOT / name
            services = yaml.safe_load(path.read_text(encoding='utf-8')).get('services', {})
            wanted = {key for key, service in services.items() if needs_a_lock(service)}
            if not wanted:
                continue
            lock_path = path.with_name('compose.lock.yaml')
            self.assertTrue(lock_path.exists(), f'{name}: compose.lock.yaml がリポジトリに無い')
            locked = yaml.safe_load(lock_path.read_text(encoding='utf-8'))['services']
            self.assertEqual(wanted - set(locked), set(), f'{name}: lock に無いサービス')
            for key in wanted:
                self.assertRegex(locked[key]['image'], DIGEST, f'{name}: {key}')
                repository = default_image(services[key]['image']).split('@')[0]
                repository = re.sub(r':[^:/]+$', '', repository)
                self.assertTrue(
                    locked[key]['image'].split('@')[0].endswith(repository),
                    f'{name}: {key} の lock が別のリポジトリを指している')

    def test_the_exceptions_are_real_and_still_unpinned(self):
        # 例外の一覧が古くならないよう、lock が入ったら行を消させる。
        for name in UNPINNED:
            self.assertTrue((ROOT / name).exists(), name)
            self.assertFalse((ROOT / name).with_name('compose.lock.yaml').exists(),
                             f'{name}: lock が入ったので UNPINNED から外す')


if __name__ == '__main__':
    unittest.main()

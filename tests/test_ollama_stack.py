"""Safety checks for the shared game1 Ollama unit."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / 'stacks/pokemon-ai/ollama'


def load_manage():
    spec = importlib.util.spec_from_file_location('ollama_manage', STACK / 'manage.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ComposeTests(unittest.TestCase):
    def setUp(self):
        self.compose = yaml.safe_load((STACK / 'compose.yaml').read_text(encoding='utf-8'))
        self.service = self.compose['services']['ollama']

    def test_the_host_listener_is_loopback_only_and_model_cache_is_separate(self):
        self.assertEqual(self.service['ports'], ['127.0.0.1:${OLLAMA_PORT:-11434}:11434'])
        self.assertIn('${STORAGE_ROOT:-/srv/game1/ollama}/models:/root/.ollama',
                      self.service['volumes'])

    def test_the_shared_network_has_a_stable_name(self):
        self.assertEqual(self.service['networks'], ['game1-ai'])
        self.assertEqual(self.compose['networks']['game1-ai']['name'], 'game1-ai')
        self.assertTrue(self.compose['networks']['game1-ai']['external'])

    def test_parallelism_and_loaded_models_are_limited_by_default(self):
        env = self.service['environment']
        self.assertEqual(env['OLLAMA_NUM_PARALLEL'], '${OLLAMA_NUM_PARALLEL:-1}')
        self.assertEqual(env['OLLAMA_MAX_LOADED_MODELS'], '${OLLAMA_MAX_LOADED_MODELS:-1}')
        self.assertIn('127.0.0.1', ' '.join(self.service['ports']))


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.manage = load_manage()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.patch = patch.object(self.manage, 'ROOT', self.root)
        self.patch.start()
        (self.root / '.env.example').write_text(
            'STORAGE_ROOT=/srv/game1/ollama\nOLLAMA_PORT=11434\n', encoding='utf-8')

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def test_init_rejects_state_inside_project(self):
        (self.root / '.env').write_text(f'STORAGE_ROOT={self.root / "state"}\n', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.manage.init()

    def test_init_creates_private_env_and_model_directory(self):
        state = self.root.parent / f'{self.root.name}-state'
        (self.root / '.env').write_text(f'STORAGE_ROOT={state}\n', encoding='utf-8')
        self.manage.init()
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)
        self.assertTrue((state / 'models').is_dir())
        shutil.rmtree(state)

    def test_pull_rejects_whitespace_and_passes_one_model(self):
        with self.assertRaises(ValueError):
            self.manage.pull('qwen3 4b')
        with patch.object(self.manage, 'compose') as compose:
            self.manage.pull('qwen3:4b')
        compose.assert_called_once_with('exec', '-T', 'ollama', 'ollama', 'pull', 'qwen3:4b')

    def test_missing_shared_network_is_created_explicitly(self):
        with patch('subprocess.run') as run:
            run.return_value.returncode = 1
            self.manage.ensure_network()
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args.args[0][-1], 'game1-ai')

    def test_lock_preserves_a_repository_digest(self):
        (self.root / '.env').write_text('STORAGE_ROOT=/tmp/ollama-state\n', encoding='utf-8')
        (self.root / 'compose.yaml').write_text(
            'services: {ollama: {image: ollama/ollama:latest}}\n', encoding='utf-8')
        responses = [
            type('Result', (), {'stdout': ''})(),
            type('Result', (), {'stdout': json.dumps({'services': {'ollama': {'image': 'ollama/ollama:latest'}}})})(),
        ]
        with patch.object(self.manage, 'compose', side_effect=responses), \
             patch('subprocess.check_output', return_value=json.dumps([{
                 'RepoDigests': ['ollama/ollama@sha256:' + 'b' * 64],
             }]).encode()):
            self.manage.lock()
        lock = yaml.safe_load((self.root / 'compose.lock.yaml').read_text(encoding='utf-8'))
        self.assertRegex(lock['services']['ollama']['image'], r'@sha256:[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()

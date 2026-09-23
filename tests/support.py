"""Shared helpers for the test suite.

The tests are split by the unit they guard and run with
`python3 -m unittest discover -s tests`. Only helpers that were copied into
three or more test files live here, so the module stays small and
standard-library only. Scratch directories made with `scratch_dir` live under
one root that is removed when the test process exits.
"""
import atexit
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

_SCRATCH = tempfile.TemporaryDirectory(prefix='shake-cloud-tests-')
atexit.register(_SCRATCH.cleanup)
_SCRATCH_PATH = Path(_SCRATCH.name)


def read(path):
    """Return a repository file as UTF-8 text."""
    return Path(path).read_text(encoding='utf-8')


def load_module(path, name):
    """Load a deployment script (manage.py, configure.py, ...) by file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def role_task(tasks, name_fragment):
    """Return the first Ansible task whose name contains the fragment."""
    return [item for item in tasks if name_fragment in item.get('name', '')][0]


def scratch_dir(prefix='test-'):
    """Return a new scratch directory, removed when the test process exits."""
    return Path(tempfile.mkdtemp(prefix=prefix, dir=_SCRATCH_PATH))


def ansible_playbook():
    """Return the ansible-playbook next to the running interpreter, or skip."""
    candidate = Path(sys.executable).with_name('ansible-playbook')
    if candidate.exists():
        return str(candidate)
    found = shutil.which('ansible-playbook')
    if found:
        return found
    raise unittest.SkipTest('ansible-playbook is not installed')


def syntax_check(playbook, inventory='localhost,'):
    """Run `ansible-playbook --syntax-check` and return the completed process.

    The controller-side temporary directory goes under the test scratch root:
    some hosts expose a read-only home, and leaving ansible's temp dirs in /tmp
    accumulates when the suite runs often.
    """
    environment = dict(os.environ)
    environment.setdefault('ANSIBLE_LOCAL_TEMP', str(_SCRATCH_PATH / 'ansible'))
    return subprocess.run(
        [ansible_playbook(), '--syntax-check', '-i', inventory, str(playbook)],
        cwd=ROOT, capture_output=True, text=True, env=environment)

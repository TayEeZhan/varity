"""The sandboxed reader child runs with python -I, which ignores PYTHONPATH (Replit's package path)."""

import json
import os
import subprocess
import sys

from intake import readers

PROBE = "import json, os, sys; sys.path.extend(json.loads(os.environ.get('VARITY_CHILD_PATH', '[]'))); import intake.readers"


def test_isolated_child_needs_the_parent_path():
    bare = subprocess.run([sys.executable, "-I", "-c", PROBE], capture_output=True, text=True, env={**os.environ, "VARITY_CHILD_PATH": "[]"})
    assert bare.returncode != 0  # like Replit: the package is only on the parent's path
    given = subprocess.run([sys.executable, "-I", "-c", PROBE], capture_output=True, text=True,
                           env={**os.environ, "VARITY_CHILD_PATH": json.dumps(readers._package_dirs())})
    assert given.returncode == 0, given.stderr


def test_package_dirs_are_absolute_and_exclude_cwd():
    dirs = readers._package_dirs()
    assert dirs and all(os.path.isabs(p) for p in dirs) and "" not in dirs

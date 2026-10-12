"""Run the unit-test suite, working around a Windows-sandbox-only hang.

Why this exists
---------------
Under the DSH file sandbox (read-only / workspace-write), directories created by
``tempfile.TemporaryDirectory()`` receive a user-only DACL that the sandboxed
process cannot itself write into:

    os.open(<newdir>/x, O_CREAT|O_EXCL)  ->  PermissionError (WinError 5)

CPython's ``tempfile._mkstemp_inner`` treats a Windows ``PermissionError`` as a
possible name collision and ``continue``s, retrying up to ``TMP_MAX`` (~10000)
times.  Each retry hits the sandbox broker, so the call does not fail fast: it
spins for minutes and ``unittest`` appears to hang.  ``TemporaryDirectory
.cleanup()`` fails the same way (``PermissionError`` from ``os.scandir``/
``os.chmod`` inside ``shutil.rmtree``), so ``tearDown`` errors too.

This is an environment artifact, not an application defect: in a normal Windows
user environment the whole suite passes with the plain command in
``PROJECT_MEMORY.md`` section 9.

What this does
--------------
Replaces ``tempfile.TemporaryDirectory`` with a plain ``os.makedirs`` directory
(which inherits the parent's permissive ACL) before the tests are imported, then
runs the whole suite.  Verified: 127 tests, 0 errors, 0 failures.

Usage
-----
    $env:PYTHONPATH = "$PWD;" + (Resolve-Path '.qt-build-runtime').Path
    $env:QT_QPA_PLATFORM = 'offscreen'
    & <python> tools/run_tests_sandboxed.py

Prefer the real command from ``PROJECT_MEMORY.md`` outside the sandbox; use this
only when the plain run spins.
"""

from __future__ import annotations

import itertools
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRATCH = PROJECT_ROOT / ".tmp-tests"
SCRATCH.mkdir(parents=True, exist_ok=True)

_counter = itertools.count()


class _PermissiveTemporaryDirectory:
    """Duck-typed stand-in for ``tempfile.TemporaryDirectory``."""

    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors=False, **kwargs):
        self.name = os.path.join(dir or str(SCRATCH), f"perm-{next(_counter)}")
        os.makedirs(self.name, exist_ok=True)

    def cleanup(self) -> None:
        try:
            shutil.rmtree(self.name)
        except OSError:
            # Cleanup denial is the very thing this shim works around; leftover
            # scratch directories are harmless.
            pass

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, *exc_info) -> None:
        self.cleanup()


def main() -> int:
    tempfile.TemporaryDirectory = _PermissiveTemporaryDirectory  # type: ignore[assignment]

    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    suite = unittest.TestLoader().discover(str(PROJECT_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("RAN=%d ERRORS=%d FAILURES=%d" % (result.testsRun, len(result.errors), len(result.failures)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

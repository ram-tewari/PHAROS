# Manual scripts (NOT pytest tests)

These files are named `test_*.py` for historical reasons but are **hand-run
scripts**, not automated tests. Several call `sys.exit()` at import time or hit
a live backend over HTTP, which crashes or hangs pytest collection. They are
excluded from the suite via `--ignore=tests/manual` in `pytest.ini`.

Run one directly when you want it, e.g.:

    python tests/manual/test_cli_backend_final.py

If you convert one into real assertions (no `sys.exit`, no live-server
dependency, functions named `test_*`), move it back under `tests/` so CI runs it.

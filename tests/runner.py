"""Dependency-free test runner:  python tests/runner.py   (pytest also works)."""
import importlib.util
import sys
import traceback
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parent / "src"))
sys.path.insert(0, str(here))
failed = passed = 0
for f in sorted(here.glob("test_*.py")):
    spec = importlib.util.spec_from_file_location(f.stem, f)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for name in sorted(dir(mod)):
        fn = getattr(mod, name)
        if name.startswith("test_") and callable(fn) and fn.__code__.co_argcount == 0:
            try:
                fn()
                passed += 1
            except Exception:
                failed += 1
                print(f"FAIL {f.name}::{name}")
                traceback.print_exc()
print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)

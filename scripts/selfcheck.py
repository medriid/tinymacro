#!/usr/bin/env python3
"""Dependency-light test runner for environments without pytest installed.

It provides just enough of the pytest API (``raises``, ``importorskip``,
``fixture``, ``mark``) plus ``tmp_path`` and ``monkeypatch`` fixtures to execute
Tiny Macro's non-GUI tests. GUI tests self-skip via ``importorskip("PyQt6")``.

Run from the project root:  python scripts/selfcheck.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import inspect
from pathlib import Path
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS = ROOT / "tests"
sys.path.insert(0, str(SRC))


class Skipped(Exception):
    pass


class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(f"Expected {self.exc.__name__} but nothing was raised")
        return issubclass(exc_type, self.exc)


class _MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value=None, raising=True):
        if isinstance(target, str):
            module_name, _, attr = target.rpartition(".")
            module = importlib.import_module(module_name)
            old = getattr(module, attr, None)
            self._undo.append(lambda: setattr(module, attr, old))
            setattr(module, attr, name)
        else:
            old = getattr(target, name, None)
            self._undo.append(lambda: setattr(target, name, old))
            setattr(target, name, value)

    def setitem(self, mapping, key, value):
        had = key in mapping
        old = mapping.get(key)
        def undo():
            if had:
                mapping[key] = old
            else:
                mapping.pop(key, None)
        self._undo.append(undo)
        mapping[key] = value

    def undo(self):
        for fn in reversed(self._undo):
            fn()
        self._undo.clear()


def _make_pytest_stub():
    stub = types.ModuleType("pytest")

    def raises(exc):
        return _Raises(exc)

    def importorskip(name, *args, **kwargs):
        try:
            return importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001
            raise Skipped(f"missing {name}: {exc}")

    def fixture(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]):
            return args[0]
        return decorator

    class _Mark:
        def __getattr__(self, _name):
            def decorator(fn=None, **_kw):
                return fn if fn is not None else (lambda f: f)
            return decorator

    stub.raises = raises
    stub.importorskip = importorskip
    stub.fixture = fixture
    stub.mark = _Mark()
    stub.skip = lambda *a, **k: (_ for _ in ()).throw(Skipped("skip"))
    return stub


def _provide_fixtures(params, tmp_root, monkeypatches):
    kwargs = {}
    for name in params:
        if name == "tmp_path":
            path = Path(tempfile.mkdtemp(dir=tmp_root))
            kwargs[name] = path
        elif name == "monkeypatch":
            mp = _MonkeyPatch()
            monkeypatches.append(mp)
            kwargs[name] = mp
        else:
            raise Skipped(f"unsupported fixture: {name}")
    return kwargs


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(f"selfcheck_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # may raise Skipped at import time
    return module


def main() -> int:
    sys.modules["pytest"] = _make_pytest_stub()
    # Conftest adds src to path for the real suite; emulate it here too.
    passed = failed = skipped = 0
    failures = []
    with tempfile.TemporaryDirectory() as tmp_root:
        for path in sorted(TESTS.glob("test_*.py")):
            try:
                module = _load_module(path)
            except Skipped as exc:
                skipped += 1
                print(f"SKIP module {path.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                failed += 1
                failures.append((path.name, "<import>", repr(exc)))
                print(f"ERROR importing {path.name}: {exc!r}")
                continue
            for name, fn in sorted(vars(module).items()):
                if not (name.startswith("test_") and inspect.isfunction(fn)):
                    continue
                params = list(inspect.signature(fn).parameters)
                monkeypatches: list[_MonkeyPatch] = []
                try:
                    kwargs = _provide_fixtures(params, tmp_root, monkeypatches)
                    fn(**kwargs)
                    passed += 1
                except Skipped as exc:
                    skipped += 1
                    print(f"SKIP {path.name}::{name}: {exc}")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    failures.append((path.name, name, repr(exc)))
                    print(f"FAIL {path.name}::{name}: {exc!r}")
                finally:
                    for mp in monkeypatches:
                        mp.undo()
    print("\n" + "=" * 60)
    print(f"passed={passed} failed={failed} skipped={skipped}")
    if failures:
        print("\nFailures:")
        for file, test, err in failures:
            print(f"  {file}::{test} -> {err}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

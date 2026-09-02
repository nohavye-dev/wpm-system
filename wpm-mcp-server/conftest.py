"""Minimal pytest glue for the script-style test files at this repo root.

The repository's test_*.py files are assertion scripts (module-level asserts +
prints) rather than pytest test functions, so pytest would collect nothing from
them. This conftest makes pytest collect each test_*.py file as a single test
item that executes the file via runpy; a failed assert fails the test.

It overrides the firstresult hook pytest_pycollect_makemodule so the default
Python module collector does not also pick up the same files (avoiding a
double execution of their module-level side effects).
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest


class ScriptItem(pytest.Item):
    def __init__(self, name: str, parent, path: Path) -> None:
        super().__init__(name, parent)
        self.path = path

    def runtest(self) -> None:
        runpy.run_path(str(self.path))

    def reportinfo(self):
        return self.path, 0, f"script test: {self.path.name}"


class ScriptModule(pytest.Module):
    def collect(self):
        yield ScriptItem.from_parent(self, name=self.path.stem, path=self.path)


def pytest_pycollect_makemodule(module_path: Path, parent):
    if module_path.suffix == ".py" and module_path.parent == Path(__file__).resolve().parent:
        return ScriptModule.from_parent(parent, path=module_path)
    return None

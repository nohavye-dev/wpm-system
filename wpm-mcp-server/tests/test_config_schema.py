"""Config schema generation coverage + loader tolerance for '$' meta-keys.

Run with the project venv:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "wpm-mcp-server" / "src"))

import generate_config_schema as gen  # noqa: E402
from wpm_mcp_server.config.settings import DomainSettings, Settings, load_settings  # noqa: E402


def field_paths(cls: type, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    hints = __import__("typing").get_type_hints(cls)
    for field in dataclasses.fields(cls):
        dotted = f"{prefix}{field.name}"
        paths.add(dotted)
        tp = gen.unwrap_optional(hints.get(field.name, field.type))
        if dataclasses.is_dataclass(tp) and isinstance(tp, type):
            paths |= field_paths(tp, f"{dotted}.")
    return paths


class TestSchemaCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.schema = gen.build_schema()
        self.example = gen.build_example()

    def test_every_settings_field_is_in_schema(self) -> None:
        def collect(node: dict, prefix: str = "") -> set[str]:
            found: set[str] = set()
            for name, sub in node["properties"].items():
                dotted = f"{prefix}{name}"
                found.add(dotted)
                if "properties" in sub:
                    found |= collect(sub, f"{dotted}.")
            return found

        self.assertEqual(field_paths(Settings), collect(self.schema))

    def test_example_keys_are_schema_keys(self) -> None:
        example_root = set(self.example)
        schema_root = set(self.schema["properties"])
        self.assertTrue(example_root <= schema_root)
        domain_schema = set(self.schema["properties"]["domain"]["properties"])
        self.assertTrue(set(self.example["domain"]) <= domain_schema)

    def test_new_keys_present(self) -> None:
        for key in ("rag_similarity_threshold", "rag_max_items"):
            self.assertIn(key, self.schema["properties"])
            self.assertIn(key, self.example)


class TestLoaderTolerance(unittest.TestCase):
    def test_dollar_meta_key_is_tolerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "wpm.config.json"
            path.write_text(json.dumps({
                "$schema": "/somewhere/wpm.config.schema.json",
                "db_path": ".wpm/wpm.db",
            }), encoding="utf-8")
            settings = load_settings(path)
            self.assertEqual(settings.db_path, ".wpm/wpm.db")

    def test_unknown_typo_key_still_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "wpm.config.json"
            path.write_text(json.dumps({"rag_max_item": 3}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_settings(path)


if __name__ == "__main__":
    unittest.main()

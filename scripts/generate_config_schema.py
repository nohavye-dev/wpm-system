#!/usr/bin/env python3
"""Generate the JSON Schema and the example for wpm.config.json.

Single source of truth: the Settings dataclasses in
wpm_mcp_server/config/settings.py. Types, nesting and defaults are
introspected — hand-edits to the emitted files would be overwritten.

Usage (from the repository root, ideally with the project venv):
    python3 scripts/generate_config_schema.py           # writes both files
    python3 scripts/generate_config_schema.py --check   # exit 1 on drift

Descriptions live in DESCRIPTIONS below (dotted paths); prose is the only
hand-maintained part.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import sys
import types
import typing

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "wpm-mcp-server" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wpm_mcp_server.config.settings import Settings  # noqa: E402

SCHEMA_TARGET = REPO_ROOT / "wpm-mcp-server" / "wpm.config.schema.json"
EXAMPLE_TARGET = REPO_ROOT / "wpm-mcp-server" / "wpm.config.example.json"

# Curated presentation values; everything else comes from dataclass defaults.
EXAMPLE_OVERRIDES: dict[str, object] = {
    "db_path": ".wpm/wpm.db",
    "response_language": "auto",
    "verification_command_patterns": ["\\bmy-custom-runner\\b"],
}

DESCRIPTIONS: dict[str, str] = {
    "db_path": "Path of the SQLite memory database, relative to this file. Required for an active server.",
    "confidence_threshold": "Minimum confidence for an entry to enter the <project-rules> block.",
    "verification_command_patterns": "Extra regexes ADDED to the built-in strong-evidence command list.",
    "response_language": 'Agent response language ("auto" or null = user language; fixed value forces it). Never governs stored content.',
    "rag_similarity_threshold": "Minimum cosine similarity between the raw user message and an entry for the RAG pop-in.",
    "rag_max_items": "Maximum entries injected per turn by the RAG pop-in.",
    "domain.provenance.base_confidence": "Starting confidence per source type.",
    "domain.provenance.default": "Default provenance confidence.",
    "domain.decay.lambda_per_type": "Confidence erosion rate per entry type.",
    "domain.decay.default_lambda": "Default erosion rate.",
    "domain.evidence.confirm_weight": "Confidence delta per evidence type supporting an entry.",
    "domain.evidence.contradict_weight": "Confidence delta per evidence type contradicting an entry.",
    "domain.validation.score_min": "Lower bound of the validation score.",
    "domain.validation.score_max": "Upper bound of the validation score.",
    "domain.validation.dedup_window_seconds": "Window during which identical evidence events are deduplicated.",
    "domain.retrieval.weight_similarity": "Composite score weight: similarity.",
    "domain.retrieval.weight_confidence": "Composite score weight: confidence.",
    "domain.retrieval.weight_centrality": "Composite score weight: centrality.",
    "domain.retrieval.min_similarity": "Similarity floor below which a candidate entry is discarded.",
    "domain.expansion.hop_decay": "Multiplier applied per graph-expansion hop.",
    "domain.expansion.min_confidence": "Confidence floor for expansion results.",
    "domain.expansion.top_n_candidates": "Vector-search candidate pool size.",
    "domain.expansion.auto_link_similarity_threshold": "Similarity above which two entries are auto-linked.",
    "domain.expansion.contradiction_alert_threshold": "Score threshold triggering contradiction alerts.",
}


def unwrap_optional(tp: object) -> object:
    """Return the non-None member of `X | None`, else the type itself."""
    if typing.get_origin(tp) in (typing.Union, types.UnionType):
        members = [a for a in typing.get_args(tp) if a is not type(None)]
        if len(members) == 1:
            return members[0]
    return tp


def default_of(field: dataclasses.Field) -> object:
    if field.default is not dataclasses.MISSING:
        return field.default
    if field.default_factory is not dataclasses.MISSING:
        value = field.default_factory()
        # Only mutable containers need deep-copying into plain structures;
        # nested dataclass instances are recursed into by the callers.
        if isinstance(value, (dict, list)):
            return json.loads(json.dumps(value))
        return value
    raise ValueError(f"no default for {field.name}")


def leaf_schema(tp: object) -> dict:
    origin = typing.get_origin(tp)
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if tp is str:
        return {"type": "string"}
    if origin in (list, typing.List):
        return {"type": "array", "items": leaf_schema(typing.get_args(tp)[0])}
    if origin in (dict, typing.Dict):
        return {"type": "object", "additionalProperties": leaf_schema(typing.get_args(tp)[1])}
    raise ValueError(f"unsupported leaf type {tp!r}")


def schema_for(cls: type, prefix: str = "") -> dict:
    # PEP 649 (py3.14): annotations are lazy — resolve them explicitly.
    hints = typing.get_type_hints(cls)
    properties: dict[str, object] = {}
    for field in dataclasses.fields(cls):
        dotted = f"{prefix}{field.name}"
        description = DESCRIPTIONS.get(dotted)
        tp = unwrap_optional(hints.get(field.name, field.type))

        node: dict[str, object]
        if dataclasses.is_dataclass(tp) and isinstance(tp, type):
            node = {"description": description or f"{tp.__name__} sub-section.", **schema_for(tp, f"{dotted}.")}
        else:
            node = leaf_schema(tp)
            if description:
                node["description"] = description

        properties[field.name] = node

    return {"type": "object", "properties": properties, "additionalProperties": False}


def build_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "wpm.config.json",
        "description": "Configuration of the WPM weighted persistent memory system. Unknown keys fail loudly at server startup; '$'-prefixed meta-keys are tolerated for editors.",
        "type": "object",
        "$comment": "Generated by scripts/generate_config_schema.py — do not edit by hand.",
        **schema_for(Settings),
        "patternProperties": {"^\\$": {}},
    }


def build_example() -> dict:
    def walk(cls: type, prefix: str = "") -> dict:
        out: dict[str, object] = {}
        for field in dataclasses.fields(cls):
            dotted = f"{prefix}{field.name}"
            if dotted in EXAMPLE_OVERRIDES:
                out[field.name] = EXAMPLE_OVERRIDES[dotted]
                continue
            value = default_of(field)
            out[field.name] = walk(type(value), f"{dotted}.") if dataclasses.is_dataclass(value) else value
        return out

    return walk(Settings)


def dump(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed files drift from Settings")
    args = parser.parse_args()

    outputs = {
        SCHEMA_TARGET: build_schema(),
        EXAMPLE_TARGET: build_example(),
    }
    if args.check:
        drifted = [str(path) for path, doc in outputs.items() if path.read_text(encoding="utf-8") != dump(doc)]
        for path in drifted:
            print(f"drifted: {path}", file=sys.stderr)
        return 1 if drifted else 0

    for path, doc in outputs.items():
        path.write_text(dump(doc), encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

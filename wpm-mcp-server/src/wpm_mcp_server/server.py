"""Pure-MCP memory server (FastMCP): tools, resources, prompts, instructions.

Replaces the old opencode plugin. Everything the plugin used to do through
opencode-specific hooks is now expressed with standard MCP primitives so the
server works with any MCP host:

- the 16 usage rules live in initialize.instructions (read once per session)
  and are re-readable via the wpm://memory-rules resource;
- project rules/conventions are exposed as the wpm://project-rules resource,
  recomputed from memory and invalidated (with a resources/updated
  notification) on every mutation;
- record_execution captures test/build/lint results as execution_verified
  evidence without relying on a tool.execute.after hook;
- the wpm workflows are exposed as MCP prompts (persist, audit, learn, map,
  bootstrap, patterns).

Host-agnostic activation: the server is active when it can resolve a database
path — from wpm.config.json (relative to its own location, not the host's
cwd) or WPM_DB_PATH. Without one it stays inert: it starts and lists its
tools, but every tool returns a clear "not activated" error.
"""

import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Context

from wpm_mcp_server import db
from wpm_mcp_server.behavior import (
    MEMORY_USAGE_RULES,
    PROJECT_RULES_QUERY,
    PROJECT_RULES_TOKEN_BUDGET,
    VERIFICATION_COMMAND_PATTERNS,
    build_project_rules_block,
    compile_verification_patterns,
    format_project_rules,
    looks_like_verification_command,
)
from wpm_mcp_server.embeddings import get_provider
from wpm_mcp_server.repository import WpmError, Repository
from wpm_mcp_server.settings import load_settings

NOT_ACTIVATED_MESSAGE = (
    "wpm is not activated in this project: run 'wpm enable' at the project "
    "root (writes wpm.config.json) and launch this MCP server with the "
    "project as its working directory (or set WPM_DB_PATH)."
)

_config_path = Path(os.environ.get("WPM_CONFIG_PATH", "wpm.config.json"))
_has_config = _config_path.exists()
_config_dir = _config_path.resolve().parent if _has_config else Path.cwd()

_settings = load_settings(_config_path)

_db_path = os.environ.get("WPM_DB_PATH") or _settings.db_path
if _db_path:
    DB_PATH = db.resolve_within_root(_db_path, _config_dir)
else:
    DB_PATH = None

mcp = FastMCP(
    name="wpm-server",
    instructions=MEMORY_USAGE_RULES,
)

_repo: Repository | None = None
_project_rules_cache: str | None = None

_verification_patterns, _invalid_patterns = compile_verification_patterns(
    _settings.verification_command_patterns or []
)


def get_repo() -> Repository:
    global _repo
    if _repo is None:
        if DB_PATH is None:
            raise RuntimeError(NOT_ACTIVATED_MESSAGE)
        conn = db.connect(DB_PATH)
        model = os.environ.get("WPM_EMBEDDING_MODEL")
        embedder = get_provider(model)
        _repo = Repository(conn=conn, embedder=embedder, settings=_settings.domain)
    return _repo


async def _on_memory_mutated(ctx: Context | None) -> None:
    """Drop the project-rules cache and tell subscribed clients to reload it."""
    global _project_rules_cache
    _project_rules_cache = None
    try:
        session = ctx.session
        if session is not None:
            await session.send_resource_updated("wpm://project-rules")
    except Exception:
        # Notification is best-effort — the resource itself is always fresh
        # on the next read.
        pass


# --- tools -----------------------------------------------------------------

@mcp.tool(
    description=(
        "Store a new memory entry (doc, archi_decision, learning, convention, "
        "or bug_pattern). CONTENT MUST BE IN ENGLISH. "
        "'source' should be one of: official_doc, observed_code, "
        "tool_execution, agent_inference (unknown sources get a neutral "
        "default confidence). Before storing, run query_context on the "
        "topic: if a near-duplicate already exists, call validate_entry on "
        "it instead of creating a duplicate. Only store durable facts that "
        "will still be true and useful in weeks. Returns the new entry_id "
        "and its initial confidence — this entry starts unvalidated; call "
        "validate_entry with real evidence once it is confirmed."
    )
)
async def store_entry(ctx: Context, type: str, content: str, source: str) -> dict:
    try:
        result = get_repo().store_entry(type_=type, content=content, source=source)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        if isinstance(exc, ValueError):
            return {"error": True, "message": f"invalid type: {exc}"}
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Hybrid retrieval: vector similarity + confidence weighting + graph "
        "centrality, plus 1-hop graph expansion for associative recall. "
        "Call this tool at the start of every substantive answer and before "
        "reading files or searching the codebase (MEMORY FIRST). Query text "
        "should be in English for best similarity matching. Returns "
        "direct_matches (strong hits), related_context (associative, "
        "lower-confidence recall via linked entries), and conflicts (entries "
        "with an active 'contradicts' link) — always check conflicts before "
        "relying on a direct_match."
    )
)
def query_context(query: str, min_confidence: float = 0.0, token_budget: int = 2000) -> dict:
    try:
        return get_repo().query_context(
            query=query, min_confidence=min_confidence, token_budget=token_budget
        )
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Record EXTERNAL, CHECKABLE evidence that an entry was confirmed. "
        "evidence_type must be one of: execution_verified (test/build/command "
        "ran with expected result — strongest), cross_reference (confirmed "
        "independently by another source), reuse_without_failure (reused "
        "without issue — weak, capped), agent_reasoning (no external proof — "
        "logged but does NOT move the score, do not use this to inflate "
        "confidence). evidence_ref should point to what proves it (a test "
        "log, a file path, another entry_id). session_id is required for "
        "dedup: repeated validation of the same entry within one session "
        "only counts once."
    )
)
async def validate_entry(
    ctx: Context, entry_id: str, evidence_type: str, evidence_ref: str, session_id: str
) -> dict:
    try:
        result = get_repo().validate_entry(
            entry_id=entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
            session_id=session_id,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Record that entry_id is contradicted by conflicting_entry_id, with "
        "external evidence (same evidence_type rules as validate_entry). "
        "NEVER deletes either entry — only lowers entry_id's validation_score "
        "(contradiction lowers the score faster than a confirmation raises "
        "it) and creates a visible 'contradicts' link so future "
        "query_context calls surface the conflict instead of hiding it."
    )
)
async def contradict_entry(
    ctx: Context, entry_id: str, conflicting_entry_id: str, evidence_type: str, evidence_ref: str
) -> dict:
    try:
        result = get_repo().contradict_entry(
            entry_id=entry_id,
            conflicting_entry_id=conflicting_entry_id,
            evidence_type=evidence_type,
            evidence_ref=evidence_ref,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Create or update an EXPLICIT link between two entries. relation_type "
        "must be one of: related, contradicts, depends_on, refines. Implicit "
        "'related' links are created automatically by store_entry above a "
        "similarity threshold — use this tool for relationships the "
        "similarity search would not infer on its own (e.g. a dependency "
        "between an architecture decision and a convention)."
    )
)
async def link_entries(
    ctx: Context, source_id: str, target_id: str, relation_type: str, weight: float = 1.0
) -> dict:
    try:
        result = get_repo().link_entries(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            weight=weight,
        )
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Capture the result of a test/build/lint command as memory: stores a "
        "learning entry (source=tool_execution) and, on success, validates it "
        "as execution_verified in a single call. The command must look like a "
        "verification command (pytest, npm/pnpm/yarn/bun test or build, "
        "dotnet/cargo/go test or build, make/mix/flutter/mvn/gradle/sbt test, "
        "vitest, jest, deno test, tox, phpunit, rake test, compileall, "
        "py_compile, bash -n, shellcheck, tsc --noEmit, ruff check, mypy, "
        "eslint, plus any configured verification_command_patterns). Call "
        "this right after running such a command — do not use it for trivial "
        "commands (ls, cat, echo, grep, git status) whose exit 0 proves "
        "nothing. session_id must be the current session id."
    )
)
async def record_execution(ctx: Context, command: str, succeeded: bool, session_id: str) -> dict:
    try:
        if not looks_like_verification_command(command, _verification_patterns):
            return {
                "error": True,
                "message": (
                    "command does not match a verification pattern; if it is "
                    "still meaningful evidence, use store_entry + validate_entry "
                    "manually instead"
                ),
            }
        repo = get_repo()
        content = "\n".join(
            [
                f"Command executed: {command}",
                f"Result: {'success' if succeeded else 'failure'}",
                f"Directory: {_config_dir}",
            ]
        )
        store_result = repo.store_entry(type_="learning", content=content, source="tool_execution")
        entry_id = store_result["entry_id"]
        if succeeded:
            validation = repo.validate_entry(
                entry_id=entry_id,
                evidence_type="execution_verified",
                evidence_ref=command,
                session_id=session_id,
            )
        else:
            validation = {"note": "left unvalidated (command failed)"}
        await _on_memory_mutated(ctx)
        return {
            "entry_id": entry_id,
            "type": "learning",
            "stored": True,
            "validation": validation,
        }
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Pin an entry so its confidence NEVER decays. USE WHEN: a fundamental "
        "architecture decision that defines the project, a convention that is "
        "company/project policy, or an entry that has been validated repeatedly "
        "across many sessions and is now considered settled. DO NOT use for: "
        "recent learnings, bug patterns that may be fixed, entries with active "
        "contradictions. Pinning is reversible via restore_entry."
    )
)
async def pin_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().pin_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Mark an entry as deprecated — excluded from all future queries. "
        "USE WHEN: an entry has been conclusively contradicted and the newer "
        "entry is confirmed, the code/module it references no longer exists, "
        "or it describes a bug pattern that has been fixed. DO NOT use for: "
        "entries you are unsure about. Deprecation is reversible via "
        "restore_entry, but prefer caution."
    )
)
async def deprecate_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().deprecate_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Restore a pinned or deprecated entry back to active status. "
        "USE WHEN: a deprecation was premature, the entry is relevant again, "
        "or a pin is no longer warranted."
    )
)
async def restore_entry(ctx: Context, entry_id: str) -> dict:
    try:
        result = get_repo().restore_entry(entry_id=entry_id)
        await _on_memory_mutated(ctx)
        return result
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Paginated, filterable list of memory entries with current confidence. "
        "Excludes deprecated entries by default (set status='deprecated' to "
        "include them). Optional filters: type (doc/archi_decision/learning/"
        "convention/bug_pattern), status (active/pinned/deprecated), "
        "min_confidence, max_confidence. limit max 200, default 50. "
        "Sorted by confidence descending. Returns entries + total for pagination."
    )
)
def list_entries(type: str | None = None, status: str | None = None,
                 min_confidence: float | None = None, max_confidence: float | None = None,
                 limit: int = 50, offset: int = 0) -> dict:
    try:
        return get_repo().list_entries(
            type=type, status=status,
            min_confidence=min_confidence, max_confidence=max_confidence,
            limit=limit, offset=offset,
        )
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


@mcp.tool(
    description=(
        "Review memory health: total entries by type, confidence distribution "
        "(low <0.3 / medium 0.3-0.7 / high >0.7), entries never validated, "
        "active contradictions, 5 lowest-confidence entries, and the last 10 "
        "events. Read-only diagnostic — use this before relying heavily on "
        "memory, or when you suspect stale/contradicted entries."
    )
)
def get_memory_stats() -> dict:
    try:
        return get_repo().get_stats()
    except (ValueError, WpmError, RuntimeError) as exc:
        return {"error": True, "message": str(exc)}


# --- resources --------------------------------------------------------------

@mcp.resource(
    "wpm://project-rules",
    name="Project rules and conventions",
    description=(
        "The project's high-confidence conventions and architecture decisions, "
        "recomputed from persistent memory. Read this at session start and "
        "re-read it when memory is updated."
    ),
    mime_type="text/markdown",
)
def project_rules() -> str:
    global _project_rules_cache
    if _project_rules_cache is not None:
        return _project_rules_cache
    if DB_PATH is None:
        return ""
    try:
        result = get_repo().query_context(
            query=PROJECT_RULES_QUERY,
            min_confidence=_settings.confidence_threshold,
            token_budget=PROJECT_RULES_TOKEN_BUDGET,
        )
        text = format_project_rules(result)
        block = build_project_rules_block(text)
        _project_rules_cache = block
        return block
    except (ValueError, WpmError, RuntimeError):
        return ""


@mcp.resource(
    "wpm://memory-rules",
    name="Memory usage rules",
    description=(
        "The 16 rules governing how to use persistent memory: when to store, "
        "validate, contradict, dedup, pin and deprecate. Same content as the "
        "server instructions — re-read them if in doubt."
    ),
    mime_type="text/markdown",
)
def memory_rules() -> str:
    return MEMORY_USAGE_RULES


@mcp.resource(
    "wpm://verification-commands",
    name="Verification command patterns",
    description=(
        "The command patterns that count as strong proof (execution_verified) "
        "for record_execution: their success means something was verified. "
        "Check this list before deciding whether a command result is evidence."
    ),
    mime_type="text/markdown",
)
def verification_commands() -> str:
    lines = [
        "Commands whose successful execution counts as strong proof "
        "(execution_verified) for record_execution:",
    ]
    lines += [f"- {p}" for p in VERIFICATION_COMMAND_PATTERNS]
    lines.append("")
    lines.append(
        "Do NOT use record_execution for trivial commands (ls, cat, echo, "
        "grep, git status/diff): exit 0 on those proves nothing."
    )
    return "\n".join(lines)

# --- prompts ----------------------------------------------------------------

@mcp.prompt(
    name="persist",
    description="End-of-task persistence checklist: persist any durable facts from the session that were not yet stored.",
)
def wpm_persist() -> str:
    return (
        "Session ended. End-of-task memory pass (wpm persistent memory): if "
        "and only if durable facts from this session — decisions, confirmed "
        "results, understood bug patterns — were not yet persisted via "
        "store_entry or record_execution, persist them now. Do not invent "
        "evidence, do not store transient details or trivia, and do not "
        "validate anything without external proof. If nothing remains to "
        'persist, reply exactly: "nothing to persist".'
    )


@mcp.prompt(
    name="audit",
    description="Review the health of the project's persistent memory (read-only dashboard).",
)
def wpm_audit() -> str:
    return (
        "You are reviewing the health of this project's persistent memory system.\n"
        "\n"
        "1. Call `get_memory_stats` — a single, read-only call that returns "
        "the full dashboard.\n"
        "\n"
        "2. Present the results in a compact, scannable format:\n"
        "\n"
        "   WPM Memory Review\n"
        "   Total: <N> entries\n"
        "     archi_decision: <N>   convention: <N>   doc: <N>   "
        "learning: <N>   bug_pattern: <N>\n"
        "   Confidence: High (>0.7) <N> / Medium (0.3-0.7) <N> / Low (<0.3) <N>\n"
        "\n"
        "3. Highlight problems under dedicated headings:\n"
        "   - 'Entries never validated' — list them; they should be verified "
        "or downgraded.\n"
        "   - 'Active contradictions' — for each pair, describe what is known "
        "about the two conflicting entries (call query_context on their topics "
        "if needed). Ask whether any should be resolved.\n"
        "   - 'Lowest confidence (bottom 5)' — list each with its confidence "
        "and a short preview; entries below the project's confidence "
        "threshold (read from wpm.config.json, default 0.5) are especially "
        "concerning.\n"
        "   - 'Recent activity' — the last 10 events; flag sessions where no "
        "persistence happened.\n"
        "\n"
        "4. If the dashboard reveals problems, suggest concrete actions "
        "(pin_entry, deprecate_entry, restore_entry) — do not execute them.\n"
        "\n"
        "5. End with a one-line verdict: 'Memory is healthy' / 'N issues need "
        "attention'.\n"
        "\n"
        "Do not modify anything — this is a read-only review."
    )


@mcp.prompt(
    name="learn",
    description="Ingest one or more markdown documents into persistent memory, chunked by section.",
)
def wpm_learn(paths: str = "") -> str:
    return (
        "You are ingesting markdown documents into the project's persistent "
        "memory system (the wpm MCP server: store_entry, query_context, "
        "validate_entry, contradict_entry, link_entries).\n"
        "\n"
        "USAGE: learn <path-to-doc.md> [more-docs.md ...] — ingest one or "
        "more markdown files, section by section, into persistent memory.\n"
        "\n"
        "Paths: {paths}\n"
        "\n"
        "If no path is given, reply with this usage message and do NOT call "
        "any tool.\n"
        "\n"
        "Follow these steps exactly:\n"
        "\n"
        "1. Treat {paths} as a space-separated list of files. Process each "
        "file in order. If a file does not exist, say so and move on to the "
        "next — do not guess a file.\n"
        "\n"
        "2. For each file, split it into sections along its ##/### headings "
        "(or logical paragraphs if it has no headings). Each section becomes "
        "ONE candidate memory entry. Do NOT store a whole file as a single "
        "entry — this destroys retrieval granularity.\n"
        "\n"
        "3. For each section, before storing:\n"
        "   a. Call query_context with a short query summarizing the "
        "section's topic, min_confidence: 0.3.\n"
        "   b. If a direct_match with similarity above ~0.85 already exists "
        "and is clearly the same fact: do NOT create a duplicate. Call "
        "validate_entry on it with evidence_type 'cross_reference' and "
        "evidence_ref pointing to this file path.\n"
        "   c. Otherwise, call store_entry:\n"
        "      - content: the section's content, TRANSLATED TO ENGLISH if the "
        "source is not English (embedding consistency), rewritten concisely, "
        "not a verbatim copy of formatting artifacts;\n"
        "      - type: infer the best fit — doc (default), archi_decision, "
        "convention, bug_pattern;\n"
        "      - source: 'official_doc' (manual, deliberate ingestion of a "
        "real document).\n"
        "\n"
        "4. Link related sections to each other with link_entries when one "
        "section clearly depends on or refines another — don't over-link.\n"
        "\n"
        "5. Report back a short summary: for each file, how many sections "
        "stored as new entries, how many deduplicated/revalidated instead, "
        "and any section skipped and why.\n"
        "\n"
        "Do not ask for confirmation before each individual store_entry call "
        "— work through the whole list, then report the summary at the end."
    ).format(paths=paths)


@mcp.prompt(
    name="map",
    description="Map the structure, architecture and conventions of the given code directories/files into persistent memory.",
)
def wpm_map(scopes: str = "") -> str:
    return (
        "You are mapping the structure of this codebase into the project's "
        "persistent memory system (the wpm MCP server: store_entry, "
        "query_context, validate_entry, contradict_entry, link_entries).\n"
        "\n"
        "USAGE: map <path-or-dir> [more-paths ...] — survey the given "
        "directories/files and store durable structural facts.\n"
        "\n"
        "Scopes to map: {scopes}\n"
        "\n"
        "If no scope is given, reply with this usage message and do NOT call "
        "any tool.\n"
        "\n"
        "This is NOT a file-by-file index — that would flood memory with "
        "noise and give no retrieval value. You are extracting a small number "
        "of durable, high-value structural facts an engineer would want "
        "recalled months later.\n"
        "\n"
        "Follow these steps:\n"
        "\n"
        "1. Treat {scopes} as a space-separated list of directories/files. "
        "For each one, survey the structure — list its directory tree "
        "(respecting .gitignore; skip build artifacts, node_modules, "
        "bin/obj, dist, .venv, etc). Identify the main layers/modules and "
        "what each is responsible for.\n"
        "\n"
        "2. Read enough real code to ground your findings — key entry points, "
        "the most central classes/modules per layer, existing README/docs in "
        "each scope, project/config files. Do not infer architecture purely "
        "from folder names without checking the code actually matches.\n"
        "\n"
        "3. Identify durable facts, each becoming ONE candidate entry:\n"
        "   - archi_decision — a structural choice actually observed in the "
        "code;\n"
        "   - convention — a naming/style/error-handling pattern consistently "
        "followed across multiple files;\n"
        "   - bug_pattern — only if you find a documented known issue; never "
        "speculate about bugs you have not verified.\n"
        "   Skip anything you are not reasonably confident about — a wrong "
        "architecture entry is worse than a missing one.\n"
        "\n"
        "4. For each candidate fact, before storing:\n"
        "   a. Call query_context with a short query on the topic, "
        "min_confidence: 0.3.\n"
        "   b. If a very similar direct_match already exists: call "
        "validate_entry on it instead, evidence_type 'execution_verified' if "
        "you actually traced the code path, otherwise 'cross_reference' with "
        "evidence_ref set to the file path(s) you checked.\n"
        "   c. Otherwise store_entry with type archi_decision, convention, or "
        "bug_pattern, content in English naming the actual files/modules, "
        "source 'observed_code'.\n"
        "\n"
        "5. Link entries with link_entries where the relationship is explicit "
        "in the code.\n"
        "\n"
        "6. Report back: what was stored (grouped by type), what was "
        "revalidated instead of duplicated, and anything you considered but "
        "skipped because you weren't confident enough.\n"
        "\n"
        "Do not ask for confirmation before each individual store_entry call "
        "— do the full survey, then report the summary at the end."
    ).format(scopes=scopes)


@mcp.prompt(
    name="bootstrap",
    description="Bootstrap the project's persistent memory from existing artifacts (README, docs, configs, CI, structure).",
)
def wpm_bootstrap() -> str:
    return (
        "You are bootstrapping this project's persistent memory from its "
        "existing artifacts: README, documentation, configuration files, "
        "CI/CD pipelines, and directory structure. This is a one-time "
        "initial population — the normal incremental persist-as-you-work "
        "behavior continues alongside it.\n"
        "\n"
        "Follow these steps exactly:\n"
        "\n"
        "1. README: read README.md and extract durable facts: project "
        "purpose/domain (doc or archi_decision), key dependencies/tech stack "
        "(archi_decision), architectural overview (archi_decision), "
        "contribution guidelines (convention), testing/build instructions "
        "(learning).\n"
        "\n"
        "2. Documentation: search docs/, doc/, documentation/. Read relevant "
        ".md/.rst files (skip CHANGELOG, LICENSE, generated docs). Extract "
        "explicit architecture decisions (archi_decision), documented "
        "conventions (convention), documented pitfalls (bug_pattern only if "
        "explicitly documented).\n"
        "\n"
        "3. Lint and style config: .editorconfig, .prettierrc*, "
        "eslint.config.*, ruff.toml, .mypy.ini, tsconfig*.json, .flake8, "
        "tox.ini (flake8), .hadolint.yaml, .markdownlint.*, biome.json. "
        "Extract conventions: indentation, quotes, line length, strictness, "
        "enforced rules implying a coding standard.\n"
        "\n"
        "4. Dependencies and tooling: pyproject.toml / package.json / "
        "Cargo.toml / go.mod / Makefile / Justfile. Extract primary "
        "framework/runtime (archi_decision), package manager (convention), "
        "standard build/test/lint commands (learning).\n"
        "\n"
        "5. CI/CD: .github/workflows/, .gitlab-ci.yml, .circleci/config.yml, "
        "Jenkinsfile. Extract provider, key stages, required checks; if CI "
        "defines official test/build commands, they supersede package-config "
        "inference.\n"
        "\n"
        "6. Directory structure: list the top 2 levels respecting .gitignore "
        "(skip node_modules, .git, dist, build, __pycache__, .venv, target, "
        ".next, coverage). For each top-level non-config directory, name the "
        "module/layer and infer its role — check 1-2 files inside to confirm "
        "before recording anything. Do NOT record a convention or "
        "archi_decision based solely on a directory name.\n"
        "\n"
        "7. Persist each fact: before storing, call query_context "
        "(min_confidence: 0.3). If a direct_match above ~0.85 already exists, "
        "validate_entry with evidence_type 'cross_reference' and evidence_ref "
        "= the file path. Otherwise store_entry: content in English naming "
        "actual files/configs, correct type, source 'observed_code'.\n"
        "\n"
        "8. Report: group stored entries by type with counts (stored vs "
        "revalidated), plus any facts skipped because evidence was too thin.\n"
        "\n"
        "Do not ask for confirmation between steps — work through the full "
        "pipeline, then report the summary at the end."
    )


@mcp.prompt(
    name="patterns",
    description="Analyze memory for recurring patterns and suggest (and execute) new conventions or architecture decisions.",
)
def wpm_patterns(type_filter: str = "") -> str:
    filter_text = type_filter.strip() or "ALL entry types"
    return (
        "You are analyzing the project's persistent memory to detect "
        "recurring patterns and identify opportunities for improvement. "
        "This is metacognitive analysis — the memory system examining itself.\n"
        "\n"
        "Type filter: {type_filter}\n"
        "\n"
        "1. Gather entries: call list_entries(type=<type_filter>, limit=100) "
        "for the target type(s). If total > 100, note in your report that "
        "only the top 100 by confidence were analyzed.\n"
        "\n"
        "2. Read and categorize: group entries by semantic themes using human "
        "judgment (not vector similarity). Each entry belongs to exactly one "
        "theme; if fewer than 3 entries share a theme, label them 'isolated'.\n"
        "\n"
        "3. Identify actionable patterns for each theme with 3+ entries: a "
        "root cause suggesting a new archi_decision or convention; a missing "
        "rule (several bug_patterns with the same cause); an entry repeatedly "
        "confirmed (suggest pin_entry); lingering contradictions to resolve.\n"
        "\n"
        "4. Propose and execute: for each actionable pattern, present your "
        "reasoning then execute it automatically — do NOT ask for "
        "confirmation per action:\n"
        "   - 4+ bug_patterns with the same cause -> create a convention "
        "(store_entry, type convention);\n"
        "   - convention validated 3+ times -> pin_entry;\n"
        "   - long-standing contradiction -> deprecate_entry the weaker one;\n"
        "   - 3+ learnings confirming the same architecture decision -> "
        "store_entry (type archi_decision) + pin_entry.\n"
        "   For each store_entry follow the standard rules: dedup via "
        "query_context first, English content, source 'observed_code' if "
        "grounded in real entries, 'agent_inference' if inferred.\n"
        "\n"
        "5. Report a structured summary: themes found (with counts), actions "
        "taken, and themes needing no action. Do NOT invent patterns where "
        "none exist — a negative result is valid.\n"
        "\n"
        "If no actionable patterns are found, report this clearly and end."
    ).format(type_filter=filter_text)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

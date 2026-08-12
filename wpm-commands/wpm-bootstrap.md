---
description: Bootstrap the project's persistent memory from existing artifacts
agent: build
subtask: true
---

> Guard: if `wpm.config.json` does not exist at the project root, memory is not activated. Politely explain that the user must run `wpm enable` (then restart opencode) and stop without doing anything else.

You are bootstrapping this project's persistent memory from its existing
artifacts: README, documentation, configuration files, CI/CD pipelines,
and directory structure. This is a one-time initial population — the
normal incremental persist-as-you-work behavior continues alongside it.

Follow these steps exactly:

---

## 1. README

Read `README.md`. Extract durable facts:
- Project purpose and domain (→ `doc` or `archi_decision`)
- Key dependencies / tech stack mentioned (→ `archi_decision`)
- Architectural overview (layers, services, data flow) — if described (→ `archi_decision`)
- Contribution guidelines or documented conventions (→ `convention`)
- Testing or build instructions (→ `learning`)

## 2. Documentation

Search for documentation directories: `docs/`, `doc/`, `documentation/`.
If found, list their contents (`ls -R <dir>`), then read any `.md` or
`.rst` files that look relevant. Skip `CHANGELOG.md`, `LICENSE`,
generated API docs, and auto-generated files. For each document:
- Extract architecture decisions explicitly stated (→ `archi_decision`)
- Extract documented conventions or coding rules (→ `convention`)
- Extract known patterns, pitfalls, or gotchas (→ `bug_pattern`, only
  if explicitly documented — never speculate)

## 3. Lint and style configuration

Look for and read these files if they exist:
- `.editorconfig`
- `.prettierrc`, `.prettierrc.json`, `prettier.config.*`
- `eslint.config.*`, `.eslintrc*`
- `ruff.toml`, `.ruff.toml`
- `.mypy.ini`, `mypy.ini`, `pyproject.toml` (tool.mypy section)
- `tsconfig.json`, `tsconfig.*.json`
- `.flake8`, `setup.cfg` (flake8 section), `tox.ini` (flake8 section)
- `.hadolint.yaml`, `.markdownlint.*`
- `biome.json`

For each file, extract conventions into facts:
- Indentation style (spaces vs tabs, width)
- Quote style (single vs double)
- Line length limits
- Type checking strictness (strict mode, noImplicitAny, etc.)
- Enforced lint rules that imply a coding standard (not every rule —
  only patterns consistently enforced: naming conventions,
  banned APIs, import ordering, etc.)

## 4. Dependencies and tooling

Read at least one of these (whichever exists):
- `pyproject.toml` → Python: framework (FastAPI, Django, Flask, etc.),
  package manager (poetry, pip, uv), core dependencies, scripts
- `package.json` → Node: framework (Next.js, Express, etc.), package
  manager (npm, pnpm, yarn), scripts (build, test, dev, lint)
- `Cargo.toml` → Rust: key dependencies, features, workspace layout
- `go.mod` → Go: module name, key dependencies
- `Makefile` or `Justfile` → build targets, test commands, common workflows

Extract:
- Primary framework / runtime (→ `archi_decision`)
- Package manager and dependency management (→ `convention`)
- Standard build/test/lint commands (→ `learning` — these are
  execution results, revalidated when actually run)

## 5. CI/CD

Look for:
- `.github/workflows/*.yml`
- `.gitlab-ci.yml`
- `.circleci/config.yml`
- `Jenkinsfile`
- Any CI configuration files

For each pipeline found, extract:
- CI provider (→ `learning` or `archi_decision`)
- Key pipeline stages (test, build, deploy, lint)
- Any project-specific CI conventions (required checks, secrets,
  environment setup)
- If the CI defines the official test/build commands, these
  supersede what was inferred from package configs

## 6. Directory structure

List the top 2 levels of the project tree, respecting `.gitignore`.
Skip: `node_modules`, `.git`, `dist`, `build`, `__pycache__`,
`.venv`, `venv`, `target`, `bin`, `obj`, `.next`, `coverage`.

For each top-level directory that is NOT a config/tooling folder:
- Name the module/layer it represents
- Infer its role (e.g. "API layer", "data access", "frontend components",
  "shared utilities")
- Check 1–2 files inside to confirm the directory actually does what
  its name suggests

Extract:
- Layered architecture (if visible) → `archi_decision`
- Module responsibilities → `archi_decision`

Do NOT record a `convention` or `archi_decision` based solely on a
directory name without checking code inside — a folder called
`services/` might contain API clients, not services.

## 7. Persist each fact

For every candidate fact identified above, before storing:

a. Call `query_context` with a short query summarizing the topic,
   `min_confidence: 0.3`.

b. If a direct_match with similarity above ~0.85 already exists:
   `validate_entry` on it instead, with `evidence_type: "cross_reference"`,
   `evidence_ref` set to the file path you read.

c. Otherwise `store_entry`:
   - `content`: in English, concise, naming actual files/configs involved.
     Example: "ESLint enforces single quotes, no semicolons, and trailing
     commas in `eslint.config.mjs`" — not "The project uses ESLint".
   - `type`: `archi_decision` (structural choice), `convention` (naming/
     style/process rule), `learning` (tooling/command), `bug_pattern`
     (documented known issue), `doc` (explanatory content from docs).
   - `source`: `"observed_code"` — you read this directly from project
     files, not inferred.

## 8. Report

Group stored entries by type and print a summary:
- N `archi_decision` stored, N revalidated
- N `convention` stored, N revalidated
- N `learning` stored, N revalidated
- N `bug_pattern` stored (if any), N `doc` stored (if any)
- Any facts you considered but skipped because the evidence was too thin

Do not ask for confirmation between steps — work through the full
pipeline, then report the summary at the end.

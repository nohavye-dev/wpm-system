# Contribuer à WPM

> Pour l'utilisateur final, voir `README.md` et le site [wpm-site](https://nohavye-dev.github.io/wpm-site/). Ce guide s'adresse aux mainteneurs et contributeurs : installer en mode dev, tester, proposer une contribution, publier.

## 1. Prérequis

- **Bun 1.4.0** — version pinnée dans `wpm-opencode-plugin/package.json` (`bun-types 1.4.0`), `.github/workflows/ci.yml` (`bun-version: 1.4.0`) et `wpm-opencode-plugin/bun.lock`. Install via `curl -fsSL https://bun.sh/install | bash` (ou `~/.bun/bin/bun` si déjà présent).
- **Python >=3.11** — `wpm-mcp-server/pyproject.toml:requires-python`. Dépendances : `mcp==1.9.4`, `sqlite-vec`, `onnxruntime`, `tokenizers`, `huggingface-hub`, `prompt_toolkit>=3.0`.
- Outils système : `sha256sum`, `rsync`, `curl` (pour `install.sh` et `update-source-checksum.sh` / `sync-public-docs.sh`).

## 2. Installation dev

```bash
# Serveur (depuis la racine du repo)
pip install -e ./wpm-mcp-server

# Plugin OpenCode (bun)
cd wpm-opencode-plugin && bun install
bun run typecheck   # tsc --noEmit — plus d'erreur bun-types
bun test            # 30 tests (bridge, client, schema, nudges, hooks)
bun run lint        # biome check . (warning non-bloquant)

# Pre-commit (optionnel mais recommandé)
pip install pre-commit && pre-commit install
# Lance ruff, mypy, biome, generate_config_schema --check et sha256sum -c
```

`install.sh` reste la voie globale utilisateur : crée `~/.local/share/wpm-system/venv`, pré-télécharge le modèle ONNX `paraphrase-multilingual-MiniLM-L12-v2` (~120 MB quantifié, `EMBEDDING_DIM=384`), installe `~/.local/bin/wpm` et le plugin `~/.config/opencode/plugins/wpm-plugin.ts` + `wpm-lib/`.

## 3. Proposer une contribution

Fork le repo → branche `feature/xxx` sur ton fork → Pull Request vers `main-dev` de `nohavye-dev/wpm-system` (pas `main`).

Avant de pousser ton fork :

```bash
scripts/update-source-checksum.sh   # régénère SHA256SUMS (voir §4)
pytest wpm-mcp-server -q            # 19 tests
bun run typecheck --cwd wpm-opencode-plugin && bun test --cwd wpm-opencode-plugin
```

La CI (`.github/workflows/ci.yml`) vérifie : `pytest` (`WPM_SKIP_ONNX_TEST=1`) + `generate_config_schema --check` + `sha256sum -c` + `bun typecheck/test/lint`.
La PR est examinée par le mainteneur.

## 4. Avant de pousser — Checksums

Tout fichier suivi par git est vérifié à l'installation :

```bash
scripts/update-source-checksum.sh   # régénère SHA256SUMS (135+ fichiers)
git add SHA256SUMS && git commit
sha256sum -c SHA256SUMS --status    # vérif locale, comme la CI et install.sh
```

Sans cela, `curl -fsSL .../install.sh | bash` échoue (`install.sh:24` `sha256sum -c SHA256SUMS --status` → `checksum verification failed`). Les docs `docs/public/` et `docs/internals/` en font partie — une doc éditée sans régénération casse l'install.

## 5. Branches & publication

- `main-dev` : développement (push courant).
- `main` : publication (`WPM_SOURCE_REF=main` pour `curl | bash`).

**Interdit de committer directement sur `main`.**

Pour publier :

```bash
git checkout main
git merge --ff-only main-dev
git push
```

Si le merge touche `docs/public/`, publie ensuite la doc du site (voir §7).

## 6. Tester l'installation globale

Pour réinstaller le worktree courant en conditions réelles :

```bash
wpm uninstall --force && ./install.sh
```

Redémarre les sessions opencode après : le serveur chaud garde l'ancien code jusqu'au restart.

## 7. Synchroniser la documentation publique

`docs/public/` est une **vraie copie** (pas un lien symbolique) de `wpm-site/docs`, le dossier consommé par le site.

```bash
scripts/sync-public-docs.sh                # message par défaut
scripts/sync-public-docs.sh -m "docs: ..." # message personnalisé
```

Le script (`rsync --delete` vers `wpm-site/docs`, puis `commit` + `push origin`) refuse si :

- `wpm-system` n'est pas sur la branche `main` ;
- `wpm-site` contient des modifications non commitées ;
- le réseau est indisponible (`ls-remote origin`, timeout 15 s).

Si rien n'a changé, il ne fait rien.

## 8. Debug

Fichier cache `WPM_DEBUG` (Lot 2C) : `${XDG_CACHE_HOME:-~/.cache}/wpm-system/logs/wpm-embeddings.log`.

```bash
WPM_DEBUG=1 wpm search "..."      # CLI / serveur (infra/embeddings.py)
WPM_DEBUG=1 opencode              # plugin (hooks.ts, system-push.ts) → console.error [wpm]
```

Sans `WPM_DEBUG`, la TUI reste propre (`silenced_stderr` vers `/dev/null` étanche, sans fuite fd). Avec, les logs ONNX/tokenizers y sont conservés.

Traces utiles :

- `WPM_DEBUG=1` loggue `current-user read failed`, `project-rules read failed`, `recall empty` (`sim>=0.35`, `ragMaxItems=5`).
- Sans `WPM_DEBUG`, une trace `rag decision` (`level info`, service `wpm`) reste via `client.app.log` avec `candidates/picked/top_sim`.

## 9. Références

- Serveur : `wpm-mcp-server/README.md` (outils, resources, embeddings, tests).
- Plugin : `wpm-opencode-plugin/README.md` + `docs/internals/opencode-plugin-guide.md` et `architecture-plugin-hote-mcp.md`.
- Internals : `docs/internals/` (calibration, RAG, migration embedding).

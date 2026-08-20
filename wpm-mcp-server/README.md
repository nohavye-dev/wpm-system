# wpm-mcp-server

Le serveur de mémoire persistante **pondérée par la confiance**, implémentation
Python (SQLite + sqlite-vec + ONNX). C'est la **source de vérité** du projet :
scoring, décroissance, expansion de graphe, outils MCP.

> **Présentation vs technique** — les sections « Outils », « Resources »
> et « Configuration » ci-dessous sont techniques. Pour
> comprendre *pourquoi* tout cela existe, voir
> `docs/concepts.md`.

## Documentation

- Site web du projet : [WPM — Weighted Persistent Memory](https://nohavye-dev.github.io/wpm-site/)

---

## Présentation

Le serveur expose la mémoire via MCP : 11 outils, 3 resources.
Il est lancé **par le plugin OpenCode** (qui l'enregistre automatiquement à
partir de `wpm.config.json`) — pas besoin de le déclarer à la main. Sans
activation (pas de `wpm.config.json` ni `WPM_DB_PATH`), il démarre inerte :
il liste ses outils mais chaque appel renvoie « wpm is not activated ».

Le comportement de l'agent est orienté par :

- **`initialize.instructions`** — 3 règles d'or (MEMORY FIRST / WRITE AS
  YOU GO / PROOF BEFORE VALIDATION) + politiques, re-lisibles via
  `wpm://memory-rules` ;
- **descriptions d'outils directives** — relues à chaque décision d'appel
  (dédoublonnage, hiérarchie des preuves, choix du type/source…) ;
- **rappels ciblés (`tool_result`)** — relus au moment exact de l'action.

---

## Installation

Installation globale via `install.sh` (recommandée), ou manuelle pour le
développement :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Exécution autonome (sans host) :

```bash
WPM_DB_PATH=./wpm.db python -m wpm_mcp_server
```

---

## Outils

| Tool | Rôle |
|---|---|
| `store_entry(type, content, source)` | Créer une entrée (type ∈ `doc`/`archi_decision`/`insight`/`convention`/`bug_pattern`/`execution_result` ; source ∈ `official_doc`/`observed_code`/`tool_execution`/`agent_inference`) |
| `query_context(query, min_confidence?, token_budget?)` | Récupération hybride vecteur + confiance + graphe, avec expansion à 1 saut |
| `validate_entry(entry_id, evidence_type, evidence_ref, session_id)` | Enregistrer une preuve de confirmation (dédupliquée par session) |
| `contradict_entry(entry_id, conflicting_entry_id, evidence_type, evidence_ref)` | Enregistrer un conflit — ne supprime jamais, baisse le score + lien `contradicts` |
| `link_entries(source_id, target_id, relation_type, weight?)` | Relation explicite (`related`/`contradicts`/`depends_on`/`refines`) |
| `get_memory_stats()` | Diagnostic : totaux, distribution de confiance, jamais validées, contradictions, plus faibles |
| `pin_entry(entry_id)` | Épingler — la confiance ne décroît jamais |
| `deprecate_entry(entry_id)` | Déprécier — exclue des résultats (réversible) |
| `restore_entry(entry_id)` | Restaurer en statut actif |
| `list_entries(type?, status?, min_confidence?, max_confidence?, limit?, offset?)` | Liste paginée et filtrable |
| `record_execution(command, succeeded, session_id)` | Capturer un test/build/lint : stocke une entrée `execution_result` et la valide `execution_verified`. Les commandes triviales (`ls`, `cat`, `grep`, `git status`…) sont rejetées |

`type` et `source` sont typés (`Literal`) : une valeur hors liste est
rejetée par le schéma avant même d'atteindre le code.

---

## Resources

| Resource | Contenu |
|---|---|
| `wpm://project-rules` | Conventions/décisions du projet (≥ `confidence_threshold`), bloc `<project-rules>` |
| `wpm://memory-rules` | Les règles d'usage (même contenu que `instructions`) |
| `wpm://verification-commands` | Commandes comptant comme preuve forte |

---

## Prompts

Les workflows `persist`, `audit`, `learn`, `map`, `bootstrap`, `patterns`
ne sont plus des prompts MCP : le serveur n'en expose aucun. Ils ont été
migrés vers le plugin OpenCode (`wpm-opencode-plugin`) comme commandes
slash natives `/wpm-persist`, `/wpm-audit`, `/wpm-learn`, `/wpm-map`,
`/wpm-bootstrap`, `/wpm-patterns` — enregistrées via le hook `config`
(`config.command`) et masquées à l'exécution (part synthétique + label
court) par `command.execute.before`.

---

## Configuration

Voir `docs/configuration.md` pour le détail de
`wpm.config.json`. `wpm enable` écrit ce fichier (avec `db_path` par
défaut), `wpm disable` le supprime.

---

## Embeddings

ONNX Runtime + tokenizers HuggingFace (~150 MB), modèle
`paraphrase-multilingual-MiniLM-L12-v2` (384 dims, 50+ langues), téléchargé
et mis en cache au premier démarrage (variante quantifiée selon
l'architecture CPU, repli float32). `EMBEDDING_DIM` (`domain.py`) doit
correspondre à la dimension du modèle — validé au démarrage. Les espaces
vectoriels sont spécifiques au modèle : après un changement de modèle
(`WPM_EMBEDDING_MODEL` ou montée de version), lancer `wpm reembed` pour
ré-encoder toutes les entrées avant toute requête.

---

## Tests

```bash
pytest   # 12 fichiers de test à la racine (script-style via conftest)
```

- `test_repository.py`, `test_scoring.py`, `test_domain.py`,
  `test_embeddings.py`, `test_db.py`, `test_contradict_validation.py` —
  couche dépôt, sans transport MCP ;
- `test_stdio.py` — protocole MCP complet sur stdio ;
- `test_behavior.py` — règles, matching des commandes de vérification ;
- `test_settings.py`, `test_db_path_precedence.py`,
  `test_db_path_constraint.py` — config et contrainte d'emplacement ;
- `test_integration.py` — parcours complet depuis un vrai répertoire projet.

---

## Limites (volontaires)

- Pas d'authentification / multi-location : un fichier SQLite local par
  projet.
- Le modèle de confiance (λ de decay, seuils, poids) est calé sur des valeurs
  **raisonnées mais à valider** — voir [`docs/internal/`](../docs/internal/).

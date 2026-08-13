# wpm-mcp-server

Confidence-weighted, serveur MCP de mémoire persistante hybride
vecteur+graphe — implémentation de référence Python du document de
spécification (sections 1-9).

**Serveur MCP pur** : pas de plugin OpenCode, pas de hooks `experimental.*`.
Tout est exprimé avec des primitives MCP standard, donc le serveur fonctionne
avec n'importe quel host (OpenCode, Claude Desktop, etc.).

Testé de bout en bout sur le vrai transport MCP stdio (`test_stdio.py`), pas
seulement testé unitairement contre la couche de dépôt.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
```

`install.sh` à la racine du dépôt effectue une installation globale non
éditable dans un environnement virtuel géré
(`~/.local/share/wpm-system/venv`) ; l'installation manuelle ci-dessus
reste l'alternative pour le développement autonome.

## Exécution autonome

```bash
WPM_DB_PATH=./wpm.db python -m wpm_mcp_server
```

Parle MCP via stdio. Sans `WPM_DB_PATH` ni `wpm.config.json`, le serveur
démarre en mode **inerte** : il liste ses outils mais chaque appel renvoie
« wpm is not activated in this project ».

## Brancher dans votre host MCP

Ajoutez une entrée `mcp` à la configuration de votre host (ex. `opencode.json`,
projet ou global). `WPM_CONFIG_PATH` pointe vers le `wpm.config.json` du
projet — cela rend l'activation indépendante du répertoire de travail avec
lequel le host lance le serveur :

```json
{
  "mcp": {
    "wpm": {
      "type": "local",
      "command": ["~/.local/share/wpm-system/venv/bin/python", "-m", "wpm_mcp_server"],
      "environment": {
        "WPM_CONFIG_PATH": "/abs/path/to/project/wpm.config.json"
      }
    }
  },
  "permission": {
    "wpm_*": "allow"
  }
}
```

Le bloc `permission` est spécifique à opencode : il permet à l'agent de
persister la mémoire (outils `wpm_*`) **même en mode plan**. Les autres
hosts (Claude Desktop, etc.) acceptent le même bloc `mcp` et ignorent
`permission`.

`wpm enable` (voir le `README.md` racine) affiche ce snippet prêt à coller et
`wpm enable --write-config` écrit le fichier `wpm.config.json` pour vous.
Redémarrez votre host après tout changement — la configuration est lue une
seule fois au démarrage.

## Comment le serveur oriente le comportement de l'agent (100 % MCP)

- **`initialize.instructions`** — les règles d'usage de la mémoire (16 règles,
  `MEMORY_USAGE_RULES`) : l'agent doit appeler `query_context` en préambule de
  toute réponse substantielle, écrire au fil de l'eau, valider par preuves
  externes, ne jamais supprimer, etc. Re-lisibles via la resource
  `wpm://memory-rules`.
- **`wpm://project-rules`** — les règles/conventions du projet, recomputées
  depuis la mémoire (`query_context(PROJECT_RULES_QUERY, min_confidence=
  confidence_threshold, token_budget=800)`) et formatées en bloc
  `<project-rules>`. Le cache est invalidé à chaque mutation (store/validate/
  contradict/link/...), avec notification `resources/updated`.
- **`wpm://verification-commands`** — les commandes dont le succès compte
  comme preuve forte (`execution_verified`).
- **Descriptions d'outils directives** — relues à chaque décision d'appel :
  « à appeler en début de chaque réponse substantielle » sur `query_context`,
  etc.

## Outils exposés

| Tool | Rôle |
|---|---|
| `store_entry(type, content, source)` | Créer une nouvelle entrée de mémoire |
| `query_context(query, min_confidence?, token_budget?)` | Récupération hybride : vecteur + confiance + graphe, avec expansion associative à 1 saut |
| `validate_entry(entry_id, evidence_type, evidence_ref, session_id)` | Enregistrer une preuve de confirmation (dédupliquée par session) |
| `contradict_entry(entry_id, conflicting_entry_id, evidence_type, evidence_ref)` | Enregistrer un conflit — ne supprime jamais, ne fait que réduire le poids et marquer |
| `link_entries(source_id, target_id, relation_type, weight?)` | Relation explicite (`related`/`contradicts`/`depends_on`/`refines`) |
| `get_memory_stats()` | Diagnostic de la santé mémoire : totaux, distribution de confiance, entrées jamais validées, contradictions actives, 5 plus faibles |
| `pin_entry(entry_id)` | Épingler une entrée — sa confiance ne décroît jamais |
| `deprecate_entry(entry_id)` | Déprécier une entrée — exclue des résultats (réversible) |
| `restore_entry(entry_id)` | Restaurer une entrée épinglée ou dépréciée en statut actif |
| `list_entries(type?, status?, min_confidence?, max_confidence?, limit?, offset?)` | Liste paginée et filtrable des entrées avec leur confiance actuelle |
| `record_execution(command, succeeded, session_id)` | Capturer un test/build/lint comme preuve forte : stocke une entrée `execution_result` (`tool_execution`) et la valide `execution_verified` en un seul appel. La commande doit matcher un pattern de vérification — les commandes triviales (`ls`, `cat`, `echo`, `grep`, `git status`) sont rejetées |

`type` ∈ `doc`, `archi_decision`, `insight`, `convention`, `bug_pattern`, `execution_result`.
`evidence_type` ∈ `execution_verified`, `cross_reference`,
`reuse_without_failure`, `agent_reasoning` (exclu du scoring — uniquement
journalisé, selon la section 4 de la spécification).

Les règles d'utilisation (contenu en anglais uniquement, exigences de
preuve, non-suppression) sont intégrées dans `initialize.instructions` et
dans les descriptions d'outils que l'agent voit à chaque appel — voir la
section 8 de la spécification.

## Resources

| Resource | Contenu |
|---|---|
| `wpm://project-rules` | Conventions/décisions du projet (≥ `confidence_threshold`), en bloc `<project-rules>` |
| `wpm://memory-rules` | Les 16 règles d'usage de la mémoire (même contenu que `instructions`) |
| `wpm://verification-commands` | Commandes considérées comme preuve forte pour `record_execution` |

## Prompts

Les workflows des commandes `/wpm-*` de l'ancien plugin sont désormais des
prompts MCP :

| Prompt | Rôle |
|---|---|
| `persist` | Checklist de fin de tâche : persister ce qui n'a pas encore été stocké |
| `audit` | Revue de la santé de la mémoire (conflits, entrées jamais validées, faibles) |
| `learn(paths)` | Ingest un ou plusieurs documents markdown, section par section (dédup ≥ 0.85, traduction EN) |
| `map(scopes)` | Cartographie de répertoires/fichiers en entrées de mémoire (conventions, patterns) |
| `bootstrap` | Bootstrap initial d'un projet (README, docs, configs de lint, CI/CD) |
| `patterns(type_filter)` | Analyse de patterns récurrents dans le code |

Votre host les expose tels quels (dans opencode : `/wpm:learn:mcp`, etc.).

## Embeddings

Les embeddings sémantiques sont inclus par défaut via ONNX Runtime +
tokenizers HuggingFace (~100 MB de dépendances, contre ~1 GB pour
l'ancien pipeline torch/sentence-transformers). Aucune configuration
n'est nécessaire — le modèle `all-MiniLM-L6-v2` (384 dimensions) est
téléchargé automatiquement depuis HuggingFace Hub au premier démarrage
et mis en cache localement.

Pour changer de modèle : positionnez `WPM_EMBEDDING_MODEL` dans
l'environnement (ex. `WPM_EMBEDDING_MODEL=all-mpnet-base-v2`). Le modèle
doit être disponible sur HuggingFace Hub sous `sentence-transformers/` et
avoir une exportation ONNX (`onnx/model.onnx`). Changer de modèle après
avoir déjà inséré des entrées nécessite de ré-embedder la base
(supprimez le fichier `.wpm/wpm.db` et recommencez).

`EMBEDDING_DIM` dans `domain.py` doit correspondre à la dimension de
sortie du modèle (384 pour all-MiniLM-L6-v2, déjà le défaut) — le
serveur le valide au démarrage et échoue rapidement avec un message
clair en cas de discordance.

## Configuration — `wpm.config.json` à la racine du projet

C'est la façon principale et documentée de configurer un projet. Les
variables d'environnement (`WPM_DB_PATH`, `WPM_CONFIG_PATH`)
remplacent toujours le fichier lorsqu'elles sont définies, pour une
substitution locale rapide sans le modifier, mais le fichier est l'endroit
où vous êtes censé configurer les choses au quotidien.

Réglages de base, quotidiens, au niveau supérieur :

```json
{
  "db_path": ".wpm/wpm.db"
}
```

- `db_path` — **obligatoire**, chemin relatif vers la base de données
  SQLite — sans lui (ni `WPM_DB_PATH`), le serveur démarre inerte. Un
  chemin relatif est résolu **par rapport au répertoire de
  `wpm.config.json`**, pas par rapport au cwd du host. La base doit
  toujours vivre à l'intérieur de ce répertoire : le serveur refuse de
  démarrer si le chemin résolu sort du répertoire du projet (y compris via
  un symlink).
- `confidence_threshold` — **optionnel**, défaut `0.5`. Seuil de confiance
  sous lequel la resource `wpm://project-rules` n'injecte pas une entrée.
- `verification_command_patterns` — **optionnel**, défaut `[]` (aucun
  ajout). Liste de regex **ajoutées** à la liste en dur
  `VERIFICATION_COMMAND_PATTERNS` du serveur (`behavior.py`), pour désigner
  les commandes shell supplémentaires dont le succès compte comme preuve
  forte (`execution_verified`) dans `record_execution` — critère : pas de
  `ls`/`grep`/`cat`/`git status`.

`wpm enable --write-config` (voir le `README.md` racine) écrit ce fichier
automatiquement pour vous lors de l'activation d'un projet.

### Avancé : la section `domain` (réglage du scoring/récupération)

Tout ce qui précède suffit à la plupart des gens. La section `domain` est
facultative, séparée, et uniquement destinée aux formules de
scoring/récupération de la spécification (sections 3-6) — taux de
décroissance de la confiance, poids des preuves, pondération du score de
récupération, réglage de l'expansion de graphe. Omettez-la entièrement sauf
si vous voulez spécifiquement la régler. Voir `wpm.config.example.json`
pour l'ensemble complet avec chaque valeur par défaut et ce que chacune
contrôle.

Six sous-sections, toutes imbriquées sous `"domain"` :

| Section | Règle |
|---|---|
| `provenance` | Confiance de départ par valeur de `source` |
| `decay` | Taux d'érosion de la confiance (lambda) par `type` d'entrée |
| `evidence` | De combien `validation_score` bouge par `evidence_type`, confirmer vs. contredire |
| `validation` | Bornes du score et fenêtre de déduplication anti-boucle |
| `retrieval` | Pondération similarité / confiance / centralité dans le score final + plancher `min_similarity` pour les `direct_matches` |
| `expansion` | Réglage de l'expansion de graphe à 1 saut + seuil de similarité pour l'auto-liaison |

Ne remplacez que ce dont vous avez besoin :

```json
{
  "domain": {
    "retrieval": {
      "weight_similarity": 0.6
    }
  }
}
```

Une clé inconnue au niveau supérieur ou imbriquée lève une erreur claire au
démarrage plutôt que d'être silencieusement ignorée — une faute de frappe
dans le JSON est attrapée immédiatement au lieu de n'avoir aucun effet en
silence.

### Substitutions par variables d'environnement (facultatif)

| Variable | Remplace | Défaut si non définie (et pas de JSON) |
|---|---|---|
| `WPM_DB_PATH` | `db_path` | aucune — serveur inerte |
| `WPM_CONFIG_PATH` | quel fichier JSON lire | `wpm.config.json` (cwd) |
| `WPM_EMBEDDING_MODEL` | modèle d'embedding | `all-MiniLM-L6-v2` |

## Tests

```bash
pytest            # 12 fichiers de test à la racine (script-style via conftest)
```

- `test_repository.py`, `test_scoring.py`, `test_domain.py`,
  `test_embeddings.py`, `test_db.py`, `test_contradict_validation.py` — la
  couche dépôt, sans transport MCP
- `test_stdio.py` — protocole MCP complet sur stdio, comme un client réel
- `test_behavior.py` — règles, matching des commandes de vérification,
  rendu des project-rules
- `test_settings.py`, `test_db_path_precedence.py`,
  `test_db_path_constraint.py` — config et contrainte d'emplacement de la base
- `test_integration.py` — parcours complet depuis un vrai répertoire projet

## Ce qui n'est volontairement PAS encore implémenté

- La discipline du **working scope** (section 8 de la spécification : vidage
  avant compaction) était portée par les hooks du plugin OpenCode, supprimés
  dans cette version MCP-pure. Elle est remplacée par la discipline
  write-as-you-go des règles 4/13 + le prompt `persist`.
- Pas d'authentification/multi-location — suppose un seul fichier SQLite
  local par projet, conformément à la contrainte « local, fichier unique »
  de la spécification.
- Le seuil d'auto-liaison (similarité cosinus 0.82, défini dans `settings.py`
  via `ExpansionSettings.auto_link_similarity_threshold`, seulement utilisé
  dans `repository.py`) et toutes les constantes de scoring (`domain.py`)
  sont des valeurs par défaut
  à régler une fois que de vraies données d'utilisation existent — voir les
  sections 3-6 de la spécification pour les formules qu'elles implémentent.

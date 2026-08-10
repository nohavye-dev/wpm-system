# wpm-mcp-server

Confidence-weighted, serveur MCP de mémoire persistante hybride
vecteur+graphe — implémentation de référence Python du document de
spécification (sections 1-9).

Testé de bout en bout sur le vrai transport MCP stdio (`test_stdio.py`), pas
seulement testé unitairement contre la couche de dépôt.

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
```

Pour de vrais embeddings sémantiques (recommandé au-delà des tests locaux —
voir « Embeddings » ci-dessous) :

```bash
pip install -e ".[semantic-embeddings]"
```

`install.sh` à la racine du dépôt effectue une installation globale non
éditable dans un environnement virtuel géré
(`~/.local/share/wpm-system/venv`) ; l'installation manuelle ci-dessus
reste l'alternative pour le développement autonome.

## Exécution autonome

```bash
WPM_DB_PATH=./wpm.db python -m wpm_mcp_server
```

Parle MCP via stdio — le même sous-processus que lance le plugin OpenCode
global (avec les constantes fixes ci-dessous).

## Brancher dans OpenCode

Aucune entrée `mcp` n'est requise dans `opencode.json`. Le plugin OpenCode
global (`wpm-opencode-plugin`, installé par `install.sh` dans
`~/.config/opencode/plugins/wpm-plugin/`) expose les 5 outils de mémoire
directement à l'LLM via l'API du plugin et lance lui-même ce serveur comme
sous-processus. N'ajoutez pas aussi ce serveur comme entrée `mcp` dans
`opencode.json` : le plugin expose déjà les 5 outils sous ces noms, et deux
expositions du même nom entreraient en conflit. Le plugin est inerte par
projet : il ne s'active que si un `wpm.config.json` existe à la racine du
projet :

```json
{
  "db_path": ".wpm/wpm.db"
}
```

`wpm enable` écrit ce fichier pour vous et crée `.wpm/`. Le serveur est
ensuite lancé par le plugin avec des constantes fixes — interpréteur
`~/.local/share/wpm-system/venv/bin/python` (chemin respectant
`XDG_DATA_HOME`), arguments `["-m", "wpm_mcp_server"]`, répertoire de
travail = racine du projet — seul l'interpréteur est surchargeable via
l'environnement :

| Variable | Remplace |
|---|---|
| `WPM_DB_PATH` | `db_path` |
| `WPM_MCP_COMMAND` | l'interpréteur Python |

Le seuil de confiance se règle via la clé top-level `confidence_threshold`
de `wpm.config.json` (défaut 0.5). `WPM_CONFIDENCE_THRESHOLD` n'est pas lu
par le serveur : il est lu par le plugin OpenCode (hook de compaction).

Redémarrez OpenCode après tout changement — la configuration est lue une
seule fois au démarrage.

## Outils exposés

| Tool | Rôle |
|---|---|
| `store_entry(type, content, source)` | Créer une nouvelle entrée de mémoire |
| `query_context(query, min_confidence?, token_budget?)` | Récupération hybride : vecteur + confiance + graphe, avec expansion associative à 1 saut |
| `validate_entry(entry_id, evidence_type, evidence_ref, session_id)` | Enregistrer une preuve de confirmation (dédupliquée par session) |
| `contradict_entry(entry_id, conflicting_entry_id, evidence_type, evidence_ref)` | Enregistrer un conflit — ne supprime jamais, ne fait que réduire le poids et marquer |
| `link_entries(source_id, target_id, relation_type, weight?)` | Relation explicite (`related`/`contradicts`/`depends_on`/`refines`) |

`type` ∈ `doc`, `archi_decision`, `learning`, `convention`, `bug_pattern`.
`evidence_type` ∈ `execution_verified`, `cross_reference`,
`reuse_without_failure`, `agent_reasoning` (exclu du scoring — uniquement
journalisé, selon la section 4 de la spécification).

Les règles d'utilisation (contenu en anglais uniquement, exigences de
preuve, non-suppression) sont intégrées directement dans les descriptions
d'outils que l'agent voit à chaque appel — voir la section 8 de la
spécification pour savoir pourquoi cela est préféré au fait de s'appuyer
uniquement sur AGENTS.md.

## Embeddings

`embeddings.py` définit une interface `EmbeddingProvider`. Le défaut
(`HashingEmbeddingProvider`) est un **repli déterministe, hors ligne et sans
dépendance** — idéal pour exercer les rouages de stockage/récupération de
bout en bout, mais il n'a aucune véritable compréhension sémantique (c'est
du feature hashing, pas un modèle entraîné).

Pour une vraie recherche de similarité, activez `SentenceTransformerProvider`
via `wpm.config.json` — aucune modification de code nécessaire :

```json
{
  "embedding": {
    "provider": "sentence_transformers",
    "model": "all-MiniLM-L6-v2"
  }
}
```

`provider` accepte `null` / `"hashing"` (défaut, aucune dépendance
supplémentaire) ou `"sentence_transformers"`. `model` n'est utilisé que pour
ce dernier. Une valeur de `provider` inconnue lève une erreur au démarrage
au lieu de retomber silencieusement sur un repli.

Cela nécessite `pip install -e ".[semantic-embeddings]"` et un téléchargement
unique du modèle (accès réseau vers huggingface.co). `EMBEDDING_DIM` dans
`domain.py` doit correspondre à la dimension de sortie du modèle (384 pour
all-MiniLM-L6-v2, déjà le défaut) — le serveur le valide au démarrage et
échoue rapidement avec un message clair en cas de discordance.

Substitutions par variables d'environnement : `WPM_EMBEDDING_PROVIDER` et
`WPM_EMBEDDING_MODEL` remplacent le fichier JSON lorsqu'elles sont
définies.

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
  SQLite — le serveur refuse de démarrer sans lui (ou sans `WPM_DB_PATH`).
  Lu par ce serveur uniquement (jamais par le plugin OpenCode). La base
  doit toujours vivre à l'intérieur du répertoire du projet : le serveur
  refuse de démarrer si le chemin résolu sort du répertoire de travail.
- `confidence_threshold` — **optionnel**, défaut `0.5`. Validé par le
  serveur, utilisé par le hook de compaction du plugin.

`wpm enable` (voir le `README.md` racine du bundle) écrit ce fichier
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
| `WPM_DB_PATH` | `db_path` | aucune — obligatoire |
| `WPM_CONFIG_PATH` | quel fichier JSON lire | `wpm.config.json` (cwd) |
| `WPM_EMBEDDING_PROVIDER` | `embedding.provider` | (unset → hashing) |
| `WPM_EMBEDDING_MODEL` | `embedding.model` | `all-MiniLM-L6-v2` |

## Tests

```bash
python test_repository.py   # repository logic, no MCP transport
python test_stdio.py        # full MCP protocol over stdio, as a client would use it
```

## Ce qui n'est volontairement PAS encore implémenté

- La discipline du **working scope** (section 8 de la spécification : vidage
  avant compaction) vit dans le plugin OpenCode compagnon, pas ici — ce
  serveur reste un magasin passif d'enregistrements.
- Pas d'authentification/multi-location — suppose un seul fichier SQLite
  local par projet, conformément à la contrainte « local, fichier unique »
  de la spécification.
- Le seuil d'auto-liaison (similarité cosinus 0.82, défini dans `settings.py`
  via `ExpansionSettings.auto_link_similarity_threshold`, seulement utilisé
  dans `repository.py`) et toutes les constantes de scoring (`domain.py`)
  sont des valeurs par défaut
  à régler une fois que de vraies données d'utilisation existent — voir les
  sections 3-6 de la spécification pour les formules qu'elles implémentent.

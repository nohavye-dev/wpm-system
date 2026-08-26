# Configuration — `wpm.config.json`

Référence du fichier de configuration. **Dans la pratique, vous n'avez
souvent rien à écrire à la main** : `wpm enable` crée le fichier avec un
`db_path` par défaut, et la plupart des réglages sont optionnels.

---

## Ce qu'il faut savoir d'abord

`wpm.config.json` vit à la **racine du projet**. C'est le **marqueur
d'activation** : sans lui (ni `WPM_DB_PATH`), le serveur démarre en mode
**inerte** — il liste ses outils mais chaque appel renvoie « wpm is not
activated in this project ».

Le serveur est enregistré **automatiquement par le plugin OpenCode** (pas de
configuration manuelle dans `opencode.json`). Le fichier sert donc surtout à
dire *où* vit la base et, si besoin, à ajuster quelques réglages.

Exemple minimal (souvent suffisant) :

```json
{
  "db_path": ".wpm/wpm.db"
}
```

Une clé absente garde sa valeur par défaut ; une clé **inconnue** (typo)
fait lever une erreur explicite au démarrage plutôt que d'être ignorée.
Les clés commençant par `$` (méta-données éditeur) sont tolérées et
ignorées par le serveur.

---

## Validation dans l'éditeur (`$schema`)

Un JSON Schema décrit l'intégralité de la configuration (types, défauts,
descriptions) : `wpm-mcp-server/wpm.config.schema.json`, généré depuis le
code du serveur par `scripts/generate_config_schema.py`.

Trois façons de le référencer via la clé `"$schema"` :

| Niveau | Référence | Pour qui |
|---|---|---|
| Machine locale | chemin absolu vers `~/.local/share/wpm-system/wpm.config.schema.json` | **automatique** : `wpm enable` injecte la clé s'il trouve la copie locale |
| Dans ce repo | `"./wpm-mcp-server/wpm.config.schema.json"` | développement de wpm-system |
| Distant | `https://raw.githubusercontent.com/nohavye-dev/wpm-system/main/wpm-mcp-server/wpm.config.schema.json` | référence, machines sans installation |

Après modification des réglages serveur, régénérer schéma et exemple :

```bash
python3 scripts/generate_config_schema.py          # écrit les deux fichiers
python3 scripts/generate_config_schema.py --check  # vérifie la dérive
```

---

## Réglages de base

### `db_path` — base SQLite (requise)

```json
"db_path": ".wpm/wpm.db"
```

| | |
|---|---|
| Requis | oui (sinon serveur inerte) |

Chemin du fichier SQLite. Un chemin **relatif est résolu par rapport au
répertoire qui contient `wpm.config.json`**. La base doit rester **à
l'intérieur du projet** (un chemin qui en sort, y compris via un symlink,
est refusé). Précédence : `WPM_DB_PATH` (env) > `db_path` (fichier).

### `confidence_threshold` — seuil des project-rules (optionnel, défaut 0.5)

Seuil de confiance sous lequel une entrée n'est pas injectée dans le bloc
`<project-rules>` recomposé à partir de la mémoire. Uniquement réglable
dans le fichier (pas de variable d'env).

```json
"confidence_threshold": 0.6
```

### `response_language` — langue des réponses (optionnel, défaut auto)

Fixe la langue des **réponses, résumés et rapports** de l'agent — **pas**
le contenu stocké, qui reste dans sa langue native (le modèle d'embedding
est multilingue).

- Absent, `null` ou `"auto"` : l'agent répond dans la langue de
  l'utilisateur.
- Valeur fixe (ex. `"french"`) : l'agent répond toujours dans cette langue.

```json
"response_language": "french"
```

Surcharge : `WPM_RESPONSE_LANGUAGE`. La valeur est lue au démarrage du
serveur (redémarrage requis pour changer).

### `verification_command_patterns` — commandes de preuve forte (optionnel, défaut [])

Liste de regex **ajoutées** à la liste en dur des commandes dont le succès
compte comme preuve forte (`execution_verified`) pour `record_execution`.

```json
"verification_command_patterns": ["\\bmy-custom-runner\\b"]
```

N'ajouter que des commandes dont `exit 0` **prouve** quelque chose (tests,
build, lint). Ne **jamais** ajouter `ls`, `cat`, `echo`, `grep`, `git
status`/`diff` : `exit 0` n'y prouve rien.

---

## Mode plugin maître (`plugin_master`)

Deux architectures coexistent, choisies par une clé booléenne :

| | Legacy (défaut) | `"plugin_master": true` |
|---|---|---|
| Serveur MCP | hébergé par OpenCode (enregistré par le plugin) | spawné et possédé par le plugin |
| Règles projet | tirées par l'agent (lecture de la resource) | poussées chaque tour dans le contexte |
| Règles d'or + profil utilisateur | injectés via `initialize.instructions` + lecture de resource | poussés chaque tour dans le contexte |
| Recherche mémoire | tool `wpm_query_context` (à l'initiative du LLM) | idem + **pop-in** automatique des mémoires fortement pertinentes |
| Enregistrement des exécutions | via le CLI `wpm` | appel direct du serveur chaud |

```json
{
  "db_path": ".wpm/wpm.db",
  "plugin_master": true
}
```

Sans la clé (ou avec `false`), le comportement historique s'applique à
l'identique. Les deux réglages ci-dessous ne prennent effet qu'en mode
maître.

### `rag_similarity_threshold` — seuil du pop-in (optionnel, défaut 0.35)

Similarité cosinus minimale entre le message brut de l'utilisateur et une
entrée mémoire pour que celle-ci soit injectée automatiquement dans le
contexte, combinée à `confidence_threshold` comme garde de qualité. Abaissé
de 0.45 à 0.35 après calibration end-to-end du rappel (voir
`docs/internals/recall-rag-calibration.md`).

### `rag_max_items` — volume du pop-in (optionnel, défaut 5)

Nombre maximal d'entrées injectées par tour, après filtrage et déduplication
contre le bloc `<project-rules>`.

```json
"rag_similarity_threshold": 0.35,
"rag_max_items": 5
```

Ces deux clés ne sont lues que par le plugin (mode maître) ; les valeurs
déclarées côté serveur servent à la validation du schéma.

---

## Avancé : la section `domain`

**À laisser de côté sauf besoin explicite de tuning.** Cette section ne
concerne que les formules de scoring et de récupération. Elle est composée
de 6 sous-sections, toutes sous `"domain"` :

| Section | Règle |
|---|---|
| `provenance` | confiance de départ selon la `source` |
| `decay` | vitesse d'érosion de la confiance (λ) par `type` |
| `evidence` | de combien `validation_score` bouge par preuve |
| `validation` | bornes du score + fenêtre de déduplication |
| `retrieval` | pondération similarité/confiance/centralité |
| `expansion` | expansion de graphe + seuils d'auto-liaison |

On ne remplace que ce dont on a besoin :

```json
{
  "db_path": ".wpm/wpm.db",
  "domain": {
    "retrieval": { "weight_similarity": 0.6 }
  }
}
```

Le détail complet de chaque sous-section, avec ses valeurs par défaut, est
dans [`wpm-mcp-server/wpm.config.example.json`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/wpm.config.example.json).

---

## Variables d'environnement

| Variable | Remplace |
|---|---|
| `WPM_CONFIG_PATH` | quel fichier JSON est lu |
| `WPM_DB_PATH` | `db_path` |
| `WPM_RESPONSE_LANGUAGE` | `response_language` |
| `WPM_EMBEDDING_MODEL` | modèle d'embedding (défaut `paraphrase-multilingual-MiniLM-L12-v2`) |

Les clés de `domain` n'ont pas de variable d'env : réglables uniquement via
le fichier.

---

## Embeddings

Les embeddings utilisent ONNX Runtime + tokenizers HuggingFace, modèle
`paraphrase-multilingual-MiniLM-L12-v2` (384 dimensions, 50 langues),
pré-téléchargé à l'installation et mis en cache. Changer de modèle
(`WPM_EMBEDDING_MODEL`) après avoir inséré des entrées nécessite de
ré-embedder la base : lancez `wpm reembed` à la racine du projet (le serveur
refuse de requêter une base dont les vecteurs viennent d'un autre modèle tant
que ce n'est pas fait).

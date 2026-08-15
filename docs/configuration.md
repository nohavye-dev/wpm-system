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
le contenu stocké, qui reste en anglais.

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
dans [`wpm-mcp-server/wpm.config.example.json`](../wpm-mcp-server/wpm.config.example.json).

---

## Variables d'environnement

| Variable | Remplace |
|---|---|
| `WPM_CONFIG_PATH` | quel fichier JSON est lu |
| `WPM_DB_PATH` | `db_path` |
| `WPM_RESPONSE_LANGUAGE` | `response_language` |
| `WPM_EMBEDDING_MODEL` | modèle d'embedding (défaut `all-MiniLM-L6-v2`) |

Les clés de `domain` n'ont pas de variable d'env : réglables uniquement via
le fichier.

---

## Embeddings (fixes)

Les embeddings utilisent ONNX Runtime + tokenizers HuggingFace, modèle
`all-MiniLM-L6-v2` (384 dimensions), téléchargé au premier démarrage et mis
en cache. Changer de modèle (`WPM_EMBEDDING_MODEL`) après avoir inséré des
entrées nécessite de ré-embedder la base (supprimez `.wpm/wpm.db`).

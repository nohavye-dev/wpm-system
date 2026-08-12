# `wpm.config.json` — référence de configuration

## Où vit la config

`wpm.config.json` se trouve à la **racine du projet**. C'est aussi le **marqueur d'activation** du plugin global : à chaque démarrage d'OpenCode, le plugin vérifie l'existence de ce fichier à la racine du projet courant.

- Fichier **absent** → le plugin est inerte : aucun outil exposé, aucun hook, aucun serveur lancé.
- Fichier **présent** → le plugin s'active et expose les 10 outils mémoire directement à l'LLM : `store_entry`, `query_context`, `validate_entry`, `contradict_entry`, `link_entries`, `get_memory_stats`, `pin_entry`, `deprecate_entry`, `restore_entry`, `list_entries`.

Le fichier est normalement écrit par `wpm enable` (qui remplit `db_path` par défaut `.wpm/wpm.db` s'il est absent) et supprimé par `wpm disable` (les données sont conservées). Il peut aussi être localisé via `WPM_CONFIG_PATH`.

Une clé absente garde sa valeur par défaut ; le fichier peut être partiel. Une clé **inconnue** (typo) fait lever une erreur explicite au démarrage du serveur plutôt que d'être ignorée silencieusement.

---

## `db_path` — base de données SQLite (obligatoire)

```json
"db_path": ".wpm/wpm.db"
```

| | |
|---|---|
| Type | string (chemin) |
| Requis | oui |
| Défaut si absent | Aucune — le serveur refuse de démarrer sans db_path ou WPM_DB_PATH |

Chemin vers le fichier SQLite. Un chemin **relatif est résolu par rapport à la racine du projet** — `wpm enable` écrit `.wpm/wpm.db` s'il est absent (les clés existantes — dont `db_path` — sont préservées). Le chemin doit pointer **à l'intérieur de la racine du projet** : `wpm enable` refuse un `db_path` qui en sort (chemin absolu externe, ou relatif avec `..`), et le serveur refuse de démarrer si le chemin résolu sort du répertoire de travail. Précédence : `WPM_DB_PATH` (variable d'env) > `db_path` (config). Aucune valeur par défaut : sans l'un des deux, le serveur lève une erreur explicite au démarrage.

---

## `confidence_threshold` — seuil de confiance du hook de compaction [optionnel]

Clé **top-level** optionnelle (défaut `0.5`), validée par le serveur mais
utilisée par le plugin OpenCode : c'est le seuil de confiance sous lequel le
hook `experimental.session.compacting` n'injecte pas une entrée dans le
contexte préservé avant compaction. Il pilote aussi l'**injection des règles
projet** dans le prompt système (`experimental.chat.system.transform`) : seules
les conventions/décisions `≥ confidence_threshold` y sont injectées de façon
déterministe.

```json
"confidence_threshold": 0.6
```

Précédence : `WPM_CONFIDENCE_THRESHOLD` (variable d'env) > `confidence_threshold` (fichier) > `0.5`.

---

## `idle_nudge` — relance en session inactive [optionnel]

Clé **top-level** optionnelle (défaut `false`), validée par le serveur
comme clé connue mais **utilisée par le plugin OpenCode**. Quand elle est
active, le plugin envoie une seule relance à l'agent (`promptAsync`) quand
une session qui a **réellement travaillé** (édition de fichier, outil
exécuté) devient inactive, pour lui rappeler de persister ce qui n'a pas
encore été stocké. Sans elle, le hook `session.idle` se contente d'une
entrée de journal passive.

```json
"idle_nudge": true
```

Conditions et limites :
- **Opt-in explicite** : défaut `false`, on n'embête jamais l'agent sans
  demande.
- Une seule relance **par session** (même si la session redevient
  inactive plusieurs fois).
- Uniquement pour une session ayant montré de l'activité (édition,
  outil de travail) — une session en simple lecture n'est jamais relancée.
- En cas d'échec d'envoi, la relance est simplement journalisée (pas de
  nouvelle tentative dans la même session).

Précédence : `WPM_IDLE_NUDGE` (variable d'env, `"true"`/`"false"`) >
`idle_nudge` (fichier) > `false`.

---

## `verification_command_patterns` — ajouts de commandes de preuve forte [optionnel]

Clé **top-level** optionnelle (défaut `[]` : aucun ajout), validée par le
serveur comme clé connue mais **utilisée par le plugin OpenCode**. C'est
une liste de regex **ajoutée** à la liste en dur `VERIFICATION_COMMAND_PATTERNS`
du plugin (`src/index.ts`) qui désigne les commandes shell dont le succès
compte comme preuve forte (`execution_verified`) dans le hook
`tool.execute.after`. **Sémantique = addition, pas remplacement** : on ne
peut pas retirer une commande de la liste en dur.

```json
"verification_command_patterns": [
  "\\bmy-custom-runner\\b"
]
```

| | |
|---|---|
| Type | liste de strings (regex JavaScript valides) |
| Défaut si absent | `[]` — aucune commande ajoutée à la liste en dur |
| Sémantique | addition aux built-ins ; une liste vide n'ajoute rien |

**Critère** : un pattern ne doit compter que si `exit 0` prouve que quelque
chose de *correct* est vérifié (les tests passent, le build compile, le
typecheck/lint passe). Chaque commande matchée déclenche `store_entry` +
validation : un pattern trop laxiste inonde la mémoire de bruit.

**Anti-patterns — à ne pas ajouter** : `ls`, `cat`, `echo` (`exit 0`
toujours vrai, aucun signal de correction) ; `grep` (observation, pas
vérification) ; `git status` / `git diff` (observation d'état). Pour une
preuve ponctuelle qui a de la valeur, ne pas l'ajouter à la liste : faire
`validate_entry` avec `evidence_type: "execution_verified"` et un
`evidence_ref` pointant le log/la commande — même force de preuve, sans
polluer l'auto-capture.

---

## Embeddings [intégré, non configurable]

Les embeddings sémantiques sont inclus par défaut via ONNX Runtime +
tokenizers HuggingFace (~100 MB de dépendances obligatoires). Le modèle
`all-MiniLM-L6-v2` (384 dimensions) est téléchargé automatiquement depuis
HuggingFace Hub au premier démarrage et mis en cache localement. Aucune
section `embedding` dans `wpm.config.json` — le fournisseur et le modèle
sont fixes côté serveur.

Pour changer de modèle : positionnez `WPM_EMBEDDING_MODEL` dans
l'environnement (ex. `WPM_EMBEDDING_MODEL=all-mpnet-base-v2`). Le modèle
doit être disponible sur HuggingFace Hub sous `sentence-transformers/` et
avoir une exportation ONNX (`onnx/model.onnx`). Changer de modèle après
avoir déjà inséré des entrées nécessite de ré-embedder la base (supprimez
`.wpm/wpm.db` et recommencez).

---

## `domain` — configuration avancée (scoring et retrieval) [optionnel]

Section **optionnelle** de tuning avancé du scoring, composée de 6 sous-sections : `provenance`, `decay`, `evidence`, `validation`, `retrieval`, `expansion`. Elle est **préservée par `wpm enable`** si elle existe déjà dans le fichier. Uniquement lue par le serveur Python. **À laisser de côté sauf besoin explicite de tuning** — les 6 sous-sections suivantes ne concernent que le calcul du score de confiance et du retrieval, pas le fonctionnement de base.

### `domain.provenance`

Confiance de départ (`provenance_score`) attribuée à une entrée à sa
création, selon la valeur de `source` passée à `store_entry`.

```json
"provenance": {
  "base_confidence": {
    "official_doc": 0.9,
    "observed_code": 0.75,
    "tool_execution": 0.7,
    "agent_inference": 0.35
  },
  "default": 0.5
}
```

| Clé | Type | Rôle |
|---|---|---|
| `base_confidence` | objet `{source: float}` | Confiance de départ par valeur de `source`. Clés arbitraires — n'importe quelle chaîne passée en `source` à `store_entry` peut avoir sa propre entrée ici. |
| `default` | float | Confiance appliquée si `source` ne correspond à aucune clé de `base_confidence`. |

Les 4 clés par défaut (`official_doc`, `observed_code`, `tool_execution`,
`agent_inference`) sont des **conventions**, pas des valeurs figées dans
le code des enums — tu peux en ajouter d'autres dans le JSON (ex:
`"client_email": 0.8`) sans toucher au code.

### `domain.decay`

Vitesse d'érosion de la confiance dans le temps depuis la dernière
validation, par type d'entrée.

```json
"decay": {
  "lambda_per_type": {
    "archi_decision": 0.002,
    "convention": 0.003,
    "doc": 0.004,
    "learning": 0.008,
    "bug_pattern": 0.015
  },
  "default_lambda": 0.01
}
```

| Clé | Type | Rôle |
|---|---|---|
| `lambda_per_type` | objet `{type: float}` | Taux de décroissance (λ) par valeur de `type` (`doc`, `archi_decision`, `learning`, `convention`, `bug_pattern` — ce sont les seules valeurs valides pour `type` dans `store_entry`, contrairement à `source` ci-dessus). |
| `default_lambda` | float | Utilisé si un type n'a pas d'entrée dans `lambda_per_type` (ne devrait pas arriver avec les 5 types standards, sert de filet de sécurité). |

Formule appliquée (voir `scoring.py::confidence_at`) :

```
confidence(t) = min(1, provenance_score + validation_score) × exp(−λ × heures_écoulées)
```

Plus λ est **grand**, plus la confiance chute vite. `bug_pattern` (0.015)
décroît environ 7× plus vite que `archi_decision` (0.002) — une décision
d'architecture reste valable longtemps, un pattern de bug observé devient
vite obsolète si non revalidé.

### `domain.evidence`

Combien `validation_score` bouge à chaque preuve reçue via
`validate_entry` / `contradict_entry`, selon le type de preuve.

```json
"evidence": {
  "confirm_weight": {
    "execution_verified": 0.25,
    "cross_reference": 0.15,
    "reuse_without_failure": 0.05,
    "agent_reasoning": 0.0
  },
  "contradict_weight": {
    "execution_verified": 0.4,
    "cross_reference": 0.25,
    "reuse_without_failure": 0.1,
    "agent_reasoning": 0.0
  }
}
```

| Clé | Type | Rôle |
|---|---|---|
| `confirm_weight` | objet `{evidence_type: float}` | Incrément appliqué à `validation_score` sur `validate_entry`. |
| `contradict_weight` | objet `{evidence_type: float}` | Décrément appliqué sur `contradict_entry`. |

Les 4 clés (`execution_verified`, `cross_reference`,
`reuse_without_failure`, `agent_reasoning`) sont les seules valeurs
valides pour `evidence_type` — contrairement à `source` en
`domain.provenance`, ces clés correspondent à un enum fermé côté code
(`EvidenceType`), pas une convention libre.

**Asymétrie intentionnelle** : chaque poids de `contradict_weight` est
plus élevé que son équivalent dans `confirm_weight` (0.4 vs 0.25 pour
`execution_verified`) — une contradiction fait chuter la confiance plus
vite qu'une confirmation ne la fait monter (principe de falsifiabilité,
spec section 4).

`agent_reasoning` à `0.0` dans les deux tables : une validation par
simple raisonnement de l'agent, sans preuve externe, est journalisée
(traçabilité) mais ne fait jamais bouger le score, quelle que soit la
valeur ici — c'est appliqué en dur dans `repository.py`, pas piloté par
ce fichier (mettre une valeur non nulle ici n'aurait aucun effet).

### `domain.validation`

```json
"validation": {
  "score_min": 0.0,
  "score_max": 1.0,
  "dedup_window_seconds": 1800
}
```

| Clé | Type | Rôle |
|---|---|---|
| `score_min` | float | Borne basse de `validation_score` (clampé après chaque preuve). |
| `score_max` | float | Borne haute de `validation_score`. |
| `dedup_window_seconds` | int (secondes) | Fenêtre anti-boucle : une validation répétée sur la même entrée, dans la même `session_id`, à l'intérieur de cette fenêtre, ne compte qu'une fois (spec section 4/8). Défaut : 1800s = 30 minutes. |

### `domain.retrieval`

Pondération du score final retourné par `query_context`.

```json
"retrieval": {
  "weight_similarity": 0.5,
  "weight_confidence": 0.35,
  "weight_centrality": 0.15,
  "min_similarity": 0.1
}
```

Formule (voir `repository.py::_score_entry`) :

```
score = weight_similarity × similarité_cosinus
      + weight_confidence × confidence(t)
      + weight_centrality × centralité_graphe
```

| Clé | Type | Rôle |
|---|---|---|
| `weight_similarity` | float | Poids de la similarité vectorielle brute avec la requête. |
| `weight_confidence` | float | Poids de la confiance actuelle de l'entrée (voir `domain.decay`). |
| `weight_centrality` | float | Poids du nombre/poids de liens entrants dans le graphe (`entry_links`) — une entrée référencée par beaucoup d'autres remonte plus haut. |
| `min_similarity` | float | Plancher de similarité cosinus pour `direct_matches` de `query_context` : sous ce seuil, une entrée est du bruit et est exclue, même avec `min_confidence` à 0 (le défaut). `related_context` (expansion de graphe) n'est pas soumis à ce plancher, seulement à `expansion.min_confidence`. |

Ces 3 poids ne sont **pas contraints de sommer à 1** par le code — libre
à toi de les rééquilibrer, mais garder une somme ≈1 facilite
l'interprétation du score final comme une moyenne pondérée.

### `domain.expansion`

Tuning de l'expansion associative par graphe (1 saut, spec section 6) et
du seuil de création automatique de liens implicites.

```json
"expansion": {
  "hop_decay": 0.5,
  "min_confidence": 0.3,
  "top_n_candidates": 20,
  "auto_link_similarity_threshold": 0.82,
  "contradiction_alert_threshold": 0.92
}
```

| Clé | Type | Rôle |
|---|---|---|
| `hop_decay` | float | Facteur multiplicatif appliqué au score d'une entrée atteinte par expansion (1 saut dans `entry_links`) plutôt que par similarité directe. `0.5` = une entrée liée compte pour moitié moins qu'un match direct de même similarité. |
| `min_confidence` | float | Confiance minimum pour qu'une entrée trouvée par expansion (pas par match direct) soit incluse dans `related_context`. |
| `top_n_candidates` | int | Nombre de candidats récupérés par la recherche vectorielle brute (`k` dans la requête `sqlite-vec`), avant filtrage/scoring. |
| `auto_link_similarity_threshold` | float | Seuil de similarité cosinus au-delà duquel `store_entry` crée automatiquement un lien implicite `related` avec une entrée existante. |
| `contradiction_alert_threshold` | float | Seuil de similarité cosinus au-delà duquel `store_entry` signale une entrée existante comme candidate à la contradiction dans le champ `potential_contradictions` de la réponse. Ne crée pas de lien automatiquement — c'est au LLM d'évaluer les candidates et d'appeler `contradict_entry` si les contenus sont effectivement contradictoires. |

---

## Constantes de lancement du serveur

Les paramètres de lancement du serveur MCP sont des constantes du
plugin :

| Constante | Valeur fixe |
|---|---|
| `mcp_command` | `~/.local/share/wpm-system/venv/bin/python` (chemin respectant `XDG_DATA_HOME`) |
| `mcp_args` | `["-m", "wpm_mcp_server"]` (fixes) |
| `mcp_cwd` | racine du projet (fixe) |

Ces constantes ne se modifient **pas** dans le fichier de config — seul
`WPM_MCP_COMMAND` (l'interpréteur) est surchargeable via l'environnement
(voir la table de précédence ci-dessous). `confidence_threshold` n'est plus
une constante de lancement : il se règle via la clé de config décrite
ci-dessus. Le serveur continue de fonctionner en standalone
(`python -m wpm_mcp_server` avec `WPM_DB_PATH` etc.).

---

## Exemple minimal

Tu n'as besoin d'écrire que ce que tu veux changer — tout le reste
garde sa valeur par défaut :

```json
{
  "db_path": ".wpm/wpm.db"
}
```

Avec une section `domain` optionnelle :

```json
{
  "db_path": ".wpm/wpm.db",
  "domain": {
    "retrieval": {
      "weight_similarity": 0.6
    }
  }
}
```

---

## Table de précédence (variable d'env > fichier > défaut)

| Variable d'env | Surcharge |
|---|---|
| `WPM_CONFIG_PATH` | quel fichier JSON est lu (chemin du fichier lui-même, pas une clé à l'intérieur) |
| `WPM_DB_PATH` | `db_path` |
| `WPM_MCP_COMMAND` | surcharge l'interpréteur du plugin |
| `WPM_CONFIDENCE_THRESHOLD` | `confidence_threshold` |
| `WPM_IDLE_NUDGE` | `idle_nudge` (parse `"true"`/`"false"`) |

Les clés de `domain` n'ont pas de variable d'env — cette section n'est
configurable que via le fichier JSON. Les variables d'environnement côté
serveur (par champ) passent devant le fichier de config ; les constantes
du plugin ne sont surchargeables que par leurs variables d'env
respectives.

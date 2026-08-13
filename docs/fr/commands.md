# Workflows `learn`, `map`, `audit`, `bootstrap` et `patterns`

Les cinq workflows sont des **prompts MCP** exposés par le serveur, invoqués
manuellement par l'utilisateur. Dans opencode ils apparaissent comme commandes
slash (ex. `/wpm:learn:mcp`) ; dans tout autre host MCP, comme des prompts
du serveur `wpm`. Ils offrent un moyen **contrôlé** d'intégrer de la
documentation et du code dans la mémoire persistante du projet.

> **Deux canaux de mémorisation, ne pas les confondre**
>
> - **Mémorisation incrémentale (agent, automatique)** : au fil du travail,
>   le LLM persistе tout fait durable qu'il rencontre (`store_entry`,
>   `validate_entry`…) — c'est le comportement par défaut, décrit dans
>   [`memory-behavior-spec.md`](memory-behavior-spec.md). Les prompts ne le
>   remplacent ni ne le bloquent.
> - **Ingestion contrôlée (utilisateur, manuelle)** : `learn`,
>   `map` et `bootstrap` servent à l'apport massif et vérifié
>   de documents, d'une cartographie du code ou d'un peuplement
>   initial. On ne les utilise pas pour des faits
>   ponctuels rencontrés pendant une tâche.

## Garde commune

Si `wpm.config.json` n'existe pas à la racine du projet, la mémoire n'est
pas activée. Le prompt le signale poliment : lancez
`wpm enable --write-config` à la racine du projet, ajoutez l'entrée `mcp`
affichée dans la configuration de votre host, puis redémarrez le host.

Si aucun chemin n'est fourni à `learn` ou `map`, le prompt affiche
**uniquement son usage** (la ligne `USAGE:` ci-dessous) et ne fait rien
d'autre — il ne devine ni fichier ni périmètre.

---

## `learn <chemins>`

Ingère un ou plusieurs documents markdown existants dans la mémoire
persistante. Les chemins sont séparés par des espaces (guillemets pour les
chemins avec espaces) ; chaque fichier est traité dans l'ordre.

- Chaque document est **découpé par sections** (`##`/`###`, ou paragraphes
  logiques) — chaque section devient une entrée de mémoire candidate.
- **Déduplication** : avant chaque écriture, `query_context` vérifie si le
  fait existe déjà (similarité ~0.85) → au lieu d'un doublon,
  `validate_entry` avec `evidence_type: "cross_reference"` pointant vers
  le fichier.
- Contenu **traduit en anglais**, reformulé de façon concise (cohérence des
  embeddings), jamais copié à l'identique.
- `type` inféré (`doc`, `archi_decision`, `convention`, `bug_pattern`),
  `source: "official_doc"`.
- Les sections liées entre elles sont reliées via `link_entries` quand la
  relation est explicite.
- Le prompt rend un **résumé** en fin de parcours : par fichier, sections
  stockées, dédupliquées/revalidées, ignorées (et pourquoi).

Sans chemin : affiche l'usage et s'arrête — ne devine pas de fichier.

---

## `map [scopes]`

Cartographie l'architecture et les conventions de la base de code dans la
mémoire persistante. Les scopes (répertoires ou fichiers) sont séparés par
des espaces ; chacun est parcouru dans l'ordre.

- Ce n'est **pas un index fichier par fichier** : seuls quelques faits
  structurants durables sont extraits, toujours ancrés dans du code
  réellement lu (pas des noms de dossiers devinés).
- Types utilisés : `archi_decision` (choix structurel observé),
  `convention` (règle suivie de façon cohérente), `bug_pattern` (problème
  connu documenté, jamais supposé), `source: "observed_code"`.
- Même déduplication que `learn` (`query_context` avant écriture,
  `validate_entry` au lieu d'un doublon).
- Le prompt rend un **résumé** : ce qui a été stocké (groupé par type),
  revalidé, et surtout ce qui a été envisagé puis **écarté** faute de
  confiance suffisante.

Sans scope : affiche l'usage et s'arrête — ne devine pas de périmètre.

## `audit`

Affiche un tableau de bord de la santé de la mémoire persistante.

- Appelle l'outil MCP `get_memory_stats` — un seul appel, lecture seule.
- Présente les résultats en sections :
  - **Total par type** (`archi_decision`, `convention`, `doc`, `insight`, `bug_pattern`, `execution_result`)
  - **Distribution de confiance** : high (>0.7), medium (0.3-0.7), low (<0.3)
  - **⚠ Entrées jamais validées** — jamais confirmées par test, cross-reference ou réutilisation
  - **⚠ Contradictions actives** — paires d'entrées en conflit non résolu
  - **🔻 5 entrées les plus faibles** — avec leur confiance et aperçu du contenu
  - **Activité récente** — 10 derniers événements (créations, validations, contradictions, pin/deprecate)
- Se termine par un verdict : "Memory is healthy" ou "N issues need attention".
- C'est un diagnostic en lecture seule — aucune entrée n'est modifiée.
- Si le dashboard révèle des problèmes (entrées faibles, contradictions non résolues), le prompt peut suggérer des actions concrètes : épingler des entrées fiables avec `pin_entry`, déprécier des entrées obsolètes avec `deprecate_entry`, ou restaurer une entrée dépréciée par erreur avec `restore_entry`.

---

## `bootstrap`

Peuple la mémoire à partir des artefacts existants du projet — en une seule
passe. C'est l'équivalent d'un `learn` + `map` généralisé, mais
appliqué à tout le projet.

Lit automatiquement, dans l'ordre :
1. **`README.md`** — description du projet, stack technique, architecture
2. **Documentation** (`docs/` ou `doc/`) — décisions d'architecture et
   conventions documentées explicitement
3. **Configuration de lint/style** (`.editorconfig`, `eslint.config.*`,
   `ruff.toml`, `tsconfig.json`, etc.) — conventions de code imposées
4. **Dépendances et tooling** (`package.json`, `pyproject.toml`,
   `Cargo.toml`, `Makefile`, etc.) — framework, gestionnaire de paquets,
   commandes standard
5. **CI/CD** (`.github/workflows/`, `.gitlab-ci.yml`) — étapes de pipeline,
   commandes de validation officielles
6. **Structure de dossiers** (top 2 niveaux) — couches et modules, avec
   vérification dans le code (pas de déduction depuis les noms de dossiers
   seuls)

Pour chaque fait trouvé : déduplication via `query_context`, puis
`store_entry(type, content, source="observed_code")`. Le prompt rend
un résumé groupé par type (`archi_decision`, `convention`, `insight`).

À utiliser une seule fois par projet, après `wpm enable --write-config`,
pour peupler rapidement la mémoire avec ce qui existe déjà. La mémorisation
incrémentale au fil du travail continue ensuite normalement.

---

## `patterns [type]`

Analyse la mémoire pour détecter des patterns récurrents et proposer
des améliorations — conventions manquantes, décisions d'architecture
implicites, contradictions à résoudre.

Utilise `list_entries` pour récupérer toutes les entrées du type ciblé,
puis les catégorise par thème sémantique (jugement humain, pas similarité
vectorielle). Pour chaque thème avec 3+ entrées, identifie un pattern
actionnable :

- Thème de `bug_pattern` récurrent → suggère une `convention` pour les
  prévenir
- Convention validée 3+ fois → propose de l'épingler avec `pin_entry`
- Contradiction non résolue depuis longtemps → propose de trancher et de
  déprécier l'entrée la plus faible
- `insight` confirmant un choix structurel → propose de le solidifier
  en `archi_decision`

Les actions sont exécutées automatiquement (pas de confirmation par
action). Le prompt rend un rapport structuré : thèmes trouvés, actions
prises, et ce qui n'a pas nécessité d'action. Si aucun pattern n'émerge,
le résultat négatif est valide et signalé clairement.

## Notes

- Les cinq prompts sont déclarés dans `wpm-mcp-server` sous les mêmes noms
  (`learn`, `map`, `audit`, `bootstrap`, `patterns`), à
  côté de `persist` (checklist de fin de tâche).
- Lire le résumé renvoyé : des sections/faits écartés volontairement (trop
  vagues, trop incertains) indiquent un travail de sélection, pas un échec.
- Après une ingestion, vous pouvez renforcer une entrée par des preuves
  supplémentaires (`validate_entry`, `contradict_entry`) au fil des
  sessions suivantes.

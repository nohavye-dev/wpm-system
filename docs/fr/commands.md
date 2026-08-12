# Commandes `/wpm-doc`, `/wpm-code` et `/wpm-review`

Les deux commandes sont des **commandes slash opencode** exécutées
manuellement par l'utilisateur. Elles offrent un moyen **contrôlé** d'intégrer
de la documentation et du code dans la mémoire persistante du projet.

Elles sont installées **globalement** par `install.sh` dans
`~/.config/opencode/commands/` et disponibles dans tous les projets. Les
versions opérationnelles vivent dans `wpm-commands/` à la racine du dépôt.

> **Deux canaux de mémorisation, ne pas les confondre**
>
> - **Mémorisation incrémentale (agent, automatique)** : au fil du travail,
>   le LLM persistе tout fait durable qu'il rencontre (`store_entry`,
>   `validate_entry`…) — c'est le comportement par défaut, décrit dans
>   [`memory-behavior-spec.md`](memory-behavior-spec.md). Les commandes ne
>   le remplacent ni ne le bloquent.
> - **Ingestion contrôlée (utilisateur, manuelle)** : `/wpm-doc` et
>   `/wpm-code` servent à l'apport massif et vérifié d'un document complet
>   ou d'une cartographie du code. On ne les utilise pas pour des faits
>   ponctuels rencontrés pendant une tâche.

## Garde commune

Si `wpm.config.json` n'existe pas à la racine du projet, la mémoire n'est
pas activée. La commande le signale poliment : lancez `wpm enable` à la
racine du projet puis redémarrez opencode.

---

## `/wpm-doc <chemin>`

Ingère un document markdown existant dans la mémoire persistante.

```
/wpm-doc docs/architecture.md
```

- Le document est **découpé par sections** (`##`/`###`, ou paragraphes
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
- La commande rend un **résumé** en fin de parcours : sections stockées,
  dédupliquées/revalidées, ignorées (et pourquoi).

Si aucun chemin n'est fourni, la commande demande un chemin et s'arrête —
elle ne devine pas de fichier.

---

## `/wpm-code [scope]`

Cartographie l'architecture et les conventions de la base de code dans la
mémoire persistante.

```
/wpm-code
/wpm-code wpm-opencode-plugin/src
```

- Si `<scope>` est vide, tout le projet est cartographié ; sinon, le
  sous-arbre nommé.
- Ce n'est **pas un index fichier par fichier** : seuls quelques faits
  structurants durables sont extraits, toujours ancrés dans du code
  réellement lu (pas des noms de dossiers devinés).
- Types utilisés : `archi_decision` (choix structurel observé),
  `convention` (règle suivie de façon cohérente), `bug_pattern` (problème
  connu documenté, jamais supposé), `source: "observed_code"`.
- Même déduplication que `/wpm-doc` (`query_context` avant écriture,
  `validate_entry` au lieu d'un doublon).
- La commande rend un **résumé** : ce qui a été stocké (groupé par type),
  revalidé, et surtout ce qui a été envisagé puis **écarté** faute de
  confiance suffisante.

## `/wpm-review`

Affiche un tableau de bord de la santé de la mémoire persistante.

```
/wpm-review
```

- Appelle l'outil MCP `get_memory_stats` — un seul appel, lecture seule.
- Présente les résultats en sections :
  - **Total par type** (`archi_decision`, `convention`, `doc`, `learning`, `bug_pattern`)
  - **Distribution de confiance** : high (>0.7), medium (0.3-0.7), low (<0.3)
  - **⚠ Entrées jamais validées** — jamais confirmées par test, cross-reference ou réutilisation
  - **⚠ Contradictions actives** — paires d'entrées en conflit non résolu
  - **🔻 5 entrées les plus faibles** — avec leur confiance et aperçu du contenu
  - **Activité récente** — 10 derniers événements (créations, validations, contradictions, pin/deprecate)
- Se termine par un verdict : "Memory is healthy" ou "N issues need attention".
- C'est un diagnostic en lecture seule — aucune entrée n'est modifiée.
- Si le dashboard révèle des problèmes (entrées faibles, contradictions non résolues), la commande peut suggérer des actions concrètes : épingler des entrées fiables avec `pin_entry`, déprécier des entrées obsolètes avec `deprecate_entry`, ou restaurer une entrée dépréciée par erreur avec `restore_entry`.

---

- Les deux commandes tournent en **tâche annexe** (`subtask: true`,
  `agent: build`) : elles ne polluent pas le contexte de la conversation
  principale et rendent leur résumé à la fin.
- Lire le résumé renvoyé : des sections/faits écartés volontairement (trop
  vagues, trop incertains) indiquent un travail de sélection, pas un échec.
- Après une ingestion, vous pouvez renforcer une entrée par des preuves
  supplémentaires (`validate_entry`, `contradict_entry`) au fil des
  sessions suivantes.

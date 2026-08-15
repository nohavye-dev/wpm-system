# Workflows — `learn`, `map`, `bootstrap`, `audit`, `patterns`

Cinq workflows prêts à l'emploi pour alimenter ou inspecter la mémoire du
projet. Dans OpenCode, ce sont des commandes slash (ex. `/wpm:learn:mcp`) ;
ils ne s'exécutent que sur invocation explicite.

## Deux façons de mémoriser, à ne pas confondre

- **Mémorisation incrémentale (automatique)** — pendant son travail, l'agent
  note tout fait durable dès qu'il le rencontre. C'est le comportement par
  défaut, décrit dans [`agent-behavior.md`](agent-behavior.md). Les
  workflows ne le remplacent pas.
- **Ingestion contrôlée (manuelle)** — `learn`, `map` et `bootstrap`
  servent à apporter **en masse** des documents, une cartographie du code,
  ou un peuplement initial. Pas pour les faits ponctuels d'une tâche.

## Garde commune

- Si `wpm.config.json` n'existe pas, la mémoire n'est pas activée : lancez
  `wpm enable` à la racine du projet puis redémarrez OpenCode.
- Si aucun chemin n'est fourni à `learn` ou `map`, le prompt affiche
  uniquement son usage et ne devine rien.

---

## `learn <chemins>`

Ingère un ou plusieurs documents markdown, section par section.

- Chaque section (`##`/`###`) devient une entrée candidate.
- **Déduplication** : avant d'écrire, le workflow vérifie si le fait existe
  déjà ; si oui, il revalide au lieu de créer un doublon.
- Contenu **traduit en anglais**, reformulé de façon concise.
- Type inféré (`doc`, `archi_decision`, `convention`, `bug_pattern`),
  source `official_doc`.
- Rendu d'un **résumé** : par fichier, sections stockées / dédupliquées /
  ignorées.

## `map [scopes]`

Cartographie l'architecture et les conventions de la base de code.

- **Pas un index fichier par fichier** : seuls quelques faits structurants,
  toujours ancrés dans du code réellement lu.
- Types : `archi_decision`, `convention`, `bug_pattern` ; source
  `observed_code`.
- Même déduplication que `learn`, avec un résumé final (stocké / revalidé /
  écarté faute de confiance).

## `bootstrap`

Peuple la mémoire à partir des artefacts existants (README, docs, configs de
lint, CI/CD, structure de dossiers) — en une seule passe. À lancer une fois
par projet, après `wpm enable`, puis la mémorisation incrémentale prend le
relais.

## `audit`

Tableau de bord **en lecture seule** de la santé de la mémoire : total par
type, distribution de confiance, entrées jamais validées, contradictions
actives, 5 entrées les plus faibles, activité récente. Se termine par un
verdict (« Memory is healthy » / « N issues need attention ») et peut
suggérer des actions (`pin_entry`, `deprecate_entry`, `restore_entry`)
sans les exécuter.

## `patterns [type]`

Analyse la mémoire pour détecter des patterns récurrents et propose des
améliorations : convention manquante, décision implicite, contradiction à
résoudre. Les actions proposées sont **exécutées automatiquement** (par
exemple : 4+ `bug_pattern` de même cause → créer une `convention` ; une
convention validée 3+ fois → `pin_entry`). Si rien n'émerge, le résultat
négatif est signalé.

---

> Après une ingestion, lisez le résumé : des faits « écartés » indiquent un
> tri volontaire (trop vague, trop incertain), pas un échec. Vous pouvez
> ensuite renforcer les entrées au fil des sessions (`validate_entry`,
> `contradict_entry`).

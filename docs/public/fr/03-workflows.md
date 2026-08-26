# Workflows — `wpm-learn`, `wpm-map`, `wpm-bootstrap`, `wpm-audit`, `wpm-patterns`, `wpm-persist`

Six workflows prêts à l'emploi pour alimenter, inspecter ou persister la
mémoire du projet. Dans OpenCode, ce sont des commandes slash (ex.
`/wpm-learn`) ; ils ne s'exécutent que sur invocation explicite.

## Deux façons de mémoriser, à ne pas confondre

- **Mémorisation incrémentale (automatique)** — pendant son travail, l'agent
  note tout fait durable dès qu'il le rencontre. C'est le comportement par
  défaut, décrit dans [`04-agent-behavior.md`](https://nohavye-dev.github.io/wpm-site/fr/docs/agent-behavior). Les
  workflows ne le remplacent pas.
- **Ingestion contrôlée (manuelle)** — `wpm-learn`, `wpm-map` et `wpm-bootstrap`
  servent à apporter **en masse** des documents, une cartographie du code,
  ou un peuplement initial. Pas pour les faits ponctuels d'une tâche.

## Garde commune

- Si `wpm.config.json` n'existe pas, la mémoire n'est pas activée : lancez
  `wpm enable` à la racine du projet puis redémarrez OpenCode.
- Si aucun chemin n'est fourni à `wpm-learn` ou `wpm-map`, la commande
  affiche uniquement son usage et ne devine rien.

---

## `wpm-learn <chemins>`

Ingère un ou plusieurs documents markdown, section par section.

- Chaque section (`##`/`###`) devient une entrée candidate.
- **Déduplication** : avant d'écrire, le workflow vérifie si le fait existe
  déjà ; si oui, il revalide au lieu de créer un doublon.
- Contenu **conservé dans sa langue native**, reformulé de façon concise
  (termes techniques et code tels quels).
- Type inféré (`doc`, `archi_decision`, `convention`, `bug_pattern`),
  source `official_doc`.
- Rendu d'un **résumé** : par fichier, sections stockées / dédupliquées /
  ignorées.

## `wpm-map [scopes]`

Cartographie l'architecture et les conventions de la base de code.

- **Pas un index fichier par fichier** : seuls quelques faits structurants,
  toujours ancrés dans du code réellement lu.
- Types : `archi_decision`, `convention`, `bug_pattern` ; source
  `observed_code`.
- Même déduplication que `wpm-learn`, avec un résumé final (stocké / revalidé /
  écarté faute de confiance).

## `wpm-bootstrap`

Peuple la mémoire à partir des artefacts existants (README, docs, configs de
lint, CI/CD, structure de dossiers) — en une seule passe. À lancer une fois
par projet, après `wpm enable`, puis la mémorisation incrémentale prend le
relais.

## `wpm-audit`

Tableau de bord **en lecture seule** de la santé de la mémoire : total par
type, distribution de confiance, entrées jamais validées, contradictions
actives, 5 entrées les plus faibles, activité récente. Se termine par un
verdict (« Memory is healthy » / « N issues need attention ») et peut
suggérer des actions (`pin_entry`, `deprecate_entry`, `restore_entry`)
sans les exécuter.

## `wpm-patterns [type]`

Analyse la mémoire pour détecter des patterns récurrents et propose des
améliorations : convention manquante, décision implicite, contradiction à
résoudre. Les actions proposées sont **exécutées automatiquement** :
- 4+ `bug_pattern` de même cause → créer une `convention` ;
- une `convention` validée 3+ fois → `pin_entry` ;
- une contradiction ancienne → `deprecate_entry` sur l'entrée la plus faible ;
- 3+ `insight` confirmant la même décision d'architecture → créer un
  `archi_decision` + `pin_entry`.
Si rien n'émerge, le résultat négatif est signalé.

## `wpm-persist`

Passe de persistance silencieuse, injectée automatiquement entre les tours
quand la session devient inactive — la session continue normalement après.
Invoquable explicitement (`/wpm-persist`) pour écrire tout fait durable
resté non persisté — décisions, résultats confirmés, bug patterns compris.
Si quelque chose a été persisté : une seule ligne courte le résumant. Sinon :
aucun message — pas d'acquittement, pas de justification.

---

> Après une ingestion, lisez le résumé : des faits « écartés » indiquent un
> tri volontaire (trop vague, trop incertain), pas un échec. Vous pouvez
> ensuite renforcer les entrées au fil des sessions (`validate_entry`,
> `contradict_entry`).

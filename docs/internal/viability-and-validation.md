# Analyse de viabilité et plan de validation

Document de réflexion sur l'avenir du projet WPM, la viabilité de son
architecture, et la façon de valider son modèle de confiance.

> **Note historique** — ce document a été écrit avant le pivot. Depuis, le
> projet a tranché : **OpenCode comme host unique**, plugin installé par
> défaut qui enregistre le serveur MCP et les permissions (plus de
> déclaration manuelle). Les paragraphes sur la « portabilité » et le
> « découplage du plugin » décrivent donc une piste qui n'a **pas** été
> retenue ; le reste (validation de l'heuristique, fragilité des hooks
> `experimental.*`) reste d'actualité.

---

## 1. Évaluation du projet

Verdict d'ensemble : projet **raisonnable et bien conçu**, mais son avenir
dépend de facteurs hors de notre contrôle.

### Ce qui est solide

- **Il résout un vrai problème.** Le contexte d'un agent IA est éphémère —
  les décisions d'architecture, conventions et patterns découverts dans une
  session sont perdus à la suivante. Une mémoire persistante a une vraie
  valeur.
- **L'ingénierie est propre.** Serveur source de vérité, plugin thin client,
  séparation nette, tests, docs. Pas du code jetable.
- **Le modèle de confiance est le vrai différenciateur.** Decay temporel,
  asymétrie contradiction/confirmation, preuves externes au lieu de
  raisonnement, jamais de suppression. C'est plus réfléchi que 95% des
  systèmes « mémoire » qui se contentent de stocker des embeddings.

### Ce qui est fragile

- **Dépendance à OpenCode.** Les hooks sont `experimental.*` — ils peuvent
  casser silencieusement à chaque version. Toute l'intégration automatique
  (compaction, auto-capture, nudge) repose dessus. C'est le plus gros risque.
- **Heuristique non validée.** Le modèle de decay (λ par type, seuils
  0.82/0.92, poids 0.5/0.35/0.15) est élégant sur le papier mais aucune
  valeur n'a été calibrée sur des données réelles. On a même vu en test que
  les seuils de similarité produisent des résultats imprévisibles (entrées
  en `related_context` au lieu de `direct_matches`).
- **Concurrence.** OpenCode a déjà AGENTS.md et ses règles. Il existe des
  solutions mémoire génériques (mem0, ChromaDB+RAG, MCP memory servers).
  La niche est étroite : la mémoire avec un modèle de confiance pondéré
  pour OpenCode spécifiquement.

### Ce qui déciderait de son avenir

1. **Prouver la valeur empiriquement.** Est-ce qu'un agent avec WPM produit
   réellement de meilleures décisions sur un projet de plusieurs semaines ?
   Aujourd'hui c'est une intuition, pas une démonstration.
2. **Stabilité de l'API plugin.** Si OpenCode fige ses hooks, le projet est
   pérenne. Sinon, on passe le temps à réparer.
3. **Portabilité.** Si le cœur (le serveur MCP + le modèle de confiance)
   était découplé d'OpenCode, il deviendrait utile pour n'importe quel
   agent. Aujourd'hui c'est un bundle OpenCode.

### Verdict

Bonne idée, bonne exécution, rigueur démontrée (tests de bout en bout,
gestion des cas limites, docs). Mais c'est un pari à horizon incertain : la
pérennité dépend plus de l'écosystème OpenCode et d'une validation réelle
du modèle de confiance que du code lui-même.

Le plus rentable pour l'avenir : **mesurer l'impact réel** (avec et sans WPM,
sur un vrai projet long) et **découpler le cœur du plugin OpenCode** pour ne
pas dépendre d'une seule plateforme.

---

## 2. Le plugin est-il viable sans les hooks ?

**Oui — et il serait même plus robuste.** Il faut séparer deux choses :

### Ce qui est le produit (indépendant des hooks)

Les **11 outils MCP** (`store_entry`, `query_context`, etc.). Ils ne
dépendent *pas* du plugin : ce sont des fonctions du serveur Python,
exposables par une simple entrée `mcp` dans `opencode.json` — la voie
standard que le projet a justement évitée en lançant le serveur lui-même
via le plugin.

Sans plugin, on perd :

| Hook | Rôle | Perte critique ? |
|------|------|------------------|
| `system.transform` | injecter les règles + project-rules | Non — remplaçable par AGENTS.md / instructions |
| `session.compacting` | préserver le contexte avant compaction | **Oui** — le filet de sécurité le plus important |
| `tool.execute.after` | auto-capture des tests/builds | Non — l'agent peut valider manuellement |
| `session.idle` | relance de fin de session | Non — déjà opt-in |

Le seul vrai argument pour les hooks est le **déterminisme** : l'injection
des règles et la sécurité à la compaction sont garanties, pas laissées au
bon vouloir du LLM. Mais on a vu en test que le LLM suit les règles assez
fidèlement (la règle d'or « write as you go » + la passe finale couvrent
l'essentiel).

### Verdict

Le projet serait **plus viable sans les hooks** : un serveur MCP standard
(`mcp` dans `opencode.json`) + des règles dans AGENTS.md, et on perd la
fragilité `experimental.*`. On garde 100% de la valeur produit (les outils
+ le modèle de confiance). Le coût : remplacer la sécurité déterministe
par de la discipline LLM — un compromis acceptable.

**La meilleure architecture serait un hybride :** serveur MCP standard comme
socle stable, et le plugin OpenCode (hooks) comme *optimisation optionnelle*
par-dessus, pas comme dépendance critique. Aujourd'hui c'est l'inverse :
tout repose sur le plugin fragile.

---

## 3. Comment valider l'heuristique ?

C'est le vrai trou du projet. Toutes les constantes (λ de decay, provenance,
poids de preuve, poids de retrieval, seuils 0.82/0.92) sont des valeurs
**non calibrées**. Voici comment les valider, du plus simple au plus complet.

### Niveau 1 — Calibration du modèle de confiance (le plus important)

**Principe :** la confiance doit être *prédictive de la vérité*. Une entrée
à 0.9 doit réellement être vraie ~90% du temps ; une à 0.3, ~30%.

**Comment :** logger chaque `query_context` + l'issue réelle (l'entrée
s'est-elle révélée correcte ?). Les signaux d'issue existent déjà dans le
système : les `validate_entry` et `contradict_entry` postérieurs sont des
vérités terrain. On peut mesurer :

- pour chaque entrée, sa confiance au moment où elle a été *contredite* ou
  *validée* ;
- si les entrées contredites avaient en moyenne une confiance basse et les
  validées une confiance haute, le modèle est bien calibré.

**Concrètement :** un outil d'analyse (ou un script) qui relit
`entry_events` et calcule la courbe de calibration :
`P(contredite | confiance=x)` en fonction de x. C'est un diagramme de
fiabilité classique.

### Niveau 2 — Calibration du decay

**Question :** λ=0.015 pour `bug_pattern` signifie-t-il que les bugs
deviennent effectivement obsolètes 7× plus vite que les décisions d'archi ?
Il faut le mesurer : combien de temps s'écoule en moyenne entre la création
d'un `bug_pattern` et sa contradiction/dépréciation ? Ajuster λ pour que la
confiance décroisse à ce rythme.

### Niveau 3 — Benchmark de retrieval

Créer un jeu de test avec **vérité terrain** : N faits « corrects » + M
faits « faux » injectés, et mesurer si `query_context` remonte les bons en
premier (précision@k, rappel). Ajuster les poids `weight_similarity` /
`weight_confidence` / `weight_centrality` pour maximiser.

### Niveau 4 — A/B sur un vrai projet

Le test ultime : sur un projet long, comparer les décisions de l'agent
**avec** vs **sans** WPM (ou avec des seuils différents). Coûteux mais c'est
la seule preuve de valeur réelle.

### Artefacts requis

Pour les niveaux 1-3, il faudrait 2 artefacts que le projet n'a pas :

1. **Un logger de métriques** — enregistrer chaque appel `query_context`
   (entrées retournées + confiance) et chaque issue (`validate_entry` /
   `contradict_entry` postérieur), pour reconstruire la calibration
   a posteriori.
2. **Un harness d'évaluation** — un script qui, à partir de `entry_events`
   + `entry_links`, produit le diagramme de fiabilité et les métriques de
   calibration.

Ces deux artefacts sont la réponse honnête : **on ne peut pas valider
l'heuristique sans la mesurer**, et le projet n'a pas encore
l'infrastructure de mesure.

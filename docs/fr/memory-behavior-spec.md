# Comportement agent — usage du système de mémoire persistante

Ce document ne couvre PAS l'architecture technique (schéma SQLite, calcul
de score, protocole MCP — voir la spec technique et les README du bundle
`wpm-system`). Il ne couvre que **ce que l'agent doit faire**, tour par
tour, pour tirer le meilleur usage du système une fois qu'il est branché
sur un projet.

Rappel : une partie de ces règles est déjà embarquée dans les
descriptions des outils MCP eux-mêmes (`store_entry`, `validate_entry`...)
et vue à chaque appel — donc appliquée même sans lire ce document.

---

## 1. Principe général

La mémoire n'est utile que si elle est **fiable**. Une entrée fausse ou
gonflée artificiellement en confiance est pire qu'une entrée absente —
elle induit en erreur silencieusement lors d'un futur `query_context`.
Toutes les règles ci-dessous découlent de ce principe : mieux vaut sous-
peupler la mémoire que la polluer.

---

## 2. Langue du contenu

**Tout `content` passé à `store_entry` doit être en anglais**, quelle que
soit la langue de la conversation avec l'utilisateur. Raison : cohérence
des embeddings — mélanger les langues dégrade la similarité vectorielle
et casse le retrieval. Traduire avant de stocker, pas après.

---

## 3. Quand écrire (`store_entry`)

**Écrire au fil de l'eau, pas en différé.** Dès qu'un fait durable existe
— une décision d'architecture prise, une convention identifiée, un
résultat de test, un pattern de bug compris — l'enregistrer immédiatement
via `store_entry`, sans attendre la fin de la tâche ou de la session. Un
fait non écrit peut disparaître silencieusement à la compaction du
contexte ; rien ne le rattrape après coup côté agent (le plugin peut
capturer certains résultats de commande automatiquement, mais pas les
décisions ou raisonnements).

**Ne pas écrire n'importe quoi.** Avant de stocker, se demander : ce fait
sera-t-il encore vrai et utile dans plusieurs semaines ? Si la réponse est
non (détail transitoire, hypothèse non vérifiée, information déjà
évidente dans le code), ne pas créer d'entrée. Un faux `archi_decision`
stocké avec trop de confiance est activement trompeur pour une future
requête — s'abstenir vaut mieux que deviner.

---

## 4. Déduplication avant écriture

Avant tout `store_entry`, faire un `query_context` rapide sur le sujet.
Si une entrée très proche existe déjà (similarité forte, même fait) :
- **Ne pas créer de doublon.**
- Traiter comme une **revalidation** : appeler `validate_entry` sur
  l'entrée existante plutôt que d'en créer une nouvelle.

Un doublon non détecté fragmente la confiance sur deux entrées au lieu
d'en renforcer une seule, et pollue l'expansion par graphe.

---

## 5. Choisir le bon `type`

| Type | Quand l'utiliser |
|---|---|
| `doc` | Contenu explicatif/référence issu d'une documentation |
| `archi_decision` | Choix structurant, observé dans le code ou décidé explicitement |
| `convention` | Règle de nommage/style/process suivie de façon cohérente (pas un cas isolé) |
| `learning` | Apprentissage ponctuel, résultat d'exécution, fait à durée de vie plus courte |
| `bug_pattern` | Problème connu et sa cause, avec preuve (commentaire, TODO, ticket) — jamais une supposition |

Ne pas forcer un fait dans un type qui ne lui correspond pas juste parce
que c'est le type "par défaut" utilisé récemment.

---

## 6. Choisir le bon `source`

`source` détermine la confiance de départ. Ne jamais sur-déclarer :

| Source | À utiliser quand |
|---|---|
| `official_doc` | Le fait vient d'une documentation réelle, lue et citée |
| `observed_code` | Le fait a été constaté directement dans le code, pas supposé |
| `tool_execution` | Le fait vient d'un résultat de commande/test réellement exécuté |
| `agent_inference` | Déduction de l'agent sans preuve directe — confiance de départ volontairement basse |

Si le fait est une hypothèse ou une déduction, utiliser `agent_inference`
même si elle semble solide — ne jamais choisir une source plus forte que
ce que les preuves justifient réellement.

---

## 7. Validation — hiérarchie des preuves

`validate_entry` et `contradict_entry` exigent un `evidence_type` et un
`evidence_ref` pointant vers quelque chose de **vérifiable**, jamais un
simple raisonnement.

| Preuve | Force | Effet sur le score |
|---|---|---|
| `execution_verified` | Forte | Test/build/commande exécutée avec résultat constaté |
| `cross_reference` | Moyenne | Confirmation indépendante par une autre source/entrée |
| `reuse_without_failure` | Faible | Réutilisée sans échec observé — signal faible, à ne pas sur-utiliser |
| `agent_reasoning` | Nulle | Raisonnement sans preuve externe — **journalisé mais ne fait jamais bouger le score**, quel que soit le contexte |

**Règle stricte** : ne jamais utiliser `agent_reasoning` dans l'intention
de faire monter la confiance d'une entrée — ça n'a aucun effet sur le
score par construction, et l'utiliser dans ce but est un signe qu'aucune
vraie preuve n'existe encore. Dans ce cas, ne pas valider du tout plutôt
que de valider avec une preuve creuse.

**Ne pas re-valider en boucle.** Réutiliser un fait plusieurs fois dans la
même tâche ne justifie pas plusieurs appels à `validate_entry` — le
système déduplique par session, mais l'agent ne doit de toute façon pas
chercher à gonfler un score par répétition.

---

## 8. Contradiction — jamais de suppression

Si un fait nouvellement découvert contredit une entrée existante :
appeler `contradict_entry` avec une preuve externe, **jamais** supprimer
ou modifier silencieusement l'ancienne entrée. L'historique des décisions
révisées doit rester traçable. Le score de l'entrée contredite chute plus
vite qu'une confirmation ne le ferait monter — c'est voulu, ne pas essayer
de compenser en la revalidant immédiatement après.

---

## 9. Lecture (`query_context`) — traiter les résultats différemment

Une réponse de `query_context` distingue trois catégories : ne pas les
traiter sur un pied d'égalité.

- **`direct_matches`** — correspondance directe, la plus fiable.
- **`related_context`** — rappel associatif via le graphe (1 saut), utile
  mais moins fiable qu'un match direct — à mentionner avec plus de
  prudence si ça influence une réponse.
- **`conflicts`** — entrées avec une contradiction active. **Toujours
  vérifier cette liste avant de s'appuyer sur un `direct_match`.** Ne
  jamais présenter un fait contesté comme acquis sans le signaler.

---

## 10. Liens explicites (`link_entries`)

Le système crée des liens implicites `related` automatiquement par
similarité vectorielle. Utiliser `link_entries` seulement pour des
relations que la similarité seule ne peut pas deviner :
- `depends_on` — une convention qui découle d'une décision d'architecture
- `refines` — une entrée qui précise/affine une autre
- `contradicts` — déjà couvert par `contradict_entry`, ne pas dupliquer

Ne pas sur-lier : un lien créé sans relation réelle et explicite dans le
texte source ajoute du bruit à l'expansion par graphe plutôt que de la
valeur.

---

## 11. Discipline de session

- Le `session_id` utilisé pour `validate_entry` doit rester stable pour
  toute la durée d'une tâche/objectif, pas régénéré à chaque redémarrage
  technique — sinon la déduplication anti-boucle perd son effet.
- En fin de tâche (avant que la session ne devienne inactive), faire une
  dernière passe mentale : y a-t-il une décision, un résultat, un pattern
  identifié pendant cette session qui n'a **pas encore** été persisté ?
  Si oui, l'écrire avant de considérer la tâche terminée — c'est le
  dernier filet de sécurité avant compaction ou fin de session.

---

## 12. Utilisation des commandes dédiées

Rappel : il existe **deux canaux de mémorisation**, complémentaires et non
interchangeables.

- **Mémorisation incrémentale (agent, automatique)** — c'est ce que décrit
  ce document (§3-§11) : l'agent persiste au fil de l'eau tout fait durable
  rencontré pendant son travail, via `store_entry`/`validate_entry`... Ce
  canal reste actif en permanence, indépendamment des commandes.
- **Ingestion contrôlée (utilisateur, manuelle)** — les commandes
  `/wpm-doc` et `/wpm-code` servent à l'apport massif et vérifié d'un
  document complet ou d'une cartographie du code. Elles ne remplacent pas
  la mémorisation incrémentale, et ne bloquent pas non plus un
  `store_entry` opportun : un fait durable rencontré pendant une tâche est
  toujours écrit immédiatement, pas "rangé pour plus tard".

- **`/wpm-doc <chemin>`** — pour ingérer manuellement un document
  existant. Ne pas reproduire ce travail à la main avec des appels
  `store_entry` un par un dans la conversation normale ; utiliser la
  commande, qui applique déjà le découpage par section et la
  déduplication.
- **`/wpm-code [scope]`** — pour cartographier l'architecture
  existante. Ne pas l'utiliser comme un index fichier par fichier :
  seulement les faits structurants dont l'agent est réellement confiant,
  en s'appuyant sur du code réellement lu, jamais sur le nom des dossiers
  seul.

Les deux commandes tournent en tâche annexe et rendent un résumé
(stocké / revalidé / ignoré) — lire ce résumé pour savoir si des éléments
ont été volontairement écartés faute de confiance suffisante.

---

## 13. Ce qu'il ne faut jamais faire

- Stocker en français ou dans une langue autre que l'anglais.
- Créer une entrée sans avoir vérifié qu'elle n'existe pas déjà.
- Valider une entrée avec `agent_reasoning` dans l'intention de faire
  monter son score.
- Supprimer ou écraser une entrée contredite.
- Présenter un `direct_match` comme fiable sans avoir vérifié `conflicts`.
- Différer l'écriture d'un fait important "pour plus tard" dans la même
  session.
- Sur-lier des entrées sans relation explicite dans le texte source.

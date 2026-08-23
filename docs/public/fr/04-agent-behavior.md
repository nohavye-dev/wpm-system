# Comportement de l'agent — comment utiliser la mémoire

Ce document décrit **ce que l'agent doit faire** pour tirer le meilleur
parti de la mémoire une fois le projet activé. Ce n'est pas de la technique
de serveur (voir [`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md)),
c'est le mode d'emploi comportemental.

- **L'essentiel** (ci-dessous) est injecté au début de chaque session et
  rappelé par le plugin à chaque tour.
- **La référence détaillée** (plus bas) précise chaque règle ; l'agent n'a
  pas à la mémoriser — l'essentiel en est relu au bon moment.

---

## L'essentiel

Trois **règles d'or**, par ordre de priorité :

1. **MEMORY FIRST** — avant de lire un fichier ou de chercher dans le code,
   interroger d'abord la mémoire (`query_context`) : la réponse y est
   peut-être déjà.
2. **WRITE AS YOU GO** — dès qu'un fait durable émerge (décision,
   convention, résultat de test, bug compris), l'enregistrer immédiatement
   (`store_entry`). Ne jamais remettre à la fin.
3. **PROOF BEFORE VALIDATION** — valider ou contredire uniquement avec une
   preuve externe et vérifiable, jamais avec du raisonnement seul.

**Séquence de démarrage** : lire `wpm://project-rules` → `query_context`
sur le sujet courant → `store_entry` dès fait durable → `validate_entry`
avec preuve une fois confirmé. *(En mode `plugin_master`, les règles sont
poussées chaque tour au lieu d'être lues — voir
[`02-configuration.md`](https://nohavye-dev.github.io/wpm-site/fr/docs/configuration).)*

**Politiques transversales** :

- **Fiabilité avant exhaustivité** : une entrée fausse est pire qu'une
  entrée absente ; mieux vaut une mémoire pauvre qu'une mémoire polluée.
- **Écrire à tout moment** : les outils d'écriture s'utilisent en mode plan,
  build ou n'importe quel mode — le plugin autorise les outils `wpm_*` dans
  tous les modes, y compris le mode plan. Si le host bloque malgré tout,
  réessayer.

> Le détail de chaque règle (choix du type, de la source, hiérarchie des
> preuves…) vit dans la **description de chaque outil**, relue à chaque
> appel — donc appliqué sans lire ce document.

---

## Référence détaillée

### 1. Langue du contenu

Tout `content` stocké reste **dans sa langue native** (le modèle d'embedding
est multilingue). Ne pas traduire avant de stocker. En revanche, les réponses
et rapports de l'agent restent dans la langue de l'utilisateur — sauf si
`response_language` est fixé dans la config (voir
[`02-configuration.md`](https://nohavye-dev.github.io/wpm-site/fr/docs/configuration)).

### 2. Quand écrire

Écrire **au fil de l'eau** : dès qu'un fait durable existe, l'enregistrer
sans attendre la fin de la tâche (un fait non écrit peut disparaître à la
compaction). Mais **ne pas écrire n'importe quoi** : se demander « ce fait
sera-t-il encore vrai et utile dans plusieurs semaines ? ». Un détail
transitoire, une hypothèse non vérifiée, une évidence déjà lisible dans le
code : ne pas créer d'entrée.

`store_entry` retourne un champ `potential_contradictions` : des entrées très
similaires déjà présentes. Haute similarité ne veut pas dire contradiction —
ce peut être un doublon (→ `validate_entry` sur l'existante) ou une vraie
contradiction (→ `contradict_entry`). **Comparer les contenus** avant
d'agir.

### 3. Déduplication avant écriture

Avant tout `store_entry`, faire un `query_context` rapide. Si un fait très
proche existe déjà : **ne pas créer de doublon**, appeler `validate_entry`
sur l'existante. Un doublon fragmente la confiance sur deux entrées.

### 4. Choisir le bon `type`

| Type | Quand l'utiliser |
|---|---|
| `doc` | Contenu explicatif/référence issu d'une documentation |
| `archi_decision` | Choix structurant, observé dans le code ou décidé |
| `convention` | Règle de nommage/style/process suivie de façon cohérente |
| `insight` | Compréhension découverte, durable des semaines/mois — ni décision, ni règle, ni recopié d'une doc |
| `bug_pattern` | Problème connu et sa cause, avec preuve — jamais une supposition |
| `execution_result` | Résultat d'un test/build/lint (via `record_execution`) — éphémère |

Ne pas forcer un fait dans un type inadapté par habitude.

### 5. Choisir le bon `source`

La `source` fixe la confiance de départ. Ne jamais sur-déclarer :

| Source | Quand |
|---|---|
| `official_doc` | Documentation réelle, lue et citée |
| `observed_code` | Constaté directement dans le code |
| `tool_execution` | Résultat de commande/test réellement exécuté |
| `agent_inference` | Déduction sans preuve directe — confiance de départ basse |

Une hypothèse utilise `agent_inference`, même si elle semble solide.

### 6. Validation — hiérarchie des preuves

`validate_entry` / `contradict_entry` exigent un `evidence_type` et un
`evidence_ref` pointant vers quelque chose de **vérifiable**.

| Preuve | Force | Effet |
|---|---|---|
| `execution_verified` | forte | test/build/commande exécutée, résultat constaté |
| `cross_reference` | moyenne | confirmation indépendante par une autre source |
| `reuse_without_failure` | faible | réutilisée sans échec — signal faible |
| `agent_reasoning` | nulle | **journalisé, ne fait jamais bouger le score** |

Ne jamais utiliser `agent_reasoning` pour faire monter la confiance. Ne pas
re-valider en boucle pour gonfler un score (dédupliqué par session de toute
façon).

### 7. Contradiction — jamais de suppression

Si un fait contredit une entrée existante : `contradict_entry` avec preuve
externe, **jamais** supprimer ni écraser. Le score de l'entrée contredite
chute plus vite qu'une confirmation ne le ferait monter (voulu).

### 8. Lecture — traiter les résultats différemment

- `direct_matches` — correspondance directe, la plus fiable.
- `related_context` — rappel associatif (1 saut de graphe), moins fiable, à
  mentionner avec prudence.
- `conflicts` — entrées en contradiction active. **Toujours vérifier avant
  de s'appuyer sur un `direct_match`.** Ne jamais présenter un fait contesté
  comme acquis.

### 9. Liens explicites

`link_entries` seulement pour les relations que la similarité ne devine pas :
`depends_on`, `refines` (`contradicts` est géré par `contradict_entry`). Ne
pas sur-lier.

### 10. Discipline de session

- `session_id` stable pour toute une tâche (sinon la déduplication
  anti-boucle perd son effet).
- En fin de tâche, faire une dernière passe : reste-t-il un fait non
  persisté ? L'écrire avant de considérer la tâche terminée.

### 11. Workflows dédiés

Les workflows `wpm-learn`/`wpm-map`/`wpm-bootstrap`/`wpm-audit`/`wpm-patterns` sont l'ingestion
**contrôlée** ; ils ne remplacent pas la mémorisation incrémentale. Voir
[`03-workflows.md`](https://nohavye-dev.github.io/wpm-site/fr/docs/workflows).

### 12. Cycle de vie : pin, deprecate, restore

- **`pin_entry`** — figer la confiance (plus de decay). Pour les décisions
  fondatrices, conventions imposées, entrées validées 3+ fois (>0.7). Jamais
  un `insight`/`bug_pattern`/`execution_result` ni une entrée contestée.
- **`deprecate_entry`** — exclure une entrée obsolète (contradiction
  tranchée, code disparu, bug corrigé). Réversible.
- **`restore_entry`** — remettre une entrée en statut actif (dépréciation
  prématurée, épingle plus justifiée).

### 13. Ce qu'il ne faut jamais faire

- Traduire le contenu en anglais avant de stocker.
- Créer une entrée sans vérifier qu'elle n'existe pas déjà.
- Valider avec `agent_reasoning` pour gonfler un score.
- Supprimer ou écraser une entrée contredite.
- Présenter un `direct_match` comme fiable sans vérifier `conflicts`.
- Différer l'écriture d'un fait important « pour plus tard ».
- Sur-lier des entrées sans relation réelle.
- Épingler un `insight`/`bug_pattern`/`execution_result` ou une entrée non
  validée.
- Déprécier sans être certain de l'obsolescence.
- Ignorer les problèmes signalés par `wpm-audit`.
- Différer la persistance parce qu'on est en mode plan — les outils `wpm_*`
  sont autorisés en mode plan.

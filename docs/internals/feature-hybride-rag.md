# Injection hybride de mémoire (RAG) : pop-in + tool de recherche

## Contexte

Le système actuel expose la recherche de mémoire via un tool explicite : le LLM déclenche une requête, reçoit les x résultats les plus proches, et les analyse lui-même. Ce fonctionnement dépend entièrement du jugement du LLM pour décider *quand* chercher — avec le risque qu'il n'appelle pas l'outil alors qu'une mémoire pertinente existe.

Cette fiche propose un mode d'injection directe en complément du tool existant, formant une architecture hybride.

## Deux approches, deux tradeoffs

### Injection directe (pop-in)

Un hook déterministe (`experimental.chat.system.transform`, déjà utilisé côté plugin pour les golden rules) effectue la recherche vectorielle en arrière-plan et splice automatiquement les meilleurs résultats dans le contexte, sans intervention du LLM.

**Avantages :**
- Pas de dépendance au jugement du LLM pour déclencher la recherche
- Pas d'aller-retour supplémentaire (latence, tokens de schéma d'outil)
- Garantit qu'une mémoire à haute confiance est toujours présente en contexte

**Limites :**
- La requête de recherche est le message brut de l'utilisateur, jamais reformulée — moins précis qu'une requête pensée par le LLM
- Aucune itération possible si les résultats sont mauvais
- Risque de pollution de contexte si le seuil de pertinence est mal calibré
- Perte de traçabilité : plus difficile d'auditer pourquoi une mémoire a été injectée

### Tool de recherche actif

Le LLM reste libre d'appeler un outil de recherche sémantique, avec sa propre reformulation de requête et la possibilité d'itérer.

**Avantages :**
- Requête reformulée par le LLM, généralement plus précise que le texte brut
- Itération possible (relancer avec une autre requête si les résultats sont mauvais)
- Traçabilité claire de l'usage de la mémoire

**Limites :**
- Dépend du LLM pour décider de chercher — risque d'omission
- Coût de latence et de tokens à chaque appel

## Mode proposé : hybride à seuil de similarité

Combiner les deux mécanismes plutôt que choisir l'un ou l'autre, en calant le déclenchement du pop-in sur les métriques déjà retournées par `query_context` (`storage/retrieval.py`). Trois scores coexistent, et un seul porte la pertinence :

| Métrique | Nature | Rôle dans le pop-in |
|---|---|---|
| `similarity` | Cosinus requête ↔ entrée, dépendante de la requête | **Porte le seuil haut** |
| `confidence` | Provenance + validation − decay temporel, indépendante de la requête | Condition secondaire (garde-fou qualité) |
| `score` composite | `0.5·similarity + 0.35·confidence + 0.15·centralité` | Écarté comme critère de pop-in : partiellement aveugle au sujet (confiance et centralité ne varient pas selon la requête) |

Un seuil posé sur le score composite ou sur la confiance seule injecterait les mêmes entrées quel que soit le sujet de la question — c'est donc la similarité qui décide.

| Condition | Comportement |
|---|---|
| `similarity ≥ seuil_haut` **ET** `confidence ≥ seuil_confiance` | Injection directe et silencieuse via hook déterministe. Peu de résultats (haute précision, pas de bruit). |
| Sinon | Pas d'injection automatique. Le tool de recherche reste disponible pour que le LLM creuse avec une requête reformulée. |

### Principe de fonctionnement

1. Point d'injection : **`experimental.chat.system.transform`** — le seul hook qui splice réellement du contenu en contexte avant l'appel LLM (déjà utilisé pour les golden rules dans `wpm-lib/server/hooks.ts`). Contrainte documentée : ce hook ne reçoit pas le texte utilisateur (seulement sessionID/model) ; le plugin récupère le dernier message utilisateur via le SDK (`client.session.messages`) à partir du sessionID.
2. Sur ce texte brut, une recherche vectorielle est effectuée en arrière-plan via le **serveur chaud** (tool `query_context` appelé par le client MCP du plugin — voir `architecture-plugin-hote-mcp.md`) : `similarity`, `confidence` et `score` sont déjà retournés par entrée.
3. Si le(s) résultat(s) satisfai(en)t la condition du tableau ci-dessus : splice direct dans `output.system`, sans passer par un tool call.
4. Sinon : rien n'est injecté automatiquement, mais le tool de recherche sémantique reste disponible pour un appel explicite du LLM si besoin.

Contrainte de latence : ce hook s'exécute sur le chemin critique de chaque tour. Avec un serveur chaud, le coût se réduit à un aller-retour `tools/call` sur la connexion stdio du plugin (embedding déjà chargé en RAM) — plus de cold start ni de rechargement ONNX par tour.

## Extension : pop-in des règles projet (cas dégénéré du même mécanisme)

La lecture des règles de projet souffre aujourd'hui du même défaut que la recherche : c'est un **pull dépendant du LLM**. Le nudge injecte l'instruction *« At session start, read the `wpm://project-rules` resource »* (`wpm-lib/prompts/nudges.ts`), et la « Startup sequence » des golden rules la répète (`wpm_mcp_server/prompts/memory_rules.py`). Si le modèle ne lit pas la resource, les règles ne sont jamais en contexte.

Les règles sont le cas dégénéré du pop-in : leur contenu est **déterministe** (`PROJECT_RULES_QUERY` fixe, filtre par `confidence_threshold`, budget 800 tokens, cache jusqu'à la prochaine mutation). Il n'y a ni message utilisateur à extraire ni seuil de similarité à calibrer.

| Caractéristique | Règles projet | Pop-in RAG |
|---|---|---|
| Déclencheur | Mutation mémoire (sinon cache) | Chaque tour (requête changeante) |
| Requête | Fixe (`PROJECT_RULES_QUERY`) | Dérivée du message utilisateur |
| Filtre | `confidence_threshold` + budget | Seuil similarité + confiance |
| Rendu | Serveur (`format_project_rules`) | Composé côté plugin après filtrage/dédup |

Mécanisme : le plugin lit la resource `wpm://project-rules` sur **son propre serveur chaud** (voir `architecture-plugin-hote-mcp.md`), met le bloc en cache mémoire, et le re-splice à chaque tour dans `output.system`. Le cache est invalidé par la notification `resources/updated` reçue du serveur — plus besoin de détecter les mutations dans `tool.execute.after`. Mémoire vide → bloc vide → rien n'est poussé.

## Bloc d'injection générique

Les deux canaux de push (règles + pop-in RAG) partagent le même besoin : wrapper le contenu injecté dans `output.system`. Plutôt que deux formats ad hoc, une seule entité générique dans `wpm-lib/prompts/entities.ts`, dans le style fluide de `PromptContext` :

```
InjectionBlock
  tag        — marqueur XML (ex. wpm-project-rules / wpm-memory-recall)
  title      — optionnel
  purpose[]  — lignes d'intro optionnelles
  body       — contenu pré-rendu (setBody) OU items structurés (addItems)
  notes[]    — pied de bloc optionnel (ex. avis de conflit)
```

Toutes les sections sont optionnelles et composables. Deux modes d'alimentation reflètent l'asymétrie fondamentale entre les deux canaux :

- **Règles projet** — `setBody(pré-rendu)` : le texte est produit **une seule fois côté serveur** (`format_project_rules` + `build_project_rules_block`, déjà utilisés par la resource). La resource et le push sortent *le même octet* : zéro dérive.
- **Pop-in RAG** — `addItems({content, meta})` : les entrées sont filtrées et dédupliquées côté plugin (seuil, top-N, dédup contre l'état de session) avant rendu, avec métadonnées (`similarity`, `confidence`) et `notes` pour les conflits.

Le rendu serveur des règles est ainsi la **source unique** (aucun `wpm rules --markdown` nécessaire) ; la composition reste cliente pour le RAG, car seul le plugin connaît l'état de session (dédup, seuil).

## Répartition des canaux de démarrage de session

Une fois le push en place, la règle de séparation devient : **instructions/nudge = procédural** (comment utiliser la mémoire), **transform push = données** (ce que la mémoire contient).

| Canal | Rôle | Contenu |
|---|---|---|
| Golden rules poussées (`system.transform`) | Procédural | 3 règles + politiques (`wpm://memory-rules`, lues par le plugin) |
| Nudge compact (`system.transform`) | Ré-ancre anti-dilution | rappels courts |
| `<project-rules>` (push) | Données déterministes | bloc rendu serveur, cache + invalidation |
| Pop-in RAG (push) | Données dépendantes du tour | top-N au-dessus du seuil |
| Hook `config` (plan agent) | Permissions | exception `wpm_*` en mode plan |
| Resource `wpm://project-rules` | Pull manuel/audit | relecture à la demande |

L'instruction *« read the `wpm://project-rules` resource »* est retirée du `buildNudge` **et** de la « Startup sequence » de `memory_rules.py` : les règles sont désormais poussées, plus tirées.

## Bénéfices attendus

- **Fiabilité** : les mémoires les plus pertinentes sont garanties d'être présentes en contexte, sans dépendre d'une décision du LLM.
- **Contrôle du bruit** : seuil élevé + peu de résultats évite la pollution de contexte sur les cas ambigus.
- **Flexibilité conservée** : le LLM garde la main pour les cas incertains, avec reformulation de requête et itération.
- **Cohérence avec l'architecture existante** : s'appuie sur les métriques de retrieval et le hook `experimental.chat.system.transform` déjà en place (golden rules), plus les hooks déterministes existants (`tool.execute.after`, `session.idle`, `session.compacting`).

## Points de vigilance

- **Calibration du seuil** : un seuil trop bas génère du bruit systématique, un seuil trop haut réduit l'utilité du pop-in. À valider empiriquement sur un échantillon de requêtes réelles.
- **Nombre de résultats injectés** : le pop-in doit rester restreint (peu de résultats) pour ne pas saturer le contexte à chaque tour.
- **Traçabilité du pop-in** : même sans tool call, il est utile de logger quelles mémoires ont été injectées automatiquement, pour audit et debug du seuil.
- **Déduplication** : une Map par session des `entry_id` déjà injectés évite de re-poppiner les mêmes mémoires à chaque tour ; symétriquement, exclure les entrées déjà remontées par `wpm_query_context` dans le même tour (sinon double présence en contexte).
- **Conflits** : si une entrée candidate au pop-in porte des liens `contradicts` actifs, injecter l'avis de conflit en même temps (`collect_conflicts` existe côté serveur) — sinon le LLM reçoit une affirmation sans savoir qu'elle est contredite.
- **Chevauchement règles ↔ RAG** : une entrée `convention`/`archi_decision` peut ressortir à la fois du bloc `<project-rules>` et du pop-in RAG du même tour — la Map de déduplication doit être **partagée** entre les deux blocs (`entry_id`).
- **Coût contexte des règles** : ~800 tokens constants par tour si le bloc `<project-rules>` est re-splicé à chaque `system.transform` ; acceptable dans la philosophie anti-dilution, mais à assumer (le cache mémoire évite le coût de recherche, pas le coût d'injection).
- **Interaction avec la migration d'embedding multilingue** : la fiabilité du seuil de similarité dépend directement de la qualité de l'embedding sur le français. La migration vers un modèle multilingue est désormais **implémentée** (voir `migration-embedding.md`) — le prérequis d'un seuil de pop-in fiable en français est satisfait ; reste la validation empirique du seuil.

## Étapes de mise en œuvre (proposition)

1. Côté serveur chaud : le plugin récupère le dernier message utilisateur (SDK) et appelle `query_context` via son client MCP (voir `architecture-plugin-hote-mcp.md`).
2. Implémenter la logique de seuil : `similarity ≥ seuil_haut` **ET** `confidence ≥ seuil_confiance` → injection ; sinon rien (le tool de recherche reste actif).
3. Créer `InjectionBlock` dans `wpm-lib/prompts/entities.ts` (+ tests bun) — enveloppe générique à sections optionnelles.
4. Pop-in règles : lire `wpm://project-rules` sur le serveur chaud, cache mémoire, re-splice via `InjectionBlock` (`setBody`) ; invalidation sur `resources/updated`.
5. Pop-in RAG : composer les top-N (N ≤ 3) en `addItems`, marqueur dédié distinguable des golden rules.
6. Déduplication : Map par session partagée entre les deux blocs (`entry_id`) + exclusion des entrées déjà retournées par `wpm_query_context`.
7. Retirer l'instruction pull des règles du `buildNudge` et de la « Startup sequence » de `memory_rules.py`.
8. Logger les injections automatiques via `client.app.log` (entry_ids, scores, sessionID) pour audit du seuil.
9. Tester la calibration du seuil sur un échantillon représentatif de requêtes françaises (la migration vers un embedding multilingue étant en place).
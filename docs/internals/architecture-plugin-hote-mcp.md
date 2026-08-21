# Le plugin comme hôte du serveur MCP

## Contexte

Aujourd'hui trois processus cohabitent :

| Processus | Possesseur | Accès par le plugin |
|---|---|---|
| opencode (host) | l'utilisateur | `client` (SDK, `localhost:4096`) |
| serveur MCP `wpm` (stdio) | opencode | ❌ — la connexion appartient au host |
| CLI `wpm` (spawné) | le plugin via `$` | ✅ shell |

Le protocole MCP est host↔serveur ; le plugin est un tiers sans poignée sur la
connexion que tient opencode. Vérification faite dans la documentation du SDK :
celui-ci n'expose **aucun** namespace `mcp`, `tool` ou `resource` — un plugin ne
peut pas appeler un tool MCP ni lire une resource à travers `client`.

Conséquence : pour ses besoins déterministes, le plugin contourne le serveur en
shelloutant vers le CLI (`wpm record-execution` dans `tool.execute.after`). Chaque
appel est un *cold start* (spawn Python + import + chargement du modèle ONNX), et
le serveur MCP — pourtant **chaud** (embedding en RAM, cache `<project-rules>`) —
reste hors d'atteinte du plugin.

## Décision : le plugin devient maître du serveur

Plutôt que d'exposer le serveur MCP au host opencode, le plugin **spawn et possède**
`python -m wpm_mcp_server`, et tient son propre client MCP persistant. Il réexpose
ensuite chacun des tools et resources du serveur comme tools/ressources de plugin.

### Ce que cela implique

1. Retirer `config.mcp["wpm"]` du hook `config` — opencode ne spawn plus le serveur.
2. Le plugin spawn le serveur (stdio) via `resolvePythonPath()`, et maintient une
   connexion MCP persistante (serveur chaud : embedding + cache règles en RAM).
3. Réexposer chaque tool en tool de plugin nommé `wpm_*` (les règles de permission
   `wpm_*: allow` et l'exception plan-mode restent valides telles quelles).
4. Réexposer les resources (`project-rules`, `memory-rules`,
   `verification-commands`) : lecture à la demande + contenu poussé par le plugin.
5. Livrer les instructions soi-même : opencode n'injectant plus
   `initialize.instructions`, le plugin pousse les golden rules (source unique :
   la resource `wpm://memory-rules`, lue sur son propre serveur).
6. Pop-in des règles projet et du RAG via le serveur chaud — zéro spawn, zéro
   rechargement ONNX par tour (voir `feature-hybride-rag.md`).
7. Le CLI se réduit aux opérations administratives (`enable`, `disable`,
   `reembed`, `export`, `generate`) ; `record-execution` passe par le tool direct.

### Bénéfices

- **Un seul processus serveur**, partagé par le plugin (pop-in déterministe) et le
  LLM (tools réexposés) — plus de double travail ni de dérive de rendu.
- **Chemin chaud** pour le push par tour : embedding déjà chargé, cache
  `<project-rules>` déjà rempli.
- **Descriptions de tools single-source** côté serveur (voir bridge dynamique).
- **Invalidation native** : le plugin reçoit `resources/updated` et invalide son
  cache sans bricolage dans `tool.execute.after`.

### Points de vigilance

- **Client MCP sous Bun** : privilégier un client minimal fait main (voir plus bas)
  plutôt qu'une dépendance dont la compatibilité Bun n'est pas garantie.
- **Robustesse** : si le plugin tombe, le LLM perd *tout* accès mémoire (aujourd'hui
  opencode gère la vie du serveur). Prévoir un restart automatique du serveur si le
  sous-processus meurt, et un teardown propre à l'arrêt du plugin.
- **Conversion JSON Schema → Zod** : les schémas des tools wpm sont simples
  (objets string/number optionnels) ; la conversion générique couvre l'essentiel,
  les cas exotiques devant être traités avec une fallback permissive.
- **Ordre d'initialisation** : le plugin doit pouvoir fonctionner dégradé (tools
  non encore enregistrés) si le serveur met du temps à répondre à `initialize`.

## Client MCP minimal fait main

Sans dépendance, `Bun.spawn` + framing JSON-RPC 2.0 ligne à ligne sur
stdin/stdout. Le protocole étant limité et contrôlé des deux côtés, un client
minimal suffit :

- `initialize` — au boot (récupère aussi `instructions` pour la livraison locale).
- `tools/list` — pour le bridge dynamique.
- `tools/call` — forward des tools réexposés.
- `resources/read` — `project-rules`, `memory-rules`, `verification-commands`.
- notification `notifications/resources/updated` — invalidation du cache règles.

Requêtes/notifications corrélées par `id`, lecture ligne à ligne des messages
JSON-RPC depuis le stdout du sous-processus.

## Bridge dynamique des tools

Au boot, après `tools/list` :

1. Pour chaque tool du serveur, enregistrer un tool de plugin portant le même
   préfixe `wpm_<nom>`.
2. Réutiliser **telle quelle** la `description` du serveur (les prompts d'usage
   restent single-source dans `wpm_mcp_server/prompts`).
3. Convertir `inputSchema` (JSON Schema) en schéma Zod pour le helper `tool`.
4. `execute` = `tools/call` sur le serveur, retour du résultat sérialisé.

Cela évite toute duplication des descriptions (et donc toute dérive entre le
serveur et le plugin), et conserve l'identité des noms `wpm_*` sur laquelle
reposent la permission `allow`, l'exception plan-mode et la détection de
`wpm_query_context` dans `tool.execute.after`.

## Livraison des instructions

Aujourd'hui les golden rules (3 règles + séquence de démarrage + politiques)
atteignent le LLM via `initialize.instructions` injecté par opencode. Le plugin
s'appuie d'ailleurs dessus (son nudge `buildNudge` est volontairement « compact »).

Une fois opencode hors circuit, le plugin est **seul** injecteur : il lit
`wpm://memory-rules` (même source, côté serveur) et la pousse via
`experimental.chat.system.transform`, le nudge compact restant la ré-ancre
anti-dilution de chaque tour. La « Startup sequence » qui demandait *« Read the
wpm://project-rules resource »* est retirée — les règles sont désormais poussées,
plus tirées (voir `feature-hybride-rag.md`).

## Répartition des responsabilités après migration

| Couche | Rôle | Canal |
|---|---|---|
| Golden rules + politiques | Procédural statique | poussé par le plugin (`system.transform`) |
| Nudge compact | Ré-ancre anti-dilution | poussé par le plugin (`system.transform`) |
| Règles projet `<project-rules>` | Données (déterministes) | poussées via serveur chaud, cache + invalidation |
| Pop-in RAG | Données (dépendantes du tour) | poussées via serveur chaud, requête par tour |
| Tools `wpm_*` | Écriture/lecture mémoire par le LLM | réexposés en tools de plugin |
| CLI `wpm` | Admin (enable/reembed/export/…) | shell, hors chemin de réponse |

## Étapes de mise en œuvre (proposition)

1. Retirer l'enregistrement MCP du hook `config` ; conserver permission `wpm_*` et
   exception plan-mode.
2. Implémenter le client MCP minimal (spawn + framing JSON-RPC) dans le plugin.
3. Spawn + lifecycle du serveur : démarrage lazy par projet, restart auto, teardown.
4. Bridge dynamique : `tools/list` → tools plugin `wpm_*` (description reprise,
   JSON Schema → Zod, forward `tools/call`).
5. Pousser les golden rules via `system.transform` (lecture `wpm://memory-rules`).
6. Basculer `record-execution` du shell CLI vers le tool direct.
7. Brancher le pop-in règles + RAG sur le serveur chaud (voir `feature-hybride-rag.md`).
8. Réduire le CLI aux opérations administratives et mettre à jour ses usages.

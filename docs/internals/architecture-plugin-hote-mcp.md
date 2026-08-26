# Le plugin comme hôte du serveur MCP

> **Statut : implémenté** (branche `main-dev`). Le plugin spawn et possède
> `wpm_mcp_server` via `wpm-lib/mcp/client.ts` (client MCP minimal fait main) ;
> les tools sont bridgés dynamiquement (`bridge.ts`), les golden rules, le bloc
> `<current-user>` (profil utilisateur) et les règles projet sont poussés
> chaque tour (`server/system-push.ts`), le pop-in RAG hybride est actif et
> son succès alimente le gate memory-first. `record-execution` passe par
> `tools/call`. Voir « Décisions prises à l'implémentation » en fin de document.

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

## Décisions prises à l'implémentation

1. **Prompting gelé** : aucun texte agent-facing modifié (`nudges.ts`,
   `memory_rules.py`, descriptions, exception plan-mode). En particulier la
   ligne « read the `wpm://project-rules` resource » est conservée — une fois
   le push actif elle devient redondante mais inoffensive. La suppression
   proposée (ici et dans `feature-hybride-rag.md` étape 7) est **écartée**.
2. **Resources non bridgées en tools** : le retrait de `config.mcp["wpm"]`
   fait disparaître les tools natifs `read_mcp_resource` / `list_mcp_resources`
   (opencode ne les crée que si un serveur déclare la capability `resources`).
   Le push par tour rend ce pull inutile ; résidu accepté : la référence molle
   à `wpm://verification-commands` dans la description de `record_execution`
   n'est plus résolvable par le LLM (non bloquant).
3. **Dépendances** : seul `@opencode-ai/plugin` est importé au runtime ;
   zod est utilisé via `tool.schema` (réexport SDK) — jamais importé
   directement, sa présence dans node_modules étant incidente.
4. **Lifecycle** : spawn lazy par projet au chargement du plugin (init
   bloquante ~0.5 s, timeout 10 s, repli dégradé sans tools) ; respawn
   transparent avec backoff exponentiel après mort du sous-processus ;
   `ready()` échoue instantanément pendant la fenêtre de backoff pour ne pas
   stall-er les hooks par tour ; teardown = EOF stdin + kill à la fin du
   process hôte.
5. **Effet de bord assumé** : les `query_context` internes du plugin (pop-in)
   lèvent le flag serveur `_queried_since_last_store` → le rappel « memory-first »
   de `store_entry` ne se déclenche plus. Cohérent avec la garantie push.
6. **Seuil RAG** : `rag_similarity_threshold` (défaut **0.35** après
   recalibration end-to-end, voir `recall-rag-calibration.md` ; déclaré dans
   les `Settings` serveur pour que la validation stricte de `wpm.config.json`
   reste explicite ; lu par le plugin seul) et `rag_max_items` (constante 5). La
   calibration repose sur la distribution observée en conditions réelles :
   les questions FR réelles cosignent 0.36–0.48 contre leurs entrées
   pertinentes avec l'embedding MiniLM multilingue (les paires quasi
   identiques des tests artificiels montent à 0.70 — ne pas s'y fier). Le
   garde `confidence ≥ confidence_threshold` reste l'outil de précision.
   Traçabilité : une ligne `rag decision` (niveau info) est loggée par tour
   avec candidats, picks et top_sim ; traces de décision détaillées via
   `WPM_DEBUG=1`.
7. **Dédup** : dans un même tour, une entrée déjà rendue dans le bloc
   `<project-rules>` n'est pas re-injectée par le pop-in (filtre par contenu).
   La dédup inter-tours et l'exclusion des résultats déjà remontés au LLM via
   `wpm_query_context` restent à faire si les tests manuels montrent des
   doublons ; l'avis de conflit utilise les `conflicts` déjà retournés par
   `query_context`.
8. **Étape 8 (réduction CLI)** : non exécutée ; `wpm record-execution` reste
   disponible mais n'est plus appelé par le plugin.
9. **Mode optionnel (`plugin_master`)** : les deux architectures coexistent,
   choisies par clé booléenne dans `wpm.config.json` (défaut `false` =
   legacy). Legacy : bloc `config.mcp["wpm"]` restauré verbatim, nudge seul
   poussé, shellout CLI pour `record-execution` — l'injection
   `initialize.instructions` par opencode redevient le canal des golden
   rules et les tools natifs `read_mcp_resource` réapparaissent (le host
   détecte la capability `resources`). Master : comportement décrit
   ci-dessus. Le plugin ne spawn **jamais** de serveur en legacy.
10. **Réglages RAG** : `rag_similarity_threshold` (0.35) et `rag_max_items`
    (5) sont déclarés dans les `Settings` serveur mais lus par le plugin ;
    sans effet en mode legacy.
11. **Prompt fidelity per-mode** : les instructions « Read the wpm://…
    resource » n'ont de sens qu'en legacy (le LLM y lit via
    `read_mcp_resource`). En master, elles sont **omises à la construction**
    — jamais mutées après rendu :
    - serveur : `WPM_PROMPT_MODE=push` (posé par le plugin au spawn) fait
      rendre à `build_memory_usage_rules` la variante sans l'étape 1
      (renumérotation naturelle par assemblage dynamique) et retire la
      mention `wpm://verification-commands` de la description de
      `record_execution` ; défaut = octets historiques bit-identiques ;
    - plugin : `buildNudge(language, pluginMaster)` insère la ligne pull
      uniquement en legacy via l'option `{before}` des entités
      (`addInstruction({before: true}, …)`), toutes manipulables après
      instanciation (`clone()` partout, `InjectionBlock.clone()` inclus).
12. **Durabilité `record_execution`** : en master, toute dégradation du
    serveur au moment du hook bash (indisponible au check ou mort pendant
    l'appel) bascule sur le shellout CLI autonome — parité de durabilité
    totale avec legacy, coût nul en nominal.
13. **Anti-hijack d'agent** : incident réel — un tour build a été basculé
    en plan par une injection du plugin créée via `client.session.prompt`
    **sans champ `agent`** (héritage du `default_agent`=plan). Correctifs :
    `default_agent` n'est plus posé (sessions en build par défaut) ; les
    deux injections restantes (filet idle, nudge memory-first) résolvent
    l'agent vivant via `client.session.get` et le passent explicitement ;
    la détection `queriedRecently` pour le gate memory-first est alimentée
    par le bridge lui-même (`onQueryContext`) **et** par un recall RAG
    réussi (`system-push.ts`), les hooks hôte s'étant révélés non fiables
    pour les tools définis par plugin.

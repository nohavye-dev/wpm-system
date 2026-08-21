# Moyens MCP pour orienter le comportement du LLM à des moments définis

Basé sur la spécification MCP (dernière révision publiée : `2025-11-25`, schema.ts faisant foi).
Référence : https://modelcontextprotocol.io/specification/2025-11-25

> **Note** — ce document explore les options pour rester 100 % MCP et
> portable. Le projet a finalement retenu l'autre branche : OpenCode comme
> host unique, avec le push déterministe porté par le plugin (hooks
> `experimental.*`), voir `prompting-optimization-guide.md`. Ce
> document reste utile comme référence des primitives MCP.

---

## Vue d'ensemble : les primitives et leur moment d'injection

| Primitive | Direction | Déclenché quand | Contrôle temporel |
|---|---|---|---|
| `initialize.instructions` | serveur → client | une fois, au démarrage de session | aucun (statique pour toute la session) |
| Description de tool | serveur → client | chargé au `tools/list`, relu à chaque décision d'appel | statique sauf `listChanged` |
| `prompts/get` | serveur → client | à la demande (utilisateur ou client déclenche) | fort — tu choisis le moment |
| Contenu de `resources/read` | serveur → client | quand le LLM/client lit la ressource | moyen — dépend de quand elle est lue |
| Résultat de `tools/call` (`tool_result`) | serveur → client | juste après exécution d'un outil | fort — c'est le canal le plus fiable pour "après action X, fais Y" |
| `sampling/createMessage` | serveur → client → LLM | le serveur le déclenche lui-même, à tout moment de sa propre logique | très fort, mais soumis à approbation utilisateur |
| `elicitation/create` | serveur → client → utilisateur | le serveur le déclenche pour demander une info | fort pour obtenir des données, pas pour "instruire" le LLM directement |
| `notifications/*` + `listChanged` | serveur → client | changement d'état côté serveur | permet de re-déclencher un rechargement de contexte |
| Annotations de tool (`title`, `readOnlyHint`, etc.) | serveur → client | chargé avec la description | influence le choix d'outil, pas une instruction directe |

---

## 1. `instructions` dans la réponse `initialize`

Champ prévu spécifiquement pour donner des règles d'usage du serveur au LLM.

```json
{
  "result": {
    "protocolVersion": "2025-06-18",
    "capabilities": { "tools": {}, "resources": {} },
    "serverInfo": { "name": "mon-serveur", "version": "1.0.0" },
    "instructions": "Utilise toujours l'outil `search` avant `write`. Ne jamais appeler `delete` sans confirmation explicite de l'utilisateur."
  }
}
```

**Portée temporelle** : chargé une seule fois, au tout début de la session. La plupart des clients l'injectent dans le system prompt ou en tout début de contexte. Ce n'est **pas** un canal pour du "juste-à-temps" — c'est une instruction de fond, valable toute la session.

**Usage pour du comportement daté/conditionnel** : décrire des règles générales ("quand X, fais Y"), pas déclencher une action précise à un instant précis.

---

## 2. Descriptions de tools (`tools/list`)

```json
{
  "name": "deploy",
  "description": "Déploie l'application en production. À N'UTILISER QU'APRÈS avoir appelé `run_tests` et reçu un résultat 'passed'. Ne jamais appeler ce tool un vendredi.",
  "inputSchema": { "...": "..." }
}
```

**Portée temporelle** : chargée au `tools/list`, relue par le modèle à **chaque** décision d'invocation d'outil (contrairement à `instructions`, qui n'est vue qu'une fois puis reste diluée dans le contexte). C'est donc un vecteur plus fiable que `instructions` pour des règles de séquencement ("fais A avant B").

**Limite** : aucune garantie que le client ne cache/tronque cette description dans son UI de consentement, et aucune garantie de relecture stricte par le modèle à chaque tour — dépend de l'implémentation du client (system prompt vs. function-calling schema natif).

Depuis `2025-06-18`, les tools peuvent aussi déclarer :
- **`outputSchema`** (sortie structurée) — utile pour forcer un format de retour exploitable par ta logique de routing.
- **Resource links** dans le résultat — le tool peut renvoyer une référence vers une resource plutôt que son contenu brut, ce qui te permet de contrôler *quand* le contenu volumineux est réellement chargé (uniquement si le LLM va le lire).

---

## 3. `prompts` — le canal le plus adapté à un déclenchement précis

C'est la primitive prévue pour **injecter des instructions à la demande**, pas en continu.

```json
// prompts/list
{
  "prompts": [
    {
      "name": "pre-deploy-checklist",
      "description": "Charge la checklist de déploiement avant toute mise en production.",
      "arguments": [{ "name": "environment", "required": true }]
    }
  ]
}
```

```json
// prompts/get
{
  "messages": [
    {
      "role": "user",
      "content": {
        "type": "text",
        "text": "Avant de déployer sur {environment}, vérifie: 1) tests passés 2) migration DB appliquée 3) rollback plan écrit."
      }
    }
  ]
}
```

**Portée temporelle** : c'est **toi** (ou le client, ou l'utilisateur via une commande slash `/pre-deploy-checklist`) qui déclenche `prompts/get` au moment choisi. C'est le mécanisme le plus explicite pour "à ce moment précis du workflow, injecte ce message dans le contexte."

C'est probablement le canal le plus propre pour insérer des instructions à un moment précis du workflow (par exemple avant un dispatch de sous-agent), plutôt que de bricoler via `tool_result`.

---

## 4. `resources` — contexte chargé au moment de la lecture

```json
{
  "uri": "config://project-rules",
  "name": "Règles du projet",
  "mimeType": "text/plain",
  "text": "Toute modification du Synchronizer doit passer par une revue avant merge."
}
```

**Portée temporelle** : injecté dans le contexte au moment où le client (ou le LLM via un tool `resources/read`) va la chercher. Si tu veux forcer un chargement à un instant précis, deux stratégies :
- **`resources/subscribe`** + `notifications/resources/updated` : le serveur notifie le client qu'une resource a changé, ce qui peut déclencher un rechargement automatique côté client selon son implémentation.
- Renvoyer un **resource link** dans un `tool_result` juste après une action, pour que la resource soit lue "à chaud" dans la continuité logique de l'action.

---

## 5. Résultat de `tools/call` — le canal le plus fiable pour du séquencement

C'est objectivement le vecteur le **plus efficace** pour orienter un comportement juste après une action précise, parce qu'il est réinjecté directement dans le fil de conversation, à l'endroit exact où le modèle va raisonner sur la suite.

```json
{
  "content": [
    { "type": "text", "text": "Fichier importé avec succès (142 lignes)." },
    { "type": "text", "text": "ÉTAPE SUIVANTE REQUISE : appelle `validate_import` avant toute autre opération sur ces données." }
  ],
  "isError": false
}
```

**Portée temporelle** : immédiatement après l'exécution de l'outil, donc c'est le mécanisme naturel pour "après avoir fait X, fais Y" — bien plus fiable que d'espérer que le modèle se souvienne d'une règle énoncée 30 tours plus tôt dans `instructions`.

**Sortie structurée (`structuredContent`, depuis 2025-06-18)** : si tu définis un `outputSchema`, tu peux forcer un format de retour prévisible, ce qui te permet de piloter la logique de suite côté client/orchestrateur plutôt que de compter uniquement sur le LLM pour "bien lire" le texte.

---

## 6. `sampling/createMessage` — le serveur pilote directement une génération LLM

Le serveur peut demander au client de faire générer du texte par le modèle, avec un prompt que **le serveur choisit**, à un moment que **le serveur choisit** dans sa propre logique métier (pas seulement en réponse à un appel de tool).

```json
{
  "method": "sampling/createMessage",
  "params": {
    "messages": [{ "role": "user", "content": { "type": "text", "text": "Résume ces logs et signale toute anomalie critique." } }],
    "systemPrompt": "Tu es un agent de supervision. Si tu détectes une anomalie critique, réponds uniquement par le JSON {\"alert\": true, \"reason\": \"...\"}.",
    "maxTokens": 500
  }
}
```

**Portée temporelle** : totalement libre côté serveur — c'est le mécanisme le plus fort pour un déclenchement autonome à un instant choisi (ex : après un événement interne du serveur, un cron, un webhook reçu).

**Contrainte du protocole** : la spec exige explicitement une **approbation utilisateur** avant tout sampling, et limite volontairement la visibilité du serveur sur le prompt final envoyé (le client peut le modifier/filtrer). C'est un garde-fou protocolaire — impossible à contourner proprement, donc à prendre en compte dans ton archi si tu veux du déclenchement "silencieux".

Note : dans le brouillon `2026-07-28`, `sampling` (ainsi que `roots` et `logging`) est marqué **déprécié**, au profit de paramètres de tool ou d'appels directs à l'API du provider. À surveiller si tu conçois quelque chose de durable dessus.

---

## 7. `elicitation/create` — demander une info à un moment précis

```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Confirmer le déploiement en production ?",
    "requestedSchema": { "type": "object", "properties": { "confirm": { "type": "boolean" } } }
  }
}
```

**Portée temporelle** : déclenché par le serveur à l'instant où il a besoin d'une donnée ou d'une confirmation — utile pour forcer une pause/synchronisation dans un workflow agentique avant de laisser le LLM continuer.

---

## 8. Notifications de changement (`listChanged`)

- `notifications/tools/list_changed`
- `notifications/resources/list_changed`
- `notifications/prompts/list_changed`

**Usage pour du timing** : si tu veux que de nouvelles instructions (nouveaux tools, nouvelles descriptions, nouveaux prompts) apparaissent **seulement** à partir d'un certain moment du workflow (ex: débloquer des tools de "phase 2" seulement après la phase 1), tu peux :
1. Ne déclarer la capability `listChanged: true` qu'au début,
2. Modifier dynamiquement la liste des tools/prompts/resources exposés côté serveur selon l'état interne,
3. Émettre la notification correspondante pour forcer le client à recharger via `tools/list` / `prompts/list`.

C'est le mécanisme protocolaire le plus propre pour du **contexte conditionnel dans le temps** (plutôt que de tout charger dès `initialize` et compter sur le LLM pour ignorer ce qui n'est pas encore pertinent).

---

## Synthèse pour `wpm-system` (mémoire persistante pondérée)

Ici l'objectif n'est pas "après action X, fais Y" mais **injecter le bon souvenir, au bon moment de la conversation, avec le bon poids**. Correspondance par mécanisme :

1. **`resources` + `resources/subscribe`** — chaque souvenir (ou cluster) exposé comme resource individuelle plutôt qu'un blob unique chargé en bloc. `notifications/resources/updated` permet de signaler qu'un score de confiance a changé suite à une nouvelle interaction, sans attendre un nouveau cycle `initialize`.

2. **`prompts/get` paramétré** — un prompt qui prend `topic`/`session_id` en argument et retourne les souvenirs déjà filtrés/pondérés par ton scoring hybride vecteur+graphe. C'est le point d'entrée le plus propre pour un rappel explicite "à la demande", plutôt que tout précharger dans `initialize.instructions`.

3. **`tool_result` d'un tool `recall`/`memory_search`** — si le rappel est déclenché par un appel de tool, le résultat est vu par le modèle exactement au tour où il en a besoin. Plus fiable que `instructions`, qui se dilue au fil de la conversation.

4. **`sampling/createMessage` pour l'auto-évaluation de pertinence** — le serveur wpm peut lui-même interroger le LLM ("ce souvenir est-il pertinent pour ce contexte ?") avant de décider de l'injecter, plutôt que de tout pousser et compter sur le modèle principal pour trier. Soumis à consentement utilisateur — donc pas silencieux, à prévoir dans l'UX.

5. **`instructions` (initialize)** et **descriptions de tools** — utiles uniquement pour des règles de fond permanentes ("comment interpréter le score de confiance"), pas pour du rappel contextuel précis.

**Limite structurelle à connaître** : la spec MCP ne prévoit **aucun mécanisme serveur pour forcer une injection à chaque tour**. Le "push systématique avant chaque message" est par nature une responsabilité du host/client (c'est lui qui construit le contexte final envoyé au LLM), pas du serveur. Les hooks type `messages.transform` d'OpenCode ne sont donc pas un raccourci parmi d'autres — c'est la seule vraie porte d'entrée pour du push inconditionnel, et elle est nécessairement propriétaire à chaque host puisque non normalisée. Aucun host MCP (Claude Desktop, OpenCode, autres) n'expose une garantie standard "exécute ceci avant chaque tour".

**Si tu veux rester 100 % MCP et portable entre hosts**, les options réalistes sont toutes en **pull renforcé** côté serveur, pas en push :

1. **`instructions` (initialize) comme directive de comportement récurrent** — au lieu d'y mettre du contexte statique, y mettre une consigne procédurale explicite : *"Avant de répondre à toute question nécessitant du contexte historique, appelle systématiquement `memory_recall` avec le sujet courant."* Ça ne force rien au niveau protocole, mais c'est le seul canal qui s'adresse au modèle une fois par session et qui vaut pour n'importe quel host respectant MCP.

2. **Description de tool volontairement directive** — sur le tool `memory_recall` lui-même, une description du type *"À appeler en tout début de chaque réponse substantielle, avant toute autre action."* Comme les descriptions sont relues à chaque décision d'invocation (contrairement à `instructions`, lu une fois), c'est le levier le plus fiable en pur MCP pour approcher un comportement "systématique" sans dépendre du host.

3. **`resources/subscribe` sur les souvenirs à forte pondération** — certains hosts MCP (pas seulement OpenCode) incluent automatiquement les resources souscrites dans le contexte à chaque tour, selon leur propre politique. C'est un comportement d'implémentation, pas garanti par la spec, mais il ne dépend pas d'un hook spécifique à OpenCode : n'importe quel host qui gère correctement `resources/subscribe` en bénéficiera.

4. **Réponse de tool auto-suggestive** — chaque `tool_result` (y compris d'outils sans rapport avec la mémoire) peut se terminer par une ligne du type *"Rappel : vérifie `memory_recall` si le contexte historique est pertinent ici."* C'est un pull encouragé à répétition, portable, mais ça consomme du contexte à chaque tour et reste probabiliste.

**Constat honnête** : sans le host, il n'existe pas de push déterministe garanti par le protocole. Le compromis 100 % MCP le plus robuste est la combinaison **1 + 2** : une directive de fond en `instructions`, doublée d'une description de tool très directive — ce qui rapproche fortement le comportement d'un push sans jamais l'être formellement, et reste portable si tu changes de host un jour.

**Point de vigilance protocolaire** : aucun de ces canaux n'a de distinction native entre "instruction de confiance" et "donnée" une fois dans le contexte du LLM — la spec le reconnaît explicitement ("descriptions of tool behavior ... should be considered untrusted, unless obtained from a trusted server"). Si tu es à la fois auteur du serveur et de l'orchestrateur (ton cas), ce n'est pas un problème de sécurité pour toi, juste une chose à garder en tête si tu documentes ça pour d'autres usages.

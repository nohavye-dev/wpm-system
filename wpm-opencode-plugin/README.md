# wpm-opencode-plugin

Le plugin OpenCode de WPM, **installé par défaut** par `install.sh` dans
`~/.config/opencode/plugins/`. Il fait deux choses qu'un serveur MCP pur ne
peut pas faire :

1. **Permission et commandes** — à partir du `wpm.config.json` du projet, le
   hook `config` déclare la permission `wpm_*` et les commandes slash `wpm-*`
   dans la configuration d'OpenCode.
2. **Pousser de façon déterministe** — les règles se diluent dans un long
   contexte ; le plugin les ré-injecte au bon moment. Il spawn et possède
   le serveur MCP `wpm` (serveur chaud).

## Documentation

- Site web du projet : [WPM — Weighted Persistent Memory](https://nohavye-dev.github.io/wpm-site/)

## Ce qu'il fait

- **`config`** — déclare la permission `wpm_*` (`allow`) + les commandes
  slash `wpm-*`. Injecte une exception
  mémoire dans l'agent plan : les outils `wpm_*` restent autorisés même en
  mode plan. `default_agent` est volontairement **non** positionné — forcer
  `plan` faisait basculer silencieusement des tours `build` (chaque commande
  porte son `agent: "plan"` individuellement).
- **`command.execute.before`** — masque le long texte des commandes slash
  (part `synthetic`) et affiche un label court `/wpm-<commande>`.
- **`chat.message`** — ré-arme la passe de persistance sur un vrai message
  utilisateur.
- **`experimental.chat.system.transform`** — push système à chaque tour :
  règles d'or + bloc `<current-user>` + règles projet + pop-in RAG (recall
  du dernier message utilisateur), puis le nudge compact en bas de contexte.
- **`experimental.session.compacting`** — rappelle de persister ce qui ne
  l'est pas avant compaction.
- **`tool.execute.after`** — capture les commandes de test/build/lint
  via `record_execution` (warm `tools/call`) sans dépendre du LLM ; suit
  les `query_context`.
- **`tool.execute.before`** — nudge « memory first » conditionnel avant une
  lecture/`grep`/`glob` sans `query_context` récent.
- **`event` (`session.idle`)** — déclenche la passe de persistance :
  maintenance de fond injectée entre les tours, la session continue
  normalement après ; silence strict si rien n'a été persisté.

## Structure

Le plugin est découpé en modules (un seul fichier installé côté OpenCode
n'est pas possible : chaque `*.ts` à la racine du dossier `plugins/` serait
chargé comme un plugin). Les modules d'aide vivent donc dans `wpm-lib/`,
un sous-dossier ignoré par le scan non récursif d'OpenCode :

```
wpm-opencode-plugin/
  plugin.ts              # entrée : isEnabled → langue → état → assemble les hooks
  wpm-lib/
    core/
      constants.ts       # SERVER_NAME
    config/
      settings.ts        # isEnabled / readConfigParam / resolveResponseLanguage
    infra/
      paths.ts           # resolvePythonPath (venv du serveur)
    mcp/
      client.ts          # client MCP stdio (serveur chaud) + lectures resources
      bridge.ts          # pont dynamique des tools serveur en tools plugin
      schema.ts          # JSON Schema → zod
      entities.ts        # types résultats MCP
    prompts/
      entities.ts        # DSL PromptTask / PromptContext / InjectionBlock
      clauses.ts         # clauses de langue (réponse attendue, note de langue)
      nudges.ts          # nudges ré-injectés + buildPersistPromptText(language)
      commands/          # un fichier par commande slash + index (buildCommands)
    server/
      hooks.ts           # createHooks(ctx) — tous les hooks
      system-push.ts     # push déterministe par tour (règles, profil, RAG)
```

## Langue de réponse

Le contenu stocké en mémoire est écrit en **langue native** (le modèle
d'embedding est multilingue). La langue des **réponses** est régie par des
clauses fermes et répétées, injectées aux endroits où la donnée (souvent
anglaise) risque de l'emporter :

- `response_language` dans `wpm.config.json` (ex. `"french"`), ou `"auto"`/
  omis pour suivre la langue de l'utilisateur. Surchargeable par
  `WPM_RESPONSE_LANGUAGE`.
- Le **nudge** ré-injecté dans le system prompt à **chaque tour** porte la
  clause « … MUST be written in french, regardless of the language used in
  memory or in these instructions » — c'est la position la plus forte
  (system, tout tour).
- Le serveur MCP injecte la clause dans les règles principales
  (`initialize.instructions` / `wpm://memory-rules`) ; en `auto` il injecte
  « … MUST use the same language as the user asking questions — do not
  switch to English for output ».
- Les commandes slash réaffirment la langue : `wpm-audit` et `wpm-patterns`
  portent une directive explicite en tête (rapport entier dans la langue
  cible : titres, analyse, recommandations, verdict), plus `languageNote`
  dans `wpm-learn` / `wpm-map` / `wpm-bootstrap`.

## Installation

Installé par défaut par `install.sh`, qui copie `plugin.ts` + `wpm-lib/`
dans `~/.config/opencode/plugins/`. Pour le réinstaller, relancer
`install.sh` ; pour le retirer, `wpm uninstall` supprime aussi les fichiers
du plugin.

Puis redémarrer OpenCode.

## Prérequis

- Un `wpm.config.json` à la racine du projet (`wpm enable`).
- Le venv du serveur installé (`install.sh`).

## Avertissement

Les hooks `experimental.*` ne sont **pas stabilisés** côté OpenCode et
peuvent être ignorés silencieusement selon la version (vérifiés sur
1.18.11). Après chaque montée de version d'OpenCode, confirmez que les hooks
se déclenchent (logs du service `wpm-plugin` pendant une vraie session).

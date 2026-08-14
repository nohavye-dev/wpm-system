# wpm-opencode-plugin

Couche **optionnelle** OpenCode qui ajoute le push déterministe qu'un
serveur MCP pur ne peut pas fournir. Sans elle, le serveur wpm est
entièrement fonctionnel mais sa conformité repose sur des règles injectées
une seule fois en début de session : elles se **diluent** à mesure que le
contexte grossit (observé en condition réelle : les règles ne sont plus
suivies après les 3-4 premiers messages).

Le plugin ré-injecte une carte de règles compacte au **bas** du contexte, là
où le modèle porte son attention.

## Ce qu'il fait

- **`experimental.chat.system.transform`** — injecte la carte d'or
  (MEMORY FIRST / WRITE AS YOU GO / PROOF BEFORE VALIDATION, avec les noms
  `wpm_*`) dans le prompt système à **chaque tour**.
- **`experimental.session.compacting`** — ré-injecte la carte + un rappel
  « persiste tout fait durable non stocké » dans le résumé de compaction.
- **`event` (`session.idle`)** — journalise un rappel de fin de session.

Il est **inerte par projet** : sans `wpm.config.json` à la racine, aucun hook
n'agit. Le serveur MCP reste autonome sans lui.

## Installation (opt-in)

```bash
wpm plugin install      # copie plugin.ts dans ~/.config/opencode/plugins/
wpm plugin uninstall    # le retire
```

Puis redémarrer OpenCode.

## Prérequis

- Le serveur MCP doit être enregistré sous le nom `wpm` dans `opencode.json`
  (les outils sont alors `wpm_query_context`, `wpm_store_entry`, …). Si vous
  l'enregistrez sous un autre nom, adaptez la constante `SERVER_NAME` en tête
  de `plugin.ts`.
- Le projet doit avoir `wpm.config.json` (`wpm enable`).

## Avertissement

Les hooks `experimental.*` sont non stabilisés et peuvent être ignorés
silencieusement par OpenCode si leur nom change. Ils ont été vérifiés sur
OpenCode 1.18.11 (`experimental.chat.system.transform` et
`experimental.session.compacting`). Après installation, confirmez que le hook
se déclenche en surveillant les logs du service `wpm-plugin` pendant une
vraie session.

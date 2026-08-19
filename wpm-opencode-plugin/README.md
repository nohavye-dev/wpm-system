# wpm-opencode-plugin

Le plugin OpenCode de WPM, **installé par défaut** par `install.sh` dans
`~/.config/opencode/plugins/`. Il fait deux choses qu'un serveur MCP pur ne
peut pas faire :

1. **Enregistrer le serveur** — à partir du `wpm.config.json` du projet, le
   hook `config` déclare le serveur MCP `wpm` et la permission `wpm_*` dans
   la configuration d'OpenCode : aucune entrée `mcp` manuelle dans
   `opencode.json`.
2. **Pousser de façon déterministe** — les règles se diluent dans un long
   contexte ; le plugin les ré-injecte au bon moment.

## Documentation

- Site web du projet : [WPM — Weighted Persistent Memory](https://nohavye-dev.github.io/wpm-site/)

## Ce qu'il fait

- **`config`** — enregistre le serveur MCP `wpm` (venv `python -m
  wpm_mcp_server`, `WPM_CONFIG_PATH` pointé sur le projet) + permission
  `wpm_*` (`allow`) + les commandes slash `wpm-*`.
- **`command.execute.before`** — masque le long texte des commandes slash
  (part `synthetic`) et affiche un label court `/wpm-<commande>`.
- **`chat.message`** — ré-arme la passe de persistance sur un vrai message
  utilisateur.
- **`experimental.chat.system.transform`** — ré-injecte la carte de règles
  compacte à chaque tour.
- **`experimental.session.compacting`** — rappelle de persister ce qui ne
  l'est pas avant compaction.
- **`tool.execute.after`** — capture les commandes de test/build/lint
  (`wpm record-execution`) sans dépendre du LLM ; suit les `query_context`.
- **`tool.execute.before`** — nudge « memory first » conditionnel avant une
  lecture/`grep`/`glob` sans `query_context` récent.
- **`event` (`session.idle`)** — déclenche la passe de persistance de fin de
  session.

## Structure

Le plugin est découpé en modules (un seul fichier installé côté OpenCode
n'est pas possible : chaque `*.ts` à la racine du dossier `plugins/` serait
chargé comme un plugin). Les modules d'aide vivent donc dans `wpm-lib/`,
un sous-dossier ignoré par le scan non récursif d'OpenCode :

```
wpm-opencode-plugin/
  plugin.ts              # entrée : isEnabled → langue → état → assemble les hooks
  wpm-lib/
    constants.ts         # SERVER_NAME
    language.ts          # gestion de la langue de réponse (response_language)
    nudges.ts            # nudges ré-injectés + buildPersistPromptText(language)
    commands.ts          # templates + buildCommands(language)
    helpers.ts           # isEnabled / resolvePythonPath
    hooks.ts             # createHooks(ctx) — tous les hooks
```

## Langue de réponse

Miroir de la gestion du serveur MCP : le contenu stocké en mémoire et les
instructions restent **en anglais** (cohérence d'embedding) — seule la
langue de **réponse conversationnelle** est régie.

- `response_language` dans `wpm.config.json` (ex. `"french"`), ou
  `"auto"`/omis pour suivre la langue de l'utilisateur. Surchargeable par
  `WPM_RESPONSE_LANGUAGE`.
- Le nudge injecté à chaque tour porte la clause `OUTPUT LANGUAGE`.
- Les templates des commandes slash portent toujours une directive de
  langue (y compris en mode auto) couvrant titres, intitulés, libellés et
  verdict — seuls les noms de types d'entrées et le contenu stocké restent
  anglais.
- Les réponses du pass de persistance sont localisées dans la langue de
  réponse.

## Installation

Installé par défaut par `install.sh`. Réinstallation / retrait manuel :

```bash
wpm plugin install      # copie plugin.ts + wpm-lib/ dans ~/.config/opencode/plugins/
wpm plugin uninstall    # les retire
```

Puis redémarrer OpenCode.

## Prérequis

- Un `wpm.config.json` à la racine du projet (`wpm enable`).
- Le venv du serveur installé (`install.sh`).

## Avertissement

Les hooks `experimental.*` ne sont **pas stabilisés** côté OpenCode et
peuvent être ignorés silencieusement selon la version (vérifiés sur
1.18.11). Après chaque montée de version d'OpenCode, confirmez que les hooks
se déclenchent (logs du service `wpm-plugin` pendant une vraie session).

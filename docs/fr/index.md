# Documentation — WPM (français)

Bienvenue dans la documentation française du bundle WPM.

## Documentation

- [`setup.md`](setup.md) — guide d'activation : couvre l'installation globale (`install.sh`) et le flux par projet `wpm enable` / `wpm disable` / `wpm uninstall`, ainsi que le redémarrage d'OpenCode après chaque étape.
- [`wpm-config-reference.md`](wpm-config-reference.md) — référence du schéma `wpm.config.json` : `db_path` obligatoire, section `domain` facultative, constantes de lancement du serveur fixées et leurs substitutions par variables d'environnement.
- [`wpm-doc.md`](wpm-doc.md) — commande `/wpm-doc` : ingestion d'un document markdown dans la mémoire persistante, découpé par section.
- [`wpm-code.md`](wpm-code.md) — commande `/wpm-code` : cartographie de la base de code en faits d'architecture et de conventions durables.

## Liens vers la racine du dépôt

- [`../../README.md`](../../README.md) — README du bundle.

## README des composants

- [`../../wpm-mcp-server/README.md`](../../wpm-mcp-server/README.md) — serveur MCP Python : installation et utilisation.
- [`../../wpm-opencode-plugin/README.md`](../../wpm-opencode-plugin/README.md) — plugin TypeScript pour OpenCode : compilation et utilisation.

## À propos des commandes installées

`project-commands/wpm-doc.md` et `project-commands/wpm-code.md` sont
les versions fonctionnelles **installées** (copiées par `install.sh` dans
`~/.config/opencode/commands/` comme commandes slash globales
`/wpm-doc` et `/wpm-code`) ; les copies présentes dans `docs/fr/`
sont des traductions/documentation.

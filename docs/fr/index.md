# Documentation — WPM (français)

Bienvenue dans la documentation française de WPM.

WPM est un **serveur MCP pur** (Python, SQLite + sqlite-vec) qui donne à
votre agent une mémoire persistante pondérée par la confiance, ainsi que les
règles d'usage et les workflows associés — portable sur n'importe quel host
MCP (OpenCode, Claude Desktop, etc.).

## Documentation

- [`setup.md`](setup.md) — guide d'activation : couvre l'installation globale (`install.sh`) et le flux par projet `wpm enable` / `wpm enable --write-config` / `wpm disable` / `wpm uninstall`, l'entrée `mcp` à ajouter dans votre host, et le redémarrage après chaque étape.
- [`wpm-config-reference.md`](wpm-config-reference.md) — référence du schéma `wpm.config.json` : `db_path` obligatoire, sections optionnelles (`confidence_threshold`, `verification_command_patterns`, `domain`), et substitutions par variables d'environnement.
- [`memory-behavior-spec.md`](memory-behavior-spec.md) — comportement de l'agent : quand et comment écrire/valider/contredire/lire la mémoire, et le rôle des commandes d'ingestion.
- [`commands.md`](commands.md) — commandes `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns` : ingestion contrôlée d'un document, cartographie du code, revue de la santé de la mémoire, bootstrap initial du projet, et analyse de patterns.

## Liens vers la racine du dépôt

- [`../../README.md`](../../README.md) — README du bundle.

## README du composant

- [`../../wpm-mcp-server/README.md`](../../wpm-mcp-server/README.md) — serveur MCP Python : installation, outils, resources, prompts.

## À propos des commandes installées

`wpm-commands/wpm-doc.md`, `wpm-commands/wpm-code.md`,
`wpm-commands/wpm-review.md`, `wpm-commands/wpm-bootstrap.md` et
`wpm-commands/wpm-patterns.md`
(à la racine du
dépôt) sont les versions fonctionnelles **installées** : copiées par
`install.sh` dans `~/.config/opencode/commands/` comme commandes slash
globales `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns`.
Ce sont des **wrappers opencode** qui délèguent aux prompts MCP du serveur
(`wpm-doc`, `wpm-code`, ...) — des commandes **manuelles** : elles ne
s'exécutent que sur invocation explicite de l'utilisateur.

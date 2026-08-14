# Documentation — WPM (français)

Bienvenue dans la documentation française de WPM.

WPM est un **serveur MCP pur** (Python, SQLite + sqlite-vec) qui donne à
votre agent une mémoire persistante pondérée par la confiance, ainsi que les
règles d'usage et les workflows associés — portable sur n'importe quel host
MCP (OpenCode, Claude Desktop, etc.).

## Documentation

- [`setup.md`](setup.md) — guide d'activation : couvre l'installation globale (`install.sh`), l'enregistrement unique du serveur dans le host, et le flux par projet `wpm enable` / `wpm disable` / `wpm uninstall`, avec le redémarrage après chaque étape.
- [`wpm-config-reference.md`](wpm-config-reference.md) — référence du schéma `wpm.config.json` : `db_path` obligatoire, sections optionnelles (`confidence_threshold`, `verification_command_patterns`, `domain`), et substitutions par variables d'environnement.
- [`memory-behavior-spec.md`](memory-behavior-spec.md) — comportement de l'agent : quand et comment écrire/valider/contredire/lire la mémoire, et le rôle des commandes d'ingestion.
- [`commands.md`](commands.md) — workflows `learn`, `map`, `audit`, `bootstrap` et `patterns` (prompts MCP) : ingestion contrôlée de documents, cartographie du code, revue de la santé de la mémoire, bootstrap initial du projet, et analyse de patterns.

## Liens vers la racine du dépôt

- [`../../README.md`](../../README.md) — README du bundle.

## README du composant

- [`../../wpm-mcp-server/README.md`](../../wpm-mcp-server/README.md) — serveur MCP Python : installation, outils, resources, prompts.

## À propos des workflows d'ingestion

Les workflows `learn`, `map`, `audit`, `bootstrap` et
`patterns` sont des **prompts MCP** exposés par le serveur (déclarés
dans `wpm-mcp-server/src/wpm_mcp_server/server.py`). Dans opencode ils
apparaissent comme commandes slash (ex. `/wpm:learn:mcp`) ; dans tout
autre host MCP, comme des prompts du serveur `wpm`. Ce sont des workflows
**manuels** : ils ne s'exécutent que sur invocation explicite de
l'utilisateur.

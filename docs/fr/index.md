# Documentation — WPM (français)

Bienvenue dans la documentation française du bundle WPM.

## Documentation

- [`setup.md`](setup.md) — guide d'activation : couvre l'installation globale (`install.sh`) et le flux par projet `wpm enable` / `wpm disable` / `wpm uninstall`, ainsi que le redémarrage d'OpenCode après chaque étape.
- [`wpm-config-reference.md`](wpm-config-reference.md) — référence du schéma `wpm.config.json` : `db_path` obligatoire, sections optionnelles (`confidence_threshold`, `idle_nudge`, `domain`), constantes de lancement du serveur fixées et leurs substitutions par variables d'environnement.
- [`memory-behavior-spec.md`](memory-behavior-spec.md) — comportement de l'agent : quand et comment écrire/valider/contredire/lire la mémoire, et le rôle des commandes d'ingestion.
- [`commands.md`](commands.md) — commandes `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns` : ingestion contrôlée d'un document, cartographie du code, revue de la santé de la mémoire, bootstrap initial du projet, et analyse de patterns.

## Liens vers la racine du dépôt

- [`../../README.md`](../../README.md) — README du bundle.

## README des composants

- [`../../wpm-mcp-server/README.md`](../../wpm-mcp-server/README.md) — serveur MCP Python : installation et utilisation.
- [`../../wpm-opencode-plugin/README.md`](../../wpm-opencode-plugin/README.md) — plugin TypeScript pour OpenCode : compilation et utilisation.

## À propos des commandes installées

`wpm-commands/wpm-doc.md`, `wpm-commands/wpm-code.md`,
`wpm-commands/wpm-review.md`, `wpm-commands/wpm-bootstrap.md` et
`wpm-commands/wpm-patterns.md`
(à la racine du
dépôt) sont les versions fonctionnelles **installées** : copiées par
`install.sh` dans `~/.config/opencode/commands/` comme commandes slash
globales `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns`.
Ce sont des commandes **manuelles** :
elles ne s'exécutent que sur invocation explicite de l'utilisateur.

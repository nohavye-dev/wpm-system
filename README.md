# WPM — bundle de déploiement

Deux composants, déployés ensemble :

- `wpm-mcp-server/` — serveur MCP Python (SQLite + sqlite-vec). Source de vérité : scoring, décroissance (decay), expansion de graphe, les 10 outils.
- `wpm-opencode-plugin/` — plugin TypeScript pour OpenCode. Client léger : hooks déterministes (compaction, preuve d'exécution, revue en session inactive) qui appellent les outils du serveur au bon moment.

## Installation

`./install.sh` installe tout globalement en une étape :

- compile le plugin dans `~/.config/opencode/plugins/wpm-plugin/` (plugin global chargé automatiquement) ;
- crée un environnement virtuel géré dans `~/.local/share/wpm-system/venv` et y installe `wpm-mcp-server` (non éditable) ;
- copie `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns` dans `~/.config/opencode/commands/` (commandes slash globales) ;
- installe la commande `wpm` dans `~/.local/bin` (ou `$XDG_BIN_HOME`).

(les chemins ci-dessus honorent $XDG_CONFIG_HOME / $XDG_DATA_HOME / $XDG_BIN_HOME lorsqu'ils sont définis)

`./install.sh uninstall` (ou `wpm uninstall`) supprime tout globalement : plugin, venv, commandes, binaire `wpm`, dépendances.

## Activation par projet

Le plugin est global mais inerte : il ne s'active que si un
`wpm.config.json` existe à la racine du projet (aucune entrée `mcp` dans
`opencode.json`, aucune copie par projet).

```bash
wpm enable           # écrit wpm.config.json (db_path ".wpm/wpm.db" s'il est absent), crée le dossier de la base + la base (schéma), l'ajoute au .gitignore
wpm enable .memory   # dossier de base personnalisé → db_path ".memory/wpm.db"
                     # la base doit vivre dans le projet : refuse un db_path qui en sort (chemin absolu externe, ou relatif avec « .. »)
wpm disable          # supprime wpm.config.json, conserve les données (db_path) sur place, suggère la commande de ré-activation
wpm uninstall        # suppression globale complète (demande confirmation) ; --force pour sauter la confirmation
```

**Redémarrez OpenCode** après `install.sh`, `wpm enable` ou `wpm disable` — la configuration est lue une seule fois au démarrage.

Lorsqu'il est actif, le plugin expose les 10 outils de mémoire directement à
l'LLM (`store_entry`, `query_context`, `validate_entry`, `contradict_entry`,
`link_entries`, `get_memory_stats`, `pin_entry`, `deprecate_entry`,
`restore_entry`, `list_entries`) et exécute ses 3 hooks (compaction,
`tool.execute.after`, `session.idle`).

## Démarrage rapide

1. `./install.sh`
2. `wpm enable` à la racine du projet
3. Redémarrez OpenCode

## Documentation

La documentation détaillée vit dans [`docs/fr/`](docs/fr/index.md) :

- [`docs/fr/setup.md`](docs/fr/setup.md) — guide d'activation complet (installation, `wpm`, redémarrage).
- [`docs/fr/wpm-config-reference.md`](docs/fr/wpm-config-reference.md) — schéma `wpm.config.json` et constantes du serveur (substituables par variables d'environnement).
- [`docs/fr/memory-behavior-spec.md`](docs/fr/memory-behavior-spec.md) — comportement de l'agent : quand/comment écrire, valider, contredire, lire la mémoire.
- [`docs/fr/commands.md`](docs/fr/commands.md) — commandes `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns`.
- [`wpm-mcp-server/README.md`](wpm-mcp-server/README.md) — le serveur.
- [`wpm-opencode-plugin/README.md`](wpm-opencode-plugin/README.md) — le plugin.

## Limitations

- Le document de spécification complet (modèle de poids, formules de récupération, working-scope) reste à conserver à côté du bundle ; les commentaires du code renvoient à ses sections.
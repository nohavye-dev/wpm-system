# WPM — Weighted Persistent Memory

Un **serveur MCP pur** (Python, SQLite + sqlite-vec) qui donne à votre agent
une mémoire persistante **pondérée par la confiance** : les décisions
d'architecture, conventions et patterns découverts dans une session ne sont
pas perdus à la suivante.

Composant unique :

- `wpm-mcp-server/` — serveur MCP Python. Source de vérité : scoring,
  décroissance (decay), expansion de graphe, les 11 outils (`store_entry`,
  `query_context`, `validate_entry`, `contradict_entry`, `link_entries`,
  `get_memory_stats`, `pin_entry`, `deprecate_entry`, `restore_entry`,
  `list_entries`, `record_execution`), 3 resources (`wpm://project-rules`,
  `wpm://memory-rules`, `wpm://verification-commands`), 6 prompts
  (`persist`, `audit`, `learn`, `map`, `bootstrap`,
  `patterns`) et les règles d'usage dans `initialize.instructions`.

Plus de plugin OpenCode, plus de hooks `experimental.*` : tout est exprimé
avec des primitives MCP standard, donc le serveur fonctionne sur **n'importe
quel host MCP** (OpenCode, Claude Desktop, etc.).

## Installation

`./install.sh` installe tout globalement en une étape :

- crée un environnement virtuel géré dans `~/.local/share/wpm-system/venv` et y installe `wpm-mcp-server` (non éditable) ;
- pré-télécharge le modèle d'embedding (~80 MB) pour un premier démarrage hors-ligne ;
- installe la commande `wpm` dans `~/.local/bin` (ou `$XDG_BIN_HOME`).

(les chemins ci-dessus honorent $XDG_CONFIG_HOME / $XDG_DATA_HOME / $XDG_BIN_HOME lorsqu'ils sont définis)

`./install.sh uninstall` (ou `wpm uninstall`) supprime tout globalement : venv, binaire `wpm`, données.

## Activation par projet

Le serveur est global mais **inerte par projet** : il ne s'active que si un
`wpm.config.json` existe dans le projet (ou si `WPM_DB_PATH` est défini).
L'activation = ce fichier à la racine du projet. Le serveur est enregistré
**une fois** dans le host (globalement), avec un répertoire de travail ancré
au projet (`cwd: "."`).

```bash
wpm enable                      # écrit wpm.config.json (db_path ".wpm/wpm.db" s'il est absent), crée le dossier de la base + la base (schéma), l'ajoute au .gitignore (demande confirmation ; --yes pour sauter)
wpm enable .memory              # dossier de base personnalisé → db_path ".memory/wpm.db"
                                 # la base doit vivre dans le projet : refuse un db_path qui en sort
wpm disable                     # supprime wpm.config.json, conserve les données (db_path) sur place
wpm uninstall                   # suppression globale complète (demande confirmation) ; --force pour sauter la confirmation
```

Enregistrez le serveur une fois dans la configuration globale d'opencode
(`~/.config/opencode/opencode.json`) :

```json
{
  "mcp": {
    "wpm": {
      "type": "local",
      "command": ["~/.local/share/wpm-system/venv/bin/python", "-m", "wpm_mcp_server"],
      "cwd": "."
    }
  },
  "permission": {
    "wpm_*": "allow"
  }
}
```

`cwd: "."` lance le serveur avec comme répertoire de travail le **projet
ouvert** ; il y cherche `wpm.config.json` automatiquement (projet activé) ou
reste inerte (projet sans config).

Le bloc `permission` est spécifique à opencode : il permet à l'agent de
persister la mémoire (outils `wpm_*`) **même en mode plan**.

**Redémarrez votre host** après `install.sh`, `wpm enable`, `wpm disable` ou
toute modification de la config du host — la configuration est lue une seule
fois au démarrage.

Lorsqu'il est actif, le serveur expose les 11 outils de mémoire à l'LLM et
oriente son comportement : `initialize.instructions` embarque les règles
d'usage (l'agent doit appeler `query_context` en préambule des réponses
substantielle et lire `wpm://project-rules` au démarrage de session), la
resource `wpm://project-rules` est recomputée depuis la mémoire et invalidée
à chaque mutation, et les workflows `learn`, `map`, `audit`,
`bootstrap` et `patterns` sont des prompts MCP.

## Démarrage rapide

1. `./install.sh`
2. Enregistrez le serveur `wpm` dans `~/.config/opencode/opencode.json` (bloc `mcp` + `cwd: "."` ci-dessus)
3. `wpm enable` à la racine du projet
4. Redémarrez votre host

## Documentation

La documentation détaillée vit dans [`docs/fr/`](docs/fr/index.md) :

- [`docs/fr/setup.md`](docs/fr/setup.md) — guide d'activation complet (installation, enregistrement du serveur, `wpm`, redémarrage).
- [`docs/fr/wpm-config-reference.md`](docs/fr/wpm-config-reference.md) — schéma `wpm.config.json` et substitutions par variables d'environnement.
- [`docs/fr/memory-behavior-spec.md`](docs/fr/memory-behavior-spec.md) — comportement de l'agent : quand/comment écrire, valider, contredire, lire la mémoire.
- [`docs/fr/commands.md`](docs/fr/commands.md) — workflows `learn`, `map`, `audit`, `bootstrap` et `patterns` (prompts MCP).
- [`wpm-mcp-server/README.md`](wpm-mcp-server/README.md) — le serveur MCP.

## Limitations

- Le document de spécification complet (modèle de poids, formules de récupération, working-scope) reste à conserver à côté du bundle ; les commentaires du code renvoient à ses sections.
- Sans host, pas de push déterministe : la perte des hooks du plugin (compaction, auto-capture, nudge) est compensée par la discipline write-as-you-go (dans les règles) + le prompt `persist`.

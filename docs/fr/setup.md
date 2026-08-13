# WPM — installation et activation par projet

## Principe

WPM est un **serveur MCP pur** : plus de plugin OpenCode, plus de hooks. Le
serveur Python (`wpm-mcp-server`) expose la mémoire (11 outils), les règles
d'usage (dans `initialize.instructions` + resource `wpm://memory-rules`), les
règles du projet (resource `wpm://project-rules`) et les workflows
(prompts `wpm-persist`, `wpm-review`, `wpm-doc`, `wpm-code`, `wpm-bootstrap`,
`wpm-patterns`) via le protocole MCP standard. Il fonctionne avec **n'importe
quel host MCP**.

Le serveur est **inerte par projet** : sans `wpm.config.json` (ou sans
`WPM_DB_PATH`), il démarre, liste ses outils, mais chaque appel renvoie une
erreur claire « wpm is not activated in this project ». L'activation d'un
projet = un `wpm.config.json` à sa racine + une entrée `mcp` dans la
configuration de votre host qui pointe vers ce fichier.

- `wpm.config.json` **absent** + pas de `WPM_DB_PATH` → serveur inerte.
- `wpm.config.json` **présent** → les 11 outils mémoire sont exposés à
  l'LLM : `store_entry`, `query_context`, `validate_entry`,
  `contradict_entry`, `link_entries`, `get_memory_stats`, `pin_entry`,
  `deprecate_entry`, `restore_entry`, `list_entries`, `record_execution`.

## Installation globale

Depuis la racine du dépôt :

```bash
./install.sh
```

Ce que fait `install.sh` :
1. Crée un venv géré à `~/.local/share/wpm-system/venv` et y installe
   `wpm-mcp-server` (non éditable) via `pip install`
2. Pré-télécharge le modèle d'embedding (~80 MB) pour un premier démarrage
   hors-ligne
3. Installe la commande `wpm` dans `~/.local/bin` (ou `$XDG_BIN_HOME`)

## Activer sur un projet

Depuis la racine du projet concerné :

```bash
wpm enable
```

`wpm enable` **n'écrit rien** : il affiche le snippet `mcp` prêt à coller
dans votre configuration de host (avec le chemin du venv et
`WPM_CONFIG_PATH` pointant vers le `wpm.config.json` du projet).

Pour aussi écrire le fichier de config (avec confirmation) :

```bash
wpm enable --write-config
```

Ce que fait `--write-config` :
1. Confirme l'écriture de `wpm.config.json` à la racine du projet
   (`--yes` pour sauter la confirmation) ; `db_path` par défaut `.wpm/wpm.db`
   s'il est absent — les clés existantes sont préservées
2. Crée le répertoire de la base et l'ajoute au `.gitignore` du projet
3. Crée la base de données (schéma SQLite seul — le modèle d'embedding n'est
   pas téléchargé ici)
4. Refuse un `db_path` qui sort du projet (chemin absolu externe, ou relatif
   avec `..`) — la base doit toujours vivre dans le répertoire du projet ;
   le serveur refuse aussi de démarrer dans ce cas

### Dossier de base personnalisé

Pour stocker la base dans un sous-dossier autre que `.wpm/` :

```bash
wpm enable .memory --write-config   # → db_path ".memory/wpm.db"
```

Le `db_dir` ne définit le chemin que lors d'une **première activation** : si
un `db_path` existe déjà dans `wpm.config.json`, il est préservé et `db_dir`
est ignoré.

### Brancher le serveur dans le host

Collez le snippet affiché par `wpm enable`. Pour opencode (projet ou global) :

```json
{
  "mcp": {
    "wpm": {
      "type": "local",
      "command": ["~/.local/share/wpm-system/venv/bin/python", "-m", "wpm_mcp_server"],
      "environment": {
        "WPM_CONFIG_PATH": "/abs/path/to/project/wpm.config.json"
      }
    }
  },
  "permission": {
    "wpm_*": "allow"
  }
}
```

Le bloc `permission` est spécifique à opencode : il permet à l'agent de
persister la mémoire (outils `wpm_*`) **même en mode plan**. Les autres
hosts (Claude Desktop, etc.) acceptent le même bloc `mcp` et ignorent
`permission`.

Redémarrez ensuite votre host : les serveurs MCP sont configurés une seule
fois au démarrage.

> **Note** : `WPM_CONFIG_PATH` rend l'activation indépendante du répertoire
> de travail avec lequel le host lance le serveur — un `db_path` relatif
> dans la config est résolu par rapport au répertoire du fichier, pas par
> rapport au cwd du host.

## Désactiver sur un projet

```bash
wpm disable
```

Supprime `wpm.config.json` du projet. Les données (`.wpm/wpm.db`) sont
**conservées**. Retirez ensuite l'entrée `mcp` « wpm » de votre
configuration de host (elle reste active sinon) et redémarrez le host.

## Désinstallation complète

```bash
wpm uninstall            # demande confirmation (abandon par défaut)
wpm uninstall --force    # pas de confirmation (scripts/CI)
```

ou, depuis la racine du dépôt :

```bash
./install.sh uninstall
```

`install.sh uninstall` délègue à la commande `wpm uninstall` si le binaire
`wpm` existe, sinon au script du bundle `scripts/wpm uninstall` ; il ne
signale « non installé » que si ce script est lui aussi absent. Supprime le
venv serveur, les commandes globales et la commande `wpm`. Retirez ensuite
les entrées `mcp` « wpm » de vos configurations de host.

## `wpm search` — interroger la mémoire depuis le terminal

```bash
wpm search "constructor parameter object pattern"
```

Recherche les entrées pertinentes via l'API `query_context` et affiche les
résultats formatés pour un humain. Fonctionne uniquement dans un projet
où `wpm enable --write-config` a été exécuté.

Options :
```bash
wpm search --json "query"          # Sortie JSON brute (pour piping vers jq)
wpm search --min-confidence 0.5 "query"  # Filtrer par seuil de confiance
```

L'affichage texte montre pour chaque entrée : l'ID tronqué, le type, la
confiance, le score, le statut (`active`/`pinned`/`deprecated`), et un
aperçu du contenu.

## Vérifier

- Dans votre host, les outils `store_entry`, `query_context`,
  `validate_entry`, `contradict_entry`, `link_entries`, `get_memory_stats`,
  `pin_entry`, `deprecate_entry`, `restore_entry`, `list_entries`,
  `record_execution` sont visibles par l'LLM.
- La resource `wpm://project-rules` doit contenir un bloc `<project-rules>`
  (vide si la mémoire est vide) ; `initialize.instructions` embarque les
  règles d'usage de la mémoire.
- Sans activation, les outils répondent « wpm is not activated in this
  project: run 'wpm enable' ... ».

## Règles et limites

- Toutes les clés documentées de `wpm.config.json` sont éditables à la main :
  `db_path` (choix du dossier/nom de la base), `confidence_threshold`
  (seuil d'injection des project-rules), `verification_command_patterns`
  (regex ajoutées pour `record_execution`), `domain` (tuning avancé du
  scoring). `wpm enable --write-config` les préserve et ne remplit que les
  clés absentes.
- Après toute modification de la config de host (`opencode.json`,
  `wpm.config.json`, `install.sh`), **redémarrez votre host** : la config
  n'est chargée qu'une fois au démarrage.
- Le serveur se lance avec `python -m wpm_mcp_server` (interpréteur du venv
  `~/.local/share/wpm-system/venv/bin/python`) et lit `WPM_CONFIG_PATH`
  (défaut `wpm.config.json` dans le cwd). `WPM_DB_PATH` passe devant
  `db_path` ; `WPM_EMBEDDING_MODEL` change le modèle d'embedding.

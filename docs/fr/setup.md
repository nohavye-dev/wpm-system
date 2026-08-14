# WPM — installation et activation par projet

## Principe

WPM est un **serveur MCP pur** : plus de plugin OpenCode, plus de hooks. Le
serveur Python (`wpm-mcp-server`) expose la mémoire (11 outils), les règles
d'usage (dans `initialize.instructions` + resource `wpm://memory-rules`), les
règles du projet (resource `wpm://project-rules`) et les workflows
(prompts `persist`, `audit`, `learn`, `map`, `bootstrap`,
`patterns`) via le protocole MCP standard. Il fonctionne avec **n'importe
quel host MCP**.

Le serveur est **inerte par projet** : sans `wpm.config.json` (ou sans
`WPM_DB_PATH`), il démarre, liste ses outils, mais chaque appel renvoie une
erreur claire « wpm is not activated in this project ». L'activation d'un
projet = un `wpm.config.json` à sa racine. Le serveur est enregistré **une
seule fois** dans le host (globalement), avec un répertoire de travail ancré
au projet (`cwd: "."` pour opencode) : il détecte alors le `wpm.config.json`
du projet automatiquement.

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

`wpm enable` écrit `wpm.config.json` à la racine du projet (avec
confirmation ; `--yes` pour sauter la confirmation) :

1. `db_path` par défaut `.wpm/wpm.db` s'il est absent — les clés existantes
   sont préservées
2. Crée le répertoire de la base et l'ajoute au `.gitignore` du projet
3. Crée la base de données (schéma SQLite seul — le modèle d'embedding n'est
   pas téléchargé ici)
4. Refuse un `db_path` qui sort du projet (chemin absolu externe, ou relatif
   avec `..`) — la base doit toujours vivre dans le répertoire du projet ;
   le serveur refuse aussi de démarrer dans ce cas

### Dossier de base personnalisé

Pour stocker la base dans un sous-dossier autre que `.wpm/` :

```bash
wpm enable .memory   # → db_path ".memory/wpm.db"
```

Le `db_dir` ne définit le chemin que lors d'une **première activation** : si
un `db_path` existe déjà dans `wpm.config.json`, il est préservé et `db_dir`
est ignoré.

## Enregistrer le serveur MCP (une fois, global)

Après l'installation, enregistrez le serveur dans la configuration globale
d'opencode (`~/.config/opencode/opencode.json`) :

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
ouvert** (résolu depuis le workspace opencode). Le serveur y cherche alors
`wpm.config.json` automatiquement : un projet avec config est activé, un
projet sans config reste inerte.

Le bloc `permission` est spécifique à opencode : il permet à l'agent de
persister la mémoire (outils `wpm_*`) **même en mode plan**.

Redémarrez ensuite opencode : les serveurs MCP sont configurés une seule
fois au démarrage.

## Désactiver sur un projet

```bash
wpm disable
```

Supprime `wpm.config.json` du projet. Les données (`.wpm/wpm.db`) sont
**conservées**. L'entrée `mcp` globale reste en place — le serveur devient
simplement inerte pour ce projet (plus de config trouvée).

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
venv serveur et la commande `wpm`. Retirez ensuite l'entrée `mcp` « wpm »
de votre configuration globale d'opencode.

## `wpm search` — interroger la mémoire depuis le terminal

```bash
wpm search "constructor parameter object pattern"
```

Recherche les entrées pertinentes via l'API `query_context` et affiche les
résultats formatés pour un humain. Fonctionne uniquement dans un projet
où `wpm enable` a été exécuté.

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
  scoring). `wpm enable` les préserve et ne remplit que les clés absentes.
- Après toute modification de la config de host (`opencode.json`,
  `wpm.config.json`, `install.sh`), **redémarrez votre host** : la config
  n'est chargée qu'une fois au démarrage.
- Le serveur se lance avec `python -m wpm_mcp_server` (interpréteur du venv
  `~/.local/share/wpm-system/venv/bin/python`) et cherche `wpm.config.json`
  dans son répertoire de travail (le projet, via `cwd: "."`). `WPM_CONFIG_PATH`
  reste disponible comme override explicite ; `WPM_DB_PATH` passe devant
  `db_path` ; `WPM_EMBEDDING_MODEL` change le modèle d'embedding.

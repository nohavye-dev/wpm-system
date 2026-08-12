# WPM — installation et activation par projet

## Principe

Le bundle mémoire se compose d'un plugin OpenCode **global** et d'un serveur MCP installé dans un venv dédié. Le plugin est global mais **inerte par projet** : à chaque démarrage d'OpenCode, il vérifie la présence de `wpm.config.json` à la racine du projet courant.

- `wpm.config.json` **absent** → le plugin ne fait rien : aucun outil exposé, aucun hook, aucun serveur lancé.
- `wpm.config.json` **présent** → le plugin s'active et expose les 10 outils mémoire directement à l'LLM : `store_entry`, `query_context`, `validate_entry`, `contradict_entry`, `link_entries`, `get_memory_stats`, `pin_entry`, `deprecate_entry`, `restore_entry`, `list_entries`.

L'activation se résume à la présence de `wpm.config.json` à la racine du projet : aucune entrée MCP dans `opencode.json`, aucune copie du plugin par projet. Aucun projet n'est affecté sans cette activation.

## Installation globale

Depuis la racine du dépôt :

```bash
./install.sh
```

Ce que fait `install.sh` :
1. Construit le plugin compilé
2. Copie le plugin dans `~/.config/opencode/plugins/wpm-plugin/` — plugin **global**, auto-chargé par OpenCode
3. Écrit le shim `~/.config/opencode/plugins/wpm-plugin.ts` qui permet à OpenCode de découvrir le plugin (le dossier seul ne suffit pas)
4. Crée un venv géré à `~/.local/share/wpm-system/venv` et y installe `wpm-mcp-server` (non éditable) via `pip install`
5. Copie `/wpm-doc`, `/wpm-code`, `/wpm-review`, `/wpm-bootstrap` et `/wpm-patterns` dans `~/.config/opencode/commands/` — commandes globales
6. Installe la commande `wpm` dans `~/.local/bin` (ou `$XDG_BIN_HOME`)

Redémarre ensuite opencode : la config n'est chargée qu'une seule fois au démarrage.

> **Note** : un `opencode.json` de projet contenant `"plugin": []` désactive
> le chargement du plugin global. Retirez ce champ (ou listez `wpm-plugin`
> dedans) pour que le plugin soit chargé.

## Activer sur un projet

Depuis la racine du projet concerné :

```bash
wpm enable
```

`wpm` (weighted persistent memory) agit toujours sur le **répertoire courant** — pas d'argument projet. Ce que fait `wpm enable` :
1. Lit `wpm.config.json` s'il existe — toutes les clés existantes sont préservées (dont un `db_path` personnalisé)
2. Écrit `wpm.config.json` à la racine du projet ; `db_path` par défaut `.wpm/wpm.db` (chemin relatif) s'il est absent
3. Crée le répertoire de la base et l'ajoute au `.gitignore` du projet
4. Crée la base de données (schéma SQLite seul — le modèle d'embedding n'est pas téléchargé ici)
5. Refuse un `db_path` qui sort du projet (chemin absolu externe, ou relatif avec `..`) — la base doit toujours vivre dans le répertoire du projet ; le serveur refuse aussi de démarrer dans ce cas

### Dossier de base personnalisé

Pour stocker la base dans un sous-dossier autre que `.wpm/` :

```bash
wpm enable .memory   # → db_path ".memory/wpm.db"
```

Le `db_dir` ne définit le chemin que lors d'une **première activation** : si un `db_path` existe déjà dans `wpm.config.json`, il est préservé et `db_dir` est ignoré.

Redémarre ensuite opencode : le plugin détecte `wpm.config.json` et active les outils mémoire sur ce projet.

## Désactiver sur un projet

```bash
wpm disable
```

Supprime `wpm.config.json` du projet. Les données (`.wpm/wpm.db`) sont **conservées** — la commande affiche le chemin de la base et la commande de ré-activation (`wpm enable` ou `wpm enable <db_dir>`). Redémarre opencode.

## Désinstallation complète

```bash
wpm uninstall            # demande confirmation (abandon par défaut)
wpm uninstall --force    # pas de confirmation (scripts/CI)
```

ou, depuis la racine du dépôt :

```bash
./install.sh uninstall
```

`install.sh uninstall` délègue à la commande `wpm uninstall` si le binaire `wpm` existe, sinon au script du bundle `scripts/wpm uninstall` ; il ne signale « non installé » que si ce script est lui aussi absent. Supprime le plugin global, le venv serveur, les commandes globales et la commande `wpm`. Redémarre opencode.

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

- Dans opencode, les outils `store_entry`, `query_context`, `validate_entry`, `contradict_entry`, `link_entries`, `get_memory_stats`, `pin_entry`, `deprecate_entry`, `restore_entry`, `list_entries` sont visibles par l'LLM (outils exposés par le plugin).
- Consulte le journal du plugin pour confirmer l'activation ou l'inertie sur le projet courant.

## Règles et limites

- Toutes les clés documentées de `wpm.config.json` sont éditables à la main : `db_path` (choix du dossier/nom de la base), `confidence_threshold`, `idle_nudge` (relance opt-in en session inactive), `domain` (tuning avancé du scoring). `wpm enable` les préserve et ne remplit que les clés absentes.
- Après `wpm enable`, `wpm disable` ou `install.sh`, **redémarre opencode** : la config n'est chargée qu'une fois au démarrage.
- Les constantes de lancement du serveur sont fixées dans le plugin (interpréteur du venv `~/.local/share/wpm-system/venv/bin/python`, arguments `["-m","wpm_mcp_server"]`, répertoire de travail = racine du projet). Seul l'interpréteur est surchargeable (`WPM_MCP_COMMAND`). `confidence_threshold` (défaut 0.5) se règle via la clé `confidence_threshold` de `wpm.config.json`, surchargée par `WPM_CONFIDENCE_THRESHOLD`. `idle_nudge` (défaut `false`) se règle via la clé `idle_nudge`, surchargée par `WPM_IDLE_NUDGE`. `WPM_DB_PATH` passe devant `db_path` côté serveur.

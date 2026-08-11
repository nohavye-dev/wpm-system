# WPM — installation et activation par projet

## Principe

Le bundle mémoire se compose d'un plugin OpenCode **global** et d'un serveur MCP installé dans un venv dédié. Le plugin est global mais **inerte par projet** : à chaque démarrage d'OpenCode, il vérifie la présence de `wpm.config.json` à la racine du projet courant.

- `wpm.config.json` **absent** → le plugin ne fait rien : aucun outil exposé, aucun hook, aucun serveur lancé.
- `wpm.config.json` **présent** → le plugin s'active et expose les 5 outils mémoire directement à l'LLM : `store_entry`, `query_context`, `validate_entry`, `contradict_entry`, `link_entries`.

L'activation se résume à la présence de `wpm.config.json` à la racine du projet : aucune entrée MCP dans `opencode.json`, aucune copie du plugin par projet. Aucun projet n'est affecté sans cette activation.

## Installation globale

Depuis la racine du dépôt :

```bash
./install.sh
```

Ce que fait `install.sh` :
1. Construit le plugin compilé
2. Copie le plugin dans `~/.config/opencode/plugins/wpm-plugin/` — plugin **global**, auto-chargé par OpenCode
3. Crée un venv géré à `~/.local/share/wpm-system/venv` et y installe `wpm-mcp-server` (non éditable) via `pip install`
4. Copie `/wpm-doc` et `/wpm-code` dans `~/.config/opencode/commands/` — commandes globales
5. Installe la commande `wpm` dans `~/.local/bin` (ou `$XDG_BIN_HOME`)

Redémarre ensuite opencode : la config n'est chargée qu'une seule fois au démarrage.

## Activer sur un projet

Depuis la racine du projet concerné :

```bash
wpm enable
```

`wpm` (weighted persistent memory) agit toujours sur le **répertoire courant** — pas d'argument projet. Ce que fait `wpm enable` :
1. Lit `wpm.config.json` s'il existe — toutes les clés existantes sont préservées (dont un `db_path` personnalisé)
2. Écrit `wpm.config.json` à la racine du projet ; `db_path` par défaut `.wpm/wpm.db` (chemin relatif) s'il est absent
3. Crée le répertoire de la base et l'ajoute au `.gitignore` du projet
4. Refuse un `db_path` qui sort du projet (chemin absolu externe, ou relatif avec `..`) — la base doit toujours vivre dans le répertoire du projet ; le serveur refuse aussi de démarrer dans ce cas

Redémarre ensuite opencode : le plugin détecte `wpm.config.json` et active les outils mémoire sur ce projet.

## Désactiver sur un projet

```bash
wpm disable
```

Supprime `wpm.config.json` du projet. Les données (`.wpm/wpm.db`) sont **conservées** — réactive à tout moment avec `wpm enable`. Redémarre opencode.

## Désinstallation complète

```bash
wpm uninstall
```

ou, depuis la racine du dépôt :

```bash
./install.sh uninstall
```

`install.sh uninstall` délègue à la commande `wpm uninstall` si le binaire `wpm` existe, sinon au script du bundle `scripts/wpm.sh uninstall` ; il ne signale « non installé » que si ce script est lui aussi absent. Supprime le plugin global, le venv serveur, les commandes globales et la commande `wpm`. Redémarre opencode.

## Vérifier

- Dans opencode, les outils `store_entry`, `query_context`, `validate_entry`, `contradict_entry`, `link_entries` sont visibles par l'LLM (outils exposés par le plugin).
- Consulte le journal du plugin pour confirmer l'activation ou l'inertie sur le projet courant.

## Règles et limites

- Toutes les clés documentées de `wpm.config.json` sont éditables à la main : `db_path` (choix du dossier/nom de la base), `confidence_threshold`, `idle_nudge` (relance opt-in en session inactive), `domain` (tuning avancé du scoring). `wpm enable` les préserve et ne remplit que les clés absentes.
- Après `wpm enable`, `wpm disable` ou `install.sh`, **redémarre opencode** : la config n'est chargée qu'une fois au démarrage.
- Les constantes de lancement du serveur sont fixées dans le plugin (interpréteur du venv `~/.local/share/wpm-system/venv/bin/python`, arguments `["-m","wpm_mcp_server"]`, répertoire de travail = racine du projet). Seul l'interpréteur est surchargeable (`WPM_MCP_COMMAND`). `confidence_threshold` (défaut 0.5) se règle via la clé `confidence_threshold` de `wpm.config.json`, surchargée par `WPM_CONFIDENCE_THRESHOLD`. `idle_nudge` (défaut `false`) se règle via la clé `idle_nudge`, surchargée par `WPM_IDLE_NUDGE`. `WPM_DB_PATH` passe devant `db_path` côté serveur.

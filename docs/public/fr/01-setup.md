# Installation et activation

WPM s'installe une fois (globalement), puis s'active projet par projet. Le
plugin OpenCode est installé **par défaut** et enregistre le serveur MCP à
votre place : aucune configuration OpenCode manuelle n'est nécessaire.

---

## 1. Installation globale

```bash
curl -fsSL https://raw.githubusercontent.com/nohavye-dev/wpm-system/main/install.sh | bash
```

Ce que fait le script :

1. crée un environnement Python dédié (`~/.local/share/wpm-system/venv`) et
   y installe le serveur ;
2. pré-télécharge le modèle d'embedding (~120 MB) pour un premier démarrage
   hors-ligne ;
3. installe la commande `wpm` (`~/.local/bin/wpm`) ;
4. installe le plugin OpenCode dans `~/.config/opencode/plugins/` (global).

> Les chemins honorent `$XDG_DATA_HOME` / `$XDG_BIN_HOME` /
> `$XDG_CONFIG_HOME` s'ils sont définis.

---

## 2. Activer un projet

Depuis la racine du projet concerné :

```bash
wpm enable
```

`wpm enable` écrit `wpm.config.json` à la racine du projet (confirmation ;
`--yes` pour la sauter) :

- `db_path` par défaut `.wpm/wpm.db` s'il est absent (les clés existantes
  sont préservées) ;
- crée le dossier de la base et l'ajoute au `.gitignore` ;
- crée la base de données ;
- refuse un `db_path` qui sort du projet (chemin absolu externe, ou relatif
  avec `..`).

Pour un dossier de base personnalisé :

```bash
wpm enable .memory   # → db_path ".memory/wpm.db"
```

> Le `db_dir` ne sert que lors d'une **première** activation : si un
> `db_path` existe déjà, il est préservé.

---

## 3. Ce qui se passe ensuite

Au prochain démarrage d'OpenCode sur ce projet, le plugin détecte le
`wpm.config.json` et :

1. enregistre le serveur MCP `wpm` (outils `wpm_store_entry`,
   `wpm_query_context`, …) ;
2. accorde la permission `wpm_*` pour que l'agent puisse écrire la mémoire,
   même en mode plan.

**Redémarrez OpenCode** après `wpm enable` (ou `wpm disable`) : la
configuration n'est lue qu'une fois au démarrage.

---

## 4. Vérifier que ça marche

- Dans OpenCode, l'agent doit voir les outils `wpm_*`.
- Depuis le terminal, dans le projet activé :

```bash
wpm search "nom d'un sujet"      # interroge la mémoire
```

Sans activation, les outils répondent « wpm is not activated in this
project ».

---

## 5. Désactiver / désinstaller

```bash
wpm disable      # retire wpm.config.json (les données sont conservées)
wpm uninstall    # suppression globale complète (venv, binaire, plugin) ; --force pour sauter la confirmation
```

---

## Pour les curieux — comment le plugin enregistre le serveur

C'est le hook `config` du plugin qui, au chargement, injecte dans la
configuration d'OpenCode une entrée `mcp.wpm` pointant vers
`python -m wpm_mcp_server` avec `WPM_CONFIG_PATH` positionné sur le
`wpm.config.json` du projet, plus la permission `wpm_*`. Vous n'avez donc
**rien à déclarer** dans `opencode.json`. Pour brancher le serveur à la main
(hors OpenCode, ou pour comprendre), voir
[`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md).

# WPM — installation et activation par projet

## Principe

WPM est un **serveur MCP pur** : plus de plugin OpenCode obligatoire, plus de
hooks. Le serveur Python (`wpm-mcp-server`) expose la mémoire (11 outils),
les règles d'usage (dans `initialize.instructions` + resource
`wpm://memory-rules`), les règles du projet (resource `wpm://project-rules`)
et les workflows (prompts `persist`, `audit`, `learn`, `map`,
`bootstrap`, `patterns`) via le protocole MCP standard. Il fonctionne avec
**n'importe quel host MCP**.

Un **plugin OpenCode optionnel** (`wpm plugin install`) ré-injecte une carte
de règles compacte à chaque tour pour lutter contre la dilution du contexte
(voir [« Plugin optionnel (anti-dilution) »](#plugin-optionnel-anti-dilution)).
Le serveur reste entièrement autonome sans lui.

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
4. Met en place le plugin OpenCode optionnel
   (`~/.local/share/wpm-system/plugin.ts`, installé à la demande via
   `wpm plugin install`)

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

## Plugin optionnel (anti-dilution)

Le serveur MCP injecte les règles d'usage **une seule fois** en début de
session (`initialize.instructions`). En condition réelle, ces règles se
**diluent** à mesure que le contexte grossit : après quelques messages, l'agent
cesse de les suivre. Un serveur MCP pur ne peut pas y remédier — il ne voit
pas le contexte et ne peut pas ré-injecter d'instruction à chaque tour (limite
du protocole, documentée dans `new_spec/mcp-llm-behavior.md`).

Le plugin optionnel ajoute ce push déterministe, côté OpenCode uniquement :

```bash
wpm plugin install      # copie plugin.ts dans ~/.config/opencode/plugins/
wpm plugin uninstall    # le retire
```

Puis redémarrer OpenCode. Le plugin est **inerte par projet** : sans
`wpm.config.json` à la racine, aucun hook n'agit. Quand il est actif, il :

- injecte une carte de règles compacte (`<wpm-memory>`) dans le prompt
  système à **chaque tour** (`experimental.chat.system.transform`) ;
- ré-injecte la carte + un rappel « persiste tout fait durable non stocké »
  dans le résumé de **compaction** (`experimental.session.compacting`) ;
- journalise un rappel de fin de session (`session.idle`).

Le prérequis : le serveur doit être enregistré sous le nom `wpm` (les outils
sont alors `wpm_query_context`, `wpm_store_entry`, …). Si vous l'enregistrez
sous un autre nom, adaptez la constante `SERVER_NAME` en tête de `plugin.ts`.

> Les hooks `experimental.*` sont non stabilisés et peuvent être ignorés
> silencieusement selon la version d'OpenCode. Ils ont été vérifiés sur
> OpenCode 1.18.11.

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

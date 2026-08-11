# wpm-opencode-plugin

Plugin OpenCode compagnon pour le serveur MCP de mémoire persistante pondérée
(voir le document de spécification, section 11). Le plugin expose les 5
outils de mémoire du serveur (`store_entry`, `query_context`,
`validate_entry`, `contradict_entry`, `link_entries`) directement à l'LLM
via l'API du plugin, et fournit des hooks déterministes qu'un serveur MCP
sans état ne peut pas garantir à lui seul :

- **`experimental.session.compacting`** — injecte le contexte pertinent à
  haute confiance dans le résumé de compaction, et rappelle à l'agent de
  vider tout ce qui n'est pas persisté avant qu'il ne soit perdu.
- **`tool.execute.after`** — capture automatiquement les résultats des
  commandes de test/build comme preuves `execution_verified`, sans dépendre
  de l'agent pour les signaler.
- **`event` (`session.idle`)** — journalise un rappel de fin de session pour
  revoir l'état non persisté ; si `idle_nudge` est activé (voir
  « Activation par projet »), envoie une seule relance à l'agent pour les
  sessions qui ont réellement travaillé.
- **`experimental.chat.system.transform`** — injecte les règles d'usage de
  la mémoire (`MEMORY_USAGE_RULES` dans `src/rules.ts`, traduites de la
  spec `memory-behavior-spec.md`) dans le prompt système, pour que le
  comportement de l'agent soit guidé même sans lire le document.

Le plugin lance lui-même le serveur de mémoire Python comme sous-processus
(constantes fixes, voir « Activation par projet » ci-dessous), donc aucune
entrée `mcp` dans `opencode.json` n'est nécessaire. N'en ajoutez pas une :
le plugin expose déjà les 5 outils sous les mêmes noms, et deux expositions
du même nom entreraient en conflit.

## Avant de vous y fier en production

Le plugin est **global mais inerte par projet** : il ne s'active que si un
`wpm.config.json` existe à la racine du projet (`wpm enable` le crée).
Les hooks `experimental.*` sont instables selon les versions d'OpenCode et
peuvent être silencieusement ignorés si le nom du hook change ou devient non
pris en charge — OpenCode ne génère pas d'erreur sur les noms de hooks
inconnus. Après l'installation :

1. Vérifiez les noms de hooks actuels sur <https://opencode.ai/docs/plugins/>.
2. Dans un projet où `wpm.config.json` existe, confirmez que le hook se
   déclenche réellement en surveillant la sortie de journal du plugin
   (service `wpm-opencode-plugin`) pendant une vraie compaction.

## Installation

### 1. Compilation

```bash
npm install
npm run build
```

### 2. Chargement du plugin

**Global (défaut)** — `install.sh` à la racine du dépôt compile le plugin
et copie `dist/` dans `~/.config/opencode/plugins/wpm-plugin/`, où
OpenCode le charge automatiquement :

```bash
./install.sh
```

L'installation globale reste inerte jusqu'à ce qu'un projet possède un
`wpm.config.json` à sa racine, donc aucun projet n'est affecté par
défaut.

**Avancé — copie locale au projet** — copiez `dist/` dans un projet à la
place :

```bash
mkdir -p .opencode/plugins/wpm-plugin
cp -r dist package.json .opencode/plugins/wpm-plugin/
cd .opencode/plugins/wpm-plugin && npm install --omit=dev
```

**Ou via npm** (après publication sur un registre accessible à votre équipe) :

```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["wpm-opencode-plugin"]
}
```

### 3. Activation par projet

Le plugin lit `wpm.config.json` à la racine du projet — le **même
fichier** que lit le serveur Python (`wpm-mcp-server/README.md` contient
la référence complète). `wpm enable` l'écrit pour vous ; manuellement, il
ressemble à :

```json
{
  "db_path": ".wpm/wpm.db"
}
```

`db_path` est obligatoire (relatif, p. ex. `.wpm/wpm.db`) — le serveur
refuse de démarrer sans lui. C'est le serveur Python qui le lit, dans
`wpm.config.json` via son répertoire de travail (= racine du projet,
fixé par le plugin) ou via `WPM_DB_PATH` (voir le tableau ci-dessous) ;
le plugin ne lit jamais `db_path` ni `WPM_DB_PATH` — il se contente de
transmettre son `process.env` au sous-processus, et le serveur Python
les interprète lui-même. Les constantes de lancement sont fixées dans le
plugin : interpréteur
`~/.local/share/wpm-system/venv/bin/python` (chemin respectant
`XDG_DATA_HOME`), arguments `["-m", "wpm_mcp_server"]`, répertoire de
travail = racine du projet. Le seuil de confiance (défaut `0.5`) se règle
via la clé top-level `confidence_threshold` de `wpm.config.json`.
La relance en session inactive (`idle_nudge`, défaut `false`) est opt-in
via la clé top-level `idle_nudge` — le hook `session.idle` reste
passif (simple journal) tant qu'elle est désactivée.

Les variables d'environnement remplacent ces constantes lorsqu'elles sont
définies, pour une substitution locale rapide sans modifier le fichier :

| Variable | Remplace |
|---|---|
| `WPM_DB_PATH` | `db_path` |
| `WPM_MCP_COMMAND` | l'interpréteur Python |
| `WPM_CONFIDENCE_THRESHOLD` | le seuil de confiance (passe devant `confidence_threshold` du fichier) |
| `WPM_IDLE_NUDGE` | `idle_nudge` (parse `"true"`/`"false"`, passe devant la clé du fichier) |

Redémarrez OpenCode après l'activation ou la désactivation — la
configuration est lue une seule fois au démarrage.

## Personnalisation

- `VERIFICATION_COMMAND_PATTERNS` dans `src/index.ts` — ajustez quelles
  commandes shell comptent comme preuve forte (`execution_verified`) pour
  votre pile (actuellement pytest, dotnet test, npm test/build, cargo test,
  go test).
- `MEMORY_USAGE_RULES` dans `src/rules.ts` — les règles injectées dans le
  prompt système ; `IDLE_NUDGE_TEXT` y vit aussi, gardé volontairement
  court pour ne pas polluer le contexte.
- `idle_nudge` est une fonctionnalité **opt-in** (`wpm.config.json` ou
  `WPM_IDLE_NUDGE`). Sans activation, `session.idle` reste une simple
  entrée de journal passive.
- La requête de compaction (`"current task relevant decisions and
  conventions"`) est volontairement générique — réglez-la une fois que vous
  verrez de vraies charges utiles de compaction.

## Note d'architecture

Ce plugin est volontairement un **client léger** : il ne contient aucune
logique métier (pas de scoring, pas de décroissance, pas d'expansion de
graphe). Tout cela reste dans le serveur MCP Python et SQLite, comme défini
dans la spécification principale. Le plugin décide uniquement *quand* appeler
`store_entry` / `query_context` de manière déterministe — jamais *comment* le
score est calculé.

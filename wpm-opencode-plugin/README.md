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

### Commandes de preuve forte (`VERIFICATION_COMMAND_PATTERNS` + `verification_command_patterns`)

Les commandes shell dont le succès compte comme preuve `execution_verified`
(auto-capturées par le hook `tool.execute.after`, sans dépendre de l'agent)
sont définies par une liste **en dur, enrichie**, dans `src/index.ts` :
`VERIFICATION_COMMAND_PATTERNS` couvre les écosystèmes courants — tests
(pytest, npm/pnpm/yarn/bun test, dotnet/cargo/go test, make/mix/flutter/mvn/
gradle/sbt test, vitest, jest, deno test, tox, phpunit, rake test), builds
(npm/pnpm run build, yarn build, bun run build, dotnet/cargo/go build) et
vérificateurs (compileall, py_compile, bash -n, shellcheck, tsc --noEmit,
ruff check, mypy, eslint).

Pour votre pile, **ajoutez** des commandes via la clé
`verification_command_patterns` de `wpm.config.json` (liste de regex
ajoutées à la liste en dur — on ne peut pas en retirer) :

```json
{
  "db_path": ".wpm/wpm.db",
  "verification_command_patterns": ["\\bmy-custom-runner\\b"]
}
```

**Critère** : un pattern ne doit compter que si `exit 0` prouve que quelque
chose de *correct* est vérifié — les tests passent, le build compile, le
typecheck/lint passe. Chaque commande matchée déclenche `store_entry` +
validation : un pattern trop laxiste inonde la mémoire de bruit et
contredit la règle 1 (« reliability over completeness ») de
`MEMORY_USAGE_RULES`.

À ne **pas** ajouter :

| Commandes | Pourquoi non |
|---|---|
| `ls`, `cat`, `echo` | `exit 0` toujours vrai — aucun signal de correction |
| `grep` | observation, pas vérification — quasi jamais faux |
| `git status` / `git diff` | observation d'état, pas preuve de correction |

Pour une preuve ponctuelle qui a de la valeur (ex. un `grep` qui confirme
l'existence d'une fonction dans un fichier précis) : n'ajoutez **pas** la
commande à la liste — faites `validate_entry` avec `evidence_type:
"execution_verified"` et un `evidence_ref` pointant le log/la commande.
Même force de preuve, sans polluer l'auto-capture.

### Autres points réglables

- **Règles projet injectées** — le hook `experimental.chat.system.transform`
  injecte dans le prompt système les conventions/décisions à haute confiance
  (`≥ confidence_threshold`) récupérées en mémoire (`query_context`), dans
  un bloc `<project-rules>`. Résultat **déterministe** : les règles vivent
  en mémoire (évolutives) mais sont **garanties présentes à chaque tour**,
  sans que l'agent ait à penser à les requêter. Cache par session
  (budget borné, 800 tokens par requête, bloc plafonné) ; rafraîchi dès
  qu'une mutation mémoire (`store_entry`, `validate_entry`,
  `contradict_entry`, `link_entries`) a lieu dans la session.
- **Requête de compaction contextuelle** — le hook
  `experimental.session.compacting` dérive sa requête des **2 derniers
  messages utilisateur** de la session (signal topical) ; s'ils n'en
  portent pas (ex. « continue »), il élargit aux 5 derniers, puis retombe
  sur la requête générique `"current task relevant decisions and
  conventions"`. La récupération du contexte préservé est ainsi alignée sur
  le travail réel de la session.
- `MEMORY_USAGE_RULES` dans `src/rules.ts` — les règles injectées dans le
  prompt système ; `IDLE_NUDGE_TEXT` y vit aussi, gardé volontairement
  court pour ne pas polluer le contexte.
- `idle_nudge` est une fonctionnalité **opt-in** (`wpm.config.json` ou
  `WPM_IDLE_NUDGE`). Sans activation, `session.idle` reste une simple
  entrée de journal passive.

## Note d'architecture

Ce plugin est volontairement un **client léger** : il ne contient aucune
logique métier (pas de scoring, pas de décroissance, pas d'expansion de
graphe). Tout cela reste dans le serveur MCP Python et SQLite, comme défini
dans la spécification principale. Le plugin décide uniquement *quand* appeler
`store_entry` / `query_context` de manière déterministe — jamais *comment* le
score est calculé.

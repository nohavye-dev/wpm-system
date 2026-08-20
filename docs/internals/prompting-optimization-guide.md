# Guide d'optimisation du prompting — wpm-system

Objectif : faire sortir un maximum des 16 règles hors du bloc monolithique
`initialize.instructions` et les redistribuer vers le canal le plus fiable
pour leur moment d'usage réel. Le principe directeur : **une règle lue ou
déclenchée au bon moment vaut mieux qu'une règle lue une fois et espérée
pour toute la session.**

**Périmètre : OpenCode comme host unique.** L'objectif de portabilité
host-agnostic est abandonné — le projet exploite pleinement
`wpm-opencode-plugin/plugin.ts`, qui offre un canal qu'un serveur MCP pur
ne peut structurellement pas avoir : la visibilité sur **tous** les appels
d'outils de l'host (`read`, `grep`, `bash`...), pas seulement ceux de wpm.
Deux couches complémentaires :

- **Couche MCP** (déclarative, lue par le modèle) : `instructions`,
  descriptions de tools, schéma JSON, `tool_result`.
- **Couche plugin** (événementielle, déclenchée par l'host) :
  `experimental.chat.system.transform`, `experimental.session.compacting`,
  `tool.execute.before/after`, `event` (`session.idle`).

Fichiers concernés : `behavior.py` + `server.py` (couche MCP),
`wpm-opencode-plugin/plugin.ts` (couche plugin),
`scripts/wpm_metrics.py` (mesure).

---

## 1. Cartographie des 16 règles par canal cible

| # | Règle | Canal actuel | Canal cible | Action |
|---|-------|--------------|-------------|--------|
| 1 | Reliability over completeness | instructions | **instructions** | garder (principe de fond, aucun déclencheur) |
| 2 | Memory first | instructions (long) + description `query_context` | **description `query_context`** | supprimer la version longue des instructions, garder la golden rule courte |
| 3 | Contenu en anglais | instructions (long) + `_language_note` | **description `store_entry`** | idem : supprimer le paragraphe long des instructions |
| 4 | Write as you go | instructions (long) + description `store_entry` | **description `store_entry`** | supprimer la version longue des instructions |
| 5 | Dedup before writing | instructions (long) + description `store_entry` | **description `store_entry`** (déjà fait) | supprimer entièrement des instructions |
| 6 | Choix du `type` | instructions | **schéma JSON (`Literal`)** + description compacte | voir §3 |
| 7 | Choix du `source` | instructions | **schéma JSON (`Literal`)** + description compacte | voir §3 |
| 8 | Evidence hierarchy | instructions + description `validate_entry` | **description `validate_entry`/`contradict_entry`** (déjà fait) | supprimer des instructions |
| 9 | Never delete/overwrite | instructions + description `contradict_entry` | **description `contradict_entry`** (déjà fait) | supprimer des instructions |
| 10 | Lire direct_matches / related_context / conflicts | instructions | **`tool_result` de `query_context`** | voir §4.1 |
| 11 | Pin/deprecate avec parcimonie | instructions | **`tool_result` de `get_memory_stats`** | voir §4.2 |
| 12 | Links | instructions + description `link_entries` | **description `link_entries`** (déjà fait) | supprimer des instructions |
| 13 | Session discipline (fin de tâche) | instructions | **hook `event: session.idle`** (plugin) | voir §9.3 — déclenchement actif, plus seulement un log |
| 14 | Write memory anytime (plan mode) | instructions | **config `agent.plan.prompt` + `agent.plan.permission`** (plugin) | migré vers la config d'agent — l'exception plan mode est native, plus rappelée en instructions |
| 15 | Incremental ≠ bulk workflows | instructions | **description de chaque commande bulk** (plugin) | voir §5.2 |
| 16 | Record executions | instructions + description `record_execution` | **hook `tool.execute.after`** (plugin) | voir §9.1 — le plugin voit l'exécution shell, wpm non |

Résultat attendu : `_MEMORY_USAGE_RULES_TEMPLATE` passe d'environ 16
règles détaillées à 3 golden rules + règles 1 et 14 — soit une réduction
d'environ 70 % du bloc lu une fois en `instructions`, les règles 2, 13 et
16 étant désormais appliquées par le plugin au moment exact où elles
comptent plutôt que rappelées de mémoire.

---

## 2. Nouveau contenu pour `behavior.py`

Remplacer le corps « DETAILED RULES » (règles 1 à 16) par une version
réduite. Squelette proposé :

```text
<wpm-memory-rules>
You have access to the project's persistent weighted memory via the wpm MCP
server. Follow these rules every turn.

GOLDEN RULES — the three non-negotiable principles, in priority order:

1. MEMORY FIRST. [... inchangé ...]
2. WRITE AS YOU GO. [... inchangé ...]
3. PROOF BEFORE VALIDATION. [... inchangé ...]

STARTUP SEQUENCE — [... inchangé ...]

STANDING POLICIES (apply across all tools, not tied to a single call):

1. RELIABILITY OVER COMPLETENESS. A wrong or artificially boosted entry is
   worse than a missing one. Prefer an underpopulated memory to a
   polluted one.

2. WRITE MEMORY ANYTIME. Memory write tools MUST be used whenever a
   durable fact emerges. If the host blocks the write, retry immediately.

3. RECORD EXECUTIONS. After running a test, build, or lint command, call
   record_execution(command, succeeded, session_id) instead of doing
   store_entry + validate_entry by hand. Do not call it for trivial
   commands (ls, cat, echo, grep, git status/diff).

Every other rule (type/source selection, dedup, evidence hierarchy,
reading query results, pin/deprecate, links, English-only content,
end-of-session persistence) lives in the description of the relevant
tool — re-read it there at the moment of the decision.
</wpm-memory-rules>
```

Gain : moins de dilution sur les 3 golden rules + 3 politiques
transversales, qui sont justement celles qui ont le plus besoin de
rester présentes tout au long d'une longue session.

---

## 3. Règles 6 et 7 : passer de la prose au schéma

Aujourd'hui (`server.py`, lignes 147 et 240) :

```python
async def store_entry(ctx: Context, type: str, content: str, source: str) -> dict:
```

`type` et `source` sont de simples `str` — rien n'empêche structurellement
un modèle d'envoyer une valeur invalide ou mal choisie ; tout repose sur
la lecture de la description.

**Étape 1 — contrainte structurelle réelle**, indépendante du prompting :

```python
from typing import Literal

EntryType = Literal[
    "doc", "archi_decision", "insight", "convention",
    "bug_pattern", "execution_result",
]
EntrySource = Literal[
    "official_doc", "observed_code", "tool_execution", "agent_inference",
]

async def store_entry(
    ctx: Context, type: EntryType, content: str, source: EntrySource
) -> dict:
```

FastMCP génère alors un `enum` dans le JSON Schema : une valeur hors
liste est rejetée avant même d'atteindre votre code. C'est strictement
supérieur à une règle textuelle — ce n'est plus du prompting, c'est de
la validation. Attention : le JSON Schema ne permet pas de description
par valeur d'enum, donc la nuance sémantique (pourquoi `insight` et pas
`archi_decision`) doit rester en prose — mais uniquement dans la
description du tool, pas dupliquée dans `instructions`.

**Étape 2 — compacter la description existante** (déjà présente dans
`store_entry`, ligne 135) en format scannable un-critère-par-ligne
plutôt qu'en paragraphe continu :

```
type: doc=explanatory content | archi_decision=structural choice
(observed or decided) | convention=consistent naming/style/process rule
| insight=discovered understanding, durable for weeks (not a decision)
| bug_pattern=known issue+cause WITH PROOF | execution_result=use
record_execution instead, not this tool.
```

Un format court et régulier se scanne plus vite qu'une phrase — utile
vu que cette description est relue à chaque appel.

---

## 4. Rappels contextuels via `tool_result`

### 4.1 Règle 10 — légender `related_context` comme `conflicts`

`query_context` (server.py, ligne 183) ajoute déjà un `reminder` quand
`conflicts` est non vide (`_REMINDER_CONFLICTS`, ligne 193-194). Étendre
le même mécanisme à `related_context`, pour que la distinction
"direct_matches fiable / related_context associatif" soit rappelée au
moment exact où le modèle lit le résultat plutôt qu'espérée d'une règle
apprise 40 tours plus tôt :

```python
result = get_repo().query_context(...)
_queried_since_last_store = True
reminders = []
if result.get("related_context"):
    reminders.append(
        "related_context is 1-hop associative recall — lower "
        "confidence than direct_matches, mention it cautiously."
    )
if result.get("conflicts"):
    reminders.append(_REMINDER_CONFLICTS)
if reminders:
    result["reminder"] = " ".join(reminders)
```

### 4.2 Règle 11 — suggestion actionnable dans `get_memory_stats`

**Correction** : ma proposition précédente supposait des champs
(`all_entries`, `validation_count` par entrée) qui n'existent pas dans
`Repository.get_stats()` (`repository.py`, ligne 446) — la méthode
retourne `total_entries`, `by_type`, `confidence_distribution`,
`never_validated`, `active_contradictions`, `lowest_confidence`,
`recent_activity`, mais rien sur les entrées les plus validées. Il faut
une vraie requête supplémentaire, sur le schéma réel
(`entries.status`, `entry_events.event_type = 'validated'`) :

```python
pin_candidates_rows = self.conn.execute(
    """
    SELECT e.id, e.type, e.provenance_score, e.validation_score,
           e.last_validated_at, e.status, COUNT(ev.id) AS validation_count
    FROM entries e
    JOIN entry_events ev ON ev.entry_id = e.id AND ev.event_type = 'validated'
    WHERE e.status = 'active' AND e.type IN ('archi_decision', 'convention')
    GROUP BY e.id
    HAVING validation_count >= 3
    """
).fetchall()
pin_candidates = [
    row["id"] for row in pin_candidates_rows
    if confidence_at(
        entry_type=EntryType(row["type"]), provenance_score=row["provenance_score"],
        validation_score=row["validation_score"], last_validated_at=row["last_validated_at"],
        status=row["status"], settings=self.settings,
    ) > 0.7
]
if pin_candidates:
    stats["pin_candidates"] = pin_candidates
    stats["reminder"] = f"{len(pin_candidates)} entries validated 3+ times could be pinned via pin_entry."
```

**Nuance à noter** : la commande `/wpm-patterns` (plugin.ts, `WPM_COMMANDS`)
exécute déjà cette même règle de façon active — "convention validated 3+
times -> pin_entry" y est explicitement câblé et exécuté automatiquement à
l'invocation. Le changement ci-dessus n'est donc pas la seule couverture
de la règle 11, juste un signal léger visible sans invoquer `/wpm-patterns`
explicitement. Priorité plus basse que je ne l'avais indiqué au tour
précédent — voir §10.

---

## 5. Prompts : le canal sous-exploité — puis migrés en commandes slash

Historiquement, les règles 13 et 15 ont d'abord été déplacées vers des
prompts MCP (`persist`, `audit`, `learn`, `map`, `bootstrap`, `patterns`).
Cette étape est **dépassée** : côté OpenCode, un prompt MCP s'expose comme
commande slash `/wpm:xxx:mcp`, sans contrôle du texte affiché à
l'exécution ni enregistrement par le plugin.

**Décision finale (migration)** : les 6 workflows sont sortis du serveur
MCP (les `@mcp.prompt` de `server.py` ont été supprimés) et déplacés dans
`wpm-opencode-plugin/plugin.ts` comme commandes slash natives
(`/wpm-persist`, `/wpm-audit`, `/wpm-learn`, `/wpm-map`, `/wpm-bootstrap`,
`/wpm-patterns`) :

- enregistrées par le hook `config` (`config.command`), donc exposées dans
  le picker `/` comme n'importe quelle commande OpenCode ;
- masquées à l'exécution par `command.execute.before` : la part texte du
  template est marquée `synthetic: true` (invisible dans l'UI, mais
  injectée dans le contexte modèle) et remplacée en tête de `parts` par un
  label court visible `/wpm-<commande> [args]`;
- les templates utilisent `$ARGUMENTS` (substitution native des arguments)
  et référencent les outils MCP par leur nom complet `wpm_<tool>`.

### 5.1 Règle 13 — le pass de fin de tâche appartient à `/wpm-persist`

`PERSIST_PROMPT_TEXT` (plugin.ts) est la **source de vérité unique** du
pass de fin de tâche : il est poussé par le hook `session.idle` (via
`client.session.prompt`) et réutilisé tel quel comme template de la
commande `/wpm-persist`. La description de la commande
(`WPM_COMMANDS["wpm-persist"].description`) indique explicitement quand
l'invoquer — « call this yourself when a task or session is wrapping
up » — pour que le modèle la déclenche sans intervention utilisateur.

### 5.2 Règle 15 — répartir la mise en garde dans chaque commande bulk

Chaque commande bulk (`learn`, `map`, `bootstrap`, `patterns`) porte sa
clause « bulk ≠ incremental » dans sa description
(`WPM_COMMANDS[*].description`), relue au moment où la commande est
invoquée. `audit` est read-only, la clause ne s'y applique pas.

---

## 6. Mesurer, pas deviner

`scripts/wpm_metrics.py` ne couvre aujourd'hui que la règle 5 (dedup
before write), via les `entry_events`. Deux extensions concrètes,
réutilisant le même pattern `analyze()` :

**a) Taux de validation avec preuve réelle (règle 8)** — compter, pour
chaque `validate_entry`, la proportion utilisant `agent_reasoning` vs
les autres `evidence_type`. Si `agent_reasoning` apparaît dans les logs
malgré la règle "ne fait pas monter le score", c'est un signal que la
description de `validate_entry` doit être reformulée, indépendamment de
ce que dit `instructions`.

```python
def analyze_evidence_types(rows: list[tuple]) -> dict:
    """rows: (event_type, evidence_type) from entry_events."""
    counts = defaultdict(int)
    for event_type, evidence_type in rows:
        if event_type == "validated":
            counts[evidence_type or "unknown"] += 1
    total = sum(counts.values())
    return {
        "counts": dict(counts),
        "agent_reasoning_rate": (
            round(counts.get("agent_reasoning", 0) / total, 4) if total else None
        ),
    }
```

**b) Entrées jamais validées (règle 3/reliability)** — proportion
d'entrées qui restent `agent_reasoning`-only ou non validées après N
jours. Un taux élevé indique soit une sur-écriture (règle 4 mal suivie),
soit un manque de rappel post-écriture.

Sans ces deux métriques, toute reformulation de prompt reste une
hypothèse non testée — l'objectif de ce guide est justement de rendre
chaque changement vérifiable plutôt qu'esthétique.

---

## 7. Ordre de mise en œuvre suggéré

1. **§3 (Literal sur `type`/`source`)** — gain immédiat, zéro risque de
   régression comportementale, contrainte structurelle plutôt que
   textuelle.
2. **§1-2 (réduction des instructions)** — supprimer les règles déjà
   couvertes ailleurs ; mesurer l'impact avec `wpm_metrics.py` avant/après
   sur une même charge de sessions si possible.
3. **§4 (reminders `tool_result`)** — extensions ciblées, faible risque.
4. **§5 (commandes slash)** — migration des prompts MCP en commandes
   slash natives + masquage `synthetic`, faible risque.
5. **§6 (mesure)** — à mettre en place en parallèle du reste, pas après :
   c'est ce qui permet de juger si les étapes 1-4 ont vraiment amélioré
   la conformité ou juste raccourci le texte.

---

## 9. Exploiter le plugin OpenCode à fond

`plugin.ts` fait déjà deux choses bien ciblées : le nudge des golden
rules à chaque tour (`experimental.chat.system.transform`) et le
ré-ancrage à la compaction (`experimental.session.compacting`). Trois
extensions concrètes, dans l'ordre où l'ajout d'un hook a le plus
d'impact pour le moins de risque.

### 9.1 `tool.execute.after` — fermer le trou de la règle 16, sans passer par le LLM

**Correction par rapport à la version précédente de ce guide** : la doc du
package `@opencode-ai/plugin` précise explicitement que le client SDK
interne (`client`) n'est pas fait pour appeler des serveurs MCP — donc le
plugin ne peut pas invoquer `wpm_record_execution` directement via
`client`. Mais il n'en a pas besoin : **le projet a déjà le bon pattern,
sous les yeux**, dans `scripts/wpm` (`cmd_search`) — un sous-comportement
CLI qui instancie `Repository` directement et court-circuite le MCP
entièrement. Ce même pattern permet de rendre la règle 16 **déterministe
à 100 %**, sans dépendre du modèle :

**a) Ajouter `wpm record-execution` au CLI**, sur le modèle exact de
`cmd_search` dans `scripts/wpm`, en réutilisant les fonctions pures déjà
testées de `behavior.py` (`compile_verification_patterns`,
`looks_like_verification_command`) — donc aucune logique dupliquée ou
divergente entre le tool MCP et le CLI :

```python
def cmd_record_execution(args: argparse.Namespace) -> None:
    config_path = _resolve_wpm_config()
    if not config_path.exists():
        print("wpm: not activated here.", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    db_path = _contained_in_project(config.get("db_path", ""))
    if not db_path.exists():
        sys.exit(1)  # silent — this runs unattended from the plugin

    from wpm_mcp_server import db
    from wpm_mcp_server.behavior import (
        compile_verification_patterns, looks_like_verification_command,
    )
    from wpm_mcp_server.embeddings import get_provider
    from wpm_mcp_server.repository import Repository
    from wpm_mcp_server.settings import load_settings

    settings = load_settings(config_path)
    patterns, _ = compile_verification_patterns(settings.verification_command_patterns or [])
    if not looks_like_verification_command(args.command, patterns):
        sys.exit(0)  # not a verification command — silently skip, not an error

    conn = db.connect(str(db_path))
    repo = Repository(conn=conn, embedder=get_provider(), settings=settings.domain)
    content = f"Command executed: {args.command}\nResult: {'success' if args.succeeded else 'failure'}"
    stored = repo.store_entry(type_="execution_result", content=content,
                               source="tool_execution", session_id=args.session_id)
    if args.succeeded:
        repo.validate_entry(entry_id=stored["entry_id"], evidence_type="execution_verified",
                             evidence_ref=args.command, session_id=args.session_id)
    conn.close()
```

(Ajouter le sous-parseur `record-execution` avec `command`, `--succeeded`,
`--session-id` sur le modèle de `search`.)

**b) Dans `plugin.ts`, shell out via `$` au lieu d'injecter un texte** :

```typescript
"tool.execute.after": async (input, output) => {
  if (input.tool !== "bash") return
  const command = String(output.args?.command ?? "")
  const succeeded = output.metadata?.exitCode === 0  // vérifier le nom exact du champ
  await $`wpm record-execution ${command} --succeeded=${succeeded} --session-id=${input.sessionID}`
    .quiet()
    .nothrow()
}
```

Résultat : plus de dépendance au modèle du tout pour cette règle — la
commande de vérification est détectée et enregistrée que le modèle y
pense ou non. C'est strictement supérieur à un rappel, aussi bien
formulé soit-il, puisqu'un rappel reste une probabilité alors que ceci
est garanti à chaque exécution.

**Points à vérifier empiriquement avant de considérer ceci acquis** (je
ne les ai pas confirmés dans la doc consultée, à valider en conditions
réelles) :
- le nom exact du champ contenant le code de sortie dans `output` pour
  `tool.execute.after` (`exitCode`, `metadata.exitCode`, autre) ;
- le nom exact du champ session dans l'objet `input` de ce hook — les
  exemples consultés confirment `properties.sessionID` pour le hook
  `event`, mais pas explicitly pour `tool.execute.after` ;
- le coût de latence d'un `Bun.$` qui relance un interpréteur Python à
  chaque commande de vérification (connexion SQLite comprise) — mesurer
  avec `time wpm record-execution ...` avant d'appeler ça négligeable ;
- `session_id` ici sera l'id de session OpenCode (`input.sessionID`),
  différent de l'`_session_id` généré côté serveur MCP
  (`uuid.uuid4()` par process stdio) — sans conséquence fonctionnelle
  pour `record_execution` (chaque appel crée une nouvelle entrée avant de
  la valider, donc pas de dédup inter-appel à casser), mais les
  événements de cette entrée seront rattachés à un session_id différent
  de ceux créés via le MCP pendant la même conversation — à documenter
  si `wpm_metrics.py` doit un jour distinguer les deux origines.

Si l'un de ces points ne tient pas en pratique, le fallback reste la
version précédente de ce guide (rappel via
`client.session.prompt({ noReply: true, ... })`) — moins forte mais sans
dépendance à l'API exacte du hook.

### 9.2 `tool.execute.before` — rendre le nudge « memory first » conditionnel

Le nudge actuel de `chat.system.transform` est poussé à **chaque tour**,
même quand le modèle suit déjà la règle. Un hook stateful, gardant une
Map keyed par `sessionID` (pas de variable globale — l'état ne doit pas
fuiter entre sessions), permet de ne rappeler la règle que quand elle est
sur le point d'être violée :

```typescript
const queriedRecently = new Map<string, boolean>() // sessionID -> bool

return {
  "tool.execute.after": async (input) => {
    if (input.tool === "wpm_query_context") {
      queriedRecently.set(input.sessionID, true)
    }
  },
  "tool.execute.before": async (input, output) => {
    if (!["read", "grep", "glob"].includes(input.tool)) return
    if (queriedRecently.get(input.sessionID)) return
    await client.session.prompt({
      path: { id: input.sessionID },
      body: {
        noReply: true,
        parts: [{ type: "text", text: buildMemoryFirstNudge() }],
      },
    })
  },
}
```

Bénéfice double : rappel plus ciblé (juste avant une lecture de fichier,
pas à chaque tour) et moins de tokens consommés par le nudge systémique
sur les tours où la règle est déjà respectée. Si cette version est
fiable en usage réel, le nudge de `chat.system.transform` peut être
allégé — garder seulement les règles 2 et 3, la règle 2 étant déjà
couverte plus précisément ici.

### 9.3 `session.idle` — déclencher, pas seulement journaliser

Le hook actuel (lignes 63-77 de `plugin.ts`) écrit un log que personne ne
lit pendant la session. Le faire réellement agir :

```typescript
event: async ({ event }) => {
  if (event.type !== "session.idle") return
  const sessionID = (event as any).properties?.sessionID
  if (!sessionID || nudged.has(sessionID)) return
  nudged.add(sessionID)
  await client.session.prompt({
    path: { id: sessionID },
    body: { noReply: false, parts: [{ type: "text", text: PERSIST_PROMPT_TEXT }] },
  })
}
```

`PERSIST_PROMPT_TEXT` est désormais la source de vérité unique du texte de
fin de tâche : il alimente le hook `session.idle` et la commande `/wpm-persist`
(voir §5), évitant une troisième version du même texte. `noReply: false`
pour que le modèle traite effectivement la demande au lieu qu'elle reste un
message silencieux.

### 9.4 Un artefact du pivot à corriger : le docstring de `server.py`

Les lignes 1-21 de `server.py` documentent explicitement l'ancien choix :
*"Replaces the old opencode plugin [...] so the server works with any MCP
host"*, et justifient `record_execution` par *"without relying on a
tool.execute.after hook"*. Ce commentaire décrit maintenant l'inverse de
la stratégie retenue (§9.1 réintroduit précisément ce hook). À mettre à
jour pour refléter l'architecture à deux couches — sinon le prochain
contributeur (ou vous-même dans six mois) lira une justification de
design qui n'est plus vraie.

### 9.5 Avertissement à garder du README existant

Les hooks `experimental.*` ne sont pas stabilisés côté OpenCode et
peuvent être ignorés silencieusement si leur nom change de version en
version. Après chaque mise à jour d'OpenCode, revérifier au moins
`experimental.chat.system.transform` et `experimental.session.compacting`
en observant les logs du service `wpm-plugin` pendant une vraie session
— le README le fait déjà pour la version 1.18.11, à répéter à chaque
montée de version plutôt que de supposer que ça continue de fonctionner.

---

## 10. Ordre de mise en œuvre révisé

1. **§3 (Literal sur `type`/`source`)** — gain immédiat, zéro risque.
2. **§9.1a (CLI `wpm record-execution`)** — pure logique Python réutilisant
   des fonctions déjà testées, testable indépendamment du plugin.
3. **§9.1b (hook `tool.execute.after` → shell out vers le CLI)** — après
   avoir vérifié empiriquement les deux points d'API en suspens (nom des
   champs `exitCode`/`sessionID`). Ferme un vrai trou fonctionnel, pas
   seulement une reformulation de prompt.
4. **§9.4 (mise à jour du docstring `server.py`)** — cosmétique mais
   rapide, à faire pendant qu'on a le contexte en tête.
5. **§1-2 (réduction des instructions)** — une fois 9.1 et 9.3 en place,
   les règles 13 et 16 peuvent sortir des `instructions` sans perte.
6. **§9.3 (`session.idle` actif)** — faible risque, gain direct sur la
   règle 13.
7. **§4.1 (reminder `related_context`)** — gain fin, faible risque.
8. **§5 (descriptions de commandes)** — gains fins côté plugin.
9. **§9.2 (nudge conditionnel `memory first`)** — le plus risqué (état
   par session à maintenir correctement), à valider en dernier.
10. **§4.2 (pin_candidates dans get_memory_stats)** — priorité revue à la
    baisse : la commande `/wpm-patterns` couvre déjà activement cette règle:
    utile seulement comme signal passif complémentaire.
11. **§6 (mesure)** — en parallèle de tout le reste, pas après : c'est ce
    qui permet de juger si les changements 1 à 10 améliorent réellement
    la conformité plutôt que de simplement déplacer du texte.

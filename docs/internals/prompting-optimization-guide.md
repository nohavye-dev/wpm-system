# Guide d'optimisation du prompting — wpm-system

> **Statut : implémenté** (toutes les sections). Modules plats → structure
> en couches : `behavior.py` → `prompts/memory_rules.py` ;
> `server.py` → `server/tools.py` + `server/prompts.py` ;
> `settings.py` → `config/settings.py` ;
> `repository.py` → `storage/repository.py` (`get_stats`) + `storage/queries.py`
> (`compute_stats`) ; `domain.py` → `core/constants.py` ;
> `embeddings.py` → `infra/embeddings.py` ; `db.py` → `infra/database.py`.
> Côté plugin : `plugin.ts` reste l'entrée, la logique vit dans `wpm-lib/`.

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

Fichiers concernés : `prompts/memory_rules.py` + `server/tools.py` (couche MCP),
`wpm-opencode-plugin/` (couche plugin, `plugin.ts` + `wpm-lib/`),
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

## 2. Nouveau contenu pour `prompts/memory_rules.py`

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
background persistence sweeps) lives in the description of the relevant
tool — re-read it there at the moment of the decision.
</wpm-memory-rules>
```

Gain : moins de dilution sur les 3 golden rules + 3 politiques
transversales, qui sont justement celles qui ont le plus besoin de
rester présentes tout au long d'une longue session.

---

## 3. Règles 6 et 7 : passer de la prose au schéma

Aujourd'hui (`server/tools.py`, lignes 147 et 240) :

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
`store_entry` — `server/tools.py`) en format scannable un-critère-par-ligne
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

`query_context` (`server/tools.py`) ajoute déjà un `reminder` quand
`conflicts` est non vide (`_REMINDER_CONFLICTS`). Étendre
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
`get_stats` (`storage/repository.py`) / `compute_stats`
(`storage/queries.py`) — la méthode
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

**Nuance à noter** : la commande `/wpm-patterns`
(`wpm-lib/prompts/commands/patterns.ts`) exécute déjà cette même règle de façon active — "convention validated 3+
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
MCP (les `@mcp.prompt` de `server/prompts.py` ont été supprimés) et déplacés dans
`wpm-opencode-plugin/wpm-lib/prompts/commands/` comme commandes slash natives
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

`buildPersistPromptText` (`wpm-lib/prompts/nudges.ts`) est la **source de vérité unique** du
pass de fin de tâche : il est poussé par le hook `session.idle` (via
`client.session.prompt`) et réutilisé tel quel comme template de la
commande `/wpm-persist`. La description de la commande
(`wpm-lib/prompts/commands/`) indique explicitement quand
l'invoquer — « call this yourself when a task or session is wrapping
up » — pour que le modèle la déclenche sans intervention utilisateur.

### 5.2 Règle 15 — répartir la mise en garde dans chaque commande bulk

Chaque commande bulk (`learn`, `map`, `bootstrap`, `patterns`) porte sa
clause « bulk ≠ incremental » dans sa description
(`wpm-lib/prompts/commands/`), relue au moment où la commande est
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

Implémenté via le serveur chaud : le plugin possède le serveur MCP et
appelle directement `record_execution` en `tools/call` (pas de shellout
CLI, pas de cold start). La règle est déterministe à 100 %, sans dépendance
au modèle :

```typescript
"tool.execute.after": async (input, output) => {
  if (input.tool === `${SERVER_NAME}_query_context`) { queriedRecently.set(input.sessionID, true); return }
  if (input.tool !== "bash") return
  if (!deps.mcp) return
  try {
    if (!(await deps.mcp.ready())) return
    await deps.mcp.callTool("record_execution", {
      command: String(input.args?.command ?? ""),
      succeeded: output.metadata?.exit === 0,
      session_id: input.sessionID,
    })
  } catch (e) { if (process.env.WPM_DEBUG) console.error("[wpm] record_execution failed:", e) }
}
```

Plus de `wpm record-execution` CLI (supprimé `scripts/wpm:293`), plus de `Bun.$`
à chaque `bash` — chemin chaud uniquement, no-op silencieux en dégradé.

### 9.2 `tool.execute.before` — rendre le nudge « memory first » conditionnel

Le nudge actuel de `chat.system.transform` est poussé à **chaque tour**,
même quand le modèle suit déjà la règle. Un hook stateful, gardant une
Map keyed par `sessionID` (pas de variable globale — l'état ne doit pas
fuiter entre sessions), permet de ne rappeler la règle que quand elle est
sur le point d'être violée :

```typescript
const queriedRecently = new Map<string, boolean>() // sessionID -> bool

// En production ce flag a deux alimentations : le bridge
// (onQueryContext) et un recall RAG réussi (system-push.ts).
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

`buildPersistPromptText` (`wpm-lib/prompts/nudges.ts`) est désormais la source de vérité unique du texte de
fin de tâche : il alimente le hook `session.idle` et la commande `/wpm-persist`
(voir §5), évitant une troisième version du même texte. `noReply: false`
pour que le modèle traite effectivement la demande au lieu qu'elle reste un
message silencieux.

### 9.4 Un artefact du pivot à corriger : le docstring de `server/__init__.py`

**Fait** — le docstring reflète désormais l'architecture à deux couches.

L'ancien `server.py` documentait explicitement l'ancien choix :
*"Replaces the old opencode plugin [...] so the server works with any MCP
host"*, et justifiait `record_execution` par *"without relying on a
tool.execute.after hook"* — l'inverse de la stratégie retenue (§9.1
réintroduit précisément ce hook). Le docstring actuel
(`server/__init__.py`) décrit bien les deux couches complémentaires.

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
2. **§9.1 (`tool.execute.after` → warm call `record_execution`)** — ferme un
   vrai trou fonctionnel, plus de shellout CLI.
3. **§9.4 (mise à jour du docstring `server/__init__.py`)** — cosmétique mais
   rapide, à faire pendant qu'on a le contexte en tête.
4. **§1-2 (réduction des instructions)** — une fois 9.1 et 9.3 en place,
   les règles 13 et 16 peuvent sortir des `instructions` sans perte.
5. **§9.3 (`session.idle` actif)** — faible risque, gain direct sur la
   règle 13.
6. **§4.1 (reminder `related_context`)** — gain fin, faible risque.
7. **§5 (descriptions de commandes)** — gains fins côté plugin.
8. **§9.2 (nudge conditionnel `memory first`)** — le plus risqué (état
   par session à maintenir correctement), à valider en dernier.
9. **§4.2 (pin_candidates dans get_memory_stats)** — priorité revue à la
   baisse : la commande `/wpm-patterns` couvre déjà activement cette règle:
   utile seulement comme signal passif complémentaire.
10. **§6 (mesure)** — en parallèle de tout le reste, pas après : c'est ce
   qui permet de juger si les changements 1 à 9 améliorent réellement
   la conformité plutôt que de simplement déplacer du texte.

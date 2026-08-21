# Feature — Archive de contexte de session (éphémère)

Statut : proposition, non implémentée. Document séparé du guide
d'optimisation du prompting — cette feature est un composant nouveau,
pas une reformulation de règle existante.

## 1. Problème adressé

Le hook `experimental.session.compacting` de `plugin.ts` intervient au
moment où OpenCode s'apprête à compacter la conversation — c'est-à-dire
à perdre de façon irréversible une partie du contexte détaillé de la
session. Aujourd'hui, le plugin utilise ce moment uniquement pour
pousser un rappel textuel (§9 du guide). Le contenu réel qui va être
perdu (`output.context: string[]`) n'est jamais capturé.

Cette feature capture ce contenu avant qu'il disparaisse, dans une base
séparée de la mémoire persistante, pour que le modèle puisse encore y
piocher plus tard dans la même session — et éventuellement en faire
remonter des fragments vers la mémoire durable via `store_entry`.

## 2. Principe directeur : deux bases, deux philosophies opposées

| | Mémoire persistante (`.wpm/wpm.db`) | Archive de session (nouvelle) |
|---|---|---|
| Durée de vie | Traverse les sessions, les redémarrages | Le temps du process MCP (1 process/session) |
| Stockage | Fichier SQLite sur disque, WAL | `:memory:`, jamais écrit sur disque |
| Sélectivité | Volontairement sélective — "reliability over completeness" (règle 1) | Volontairement exhaustive — tout ce qui a été chunké est gardé, sans filtrage |
| Scoring | Provenance + validation + confiance | Aucun — recherche sémantique brute, pas de notion de fiabilité |
| Rôle | Faits durables sur le projet | Rappel de détails de la conversation en cours, sans jugement de valeur |

Ce n'est pas un compromis entre les deux — ce sont deux outils pour deux
besoins différents. La base persistante reste stricte précisément parce
qu'elle doit durer ; l'archive de session peut se permettre d'être
permissive précisément parce qu'elle ne dure pas.

## 3. Architecture proposée

### 3.1 Où vit le code

Le chunking et l'embedding restent côté serveur MCP (Python), pas dans
le plugin TS — pour éviter une deuxième implémentation de la logique
d'embedding qui pourrait diverger de celle utilisée pour `entries`
(même risque que la duplication de `VERIFICATION_COMMAND_PATTERNS`
évitée dans le guide, §9.1). Le plugin transmet le texte brut ;
le serveur fait le travail sémantique.

### 3.2 Nouvelle connexion, même process

Le process MCP existant (un par session, stdio) ouvre une seconde
connexion SQLite `:memory:` en plus de la connexion vers `.wpm/wpm.db`.
Elle vit et meurt avec le process — aucun nettoyage explicite requis.

```python
archive_conn = sqlite3.connect(":memory:")
archive_conn.enable_load_extension(True)
sqlite_vec.load(archive_conn)
archive_conn.execute(VEC_TABLE_SQL_TEMPLATE.format(dim=EMBEDDING_DIM))
archive_conn.execute("""
    CREATE TABLE session_chunks (
        id INTEGER PRIMARY KEY,
        content TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )
""")
```

Réutiliser `get_provider()` (le même embedder que `Repository`) pour ne
pas avoir deux pipelines d'embedding distincts.

### 3.3 Deux nouveaux tools MCP

**`archive_context(chunks: list[str])`**
Découpe (si pas déjà fait côté plugin) et stocke chaque chunk avec son
embedding dans `session_chunks`. Pas de `type`, pas de `source`, pas de
validation — la seule opération est l'insertion.

**`recall_session_archive(query: str, top_k: int = 5)`**
Recherche sémantique dans `session_chunks`. Idéalement réutilise le même
code de similarité vectorielle que `Repository.query_context`
(généraliser plutôt que dupliquer — par exemple en extrayant la partie
recherche KNN dans une fonction paramétrée par le nom de table plutôt
que deux implémentations séparées).

### 3.4 Point d'intégration : `session.compacting`

```typescript
"experimental.session.compacting": async (input, output) => {
  // existant : rappel textuel
  output.context.push(EXISTING_REMINDER)

  // nouveau : archivage fire-and-forget, ne bloque pas la compaction
  archiveContext(output.context, input.sessionID).catch((err) =>
    client.app.log({ body: { service: "wpm-plugin", level: "warn", message: String(err) } })
  )
}
```

Fire-and-forget plutôt que `await` : la compaction ne doit pas attendre
la fin de l'embedding de potentiellement plusieurs chunks. Un chunk
perdu en cas d'erreur est sans conséquence grave — cette base n'a jamais
prétendu être durable.

### 3.5 Persistance sélective vers la mémoire durable

Aucun mécanisme nouveau nécessaire : le modèle appelle
`recall_session_archive`, identifie un fragment qui mérite de durer, et
appelle `store_entry` avec ce contenu — exactement le flux existant,
juste avec une source d'inspiration différente (l'archive plutôt que sa
propre reformulation).

## 4. Ce que cette feature ne fait pas

- Ne remplace pas `query_context` / la mémoire durable — les deux
  cohabitent, avec des rôles distincts (§2).
- Ne survit pas à la fin de la session — aucune garantie de durabilité,
  par design.
- Ne score pas, ne valide pas, ne détecte pas de conflits — c'est un
  simple index sémantique du texte brut compacté.

## 5. Inconnues à vérifier avant d'implémenter

1. **Granularité réelle de `output.context`.** Est-ce déjà une liste de
   chunks distincts, ou un ou deux blocs de texte longs ? Détermine si
   `archive_context` doit lui-même découper le texte ou peut l'indexer
   tel quel. À logger une fois en conditions réelles avant de concevoir
   la logique de chunking.
2. **Comportement réel du hook `session.compacting` en cas d'erreur
   async non attendue.** Le fire-and-forget proposé en §3.4 suppose que
   le hook ne dépend pas de la résolution de cette promesse pour
   continuer — à confirmer.
3. **Guider le choix du modèle entre `query_context` et
   `recall_session_archive`.** Ajouter un troisième tool de recherche
   introduit une décision de classification supplémentaire pour le
   modèle, du même type que le choix de `type`/`source` en écriture. La
   description de `recall_session_archive` doit être explicite sur son
   rôle ("détails de cette conversation, non vérifiés, non durables")
   pour éviter toute confusion avec la mémoire persistante — sans quoi
   le modèle risque de citer un contenu non fiable de l'archive comme
   s'il s'agissait d'un fait validé du projet.

## 6. Ordre d'implémentation suggéré

1. `archive_context` + `recall_session_archive` sans intégration au hook
   — testables indépendamment via un client MCP normal.
2. Vérifier l'inconnue #1 (granularité de `output.context`) en loggant
   avant d'écrire la logique de chunking définitive.
3. Intégration au hook `session.compacting`, en fire-and-forget.
4. Description des tools soignée pour l'inconnue #3, avec un exemple
   contrasté (comme recommandé pour `type`/`source` dans le guide de
   prompting) plutôt qu'une règle abstraite.
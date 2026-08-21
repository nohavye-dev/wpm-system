# Feature — Profils utilisateurs globaux (`/wpm-user`)

Statut : proposition, non implémentée.

## 1. Problème adressé

La mémoire WPM est strictement **par projet** : elle mémorise des faits
durables sur le code, pas sur la **personne** qui interagit avec l'agent.
Résultat : à chaque nouveau projet, l'agent oublie le prénom de
l'utilisateur, sa langue, son niveau de détail attendu, son ton
(tutoiement/vouvoiement) — bref, ses préférences de conversation.

Cette feature donne à WPM une mémoire des **utilisateurs** (humains),
globale et transverse aux projets, alimentée par un entretien
conversationnel déclenché par la commande slash `/wpm-user`.

## 2. Principes

- **Global, pas par projet** — un profil utilisateur suit la personne d'un
  projet à l'autre ; il ne vit pas dans `.wpm/wpm.db`.
- **Structuré, pas sémantique** — les profils sont lus par clé (nom), pas
  par similarité vectorielle : pas de table `vec0`, pas de modèle
  d'embedding requis.
- **Utilisateur courant** — parmi les profils mémorisés, un « utilisateur
  courant » est sauvegardé (pointeur persisté). L'agent l'applique **à la
  demande**, pas par injection systématique au démarrage.
- **Plusieurs utilisateurs** — la base stocke N profils ; on peut en
  sélectionner un comme courant.

## 3. Stockage

Fichier : `$XDG_CONFIG_HOME/wpm-system/users.db`
(fallback `~/.config/wpm-system/users.db`), override `WPM_USERS_DB_PATH`.

Choix de `~/.config` plutôt que `~/.local/share/wpm-system` (DATA_DIR) :
`wpm uninstall` supprime `DATA_DIR` en bloc (`shutil.rmtree`), mais ne
touche **jamais** `~/.config`. Les profils sont donc **préservés
automatiquement au désinstall** — aucune modification de `cmd_uninstall`
nécessaire (une simple ligne informative peut être ajoutée).

Schéma SQLite :

```sql
CREATE TABLE IF NOT EXISTS users (
    name        TEXT PRIMARY KEY,   -- identifiant unique (ex. "noha")
    prenoms     TEXT,               -- prénom(s) d'affichage
    preferences TEXT,               -- JSON {language, tone, detail_level, response_style, role_context}
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL             -- clé "current_user" -> name
);
```

## 4. Champs collectés

| Champ | Description |
|---|---|
| `prenoms` | Prénom(s) / nom préféré pour s'adresser à l'utilisateur |
| `language` | Langue préférée des réponses |
| `tone` | Tutoiement / vouvoiement |
| `detail_level` | Concis / détaillé (verbosité) |
| `response_style` | Style de réponse (puces, exemples de code, format…) |
| `role_context` | Rôle, métier, domaine, fuseau horaire |

Extensibilité : ajouter un champ = ajouter un argument d'outil + une clé
JSON (coût faible).

## 5. Outils MCP (serveur)

Tous disponibles indépendamment de `DB_PATH` (donc même hors activation
projet, tant que le serveur tourne) :

| Tool | Rôle |
|---|---|
| `wpm_save_user(name, prenoms?, language?, tone?, detail_level?, response_style?, role_context?)` | Upsert du profil + le définit comme utilisateur courant |
| `wpm_get_users()` | Liste `{name, prenoms, updated_at}` |
| `wpm_get_user(name)` | Profil complet d'un utilisateur |
| `wpm_get_current_user()` | Profil de l'utilisateur courant (ou « aucun ») |
| `wpm_set_current_user(name)` | Changer d'utilisateur courant |
| `wpm_remove_user(name)` | (optionnel) supprimer un profil |

Ressource : `wpm://current-user` — rend le profil courant en texte pour
lecture à la demande.

## 6. Commande `/wpm-user` (plugin)

Enregistrée via `config.command` (comme les autres `/wpm-*`), template
dans `wpm-lib/prompts/commands/user.ts`. Le template ordonne un **entretien conversationnel** :

1. Poser les questions (prénom(s), langue, tutoiement/vouvoiement,
   niveau de détail, style, rôle/contexte), éventuellement en plusieurs
   tours.
2. Collecter les réponses.
3. Si un profil du même nom existe déjà : proposer une mise à jour via
   `wpm_save_user` (pas de doublon).
4. Appeler `wpm_save_user` puis confirmer à l'utilisateur.

Le masquage du prompt à l'exécution est déjà géré par
`command.execute.before` (générique à tous les `/wpm-*`).

## 7. Utilisation par l'agent

- **À la demande** : l'agent appelle `wpm_get_current_user` quand il a
  besoin de savoir à qui il parle et comment répondre (nom, langue, ton,
  verbosité).
- Rappel léger dans les standing policies / le nudge : « consulter
  `wpm_get_current_user` à la demande » — pas de lecture forcée au
  démarrage.
- La chaîne du prompt plan-agent (qui énumère les outils `wpm_*`) est
  étendue avec les nouveaux noms.

## 8. Fichiers touchés (à implémenter)

- `wpm-mcp-server/src/wpm_mcp_server/storage/users.py` — nouveau : `UserRepository`
  + résolution du chemin.
- `wpm-mcp-server/src/wpm_mcp_server/server/tools.py` — 5 outils +
  `server/resources.py` (resource `wpm://current-user`) + `server/prompts.py`.
- `wpm-mcp-server/src/wpm_mcp_server/prompts/memory_rules.py` — mention légère.
- `wpm-opencode-plugin/wpm-lib/prompts/commands/user.ts` — `buildUserPromptText()` +
  enregistrement `wpm-user`.
- `wpm-opencode-plugin/wpm-lib/server/hooks.ts` — étendre la liste d'outils du
  prompt plan-agent.
- `wpm-opencode-plugin/wpm-lib/prompts/nudges.ts` — rappel léger.
- `wpm-mcp-server/test_users.py` — tests du dépôt + résolution du chemin
  (`XDG_CONFIG_HOME` temporaire).
- `README.md` + `wpm-mcp-server/README.md` — docs.

## 9. Points d'attention / inconnues

1. **Activation** : le serveur est lancé par le plugin uniquement quand un
   projet est activé (`wpm.config.json`). Les profils sont globaux, mais
   accessibles seulement dans un projet wpm-activé. Acceptable en v1.
2. **`wpm_remove_user`** : inclus ou non (décision produit) — supprimer un
   profil est une perte de données sans historique.
3. **Désinstall** : vérifier que `~/.config/wpm-system` n'est touché par
   aucun chemin de `cmd_uninstall` (aujourd'hui non).

## 10. Ordre d'implémentation suggéré

1. `users.py` + tests (`test_users.py`).
2. Outils + resource dans `server.py`, testables via un client MCP.
3. Commande `/wpm-user` + intégrations plugin.
4. Docs.

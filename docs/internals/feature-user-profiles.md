# Feature — Profils utilisateurs globaux

Statut : **implémentée (v2.1)**. Les §1-§13 documentent la proposition
initiale et la v1 ; le §14 décrit la v2 (CLI de création, override de
langue par le profil) ; le **§15 décrit l'état courant** : préférences
et observations unifiées dans une table à `source` (declared/inferred),
tool unique, capture silencieuse, décroissance douce de l'inféré.

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

## 11. Décisions arrêtées à l'implémentation

Écarts par rapport à la proposition initiale, tous arbitrés en design :

1. **Surface MCP réduite à 2 tools** : `save_user` et
   `get_current_user`. `get_users`/`get_user` ne sont pas exposés au LLM —
   le merge partiel rend inutile une lecture préalable, et l'énumération
   des profils est de la gestion d'identité (territoire CLI). Le dépôt
   garde ces méthodes en interne pour le CLI ; `save_user` retourne
   `{created, profile}` pour distinguer création et mise à jour sans
   pré-check.
2. **Bascule et suppression côté CLI uniquement** : `wpm current-user
   [<name>]` (sans argument : affiche), `wpm list-users`,
   `wpm remove-user <name> [--yes]`. Le LLM ne change jamais le pointeur
   ni ne supprime — opérations d'identité destructives réservées à
   l'humain.
3. **`save_user` définit toujours l'utilisateur courant** : se présenter
   EST basculer (« si je me présente c'est que je suis ce nouvel
   utilisateur »). Le CLI sert aux bascules sans re-présentation.
4. **Injection déterministe du profil** (remplace « à la demande, pas
   d'injection au démarrage » §2) : une clause légère seule laisse échouer
   le tour critique — le premier (langue/ton dès la première réponse).
   Même logique que `record_execution` devenu déterministe : bloc poussé
   chaque tour par `buildSystemPush` (lecture fraîche, cache contourné —
   aucune notification `resources/updated` ne peut venir de la CLI).
5. **Format balisé symétrique** (`prompts/user_profile.py`) : la resource
   rend un bloc `<current-user>` markdown ; le plugin pousse ces octets
   verbatim (`InjectionBlock.setBody`, sans tag) — même source que
   `<project-rules>`, zéro drift.
6. **Nommage CLI en tirets** (`current-user`, `list-users`,
   `remove-user`) : convention en tirets.
7. **Inconnue §9.3 confirmée** : `cmd_uninstall` ne touche jamais
   `~/.config/wpm-system` — profils préservés, ligne ajoutée au README.
8. **Asymétrie resource** : il n'existe pas de chemin de lecture de resource
   côté agent ; la resource reste utile comme miroir/audit, mais le chemin
   canonique est le tool `get_current_user` et le push déterministe.

## 12. Observations comportementales (extension v1)

Deuxième brique du profil : des **faits observés/inférés** sur la
personne, distincts des préférences déclarées (`save_user`) et de la
mémoire projet (qui interdit explicitement le contexte conversationnel).

### Principe

- L'agent note « de temps en temps » une attitude, un comportement
  récurrent, une incompréhension, une préférence de workflow — via
  `record_observation(category, content, reinforce_id?)`.
- La récurrence est un **compteur** : nouvelle observation = count 1 ;
  `reinforce_id` incrémente au lieu de dupliquer. Seuls les motifs
  **renforcés ≥ 2 fois** (`RECURRENCE_THRESHOLD`) remontent dans la
  section `Observed recurring patterns` du bloc `<current-user>` —
  adaptation progressive et automatique dans les deux modes, sans nouveau
  chemin d'injection.
- Détection de récurrence **côté modèle** : `get_user_observations`
  retourne tout (singletons compris) pour décider « renforcer vs ajouter ».
  users.db reste « structuré, non sémantique » — pas d'embeddings.
- Capture **silencieuse** (v2.1) : l'agent n'annonce pas ses
  enregistrements ; la transparence est assurée par le CLI
  (`wpm user-observations` liste tout, `remove-user-observation`
  supprime).
- Garde-fous : consigne incitative + standing policy + nudge, mais
  plafond dur par session (`OBSERVATION_SESSION_LIMIT`, 20) dans
  `state.py`, taxonomie fermée (`OBSERVATION_CATEGORIES`) et fenêtre de
  fraîcheur (`OBSERVATION_STALENESS_DAYS`, 30 j) ; les préférences
  déclarées restent autoritaires sur l'inféré (en cas de conflit stable,
  proposer `/wpm-user-preferences` plutôt que d'enregistrer une
  observation contradictoire).

### Interrupteurs indépendants

| État | Effet |
|---|---|
| Utilisateur courant défini + capture on | Profil appliqué chaque tour + captation active |
| Utilisateur courant défini + `wpm user-observations off` | Profil appliqué, zéro captation |
| `wpm current-user none` | Rien n'est appliqué ni capté ; données conservées |

- Le pointeur courant EST l'interrupteur d'usage : pas de flag maître.
  `save_user` reste toujours disponible (se présenter = réactiver).
- Capture **activée par défaut** ; toggle global dans `meta`
  (`observations_enabled`, absent = on), gardes à l'appel → effet au tour
  suivant sans restart. Les tools répondent alors
  `{"error": true, "disabled": true, "message": "... run 'wpm user-observations on'"}`.
- Le mot `none` est **réservé** : `normalize_name` rejette ce nom.

### CLI

```
wpm current-user [<nom>|none]     # affiche / bascule / désactive l'usage
wpm list-users                    # profils ('*' = courant)
wpm remove-user <nom>             # supprime un profil (+ observations, cascade FK)
wpm user-observations [on|off]    # statut + liste / bascule la captation
wpm remove-user-observation <id>  # supprime une observation erronée
```

### Fichiers

`storage/users.py` (table `observations`, FK cascade, flags, CRUD),
`prompts/user_profile.py` (section + seuil), `server/tools.py`
(2 handlers + gardes), `server/state.py` (throttle),
`server/resources.py` (filtrage amont), `server/prompts.py`
(descriptions), `memory_rules.py` + `nudges.ts` (parcimonie),
`hooks.ts` (plan-agent), `scripts/wpm` (3 sous-commandes).

## 13. Décisions arrêtées à l'implémentation (observations)

1. **Récurrence par compteur, détection côté modèle** (structuré, sans
   embeddings) — cohérent avec la philosophie « structuré, non
   sémantique » de users.db ; les observations sont peu nombreuses, le
   modèle fait mieux la correspondance qu'un substring match.
2. **Écrire dès la première occurrence, n'injecter qu'à partir de ×2** :
   le modèle n'a pas d'état entre sessions ; le compteur porte la
   récurrence à sa place.
3. **Section intégrée à `<current-user>`** plutôt que bloc séparé : même
   canal déterministe, rendu serveur unique, zéro drift bi-mode.
4. **Usage piloté par le pointeur courant** (`current-user none`) plutôt
   qu'un flag maître : un état de moins, sémantique déjà existante,
   réactivation conversationnelle naturelle.
5. **Capture activée par défaut**, toggle CLI global dans users.db meta :
   transparence + correction CLI compensent ; effet immédiat grâce aux
   gardes à l'appel.
6. **Nommage CLI** : `user-observations` / `remove-user-observation`
   (namespace `user-*` explicite, tirets comme le reste).

## 14. v2 — Architecture hybride (état actuel)

Réorganisation fondée sur le constat que l'entretien LLM (`/wpm-user`)
était dépendant du modèle (modèles free/Zen n'exécutaient pas le
questionnaire) et que l'identité devait être **100 % pilotée par
l'humain**, comme la bascule et la suppression.

### 14.1 Entité `user` et modèle de données

L'entité porte son identité plus **deux listes** :

```
User {
  name          : "Noha"               -- clé unique, COLLATE NOCASE (prénom tel que saisi)
  language      : "french"             -- token anglais (auto-complétion)
  introduction  : "dev full-stack"     -- texte libre facultatif
  preferences   : [ énoncés explicites ]
  observations  : [ {category, content, count} ]   -- poids conservé
}
```

4 tables : `users(name NOCASE, language, introduction, created_at,
updated_at)`, `user_preferences` (FK cascade), `observations` (FK cascade,
avec `count` = poids de récurrence), `meta` (pointeur courant +
`observations_enabled`). Supprimés : `prenoms`, clé JSON `preferences`,
champs `tone`/`detail_level`/`response_style`/`role_context` (les
préférences de ton/verbosité/style sont désormais des **énoncés
explicites**, pas des champs structurés).

### 14.2 Surface MCP (v2 : 16 tools — voir §15 pour l'état courant)

Mémoire (11) + `get_user`, `record_user_observation`,
`get_user_observations`, `add_user_preference`, `get_user_preferences`.
**`save_user` supprimé** : le LLM ne crée ni ne modifie de profil — il
oriente vers `wpm new-user`. Nommage harmonisé : préfixe `user`, jamais
`current` (l'utilisateur courant est implicite, rappelé dans les
descriptions).

### 14.3 Création : `wpm new-user` (unique chemin)

`Enter your first name` → `name` ; `Choose your language` →
**auto-complétion** sur `SUPPORTED_LANGUAGES` (~50 langues du modèle, noms
anglais, dans `core/constants.py` + matcher pur) — lettres tapées en
blanc, complétion proposée en gris, ↑/↓ navigation, → validation,
backspace, Ctrl-C, repli `input()` hors TTY ; `Introduce yourself`
(facultatif) → `introduction`. Récapitulatif + confirmation → `save_user`
(méthode dépôt) + utilisateur courant.

### 14.4 Préférences : `/wpm-user-preferences` (supprimée en v2.1, voir §15)

Le modèle reformulait la demande de l'utilisateur en énoncé 1ʳᵉ personne
puis appelait `add_user_preference` ; dédoublonnage via
`get_user_preferences`. Les préférences étaient **explicites** (déclarées
par l'utilisateur), les observations **inférées** (parcimonie + compteur)
— les deux sections cohabitaient dans le bloc `<current-user>`.

### 14.5 Langue : override par le profil, sans toucher aux prompts

`resolve_response_language` reste le **seul** mécanisme de résolution ;
sa valeur d'entrée change seulement :
- serveur (`state.py`) : la langue du profil courant (lecture `users.db`)
  est passée comme config-value → **aucun caractère** des clauses de
  langue existantes modifié ;
- plugin (`plugin.ts`) : extraction via `wpm current-user --language`
  (shellout CLI) comme config-value.

Précédence : `WPM_RESPONSE_LANGUAGE` (env) > **langue du profil** >
`response_language` (config) > « langue de l'utilisateur ». Résolution au
démarrage (import serveur `state.py:61` / chargement plugin `plugin.ts:54`),
comme la config. Un `wpm current-user` mid-session rafraîchit le bloc
`<current-user>` dès le tour suivant (push frais `system-push.ts:38`), mais
la clause de langue figée dans `SERVER_INSTRUCTIONS`/`nudge` ne bouge
qu'au restart — le bloc reste autoritaire.

### 14.6 Décisions v2

1. **Création au CLI** (`new-user`) : déterministe, indépendante du modèle
   — adossée à l'incident « modèles Zen/free : rien ne se produit ».
2. **`save_user` retiré du MCP** : un « je suis X » en session ne peut
   plus créer de profil ; l'agent explique `wpm new-user`.
3. **Préférences séparées des observations** : déclarées (1ʳᵉ personne,
   non pondérées) vs inférées (compteur) — sections distinctes du bloc.
4. **Override de langue par le profil** : uniquement via
   `resolve_response_language`, prompts inchangés (discipline stricte).
5. **Champs structurés simplifiés** : ton/détail/style/rôle sont des
   énoncés de préférence, plus des champs du profil.

## 15. v2.1 — Unification préférences + observations (état actuel)

Une seule table `observations` avec une colonne `source` ; les tables et
tools `user_preferences` / `add_user_preference` /
`get_user_preferences` sont supprimés (pas de migration : la base est
jeune, supprimable à la main). `/wpm-user-preferences` n'existe plus.

1. **Deux sources, un stockage** (`OBSERVATION_SOURCES`,
   `core/constants.py`) :
   - `declared` : préférence **énoncée par l'humain** en session
     (« parle-moi plus simplement ») — autoritaire, injectée **dès
     l'enregistrement**, jamais de déclin, jamais bloquée par le flag de
     captation ni le budget ; `category` ignorée (NULL) ;
   - `inferred` : motif remarqué par l'agent — taxonomie fermée
     (`OBSERVATION_CATEGORIES` : `habit, workflow, knowledge, context,
     communication, personal`, l'ordre du tuple = priorité d'affichage),
     pondérée par `count`.
2. **Tool unique** :
   `record_user_observation(content, source='inferred', category=None,
   reinforce_id=None, replaces_id=None)`.
   - `reinforce_id` : incrémente un motif inféré existant (refusé sur du
     déclaré) ;
   - `replaces_id` : une nouvelle déclaration contradictoire **supprime
     durablement** la déclaration visée (réservé au `declared` ;
     refusé depuis l'inféré — l'agent ne peut jamais effacer la parole
     de l'humain) ;
   - gates différenciées : pointeur toujours requis ; flag
     `observations_enabled` + budget 20/session ne s'appliquent qu'à
     l'inféré. `get_user_observations()` reste listable capture off.
3. **Capture silencieuse + incitative** : prompts
   (`RECORD_USER_OBSERVATION_PROMPT`, standing policy, `nudges.ts`) :
   « record it right away… silently », sans annonce ; `sparingly`
   abandonné au profit du plafond dur.
4. **Décroissance douce de l'inféré** (`OBSERVATION_STALENESS_DAYS`,
   30 j) : injection seulement si `count >= RECURRENCE_THRESHOLD` (2)
   **et** `updated_at ≤ 30 jours`. Au-delà, l'observation dort en base
   jusqu'à un renforcement qui la réactive.
5. **Rendu** (`prompts/user_profile.py`) : section `## User preferences`
   (déclarées) rendue **toujours entière** ; les groupes d'inférés
   (`### Habit`, …, ordre de priorité, tri `count DESC` puis récence,
   ligne `- content (seen xN, last YYYY-MM-DD)`) remplissent le budget
   restant plafonné à `MAX_CURRENT_USER_CHARS = 2000`. Rendu serveur
   unique, zéro drift.
6. **CLI** (`wpm user-observations`) : groupe `declared preferences:` en
   tête, puis catégories inférées avec `(seen xN)`/ids/`(last date)` ;
   `[on|off]` n'affecte que l'inféré ;
   `remove-user-observation <id>` vaut pour les deux sources.

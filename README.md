# WPM — Weighted Persistent Memory

Une **mémoire persistante pondérée par la confiance** pour votre agent IA
(OpenCode). Les décisions d'architecture, conventions et patterns découverts
pendant une session ne sont pas perdus à la suivante — et surtout, on sait
**à quel point chaque souvenir est fiable**.

> WPM est en **phase d'essais** : l'idée est prometteuse, l'ingénierie est
> propre, mais le modèle de confiance reste à valider sur de vrais projets.

## Documentation

- Site web du projet : [WPM — Weighted Persistent Memory](https://nohavye-dev.github.io/wpm-site/)
- [`wpm-mcp-server/README.md`](wpm-mcp-server/README.md) — le serveur, côté technique.
- [`docs/internals/`](docs/internals/) — notes de conception internes (validation, calibration).


## Pourquoi WPM ?

Le contexte d'un agent IA est éphémère : ce qu'il comprend pendant une
session disparaît à la suivante. WPM lui donne une mémoire **locale au
projet**, entretenue automatiquement pendant le travail, où chaque
information porte un **score de confiance** qui évolue dans le temps.

## Les idées clés

- **Confiance pondérée** — chaque souvenir a un score (0 à 1) ; on distingue
  ce qui est sûr de ce qui est supposé.
- **Provenance** — une source officielle vaut plus qu'une déduction ; la
  confiance de départ en dépend.
- **Preuves, pas d'opinions** — la confiance ne monte qu'avec des preuves
  externes vérifiables, jamais avec du raisonnement seul.
- **Jamais de suppression** — on contredit une information, on ne l'efface
  pas : l'historique reste traçable.
- **Mémorisation au fil de l'eau** — l'agent note les faits durables dès
  qu'ils émergent, pas en fin de session.
- **Rappel au bon moment** — recherche hybride (sémantique + graphe) pour
  ressortir le bon souvenir quand il compte.

---



## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/nohavye-dev/wpm-system/main/install.sh | bash
```

## Démarrage

Dans chaque projet où vous voulez activer WPM :

```bash
wpm enable
```

Cette commande crée un fichier `wpm.config.json` à la racine du projet
et initialise la base de données locale (`.wpm/wpm.db`). Elle ajoute
automatiquement le répertoire de données au `.gitignore`.

Puis redémarrez OpenCode — c'est tout.

**Zéro configuration OpenCode.** Le plugin s'installe tout seul, enregistre
le serveur MCP et les permissions à votre place : pas d'entrée `mcp` à
ajouter dans `opencode.json`.

---

## CLI

En plus de `wpm enable` / `wpm disable` :

- `wpm search "<requête>"` — interroger la mémoire du projet (langue libre,
  modèle multilingue) ;
- `wpm export [-o fichier.json]` — exporter la base en JSON (sans embeddings) ;
- `wpm generate <fichier.json> --output <wpm.db>` — régénérer une base à
  partir d'un export (embeddings recalculés) ;
- `wpm reembed` — ré-encoder toutes les entrées (obligatoire après un
  changement de modèle d'embedding) ;
- `wpm new-user` — créer (ou mettre à jour) un profil utilisateur de façon
  interactive (prénom, langue en auto-complétion, présentation facultative) ;
  le profil devient l'utilisateur courant ;
- `wpm current-user [<nom>|none]` — afficher l'utilisateur courant, basculer
  sur `<nom>`, ou désactiver l'usage des profils avec `none` (données
  conservées) ; `--language` affiche uniquement le token de langue ;
- `wpm list-users` — lister les profils (`*` marque l'utilisateur courant) ;
- `wpm remove-user <nom>` — supprimer un profil ;
- `wpm user-observations [on|off]` — statut et liste des observations
  comportementales, ou bascule de la captation (activée par défaut) ;
- `wpm remove-user-observation <id>` — supprimer une observation erronée ;
- `wpm uninstall` — désinstaller complètement (venv, binaire, plugin ;
  les profils utilisateurs sous `~/.config/wpm-system/` sont conservés).

---

## Ce que vous obtenez

Une fois activé, votre agent peut :

- **mémoriser** (`store_entry`) et **relire** (`query_context`) des faits
  durables, en langue native (FR/EN, embedding multilingue) et dédupliqués ;
- **valider** (`validate_entry`) ou **contredire** (`contradict_entry`) avec
  des preuves ;
- **capturer les tests/builds** automatiquement (`record_execution`) ;
- **épingler / déprécier / restaurer** des souvenirs (`pin_entry`,
  `deprecate_entry`, `restore_entry`) ;
- **se souvenir de qui vous êtes** (`get_user`, `wpm new-user`) : un profil
  global (prénom, langue, présentation) qui suit la personne de projet en
  projet ; la langue du profil **prime** sur la config ; appliqué
  automatiquement à chaque tour ;
- **appliquer vos préférences** : dites-les simplement en session (« sois
  plus concis ») — l'agent les enregistre silencieusement comme énoncés
  **déclarés**, toujours injectés dans le profil et sans déclin ; une
  nouvelle déclaration contradictoire remplace l'ancienne ;
- **s'adapter à vos habitudes** (`record_user_observation`, source
  `inferred`) : habitudes, préférences d'outil, expertise, contexte,
  style de communication, traits personnels — notés silencieusement dans
  une taxonomie fermée, puis injectés au profil dès qu'un motif se répète
  (×2) et tant qu'il reste frais (30 jours). Visible et corrigeable via
  `wpm user-observations` / `remove-user-observation`, désactivable ; le
  toggle et le plafond par session ne concernent que l'inféré.
- lire les **règles du projet** recomposées depuis la mémoire ;
- **sauvegarder / ré-encoder** la base hors session (`wpm export`,
  `wpm generate`, `wpm reembed`).

Et des workflows prêts à l'emploi, en commandes slash enregistrées par le
plugin : `/wpm-learn`, `/wpm-map`, `/wpm-bootstrap`, `/wpm-audit`,
`/wpm-patterns` (et le pass de fin de tâche `/wpm-persist`).

---

## En phase d'essais

Les points à surveiller : la **stabilité des hooks OpenCode** (`experimental.*`)
et la **validation du modèle de confiance** sur de vrais projets.

---

## Pour les mainteneurs

Setup dev (fresh clone) : `bash scripts/setup-dev.sh` — voir [CONTRIBUTING.md](CONTRIBUTING.md) pour le workflow complet (prérequis, tests, checksums, branches, publication, debug).

> Avant chaque push : `scripts/update-source-checksum.sh` puis commit du `SHA256SUMS` — sinon `curl | bash` échoue.

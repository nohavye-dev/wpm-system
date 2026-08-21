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
- `wpm uninstall` — désinstaller complètement (venv, binaire, plugin).

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

Avant de pousser des modifications, régénérez le checksum :

```bash
scripts/update-source-checksum.sh
```

Puis commitez le `SHA256SUMS` mis à jour. Sans cela, l'installation par
`curl | bash` échouera sur un échec de vérification.

### Synchroniser la documentation publique

`docs/public/` est une **vraie copie** (pas un lien symbolique) de
`wpm-site/docs`, le dossier consommé par le site. Éditez les docs ici,
puis publiez :

```bash
scripts/sync-public-docs.sh                # message de commit par défaut
scripts/sync-public-docs.sh -m "docs: ..." # message personnalisé
```

Le script synchronise `docs/public/` vers `wpm-site/docs` (rsync --delete),
puis committe et pousse sur `origin`. Il refuse de s'exécuter si :

- wpm-system n'est pas sur la branche `main` ;
- wpm-site contient des modifications non commitées ;
- le réseau est indisponible (vérification de `origin`, timeout 15 s).

Si rien n'a changé, il ne fait rien (pas de commit vide).

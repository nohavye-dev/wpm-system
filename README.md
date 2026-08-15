# WPM — Weighted Persistent Memory

Une **mémoire persistante pondérée par la confiance** pour votre agent IA
(OpenCode). Les décisions d'architecture, conventions et patterns découverts
pendant une session ne sont pas perdus à la suivante — et surtout, on sait
**à quel point chaque souvenir est fiable**.

> WPM est en **phase d'essais** : l'idée est prometteuse, l'ingénierie est
> propre, mais le modèle de confiance reste à valider sur de vrais projets.

---

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

👉 Le détail vulgarisé de ces concepts : [`docs/concepts.md`](docs/concepts.md).

---

## Démarrage en 3 commandes

```bash
./install.sh        # 1. installe le serveur + le plugin (global, une fois)
wpm enable          # 2. active la mémoire sur ce projet (écrit wpm.config.json)
                    # 3. redémarrez OpenCode — c'est tout.
```

**Zéro configuration OpenCode.** Le plugin s'installe tout seul, enregistre
le serveur MCP et les permissions à votre place : pas d'entrée `mcp` à
ajouter dans `opencode.json`.

---

## Ce que vous obtenez

Une fois activé, votre agent peut :

- **mémoriser** (`store_entry`) et **relire** (`query_context`) des faits
  durables, en anglais et dédupliqués ;
- **valider** (`validate_entry`) ou **contredire** (`contradict_entry`) avec
  des preuves ;
- **capturer les tests/builds** automatiquement (`record_execution`) ;
- **épingler / déprécier / restaurer** des souvenirs (`pin_entry`,
  `deprecate_entry`, `restore_entry`) ;
- lire les **règles du projet** recomposées depuis la mémoire.

Et des workflows prêts à l'emploi : `learn`, `map`, `bootstrap`, `audit`,
`patterns`.

---

## Documentation

- [`docs/concepts.md`](docs/concepts.md) — **concepts et fonctionnement, vulgarisés**.
- [`docs/setup.md`](docs/setup.md) — installation, activation, désinstallation.
- [`docs/workflows.md`](docs/workflows.md) — les workflows `learn`, `map`, `bootstrap`, `audit`, `patterns`.
- [`docs/agent-behavior.md`](docs/agent-behavior.md) — ce que l'agent doit faire (référence).
- [`docs/configuration.md`](docs/configuration.md) — référence `wpm.config.json`.
- [`wpm-mcp-server/README.md`](wpm-mcp-server/README.md) — le serveur, côté technique.
- [`docs/internal/`](docs/internal/) — notes de conception internes (validation, calibration).

---

## En phase d'essais

Les points à surveiller : la **stabilité des hooks OpenCode** (`experimental.*`)
et la **validation du modèle de confiance** sur de vrais projets.

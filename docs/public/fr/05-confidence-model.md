# Le modèle de confiance — pourquoi la mémoire oublie

WPM n'est pas une base de données : c'est une **mémoire pondérée**. Chaque
entrée porte un score de confiance qui décroît avec le temps et évolue selon
ses preuves. Ce document explique comment ce score est calculé, d'où viennent
les valeurs, et comment les ajuster.

---

## La formule

```
confidence(t) = base × exp(−λ × t)
```

- **base** — la confiance de départ, fixée par la *source* de l'information
  (voir [Provenance](#provenance--la-confiance-de-départ)) ;
- **λ** — le taux d'érosion propre au *type* d'entrée (voir
  [Demi-vies](#demi-vies-par-type-dentrée)) ;
- **t** — le temps écoulé depuis l'écriture.

La grandeur intuitive derrière λ est la **demi-vie** : le temps au bout
duquel la confiance a tombé de moitié.

```
demi-vie = ln(2) / λ ≈ 0.693 / λ
```

Le score de confiance ne descend jamais sous zéro et reste une *pondération* :
une entrée à faible confiance n'est pas supprimée, elle est simplement moins
bien classée dans les résultats et exclue des blocs à seuil (comme
`<project-rules>`).

---

## Demi-vies par type d'entrée

| Type | Demi-vie | Fiabilité de la valeur |
|---|---|---|
| `archi_decision` | ~1 an | raisonnement de domaine |
| `convention` | ~6 mois | raisonnement de domaine |
| `doc` | ~4.5 mois | borne indicative (non mesurée) |
| `insight` | ~1 mois | raisonnement de domaine |
| `bug_pattern` | ~18 jours | **mesurée sur données publiées** |
| `execution_result` | ~3 jours | raisonnement de domaine |

Lecture : une convention stockée aujourd'hui pèsera encore ~50 % dans six
mois ; un résultat de build, dans trois jours. L'ordre n'est pas arbitraire —
il reflète la vitesse à laquelle chaque catégorie de savoir devient obsolète
dans un projet réel.

---

## D'où viennent ces valeurs

Les demi-vies ne sont pas devinées au hasard : elles sont **calibrées sur des
ancres externes**, avec un niveau de fiabilité explicite pour chacune.

### Mesure publiée — `bug_pattern`

La durée de vie d'un bug est approchée par son **temps de résolution**.
Une étude empirique sur des dépôts logiciels scientifiques mesure une
résolution médiane de **18.09 jours** (« What Drives Issue Resolution
Speed? », arXiv 2512.18852). Viser une confiance de 0.5 à cette médiane
donne λ ≈ 0.0016/heure — la valeur appliquée. C'est une borne prudente :
temps rapport → correction sous-estime la vraie vie introduction → correction.

### Borne indicative — `doc`

La littérature sur la documentation montre que les références de code y
deviennent obsolètes en masse et restent souvent non corrigées pendant des
années (Tan & Wagner, *Empirical Software Engineering* 2023 — DOCER,
analyse de 3 000+ projets GitHub). Une statistique sectorielle non revue
(« 60 % obsolète en 6 mois ») fournit une borne haute provisoire :
demi-vie ≈ 4.5 mois. À remplacer par une mesure rigoureuse quand disponible.

### Raisonnement de domaine — les autres types

Aucune ancre publiée n'existe pour `archi_decision`, `convention`,
`insight`, `execution_result`. Leurs λ sont posés par raisonnement de
domaine : ordre de grandeur cohérent avec les deux ancres ci-dessus, et
durées de vie cohérentes avec leur nature (une décision d'architecture vit
des années ; un résultat de test, des jours).

Sources complètes et méthode détaillée : voir la note interne
`docs/internals/heuristic-calibration.md`.

---

## Provenance — la confiance de départ

À l'écriture, la source détermine le score initial :

| Source | Confiance initiale |
|---|---|
| `official_doc` | 0.9 |
| `observed_code` | 0.75 |
| `tool_execution` | 0.7 |
| `agent_inference` | 0.35 |

Une information lue dans la documentation officielle naît plus fiable qu'une
déduction de l'agent — et décroîtra moins vite en relatif.

---

## Preuves — faire monter ou baisser le score

Après l'écriture, deux familles d'événements déplacent la confiance :

- **Confirmation** (`validate_entry`) avec preuve externe vérifiable :
  sortie de test, chemin de fichier, documentation, autre entrée corroborante.
  La preuve la plus forte est `execution_verified` (le fait a été rejoué).
- **Contradiction** (`contradict_entry`) avec le même niveau d'exigence de
  preuve — jamais une simple désaccord d'opinion.

Chaque type de preuve a un poids dédié (réglable), et les événements identiques
sont dédupliqués sur une fenêtre de temps pour éviter le gonflement artificiel.

---

## Ajuster ces paramètres

Tout ce qui précède se règle dans `wpm.config.json`, section avancée
[`domain`](02-configuration.md) : `decay` (par type), `provenance`,
`evidence`, plus les seuils de `retrieval`.

La méthode de calibration complète — bancs d'essai, fonction objectif,
caveats par ancre et prochaines mesures — est détaillée dans la note de
travail [`../../internals/heuristic-calibration.md`](../../internals/heuristic-calibration.md).

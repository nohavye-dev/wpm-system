# Calibration de l'heuristique — ancres externes

Document de référence pour calibrer les paramètres du modèle de confiance
(decay λ, provenance, poids de preuve) sur des **mesures publiées**, plutôt
que sur des valeurs devinées.

Décrit la méthode générale de calibration (bancs d'essai, fonction objectif,
niveaux 1-4).

---

## Rappel : la formule de decay

```
confidence(t) = base × exp(−λ × t)
```

La **demi-vie** (temps pour que la confiance retombe à la moitié de sa
valeur initiale) vaut :

```
demi-vie = ln(2) / λ = 0.693 / λ
```

C'est cette demi-vie qu'on compare aux durées de vie observées.

---

## 1. Ancres solides (chiffrées, rigoureuses)

### 1.1 `bug_pattern` — durée de vie ≈ temps de résolution d'un bug

**Source :** « What Drives Issue Resolution Speed? An Empirical Study of
Scientific Software », arXiv 2512.18852. Mesure sur des dépôts logiciels
scientifiques : *« median resolution time of 18.09 days »*.

D'autres jeux de données publics réutilisables existent : Bugzilla Firefox
(étude de réplication, ScienceDirect S0164121217300365), Eclipse, Mozilla.

**Conversion en λ :** un `bug_pattern` vit ~18 jours en médiane. En visant
confiance ≈ 0.5 à la médiane :

```
λ = ln(2) / 18 jours = 0.693 / 18 = 0.0385/jour ≈ 0.0016/heure
```

| | λ | Demi-vie |
|---|---|---------|
| **Valeur dérivée** | 0.0016/h | ~18 jours |
| **Défaut actuel** | 0.015/h | ~1.9 jours |

**Le défaut actuel est ~10× trop agressif.**

*Caveat :* « bug fix time » = temps rapport → fix, qui est une **borne
inférieure** de la vraie durée de vie d'un bug (introduction → fix). Le λ
dérivé est donc prudent ; la vraie demi-vie est probablement encore plus
longue.

---

### 1.2 `doc` — prévalence du drift (qualitatif, rigoureux)

**Source :** Tan & Wagner, « Detecting outdated code element references in
software repository documentation », *Empirical Software Engineering*
(2023), DOI `10.1007/s10664-023-10397-6` (arXiv 2212.01479). Analyse de
plus de **3 000 projets GitHub** : la plupart contiennent au moins une
référence de code obsolète à un moment de leur histoire ; les références
obsolètes restent souvent **non corrigées pendant des années**.

- Implémentation publique : `github.com/wesleytanws/DOCER`
- Dataset : Zenodo `records/6517557`

**Limitation constatée lors du creusement du dataset :** DOCER mesure la
**prévalence** (combien de références obsolètes existent *maintenant*),
pas le **taux** de drift (pas de colonne timestamp/âge dans le CSV).
Conclusion qualitative : le decay de `doc` doit être **lent**, très
inférieur au défaut actuel. Pas de λ précis extractible sans ré-exécution.

---

## 2. Ancres indicatives (non rigoureuses — à confirmer)

### 2.1 `doc` — borne haute de drift

**Source :** statistique de blog vendeur (Driftless) : *« 60 % de la
documentation devient obsolète en 6 mois »*. Non revue par les pairs.

**Conversion :** S(6 mois) = 0.4 → λ = −ln(0.4)/6 mois = 0.916/6 =
0.153/mois → demi-vie = ln(2)/0.153 ≈ **4.5 mois**.

| | λ | Demi-vie |
|---|---|---------|
| **Borne indicative** | ~0.00021/h | ~4.5 mois |
| **Défaut actuel** | 0.004/h | ~7 jours |

À traiter comme une **borne haute provisoire**, clairement marquée non
rigoureuse — utile pour un premier fit, à remplacer par une mesure
rigoureuse dès que possible.

---

## 3. Valeurs provisoires (raisonnement de domaine, non mesurées)

Aucune ancre publiée trouvée pour `archi_decision`, `convention`, `insight`
et `execution_result`. Résolus par **raisonnement de domaine** (option A) :
ordre de grandeur cohérent avec les deux ancres mesurées, marqués « non
mesurés ».

| Type | λ/h (provisoire) | Demi-vie | Base |
|------|------------------|----------|------|
| `archi_decision` | 0.00008 | ~1 an | érosion architecturale lente (qualitatif) |
| `convention` | 0.00016 | ~6 mois | change sur décision d'équipe |
| `insight` | 0.001 | ~1 mois | découverte durable (entre `doc` et `bug_pattern`) |
| `execution_result` | 0.01 | ~3 jours | résultat de test/build, éphémère par conception |

**Note (scission `learning`) :** l'ancien type `learning` regroupait deux
durées de vie incompatibles (« ad-hoc insight » durable et « execution
result » éphémère). Il a été scindé en `insight` (durable) et
`execution_result` (éphémère), sans rétro-compatibilité (aucun projet ne
l'utilise encore).

**Options pour mesurer plus tard :** extraction GitHub ciblée (CHANGELOG,
guides de migration, commits de refactor/dépréciation) pour
archi_decision/convention/insight.

---

## 4. Synthèse : défauts précédents vs valeurs calibrées

| Type | Ancien défaut (λ/h) | Nouvelle valeur (λ/h) | Demi-vie | Fiabilité |
|------|--------------------|----------------------|----------|-----------|
| `archi_decision` | 0.002 | 0.00008 | ~1 an | raisonnement |
| `convention` | 0.003 | 0.00016 | ~6 mois | raisonnement |
| `doc` | 0.004 | 0.00021 | ~4.5 mois | indicative (borne) |
| `insight` | *(ex-learning 0.008)* | 0.001 | ~1 mois | raisonnement |
| `bug_pattern` | 0.015 | 0.0016 | ~18 jours | **mesurée** |
| `execution_result` | *(ex-learning 0.008)* | 0.01 | ~3 jours | raisonnement |

**Conclusion :** les anciens défauts étaient uniformément **trop
agressifs** (demi-vies de 2 à 14 jours). Les nouvelles valeurs allongent
les demi-vies d'un à deux ordres de grandeur, avec `bug_pattern` ancré sur
une mesure (18 jours) et `doc` sur une borne indicative. L'ordre relatif
est archi > convention > doc > insight > bug_pattern > execution_result
(lent → rapide).

*Note :* ces valeurs sont **appliquées dans le code** (`settings.py`) et
documentées dans `configuration.md`. Elles restent provisoires tant
que `archi_decision`/`convention`/`insight` ne sont pas mesurées.

---

## 5. Prochaine étape

1. Mesurer l'effet des nouveaux λ dans un banc d'essai de retrieval
   (le λ modifie le classement via `weight_confidence`).
2. Pour les valeurs raisonnées : décider entre extraction GitHub ciblée et
   maintien du raisonnement de domaine.
3. Remplacer la borne indicative de `doc` par une mesure rigoureuse
   (ré-exécution de DOCER avec timestamps, ou autre source).

---

## Sources citables

- arXiv 2512.18852 — « What Drives Issue Resolution Speed? » (médiane 18.09 j)
- Tan & Wagner (2023), *Empirical Software Engineering*, DOI 10.1007/s10664-023-10397-6 — DOCER, 3 000+ projets
- Bugzilla Firefox replication study, ScienceDirect S0164121217300365
- Driftless (blog vendeur) — « 60 % obsolète en 6 mois » (borne indicative)

# Calibration de l'heuristique — ancres externes

Document de référence pour calibrer les paramètres du modèle de confiance
(decay λ, provenance, poids de preuve) sur des **mesures publiées**, plutôt
que sur des valeurs devinées.

Complément du document [`viabilite-et-validation.md`](viabilite-et-validation.md),
qui décrit la méthode générale (bancs d'essai, fonction objectif, niveaux 1-4).

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

## 3. Gaps (à déterminer)

Aucune ancre publiée trouvée pour ces types. Ils restent sur leurs défauts
jusqu'à extraction ou raisonnement de domaine :

| Type | Défaut λ | Demi-vie implicite | Statut |
|------|---------|-------------------|--------|
| `archi_decision` | 0.002/h | ~14 jours | gap — probablement trop rapide aussi |
| `convention` | 0.003/h | ~10 jours | gap — probablement trop rapide aussi |
| `learning` | 0.008/h | ~3.6 jours | gap — le plus difficile (fourre-tout) |

**Options pour combler :** extraction GitHub ciblée (CHANGELOG, guides de
migration, commits de refactor/dépréciation) pour archi_decision/convention ;
raisonnement de domaine avec fourchette prudente pour learning.

---

## 4. Synthèse des écarts défauts vs ancres

| Type | Défaut (λ/h) | Ancre (λ/h) | Écart | Fiabilité de l'ancre |
|------|-------------|-------------|-------|----------------------|
| `bug_pattern` | 0.015 | ~0.0016 | ~10× trop rapide | **chiffrée** |
| `doc` | 0.004 | ~0.00021 | ~19× trop rapide | indicative (borne) |
| `archi_decision` | 0.002 | ? | ? | gap |
| `convention` | 0.003 | ? | ? | gap |
| `learning` | 0.008 | ? | ? | gap |

**Conclusion :** les défauts de decay actuels sont uniformément **trop
agressifs** — les faits perdent leur confiance beaucoup plus vite que la
réalité. La calibration commence par `bug_pattern` (ancré) et `doc` (borne
indicative), et laisse `archi_decision`/`convention`/`learning` en gap.

---

## 5. Prochaine étape

1. Appliquer les λ dérivés dans un banc d'essai de retrieval et mesurer
   l'effet (le λ modifie le classement via `weight_confidence`).
2. Pour les gaps : décider entre extraction GitHub ciblée et raisonnement
   de domaine.
3. Remplacer la borne indicative de `doc` par une mesure rigoureuse
   (ré-exécution de DOCER avec timestamps, ou autre source).

---

## Sources citables

- arXiv 2512.18852 — « What Drives Issue Resolution Speed? » (médiane 18.09 j)
- Tan & Wagner (2023), *Empirical Software Engineering*, DOI 10.1007/s10664-023-10397-6 — DOCER, 3 000+ projets
- Bugzilla Firefox replication study, ScienceDirect S0164121217300365
- Driftless (blog vendeur) — « 60 % obsolète en 6 mois » (borne indicative)

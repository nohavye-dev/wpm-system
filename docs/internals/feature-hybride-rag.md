# Injection hybride de mémoire (RAG) : pop-in + tool de recherche

## Contexte

Le système actuel expose la recherche de mémoire via un tool explicite : le LLM déclenche une requête, reçoit les x résultats les plus proches, et les analyse lui-même. Ce fonctionnement dépend entièrement du jugement du LLM pour décider *quand* chercher — avec le risque qu'il n'appelle pas l'outil alors qu'une mémoire pertinente existe.

Cette fiche propose un mode d'injection directe en complément du tool existant, formant une architecture hybride.

## Deux approches, deux tradeoffs

### Injection directe (pop-in)

Un hook déterministe (dans la logique de `tool.execute.after` / `session.idle` déjà utilisés côté plugin) effectue la recherche vectorielle en arrière-plan et splice automatiquement les meilleurs résultats dans le contexte, sans intervention du LLM.

**Avantages :**
- Pas de dépendance au jugement du LLM pour déclencher la recherche
- Pas d'aller-retour supplémentaire (latence, tokens de schéma d'outil)
- Garantit qu'une mémoire à haute confiance est toujours présente en contexte

**Limites :**
- La requête de recherche est le message brut de l'utilisateur, jamais reformulée — moins précis qu'une requête pensée par le LLM
- Aucune itération possible si les résultats sont mauvais
- Risque de pollution de contexte si le seuil de pertinence est mal calibré
- Perte de traçabilité : plus difficile d'auditer pourquoi une mémoire a été injectée

### Tool de recherche actif

Le LLM reste libre d'appeler un outil de recherche sémantique, avec sa propre reformulation de requête et la possibilité d'itérer.

**Avantages :**
- Requête reformulée par le LLM, généralement plus précise que le texte brut
- Itération possible (relancer avec une autre requête si les résultats sont mauvais)
- Traçabilité claire de l'usage de la mémoire

**Limites :**
- Dépend du LLM pour décider de chercher — risque d'omission
- Coût de latence et de tokens à chaque appel

## Mode proposé : hybride à seuil de confiance

Combiner les deux mécanismes plutôt que choisir l'un ou l'autre, en s'appuyant sur le scoring de confiance déjà présent dans l'architecture WPM.

| Score de confiance | Comportement |
|---|---|
| Élevé | Injection directe et silencieuse via hook déterministe. Peu de résultats (haute précision, pas de bruit). |
| Faible / incertain | Pas d'injection automatique. Le tool de recherche reste disponible pour que le LLM creuse avec une requête reformulée. |

### Principe de fonctionnement

1. À chaque tour de conversation (ou à un point de hook défini), une recherche vectorielle est effectuée en arrière-plan sur le message courant.
2. Si le(s) résultat(s) dépasse(nt) le seuil de confiance haut : injection directe dans le contexte, sans passer par un tool call.
3. Si aucun résultat ne dépasse ce seuil : rien n'est injecté automatiquement, mais le tool de recherche sémantique reste disponible pour un appel explicite du LLM si besoin.

## Bénéfices attendus

- **Fiabilité** : les mémoires les plus pertinentes sont garanties d'être présentes en contexte, sans dépendre d'une décision du LLM.
- **Contrôle du bruit** : seuil élevé + peu de résultats évite la pollution de contexte sur les cas ambigus.
- **Flexibilité conservée** : le LLM garde la main pour les cas incertains, avec reformulation de requête et itération.
- **Cohérence avec l'architecture existante** : s'appuie sur le scoring de confiance et les hooks déterministes déjà en place (`tool.execute.after`, `session.idle`, `session.compacting`).

## Points de vigilance

- **Calibration du seuil** : un seuil trop bas génère du bruit systématique, un seuil trop haut réduit l'utilité du pop-in. À valider empiriquement sur un échantillon de requêtes réelles.
- **Nombre de résultats injectés** : le pop-in doit rester restreint (peu de résultats) pour ne pas saturer le contexte à chaque tour.
- **Traçabilité du pop-in** : même sans tool call, il est utile de logger quelles mémoires ont été injectées automatiquement, pour audit et debug du seuil.
- **Interaction avec la migration d'embedding multilingue** : la fiabilité du score de confiance dépend directement de la qualité de l'embedding sur le français. La migration vers un modèle multilingue est désormais **implémentée** (voir `migration-embedding.md`) — le prérequis d'un seuil de pop-in fiable en français est satisfait ; reste la validation empirique du seuil.

## Étapes de mise en œuvre (proposition)

1. Définir le point de hook déclenchant la recherche en arrière-plan (avant/pendant l'envoi du message au LLM).
2. Implémenter la logique de seuil (haut = injection directe, bas = pas d'injection, tool reste actif).
3. Limiter strictement le nombre de résultats injectés en mode pop-in.
4. Ajouter un logging des injections automatiques pour audit.
5. Tester la calibration du seuil sur un échantillon représentatif de
   requêtes (la migration vers un embedding multilingue étant en place).
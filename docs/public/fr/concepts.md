# Concepts — comprendre WPM sans jargon

Ce document explique **ce que fait WPM et pourquoi**, avec le moins de
technique possible. Pour la mécanique précise (schéma de données, formules,
protocole), voir [`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md) et
[`configuration.md`](configuration.md).

---

## Le problème

Un agent IA travaille dans un **contexte limité et éphémère**. Quand il
découvre une décision d'architecture, une convention de code ou un bug
récurrent, cette information vit dans sa conversation en cours… puis
disparaît à la session suivante. Résultat : chaque nouvelle session
repart de zéro, re-lit le code, re-devine ce qui avait déjà été compris.

**WPM résout ça** : il donne à l'agent une **mémoire persistante, propre au
projet**, qui survit aux sessions.

---

## L'idée en une phrase

> Un carnet de notes partagé entre toutes les sessions de l'agent, où chaque
> note a un **degré de fiabilité** qui évolue dans le temps.

Ce qui distingue WPM d'un simple stockage de notes, c'est que chaque
information est **pondérée** : on sait à quel point on peut lui faire
confiance, et cette confiance est entretenue ou érodée selon ce qui se
passe ensuite.

---

## Les concepts, un par un

### 1. La mémoire du projet

Tout ce que l'agent juge durable sur un projet est consigné : décisions
d'architecture, conventions, patterns de bugs, résultats de tests. Cette
mémoire est stockée **localement, dans le projet** (un fichier SQLite dans
un dossier `.wpm/`), pas dans le cloud.

*Analogie : un wiki interne au projet, alimenté automatiquement pendant le
travail, au lieu d'une documentation écrite à la main et vite obsolète.*

### 2. La confiance pondérée

Chaque entrée de mémoire porte un **score de confiance entre 0 et 1**.
Une entrée à 0.9 est une quasi-certitude ; à 0.3, une intuition fragile.
Ce score n'est pas décoratif : c'est lui qui décide si une information est
montrée à l'agent, et avec quel poids.

*Analogie : une note « à vérifier » vs une note « confirmée par trois
sources ». On ne les traite pas de la même façon.*

### 3. La provenance : d'où vient l'information ?

La confiance **de départ** dépend de l'origine du fait :

| Source | Confiance de départ | Exemple |
|---|---|---|
| Documentation officielle lue | haute | « la doc du framework dit que… » |
| Code observé directement | moyenne-haute | « ce fichier fait X » |
| Résultat d'une commande réellement exécutée | moyenne | « le test passe » |
| Déduction de l'agent, sans preuve | basse | « je suppose que… » |

Une hypothèse reste une hypothèse, même si elle semble solide : elle part
avec une confiance basse, et c'est normal.

*Analogie : une source primaire vaut plus qu'une rumeur.*

### 4. La décroissance (decay)

Une information qui n'est **plus confirmée depuis longtemps** s'érode :
son score baisse lentement avec le temps. Le rythme dépend du type
d'information — une décision d'architecture reste fiable ~1 an, un résultat
de test seulement quelques jours.

*Analogie : un mot de passe noté il y a trois mois n'est plus fiable ; un
principe de conception, si.*

### 5. Les preuves : comment la confiance monte

Une entrée ne gagne en confiance qu'avec des **preuves externes et
vérifiables** : un test qui passe, une seconde source qui confirme, une
réutilisation sans échec. Le simple « je pense que c'est vrai » ne fait
**jamais** monter le score.

*Analogie : on ne valide pas une hypothèse en la répétant, mais en la
testant.*

### 6. La contradiction, jamais la suppression

Quand une information se révèle fausse ou dépassée, WPM ne **supprime
jamais** l'ancienne entrée : il enregistre une **contradiction** (avec sa
preuve). L'ancienne entrée reste visible, son score chute plus vite qu'une
confirmation ne le ferait monter — et l'historique reste traçable.

*Analogie : on barre une ligne dans le carnet plutôt que de l'arracher, pour
garder la trace de ce qu'on a révisé et pourquoi.*

### 7. Le rappel hybride (vecteur + graphe)

Quand l'agent cherche « tout ce qu'on sait sur X », WPM combine deux
mécanismes :
- la **similarité sémantique** (trouver les notes qui parlent de la même
  chose, même avec des mots différents) ;
- le **graphe de liens** (suivre les relations entre notes pour remonter des
  informations liées mais pas identiques).

Le résultat distingue les **correspondances directes** (fiables) du
**contexte associatif** (lié, donc à mentionner avec prudence).

*Analogie : une recherche qui trouve non seulement l'article exact, mais
aussi les pages liées qui éclairent le contexte.*

### 8. Les règles du projet

WPM recompose automatiquement un résumé des **conventions et décisions les
plus fiables** du projet (le bloc « project-rules »), que l'agent lit en
début de session. C'est ce qui lui permet de respecter les usages du projet
sans qu'on les lui réexplique à chaque fois.

*Analogie : la page « règles de la maison » du wiki, mise à jour toute
seule à partir des notes les plus fiables.*

### 9. La mémorisation au fil de l'eau

L'agent note les faits durables **dès qu'ils émergent**, pendant son
travail, plutôt que de tout écrire à la fin (où une partie serait déjà
perdue). C'est ce qui rend la mémoire vivante et à jour.

*Analogie : prendre ses notes en réunion plutôt qu'essayer de tout
reconstituer une semaine plus tard.*

---

## Comment tout cela s'articule

```
              travail agent:
              ┌─────────────────────────────────────────┐
              │  au fil de l'eau : « tiens, un fait     │
              │  durable » → store_entry (avec source)  │
              └─────────────────┬───────────────────────┘
                                ▼
                      ┌────────────────────┐   chaque entrée a une confiance qui vit :
                      │  base de mémoire   │   
                      │  (SQLite locale)   │     • monte (preuves)
                      └────────────────────┘     • baisse (temps, contradictions)
                                │                
                                ▼
              ┌───────────────────────────────────────┐
              │  quand l'agent a besoin d'infos :     │
              │  query_context → les notes fiables    │
              │  remontent, les incertaines restent   │
              │  en retrait ou signalées              │
              └───────────────────────────────────────┘
```

L'agent n'a pas besoin de « gérer » la mémoire : il écrit au fil de l'eau
et interroge quand il a besoin d'un contexte. Le système s'occupe de la
fiabilité.

---

## Ce que ça résout (objectifs)

- **Continuité** : les sessions ne repartent plus de zéro.
- **Fiabilité** : on distingue ce qui est sûr de ce qui est supposé, et on
  ne laisse pas une information fausse polluer les décisions.
- **Traçabilité** : les révisions et contradictions restent visibles, pas
  d'écrasement silencieux.
- **Zéro friction** : l'agent mémorise pendant son travail ; pas de
  configuration à maintenir à la main.

---

## Limites (le projet est en phase d'essais)

WPM est une **expérience en cours**. Le modèle de confiance (vitesses de
décroissance, poids, seuils) est calé sur des valeurs **raisonnées mais
encore peu mesurées** ; il faudra le valider sur de vrais projets longs.
Voir [`docs/internals/`](https://github.com/nohavye-dev/wpm-system/tree/main/docs/internals) pour les notes de conception et le plan de
validation.

---

## Pour aller plus loin

- [`setup.md`](setup.md) — installer et activer WPM sur un projet.
- [`workflows.md`](workflows.md) — les commandes `wpm-learn`, `wpm-map`, `wpm-bootstrap`, `wpm-audit`, `wpm-patterns`, `wpm-persist`.
- [`agent-behavior.md`](agent-behavior.md) — le détail de ce que l'agent doit faire.
- [`wpm-mcp-server/README.md`](https://github.com/nohavye-dev/wpm-system/blob/main/wpm-mcp-server/README.md) — l'aspect technique du serveur.

# Calibration du seuil RAG et validation end-to-end du rappel automatique

> **Statut : validé empiriquement** (2026-08-25, session wpm-site).
> Le seuil par défaut `rag_similarity_threshold = 0.45` était trop haut pour
> le corpus réel ; abaissé à 0.3 en config projet, puis prouvé fonctionnel
> jusqu'au contexte modèle par un test à l'aveugle avec agent vierge.

## Contexte

Le plugin pousse un bloc `<wpm-memory-recall>` à chaque tour (hook
`experimental.chat.system.transform` → `buildRecallBlock`, `system-push.ts`) :
query_context sur le dernier message utilisateur, filtres
similarity ≥ ragSimilarityThreshold ET confidence ≥ confidenceFloor,
dédoublonnage contre project-rules, top ragMaxItems.
Constat initial : aucun bloc jamais observé en conditions normales.

## Méthodologie

1. Audit du pipeline (code plugin) → fonctionnalité complète, échecs silencieux
2. Traces auditables `rag decision` dans le log opencode (candidates/picked/top_sim)
3. Tests contrôlés : question ciblée FR, contrôle EN, formulation naturelle
4. Test à l'aveugle final : entrée secrète + agent vierge en session séparée

## Mesures (2026-08-25)

| Test | Query | top_sim | picked |
|---|---|---|---|
| Question ciblée FR | « Comment ajouter une nouvelle page de documentation... » | 0.4424 | 0 |
| Contrôle EN | « How do I add a new documentation page... » | 0.3027 | 0 |
| Tours naturels FR | diverses | 0.60–0.65 | 2–3 |

Corpus : 109 entrées actives (~53 EN anciennes, ~29 FR récentes).
Écart intra/cross-lingue confirmé : FR→FR ≈ 0.60–0.65, FR→EN/mixte ≈ 0.24–0.44
(attendu — « points de vigilance » n°1 de [migration-embedding.md](migration-embedding.md)).

## Diagnostic : deux verrous distincts

1. **Similarité (goulot principal)** : seuil 0.45 inaccessible pour des
   questions conversationnelles même parfaitement alignées (échec à 0.008 près).
2. **Confiance (filtre secondaire sain)** : `confidenceFloor 0.5` exclut les
   entrées jeunes/non validées même similaires (cas mesuré : sim 0.577 /
   conf 0.35) ; comportement voulu — probation des nouvelles entrées et sortie
   naturelle des contredites. À NE PAS baisser.

Note : l'entrée pourtant la plus pertinente (archi_decision, conf 0.9995)
ne sortait pas du retrieval vectoriel lui-même — notes techniques denses vs
questions conversationnelles : limite structurelle de l'embedding, indépendante
des seuils.

## Correctif appliqué

`wpm-site/wpm.config.json` : `"rag_similarity_threshold": 0.3` (config-only,
schéma existant, redémarrage requis). Re-test immédiat : picked=3 dont une
entrée à sim 0.4242 (< ancien 0.45 → preuve interne du nouveau seuil actif).

## Validation end-to-end (test à l'aveugle)

Mot-code unique stocké uniquement en base (`01cda5f4…`, conf 0.7). Agent vierge,
session séparée, question posée « sans utiliser tes outils mémoire » :
l'agent a restitué le mot correctement. Logs corroborent : `rag decision`
picked=3 incluant cette exacte entrée (sim 0.7535) sur SA session.
→ Chaîne complète prouvée : stockage → retrieval → buildRecallBlock →
injection system prompt → connaissance effective du modèle.
(Entrée secrète déprécatée après usage.)

## Restes

- Option B : défaut code `DEFAULT_RAG_SIMILARITY_THRESHOLD` 0.45 → 0.35
  (+ test unitaire) pour généraliser sans config locale
- Clôturer les étapes 4-5 de [migration-embedding.md](migration-embedding.md)
  (fait via ce document)
- Synchroniser repo ↔ install globale du plugin (fichiers `preferences.*`
  présents seulement dans l'install)

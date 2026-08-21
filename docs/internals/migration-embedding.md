# Migration vers un modèle d'embedding multilingue

> **Statut : implémenté** (étapes 1-3 ci-dessous). Le modèle par défaut est
> `paraphrase-multilingual-MiniLM-L12-v2` (ONNX quantifié ~120 MB, float32
> ~470 MB), dimension 384 (`EMBEDDING_DIM` dans `core/constants.py`). Le
> contenu est stocké en langue native (plus de traduction). La ré-embedding
> se fait via `wpm reembed` (`reembed_all`, `storage/lifecycle.py`), et une
> garde (`model_guard.ensure_embedding_model`) bloque toute requête si le
> modèle actif diffère de celui de la base. Les étapes 4-5 (validation du
> seuil de confiance FR et du recall cross-lingue) restent en phase d'essais.
> Surcharge du modèle via `WPM_EMBEDDING_MODEL`.

## Contexte

Le système de mémoire pondérée (`wpm-system`) utilise actuellement **all-MiniLM-L6-v2** pour générer les embeddings stockés dans sqlite-vec. Ce modèle est entraîné quasi exclusivement en anglais, ce qui impose aujourd'hui une contrainte de normalisation : tout le contenu est traduit/stocké en anglais avant embedding, afin de garantir une similarité sémantique fiable.

Cette fiche propose de lever cette contrainte via une migration vers un modèle d'embedding multilingue.

## Problème actuel

- **Biais structurel sur le français** : all-MiniLM-L6-v2 produit des similarités cosinus moins fiables sur du texte français, indépendamment de la pertinence réelle du contenu.
- **Impact direct sur le scoring de confiance** : dans un système de confidence-weighted retrieval, un score biaisé à la baisse pour le français fausse le seuil de pop-in (injection directe en contexte).
- **Étape de traduction nécessaire** : le contenu doit être normalisé en anglais avant stockage, ce qui ajoute une transformation, une latence, et une perte sémantique (traduction imparfaite, surtout sur du jargon technique dev).

## Solution proposée

Remplacer all-MiniLM-L6-v2 par un modèle d'embedding multilingue, et stocker le contenu directement en langue native (français, avec code-switching technique EN/FR tel quel — noms de fonctions, termes techniques).

### Modèle recommandé : paraphrase-multilingual-MiniLM-L12-v2

| Critère | Détail |
|---|---|
| Paramètres | 118M |
| Dimension d'embedding | 384 (identique à MiniLM-L6, compatible avec le schéma sqlite-vec existant) |
| Langues | 50+ |
| Taille disque (float32) | ~470 Mo |
| Taille disque (ONNX quantifié int8) | ~120-150 Mo |
| Licence | Apache 2.0 |

**Alternatives possibles :**
- `multilingual-e5-large` / `BGE-M3` — meilleure qualité, mais dimension 1024 (impact taille base + vitesse de recherche)
- `multilingual-e5-small` — compromis taille/perf si contrainte de légèreté forte

### Compatibilité technique

- Exports ONNX officiels disponibles (variante quantifiée incluse dans le repo HuggingFace).
- Utilisable directement via `onnxruntime` + `tokenizers` (HF, Rust-backed) en Python, sans dépendance PyTorch lourde.
- Chargement paresseux de la session ONNX compatible avec la contrainte de lazy imports du projet (pas de chargement au niveau module).

## Bénéfices attendus

1. **Suppression de la contrainte de normalisation anglaise** — le pipeline de génération de mémoire n'a plus besoin d'une étape de traduction avant stockage.
2. **Fidélité sémantique accrue** — contenu stocké tel qu'écrit (français natif + code-switching technique), sans perte due à la traduction.
3. **Scoring de confiance non biaisé par la langue** — le seuil de pop-in devient fiable sur le français, langue majoritaire du corpus.
4. **Simplification du pipeline** — une étape en moins entre écriture et stockage.

## Points de vigilance

- **Retrieval cross-lingue imparfait** : une requête FR matchant un contenu EN reste légèrement moins précise qu'un match intra-langue. Non bloquant si l'usage reste majoritairement français, à tester si le corpus est mixte.
- **Hétérogénéité du corpus existant** : les mémoires déjà stockées sont en anglais normalisé ; le nouveau contenu sera en français natif. Cherchable dans les deux cas, mais corpus non homogène après migration.
- **Re-embedding complet obligatoire** : les espaces vectoriels de MiniLM-L6 et du modèle multilingue ne sont pas compatibles. Toutes les entrées existantes doivent être ré-embeddées, pas seulement les nouvelles.

## Étapes de migration (proposition)

1. Intégrer paraphrase-multilingual-MiniLM-L12-v2 (variante ONNX quantifiée) dans le pipeline d'embedding.
2. Ré-embedder l'intégralité des entrées existantes de la base sqlite-vec.
3. Supprimer l'étape de normalisation/traduction anglaise du pipeline de génération de mémoire.
4. Valider le comportement du seuil de confiance sur un échantillon de requêtes françaises avant/après migration.
5. Tester le recall cross-lingue si le corpus contient une proportion significative de contenu anglais.
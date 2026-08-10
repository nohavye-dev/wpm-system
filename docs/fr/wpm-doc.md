---
description: Ingérer un document markdown dans la mémoire persistante, découpé par section
agent: build
subtask: true
---

> Garde : si `wpm.config.json` n'existe pas à la racine du projet, la mémoire n'est pas activée. Expliquez poliment à l'utilisateur qu'il doit lancer `wpm enable` (puis redémarrer opencode) et arrêtez-vous sans rien faire d'autre.

Vous ingérez un document markdown dans le système de mémoire persistante du
projet (le serveur MCP `wpm-server` : `store_entry`, `query_context`,
`validate_entry`, `contradict_entry`, `link_entries`).

<document_path>
$ARGUMENTS
</document_path>

Suivez ces étapes exactement :

1. **Lisez le fichier** situé au chemin indiqué. Si aucun chemin n'a été
   fourni, demandez-en un et arrêtez-vous — ne devinez pas de fichier.

2. **Découpez-le en sections** le long de ses titres `##`/`###` (ou en
   paragraphes logiques s'il n'a pas de titres). Chaque section devient UNE
   entrée de mémoire candidate. Ne stockez PAS tout le fichier comme une
   seule entrée — cela détruit la granularité de récupération (un vecteur
   moyenné unique, aucun moyen de relier une section précise à une décision
   d'architecture précise).

3. **Pour chaque section**, avant de la stocker :
   a. Appelez `query_context` avec une requête courte résumant le sujet de
      la section, `min_confidence: 0.3`.
   b. Si un direct_match avec une similarité supérieure à ~0.85 existe déjà
      et correspond clairement au même fait : ne créez PAS de doublon.
      Appelez plutôt `validate_entry` dessus avec
      `evidence_type: "cross_reference"` et `evidence_ref` pointant vers ce
      chemin de fichier — il s'agit d'une re-confirmation, pas d'un nouveau
      fait.
   c. Sinon, appelez `store_entry` :
      - `content` : le contenu de la section, TRADUIT EN ANGLAIS si la
        source est en français (cohérence des embeddings — voir les
        conventions du projet), reformulé de façon concise (pas de
        remplissage, pas de titres répétés), PAS un copier-coller à
        l'identique des artefacts de mise en forme.
      - `type` : déduisez le meilleur type —
        `doc` (par défaut pour un contenu explicatif/de référence),
        `archi_decision` (la section décrit un choix structurel),
        `convention` (une règle de codage/dénomination/processus),
        `bug_pattern` (un problème connu et sa cause).
      - `source` : `"official_doc"` (il s'agit d'une ingestion manuelle et
        délibérée d'un vrai document, pas d'une inférence).

4. **Reliez les sections liées** entre elles avec `link_entries` lorsqu'une
   section dépend clairement d'une autre ou l'affine (par ex. une section
   convention qui n'a de sens qu'à la lumière d'une section architecture
   située plus haut dans le même document) — ne sur-reliez pas, uniquement
   lorsque la relation est explicite dans le texte.

5. **Rendez compte** d'un résumé court : combien de sections ont été
   stockées comme nouvelles entrées, combien ont été dédupliquées/revalidées
   à la place, et toute section que vous avez ignorée et pourquoi (par ex.
   trop vague pour être un fait autonome utile).

Ne demandez pas de confirmation avant chaque appel individuel à
`store_entry` — parcourez tout le document, puis rendez compte du résumé à
la fin.

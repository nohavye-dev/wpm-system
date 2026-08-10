---
description: Cartographier l'architecture et les conventions de la base de code dans la mémoire persistante
agent: build
subtask: true
---

> Garde : si `wpm.config.json` n'existe pas à la racine du projet, la mémoire n'est pas activée. Expliquez poliment à l'utilisateur qu'il doit lancer `wpm enable` (puis redémarrer opencode) et arrêtez-vous sans rien faire d'autre.

Vous cartographiez la structure de cette base de code dans le système de
mémoire persistante du projet (le serveur MCP `wpm-server` : `store_entry`,
`query_context`, `validate_entry`, `contradict_entry`, `link_entries`).

<scope>
$ARGUMENTS
</scope>

Si `<scope>` est vide, cartographiez tout le projet. S'il nomme un
chemin/module, limitez la cartographie à ce sous-arbre.

Il ne s'agit PAS d'un index fichier par fichier — cela inonderait la mémoire
de bruit et n'apporterait aucune valeur de récupération. Vous extrayez un
petit nombre de faits structurels durables et à forte valeur qu'un ingénieur
voudrait se rappeler des mois plus tard.

Suivez ces étapes :

1. **Passez en revue la structure** — listez l'arborescence des répertoires
   du périmètre (en respectant .gitignore ; ignorez les artefacts de build,
   node_modules, bin/obj, dist, .venv, etc.). Identifiez les principales
   couches/modules et ce dont chacun est responsable.

2. **Lisez suffisamment de code réel** pour étayer vos constatations —
   points d'entrée clés, classes/modules les plus centraux par couche,
   README/docs existants dans le périmètre, fichiers projet/config (par ex.
   .csproj, package.json). N'inférez pas l'architecture uniquement à partir
   des noms de dossiers sans vérifier que le code correspond réellement.

3. **Identifiez des faits durables**, chacun devenant UNE entrée candidate :
   - `archi_decision` — un choix structurel réellement observé dans le code
     (par ex. « le pipeline de synchronisation des données sépare l'analyse
     DWG (ODA SDK) de la couche API via un DTO intermédiaire »).
     N'enregistrez que les décisions pour lesquelles vous pouvez pointer des
     preuves concrètes, pas des suppositions.
   - `convention` — un modèle de dénomination/style/gestion des erreurs
     suivi de manière cohérente dans plusieurs fichiers (pas un cas isolé).
   - `bug_pattern` — uniquement si vous trouvez un problème connu documenté
     (par ex. un commentaire, un TODO expliquant une solution de
     contournement, une référence à un tracker d'issues existant) — ne
     spéculez pas sur des bogues que vous n'avez pas vérifiés.

   Ignorez tout ce dont vous n'êtes pas raisonnablement sûr — une mauvaise
   entrée d'architecture est pire qu'une entrée manquante (elle induit
   activement en erreur la récupération future).

4. **Pour chaque fait candidat**, avant de le stocker :
   a. Appelez `query_context` avec une requête courte sur le sujet,
      `min_confidence: 0.3`.
   b. Si un direct_match très similaire existe déjà : appelez
      `validate_entry` dessus à la place, avec
      `evidence_type: "execution_verified"` si vous avez réellement suivi le
      chemin de code, sinon `evidence_type: "cross_reference"`,
      `evidence_ref` défini sur le(s) chemin(s) de fichier que vous avez
      vérifié(s).
   c. Sinon, `store_entry` :
      - `content` : en anglais, concis, nommant les fichiers/modules réels
        impliqués (par ex. « APCWebSystem : le pipeline MassImport valide
        les charges utiles par rapport au schéma de l'API Astech dans
        `Services/MassImport/*` avant de les persister »).
      - `type` : `archi_decision`, `convention` ou `bug_pattern` comme
        ci-dessus.
      - `source` : `"observed_code"` — cela a été lu directement dans la
        base de code, pas inféré ou deviné.

5. **Reliez les entrées** avec `link_entries` lorsque la relation est
   explicite dans le code (une convention qui implémente une décision
   d'architecture énoncée, un bug_pattern qui découle d'une
   archi_decision spécifique).

6. **Rendez compte** : une courte liste de ce qui a été stocké (groupé par
   type), de ce qui a été revalidé au lieu d'être dupliqué, et — surtout —
   tout ce que vous avez envisagé mais ignoré parce que vous n'étiez pas
   assez confiant pour l'enregistrer comme fait durable.

Ne demandez pas de confirmation avant chaque appel individuel à
`store_entry` — effectuez l'étude complète, puis rendez compte du résumé à
la fin.

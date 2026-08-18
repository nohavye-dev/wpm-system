# Guide de développement des plugins OpenCode

Guide complet pour écrire des plugins OpenCode qui étendent le comportement de l'agent via des hooks, des tools personnalisés, des fournisseurs d'authentification et la gestion d'événements.

**Fichiers source à connaître (côté OpenCode) :**

- Types et interfaces du plugin : `packages/plugin/src/index.ts`
- Utilitaires de définition de tools : `packages/plugin/src/tool.ts`
- Intégration shell : `packages/plugin/src/shell.ts`
- Plugin d'exemple : `packages/plugin/src/example.ts`
- Système de chargement des plugins : `packages/opencode/src/plugin/index.ts`
- Intégration au registre de tools : `packages/opencode/src/tool/registry.ts`
- Intégration des fournisseurs d'authentification : `packages/opencode/src/provider/provider.ts`
- Hooks du système de permissions : `packages/opencode/src/permission/index.ts`
- Hooks de prompt de session : `packages/opencode/src/session/prompt.ts`

> **⚠️ Correction par rapport aux deux sources précédentes.** La documentation officielle (mirroir de `opencode.ai/docs/plugins`, tag `v1.14.48`) indique `.opencode/plugins/` et `~/.config/opencode/plugins/` — **au pluriel**. Les deux guides fusionnés ici plus tôt indiquaient `.opencode/plugin/` au singulier, ce qui est incohérent avec la doc officielle. Je retiens le pluriel comme référence dans tout ce document à partir d'ici, et je le signale explicitly puisque `wpm-opencode-plugin/plugin.ts` doit être placé au bon endroit pour être chargé — à vérifier concrètement (un plugin dans le mauvais répertoire ne provoque pas forcément d'erreur visible, juste un chargement silencieusement absent).

## Démarrage rapide

1. Créez un fichier TypeScript dans `.opencode/plugins/` (au niveau du projet) ou `~/.config/opencode/plugins/` (global)
2. Exportez une fonction de plugin nommée
3. Redémarrez OpenCode

```ts
import type { Plugin } from "@opencode-ai/plugin"

export const MyPlugin: Plugin = async ({ client }) => {
  console.log("Plugin chargé !")

  return {
    // les hooks vont ici
  }
}
```

### Deux façons de charger un plugin

**Depuis des fichiers locaux** — les fichiers JS/TS placés dans `.opencode/plugins/` (projet) ou `~/.config/opencode/plugins/` (global) sont chargés automatiquement au démarrage.

**Depuis npm** — en les déclarant dans `opencode.json` :

```json title="opencode.json"
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["opencode-helicone-session", "opencode-wakatime", "@my-org/custom-plugin"]
}
```

Les packages npm scopés (`@org/nom`) et non scopés sont tous deux supportés. Les plugins npm sont installés automatiquement via Bun au démarrage ; packages et dépendances sont mis en cache dans `~/.cache/opencode/node_modules/`. Les plugins locaux, eux, sont chargés directement depuis le répertoire de plugins — pour utiliser des packages externes avec un plugin local, il faut un `package.json` dans le répertoire de config (voir Dépendances externes plus bas), ou publier le plugin sur npm.

**Règle de déduplication au chargement** : deux packages npm identiques (même nom, même version) ne sont chargés qu'une fois. En revanche, un plugin local et un plugin npm portant des noms proches sont chargés séparément, sans déduplication entre eux.

### Créer un package de plugin dédié (recommandé pour la distribution)

```bash
mkdir my-opencode-plugin
cd my-opencode-plugin
bun init
```

**Dépendances (`package.json`) :**

```json
{
  "dependencies": {
    "@opencode-ai/plugin": "latest",
    "@opencode-ai/sdk": "latest",
    "zod": "latest"
  },
  "devDependencies": {
    "@types/node": "latest",
    "typescript": "latest"
  }
}
```

**Configuration TypeScript (`tsconfig.json`) :**

```json
{
  "extends": "@tsconfig/node22/tsconfig.json",
  "compilerOptions": {
    "outDir": "dist",
    "module": "preserve",
    "declaration": true,
    "moduleResolution": "bundler"
  },
  "include": ["src"]
}
```

## Signature de la fonction de plugin

**CRITIQUE** : la fonction de plugin reçoit un **objet de contexte** (`ctx`), pas des paramètres individuels.

```ts
// ✅ CORRECT - déstructurez ce dont vous avez besoin
export const MyPlugin: Plugin = async ({ client, project, $, directory }) => {
  await client.session.prompt({ ... })
}

// ❌ INCORRECT - traiter le contexte comme le client
export const MyPlugin: Plugin = async (client) => {
  await client.session.prompt({ ... })  // ÉCHOUE : context.session.prompt n'existe pas
}
```

### Propriétés de l'objet de contexte (`ctx`)

| Propriété | Type | Description |
|----------|------|-------------|
| `ctx.client` | SDK Client | SDK OpenCode pour les appels API (`localhost:4096`) |
| `ctx.project.id` | string | Identifiant du projet (hash git ou `"global"`) |
| `ctx.project.worktree` | string | Racine du worktree Git |
| `ctx.project.vcs` | string \| undefined | Système de contrôle de version (`"git"` ou undefined) |
| `ctx.directory` | string | Répertoire de travail courant |
| `ctx.worktree` | string | Alias de `ctx.project.worktree` |
| `` ctx.$`command` `` | Shell | API shell de Bun pour exécuter des commandes |
| `` ctx.$`git status`.text() `` | — | Commande shell avec méthodes de récupération de sortie |

Documentation du client : https://opencode.ai/docs/sdk/#app

## Liste complète des événements

> Source de référence pour cette section : doc officielle `opencode.ai/docs/plugins` (tag `v1.14.48`). Deux noms diffèrent de ceux listés dans les guides précédents — signalés ci-dessous plutôt que corrigés silencieusement.

**Événements de session :**
- `session.created` — nouvelle session créée
- `session.updated` — session mise à jour
- `session.deleted` — session supprimée
- `session.error` — erreur de session survenue
- `session.idle` — la session est devenue inactive (tout le traitement du message en cours est terminé)
- `session.compacted` — la compaction de session vient de se terminer *(absent des deux guides précédents)*
- `session.diff` — diff de session *(absent des deux guides précédents, nature exacte non détaillée dans la doc source)*
- `session.status` — changement de statut de session *(absent des deux guides précédents ; à distinguer de `session.idle`, potentiellement plus général — sens exact à vérifier en le loggant une fois)*

**Événements de message :**
- `message.updated` — message mis à jour
- `message.removed` — message supprimé
- `message.part.updated` — partie de message mise à jour
- `message.part.removed` — partie de message supprimée

**Événements de fichiers :**
- `file.edited` — fichier modifié
- `file.watcher.updated` — le watcher de fichiers a détecté un changement (ajout/modification/suppression)

**Événements de permissions :**
- `permission.asked` — une permission est demandée *(la source officielle nomme cet événement `permission.asked`, pas `permission.updated` comme indiqué dans un guide précédent — à ne pas confondre non plus avec le hook `permission.ask`, qui est un mécanisme différent servant à répondre à la demande, pas à s'y abonner)*
- `permission.replied` — réponse à une demande de permission reçue

**Événements serveur :**
- `server.connected` — serveur connecté

**Événements LSP :**
- `lsp.updated` — Language Server Protocol mis à jour
- `lsp.client.diagnostics` — diagnostics LSP disponibles *(nommé `lsp.diagnostics` dans un guide précédent — la doc officielle utilise `lsp.client.diagnostics`)*

**Événements de commande :**
- `command.executed` — commande exécutée

**Événements todo :**
- `todo.updated` — liste de tâches (todo) mise à jour *(absent des deux guides précédents)*

**Événements shell :**
- `shell.env` — l'environnement shell est sur le point d'être construit pour une exécution ; voir le hook associé plus bas pour l'utiliser en écriture, pas seulement en lecture *(absent des deux guides précédents)*

**Événements de tool :**
- `tool.execute.before`, `tool.execute.after`

**Événements TUI :**
- `tui.prompt.append` — texte ajouté au prompt de l'interface texte
- `tui.command.execute` — commande exécutée dans la TUI
- `tui.toast.show` — notification affichée dans la TUI

**Autres événements :**
- `installation.updated` — installation mise à jour

`ide.installed`, présent dans un guide précédent, n'apparaît pas dans la
liste de la documentation officielle — probablement une extension
non documentée ou une divergence de version, à vérifier plutôt que
supposer qu'il fonctionne.

## Hooks disponibles

### Vue d'ensemble — tous les hooks dans un seul plugin

```typescript
import { Plugin, tool } from '@opencode-ai/plugin'

export const MyPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      myTool: tool({
        description: 'Tool personnalisé',
        args: { input: tool.schema.string() },
        execute: async (args) => `Résultat : ${args.input}`,
      }),
    },
    auth: {
      provider: 'monservice',
      methods: [{ type: 'api', label: 'Clé API' }],
    },
    event: async ({ event }) => console.log(event.type),
    config: async (config) => (config.myPlugin = { enabled: true }),
    'chat.message': async ({}, { message }) => console.log(message.content),
    'chat.params': async (
      { model, provider, message },
      { temperature, topP, options },
    ) => {
      temperature = 0.7
      options.custom = 'value'
    },
    'permission.ask': async (perm, out) => (out.status = 'allow'),
    'tool.execute.before': async ({ tool }, { args }) => (args.modified = true),
    'tool.execute.after': async ({ tool }, { title, output, metadata }) => {
      console.log(`Tool ${tool} terminé :`, output)
    },
  }
}
```

### Event — s'abonner aux événements système

```ts
event: async ({ event }) => {
  if (event.type === "session.created") {
    // Nouvelle session démarrée
  }
  if (event.type === "session.idle") {
    // L'agent a fini de répondre
  }
  if (event.type === "message.updated") {
    // Message ajouté/modifié
  }
}
```

### Stop — intercepter les tentatives d'arrêt de l'agent

Idéal pour imposer un workflow avant que l'agent ne s'arrête vraiment :

```ts
stop: async (input) => {
  const sessionId = input.sessionID || input.session_id

  if (!workComplete) {
    await client.session.prompt({
      path: { id: sessionId },
      body: {
        parts: [{ type: "text", text: "Merci de terminer X avant de t'arrêter." }]
      }
    })
  }
}
```

### Tool — définir des tools personnalisés

```typescript
import { tool } from '@opencode-ai/plugin'

export const MyPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      mytool: tool({
        description: 'Ceci est un tool personnalisé',
        args: {
          foo: tool.schema.string().describe('paramètre foo'),
          count: tool.schema.number().optional().describe('compteur optionnel'),
        },
        async execute(args, context) {
          // context inclut : sessionID, messageID, agent, abort
          return `Bonjour ${args.foo} ! Compteur : ${args.count || 1}`
        },
      }),
    },
  }
}
```

Vos tools personnalisés sont disponibles pour OpenCode aux côtés des
tools intégrés. **Si un tool de plugin porte le même nom qu'un tool
intégré, le tool du plugin prend le dessus** — utile à savoir si vous
voulez un jour remplacer le comportement d'un tool existant plutôt que
d'en ajouter un nouveau, mais aussi un piège si un nom est choisi par
inadvertance.

### Auth — fournisseurs d'authentification personnalisés

```typescript
export const MyPlugin: Plugin = async (ctx) => {
  return {
    auth: {
      provider: 'monservice',
      loader: async (auth, provider) => {
        // Charger la configuration d'authentification
        return { apiKey: 'clé-chargée' }
      },
      methods: [
        {
          type: 'oauth',
          label: 'Connecter MonService',
          async authorize() {
            return {
              url: 'https://monservice.com/oauth/authorize',
              instructions: "Autoriser OpenCode à accéder à MonService",
              method: 'code',
              async callback(code) {
                // Traiter le callback OAuth
                return {
                  type: 'success',
                  access: 'jeton-accès',
                  refresh: 'jeton-refresh',
                  expires: Date.now() + 3600000,
                }
              },
            }
          },
        },
      ],
    },
  }
}
```

### chat.message — intercepter et modifier les messages de chat

```typescript
'chat.message': async ({}, { message, parts }) => {
  // Modifier le message avant envoi au LLM
  console.log('Message :', message.content)
}
```

### chat.params — modifier les paramètres du LLM

```typescript
'chat.params': async (
  { model, provider, message },
  { temperature, topP, options },
) => {
  // Ajuster les paramètres selon le contexte
  temperature = 0.7
  options.customParam = 'value'
}
```

### experimental.chat.system.transform — injecter du contexte dans le prompt système

À noter : ce hook ne reçoit ni les messages ni le texte de l'utilisateur en entrée — seulement des informations comme `sessionID` et `model`.

```ts
"experimental.chat.system.transform": async (input, output) => {
  output.system.push(`<custom-context>
    Les règles importantes du projet vont ici.
  </custom-context>`)
}
```

### experimental.session.compacting — préserver l'état lors de la compaction

```ts
"experimental.session.compacting": async (input, output) => {
  output.context.push(`<preserved-state>
    Avancement de la tâche : 75%
    Fichiers modifiés : src/main.ts
  </preserved-state>`)

  // Ou remplacer entièrement le prompt de compaction
  output.prompt = "Instructions de compaction personnalisées..."
}
```

**Précisions confirmées par la doc officielle** : ce hook se déclenche
*avant* que le LLM ne génère le résumé de continuation — c'est donc le
bon moment pour injecter du contexte spécifique au domaine que le prompt
de compaction par défaut manquerait. Et surtout : **si `output.prompt`
est défini, il remplace entièrement le prompt de compaction par
défaut — le tableau `output.context` est alors ignoré.** Les deux ne se
combinent pas ; c'est l'un ou l'autre. Pertinent pour la feature
d'archive de contexte de session discutée séparément : si vous fixez
`output.prompt` pour un besoin donné, tout ce que vous auriez poussé
dans `output.context` (comme le rappel des golden rules) ne sera plus
transmis du tout.

### permission.ask — contrôler les demandes de permission

```typescript
'permission.ask': async (permission, output) => {
  // Autoriser automatiquement certains types de permission
  if (permission.type === 'read_file') {
    output.status = 'allow'
  }
}
```

### tool.execute.before / tool.execute.after — intercepter l'exécution des tools

```ts
"tool.execute.before": async ({ tool, sessionID, callID }, { args }) => {
  if (tool === "bash" && args.command.includes("rm -rf")) {
    throw new Error("Commande dangereuse bloquée")
  }
}

"tool.execute.after": async ({ tool, sessionID, callID }, { title, output, metadata }) => {
  console.log(`Tool ${tool} terminé :`, output)
}
```

### config — modifier la configuration OpenCode

```typescript
config: async (config) => {
  config.myPlugin = { enabled: true }
}
```

### shell.env — injecter des variables d'environnement

Injecte des variables d'environnement dans **toute** exécution shell (aussi bien les tools de l'IA que les terminaux utilisateur) :

```javascript title=".opencode/plugins/inject-env.js"
export const InjectEnv = async (ctx) => {
  return {
    "shell.env": async (input, output) => {
      output.env.MY_API_KEY = "secret"
      output.env.PROJECT_ROOT = input.cwd
    },
  }
}
```

## Gestion de l'état de session

Suivre l'état à travers une session en utilisant des Maps indexées par ID de session (pas de variable globale partagée entre sessions) :

```ts
interface SessionState {
  filesModified: string[]
  commitMade: boolean
}

const sessions = new Map<string, SessionState>()

function getState(sessionId: string): SessionState {
  let state = sessions.get(sessionId)
  if (!state) {
    state = { filesModified: [], commitMade: false }
    sessions.set(sessionId, state)
  }
  return state
}

export const MyPlugin: Plugin = async ({ client }) => {
  return {
    event: async ({ event }) => {
      const sessionId = (event as any).session_id || (event as any).sessionID

      if (event.type === "session.created" && sessionId) {
        sessions.set(sessionId, { filesModified: [], commitMade: false })
      }

      if (event.type === "session.deleted" && sessionId) {
        sessions.delete(sessionId)
      }
    },

    "tool.execute.after": async (input) => {
      const state = getState(input.sessionID)

      if (input.tool === "edit" || input.tool === "write") {
        state.filesModified.push(input.args.filePath as string)
      }

      if (input.tool === "bash" && /git commit/.test(input.args.command as string)) {
        state.commitMade = true
      }
    },

    stop: async (input) => {
      const sessionId = (input as any).sessionID || (input as any).session_id
      const state = getState(sessionId)

      if (state.filesModified.length > 0 && !state.commitMade) {
        await client.session.prompt({
          path: { id: sessionId },
          body: {
            parts: [{ type: "text", text: "Vous avez des modifications non commitées !" }]
          }
        })
      }
    }
  }
}
```

## Intégration shell

Accès à un shell Bun pour exécuter des commandes :

```ts
export const MyPlugin: Plugin = async ({ $ }) => {
  return {
    tool: {
      gitStatus: tool({
        description: 'Récupérer le statut git',
        args: {},
        async execute() {
          const result = await $`git status --porcelain`
          return result.text()
        },
      }),
    },
    "tool.execute.after": async (input) => {
      if (input.tool === "edit" && input.args.filePath.endsWith(".rs")) {
        // Exécuter cargo fmt après modification d'un fichier Rust
        const result = await $`cargo fmt --check`.quiet()
        if (result.exitCode !== 0) {
          console.log("Problèmes de formatage détectés")
        }
      }
    }
  }
}
```

## Journalisation

Utilisez la journalisation structurée plutôt que `console.log` en production :

```ts
await client.app.log({
  service: "my-plugin",
  level: "info",  // debug, info, warn, error
  message: "Quelque chose s'est produit",
  extra: { key: "value" }
})
```

## Dépendances externes

Ajoutez un `package.json` dans votre répertoire de config (`.opencode/`, au même niveau que le répertoire `plugins/`, pas dedans) — cette précision vient de la doc officielle, absente des deux guides précédents. OpenCode exécute `bun install` au démarrage :

```json title=".opencode/package.json"
{
  "dependencies": {
    "some-npm-package": "^1.0.0"
  }
}
```

## Enregistrer un plugin dans `opencode.json`

**Développement local :**

```json
{
  "$schema": "https://opencode.ai/config.json",
  "plugin": ["file:///chemin/vers/votre/plugin/dist/index.js"]
}
```

**Package npm publié :**

```json
{
  "plugin": ["my-opencode-plugin@1.0.0"]
}
```

**Plusieurs plugins :**

```json
{
  "plugin": [
    "plugin-one@latest",
    "plugin-two@2.0.0",
    "file:///chemin/vers/plugin/local"
  ]
}
```

**Convention de nommage pour la publication** — préfixez le nom avec `opencode-` :
- `opencode-my-service`
- `opencode-custom-tools`

## Ordre de chargement des plugins

1. Configuration globale (`~/.config/opencode/opencode.json`)
2. Configuration du projet (`opencode.json`)
3. Répertoire de plugins global (`~/.config/opencode/plugin/`)
4. Répertoire de plugins du projet (`.opencode/plugin/`)

Tous les hooks de tous les plugins s'exécutent en séquence.

## Bonnes pratiques

### Gestion des erreurs

```typescript
tool: {
  riskyTool: tool({
    description: 'Tool qui peut échouer',
    args: {},
    async execute() {
      try {
        const result = await ctx.$`some-command`
        return result.text()
      } catch (error) {
        return `Erreur : ${error.message}`
      }
    },
  }),
}
```

### Opérations asynchrones

Tous les hooks de plugin sont async — utilisez `async`/`await` correctement :

```typescript
event: async ({ event }) => {
  await processEvent(event)
}
```

### Typage strict avec Zod

```typescript
import { z } from 'zod'

tool: {
  typedTool: tool({
    description: 'Tool avec arguments typés',
    args: {
      url: tool.schema.string().url().describe('URL valide'),
      count: tool.schema.number().min(1).max(100).describe('Compteur 1-100'),
    },
    async execute(args) {
      // args est entièrement typé
      return `Traitement de ${args.url} ${args.count} fois`
    },
  }),
}
```

### Gestion des ressources

Nettoyez les ressources quand nécessaire :

```typescript
export const MyPlugin: Plugin = async (ctx) => {
  const cleanup = setupResource()

  return {
    event: async ({ event }) => {
      if (event.type === 'shutdown') {
        await cleanup()
      }
    },
  }
}
```

### Patterns courants

**Détecter les images fournies par l'utilisateur :**
```ts
event: async ({ event }) => {
  if (event.type === "message.updated") {
    const message = (event as any).properties?.message
    if (message?.role === "user") {
      const content = JSON.stringify(message.content || "")
      if (content.includes("image/") || /\.(png|jpg|jpeg|gif|webp)/i.test(content)) {
        // L'utilisateur a fourni une image
      }
    }
  }
}
```

**Suivre les modifications de fichiers :**
```ts
"tool.execute.after": async (input) => {
  if (input.tool === "edit" || input.tool === "write") {
    const filePath = input.args.filePath as string
    // Suivre la modification
  }
}
```

**Imposer une vérification avant commit :**
```ts
"tool.execute.before": async (input, output) => {
  if (input.tool === "bash" && /git commit/.test(output.args.command as string)) {
    if (!state.testsRan) {
      throw new Error("Exécutez les tests avant de commit !")
    }
  }
}
```

## Recette : envoyer un prompt de session sans réponse

Pattern utile pour injecter du contexte dans une session sans déclencher de réponse du modèle (`noReply: true`) :

```typescript
// https://github.com/malhashemi/opencode-skills/blob/main/index.ts
tool({
  async execute(args, toolCtx) {
    ctx.client.session.prompt({
      path: { id: toolCtx.sessionID },
      body: {
        noReply: true,
        parts: [{ type: 'text', text }],
      },
    })
  },
})
```

## Tester les plugins

### Test unitaire

```typescript
// src/index.test.ts
import { describe, it, expect } from 'bun:test'
import { MyPlugin } from './index'

describe('MyPlugin', () => {
  it('devrait enregistrer les tools', async () => {
    const mockCtx = createMockContext()
    const hooks = await MyPlugin(mockCtx)

    expect(hooks.tool).toBeDefined()
    expect(hooks.tool.hello).toBeDefined()
  })
})
```

### Test d'intégration

Tester avec une instance OpenCode réelle :

```bash
# Lier le plugin local pour test
bun link
cd /chemin/vers/projet/opencode
bun link my-opencode-plugin

# Ajouter à opencode.json puis tester
```

## Débogage

1. **Le plugin ne se charge pas ?** Vérifiez les erreurs TypeScript — les erreurs de syntaxe empêchent le chargement. Lancez `opencode --verbose` pour un diagnostic détaillé.
2. **Les hooks ne se déclenchent pas ?** Vérifiez que le nom du hook correspond exactement (sensible à la casse).
3. **L'état ne persiste pas ?** Utilisez des Maps indexées par session, pas des variables globales.
4. **`client.session.prompt` échoue ?** Vérifiez votre déstructuration : `async ({ client })` et non `async (client)`.
5. Pendant le développement, `console.log` reste utile pour un diagnostic rapide (le contexte inclut par exemple `ctx.project.id` pour confirmer que le bon projet est chargé).

## Exemples complets

### Plugin de rappel de commit

```ts
import type { Plugin } from "@opencode-ai/plugin"

interface SessionState {
  filesModified: string[]
  commitMade: boolean
}

const sessions = new Map<string, SessionState>()

export const CommitReminder: Plugin = async ({ client }) => {
  return {
    event: async ({ event }) => {
      const sessionId = (event as any).session_id
      if (event.type === "session.created" && sessionId) {
        sessions.set(sessionId, { filesModified: [], commitMade: false })
      }
      if (event.type === "session.deleted" && sessionId) {
        sessions.delete(sessionId)
      }
    },

    "tool.execute.after": async (input) => {
      const state = sessions.get(input.sessionID)
      if (!state) return

      if (input.tool === "edit" || input.tool === "write") {
        const path = input.args?.filePath as string
        if (path && !state.filesModified.includes(path)) {
          state.filesModified.push(path)
        }
      }

      if (input.tool === "bash") {
        const cmd = input.args?.command as string
        if (/git\s+commit/.test(cmd)) {
          state.commitMade = true
        }
      }
    },

    stop: async (input) => {
      const sessionId = (input as any).sessionID || (input as any).session_id
      if (!sessionId) return

      const state = sessions.get(sessionId)
      if (!state) return

      if (state.filesModified.length > 0 && !state.commitMade) {
        await client.session.prompt({
          path: { id: sessionId },
          body: {
            parts: [{
              type: "text",
              text: `## Modifications non commitées\n\nVous avez modifié ${state.filesModified.length} fichier(s) sans commit. Merci de commit avant de vous arrêter.`
            }]
          }
        })
      }
    }
  }
}
```

### Plugin système de fichiers

```typescript
export const FileSystemPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      listFiles: tool({
        description: 'Lister les fichiers d\'un répertoire',
        args: {
          path: tool.schema.string().describe('Chemin du répertoire'),
        },
        async execute({ path }) {
          const result = await ctx.$`ls -la ${path}`
          return result.text()
        },
      }),
      readFile: tool({
        description: 'Lire le contenu d\'un fichier',
        args: {
          path: tool.schema.string().describe('Chemin du fichier'),
        },
        async execute({ path }) {
          const file = Bun.file(path)
          return await file.text()
        },
      }),
    },
  }
}
```

### Plugin d'intégration API

```typescript
export const APIPlugin: Plugin = async (ctx) => {
  return {
    tool: {
      fetchAPI: tool({
        description: 'Récupérer des données depuis une API',
        args: {
          url: tool.schema.string().url().describe('URL de l\'API'),
          method: tool.schema.enum(['GET', 'POST']).default('GET'),
        },
        async execute({ url, method }) {
          const response = await fetch(url, { method })
          return await response.text()
        },
      }),
    },
  }
}
```

### Protection des fichiers `.env`

Empêche OpenCode de lire les fichiers `.env` :

```javascript title=".opencode/plugins/env-protection.js"
export const EnvProtection = async (ctx) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool === "read" && output.args.filePath.includes(".env")) {
        throw new Error("Lecture des fichiers .env interdite")
      }
    },
  }
}
```

### Notifications à la fin d'une session

Exemple officiel (macOS, via `osascript`) :

```javascript title=".opencode/plugins/notification.js"
export const Notification = async ({ $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.idle") {
        await $`osascript -e 'display notification "Session terminée !" with title "opencode"'`
      }
    },
  }
}
```

`osascript` est spécifique à macOS. Sur Manjaro/Hyprland, l'équivalent
serait `notify-send` (paquet `libnotify`) :

```javascript title=".opencode/plugins/notification.js"
export const Notification = async ({ $ }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.idle") {
        await $`notify-send "opencode" "Session terminée !"`
      }
    },
  }
}
```

Non testé dans cet environnement — à vérifier que `notify-send`
fonctionne correctement sous Hyprland (dépend du démon de notification
actif, par ex. `mako` ou `dunst`).

---

*Fusion de deux guides OpenCode (traduction), sans doublons de contenu.*
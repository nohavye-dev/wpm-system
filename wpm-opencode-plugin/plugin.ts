import type { Plugin } from "@opencode-ai/plugin"
import { buildNudge, buildPersistReminder } from "./wpm-lib/prompts/nudges"
import { isEnabled } from "./wpm-lib/config/settings"
import { readConfigParam } from "./wpm-lib/config/settings"
import { resolveResponseLanguage } from "./wpm-lib/config/settings"
import { createHooks } from "./wpm-lib/server/hooks"

export const WpmPlugin: Plugin = async ({ client, directory }) => {
  if (!isEnabled(directory)) {
    return {}
  }

  const languageConfig = readConfigParam(directory, "response_language")
  const thresholdConfig = readConfigParam(directory, "confidence_threshold")

  const language = resolveResponseLanguage(
    languageConfig ? String(languageConfig) : undefined,
    process.env.WPM_RESPONSE_LANGUAGE,
  )
  const confidenceThreshold = thresholdConfig
    ? String(thresholdConfig) : undefined

  return createHooks({
    client,
    directory,
    language,
    confidenceThreshold,
    nudge: buildNudge(language),
    persistReminder: buildPersistReminder(),
    nudged: new Set<string>(),
    queriedRecently: new Map<string, boolean>(),
  })
}

export default WpmPlugin

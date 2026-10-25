/**
 * Shared provider presentation helpers for model surfaces.
 *
 * Provider codes mirror `ModelProvider` in backend/app/models/model.py. Unknown
 * codes fall back to a monogram so new backend providers never render blank.
 */

export const PROVIDER_ICON_SLUGS: Record<string, string> = {
  openai: 'openai',
  openai_responses: 'openai',
  anthropic: 'anthropic',
  google: 'google',
  azure_openai: 'azure',
  deepseek: 'deepseek',
  moonshot: 'moonshot',
  zhipu: 'zhipu',
  qwen: 'qwen',
  baichuan: 'baichuan',
  minimax: 'minimax',
  volcengine: 'volcengine',
  siliconflow: 'siliconcloud',
  xai: 'xai',
  ollama: 'ollama',
  runway: 'runway',
  pika: 'pika',
  luma: 'luma',
  kling: 'kling',
  stability: 'stability',
  midjourney: 'midjourney',
  typesafe: 'typesafe',
  custom: 'gateway',
}

/** Providers that have a localized name under `models.providers.*`. */
export const KNOWN_PROVIDER_CODES = new Set(Object.keys(PROVIDER_ICON_SLUGS))

const PROVIDER_TINTS: Record<string, string> = {
  openai: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  anthropic: 'bg-orange-500/10 text-orange-600 dark:text-orange-400',
  google: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  xai: 'bg-neutral-500/10 text-neutral-600 dark:text-neutral-400',
  azure: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
  deepseek: 'bg-indigo-500/10 text-indigo-600 dark:text-indigo-400',
  moonshot: 'bg-purple-500/10 text-purple-600 dark:text-purple-400',
  zhipu: 'bg-red-500/10 text-red-600 dark:text-red-400',
  qwen: 'bg-cyan-500/10 text-cyan-600 dark:text-cyan-400',
  baichuan: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  minimax: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
  volcengine: 'bg-blue-600/10 text-blue-700 dark:text-blue-400',
  siliconcloud: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  ollama: 'bg-gray-500/10 text-gray-600 dark:text-gray-400',
  runway: 'bg-neutral-700/10 text-neutral-700 dark:text-neutral-300',
  pika: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400',
  luma: 'bg-teal-500/10 text-teal-600 dark:text-teal-400',
  kling: 'bg-orange-600/10 text-orange-700 dark:text-orange-400',
  stability: 'bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400',
  midjourney: 'bg-slate-500/10 text-slate-600 dark:text-slate-400',
  typesafe: 'bg-emerald-600/10 text-emerald-700 dark:text-emerald-400',
  longcat: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
  baai: 'bg-sky-600/10 text-sky-700 dark:text-sky-400',
  gateway: 'bg-slate-500/10 text-slate-600 dark:text-slate-400',
}

const DEFAULT_PROVIDER_TINT = PROVIDER_TINTS.gateway

/**
 * Model-family fallback for `custom` OpenAI-compatible gateways. A gateway can
 * front any vendor, so its model_id is the only available brand signal. Rules
 * are prefix-based and intentionally limited to unambiguous families.
 */
const MODEL_ID_ICON_RULES: Array<{ slug: string; pattern: RegExp }> = [
  { slug: 'baai', pattern: /^(baai[\/_-]|bge[\/_-])/i },
  { slug: 'longcat', pattern: /^longcat(?:\d|$|[\/_.:-])/i },
  {
    slug: 'openai',
    pattern:
      /^(gpt[\/_-]|chatgpt(?:\d|$|[\/_.:-])|o[134](?:$|[\/_-])|dall-e|whisper(?:\d|$|[\/_.:-])|text-embedding-3|sora(?:\d|$|[\/_.:-]))/i,
  },
  { slug: 'google', pattern: /^(gemini|gemma|palm(?:\d|$|[\/_.:-])|imagen(?:\d|$|[\/_.:-])|text-embedding-004)/i },
  { slug: 'anthropic', pattern: /^claude(?:\d|$|[\/_.:-])/i },
  { slug: 'deepseek', pattern: /^deepseek(?:\d|$|[\/_.:-])/i },
  { slug: 'qwen', pattern: /^qwen(?:\d|$|[\/_.:-])/i },
  { slug: 'zhipu', pattern: /^(glm(?:\d|$|[\/_.:-])|chatglm|cogview|cogvideo)/i },
  { slug: 'moonshot', pattern: /^(moonshot|kimi)(?:\d|$|[\/_.:-])/i },
  { slug: 'minimax', pattern: /^minimax(?:\d|$|[\/_.:-])/i },
  { slug: 'baichuan', pattern: /^baichuan(?:\d|$|[\/_.:-])/i },
  { slug: 'xai', pattern: /^grok(?:\d|$|[\/_.:-])/i },
  { slug: 'volcengine', pattern: /^(doubao|seedream|seedance|skylark)(?:\d|$|[\/_.:-])/i },
  { slug: 'stability', pattern: /^(stable-diffusion|sdxl|sd3)/i },
  { slug: 'midjourney', pattern: /^(midjourney|mj-)/i },
  { slug: 'runway', pattern: /^(runway|gen-3)/i },
  { slug: 'pika', pattern: /^pika(?:\d|$|[\/_.:-])/i },
  { slug: 'luma', pattern: /^(luma|dream-machine)(?:\d|$|[\/_.:-])/i },
  { slug: 'kling', pattern: /^kling(?:\d|$|[\/_.:-])/i },
]

export function resolveProviderIconSlug(provider: string | null | undefined): string | null {
  if (!provider) return null
  return PROVIDER_ICON_SLUGS[provider.trim()] ?? null
}

export function inferModelFamilyIconSlug(modelId: string | null | undefined): string | null {
  const id = modelId?.trim()
  if (!id) return null
  return MODEL_ID_ICON_RULES.find((rule) => rule.pattern.test(id))?.slug ?? null
}

/**
 * Resolves the mark shown for a model. Custom gateways fall back to the
 * model-family icon so a gateway fronting GPT/Gemini/LongCat/BAAI models is
 * visually identifiable; unknown families keep the neutral gateway mark.
 */
export function resolveModelIconSlug(
  provider: string | null | undefined,
  modelId?: string | null,
): string | null {
  const canonical = resolveProviderIconSlug(provider)
  if (canonical !== 'gateway') return canonical
  return inferModelFamilyIconSlug(modelId) ?? canonical
}

export function getProviderTint(
  provider: string | null | undefined,
  modelId?: string | null,
): string {
  const slug = resolveModelIconSlug(provider, modelId) ?? 'gateway'
  return PROVIDER_TINTS[slug] ?? DEFAULT_PROVIDER_TINT
}

export function getProviderInitial(label: string | null | undefined): string {
  const [first] = Array.from(label?.trim() ?? '')
  return first ? first.toUpperCase() : '?'
}

type ProviderLabelTranslator = ((key: string) => string) & {
  has?: (key: string) => boolean
}

/**
 * Custom gateway names win over the provider catalog name. Unknown provider
 * codes render as-is instead of throwing a missing-message error.
 */
export function resolveProviderLabel(
  t: ProviderLabelTranslator,
  provider: string,
  displayName?: string | null,
): string {
  const custom = displayName?.trim()
  if (custom) return custom
  const code = provider?.trim()
  if (!code) return ''
  const key = `providers.${code}`
  if (t.has) return t.has(key) ? t(key) : code
  return KNOWN_PROVIDER_CODES.has(code) ? t(key) : code
}

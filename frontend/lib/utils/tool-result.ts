export interface MediaAsset {
  url?: string | null
  base64?: string | null
  file_path?: string | null
  width?: number | null
  height?: number | null
  duration?: number | null
  format?: string
}

export interface MediaImageToolItem {
  image: MediaAsset
  revised_prompt?: string | null
  seed?: number | null
}

export interface MediaImageToolResult {
  kind: 'media.image'
  success: boolean
  prompt: string
  model?: string | null
  model_ref?: string | null
  images: MediaImageToolItem[]
  error?: string | null
}

export interface MediaVideoToolResult {
  kind: 'media.video'
  success: boolean
  prompt: string
  model?: string | null
  model_ref?: string | null
  task_id?: string | null
  status: string
  progress?: number | null
  video?: MediaAsset | null
  estimated_time?: number | null
  requires_polling?: boolean
  poll_interval_ms?: number
  poll_timeout_s?: number
  error?: string | null
}

export function parseToolResultOutput(output: unknown): unknown {
  if (typeof output !== 'string') {
    return output
  }

  try {
    return JSON.parse(output)
  } catch {
    return output
  }
}

export function isMediaImageToolResult(
  output: unknown
): output is MediaImageToolResult {
  return (
    !!output &&
    typeof output === 'object' &&
    (output as { kind?: string }).kind === 'media.image' &&
    Array.isArray((output as { images?: unknown }).images)
  )
}

export function isMediaVideoToolResult(
  output: unknown
): output is MediaVideoToolResult {
  return (
    !!output &&
    typeof output === 'object' &&
    (output as { kind?: string }).kind === 'media.video' &&
    typeof (output as { status?: unknown }).status === 'string'
  )
}

export function getImageAssetUrl(asset?: MediaAsset | null): string | null {
  if (!asset) return null
  if (asset.url) return asset.url
  if (asset.base64) {
    return `data:image/${asset.format || 'png'};base64,${asset.base64}`
  }
  return null
}

export function getVideoAssetUrl(asset?: MediaAsset | null): string | null {
  if (!asset) return null
  if (asset.url) return asset.url
  if (asset.base64) {
    return `data:video/${asset.format || 'mp4'};base64,${asset.base64}`
  }
  return null
}

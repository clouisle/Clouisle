export interface ToolCitationSource {
  type: 'document' | 'url'
  citationId: string
  title?: string
  content?: string
  url?: string
  documentId?: string
  metadata?: Record<string, unknown>
}

export interface MediaAsset {
  url?: string | null
  base64?: string | null
  file_path?: string | null
  asset_ref?: string | null
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
  let parsed = output
  if (typeof output === 'string') {
    try {
      parsed = JSON.parse(output)
    } catch {
      return output
    }
  }
  if (parsed && typeof parsed === 'object' && 'kind' in parsed && parsed.kind === 'tool.result.persisted' && 'version' in parsed && parsed.version === 1 && 'display' in parsed && 'llm_result' in parsed && typeof parsed.llm_result === 'string') {
    return parsed.display
  }
  return parsed
}

export function extractToolCitationSources(
  toolName: string,
  output: unknown
): ToolCitationSource[] {
  const parsed = parseToolResultOutput(output)
  if (!parsed || typeof parsed !== 'object') return []

  if (toolName === 'knowledge_search' || toolName === 'search_knowledge_base') {
    if (!('contexts' in parsed) || !Array.isArray(parsed.contexts)) return []
    return parsed.contexts.flatMap((context) => {
      if (!context || typeof context !== 'object' || !('citation_id' in context) || typeof context.citation_id !== 'string') return []
      return [{
        type: 'document' as const,
        citationId: context.citation_id,
        title: 'document_name' in context && typeof context.document_name === 'string' ? context.document_name : undefined,
        content: 'content' in context && typeof context.content === 'string' ? context.content : undefined,
        documentId: 'document_id' in context && typeof context.document_id === 'string' ? context.document_id : undefined,
        metadata: {
          kb_id: 'kb_id' in context ? context.kb_id : undefined,
          kb_name: 'kb_name' in context ? context.kb_name : undefined,
          score: 'score' in context ? context.score : undefined,
        },
      }]
    })
  }

  if (toolName === 'web_search') {
    if (!('results' in parsed) || !Array.isArray(parsed.results)) return []
    return parsed.results.flatMap((result) => {
      if (!result || typeof result !== 'object' || !('citation_id' in result) || typeof result.citation_id !== 'string') return []
      return [{
        type: 'url' as const,
        citationId: result.citation_id,
        title: 'title' in result && typeof result.title === 'string' && result.title.trim().length > 0 ? result.title.trim() : undefined,
        content: 'content' in result && typeof result.content === 'string' ? result.content : undefined,
        url: 'url' in result && typeof result.url === 'string' ? result.url : undefined,
      }]
    })
  }
  if (toolName === 'markitdown') {
    if (!('files' in parsed) || !Array.isArray(parsed.files)) return []
    return parsed.files.flatMap((file: unknown) => {
      if (!file || typeof file !== 'object' || !('citation_id' in file) || typeof file.citation_id !== 'string') return []
      const content = 'segments' in file && Array.isArray(file.segments)
        ? file.segments.map((segment: unknown) => segment && typeof segment === 'object' && 'text' in segment && typeof segment.text === 'string' ? segment.text : '').join('\n')
        : undefined
      return [{
        type: 'url' as const,
        citationId: file.citation_id,
        title: 'filename' in file && typeof file.filename === 'string' ? file.filename : undefined,
        url: 'url' in file && typeof file.url === 'string' ? file.url : undefined,
        content,
        metadata: {
          ref: 'ref' in file ? file.ref : undefined,
          eof: 'eof' in file ? file.eof : undefined,
        },
      }]
    })
  }
  if (toolName === 'fetch_webpage') {
    if (!('citation_id' in parsed) || typeof parsed.citation_id !== 'string') return []
    return [{
      type: 'url',
      citationId: parsed.citation_id,
      title: 'title' in parsed && typeof parsed.title === 'string' && parsed.title.trim().length > 0 ? parsed.title.trim() : undefined,
      content: 'content' in parsed && typeof parsed.content === 'string' ? parsed.content : 'segments' in parsed && Array.isArray(parsed.segments) ? parsed.segments.map((segment: unknown) => segment && typeof segment === 'object' && 'text' in segment && typeof segment.text === 'string' ? segment.text : '').join('\n') : undefined,
      url: 'url' in parsed && typeof parsed.url === 'string' ? parsed.url : undefined,
    }]
  }

  if (toolName === 'read_asset' || toolName === 'search_asset') {
    if (!('citation_id' in parsed) || typeof parsed.citation_id !== 'string') return []
    let content: string | undefined
    if ('segments' in parsed && Array.isArray(parsed.segments)) {
      content = parsed.segments
        .map((segment: unknown) => (segment && typeof segment === 'object' && 'text' in segment && typeof segment.text === 'string' ? segment.text : ''))
        .filter(Boolean)
        .join('\n')
    } else if ('matches' in parsed && Array.isArray(parsed.matches)) {
      content = parsed.matches
        .map((match: unknown) => (match && typeof match === 'object' && 'text' in match && typeof match.text === 'string' ? match.text : ''))
        .filter(Boolean)
        .join('\n')
    }
    return [{
      type: 'document',
      citationId: parsed.citation_id,
      title: 'filename' in parsed && typeof parsed.filename === 'string' ? parsed.filename : undefined,
      content: content || undefined,
      documentId: 'ref' in parsed && typeof parsed.ref === 'string' ? parsed.ref : undefined,
      metadata: {
        ref: 'ref' in parsed ? parsed.ref : undefined,
        total_lines: 'total_lines' in parsed ? parsed.total_lines : undefined,
        eof: 'eof' in parsed ? parsed.eof : undefined,
      },
    }]
  }


  return []
}

export function inferToolResultIsError(output: unknown): boolean {
  const parsedOutput = parseToolResultOutput(output)

  if (!parsedOutput || typeof parsedOutput !== 'object') {
    return false
  }

  if ('success' in parsedOutput && parsedOutput.success === false) {
    return true
  }

  if ('error' in parsedOutput) {
    const error = parsedOutput.error
    return typeof error === 'string' ? error.trim().length > 0 : Boolean(error)
  }

  return false
}

export function shouldDisplayMediaResultInBody(output: unknown): boolean {
  const parsedOutput = parseToolResultOutput(output)

  return (
    (isMediaImageToolResult(parsedOutput) || isMediaVideoToolResult(parsedOutput))
    && parsedOutput.success === true
  )
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

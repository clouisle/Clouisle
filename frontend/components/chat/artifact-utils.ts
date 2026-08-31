import { parseToolResultOutput } from '@/lib/utils/tool-result'
import type { ChatMessage, FilePart, ToolCallPart } from './types'

export type ArtifactPreviewMode =
  | 'image'
  | 'video'
  | 'audio'
  | 'pdf'
  | 'html'
  | 'markdown'
  | 'mermaid'
  | 'text'
  | 'unsupported'

/** Return the renderer used by the artifact preview panel for a file. */
export function getArtifactPreviewMode(
  file: Pick<FilePart, 'filename' | 'mimeType'>,
): ArtifactPreviewMode {
  const mimeType = file.mimeType?.toLowerCase() ?? ''
  const filename = file.filename.toLowerCase()
  if (mimeType.startsWith('image/') || /\.(?:png|jpe?g|gif|webp|svg)$/.test(filename)) return 'image'
  if (mimeType.startsWith('video/') || /\.(?:mp4|webm|mov)$/.test(filename)) return 'video'
  if (mimeType.startsWith('audio/') || /\.(?:mp3|wav|ogg|m4a)$/.test(filename)) return 'audio'
  if (mimeType === 'application/pdf' || filename.endsWith('.pdf')) return 'pdf'
  if (mimeType === 'text/html' || /\.x?html?$/.test(filename)) return 'html'
  if (mimeType === 'text/markdown' || /\.(?:md|markdown)$/.test(filename)) return 'markdown'
  if (/\.(?:mmd|mermaid)$/.test(filename)) return 'mermaid'
  if (
    mimeType.startsWith('text/')
    || mimeType.includes('json')
    || mimeType.includes('javascript')
    || mimeType === 'application/xml'
    || mimeType.endsWith('+xml')
    || /\.(?:txt|csv|json|ya?ml|xml|js|jsx|ts|tsx|py|sql|sh)$/.test(filename)
  ) return 'text'
  return 'unsupported'
}

export function isArtifactPreviewable(file: Pick<FilePart, 'filename' | 'mimeType'>) {
  return getArtifactPreviewMode(file) !== 'unsupported'
}

function isArtifactToolName(name: string) {
  return name.trim().toLowerCase() === 'artifact'
}

export function getToolArtifacts(output: unknown): FilePart[] {
  const parsedOutput = parseToolResultOutput(output)
  if (
    !parsedOutput
    || typeof parsedOutput !== 'object'
    || Array.isArray(parsedOutput)
    || !('artifacts' in parsedOutput)
    || !Array.isArray(parsedOutput.artifacts)
  ) {
    return []
  }

  return parsedOutput.artifacts
    .map((artifact): FilePart | null => {
      if (!artifact || typeof artifact !== 'object' || Array.isArray(artifact)) return null
      const artifactRecord = artifact as Record<string, unknown>
      const rawPath = typeof artifactRecord.path === 'string' ? artifactRecord.path.trim() : ''
      const path = rawPath || undefined
      const explicitFilename = typeof artifactRecord.filename === 'string'
        ? artifactRecord.filename.trim()
        : ''
      const url = typeof artifactRecord.url === 'string' ? artifactRecord.url.trim() : undefined
      if (!url) return null

      return {
        type: 'file',
        path,
        filename: explicitFilename || path?.split(/[\\/]/).pop() || path || 'artifact',
        url,
        size: typeof artifactRecord.size === 'number' ? artifactRecord.size : undefined,
        mimeType: typeof artifactRecord.content_type === 'string'
          ? artifactRecord.content_type
          : typeof artifactRecord.contentType === 'string'
            ? artifactRecord.contentType
            : typeof artifactRecord.mime_type === 'string'
              ? artifactRecord.mime_type
              : undefined,
      }
    })
    .filter((file): file is FilePart => file !== null)
}

function getArtifactKey(file: FilePart) {
  return file.path || `${file.filename}:${file.url ?? ''}`
}

/** Collect only results produced by the built-in artifact tool. */
export function getConversationArtifacts(messages: readonly ChatMessage[]): FilePart[] {
  const latestFiles = new Map<string, FilePart>()

  for (const message of messages) {
    if (message.role !== 'assistant') continue

    const artifactCallIds = new Set(
      message.parts
        .filter((part): part is ToolCallPart => (
          part.type === 'tool-call' && isArtifactToolName(part.toolName)
        ))
        .map((part) => part.toolCallId),
    )

    for (const part of message.parts) {
      if (part.type !== 'tool-result') continue
      if (!isArtifactToolName(part.toolName) && !artifactCallIds.has(part.toolCallId)) continue

      for (const file of getToolArtifacts(part.output)) {
        const key = getArtifactKey(file)
        latestFiles.delete(key)
        latestFiles.set(key, file)
      }
    }
  }

  return Array.from(latestFiles.values())
}

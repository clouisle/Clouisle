export type FilePreviewMode =
  | 'image'
  | 'video'
  | 'audio'
  | 'pdf'
  | 'docx'
  | 'pptx'
  | 'spreadsheet'
  | 'html'
  | 'markdown'
  | 'mermaid'
  | 'text'
  | 'unsupported'

export interface PreviewFile {
  filename: string
  url?: string
  mimeType?: string
  size?: number
}

const DOCX_MIME_TYPES = new Set([
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
])

const PPTX_MIME_TYPES = new Set([
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'application/vnd.ms-powerpoint',
])

const SPREADSHEET_MIME_TYPES = new Set([
  'text/csv',
  'application/csv',
  'application/vnd.ms-excel',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'application/vnd.ms-excel.sheet.macroenabled.12',
  'application/vnd.oasis.opendocument.spreadsheet',
])

/** Return the renderer used by the shared file preview panel. */
export function getFilePreviewMode(file: Pick<PreviewFile, 'filename' | 'mimeType'>): FilePreviewMode {
  const mimeType = file.mimeType?.toLowerCase() ?? ''
  const filename = file.filename.toLowerCase()

  if (mimeType.startsWith('image/') || /\.(?:png|jpe?g|gif|webp|svg)$/.test(filename)) return 'image'
  if (mimeType.startsWith('video/') || /\.(?:mp4|webm|mov)$/.test(filename)) return 'video'
  if (mimeType.startsWith('audio/') || /\.(?:mp3|wav|ogg|m4a)$/.test(filename)) return 'audio'
  if (mimeType === 'application/pdf' || filename.endsWith('.pdf')) return 'pdf'
  if (DOCX_MIME_TYPES.has(mimeType) || filename.endsWith('.docx')) return 'docx'
  if (PPTX_MIME_TYPES.has(mimeType) || /\.(?:pptx|ppt)$/.test(filename)) return 'pptx'
  if (SPREADSHEET_MIME_TYPES.has(mimeType) || /\.(?:csv|xlsx|xls|xlsm|ods|tsv)$/.test(filename)) return 'spreadsheet'
  if (mimeType === 'text/html' || /\.x?html?$/.test(filename)) return 'html'
  if (mimeType === 'text/markdown' || /\.(?:md|markdown)$/.test(filename)) return 'markdown'
  if (/\.(?:mmd|mermaid)$/.test(filename)) return 'mermaid'
  if (
    mimeType.startsWith('text/')
    || mimeType.includes('json')
    || mimeType.includes('javascript')
    || mimeType === 'application/xml'
    || mimeType.endsWith('+xml')
    || /\.(?:txt|json|ya?ml|xml|js|jsx|ts|tsx|py|sql|sh)$/.test(filename)
  ) return 'text'

  return 'unsupported'
}

export function isFilePreviewable(file: Pick<PreviewFile, 'filename' | 'mimeType'>): boolean {
  return getFilePreviewMode(file) !== 'unsupported'
}

export function getDocumentMimeType(filename: string, documentType?: string): string | undefined {
  const extension = filename.toLowerCase().split('.').pop()
    const type = extension && /^(?:pdf|docx|pptx|ppt|csv|xlsx|xls|xlsm|ods|tsv|html?|md|markdown|txt|json|xml)$/.test(extension)
    ? extension
    : documentType
  switch (type) {
    case 'pdf':
      return 'application/pdf'
    case 'docx':
      return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    case 'pptx':
      return 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    case 'ppt':
      return 'application/vnd.ms-powerpoint'
    case 'tsv':
      return 'text/tab-separated-values'
    case 'csv':
      return 'text/csv'
    case 'xlsx':
      return 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    case 'xls':
      return 'application/vnd.ms-excel'
    case 'xlsm':
      return 'application/vnd.ms-excel.sheet.macroenabled.12'
    case 'ods':
      return 'application/vnd.oasis.opendocument.spreadsheet'
    case 'html':
    case 'htm':
      return 'text/html'
    case 'md':
    case 'markdown':
      return 'text/markdown'
    case 'txt':
      return 'text/plain'
    case 'json':
      return 'application/json'
    case 'xml':
      return 'application/xml'
    default:
      return type === 'url' ? 'text/html' : undefined
  }
}

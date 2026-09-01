import {
  FileAudio,
  FileCode,
  FileIcon,
  FileImage,
  FileText,
  FileType,
  FileVideo,
  Link,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ComponentType } from 'react'

export interface FileTypeIconProps {
  filename: string
  mimeType?: string
  className?: string
}

type IconComponent = ComponentType<{ className?: string }>

/** Render the same file-type icon used for artifacts and uploaded attachments. */
export function FileTypeIcon({ filename, mimeType, className }: FileTypeIconProps) {
  const extension = filename.toLowerCase().split('.').pop()
  const normalizedMimeType = mimeType?.toLowerCase() ?? ''
  const renderIcon = (Icon: IconComponent, color = 'text-muted-foreground') => (
    <Icon className={cn(className ?? 'h-5 w-5', color)} />
  )

  switch (extension) {
    case 'pdf':
      return renderIcon(FileType, 'text-red-500')
    case 'doc':
    case 'docx':
      return renderIcon(FileType, 'text-blue-500')
    case 'txt':
    case 'md':
    case 'markdown':
    case 'yaml':
    case 'yml':
    case 'xml':
    case 'js':
    case 'jsx':
    case 'ts':
    case 'tsx':
    case 'py':
    case 'sql':
    case 'sh':
      return renderIcon(FileText, 'text-gray-500')
    case 'html':
    case 'xhtml':
      return renderIcon(FileType, 'text-orange-500')
    case 'csv':
      return renderIcon(FileType, 'text-green-500')
    case 'xlsx':
    case 'xls':
      return renderIcon(FileType, 'text-green-600')
    case 'json':
      return renderIcon(FileType, 'text-yellow-500')
    case 'url':
      return renderIcon(Link, 'text-purple-500')
    case 'mmd':
    case 'mermaid':
      return renderIcon(FileCode)
  }

  if (normalizedMimeType.startsWith('image/')) return renderIcon(FileImage)
  if (normalizedMimeType.startsWith('video/')) return renderIcon(FileVideo)
  if (normalizedMimeType.startsWith('audio/')) return renderIcon(FileAudio)
  if (normalizedMimeType === 'application/pdf') return renderIcon(FileType, 'text-red-500')
  if (normalizedMimeType === 'text/html') return renderIcon(FileType, 'text-orange-500')
  if (
    normalizedMimeType.startsWith('text/')
    || normalizedMimeType.includes('json')
    || normalizedMimeType.includes('javascript')
    || normalizedMimeType === 'application/xml'
    || normalizedMimeType.endsWith('+xml')
  ) {
    return renderIcon(FileText, 'text-gray-500')
  }

  return renderIcon(FileIcon)
}

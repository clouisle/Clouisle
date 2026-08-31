'use client';

import { useTranslations } from 'next-intl';
import {
  FileIcon,
  FileImage,
  FileVideo,
  FileAudio,
  FileText,
  FileCode,
  Download,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { getArtifactPreviewMode, isArtifactPreviewable } from './artifact-utils';
import type { FilePart } from './types';

export interface ArtifactFileListProps {
  files: FilePart[];
  className?: string;
  /** Open the right-side preview panel with the artifact. */
  onOpenPreview?: (file: FilePart) => void;
}

interface ArtifactFileProps {
  file: FilePart;
  className?: string;
  onOpenPreview?: (file: FilePart) => void;
}

function renderArtifactIcon(file: FilePart) {
  const className = 'h-5 w-5 text-muted-foreground'
  switch (getArtifactPreviewMode(file)) {
    case 'image':
      return <FileImage className={className} />
    case 'video':
      return <FileVideo className={className} />
    case 'audio':
      return <FileAudio className={className} />
    case 'html':
    case 'mermaid':
      return <FileCode className={className} />
    case 'pdf':
    case 'markdown':
    case 'text':
      return <FileText className={className} />
    default:
      return <FileIcon className={className} />
  }
}

function formatFileSize(bytes?: number): string {
  if (bytes === undefined) return '';
  const units = ['B', 'KB', 'MB', 'GB'] as const;
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}


export function ArtifactFile({ file, onOpenPreview, className }: ArtifactFileProps) {
  const t = useTranslations('chat.file')
  const previewable = Boolean(file.url && isArtifactPreviewable(file))

  return (
    <div className={cn('flex items-center gap-3 rounded-lg border bg-card p-3', className)}>
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted">
        {renderArtifactIcon(file)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{file.filename}</div>
        {file.size !== undefined && (
          <div className="text-xs text-muted-foreground">{formatFileSize(file.size)}</div>
        )}
      </div>

      {previewable && onOpenPreview && (
        <button
          type="button"
          onClick={() => onOpenPreview(file)}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-accent hover:text-accent-foreground"
          aria-label={`${t('preview')}: ${file.filename}`}
        >
          <Eye className="h-4 w-4" />
        </button>
      )}

      {file.url && (
        <a
          href={file.url}
          download={file.filename}
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-accent hover:text-accent-foreground"
          aria-label={`${t('download')}: ${file.filename}`}
        >
          <Download className="h-4 w-4" />
        </a>
      )}
    </div>
  )
}

/** Compact list of downloadable artifacts collected by the chat agent. */
export function ArtifactFileList({ files, className, onOpenPreview }: ArtifactFileListProps) {
  const t = useTranslations('chat.file')
  if (files.length === 0) return null

  return (
    <div className={cn('space-y-2', className)} data-artifact-file-list>
      <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {t('generatedFiles')}
      </div>
      {files.map((file) => (
        <ArtifactFile
          key={file.path ?? file.url ?? file.filename}
          file={file}
          onOpenPreview={onOpenPreview}
        />
      ))}
    </div>
  )
}

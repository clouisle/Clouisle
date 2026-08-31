'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  ChevronDown,
  ChevronUp,
  Download,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { isArtifactPreviewable } from './artifact-utils';
import { FileTypeIcon } from '@/components/file-type-icon';
import type { FilePart } from './types';
const MAX_VISIBLE_FILES = 3

/** Compact list of downloadable artifacts collected by the chat agent. */
export function ArtifactFileList({ files, className, onOpenPreview }: ArtifactFileListProps) {
  const t = useTranslations('chat.file')
  const [expanded, setExpanded] = useState(false)
  if (files.length === 0) return null

  const hiddenFileCount = files.length - MAX_VISIBLE_FILES
  const visibleFiles = expanded ? files : files.slice(0, MAX_VISIBLE_FILES)

  return (
    <div className={cn('overflow-hidden rounded-xl border border-border/60 bg-card/30', className)} data-artifact-file-list>
      <div className="divide-y divide-border/60">
        {visibleFiles.map((file) => (
          <ArtifactFile
            key={file.path ?? file.url ?? file.filename}
            file={file}
            className="rounded-none border-0 bg-transparent px-3 py-2"
            onOpenPreview={onOpenPreview}
          />
        ))}
      </div>
      {hiddenFileCount > 0 && (
        <button
          type="button"
          data-artifact-file-toggle
          aria-expanded={expanded}
          onClick={() => setExpanded((value) => !value)}
          className="flex w-full items-center justify-center gap-1.5 border-t border-border/60 bg-muted/30 px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted"
        >
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          <span>{expanded ? t('showLess') : t('showMore', { count: hiddenFileCount })}</span>
        </button>
      )}
    </div>
  )
}

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
    <div className={cn('flex items-center gap-2.5 rounded-lg border bg-card p-2.5', className)}>
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted/70">
        <FileTypeIcon filename={file.filename} mimeType={file.mimeType} />
      </div>

      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{file.filename}</div>
        {file.size !== undefined && (
          <div className="text-[11px] text-muted-foreground">{formatFileSize(file.size)}</div>
        )}
      </div>

      {previewable && onOpenPreview && (
        <button
          type="button"
          onClick={() => onOpenPreview(file)}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-accent hover:text-accent-foreground"
          aria-label={`${t('preview')}: ${file.filename}`}
        >
          <Eye className="h-4 w-4" />
        </button>
      )}

      {file.url && (
        <a
          href={file.url}
          download={file.filename}
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors hover:bg-accent hover:text-accent-foreground"
          aria-label={`${t('download')}: ${file.filename}`}
        >
          <Download className="h-4 w-4" />
        </a>
      )}
    </div>
  )
}

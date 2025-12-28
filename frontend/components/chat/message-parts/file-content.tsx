'use client';

import { useState } from 'react';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  FileIcon,
  FileImage,
  FileVideo,
  FileAudio,
  FileText,
  FileCode,
  FileArchive,
  Download,
  Eye,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FilePart } from '../types';

export interface FileContentProps {
  file: FilePart;
  className?: string;
}

const FILE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  image: FileImage,
  video: FileVideo,
  audio: FileAudio,
  text: FileText,
  code: FileCode,
  archive: FileArchive,
  default: FileIcon,
};

function getFileCategory(mimeType?: string): string {
  if (!mimeType) return 'default';
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';
  if (mimeType.startsWith('audio/')) return 'audio';
  if (mimeType.startsWith('text/')) return 'text';
  if (
    mimeType.includes('javascript') ||
    mimeType.includes('json') ||
    mimeType.includes('xml') ||
    mimeType.includes('typescript')
  )
    return 'code';
  if (
    mimeType.includes('zip') ||
    mimeType.includes('rar') ||
    mimeType.includes('tar') ||
    mimeType.includes('gzip')
  )
    return 'archive';
  return 'default';
}

function formatFileSize(bytes?: number): string {
  if (!bytes) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = bytes;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }
  return `${size.toFixed(1)} ${units[unitIndex]}`;
}

export function FileContent({ file, className }: FileContentProps) {
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const category = getFileCategory(file.mimeType);
  const IconComponent = FILE_ICONS[category] || FILE_ICONS.default;
  const isImage = category === 'image';

  return (
    <div className={cn('my-2', className)}>
      <div className="inline-flex items-center gap-3 p-3 rounded-lg border bg-card max-w-md">
        {/* File Icon or Image Preview */}
        {isImage && file.url ? (
          <Collapsible open={isPreviewOpen} onOpenChange={setIsPreviewOpen}>
            <CollapsibleTrigger className="block">
              <div className="relative w-12 h-12 rounded overflow-hidden bg-muted cursor-pointer group">
                <img
                  src={file.url}
                  alt={file.name}
                  className="w-full h-full object-cover"
                />
                <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                  <Eye className="h-4 w-4 text-white" />
                </div>
              </div>
            </CollapsibleTrigger>
            <CollapsibleContent className="mt-2">
              <img
                src={file.url}
                alt={file.name}
                className="max-w-full max-h-80 rounded-lg border"
              />
            </CollapsibleContent>
          </Collapsible>
        ) : (
          <div className="w-12 h-12 rounded bg-muted flex items-center justify-center shrink-0">
            <IconComponent className="h-6 w-6 text-muted-foreground" />
          </div>
        )}

        {/* File Info */}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{file.name}</div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {file.size && <span>{formatFileSize(file.size)}</span>}
            {file.mimeType && (
              <>
                {file.size && <span>·</span>}
                <span className="truncate">{file.mimeType}</span>
              </>
            )}
          </div>
        </div>

        {/* Actions */}
        {file.url && (
          <a
            href={file.url}
            download={file.name}
            className="h-8 w-8 shrink-0 inline-flex items-center justify-center rounded-md hover:bg-accent hover:text-accent-foreground transition-colors"
          >
            <Download className="h-4 w-4" />
          </a>
        )}
      </div>
    </div>
  );
}

interface FileListContentProps {
  files: FilePart[];
  className?: string;
}

export function FileListContent({ files, className }: FileListContentProps) {
  if (!files || files.length === 0) return null;

  // Group images separately for grid display
  const imageFiles = files.filter(
    (f) => f.mimeType?.startsWith('image/') && f.url
  );
  const otherFiles = files.filter(
    (f) => !f.mimeType?.startsWith('image/') || !f.url
  );

  return (
    <div className={cn('space-y-2', className)}>
      {/* Image Grid */}
      {imageFiles.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {imageFiles.map((file, index) => (
            <ImageThumbnail key={index} file={file} />
          ))}
        </div>
      )}

      {/* Other Files */}
      {otherFiles.map((file, index) => (
        <FileContent key={index} file={file} />
      ))}
    </div>
  );
}

interface ImageThumbnailProps {
  file: FilePart;
}

function ImageThumbnail({ file }: ImageThumbnailProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
      <CollapsibleTrigger>
        <div className="relative w-20 h-20 rounded-lg overflow-hidden border cursor-pointer group">
          <img
            src={file.url}
            alt={file.name}
            className="w-full h-full object-cover"
          />
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
            <Eye className="h-4 w-4 text-white" />
          </div>
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
        <div className="relative max-w-4xl max-h-full">
          <img
            src={file.url}
            alt={file.name}
            className="max-w-full max-h-[80vh] object-contain rounded-lg"
            onClick={() => setIsExpanded(false)}
          />
          <div className="mt-2 text-center text-white text-sm">{file.name}</div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

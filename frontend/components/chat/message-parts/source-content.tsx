'use client';

import { memo, useCallback, useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronRight, FileText, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SourceUrlPart, SourceDocumentPart, ChatPreviewPayload } from '../types';

interface SourceContentProps {
  sources: (SourceUrlPart | SourceDocumentPart)[];
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void;
  className?: string;
}

const SOURCE_LIST_BATCH_SIZE = 20;
const SEGMENT_CONTENT_MAX_CHARS = 4000;

// Grouped document with all its segments
interface GroupedDocument {
  documentId: string;
  documentName: string;
  segments: SourceDocumentPart[];
}

// Collapsible segment item component
export const SegmentItem = memo(function SegmentItem({ segment, index }: { segment: SourceDocumentPart; index: number }) {
  const t = useTranslations('chat.source');
  const [isOpen, setIsOpen] = useState(false);
  const fullContent = segment.content ?? '';
  const shouldTruncate = fullContent.length > SEGMENT_CONTENT_MAX_CHARS;
  const previewContent = shouldTruncate
    ? `${fullContent.slice(0, SEGMENT_CONTENT_MAX_CHARS)}…`
    : fullContent;

  const toggleOpen = useCallback(() => setIsOpen((open) => !open), []);

  return (
    <div className="w-full">
      <button type="button" className="w-full text-left" onClick={toggleOpen} aria-expanded={isOpen}>
        <div className="flex items-start gap-2 p-3 rounded-lg border bg-muted/30 hover:bg-muted/50 transition-colors">
          <div className="mt-0.5 shrink-0">
            {isOpen ? (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
              <span className="shrink-0">{t('segment', { index: index + 1 })}</span>
              {typeof segment.metadata?.score === 'number' && (
                <span className="text-primary/70 shrink-0">
                  {t('relevance', { score: Math.round(segment.metadata.score * 100) })}
                </span>
              )}
            </div>
          </div>
        </div>
      </button>
      {isOpen && (
        <div>
          <div className="p-3 ml-6 border-l-2 border-muted">
            <div className="text-sm whitespace-pre-wrap break-words">
              {previewContent}
            </div>
            {shouldTruncate && (
              <div className="mt-2 text-xs text-muted-foreground">
                {t('contentTruncated', { length: fullContent.length })}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
});

export const SourceContent = memo(function SourceContent({ sources, onOpenCodePreview, className }: SourceContentProps) {
  const t = useTranslations('chat.source');
  const [isOpen, setIsOpen] = useState(false);
  const [visibleSourceCount, setVisibleSourceCount] = useState(SOURCE_LIST_BATCH_SIZE);

  const urlSources = useMemo(() => 
    sources?.filter((s): s is SourceUrlPart => s.type === 'source-url') ?? [],
    [sources]
  );
  const documentSources = useMemo(() =>
    sources?.filter((s): s is SourceDocumentPart => s.type === 'source-document') ?? [],
    [sources]
  );

  // Group document sources by documentId or documentName
  const groupedDocuments = useMemo(() => {
    if (!sources || sources.length === 0) return [];
    const groups = new Map<string, GroupedDocument>();
    
    for (const doc of documentSources) {
      const key = doc.documentId || doc.documentName || 'unknown';
      const existing = groups.get(key);
      
      if (existing) {
        existing.segments.push(doc);
      } else {
        groups.set(key, {
          documentId: doc.documentId || key,
          documentName: doc.documentName || t('document'),
          segments: [doc],
        });
      }
    }
    
    return Array.from(groups.values());
  }, [sources, documentSources, t]);

  if (!sources || sources.length === 0) {
    return null;
  }

  // Count unique sources (URLs + unique documents)
  const uniqueSourceCount = urlSources.length + groupedDocuments.length;
  const visibleSourceItems: Array<SourceUrlPart | GroupedDocument> = [
    ...urlSources,
    ...groupedDocuments,
  ].slice(0, visibleSourceCount);
  const hiddenSourceCount = uniqueSourceCount - visibleSourceItems.length;

  return (
    <div className={cn('overflow-hidden', className)}>
      <div className="mt-3">
        <button
          type="button"
          onClick={() => {
            const nextOpen = !isOpen;
            setIsOpen(nextOpen);
            if (nextOpen) {
              setVisibleSourceCount(SOURCE_LIST_BATCH_SIZE);
            }
          }}
          aria-expanded={isOpen}
          className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors"
        >
          <span>{t('usedSources', { count: uniqueSourceCount })}</span>
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-200',
              isOpen && 'rotate-180'
            )}
          />
        </button>

        {isOpen && (
          <div className="mt-2 space-y-1">
            {visibleSourceItems.map((item, index) => (
              'type' in item ? (
                <UrlSourceItem key={`url-${index}`} source={item} />
              ) : (
                <DocumentSourceItem
                  key={item.documentId}
                  document={item}
                  onClick={() => onOpenCodePreview?.({
                    id: `source-document:${item.documentId}`,
                    kind: 'source-document',
                    documentId: item.documentId,
                    documentName: item.documentName,
                    segments: item.segments,
                  })}
                />
              )
            ))}
            {hiddenSourceCount > 0 && (
              <button
                type="button"
                onClick={() => setVisibleSourceCount((count) => count + SOURCE_LIST_BATCH_SIZE)}
                className="py-1 text-sm text-primary hover:text-primary/80 transition-colors"
              >
                {t('showMoreSources', { count: Math.min(hiddenSourceCount, SOURCE_LIST_BATCH_SIZE) })}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
});

function getUrlDisplayText(source: SourceUrlPart, fallback: string) {
  if (source.title) return source.title;

  try {
    return new URL(source.url).hostname;
  } catch {
    return source.url || fallback;
  }
}

interface UrlSourceItemProps {
  source: SourceUrlPart;
}

const UrlSourceItem = memo(function UrlSourceItem({ source }: UrlSourceItemProps) {
  const t = useTranslations('chat.source');
  const displayUrl = getUrlDisplayText(source, t('url'));

  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      className="flex items-center gap-2 py-1 text-sm text-primary hover:text-primary/80 transition-colors"
    >
      <Link2 className="h-4 w-4 shrink-0" />
      <span className="truncate">{displayUrl}</span>
    </a>
  );
});

interface DocumentSourceItemProps {
  document: GroupedDocument;
  onClick: () => void;
}

const DocumentSourceItem = memo(function DocumentSourceItem({ document, onClick }: DocumentSourceItemProps) {
  const t = useTranslations('chat.source');
  const segmentCount = document.segments.length;

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 py-1 text-sm text-primary hover:text-primary/80 transition-colors text-left w-full cursor-pointer"
    >
      <FileText className="h-4 w-4 shrink-0" />
      <span className="truncate">{document.documentName}</span>
      {segmentCount > 1 && (
        <span className="text-xs text-muted-foreground shrink-0">
          ({t('segmentCount', { count: segmentCount })})
        </span>
      )}
    </button>
  );
});

export type { SourceContentProps };

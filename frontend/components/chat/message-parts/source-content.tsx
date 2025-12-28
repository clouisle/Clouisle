'use client';

import { useState, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ChevronDown, ChevronRight, FileText, Link2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { SourceUrlPart, SourceDocumentPart } from '../types';

interface SourceContentProps {
  sources: (SourceUrlPart | SourceDocumentPart)[];
  className?: string;
}

// Grouped document with all its segments
interface GroupedDocument {
  documentId: string;
  documentName: string;
  segments: SourceDocumentPart[];
}

// Collapsible segment item component
function SegmentItem({ segment, index }: { segment: SourceDocumentPart; index: number }) {
  const t = useTranslations('chat.source');
  const [isOpen, setIsOpen] = useState(false);
  
  // Truncate content for preview (by characters, not by length which may include long URLs)
  const getPreviewContent = () => {
    const text = segment.content;
    if (text.length <= 50) return text;
    return text.slice(0, 50) + '...';
  };

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="w-full">
      <CollapsibleTrigger className="w-full text-left">
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
            {!isOpen && (
              <div className="text-sm text-muted-foreground line-clamp-1">
                {getPreviewContent()}
              </div>
            )}
          </div>
        </div>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="p-3 ml-6 border-l-2 border-muted">
          <div className="text-sm whitespace-pre-wrap break-all">
            {segment.content}
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function SourceContent({ sources, className }: SourceContentProps) {
  const t = useTranslations('chat.source');
  const [isOpen, setIsOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<GroupedDocument | null>(null);

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

  return (
    <div className={cn('overflow-hidden', className)}>
      <Collapsible
        open={isOpen}
        onOpenChange={setIsOpen}
        className="mt-3"
      >
        <CollapsibleTrigger className="flex items-center gap-1 text-sm text-primary hover:text-primary/80 transition-colors">
          <span>{t('usedSources', { count: uniqueSourceCount })}</span>
          <ChevronDown
            className={cn(
              'h-4 w-4 transition-transform duration-200',
              isOpen && 'rotate-180'
            )}
          />
        </CollapsibleTrigger>

        <CollapsibleContent className="mt-2 space-y-1">
          {/* URL Sources */}
          {urlSources.map((source, index) => (
            <UrlSourceItem key={`url-${index}`} source={source} />
          ))}

          {/* Grouped Document Sources */}
          {groupedDocuments.map((doc) => (
            <DocumentSourceItem
              key={doc.documentId}
              document={doc}
              onClick={() => setSelectedDocument(doc)}
            />
          ))}
        </CollapsibleContent>
      </Collapsible>

      {/* Document Segments Dialog */}
      <Dialog open={!!selectedDocument} onOpenChange={(open) => !open && setSelectedDocument(null)}>
        <DialogContent className="w-[70vw] !max-w-[70vw] max-h-[80vh] overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 shrink-0" />
              <span className="truncate">{selectedDocument?.documentName}</span>
            </DialogTitle>
          </DialogHeader>
          <ScrollArea className="h-[60vh]">
            <div className="space-y-2 pr-4">
              {selectedDocument?.segments.map((segment, index) => (
                <SegmentItem
                  key={index}
                  segment={segment}
                  index={index}
                />
              ))}
            </div>
          </ScrollArea>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface UrlSourceItemProps {
  source: SourceUrlPart;
}

function UrlSourceItem({ source }: UrlSourceItemProps) {
  const displayUrl = source.title || new URL(source.url).hostname;

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
}

interface DocumentSourceItemProps {
  document: GroupedDocument;
  onClick: () => void;
}

function DocumentSourceItem({ document, onClick }: DocumentSourceItemProps) {
  const t = useTranslations('chat.source');
  const segmentCount = document.segments.length;

  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 py-1 text-sm text-primary hover:text-primary/80 transition-colors text-left w-full"
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
}

export type { SourceContentProps };
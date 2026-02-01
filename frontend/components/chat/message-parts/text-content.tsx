'use client'

import * as React from 'react'
import { memo } from 'react'
import { Streamdown } from 'streamdown'
import { cn } from '@/lib/utils'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type { TextPart, SourceDocumentPart } from '../types'

export interface TextContentProps {
  part: TextPart
  className?: string
  /** RAG sources for citation rendering */
  sources?: SourceDocumentPart[]
  /** Callback when citation is clicked */
  onCitationClick?: (sourceIndex: number) => void
}

// Parse text and replace citations [[cite:N]] with placeholder
function processCitations(
  text: string,
  sources?: SourceDocumentPart[]
): { processedText: string; citations: Map<string, { index: number; source?: SourceDocumentPart }> } {
  const citations = new Map<string, { index: number; source?: SourceDocumentPart }>()
  const normalized = text
    .replace(/\[\[ref:(\d+)\]\]/gi, '[[cite:$1]]')
    .replace(/\[ref:(\d+)\]/gi, '[[cite:$1]]')
    .replace(/\(ref:(\d+)\)/gi, '[[cite:$1]]')
  const regex = /\[\[cite:(\d+)\]\]/g
  
  const processedText = normalized.replace(regex, (match, num) => {
    const index = parseInt(num, 10)
    const placeholder = `<cite-${index}>`
    citations.set(placeholder, { index, source: sources?.[index - 1] })
    return placeholder
  })
  
  return { processedText, citations }
}

export const TextContent = memo(
  ({ part, className, sources, onCitationClick }: TextContentProps) => {
    const isStreaming = part.state === 'streaming'
    
    // Process citations
    const { processedText } = React.useMemo(
      () => processCitations(part.text, sources),
      [part.text, sources]
    )

    // Custom component to render citations
    const CitationRenderer = React.useCallback(
      ({ children }: { children?: React.ReactNode }) => {
        const text = String(children || '')
        // Check if this text contains our citation placeholders
        const parts: React.ReactNode[] = []
        let lastIndex = 0
        const citationRegex = /<cite-(\d+)>/g
        let match

        while ((match = citationRegex.exec(text)) !== null) {
          // Add text before citation
          if (match.index > lastIndex) {
            parts.push(text.slice(lastIndex, match.index))
          }
          // Add citation badge
          const index = parseInt(match[1], 10)
          const source = sources?.[index - 1]
          parts.push(
            <CitationBadge
              key={`cite-${index}-${match.index}`}
              index={index}
              source={source}
              onClick={() => onCitationClick?.(index)}
            />
          )
          lastIndex = citationRegex.lastIndex
        }

        // Add remaining text
        if (lastIndex < text.length) {
          parts.push(text.slice(lastIndex))
        }

        return parts.length > 0 ? <>{parts}</> : <>{children}</>
      },
      [sources, onCitationClick]
    )

    return (
      <div
        className={cn(
          'size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
          className
        )}
      >
        <Streamdown
          components={{
            // Override text rendering to handle citations
            // Use div instead of p when paragraph contains block elements (like images)
            // This prevents React hydration error: <div> cannot be a descendant of <p>
            p: ({ children, node, ...props }) => {
              // Check AST node for img elements
              const hasImgInNode = node?.children?.some(
                (child: { tagName?: string; type?: string }) => 
                  child.tagName === 'img' || child.type === 'element' && child.tagName === 'img'
              )
              const hasBlockElements = React.Children.toArray(children).some(
                (child) => 
                  React.isValidElement(child) && 
                  (child.type === 'div' || child.type === 'img' || typeof child.type === 'function')
              )
              if (hasImgInNode || hasBlockElements) {
                return <div className="my-4" {...props}><CitationRenderer>{children}</CitationRenderer></div>
              }
              return (
                <p {...props}>
                  <CitationRenderer>{children}</CitationRenderer>
                </p>
              )
            },
            li: ({ children, ...props }) => (
              <li {...props}>
                <CitationRenderer>{children}</CitationRenderer>
              </li>
            ),
          }}
        >
          {processedText}
        </Streamdown>
        {isStreaming && (
          <span className="inline-block w-0.5 h-4 ml-0.5 bg-current animate-blink align-text-bottom" />
        )}
      </div>
    )
  },
  (prevProps, nextProps) =>
    prevProps.part.text === nextProps.part.text &&
    prevProps.part.state === nextProps.part.state &&
    prevProps.sources === nextProps.sources
)

TextContent.displayName = 'TextContent'

interface CitationBadgeProps {
  index: number
  source?: SourceDocumentPart
  onClick?: () => void
}

function CitationBadge({ index, source, onClick }: CitationBadgeProps) {
  const badge = (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center justify-center',
        'min-w-5 h-5 px-1 mx-0.5',
        'text-xs font-medium rounded',
        'bg-primary/10 text-primary hover:bg-primary/20',
        'transition-colors cursor-pointer',
        'align-middle'
      )}
    >
      {index}
    </button>
  )

  if (!source) {
    return badge
  }

  return (
    <Tooltip>
      <TooltipTrigger render={badge} />
      <TooltipContent side="top" className="max-w-xs">
        <div className="space-y-1">
          <div className="font-medium text-xs">{source.documentName || '文档'}</div>
          <div className="text-xs text-muted-foreground line-clamp-3">
            {source.content}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

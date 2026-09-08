'use client'

import * as React from 'react'
import { memo } from 'react'
import { Streamdown } from 'streamdown'
import { cn } from '@/lib/utils'
import type { TextPart } from '../types'

export interface TextContentProps {
  part: TextPart
  className?: string
}

export function TextContentComponent({ part, className }: TextContentProps) {
  const isStreaming = part.state === 'streaming'
    return (
      <div
        className={cn(
          'size-full [&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
          className
        )}
      >
        <Streamdown
          components={{
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
                return <div className="my-4" {...props}>{children}</div>
              }
              return (
                <p {...props}>
                  {children}
                </p>
              )
            },
            li: ({ children, ...props }) => (
              <li {...props}>
                {children}
              </li>
            ),
          }}
        >
          {part.text}
        </Streamdown>
        {isStreaming && (
          <span className="inline-block w-0.5 h-4 ml-0.5 bg-current animate-blink align-text-bottom" />
        )}
      </div>
    )
}

export const TextContent = memo(
  TextContentComponent,
  (prevProps, nextProps) =>
    prevProps.part.text === nextProps.part.text &&
    prevProps.part.state === nextProps.part.state
)

TextContent.displayName = 'TextContent'


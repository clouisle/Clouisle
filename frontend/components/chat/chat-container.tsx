'use client';

import { useRef, useEffect, useCallback, useState, useLayoutEffect } from 'react';
import { ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Message } from './message';
import type { ChatMessage, CodePreviewPayload, MessagePart } from './types';

interface ChatContainerProps {
  messages: ChatMessage[];
  className?: string;
  isStreaming?: boolean;
  autoScroll?: boolean;
  renderPart?: (part: MessagePart, index: number) => React.ReactNode;
  emptyState?: React.ReactNode;
  /** Callback when regenerate is clicked for a message */
  onRegenerate?: (messageId: string) => void;
  /** Callback when version is switched for a message */
  onSwitchVersion?: (messageId: string, versionIndex: number) => void;
  /** Callback when user selects an option from user input request */
  onSelectOption?: (option: string) => void;
  /** Show scroll to bottom button when not at bottom */
  showScrollToBottom?: boolean;
  /** Callback when a previewable code block is opened */
  onOpenCodePreview?: (payload: CodePreviewPayload) => void;
}

export function ChatContainer({
  messages,
  className,
  isStreaming = false,
  autoScroll = true,
  renderPart,
  emptyState,
  onRegenerate,
  onSwitchVersion,
  onSelectOption,
  showScrollToBottom = true,
  onOpenCodePreview,
}: ChatContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);
  const followStreamingRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const isNearBottom = useCallback(() => {
    if (!containerRef.current) return true;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    return scrollHeight - scrollTop - clientHeight < 100;
  }, []);

  // Scroll to bottom within container only (not the page)
  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, []);

  // Track if user has manually scrolled up
  const handleScroll = useCallback(() => {
    const atBottom = isNearBottom();
    userScrolledRef.current = !atBottom;
    followStreamingRef.current = atBottom;
    setShowScrollButton(!atBottom && messages.length > 0);
  }, [isNearBottom, messages.length]);

  // Get the last message's parts length for dependency tracking during streaming
  const lastMessagePartsLength = messages.length > 0
    ? messages[messages.length - 1].parts.length
    : 0;

  // Get last text content for streaming detection
  const lastMessageText = messages.length > 0
    ? messages[messages.length - 1].parts
        .filter(p => p.type === 'text')
        .map(p => (p as { text: string }).text)
        .join('')
        .length
    : 0;

  // Auto scroll to bottom before paint so streaming height changes do not flash at the old position.
  useLayoutEffect(() => {
    if (!autoScroll || userScrolledRef.current || !followStreamingRef.current) {
      return;
    }

    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [messages.length, lastMessagePartsLength, lastMessageText, autoScroll]);

  // Reset user scroll tracking when streaming starts
  useEffect(() => {
    if (isStreaming && isNearBottom()) {
      userScrolledRef.current = false;
      followStreamingRef.current = true;
      setShowScrollButton(false);
    }
  }, [isStreaming, isNearBottom]);

  // Hide scroll button when no messages
  useEffect(() => {
    if (messages.length === 0) {
      setShowScrollButton(false);
    }
  }, [messages.length]);

  if (messages.length === 0 && emptyState) {
    return (
      <div
        className={cn(
          'h-full flex items-center justify-center',
          className
        )}
      >
        {emptyState}
      </div>
    );
  }

  return (
    <div className={cn("relative h-full", className)}>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden [overflow-anchor:none]"
      >
        <div className="flex flex-col min-w-0">
          {messages.map((message, index) => {
            const isLast = index === messages.length - 1;
            const isCurrentStreaming = isStreaming && isLast;

            return (
              <Message
                key={message.id}
                message={message}
                isStreaming={isCurrentStreaming}
                renderPart={renderPart}
                onRegenerate={message.role === 'assistant' && onRegenerate ? () => onRegenerate(message.id) : undefined}
                onSwitchVersion={message.role === 'assistant' && onSwitchVersion ? (versionIndex) => onSwitchVersion(message.id, versionIndex) : undefined}
                onSelectOption={onSelectOption}
                onOpenCodePreview={onOpenCodePreview}
              />
            );
          })}
        </div>

        {/* Bottom padding */}
        <div className="h-4" />
      </div>

      {/* Scroll to bottom button */}
      {showScrollToBottom && showScrollButton && (
        <Button
          variant="outline"
          size="icon"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 h-8 w-8 rounded-full shadow-md bg-background/95 backdrop-blur-sm border-border/50 hover:bg-accent"
          onClick={scrollToBottom}
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

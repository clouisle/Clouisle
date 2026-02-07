'use client';

import { useRef, useEffect, useCallback, useState } from 'react';
import { ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Message } from './message';
import type { ChatMessage, MessagePart } from './types';

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
  /** Show scroll to bottom button when not at bottom */
  showScrollToBottom?: boolean;
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
  showScrollToBottom = true,
}: ChatContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Scroll to bottom within container only (not the page)
  const scrollToBottom = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, []);

  // Scroll to bottom instantly (for auto-scroll during streaming)
  const scrollToBottomInstant = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, []);

  // Track if user has manually scrolled up
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    // Consider "at bottom" if within 100px of the bottom
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 100;
    userScrolledRef.current = !isAtBottom;
    setShowScrollButton(!isAtBottom && messages.length > 0);
  }, [messages.length]);

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

  // Auto scroll to bottom when new messages arrive or streaming
  useEffect(() => {
    if (autoScroll && !userScrolledRef.current) {
      scrollToBottomInstant();
    }
  }, [messages.length, lastMessagePartsLength, lastMessageText, autoScroll, isStreaming, scrollToBottomInstant]);

  // Reset user scroll tracking when streaming starts
  useEffect(() => {
    if (isStreaming) {
      userScrolledRef.current = false;
      setShowScrollButton(false);
    }
  }, [isStreaming]);

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
          'flex-1 flex items-center justify-center',
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
        className="absolute inset-0 overflow-y-auto overflow-x-hidden"
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

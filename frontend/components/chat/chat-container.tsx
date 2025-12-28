'use client';

import { useRef, useEffect, useCallback } from 'react';
import { cn } from '@/lib/utils';
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
}: ChatContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const userScrolledRef = useRef(false);

  // Scroll to bottom within container only (not the page)
  const scrollToBottom = useCallback(() => {
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
  }, []);

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
      scrollToBottom();
    }
  }, [messages.length, lastMessagePartsLength, lastMessageText, autoScroll, isStreaming, scrollToBottom]);

  // Reset user scroll tracking when streaming starts
  useEffect(() => {
    if (isStreaming) {
      userScrolledRef.current = false;
    }
  }, [isStreaming]);

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
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className={cn(
        'flex-1 overflow-y-auto overflow-x-hidden min-h-0',
        className
      )}
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
  );
}

'use client';

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
  /** Callback when a user message is edited */
  onEditMessage?: (messageId: string, content: string) => Promise<void>;
  /** Callback when version is switched for a message */
  onSwitchVersion?: (messageId: string, versionIndex: number) => void;
  /** Callback when user selects an option from user input request */
  onSelectOption?: (option: string) => void;
  /** Show scroll to bottom button when not at bottom */
  showScrollToBottom?: boolean;
  /** Callback when a previewable code block is opened */
  onOpenCodePreview?: (payload: CodePreviewPayload) => void;
  /** Hide tool call cards and tool execution details */
  hideToolCalls?: boolean;
}

const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

function hasOpenCodeFence(content: string) {
  let openFence: '`' | '~' | null = null;
  let openFenceLength = 0;

  for (const line of content.split(/\r?\n/)) {
    const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (!match) continue;

    const fence = match[1][0] as '`' | '~';
    if (!openFence) {
      openFence = fence;
      openFenceLength = match[1].length;
      continue;
    }

    if (fence === openFence && match[1].length >= openFenceLength) {
      openFence = null;
      openFenceLength = 0;
    }
  }

  return openFence !== null;
}

export function ChatContainer({
  messages,
  className,
  isStreaming = false,
  autoScroll = true,
  renderPart,
  emptyState,
  onRegenerate,
  onEditMessage,
  onSwitchVersion,
  onSelectOption,
  showScrollToBottom = true,
  onOpenCodePreview,
  hideToolCalls = false,
}: ChatContainerProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const showScrollButtonRef = useRef(false);
  const [chainOfThoughtOpenByMessageId, setChainOfThoughtOpenByMessageId] = useState<Record<string, boolean>>({});

  const setChainOfThoughtOpen = useCallback((messageId: string, open: boolean) => {
    setChainOfThoughtOpenByMessageId((current) => ({
      ...current,
      [messageId]: open,
    }));
  }, []);

  const lastMessage = messages[messages.length - 1];
  const lastMessageId = lastMessage?.id;
  const lastMessageRole = lastMessage?.role;

  useEffect(() => {
    if (!isStreaming || !lastMessageId || lastMessageRole !== 'assistant') {
      return;
    }

    setChainOfThoughtOpenByMessageId((current) => (
      lastMessageId in current ? current : { ...current, [lastMessageId]: true }
    ));
  }, [isStreaming, lastMessageId, lastMessageRole]);

  // Last text content for "do not snap during open code fence" rule
  const lastMessageText = useMemo(() => {
    if (messages.length === 0) return '';
    return messages[messages.length - 1].parts
      .filter((p) => p.type === 'text')
      .map((p) => (p as { text: string }).text)
      .join('');
  }, [messages]);

  const atBottomThreshold = 24;

  const updateAtBottomState = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const atBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < atBottomThreshold;
    isAtBottomRef.current = atBottom;

    const nextShowButton = !atBottom && messages.length > 0;
    if (showScrollButtonRef.current !== nextShowButton) {
      showScrollButtonRef.current = nextShowButton;
      setShowScrollButton(nextShowButton);
    }
  }, [messages.length]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    scroller.scrollTo({ top: scroller.scrollHeight, behavior });
  }, []);

  useIsomorphicLayoutEffect(() => {
    if (!autoScroll || !isAtBottomRef.current) {
      updateAtBottomState();
      return;
    }

    if (isStreaming && hasOpenCodeFence(lastMessageText)) {
      updateAtBottomState();
      return;
    }

    scrollToBottom('auto');
  }, [autoScroll, isStreaming, lastMessageText, messages, scrollToBottom, updateAtBottomState]);

  const itemContent = useCallback(
    (index: number, message: ChatMessage) => {
      const isLast = index === messages.length - 1;
      const isCurrentStreaming = isStreaming && isLast;

      return (
        <Message
          message={message}
          isStreaming={isCurrentStreaming}
          renderPart={renderPart}
          onRegenerate={
            message.role === 'assistant' && onRegenerate ? () => onRegenerate(message.id) : undefined
          }
          onEditMessage={
            message.role === 'user' && onEditMessage
              ? (content) => onEditMessage(message.id, content)
              : undefined
          }
          onSwitchVersion={
            onSwitchVersion
              ? (versionIndex) => onSwitchVersion(message.id, versionIndex)
              : undefined
          }
          chainOfThoughtOpen={chainOfThoughtOpenByMessageId[message.id]}
          onChainOfThoughtOpenChange={(open) => setChainOfThoughtOpen(message.id, open)}
          onSelectOption={onSelectOption}
          onOpenCodePreview={onOpenCodePreview}
          hideToolCalls={hideToolCalls}
          onRequestScrollIntoView={() => {
            const scroller = scrollerRef.current;
            const target = messageRefs.current[message.id];
            if (!scroller || !target) return;

            scroller.scrollTo({ top: target.offsetTop, behavior: 'smooth' });
          }}
        />
      );
    },
    [
      messages.length,
      isStreaming,
      renderPart,
      onRegenerate,
      onEditMessage,
      onSwitchVersion,
      onSelectOption,
      onOpenCodePreview,
      hideToolCalls,
      chainOfThoughtOpenByMessageId,
      setChainOfThoughtOpen,
    ],
  );

  if (messages.length === 0 && emptyState) {
    return (
      <div className={cn('h-full flex items-center justify-center', className)}>{emptyState}</div>
    );
  }

  return (
    <div className={cn('relative h-full', className)}>
      <div
        ref={scrollerRef}
        className="absolute inset-0 overflow-y-auto overflow-x-hidden [overflow-anchor:none] [scrollbar-gutter:stable]"
        onScroll={updateAtBottomState}
      >
        {messages.map((message, index) => (
          <div
            key={message.id}
            ref={(element) => {
              messageRefs.current[message.id] = element;
            }}
          >
            {itemContent(index, message)}
          </div>
        ))}
        <div className="h-4" />
      </div>

      {showScrollToBottom && showScrollButton && (
        <Button
          variant="outline"
          size="icon"
          className="absolute bottom-4 left-1/2 -translate-x-1/2 h-8 w-8 rounded-full shadow-md bg-background/95 backdrop-blur-sm border-border/50 hover:bg-accent"
          onClick={() => scrollToBottom()}
        >
          <ArrowDown className="h-4 w-4" />
        </Button>
      )}
    </div>
  );
}

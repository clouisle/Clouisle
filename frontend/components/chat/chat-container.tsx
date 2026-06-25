'use client';

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
const INITIAL_RENDERED_MESSAGE_COUNT = 20;
const MESSAGE_RENDER_BATCH_SIZE = 20;

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

interface ChatMessageRowProps {
  message: ChatMessage;
  isCurrentStreaming: boolean;
  renderPart?: (part: MessagePart, index: number) => React.ReactNode;
  onRegenerate?: (messageId: string) => void;
  onEditMessage?: (messageId: string, content: string) => Promise<void>;
  onSwitchVersion?: (messageId: string, versionIndex: number) => void;
  onSelectOption?: (option: string) => void;
  onOpenCodePreview?: (payload: CodePreviewPayload) => void;
  hideToolCalls: boolean;
  chainOfThoughtOpen?: boolean;
  onChainOfThoughtOpenChange: (messageId: string, open: boolean) => void;
  onRequestScrollIntoView: (messageId: string) => void;
  setMessageElement: (messageId: string, element: HTMLDivElement | null) => void;
}

const ChatMessageRow = memo(function ChatMessageRow({
  message,
  isCurrentStreaming,
  renderPart,
  onRegenerate,
  onEditMessage,
  onSwitchVersion,
  onSelectOption,
  onOpenCodePreview,
  hideToolCalls,
  chainOfThoughtOpen,
  onChainOfThoughtOpenChange,
  onRequestScrollIntoView,
  setMessageElement,
}: ChatMessageRowProps) {
  const handleRegenerate = useCallback(() => {
    onRegenerate?.(message.id);
  }, [message.id, onRegenerate]);

  const handleEditMessage = useCallback((content: string) => {
    return onEditMessage?.(message.id, content) ?? Promise.resolve();
  }, [message.id, onEditMessage]);

  const handleSwitchVersion = useCallback((versionIndex: number) => {
    onSwitchVersion?.(message.id, versionIndex);
  }, [message.id, onSwitchVersion]);

  const handleChainOfThoughtOpenChange = useCallback((open: boolean) => {
    onChainOfThoughtOpenChange(message.id, open);
  }, [message.id, onChainOfThoughtOpenChange]);

  const handleRequestScrollIntoView = useCallback(() => {
    onRequestScrollIntoView(message.id);
  }, [message.id, onRequestScrollIntoView]);

  const setRef = useCallback((element: HTMLDivElement | null) => {
    setMessageElement(message.id, element);
  }, [message.id, setMessageElement]);

  return (
    <div ref={setRef}>
      <Message
        message={message}
        isStreaming={isCurrentStreaming}
        renderPart={renderPart}
        onRegenerate={message.role === 'assistant' && onRegenerate ? handleRegenerate : undefined}
        onEditMessage={message.role === 'user' && onEditMessage ? handleEditMessage : undefined}
        onSwitchVersion={onSwitchVersion ? handleSwitchVersion : undefined}
        chainOfThoughtOpen={chainOfThoughtOpen}
        onChainOfThoughtOpenChange={handleChainOfThoughtOpenChange}
        onSelectOption={onSelectOption}
        onOpenCodePreview={onOpenCodePreview}
        hideToolCalls={hideToolCalls}
        onRequestScrollIntoView={handleRequestScrollIntoView}
      />
    </div>
  );
}, (prev, next) => (
  prev.message === next.message
  && prev.isCurrentStreaming === next.isCurrentStreaming
  && prev.renderPart === next.renderPart
  && prev.onRegenerate === next.onRegenerate
  && prev.onEditMessage === next.onEditMessage
  && prev.onSwitchVersion === next.onSwitchVersion
  && prev.onSelectOption === next.onSelectOption
  && prev.onOpenCodePreview === next.onOpenCodePreview
  && prev.hideToolCalls === next.hideToolCalls
  && prev.chainOfThoughtOpen === next.chainOfThoughtOpen
  && prev.onChainOfThoughtOpenChange === next.onChainOfThoughtOpenChange
  && prev.onRequestScrollIntoView === next.onRequestScrollIntoView
  && prev.setMessageElement === next.setMessageElement
));

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
  const contentRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const isAtBottomRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const showScrollButtonRef = useRef(false);
  const previousMessageLengthRef = useRef(messages.length);
  const [chainOfThoughtOpenByMessageId, setChainOfThoughtOpenByMessageId] = useState<Record<string, boolean>>({});
  const [renderedMessageCount, setRenderedMessageCount] = useState(INITIAL_RENDERED_MESSAGE_COUNT);

  const setChainOfThoughtOpen = useCallback((messageId: string, open: boolean) => {
    setChainOfThoughtOpenByMessageId((current) => ({
      ...current,
      [messageId]: open,
    }));
  }, []);

  const lastMessage = messages[messages.length - 1];
  const lastMessageId = lastMessage?.id;
  const lastMessageRole = lastMessage?.role;
  const visibleMessages = useMemo(
    () => messages.slice(Math.max(0, messages.length - renderedMessageCount)),
    [messages, renderedMessageCount]
  );
  const hiddenMessageCount = messages.length - visibleMessages.length;

  useEffect(() => {
    setRenderedMessageCount((count) => Math.min(Math.max(count, INITIAL_RENDERED_MESSAGE_COUNT), messages.length));
  }, [messages.length]);
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
    if (!lastMessage) return '';
    let text = '';
    for (const part of lastMessage.parts) {
      if (part.type === 'text') {
        text += (part as { text: string }).text;
      }
    }
    return text;
  }, [lastMessage]);

  const atBottomThreshold = 24;

  const updateAtBottomState = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const atBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= atBottomThreshold;
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

    const bottom = scroller.scrollHeight + 1;
    scroller.scrollTo({ top: bottom, behavior });
  }, []);

  useIsomorphicLayoutEffect(() => {
    const previousLength = previousMessageLengthRef.current;
    previousMessageLengthRef.current = messages.length;

    if (!autoScroll || messages.length <= previousLength) {
      return;
    }

    scrollToBottom('auto');
    isAtBottomRef.current = true;
    if (showScrollButtonRef.current) {
      showScrollButtonRef.current = false;
      setShowScrollButton(false);
    }
  }, [autoScroll, messages.length, scrollToBottom]);

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
  }, [autoScroll, isStreaming, lastMessageText, lastMessageId, scrollToBottom, updateAtBottomState]);

  useIsomorphicLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const content = contentRef.current;
    if (!scroller || !content || !autoScroll || !isAtBottomRef.current) return;

    let frameId: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }

      frameId = requestAnimationFrame(() => {
        const currentScroller = scrollerRef.current;
        if (!currentScroller || !isAtBottomRef.current) return;
        currentScroller.scrollTo({ top: currentScroller.scrollHeight + 1, behavior: 'auto' });
      });
    });

    resizeObserver.observe(content);
    return () => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }
      resizeObserver.disconnect();
    };
  }, [autoScroll, lastMessageId]);

  const setMessageElement = useCallback((messageId: string, element: HTMLDivElement | null) => {
    messageRefs.current[messageId] = element;
  }, []);

  const requestMessageScrollIntoView = useCallback((messageId: string) => {
    const scroller = scrollerRef.current;
    const target = messageRefs.current[messageId];
    if (!scroller || !target) return;

    scroller.scrollTo({ top: target.offsetTop, behavior: 'smooth' });
  }, []);

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
        <div ref={contentRef}>
          {hiddenMessageCount > 0 && (
            <div className="flex justify-center py-3">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setRenderedMessageCount((count) => Math.min(messages.length, count + MESSAGE_RENDER_BATCH_SIZE))}
              >
                Load {Math.min(hiddenMessageCount, MESSAGE_RENDER_BATCH_SIZE)} older messages
              </Button>
            </div>
          )}
          {visibleMessages.map((message, index) => {
            const messageIndex = hiddenMessageCount + index;
            const isCurrentStreaming = isStreaming && messageIndex === messages.length - 1;
            return (
              <ChatMessageRow
                key={message.id}
                message={message}
                isCurrentStreaming={isCurrentStreaming}
                renderPart={renderPart}
                onRegenerate={onRegenerate}
                onEditMessage={onEditMessage}
                onSwitchVersion={onSwitchVersion}
                onSelectOption={onSelectOption}
                onOpenCodePreview={onOpenCodePreview}
                hideToolCalls={hideToolCalls}
                chainOfThoughtOpen={chainOfThoughtOpenByMessageId[message.id]}
                onChainOfThoughtOpenChange={setChainOfThoughtOpen}
                onRequestScrollIntoView={requestMessageScrollIntoView}
                setMessageElement={setMessageElement}
              />
            );
          })}
          <div className="h-4" />
        </div>
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

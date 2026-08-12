'use client';

import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ArrowDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Message } from './message';
import type { ChatMessage, ChatPreviewPayload, MessagePart } from './types';

interface ChatContainerProps {
  messages: ChatMessage[];
  className?: string;
  isStreaming?: boolean;
  isLoading?: boolean;
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
  /** Callback when a generated image is selected as a later reference */
  onSelectImageReference?: (image: { asset_ref: string; url: string }) => void;
  /** Show scroll to bottom button when not at bottom */
  showScrollToBottom?: boolean;
  /** Callback when a previewable code block is opened */
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void;
  /** Hide tool call cards and tool execution details */
  hideToolCalls?: boolean;
  /** Hide token usage/speed stats popover */
  hideMessageActions?: boolean;
  /** Hide reasoning / chain-of-thought panel */
  hideReasoning?: boolean;
  /** Current conversation ID (shown on errors for debugging) */
  conversationId?: string | null;
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
  onSelectImageReference?: (image: { asset_ref: string; url: string }) => void;
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void;
  hideToolCalls: boolean;
  hideMessageActions: boolean;
  hideReasoning: boolean;
  conversationId?: string | null;
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
  onSelectImageReference,
  onOpenCodePreview,
  hideToolCalls,
  hideMessageActions,
  hideReasoning,
  conversationId,
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
        onSelectImageReference={onSelectImageReference}
        onOpenCodePreview={onOpenCodePreview}
        hideToolCalls={hideToolCalls}
        hideMessageActions={hideMessageActions}
        hideReasoning={hideReasoning}
        conversationId={conversationId}
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
  && prev.onSelectImageReference === next.onSelectImageReference
  && prev.onOpenCodePreview === next.onOpenCodePreview
  && prev.hideToolCalls === next.hideToolCalls
  && prev.hideMessageActions === next.hideMessageActions
  && prev.hideReasoning === next.hideReasoning
  && prev.conversationId === next.conversationId
  && prev.chainOfThoughtOpen === next.chainOfThoughtOpen
  && prev.onChainOfThoughtOpenChange === next.onChainOfThoughtOpenChange
  && prev.onRequestScrollIntoView === next.onRequestScrollIntoView
  && prev.setMessageElement === next.setMessageElement
));

export function ChatContainer({
  messages,
  className,
  isStreaming = false,
  isLoading = false,
  autoScroll = true,
  renderPart,
  emptyState,
  onRegenerate,
  onEditMessage,
  onSwitchVersion,
  onSelectOption,
  onSelectImageReference,
  showScrollToBottom = true,
  onOpenCodePreview,
  hideToolCalls = false,
  hideMessageActions = false,
  hideReasoning = false,
  conversationId,
}: ChatContainerProps) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const isAtBottomRef = useRef(true);
  const shouldAutoFollowRef = useRef(true);
  // Set once the container has positioned itself at the newest message on mount.
  const hasPositionedRef = useRef(false);
  // Scroll anchor captured when "load older" is clicked, to keep the reading
  // position stable once the older batch is inserted above the viewport.
  const pendingLoadOlderRef = useRef<{ scrollHeight: number; scrollTop: number } | null>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const showScrollButtonRef = useRef(false);
  const previousMessageLengthRef = useRef(messages.length);
  const previousConversationIdRef = useRef(conversationId);
  const [chainOfThoughtOpenByMessageId, setChainOfThoughtOpenByMessageId] = useState<Record<string, boolean>>({});
  const [renderedMessageCount, setRenderedMessageCount] = useState(INITIAL_RENDERED_MESSAGE_COUNT);
  const t = useTranslations('chat');

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
    setRenderedMessageCount((count) => Math.max(Math.min(count, messages.length), INITIAL_RENDERED_MESSAGE_COUNT));
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

  const isScrollerAtBottom = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return true;
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight <= atBottomThreshold;
  }, []);

  const updateAtBottomState = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const atBottom = isScrollerAtBottom();
    isAtBottomRef.current = atBottom;
    shouldAutoFollowRef.current = atBottom;

    const nextShowButton = !atBottom && messages.length > 0;
    if (showScrollButtonRef.current !== nextShowButton) {
      showScrollButtonRef.current = nextShowButton;
      setShowScrollButton(nextShowButton);
    }
  }, [isScrollerAtBottom, messages.length]);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const bottom = scroller.scrollHeight + 1;
    scroller.scrollTo({ top: bottom, behavior });
    isAtBottomRef.current = true;
    shouldAutoFollowRef.current = true;
  }, []);

  useIsomorphicLayoutEffect(() => {
    const previousLength = previousMessageLengthRef.current;
    const conversationChanged = previousConversationIdRef.current !== conversationId;
    previousMessageLengthRef.current = messages.length;
    previousConversationIdRef.current = conversationId;

    if (conversationChanged) {
      shouldAutoFollowRef.current = false;
      hasPositionedRef.current = false;
      return;
    }

    if (!autoScroll || messages.length <= previousLength) {
      return;
    }

    const appendedUserMessage = messages
      .slice(previousLength)
      .some((message) => message.role === 'user');
    if ((!isLoading && !isStreaming) || !appendedUserMessage) {
      shouldAutoFollowRef.current = false;
      return;
    }

    scrollToBottom('auto');
    if (showScrollButtonRef.current) {
      showScrollButtonRef.current = false;
      setShowScrollButton(false);
    }
  }, [autoScroll, conversationId, isLoading, isStreaming, messages, scrollToBottom]);

  useIsomorphicLayoutEffect(() => {
    if (!autoScroll) {
      return;
    }

    if (isStreaming && hasOpenCodeFence(lastMessageText)) {
      updateAtBottomState();
      return;
    }

    if (!hasPositionedRef.current) {
      // Initial placement: start at the newest message.
      hasPositionedRef.current = true;
      scrollToBottom('auto');
      return;
    }

    // Follow the stream only while the user is actually at the bottom. The
    // scroll event is delivered asynchronously after the user's wheel input,
    // so shouldAutoFollowRef can lag by one frame; checking the live position
    // here prevents a chunk commit from yanking the view back down while the
    // user is reading history.
    if (!isScrollerAtBottom()) {
      return;
    }
    scrollToBottom('auto');
  }, [autoScroll, isStreaming, lastMessageText, lastMessageId, scrollToBottom, updateAtBottomState, isScrollerAtBottom]);

  useIsomorphicLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const content = contentRef.current;
    if (!scroller || !content || !autoScroll || !shouldAutoFollowRef.current) return;

    let frameId: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (frameId !== null) {
        cancelAnimationFrame(frameId);
      }

      frameId = requestAnimationFrame(() => {
        const currentScroller = scrollerRef.current;
        if (!currentScroller) return;
        // Same live-position check as the streaming follow: never pull the
        // view down when the user has scrolled away from the bottom.
        if (currentScroller.scrollHeight - currentScroller.scrollTop - currentScroller.clientHeight > atBottomThreshold) {
          return;
        }
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

  const handleLoadOlder = useCallback(() => {
    const scroller = scrollerRef.current;
    if (scroller) {
      pendingLoadOlderRef.current = {
        scrollHeight: scroller.scrollHeight,
        scrollTop: scroller.scrollTop,
      };
    }
    setRenderedMessageCount((count) => Math.min(messages.length, count + MESSAGE_RENDER_BATCH_SIZE));
  }, [messages.length]);

  // After an older batch is inserted above the viewport, keep the reading
  // position stable by shifting scrollTop by the added height (the scroller
  // has overflow-anchor:none, so the browser will not do this for us).
  useIsomorphicLayoutEffect(() => {
    const anchor = pendingLoadOlderRef.current;
    if (!anchor) return;
    pendingLoadOlderRef.current = null;

    const scroller = scrollerRef.current;
    if (!scroller) return;
    const delta = scroller.scrollHeight - anchor.scrollHeight;
    if (delta !== 0) {
      scroller.scrollTop = anchor.scrollTop + delta;
    }
  });

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
                onClick={handleLoadOlder}
              >
                {t('message.loadOlderMessages', { count: Math.min(hiddenMessageCount, MESSAGE_RENDER_BATCH_SIZE) })}
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
                onSelectImageReference={onSelectImageReference}
                onOpenCodePreview={onOpenCodePreview}
                hideToolCalls={hideToolCalls}
                hideMessageActions={hideMessageActions}
                hideReasoning={hideReasoning}
                conversationId={conversationId}
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

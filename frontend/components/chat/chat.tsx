'use client';

import { cn } from '@/lib/utils';
import { ChatContainer } from './chat-container';
import { ChatInput, type ChatInputFile } from './chat-input';
import type { ChatMessage, MessagePart } from './types';

interface ChatProps {
  messages: ChatMessage[];
  className?: string;
  isStreaming?: boolean;
  isLoading?: boolean;
  autoScroll?: boolean;
  renderPart?: (part: MessagePart, index: number) => React.ReactNode;
  emptyState?: React.ReactNode;
  // Input props
  inputValue?: string;
  onInputChange?: (value: string) => void;
  onSubmit?: (message: string, files?: ChatInputFile[]) => void;
  onStop?: () => void;
  placeholder?: string;
  allowAttachments?: boolean;
  inputDisabled?: boolean;
  // Callbacks
  onSelectOption?: (option: string) => void;
  // Layout
  inputPosition?: 'bottom' | 'sticky';
  containerClassName?: string;
  inputClassName?: string;
}

export function Chat({
  messages,
  className,
  isStreaming = false,
  isLoading = false,
  autoScroll = true,
  renderPart,
  emptyState,
  // Input props
  inputValue,
  onInputChange,
  onSubmit,
  onStop,
  placeholder,
  allowAttachments = true,
  inputDisabled = false,
  // Callbacks
  onSelectOption,
  // Layout
  inputPosition = 'bottom',
  containerClassName,
  inputClassName,
}: ChatProps) {
  return (
    <div className={cn('flex flex-col h-full', className)}>
      {/* Messages Container */}
      <ChatContainer
        messages={messages}
        isStreaming={isStreaming}
        autoScroll={autoScroll}
        renderPart={renderPart}
        emptyState={emptyState}
        onSelectOption={onSelectOption}
        className={containerClassName}
      />

      {/* Input Area */}
      <div
        className={cn(
          'relative pb-4',
          inputPosition === 'sticky' && 'sticky bottom-0'
        )}
      >
        <ChatInput
          value={inputValue}
          onChange={onInputChange}
          onSubmit={onSubmit}
          onStop={onStop}
          placeholder={placeholder}
          disabled={inputDisabled}
          isLoading={isLoading}
          isStreaming={isStreaming}
          allowAttachments={allowAttachments}
          className={inputClassName}
        />
      </div>
    </div>
  );
}

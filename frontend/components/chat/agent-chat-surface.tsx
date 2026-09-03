'use client'

import * as React from 'react'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { ChatInputFile, AttachmentConfig } from './chat-input'
import { ChatContainer } from './chat-container'
import { ChatInput } from './chat-input'
import { PendingAskUserForm, type PendingAskUserFormProps } from './ask-user-form'
import { VariableForm } from './variable-form'
import type { ChatMessage, ChatPreviewPayload, MessagePart } from './types'
import type { RunVariableDefinition } from '@/lib/utils/extract-variables'

type ImageReference = {
  asset_ref: string
  url: string
}

export interface AgentChatEmptyStateProps {
  agentName: string
  icon?: string | null
  avatarUrl?: string | null
  openingMessage?: string | null
  fallbackMessage: string
  suggestedQuestions?: string[]
  onSuggestedQuestion: (question: string) => void | Promise<void>
}

/**
 * Shared welcome content for the debug and preview agent chat surfaces.
 * Message history stays in AgentChatSurface; this component only owns the
 * empty-state presentation and suggested-question actions.
 */
export function AgentChatEmptyState({
  agentName,
  icon,
  avatarUrl,
  openingMessage,
  fallbackMessage,
  suggestedQuestions = [],
  onSuggestedQuestion,
}: AgentChatEmptyStateProps) {
  const displayIcon = icon || avatarUrl
  const isIconUrl = Boolean(displayIcon && (displayIcon.startsWith('http') || displayIcon.startsWith('/')))

  return (
    <div className="flex w-full max-w-3xl flex-col items-center px-4 py-6 text-center">
      <div className="mb-8">
        {displayIcon ? (
          isIconUrl ? (
            <div className="relative h-20 w-20 overflow-hidden rounded-full ring-2 ring-border">
              <Image src={displayIcon} alt={agentName} fill unoptimized className="object-cover" />
            </div>
          ) : (
            <div className="flex h-20 w-20 items-center justify-center rounded-full bg-muted ring-2 ring-border">
              <span className="text-4xl leading-none">{displayIcon}</span>
            </div>
          )
        ) : (
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Sparkles className="h-6 w-6 text-primary" />
          </div>
        )}
      </div>

      <h1 className="mb-4 max-w-3xl text-center text-2xl font-medium text-foreground md:text-3xl">
        {openingMessage || fallbackMessage}
      </h1>

      {suggestedQuestions.length > 0 && (
        <div className="mt-4 grid w-full max-w-[614px] grid-cols-1 gap-2 sm:grid-cols-2">
          {suggestedQuestions.slice(0, 4).map((question, index) => (
            <button
              key={`${question}-${index}`}
              type="button"
              onClick={() => void onSuggestedQuestion(question)}
              className="w-full min-w-0 break-words rounded-lg border border-border px-4 py-2 text-center text-sm text-foreground/80 transition-colors hover:bg-accent"
            >
              {question}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export interface AgentChatSurfaceProps {
  messages: ChatMessage[]
  isStreaming?: boolean
  isLoading?: boolean
  loadingLabel?: string
  autoScroll?: boolean
  renderPart?: (part: MessagePart, index: number) => React.ReactNode
  emptyState?: React.ReactNode
  onRegenerate?: (messageId: string) => void
  onEditMessage?: (messageId: string, content: string) => Promise<void>
  onSwitchVersion?: (messageId: string, versionIndex: number) => void
  onSelectImageReference?: (reference: ImageReference) => void
  onOpenCodePreview?: (payload: ChatPreviewPayload) => void
  hideToolCalls?: boolean
  hideMessageActions?: boolean
  hideReasoning?: boolean
  conversationId?: string | null
  headerInset?: boolean
  showUserMessageScale?: boolean
  className?: string

  inputValue: string
  onInputChange: (value: string) => void
  onSubmit: (message: string, files?: ChatInputFile[]) => void | Promise<void>
  onStop?: () => void
  placeholder?: string
  inputDisabled?: boolean
  allowAttachments?: boolean
  enableFileUpload?: boolean
  fileUploadConfig?: AttachmentConfig | null
  files?: ChatInputFile[]
  onFilesChange?: (files: ChatInputFile[]) => void
  isUploading?: boolean

  pendingAskUserToolCallId?: string | null
  onSubmitAskUser?: PendingAskUserFormProps['onSubmit']

  variables?: RunVariableDefinition[]
  variableValues?: Record<string, unknown>
  onVariablesChange?: (values: Record<string, unknown>) => void
  variableFieldErrors?: Record<string, string>
  variablesOpen?: boolean
  onVariablesOpenChange?: (open: boolean) => void
  variableTitle?: string
  poweredByText?: string | null
}

function isFilledRequiredVariable(variable: RunVariableDefinition, value: unknown): boolean {
  if (variable.type === 'checkbox') return true

  if (variable.type === 'array') {
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string' && value.trim()) {
      try {
        const parsed = JSON.parse(value)
        return Array.isArray(parsed) && parsed.length > 0
      } catch {
        return false
      }
    }
    return false
  }

  if (variable.type === 'object') {
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      return Object.keys(value).length > 0
    }
    if (typeof value === 'string' && value.trim()) {
      try {
        const parsed = JSON.parse(value)
        return typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed) && Object.keys(parsed).length > 0
      } catch {
        return false
      }
    }
    return false
  }

  return value !== undefined && value !== null && value !== ''
}

/**
 * Shared message/composer shell for agent debug and preview pages.
 * Page-specific data loading and submission policies stay in the callers;
 * message rendering, pending ask_user placement, variables, and composer
 * layout are maintained here in one place.
 */
export function AgentChatSurface({
  messages,
  isStreaming = false,
  isLoading = false,
  loadingLabel,
  autoScroll = true,
  renderPart,
  emptyState,
  onRegenerate,
  onEditMessage,
  onSwitchVersion,
  onSelectImageReference,
  onOpenCodePreview,
  hideToolCalls = false,
  hideMessageActions = false,
  hideReasoning = false,
  conversationId,
  headerInset = false,
  showUserMessageScale = false,
  className,
  inputValue,
  onInputChange,
  onSubmit,
  onStop,
  placeholder,
  inputDisabled = false,
  allowAttachments = false,
  enableFileUpload = false,
  fileUploadConfig,
  files,
  onFilesChange,
  isUploading = false,
  pendingAskUserToolCallId,
  onSubmitAskUser,
  variables = [],
  variableValues = {},
  onVariablesChange,
  variableFieldErrors,
  variablesOpen = true,
  onVariablesOpenChange,
  variableTitle,
  poweredByText,
}: AgentChatSurfaceProps) {
  const tVars = useTranslations('chat.variables')
  const hasVisibleVariables = variables.some((variable) => !variable.hidden)
  const requiredVariables = variables.filter((variable) => !variable.hidden && variable.required)
  const filledRequiredCount = requiredVariables.filter((variable) => (
    isFilledRequiredVariable(variable, variableValues[variable.name])
  )).length
  const hasPendingAskUser = Boolean(pendingAskUserToolCallId)

  const variablePanel = hasVisibleVariables && onVariablesChange ? (
    <div className="mx-auto w-full max-w-3xl px-4">
      <Collapsible open={variablesOpen} onOpenChange={onVariablesOpenChange}>
        <div className="mx-auto w-[70%] overflow-hidden rounded-t-lg border border-b-0 bg-muted/30">
          <CollapsibleTrigger className="flex w-full items-center justify-between px-2.5 py-1.5 text-xs transition-colors hover:bg-muted/50">
            <span className="flex items-center gap-1.5 text-xs font-medium">
              {variableTitle || tVars('title')}
              {requiredVariables.length > 0 && (
                <span className={cn(
                  'rounded px-1 py-0.5 text-[10px]',
                  filledRequiredCount === requiredVariables.length
                    ? 'bg-green-100 text-green-700'
                    : 'bg-orange-100 text-orange-700'
                )}>
                  {filledRequiredCount}/{requiredVariables.length}
                </span>
              )}
            </span>
            {variablesOpen ? (
              <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="px-2.5 pb-2.5 pt-0.5">
              <VariableForm
                variables={variables}
                values={variableValues}
                onChange={onVariablesChange}
                fieldErrors={variableFieldErrors}
                className="space-y-2"
              />
            </div>
          </CollapsibleContent>
        </div>
      </Collapsible>
    </div>
  ) : null

  return (
    <div className={cn('flex min-h-0 flex-1 flex-col overflow-hidden', className)}>
      <ChatContainer
        messages={messages}
        isStreaming={isStreaming}
        isLoading={isLoading}
        loadingLabel={loadingLabel}
        autoScroll={autoScroll}
        renderPart={renderPart}
        emptyState={emptyState}
        onRegenerate={onRegenerate}
        onEditMessage={onEditMessage}
        onSwitchVersion={onSwitchVersion}
        onSelectImageReference={onSelectImageReference}
        onOpenCodePreview={onOpenCodePreview}
        hideToolCalls={hideToolCalls}
        hideMessageActions={hideMessageActions}
        hideReasoning={hideReasoning}
        conversationId={conversationId}
        headerInset={headerInset}
        showUserMessageScale={showUserMessageScale}
        className="min-h-0 flex-1 overflow-y-auto"
      />

      <div className="relative shrink-0 pb-4">
        {hasPendingAskUser ? (
          <PendingAskUserForm
            messages={messages}
            pendingToolCallId={pendingAskUserToolCallId}
            disabled={isStreaming}
            onSubmit={onSubmitAskUser}
          />
        ) : (
          variablePanel
        )}
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
          enableFileUpload={enableFileUpload}
          fileUploadConfig={fileUploadConfig}
          files={files}
          onFilesChange={onFilesChange}
          isUploading={isUploading}
        />
        {poweredByText && (
          <p className="mt-2 text-center text-[11px] text-muted-foreground">{poweredByText}</p>
        )}
      </div>
    </div>
  )
}


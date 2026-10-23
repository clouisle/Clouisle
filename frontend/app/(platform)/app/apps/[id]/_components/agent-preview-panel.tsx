'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { RotateCcw, AlertCircle, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ApiError, type Agent, type ChatFileUrl } from '@/lib/api'
import { uploadApi } from '@/lib/api'
import {
  AgentChatEmptyState,
  AgentChatSurface,
  useVariableForm,
  type ChatInputFile,
} from '@/components/chat'
import { useChat, type ChatError, getErrorMsgKey } from '@/hooks/use-chat'

interface AgentPreviewPanelProps {
  agent: Agent
  onClose?: () => void
}

function showUploadValidationError(error: unknown, tCommon: ReturnType<typeof useTranslations>) {
  if (error instanceof ApiError && error.code === 1001) {
    const payload = error.data as { allowed?: string[] } | undefined
    const allowed = payload?.allowed?.join(', ')
    toast.error(
      allowed
        ? tCommon('invalidFileTypeWithAllowed', { allowed })
        : tCommon('invalidFileType')
    )
  }
}

export function AgentPreviewPanel({ agent, onClose }: AgentPreviewPanelProps) {
  const t = useTranslations('agents.orchestration.preview')
  const tVars = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const tError = useTranslations('errors')
  const tMessage = useTranslations('chat.message')
  const [input, setInput] = React.useState('')
  const [showError, setShowError] = React.useState(false)
  const [variablesOpen, setVariablesOpen] = React.useState(
    () => (agent.variables || []).some(v => !v.hidden && v.required)
  )
  
  // File upload state with progress tracking
  const [files, setFiles] = React.useState<ChatInputFile[]>([])
  const [isUploading, setIsUploading] = React.useState(false)
  const [variableAssetIds, setVariableAssetIds] = React.useState<Record<string, string | string[]>>({})

  // Variable form state
  const {
    values: variableValues,
    setValues: setVariableValues,
    needsInput: needsVariableInput,
    isValid: variablesValid,
    fieldErrors: variableFieldErrors,
    validate: validateVariables,
    reset: resetVariables,
  } = useVariableForm(agent.variables || [])

  
  const {
    messages,
    error,
    isLoading,
    isStreaming,
    conversationId,
    runStatus,
    pendingAskUserToolCallId,
    sendMessage,
    submitAskUser,
    regenerate,
    editMessage,
    switchVersion,
    stop,
    reset,
  } = useChat({
    agentId: agent.id,
    variables: variableValues,
    onError: () => setShowError(true),
  })


  // Handle submit - check if required variables are filled
  const handleSubmit = async (message: string, submittedFiles?: ChatInputFile[]) => {
    if (!message.trim() && !(submittedFiles ?? files).length) return
    if (needsVariableInput && !validateVariables()) {
      setVariablesOpen(true)
      return
    }
    setShowError(false)
    
    // Use submittedFiles from param or current files state
    const filesToProcess = submittedFiles || files
    
    let fileUrls: ChatFileUrl[] | undefined
    if (filesToProcess.length > 0) {
      if (!agent.enable_attachments) return
      setIsUploading(true)
      try {
        fileUrls = await Promise.all(filesToProcess.map(async (item) => {
          const updateProgress = (progress: { percent: number }) => {
            setFiles(prev => prev.map(file =>
              file.id === item.id ? { ...file, isUploading: true, uploadProgress: progress.percent } : file
            ))
          }
          setFiles(prev => prev.map(file =>
            file.id === item.id ? { ...file, isUploading: true, uploadProgress: 0 } : file
          ))
          const result = await uploadApi.uploadFileWithProgress(
            item.file,
            item.isDocument ? 'documents' : 'files',
            updateProgress
          )
          setFiles(prev => prev.map(file =>
            file.id === item.id ? { ...file, isUploading: false, uploadProgress: 100 } : file
          ))
          return { asset_id: result.asset_id, filename: item.name, url: result.url, size: item.size, mime_type: item.type }
        }))
      } catch (error) {
        console.error('Failed to upload files:', error)
        showUploadValidationError(error, tCommon)
        setFiles(prev => prev.map(file => ({ ...file, isUploading: false, uploadProgress: undefined })))
        return
      } finally {
        setIsUploading(false)
      }
    }
    await sendMessage(message, undefined, fileUrls, Object.values(variableAssetIds).flatMap((value) => Array.isArray(value) ? value : [value]))
    setInput('')
    setFiles([])
  }

  // Handle reset
  const handleReset = () => {
    reset()
    setVariableAssetIds({})
    resetVariables()
    setInput('')
    setFiles([])
    setIsUploading(false)
    setShowError(false)
    setVariablesOpen(true)
  }

  // Get error message
  const getErrorMessage = (err: ChatError) => {
    // Try to get i18n key first
    const msgKey = getErrorMsgKey(err)
    if (msgKey) {
      if (msgKey === 'quotaExceeded' && err.quotaType) {
        const quotaTypeKey = err.quotaType === 'input'
          ? 'quotaTypeInput'
          : err.quotaType === 'output'
            ? 'quotaTypeOutput'
            : 'quotaTypeUsage'
        return tError('quotaExceeded', { type: tError(quotaTypeKey) })
      }
      return tError(msgKey)
    }
    return err.message || tError('unknown')
  }


  return (
    <div className="flex flex-col h-full min-h-0 max-h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <h3 className="font-medium">{t('title')}</h3>
        <div className="flex items-center gap-1">
          {onClose && (
            <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose} aria-label={t('closePreview')}>
              <X className="h-4 w-4" />
            </Button>
          )}
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleReset}>
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Error Banner */}
      {showError && error && (
        <div className="mx-4 mt-3 flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-3 py-2 text-sm text-destructive shrink-0">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="flex-1">{getErrorMessage(error)}</span>
          <button
            onClick={() => setShowError(false)}
            className="shrink-0 rounded p-0.5 hover:bg-destructive/20"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <AgentChatSurface
        messages={messages}
        isStreaming={isStreaming}
        isLoading={isLoading}
        loadingLabel={runStatus === 'queued' ? tMessage('runStatusQueued') : runStatus === 'waiting' ? tMessage('runStatusWaiting') : runStatus === 'stopping' ? tMessage('runStatusStopping') : undefined}
        hideToolCalls={agent.hide_tool_calls}
        hideMessageActions={agent.hide_message_actions}
        hideReasoning={agent.hide_reasoning}
        hideCitations={!agent.enable_citations}
        hideArtifactList={agent.hide_artifact_list}
        conversationId={conversationId}
        onRegenerate={regenerate}
        onEditMessage={editMessage}
        onSwitchVersion={switchVersion}
        emptyState={
          <AgentChatEmptyState
            agentName={agent.name}
            icon={agent.icon}
            avatarUrl={agent.avatar_url}
            openingMessage={agent.opening_message}
            fallbackMessage={t('empty')}
            suggestedQuestions={agent.suggested_questions}
            onSuggestedQuestion={handleSubmit}
          />
        }
        inputValue={input}
        onInputChange={setInput}
        onSubmit={handleSubmit}
        onStop={stop}
        placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : t('placeholder')}
        inputDisabled={(isLoading && !isStreaming) || runStatus === 'waiting'}
        allowAttachments={agent.enable_attachments}
        enableFileUpload={agent.enable_attachments}
        inputModalities={agent.input_modalities ?? ['text']}
        fileUploadConfig={agent.attachment_config}
        files={files}
        onFilesChange={setFiles}
        isUploading={isUploading}
        pendingAskUserToolCallId={pendingAskUserToolCallId}
        onSubmitAskUser={submitAskUser}
        variables={agent.variables || []}
        variableValues={variableValues}
        onVariableAssetIdsChange={(name, ids) => setVariableAssetIds((previous) => {
          const next = { ...previous }
          if (ids === null) delete next[name]
          else next[name] = ids
          return next
        })}
        onVariablesChange={setVariableValues}
        variableFieldErrors={variableFieldErrors}
        variablesOpen={variablesOpen}
        onVariablesOpenChange={setVariablesOpen}
        poweredByText={agent.powered_by_text}
        className="flex-1"
      />
    </div>
  )
}

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { RotateCcw, Sparkles, AlertCircle, X, ChevronUp, ChevronDown } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { ApiError, type Agent, type ChatFileUrl } from '@/lib/api'
import { uploadApi } from '@/lib/api'
import {
  ChatContainer,
  ChatInput,
  VariableForm,
  useVariableForm,
  type ChatInputFile,
} from '@/components/chat'
import { useChat, type ChatError, type ChatImageContent, getErrorMsgKey } from '@/hooks/use-chat'
import { cn } from '@/lib/utils'

// Helper function to convert File to base64 data URL
async function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

interface AgentPreviewPanelProps {
  agent: Agent
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

export function AgentPreviewPanel({ agent }: AgentPreviewPanelProps) {
  const t = useTranslations('agents.orchestration.preview')
  const tVars = useTranslations('chat.variables')
  const tCommon = useTranslations('common')
  const tError = useTranslations('errors')
  const [input, setInput] = React.useState('')
  const [showError, setShowError] = React.useState(false)
  const [variablesOpen, setVariablesOpen] = React.useState(true)
  
  // File upload state with progress tracking
  const [files, setFiles] = React.useState<ChatInputFile[]>([])
  const [isUploading, setIsUploading] = React.useState(false)

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

  // Check if there are any visible variables
  const hasVisibleVariables = (agent.variables || []).some((v) => !v.hidden)
  
  const {
    messages,
    error,
    isLoading,
    isStreaming,
    sendMessage,
    regenerate,
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
    if (!message.trim()) return
    if (needsVariableInput && !validateVariables()) {
      setVariablesOpen(true)
      return
    }
    setShowError(false)
    
    // Use submittedFiles from param or current files state
    const filesToProcess = submittedFiles || files
    
    // Separate image files (for vision) and document files (for file upload)
    let images: ChatImageContent[] | undefined
    let fileUrls: ChatFileUrl[] | undefined
    
    if (filesToProcess && filesToProcess.length > 0) {
      // Process image files for vision
      if (agent.enable_vision) {
        const imageFiles = filesToProcess.filter(f => f.type.startsWith('image/') && !f.isDocument)
        if (imageFiles.length > 0) {
          images = await Promise.all(
            imageFiles.map(async (f) => ({
              type: 'image_url' as const,
              url: await fileToDataUrl(f.file),
            }))
          )
        }
      }
      
      // Process document files for file upload - upload to get URLs with progress
      if (agent.enable_file_upload) {
        const documentFiles = filesToProcess.filter(f => f.isDocument)
        if (documentFiles.length > 0) {
          try {
            setIsUploading(true)
            
            // Upload documents with progress tracking
            const uploadPromises = documentFiles.map(async (f) => {
              // Update file progress
              const updateProgress = (progress: { percent: number }) => {
                setFiles(prev => prev.map(file => 
                  file.id === f.id 
                    ? { ...file, isUploading: true, uploadProgress: progress.percent }
                    : file
                ))
              }
              
              // Mark as uploading
              setFiles(prev => prev.map(file => 
                file.id === f.id 
                  ? { ...file, isUploading: true, uploadProgress: 0 }
                  : file
              ))
              
              const result = await uploadApi.uploadFileWithProgress(
                f.file, 
                'documents',
                updateProgress
              )
              
              // Mark as complete
              setFiles(prev => prev.map(file => 
                file.id === f.id 
                  ? { ...file, isUploading: false, uploadProgress: 100 }
                  : file
              ))
              
              return {
                filename: f.name,
                url: result.url,
                size: f.size,
                mime_type: f.type,
              }
            })
            fileUrls = await Promise.all(uploadPromises)
          } catch (err) {
            console.error('Failed to upload files:', err)
            showUploadValidationError(err, tCommon)
            // Reset upload state on error
            setFiles(prev => prev.map(file => ({
              ...file,
              isUploading: false,
              uploadProgress: undefined
            })))
          } finally {
            setIsUploading(false)
          }
        }
      }
    }
    
    await sendMessage(message, images, fileUrls)
    setInput('')
    setFiles([])
  }

  // Handle reset
  const handleReset = () => {
    reset()
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

  // Count required variables
  const requiredCount = (agent.variables || []).filter((v) => !v.hidden && v.required).length
  const filledRequiredCount = (agent.variables || []).filter((v) => {
    if (v.hidden || !v.required) return false
    const value = variableValues[v.name]
    if (v.type === 'checkbox') return true
    return value !== undefined && value !== null && value !== ''
  }).length

  return (
    <div className="flex flex-col h-full min-h-0 max-h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <h3 className="font-medium">{t('title')}</h3>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={handleReset}>
          <RotateCcw className="h-4 w-4" />
        </Button>
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

      {/* Messages */}
      <div className="flex-1 min-h-0 overflow-hidden">
        <ChatContainer
          messages={messages}
          isStreaming={isStreaming}
          className="h-full"
          onRegenerate={regenerate}
          onSwitchVersion={switchVersion}
          onSelectOption={(option) => {
            void handleSubmit(option, [])
          }}
          emptyState={
            <div className="text-center text-muted-foreground py-8 px-4">
              <div className="flex justify-center mb-4">
                <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                  <Sparkles className="h-6 w-6 text-primary" />
                </div>
              </div>
              <p className="text-sm">{t('empty')}</p>
              {/* Suggested questions */}
              {agent.suggested_questions && agent.suggested_questions.length > 0 && (
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {agent.suggested_questions.slice(0, 3).map((question, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSubmit(question)}
                      className="px-3 py-1.5 text-xs rounded-full border bg-background hover:bg-muted transition-colors cursor-pointer"
                    >
                      {question}
                    </button>
                  ))}
                </div>
              )}
            </div>
          }
        />
      </div>

      {/* Input Area with Variables */}
      <div className="relative pb-4 shrink-0">
        {/* Variable Panel - Collapsible above input */}
        {hasVisibleVariables && (
          <div className="mx-auto max-w-3xl px-4">
            <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
              <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                  <span className="text-muted-foreground">
                    {tVars('title')}
                    {requiredCount > 0 && (
                      <span className={cn(
                        "ml-1.5",
                        filledRequiredCount === requiredCount ? "text-green-600" : "text-orange-500"
                      )}>
                        {filledRequiredCount}/{requiredCount}
                      </span>
                    )}
                  </span>
                  {variablesOpen ? (
                    <ChevronDown className="h-3 w-3 text-muted-foreground" />
                  ) : (
                    <ChevronUp className="h-3 w-3 text-muted-foreground" />
                  )}
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <div className="px-2.5 pb-2.5 pt-0.5">
                    <VariableForm
                      variables={agent.variables || []}
                      values={variableValues}
                      onChange={setVariableValues}
                      fieldErrors={variableFieldErrors}
                      className="space-y-2"
                    />
                  </div>
                </CollapsibleContent>
              </div>
            </Collapsible>
          </div>
        )}

        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          onStop={stop}
          placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : t('placeholder')}
          disabled={isLoading && !isStreaming}
          isLoading={isLoading}
          isStreaming={isStreaming}
          allowAttachments={agent.enable_vision}
          enableFileUpload={agent.enable_file_upload}
          fileUploadConfig={agent.file_upload_config}
          files={files}
          onFilesChange={setFiles}
          isUploading={isUploading}
        />
      </div>
    </div>
  )
}

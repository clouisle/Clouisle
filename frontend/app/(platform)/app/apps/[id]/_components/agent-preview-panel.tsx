'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { RotateCcw, Sparkles, AlertCircle, X, ChevronUp, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import type { Agent } from '@/lib/api'
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

export function AgentPreviewPanel({ agent }: AgentPreviewPanelProps) {
  const t = useTranslations('agents.orchestration.preview')
  const tVars = useTranslations('chat.variables')
  const tError = useTranslations('errors')
  const [input, setInput] = React.useState('')
  const [showError, setShowError] = React.useState(false)
  const [variablesOpen, setVariablesOpen] = React.useState(true)

  // Variable form state
  const {
    values: variableValues,
    setValues: setVariableValues,
    needsInput: needsVariableInput,
    isValid: variablesValid,
    reset: resetVariables,
  } = useVariableForm(agent.variables || [])

  // Check if there are any visible variables
  const hasVisibleVariables = (agent.variables || []).some((v) => !v.hidden)
  
  const {
    messages,
    status,
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
  const handleSubmit = async (message: string, files?: ChatInputFile[]) => {
    if (!message.trim()) return
    if (needsVariableInput && !variablesValid) {
      // Open the variable panel if required fields are not filled
      setVariablesOpen(true)
      return
    }
    setShowError(false)
    
    // Convert image files to data URLs for vision
    let images: ChatImageContent[] | undefined
    if (agent.enable_vision && files && files.length > 0) {
      const imageFiles = files.filter(f => f.type.startsWith('image/'))
      if (imageFiles.length > 0) {
        images = await Promise.all(
          imageFiles.map(async (f) => ({
            type: 'image_url' as const,
            url: await fileToDataUrl(f.file),
          }))
        )
      }
    }
    
    await sendMessage(message, images)
    setInput('')
  }

  // Handle reset
  const handleReset = () => {
    reset()
    resetVariables()
    setInput('')
    setShowError(false)
    setVariablesOpen(true)
  }

  // Get error message
  const getErrorMessage = (err: ChatError) => {
    // Try to get i18n key first
    const msgKey = getErrorMsgKey(err)
    if (msgKey) {
      if (msgKey === 'quotaExceeded' && err.quotaType) {
        return tError('quotaExceeded', { type: err.quotaType })
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
    <div className="flex flex-col h-full max-h-full overflow-hidden">
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
      <ChatContainer
        messages={messages}
        isStreaming={isStreaming}
        className="flex-1 min-h-0"
        onRegenerate={regenerate}
        onSwitchVersion={switchVersion}
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
                    className="px-3 py-1.5 text-xs rounded-full border bg-background hover:bg-muted transition-colors"
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}
          </div>
        }
      />

      {/* Input Area with Variables */}
      <div className="relative pb-4 shrink-0">
        {/* Variable Panel - Collapsible above input */}
        {hasVisibleVariables && (
          <div className="mx-auto max-w-3xl px-4">
            <div className="mx-5">
              <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
                <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden max-w-90 mx-auto">
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
                        className="space-y-2"
                      />
                    </div>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            </div>
          </div>
        )}

        <ChatInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          onStop={stop}
          placeholder={needsVariableInput && !variablesValid ? tVars('fillRequired') : t('placeholder')}
          disabled={(isLoading && !isStreaming) || (needsVariableInput && !variablesValid)}
          isLoading={isLoading}
          isStreaming={isStreaming}
          allowAttachments={agent.enable_vision}
          acceptedFileTypes="image/*"
        />
      </div>
    </div>
  )
}

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Sparkles,
  Wand2,
  Check,
  Copy,
  ChevronDown,
  Loader2,
} from 'lucide-react'
import {
  ApiError,
  promptsApi,
  parsePromptSSEStream,
  type PromptGenerateContext,
  type PromptStyle,
} from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { FieldError } from '@/components/ui/field'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { toast } from 'sonner'
import {
  clearValidationError,
  getValidationSummaryEntries,
  mapValidationErrors,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'

// ============ Types ============

interface PromptGenerateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  context?: PromptGenerateContext
  onApply: (generatedPrompt: string) => void
  language?: 'zh' | 'en'
}

type ToneOption = 'professional' | 'friendly' | 'concise' | 'detailed'
type FocusOption = 'task-oriented' | 'conversational' | 'balanced'

// ============ Component ============

export function PromptGenerateDialog({
  open,
  onOpenChange,
  context,
  onApply,
  language = 'zh',
}: PromptGenerateDialogProps) {
  const t = useTranslations('promptGenerator')

  // Form state
  const [description, setDescription] = React.useState('')
  const [tone, setTone] = React.useState<ToneOption>('professional')
  const [focus, setFocus] = React.useState<FocusOption>('balanced')
  const [includeCot, setIncludeCot] = React.useState(false)
  const [includeConstraints, setIncludeConstraints] = React.useState(true)

  // Generation state
  const [isGenerating, setIsGenerating] = React.useState(false)
  const [generatedPrompt, setGeneratedPrompt] = React.useState('')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [showAdvanced, setShowAdvanced] = React.useState(false)
  const [copied, setCopied] = React.useState(false)

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['description']),
    [fieldErrors]
  )

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setDescription('')
      setGeneratedPrompt('')
      setFieldErrors({})
      setIsGenerating(false)
      setCopied(false)
    }
  }, [open])

  // Handle generate
  const handleGenerate = async () => {
    if (!description.trim()) {
      setFieldErrors({ description: t('errors.descriptionRequired') })
      return
    }

    setFieldErrors({})
    setIsGenerating(true)
    setGeneratedPrompt('')

    try {
      const style: PromptStyle = {
        tone,
        focus,
        include_cot: includeCot,
        include_constraints: includeConstraints,
      }

      const response = await promptsApi.generate({
        description: description.trim(),
        context: context || null,
        style,
        language,
      })

      let content = ''
      for await (const event of parsePromptSSEStream(response)) {
        if (event.type === 'content_delta') {
          content += event.data.delta
          setGeneratedPrompt(content)
        } else if (event.type === 'error') {
          throw new Error(event.data.msg)
        }
      }
    } catch (error) {
      const errors = mapValidationErrors(normalizeValidationErrors(error), {
        description: 'description',
      })
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      }
      console.error('Failed to generate prompt:', error)
      if (!(error instanceof ApiError && error.isValidationError())) {
        toast.error(t('errors.generateFailed'))
      }
    } finally {
      setIsGenerating(false)
    }
  }

  // Handle copy
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(generatedPrompt)
      setCopied(true)
      toast.success(t('copied'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('errors.copyFailed'))
    }
  }

  // Handle apply
  const handleApply = () => {
    onApply(generatedPrompt)
    onOpenChange(false)
  }

  // Tone options
  const toneOptions: { value: ToneOption; label: string }[] = [
    { value: 'professional', label: t('style.tone.professional') },
    { value: 'friendly', label: t('style.tone.friendly') },
    { value: 'concise', label: t('style.tone.concise') },
    { value: 'detailed', label: t('style.tone.detailed') },
  ]

  // Focus options
  const focusOptions: { value: FocusOption; label: string }[] = [
    { value: 'task-oriented', label: t('style.focus.taskOriented') },
    { value: 'conversational', label: t('style.focus.conversational') },
    { value: 'balanced', label: t('style.focus.balanced') },
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            {t('title')}
          </DialogTitle>
          <DialogDescription>
            {t('description')}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-2 px-0.5">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>{formatValidationSummaryMessage(field, message)}</FieldError>
              ))}
            </div>
          )}

          {/* Description Input */}
          <div className="space-y-2">
            <Label htmlFor="description">{t('descriptionLabel')}</Label>
            <Textarea
              id="description"
              placeholder={t('descriptionPlaceholder')}
              value={description}
              onChange={(e) => {
                setDescription(e.target.value)
                setFieldErrors((prev) => clearValidationError(prev, 'description'))
              }}
              className="min-h-24 resize-none"
              disabled={isGenerating}
              aria-invalid={!!fieldErrors.description}
            />
            <FieldError>{fieldErrors.description}</FieldError>
          </div>

          {/* Context Preview */}
          {context && (context.agent_name || context.tools?.length || context.knowledge_bases?.length || context.variables?.length) && (
            <div className="rounded-lg border bg-muted/50 p-3 space-y-2">
              <Label className="text-xs text-muted-foreground">{t('contextPreview')}</Label>
              <div className="flex flex-wrap gap-2">
                {context.agent_name && (
                  <span className="inline-flex items-center px-2 py-1 rounded-md bg-background text-xs">
                    🤖 {context.agent_name}
                  </span>
                )}
                {context.tools && context.tools.length > 0 && (
                  <span className="inline-flex items-center px-2 py-1 rounded-md bg-background text-xs">
                    🔧 {t('contextTools', { count: context.tools.length })}
                  </span>
                )}
                {context.knowledge_bases && context.knowledge_bases.length > 0 && (
                  <span className="inline-flex items-center px-2 py-1 rounded-md bg-background text-xs">
                    📚 {t('contextKnowledgeBases', { count: context.knowledge_bases.length })}
                  </span>
                )}
                {context.variables && context.variables.length > 0 && (
                  <span className="inline-flex items-center px-2 py-1 rounded-md bg-background text-xs">
                    📝 {t('contextVariables', { count: context.variables.length })}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Advanced Options */}
          <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
            <CollapsibleTrigger asChild>
              <Button variant="ghost" size="sm" className="w-full justify-between">
                {t('advancedOptions')}
                <ChevronDown className={cn('h-4 w-4 transition-transform', showAdvanced && 'rotate-180')} />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="space-y-4 pt-2">
              {/* Tone Selection */}
              <div className="space-y-2">
                <Label className="text-xs">{t('style.toneLabel')}</Label>
                <div className="flex flex-wrap gap-2">
                  {toneOptions.map((option) => (
                    <Button
                      key={option.value}
                      variant={tone === option.value ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setTone(option.value)}
                      disabled={isGenerating}
                      className="text-xs h-7"
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Focus Selection */}
              <div className="space-y-2">
                <Label className="text-xs">{t('style.focusLabel')}</Label>
                <div className="flex flex-wrap gap-2">
                  {focusOptions.map((option) => (
                    <Button
                      key={option.value}
                      variant={focus === option.value ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFocus(option.value)}
                      disabled={isGenerating}
                      className="text-xs h-7"
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </div>

              {/* Toggle Options */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label className="text-xs">{t('style.includeCot')}</Label>
                    <p className="text-xs text-muted-foreground">{t('style.includeCotDesc')}</p>
                  </div>
                  <Switch
                    checked={includeCot}
                    onCheckedChange={setIncludeCot}
                    disabled={isGenerating}
                  />
                </div>
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <Label className="text-xs">{t('style.includeConstraints')}</Label>
                    <p className="text-xs text-muted-foreground">{t('style.includeConstraintsDesc')}</p>
                  </div>
                  <Switch
                    checked={includeConstraints}
                    onCheckedChange={setIncludeConstraints}
                    disabled={isGenerating}
                  />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>

          {/* Generated Result */}
          {(generatedPrompt || isGenerating) && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>{t('resultLabel')}</Label>
                {generatedPrompt && !isGenerating && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleCopy}
                    className="h-7 text-xs gap-1"
                  >
                    {copied ? (
                      <>
                        <Check className="h-3 w-3" />
                        {t('copied')}
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" />
                        {t('copy')}
                      </>
                    )}
                  </Button>
                )}
              </div>
              <div className="relative rounded-lg border bg-muted/30 p-3 min-h-32 max-h-64 overflow-y-auto">
                {isGenerating && !generatedPrompt && (
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {t('generating')}
                  </div>
                )}
                <pre className="whitespace-pre-wrap text-sm font-mono">
                  {generatedPrompt}
                  {isGenerating && <span className="inline-block w-2 h-4 bg-primary animate-pulse ml-0.5" />}
                </pre>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          {generatedPrompt && !isGenerating ? (
            <>
              <Button
                variant="outline"
                onClick={handleGenerate}
                disabled={isGenerating || !description.trim()}
              >
                <Wand2 className="h-4 w-4 mr-2" />
                {t('regenerate')}
              </Button>
              <Button onClick={handleApply}>
                <Check className="h-4 w-4 mr-2" />
                {t('apply')}
              </Button>
            </>
          ) : (
            <Button
              onClick={handleGenerate}
              disabled={isGenerating || !description.trim()}
            >
              {isGenerating ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  {t('generating')}
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4 mr-2" />
                  {t('generate')}
                </>
              )}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Bot, ChevronDown, MessageSquare, Wrench, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTeam } from '@/contexts/team-context'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { ImageUpload } from '@/components/ui/image-upload'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ScrollArea } from '@/components/ui/scroll-area'
import { teamModelsApi, type Agent, type AgentVisibility, type TeamModel } from '@/lib/api'

interface AgentSettingsDrawerProps {
  agent: Agent
  open: boolean
  onOpenChange: (open: boolean) => void
  name: string
  onNameChange: (name: string) => void
  description: string
  onDescriptionChange: (description: string) => void
  icon: string
  onIconChange: (icon: string) => void
  openingMessage: string
  onOpeningMessageChange: (message: string) => void
  suggestedQuestions: string[]
  onSuggestedQuestionsChange: (questions: string[]) => void
  visibility: AgentVisibility
  onVisibilityChange: (visibility: AgentVisibility) => void
  // Model settings
  modelId: string | null
  onModelChange: (modelId: string | null) => void
  maxIterations: number
  onMaxIterationsChange: (value: number) => void
  // Tool-related
  hasToolsEnabled: boolean
}

interface SettingsSectionProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}

function SettingsSection({ title, children, defaultOpen = true }: SettingsSectionProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <CollapsibleTrigger className="flex items-center justify-between w-full py-2 text-sm font-medium hover:text-foreground text-muted-foreground">
        {title}
        <ChevronDown
          className={cn(
            'h-4 w-4 transition-transform',
            isOpen && 'rotate-180'
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="space-y-4 pt-2 pb-4">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}

export function AgentSettingsDrawer({
  agent,
  open,
  onOpenChange,
  name,
  onNameChange,
  description,
  onDescriptionChange,
  icon,
  onIconChange,
  openingMessage,
  onOpeningMessageChange,
  suggestedQuestions,
  onSuggestedQuestionsChange,
  visibility,
  onVisibilityChange,
  modelId,
  onModelChange,
  maxIterations,
  onMaxIterationsChange,
  hasToolsEnabled,
}: AgentSettingsDrawerProps) {
  const t = useTranslations('agents')
  const ts = useTranslations('agents.settings')
  const { currentTeam } = useTeam()

  const [teamModels, setTeamModels] = React.useState<TeamModel[]>([])
  const [isLoadingModels, setIsLoadingModels] = React.useState(false)

  // Load models
  React.useEffect(() => {
    const loadModels = async () => {
      if (!currentTeam || !open) return
      setIsLoadingModels(true)
      try {
        const models = await teamModelsApi.getTeamModels(currentTeam.id, 'chat')
        setTeamModels(models.filter((m) => m.is_enabled))
      } catch {
        // Ignore errors
      } finally {
        setIsLoadingModels(false)
      }
    }
    loadModels()
  }, [currentTeam, open])

  // Get selected model info
  const selectedModel = React.useMemo(() => {
    if (!modelId) return agent.model
    const tm = teamModels.find((m) => m.id === modelId)
    return tm?.model || agent.model
  }, [modelId, teamModels, agent.model])

  const selectedTeamModel = React.useMemo(() => {
    if (!modelId) return null
    return teamModels.find((m) => m.id === modelId)
  }, [modelId, teamModels])

  // Check if model supports function calling
  const modelSupportsFunctionCall = React.useMemo(() => {
    // If we don't have full model info, assume it doesn't support
    // In a real implementation, we'd check model.capabilities.supports_function_call
    return true // Default to true for now
  }, [selectedModel])

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-100 sm:w-135 p-0 flex flex-col h-full max-h-screen">
        <SheetHeader className="px-6 pt-6 pb-4 shrink-0">
          <SheetTitle>{ts('title')}</SheetTitle>
          <SheetDescription>{ts('description')}</SheetDescription>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0">
          <div className="px-6 space-y-1 pb-6">
            {/* Basic Info Section */}
            <SettingsSection title={ts('basicInfo')}>
              {/* Icon */}
              <div className="space-y-1.5">
                <Label className="text-xs">{ts('icon')}</Label>
                <ImageUpload
                  value={icon}
                  onChange={onIconChange}
                  previewSize="lg"
                  category="icons"
                  placeholder={<Bot className="h-8 w-8 text-muted-foreground/50" />}
                />
              </div>

              {/* Name */}
              <div className="space-y-1.5">
                <Label htmlFor="name" className="text-xs">{t('name')}</Label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => onNameChange(e.target.value)}
                  placeholder={t('namePlaceholder')}
                />
              </div>

              {/* Description */}
              <div className="space-y-1.5">
                <Label htmlFor="description" className="text-xs">{t('descriptionLabel')}</Label>
                <Textarea
                  id="description"
                  value={description}
                  onChange={(e) => onDescriptionChange(e.target.value)}
                  placeholder={t('descriptionPlaceholder')}
                  rows={2}
                  className="resize-none"
                />
              </div>

              {/* Visibility */}
              <div className="space-y-1.5">
                <Label htmlFor="visibility" className="text-xs">{t('visibility')}</Label>
                <Select value={visibility} onValueChange={(v) => v && onVisibilityChange(v as AgentVisibility)}>
                  <SelectTrigger id="visibility">
                    <SelectValue>
                      {visibility === 'private' ? t('visibilityPrivate') : t('visibilityTeam')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent side="bottom" alignItemWithTrigger={false}>
                    <SelectItem value="private">{t('visibilityPrivate')}</SelectItem>
                    <SelectItem value="team">{t('visibilityTeam')}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </SettingsSection>

            {/* Model Settings Section */}
            <SettingsSection title={ts('modelConfig')}>
              {/* Model Selector */}
              <div className="space-y-1.5">
                <Label className="text-xs">{t('model')}</Label>
                <DropdownMenu>
                  <DropdownMenuTrigger className="w-full inline-flex items-center justify-between gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground h-9 px-3">
                    {selectedModel ? (
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-5 h-5 rounded bg-green-100 text-green-700 flex items-center justify-center shrink-0">
                          <MessageSquare className="h-3 w-3" />
                        </div>
                        <span className="truncate">{selectedModel.name}</span>
                      </div>
                    ) : (
                      <span className="text-muted-foreground">{t('selectModel')}</span>
                    )}
                    <ChevronDown className="h-4 w-4 opacity-50 shrink-0" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="w-[calc(var(--radix-dropdown-menu-trigger-width))]">
                    {teamModels.length > 0 ? (
                      teamModels.map((tm) => (
                        <DropdownMenuItem
                          key={tm.id}
                          onClick={() => onModelChange(tm.id)}
                          className="flex items-center gap-2"
                        >
                          <div className="w-5 h-5 rounded bg-green-100 text-green-700 flex items-center justify-center">
                            <MessageSquare className="h-3 w-3" />
                          </div>
                          <span className="flex-1 truncate">{tm.model.name}</span>
                          {tm.id === modelId && (
                            <Badge variant="outline" className="text-[10px]">
                              {ts('current')}
                            </Badge>
                          )}
                        </DropdownMenuItem>
                      ))
                    ) : (
                      <div className="px-2 py-4 text-center text-sm text-muted-foreground">
                        {t('noModels')}
                      </div>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>

              {/* Tool Call Warning */}
              {hasToolsEnabled && !modelSupportsFunctionCall && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-amber-50 border border-amber-200 text-amber-800">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <div className="text-xs">
                    <p className="font-medium">{ts('toolCallWarningTitle')}</p>
                    <p className="text-amber-700 mt-0.5">{ts('toolCallWarningDescription')}</p>
                  </div>
                </div>
              )}

              {/* Model params hint */}
              <p className="text-xs text-muted-foreground">
                {ts('modelParamsHint')}
              </p>

              {/* Max Iterations */}
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Label className="text-xs">{ts('maxIterationsLabel')}</Label>
                  <Tooltip>
                    <TooltipTrigger>
                      <Wrench className="h-3 w-3 text-muted-foreground" />
                    </TooltipTrigger>
                    <TooltipContent side="right">
                      <p className="max-w-xs text-xs">{ts('maxIterationsTooltip')}</p>
                    </TooltipContent>
                  </Tooltip>
                </div>
                <Input
                  type="number"
                  value={maxIterations}
                  onChange={(e) => {
                    const val = Number(e.target.value)
                    if (val >= 1 && val <= 20) {
                      onMaxIterationsChange(val)
                    }
                  }}
                  min={1}
                  max={20}
                />
                <p className="text-xs text-muted-foreground">
                  {ts('maxIterationsHint')}
                </p>
              </div>
            </SettingsSection>

            {/* Conversation Settings Section */}
            <SettingsSection title={ts('conversationConfig')} defaultOpen={false}>
              {/* Opening Message */}
              <div className="space-y-1.5">
                <Label htmlFor="openingMessage" className="text-xs">{t('openingMessage')}</Label>
                <Textarea
                  id="openingMessage"
                  value={openingMessage}
                  onChange={(e) => onOpeningMessageChange(e.target.value)}
                  placeholder={t('openingMessagePlaceholder')}
                  rows={2}
                  className="resize-none"
                />
              </div>

              {/* Suggested Questions */}
              <div className="space-y-1.5">
                <Label htmlFor="suggestedQuestions" className="text-xs">{t('suggestedQuestions')}</Label>
                <Textarea
                  id="suggestedQuestions"
                  value={suggestedQuestions.join('\n')}
                  onChange={(e) =>
                    onSuggestedQuestionsChange(
                      e.target.value.split('\n').filter((q) => q.trim())
                    )
                  }
                  placeholder={ts('suggestedQuestionsPlaceholder')}
                  rows={3}
                  className="resize-none"
                />
                <p className="text-xs text-muted-foreground">
                  {t('suggestedQuestionsHint')}
                </p>
              </div>
            </SettingsSection>
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}


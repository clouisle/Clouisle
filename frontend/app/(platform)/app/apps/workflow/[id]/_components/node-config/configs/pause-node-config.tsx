'use client'

import * as React from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Button } from '@/components/ui/button'
import {
  Combobox,
  ComboboxChip,
  ComboboxChips,
  ComboboxChipsInput,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxItem,
  ComboboxList,
  useComboboxAnchor,
} from '@/components/ui/combobox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useTeam } from '@/contexts/team-context'
import { teamsApi } from '@/lib/api'
import type { TeamMember } from '@/lib/api/teams'
import { PromptTextarea } from '../components/prompt-textarea'
import { ParameterEditDialog } from '../dialogs/parameter-edit-dialog'
import { parameterTypeConfig } from '../constants'
import type { AvailableVariable, Parameter } from '../types'

export interface PauseNodeConfig {
  mode: 'variables' | 'approval'
  title: string
  inputVariables: Parameter[]
  approverIds: string[]
  description?: string
  // Approval strategy: false = any one approver resolves the request,
  // true = every approver must submit their decision before the run resumes.
  requireAllApprovals?: boolean
}

export const defaultPauseNodeConfig: PauseNodeConfig = {
  mode: 'variables',
  title: '',
  inputVariables: [],
  approverIds: [],
  requireAllApprovals: false,
}

interface PauseNodeConfigProps {
  config: PauseNodeConfig
  onConfigChange: (config: PauseNodeConfig) => void
  getAvailableVariables?: (filterType?: 'iterable' | 'all') => AvailableVariable[]
}

export function PauseNodeConfig({ config, onConfigChange, getAvailableVariables }: PauseNodeConfigProps) {
  const t = useTranslations('workflow')
  const { currentTeam } = useTeam()
  const [members, setMembers] = React.useState<TeamMember[]>([])
  const [isLoadingMembers, setIsLoadingMembers] = React.useState(false)
  const safeConfig = { ...defaultPauseNodeConfig, ...config }

  React.useEffect(() => {
    if (!currentTeam) return
    let cancelled = false
    setIsLoadingMembers(true)
    teamsApi
      .getTeam(currentTeam.id)
      .then((team) => {
        if (!cancelled) setMembers(team.members || [])
      })
      .catch(() => {
        if (!cancelled) setMembers([])
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMembers(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentTeam])

  const [paramDialogOpen, setParamDialogOpen] = React.useState(false)
  const [editingParam, setEditingParam] = React.useState<Parameter | null>(null)

  const memberOptions = React.useMemo(
    () => members.map((member) => ({
      value: member.user_id,
      label: member.username,
      email: member.email,
    })),
    [members],
  )
  const selectedApprovers = React.useMemo(
    () => memberOptions.filter((option) => safeConfig.approverIds.includes(option.value)),
    [memberOptions, safeConfig.approverIds],
  )
  const approverAnchorRef = useComboboxAnchor()

  const content = (
    <div className="space-y-5">
      <div className="space-y-2">
        <Label className="text-xs font-medium">{t('configPause.mode')}</Label>
        <div className="grid grid-cols-2 gap-2">
          {(['variables', 'approval'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                safeConfig.mode === mode
                  ? 'border-amber-500 bg-amber-500/10 text-foreground'
                  : 'border-input hover:bg-muted/50'
              }`}
              onClick={() => onConfigChange({ ...safeConfig, mode })}
            >
              <span className="block font-medium">{t(`configPause.${mode}.title`)}</span>
              <span className="mt-0.5 block text-[11px] text-muted-foreground">
                {t(`configPause.${mode}.description`)}
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium" htmlFor="pause-title">
          {t('configPause.title')}
        </Label>
        <Input
          id="pause-title"
          value={safeConfig.title}
          placeholder={t('configPause.titlePlaceholder')}
          onChange={(event) => onConfigChange({ ...safeConfig, title: event.target.value })}
          className="h-9 text-xs"
        />
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-medium" htmlFor="pause-description">
          {safeConfig.mode === 'approval'
            ? t('configPause.approvalDescription')
            : t('configPause.variablesDescription')}
        </Label>
        <PromptTextarea
          value={safeConfig.description ?? ''}
          onChange={(value) => onConfigChange({ ...safeConfig, description: value })}
          variables={getAvailableVariables?.('all') || []}
          placeholder={safeConfig.mode === 'approval'
            ? t('configPause.approvalDescriptionPlaceholder')
            : t('configPause.variablesDescriptionPlaceholder')}
          minHeight="min-h-20"
        />
        <p className="text-[11px] text-muted-foreground">
          {safeConfig.mode === 'approval'
            ? t('configPause.approvalDescriptionHint')
            : t('configPause.variablesDescriptionHint')}
        </p>
      </div>

      {safeConfig.mode === 'approval' && (
        <div className="space-y-2">
          <Label className="text-xs font-medium">{t('configPause.approvalStrategy')}</Label>
          <div className="grid grid-cols-2 gap-2">
            {([false, true] as const).map((requireAll) => (
              <button
                key={String(requireAll)}
                type="button"
                className={`rounded-lg border px-3 py-2 text-left text-xs transition-colors ${
                  (safeConfig.requireAllApprovals ?? false) === requireAll
                    ? 'border-amber-500 bg-amber-500/10 text-foreground'
                    : 'border-input hover:bg-muted/50'
                }`}
                onClick={() => onConfigChange({ ...safeConfig, requireAllApprovals: requireAll })}
              >
                <span className="block font-medium">
                  {t(requireAll ? 'configPause.approvalAll' : 'configPause.approvalAnyOne')}
                </span>
                <span className="mt-0.5 block text-[11px] text-muted-foreground">
                  {t(requireAll ? 'configPause.approvalAllDescription' : 'configPause.approvalAnyOneDescription')}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <div>
          <Label className="text-xs font-medium">{t('configPause.approvers')}</Label>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{t('configPause.approversHint')}</p>
        </div>
        {isLoadingMembers ? (
          <p className="text-xs text-muted-foreground">{t('configCommon.loading')}</p>
        ) : members.length === 0 ? (
          <p className="rounded-md border border-dashed px-3 py-3 text-center text-xs text-muted-foreground">
            {t('configPause.noApprovers')}
          </p>
        ) : (
          <Combobox
            multiple
            items={memberOptions}
            value={selectedApprovers}
            onValueChange={(next) => onConfigChange({
              ...safeConfig,
              approverIds: (next as typeof memberOptions).map((option) => option.value),
            })}
          >
            <ComboboxChips ref={approverAnchorRef} className="w-full">
              {selectedApprovers.map((option) => (
                <ComboboxChip key={option.value}>{option.label}</ComboboxChip>
              ))}
              <ComboboxChipsInput placeholder={t('configPause.searchApprovers')} className="text-xs" />
            </ComboboxChips>
            <ComboboxContent anchor={approverAnchorRef}>
              <ComboboxEmpty>{t('configPause.noMatchingApprovers')}</ComboboxEmpty>
              <ComboboxList>
                {(option) => (
                  <ComboboxItem key={option.value} value={option} className="text-xs">
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-medium">{option.label}</span>
                      <span className="truncate text-[10px] text-muted-foreground">{option.email}</span>
                    </span>
                  </ComboboxItem>
                )}
              </ComboboxList>
            </ComboboxContent>
          </Combobox>
        )}
      </div>

      {safeConfig.mode === 'variables' && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div>
              <Label className="text-xs font-medium">{t('configPause.requestedVariables')}</Label>
              <p className="mt-0.5 text-[11px] text-muted-foreground">{t('configPause.variablesHint')}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => {
                setEditingParam(null)
                setParamDialogOpen(true)
              }}
            >
              <Plus className="mr-1 h-3 w-3" />
              {t('configCommon.add')}
            </Button>
          </div>

          {safeConfig.inputVariables.length === 0 ? (
            <p className="rounded-md border border-dashed px-3 py-4 text-center text-xs text-muted-foreground">
              {t('configPause.noVariables')}
            </p>
          ) : (
            <div className="space-y-1">
              {safeConfig.inputVariables.map((variable) => {
                const typeConfig = parameterTypeConfig[variable.type] || parameterTypeConfig.text
                const TypeIcon = typeConfig.icon
                return (
                  <div
                    key={variable.id}
                    className="group flex cursor-pointer items-center justify-between rounded-md px-2 py-1.5 transition-colors hover:bg-muted/50"
                    onClick={() => {
                      setEditingParam(variable)
                      setParamDialogOpen(true)
                    }}
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-2">
                      <TypeIcon className="h-4 w-4 shrink-0 text-primary/70" />
                      <span className="min-w-0 truncate text-xs font-medium">
                        {variable.name || t('configCommon.unnamed')}
                      </span>
                      {variable.label && (
                        <span className="truncate text-[11px] text-muted-foreground">{variable.label}</span>
                      )}
                    </div>
                    <div className="relative flex shrink-0 items-center gap-1">
                      {variable.required && (
                        <span className="text-xs text-muted-foreground group-hover:opacity-0">{t('configCommon.required')}</span>
                      )}
                      <span className="rounded border border-border px-1.5 py-0.5 text-xs text-muted-foreground group-hover:opacity-0">
                        {typeConfig.valueType}
                      </span>
                      <div className="absolute right-0 top-1/2 flex -translate-y-1/2 items-center gap-0.5 opacity-0 group-hover:opacity-100">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5"
                          aria-label={t('configPause.editVariable', { name: variable.name })}
                          onClick={(event) => {
                            event.stopPropagation()
                            setEditingParam(variable)
                            setParamDialogOpen(true)
                          }}
                        >
                          <Pencil className="h-3 w-3" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-5 w-5 text-muted-foreground hover:text-destructive"
                          aria-label={t('configCommon.remove')}
                          onClick={(event) => {
                            event.stopPropagation()
                            onConfigChange({
                              ...safeConfig,
                              inputVariables: safeConfig.inputVariables.filter((item) => item.id !== variable.id),
                            })
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )

  return (
    <>
      {content}
      <ParameterEditDialog
        open={paramDialogOpen}
        onOpenChange={setParamDialogOpen}
        editingParam={editingParam}
        existingParams={safeConfig.inputVariables}
        onSave={(param) => {
          onConfigChange({
            ...safeConfig,
            inputVariables: editingParam
              ? safeConfig.inputVariables.map((item) => (item.id === param.id ? param : item))
              : [...safeConfig.inputVariables, param],
          })
        }}
      />
    </>
  )
}

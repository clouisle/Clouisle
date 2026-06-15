'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { notificationsApi } from '@/lib/api/admin/notifications'
import type { NotificationChannel, NotificationLevel, NotificationScope } from '@/lib/api/notifications'
import { usersApi } from '@/lib/api/admin/users'
import { teamsApi } from '@/lib/api/admin/teams'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { MarkdownEditor } from '@/components/ui/markdown-editor'
import { FieldError } from '@/components/ui/field'
import {
  clearValidationError,
  getValidationSummaryEntries,
  normalizeValidationErrors,
  formatValidationSummaryMessage
} from '@/lib/validation'
import { toast } from 'sonner'
import { useDebounce } from '@/hooks/use-debounce'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
} from '@/components/ui/combobox'

const LEVELS: NotificationLevel[] = ['low', 'medium', 'high']
const SCOPES: NotificationScope[] = ['global', 'team', 'user']

interface TeamOption {
  id: string
  name: string
}

interface CreateNotificationDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function CreateNotificationDialog({ open, onOpenChange, onSuccess }: CreateNotificationDialogProps) {
  const t = useTranslations('notifications')
  const tCommon = useTranslations('common')

  const [teams, setTeams] = React.useState<TeamOption[]>([])
  const [formScope, setFormScope] = React.useState<NotificationScope>('global')
  const [formTeamId, setFormTeamId] = React.useState<string | null>(null)
  const [formUserId, setFormUserId] = React.useState('')
  const [userOptions, setUserOptions] = React.useState<Array<{ value: string; label: string }>>([])
  const [userSearch, setUserSearch] = React.useState('')
  const debouncedUserSearch = useDebounce(userSearch.trim(), 300)
  const [selectedUserOption, setSelectedUserOption] = React.useState<{ value: string; label: string } | null>(null)
  const [formType, setFormType] = React.useState('system_announcement')
  const [formTitle, setFormTitle] = React.useState('')
  const [formContent, setFormContent] = React.useState('')
  const [formLevel, setFormLevel] = React.useState<NotificationLevel>('medium')
  const [formLink, setFormLink] = React.useState('')
  const [formExpiresAt, setFormExpiresAt] = React.useState('')
  const [notifyChannels, setNotifyChannels] = React.useState<NotificationChannel[]>([])
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = React.useState(false)

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['scope', 'team_id', 'user_id', 'title', 'content', 'type', 'level', 'link_url', 'expires_at', 'notify_channels']),
    [fieldErrors]
  )

  const fetchTeams = React.useCallback(async () => {
    try {
      const result = await teamsApi.getTeams(1, 200)
      setTeams(result.items.map((team) => ({ id: team.id, name: team.name })))
    } catch (error) {
      console.error('Failed to fetch teams:', error)
    }
  }, [])

  React.useEffect(() => {
    if (open) {
      fetchTeams()
    }
  }, [open, fetchTeams])

  React.useEffect(() => {
    if (formScope !== 'user') {
      setSelectedUserOption(null)
      setFormUserId('')
      setUserSearch('')
      setFieldErrors((prev) => clearValidationError(clearValidationError(prev, 'user_id'), 'user_ids'))
    }
    if (formScope !== 'team') {
      setFormTeamId(null)
      setFieldErrors((prev) => clearValidationError(prev, 'team_id'))
    }
  }, [formScope])

  React.useEffect(() => {
    const fetchUsers = async () => {
      try {
        const data = await usersApi.getUsers({
          page: 1,
          pageSize: 20,
          search: debouncedUserSearch || undefined,
        })
        setUserOptions(
          data.items.map((user) => ({
            value: user.id,
            label: user.username,
          }))
        )
      } catch (error) {
        console.error('Failed to fetch users:', error)
      }
    }
    if (formScope === 'user') {
      fetchUsers()
    }
  }, [debouncedUserSearch, formScope])

  const handleCreate = async () => {
    setFieldErrors({})

    if (!formTitle.trim()) {
      setFieldErrors({ title: tCommon('requiredFields') })
      return
    }

    if (!formContent.trim()) {
      setFieldErrors({ content: tCommon('requiredFields') })
      return
    }

    if (formScope === 'team' && !formTeamId) {
      setFieldErrors({ team_id: tCommon('requiredFields') })
      return
    }

    if (formScope === 'user' && !formUserId) {
      setFieldErrors({ user_id: tCommon('requiredFields') })
      return
    }

    try {
      setIsSubmitting(true)
      const payload = {
        scope: formScope,
        team_id: formScope === 'team' ? formTeamId : null,
        user_id: formScope === 'user' ? formUserId || null : null,
        type: formType,
        title: formTitle,
        content: formContent,
        level: formLevel,
        link_url: formLink || null,
        expires_at: formExpiresAt ? new Date(formExpiresAt).toISOString() : null,
        notify_channels: notifyChannels,
      }
      await notificationsApi.adminCreate(payload, { silent: true })
      toast.success(t('toast.created'))

      setFormScope('global')
      setFormTeamId(null)
      setFormUserId('')
      setSelectedUserOption(null)
      setFormType('system_announcement')
      setFormTitle('')
      setFormContent('')
      setFormLevel('medium')
      setFormLink('')
      setFormExpiresAt('')
      setNotifyChannels([])
      setFieldErrors({})

      onSuccess()
      onOpenChange(false)
    } catch (error) {
      const errors = normalizeValidationErrors(error)
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors)
      } else {
        console.error('Failed to create notification:', error)
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!w-[70vw] !max-w-none">
        <DialogHeader>
          <DialogTitle>{t('admin.create')}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-4">
          {summaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {summaryEntries.map(([field, message]) => (
                <FieldError key={field}>
                  {formatValidationSummaryMessage(field, message)}
                </FieldError>
              ))}
            </div>
          )}

          <div className="flex items-end gap-4">
            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createScope')}</label>
              <Select value={formScope} onValueChange={(value) => {
                setFormScope(value as NotificationScope)
                setFieldErrors((prev) => clearValidationError(prev, 'scope'))
              }}>
                <SelectTrigger aria-invalid={!!fieldErrors.scope}>
                  <span>{t(`scopeOptions.${formScope}`)}</span>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {SCOPES.map((scope) => (
                    <SelectItem key={scope} value={scope}>
                      {t(`scopeOptions.${scope}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError>{fieldErrors.scope}</FieldError>
            </div>

            {formScope === 'team' && (
              <div className="grid gap-2 flex-1">
                <label className="text-sm font-medium">{t('admin.createTeam')}</label>
                <Select value={formTeamId || ''} onValueChange={(value) => {
                  setFormTeamId(value)
                  setFieldErrors((prev) => clearValidationError(prev, 'team_id'))
                }}>
                  <SelectTrigger aria-invalid={!!fieldErrors.team_id}>
                    <span>
                      {formTeamId ? (teams.find((team) => team.id === formTeamId)?.name || formTeamId) : t('admin.selectTeam')}
                    </span>
                  </SelectTrigger>
                  <SelectContent alignItemWithTrigger={false}>
                    {teams.map((team) => (
                      <SelectItem key={team.id} value={team.id}>
                        {team.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError>{fieldErrors.team_id}</FieldError>
              </div>
            )}

            {formScope === 'user' && (
              <div className="grid gap-2 flex-1">
                <label className="text-sm font-medium">{t('admin.createUser')}</label>
                <Combobox
                  items={userOptions}
                  value={selectedUserOption}
                  onValueChange={(value) => {
                    const option = (value as { value: string; label: string } | null) || null
                    setSelectedUserOption(option)
                    setFormUserId(option?.value || '')
                    setFieldErrors((prev) => clearValidationError(prev, 'user_id'))
                  }}
                  onInputValueChange={(value) => setUserSearch(value)}
                >
                  <ComboboxTrigger className="rounded-md border px-2.5 py-2 text-sm text-left flex items-center justify-between">
                    <span className="truncate">
                      {selectedUserOption?.label || t('admin.createUser')}
                    </span>
                  </ComboboxTrigger>
                  <ComboboxContent>
                    <div className="p-2">
                      <ComboboxInput
                        showTrigger={false}
                        showClear
                        placeholder={t('admin.createUser')}
                        className="w-full"
                      />
                    </div>
                    <ComboboxEmpty>{tCommon('noResults')}</ComboboxEmpty>
                    <ComboboxList>
                      {(item) => (
                        <ComboboxItem key={item.value} value={item}>
                          {item.label}
                        </ComboboxItem>
                      )}
                    </ComboboxList>
                  </ComboboxContent>
                </Combobox>
                <FieldError>{fieldErrors.user_id || fieldErrors.user_ids}</FieldError>
              </div>
            )}

            <div className="h-9 w-px bg-border" />

            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createType')}</label>
              <Select value={formType} onValueChange={(value) => {
                if (!value) return
                setFormType(value)
                setFieldErrors((prev) => clearValidationError(prev, 'type'))
              }}>
                <SelectTrigger aria-invalid={!!fieldErrors.type}>
                  <span>
                    {t(`admin.typeOptions.${formType}`)}
                  </span>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {[
                    'system_announcement',
                    'team_invite',
                    'team_member_added',
                    'team_member_removed',
                    'team_role_changed',
                    'team_ownership_transferred',
                    'team_model_granted',
                    'team_model_revoked',
                    'user_activated',
                    'user_deactivated',
                    'user_password_reset',
                    'user_pending_approval',
                    'user_mention',
                    'user_assigned',
                    'kb_doc_indexed',
                    'kb_doc_failed',
                    'workflow_run_success',
                    'workflow_run_failed',
                    'agent_published',
                    'agent_unpublished',
                    'apikey_expiring',
                    'apikey_expired',
                    'security_login_anomaly',
                    'security_account_locked',
                    'security_password_changed',
                    'password_expiring',
                    'password_expired',
                    'password_force_change',
                    'model_test_failed',
                    'quota_near_limit',
                    'quota_exceeded',
                  ].map((type) => (
                    <SelectItem key={type} value={type}>
                      {t(`admin.typeOptions.${type}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError>{fieldErrors.type}</FieldError>
            </div>

            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createLevel')}</label>
              <Select value={formLevel} onValueChange={(value) => {
                setFormLevel(value as NotificationLevel)
                setFieldErrors((prev) => clearValidationError(prev, 'level'))
              }}>
                <SelectTrigger aria-invalid={!!fieldErrors.level}>
                  <span>{t(`levelOptions.${formLevel}`)}</span>
                </SelectTrigger>
                <SelectContent alignItemWithTrigger={false}>
                  {LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {t(`levelOptions.${level}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError>{fieldErrors.level}</FieldError>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createTitle')}</label>
              <Input
                value={formTitle}
                onChange={(e) => {
                  setFormTitle(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'title'))
                }}
                disabled={isSubmitting}
                aria-invalid={!!fieldErrors.title}
              />
              <FieldError>{fieldErrors.title}</FieldError>
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createLink')}</label>
              <Input
                value={formLink}
                onChange={(e) => {
                  setFormLink(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'link_url'))
                }}
                placeholder="https://"
                disabled={isSubmitting}
                aria-invalid={!!fieldErrors.link_url}
              />
              <FieldError>{fieldErrors.link_url}</FieldError>
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createExpiresAt')}</label>
              <Input
                type="datetime-local"
                value={formExpiresAt}
                onChange={(e) => {
                  setFormExpiresAt(e.target.value)
                  setFieldErrors((prev) => clearValidationError(prev, 'expires_at'))
                }}
                disabled={isSubmitting}
                aria-invalid={!!fieldErrors.expires_at}
              />
              <FieldError>{fieldErrors.expires_at}</FieldError>
            </div>
          </div>

          <div className="grid gap-2">
            <label className="text-sm font-medium">{t('admin.createContent')}</label>
            <MarkdownEditor
              value={formContent}
              onChange={(value) => {
                setFormContent(value)
                setFieldErrors((prev) => clearValidationError(prev, 'content'))
              }}
              height={200}
              preview="live"
            />
            <FieldError>{fieldErrors.content}</FieldError>
            <p className="text-xs text-muted-foreground">{t('admin.contentMarkdownHint')}</p>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="grid gap-2">
                <label className="text-sm font-medium">{t('admin.notifyChannels')}</label>
                <FieldError>{fieldErrors.notify_channels}</FieldError>
              </div>
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="channel-email"
                    checked={notifyChannels.includes('email')}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setNotifyChannels([...notifyChannels, 'email'])
                      } else {
                        setNotifyChannels(notifyChannels.filter(c => c !== 'email'))
                      }
                      setFieldErrors((prev) => clearValidationError(prev, 'notify_channels'))
                    }}
                  />
                  <label
                    htmlFor="channel-email"
                    className="text-sm leading-none cursor-pointer"
                  >
                    {t('admin.channelEmail')}
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <Checkbox
                    id="channel-dingtalk"
                    checked={notifyChannels.includes('dingtalk')}
                    onCheckedChange={(checked) => {
                      if (checked) {
                        setNotifyChannels([...notifyChannels, 'dingtalk'])
                      } else {
                        setNotifyChannels(notifyChannels.filter(c => c !== 'dingtalk'))
                      }
                      setFieldErrors((prev) => clearValidationError(prev, 'notify_channels'))
                    }}
                  />
                  <label
                    htmlFor="channel-dingtalk"
                    className="text-sm leading-none cursor-pointer"
                  >
                    {t('admin.channelDingtalk')}
                  </label>
                </div>
              </div>
            </div>

            <Button onClick={handleCreate} disabled={isSubmitting}>
              {t('admin.submit')}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

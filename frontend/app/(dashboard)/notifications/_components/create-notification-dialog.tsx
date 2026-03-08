'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { notificationsApi } from '@/lib/api/admin/notifications'
import type { NotificationChannel, NotificationLevel, NotificationScope } from '@/lib/api/notifications'
import { usersApi } from '@/lib/api/admin/users'
import { teamsApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { MarkdownEditor } from '@/components/ui/markdown-editor'
import { toast } from 'sonner'
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
  const [debouncedUserSearch, setDebouncedUserSearch] = React.useState('')
  const [selectedUserOption, setSelectedUserOption] = React.useState<{ value: string; label: string } | null>(null)
  const [formType, setFormType] = React.useState('system_announcement')
  const [formTitle, setFormTitle] = React.useState('')
  const [formContent, setFormContent] = React.useState('')
  const [formLevel, setFormLevel] = React.useState<NotificationLevel>('medium')
  const [formLink, setFormLink] = React.useState('')
  const [formExpiresAt, setFormExpiresAt] = React.useState('')
  const [notifyChannels, setNotifyChannels] = React.useState<NotificationChannel[]>([])
  const [isSubmitting, setIsSubmitting] = React.useState(false)

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
      setDebouncedUserSearch('')
    }
  }, [formScope])

  React.useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedUserSearch(userSearch.trim())
    }, 300)
    return () => window.clearTimeout(timer)
  }, [userSearch])

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
    if (!formTitle.trim() || !formContent.trim()) {
      toast.error(tCommon('requiredFields'))
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
      await notificationsApi.adminCreate(payload)
      toast.success(t('toast.created'))

      // Reset form
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

      onSuccess()
    } catch (error) {
      console.error('Failed to create notification:', error)
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
          <div className="flex items-end gap-4">
            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createScope')}</label>
              <Select value={formScope} onValueChange={(value) => setFormScope(value as NotificationScope)}>
                <SelectTrigger>
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
            </div>

            {formScope === 'team' && (
              <div className="grid gap-2 flex-1">
                <label className="text-sm font-medium">{t('admin.createTeam')}</label>
                <Select value={formTeamId || ''} onValueChange={setFormTeamId}>
                  <SelectTrigger>
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
              </div>
            )}

            <div className="h-9 w-px bg-border" />

            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createType')}</label>
              <Select value={formType} onValueChange={(value) => value && setFormType(value)}>
                <SelectTrigger>
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
            </div>

            <div className="grid gap-2 flex-1">
              <label className="text-sm font-medium">{t('admin.createLevel')}</label>
              <Select value={formLevel} onValueChange={(value) => setFormLevel(value as NotificationLevel)}>
                <SelectTrigger>
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
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createTitle')}</label>
              <Input value={formTitle} onChange={(e) => setFormTitle(e.target.value)} />
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createLink')}</label>
              <Input value={formLink} onChange={(e) => setFormLink(e.target.value)} placeholder="https://" />
            </div>

            <div className="grid gap-2">
              <label className="text-sm font-medium">{t('admin.createExpiresAt')}</label>
              <Input type="datetime-local" value={formExpiresAt} onChange={(e) => setFormExpiresAt(e.target.value)} />
            </div>
          </div>

          <div className="grid gap-2">
            <label className="text-sm font-medium">{t('admin.createContent')}</label>
            <MarkdownEditor
              value={formContent}
              onChange={setFormContent}
              height={200}
              preview="live"
            />
            <p className="text-xs text-muted-foreground">{t('admin.contentMarkdownHint')}</p>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <label className="text-sm font-medium">{t('admin.notifyChannels')}</label>
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

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import {
  packagesApi,
  type PackagesApi,
  type ClouisleConflictAction,
  type ClouisleDependencyStatus,
  type ClouisleImportPreview,
  type ClouisleResourceType,
} from '@/lib/api/packages'
import type { Team } from '@/lib/api/teams'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

function resourceLabelKey(type: ClouisleResourceType) {
  switch (type) {
    case 'tool':
      return 'resource.tool'
    case 'agent':
      return 'resource.agent'
    case 'workflow':
      return 'resource.workflow'
    case 'knowledge_base':
      return 'resource.knowledge_base'
  }
}

function dependencyTypeLabelKey(type: string) {
  switch (type) {
    case 'agent':
      return 'dependencyType.agent'
    case 'knowledge_base':
      return 'dependencyType.knowledge_base'
    case 'model':
      return 'dependencyType.model'
    case 'tool':
      return 'dependencyType.tool'
    case 'workflow':
      return 'dependencyType.workflow'
    default:
      return null
  }
}

function dependencyStatusLabelKey(status: ClouisleDependencyStatus) {
  switch (status) {
    case 'resolved':
      return 'dependencyStatus.resolved'
    case 'missing':
      return 'dependencyStatus.missing'
    case 'forbidden':
      return 'dependencyStatus.forbidden'
    case 'unsupported':
      return 'dependencyStatus.unsupported'
  }
}

function conflictActionLabelKey(action: ClouisleConflictAction) {
  switch (action) {
    case 'install':
      return 'conflictAction.install'
    case 'rename':
      return 'conflictAction.rename'
    case 'update':
      return 'conflictAction.update'
    case 'skip':
      return 'conflictAction.skip'
  }
}

interface ImportPackageDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  teamId?: string
  teams?: Team[]
  expectedResourceType?: ClouisleResourceType
  onImported?: (resultId?: string | null) => void
  api?: PackagesApi
}

export function ImportPackageDialog({
  open,
  onOpenChange,
  teamId,
  teams = [],
  expectedResourceType,
  onImported,
  api = packagesApi,
}: ImportPackageDialogProps) {
  const t = useTranslations('packages')
  const commonT = useTranslations('common')
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const [preview, setPreview] = React.useState<ClouisleImportPreview | null>(null)
  const [action, setAction] = React.useState<ClouisleConflictAction>('install')
  const [targetName, setTargetName] = React.useState('')
  const [selectedFileName, setSelectedFileName] = React.useState('')
  const [selectedTeamId, setSelectedTeamId] = React.useState(teamId || teams[0]?.id || '')
  const [isPreviewing, setIsPreviewing] = React.useState(false)
  const [isInstalling, setIsInstalling] = React.useState(false)

  React.useEffect(() => {
    if (!open) {
      setPreview(null)
      setAction('install')
      setTargetName('')
      setSelectedFileName('')
      setSelectedTeamId(teamId || teams[0]?.id || '')
    }
  }, [open, teamId, teams])

  React.useEffect(() => {
    setSelectedTeamId(teamId || teams[0]?.id || '')
  }, [teamId, teams])

  const translateMessage = (message: string) => {
    const key = `messages.${message}`
    return t.has(key) ? t(key) : message
  }

  const previewFile = async (selectedFile: File) => {
    if (!selectedFile.name.toLowerCase().endsWith('.clouisle')) {
      toast.error(t('selectClouisleFile'))
      setPreview(null)
      return
    }
    if (!selectedTeamId) {
      toast.error(t('selectTargetTeam'))
      setPreview(null)
      return
    }
    setPreview(null)
    setIsPreviewing(true)
    try {
      const data = await api.preview(selectedTeamId, selectedFile)
      if (expectedResourceType && data.resource_type !== expectedResourceType) {
        toast.error(t('typeMismatch', {
          actual: t(resourceLabelKey(data.resource_type)),
          expected: t(resourceLabelKey(expectedResourceType)),
        }))
      }
      setPreview(data)
      setAction(data.default_action)
      setTargetName(data.resource_name)
    } catch {
      setPreview(null)
    } finally {
      setIsPreviewing(false)
    }
  }

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0]
    if (!selectedFile) return
    setSelectedFileName(selectedFile.name)
    void previewFile(selectedFile)
  }

  const conflictName = preview?.conflict?.existing_name || preview?.resource_name || ''
  const conflictResolved = !preview?.conflict || preview.conflict.type === 'none'
    || action === 'update'
    || action === 'skip'
    || (action === 'rename' && targetName.trim() !== '' && targetName.trim() !== conflictName.trim())
  const canInstall = Boolean(preview?.valid) && (!expectedResourceType || preview?.resource_type === expectedResourceType) && conflictResolved
  const dialogTitle = expectedResourceType
    ? t('dialogTitleWithResource', { resource: t(resourceLabelKey(expectedResourceType)) })
    : t('dialogTitle')

  const handleInstall = async () => {
    if (!preview || !canInstall) return
    setIsInstalling(true)
    try {
      const result = await api.install(preview.session_id, {
        action,
        target_name: action === 'rename' ? targetName : undefined,
        dependency_mapping: {},
      })
      toast.success(result.skipped ? t('importSkipped') : t('packageImported'))
      onImported?.(result.installed || result.updated)
      onOpenChange(false)
    } catch {
      // API interceptor displays the error toast.
    } finally {
      setIsInstalling(false)
    }
  }

  const handleTeamChange = (value: string | null) => {
    if (!value) return
    setSelectedTeamId(value)
    setPreview(null)
    setSelectedFileName('')
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{dialogTitle}</DialogTitle>
          <DialogDescription>
            {t('dialogDescription')}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {teams.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm font-medium">{t('targetTeam')}</div>
              <Select value={selectedTeamId} onValueChange={handleTeamChange} disabled={isPreviewing || isInstalling}>
                <SelectTrigger className="bg-background">
                  <SelectValue>{teams.find((team) => team.id === selectedTeamId)?.name || t('selectTargetTeam')}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {teams.map((team) => (
                    <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                disabled={isPreviewing || isInstalling}
                onClick={() => fileInputRef.current?.click()}
              >
                {t('chooseFile')}
              </Button>
              <Input
                ref={fileInputRef}
                type="file"
                accept=".clouisle"
                disabled={isPreviewing || isInstalling}
                className="sr-only"
                onChange={handleFileChange}
              />
              <span className="text-sm text-muted-foreground">
                {selectedFileName || t('noFileSelected')}
              </span>
            </div>
            {isPreviewing && (
              <div className="flex items-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {t('previewing')}
              </div>
            )}
          </div>

          {preview && (
            <div className="space-y-4 rounded-lg border p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm text-muted-foreground">{t(resourceLabelKey(preview.resource_type))}</div>
                  <div className="font-medium">{preview.resource_name}</div>
                </div>
                <Badge variant={preview.valid ? 'default' : 'destructive'}>
                  {preview.valid ? t('valid') : t('invalid')}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-muted-foreground">{t('format')}</span>
                  <div>{preview.format_version}</div>
                </div>
                <div>
                  <span className="text-muted-foreground">{t('exported')}</span>
                  <div>{new Date(preview.exported_at).toLocaleString()}</div>
                </div>
              </div>

              {preview.errors.length > 0 && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                  {preview.errors.map((error) => <div key={error}>{translateMessage(error)}</div>)}
                </div>
              )}

              {preview.warnings.length > 0 && (
                <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm">
                  {preview.warnings.map((warning) => <div key={warning}>{translateMessage(warning)}</div>)}
                </div>
              )}

              {preview.dependencies.length > 0 && (
                <div className="space-y-2">
                  <div className="text-sm font-medium">{t('dependencies')}</div>
                  <div className="max-h-40 overflow-y-auto rounded-md border">
                    {preview.dependencies.map((dependency, index) => {
                      const labelKey = dependencyTypeLabelKey(dependency.type)
                      return (
                        <div key={`${dependency.type}-${dependency.source_id}-${index}`} className="flex items-center justify-between border-b px-3 py-2 text-sm last:border-b-0">
                          <span>{t('dependencyLabel', {
                            type: labelKey ? t(labelKey) : dependency.type,
                            name: dependency.name || dependency.source_id || t('unknown'),
                          })}</span>
                          <Badge variant={dependency.status === 'resolved' ? 'outline' : dependency.required ? 'destructive' : 'secondary'}>
                            {dependency.status ? t(dependencyStatusLabelKey(dependency.status)) : t('unknown')}
                          </Badge>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}

              {preview.conflict && preview.conflict.type !== 'none' && (
                <div className={`space-y-3 rounded-md border p-3 ${conflictResolved ? 'border-border bg-muted/30' : 'border-destructive/40 bg-destructive/10'}`}>
                  <div className={`text-sm font-medium ${conflictResolved ? '' : 'text-destructive'}`}>{t('nameConflict', { name: conflictName })}</div>
                  <Select value={action} onValueChange={(value) => setAction(value as ClouisleConflictAction)}>
                    <SelectTrigger className="bg-background">
                      <SelectValue>{t(conflictActionLabelKey(action))}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {preview.allowed_actions.map((allowedAction) => (
                        <SelectItem key={allowedAction} value={allowedAction}>{t(conflictActionLabelKey(allowedAction))}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {action === 'rename' && (
                    <Input className="bg-background" value={targetName} onChange={(event) => setTargetName(event.target.value)} />
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{commonT('cancel')}</Button>
          <Button onClick={handleInstall} disabled={!canInstall || isInstalling}>
            {isInstalling && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('install')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

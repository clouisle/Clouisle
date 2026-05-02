'use client'

import { useCallback, useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { AlertCircle, CheckCircle2, Download, FileArchive, GitBranch, Loader2, MoreVertical, PackageOpen, Play, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'

import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { useTeam } from '@/contexts/team-context'
import { cn } from '@/lib/utils'
import {
  ApiError,
  skillsApi,
  type Skill,
  type SkillImportPreviewResponse,
  type SkillInstallAction,
  type SkillPreviewItem,
  type SkillTestResponse,
} from '@/lib/api'

interface PreviewSelection {
  checked: boolean
  action: SkillInstallAction
}

function getPreviewGroupKey(item: SkillPreviewItem) {
  return item.name || item.package_path
}

function defaultTestArguments(skill: Skill | null) {
  const required = (skill?.input_schema?.required as unknown) || []
  const properties = (skill?.input_schema?.properties as Record<string, unknown> | undefined) || {}
  const args: Record<string, unknown> = {}
  if (Array.isArray(required)) {
    required.forEach((key) => {
      if (typeof key === 'string') args[key] = key === 'prompt' ? 'Run this skill on a simple sample.' : ''
    })
  }
  if (Object.keys(args).length === 0 && properties.prompt) args.prompt = 'Run this skill on a simple sample.'
  return JSON.stringify(args, null, 2)
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(value || '{}')
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

function formatBytes(value?: number) {
  if (value == null) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unknown error'
}

function PreviewSkillSummary({ item }: { item: SkillPreviewItem }) {
  return (
    <div className="max-w-72">
      <div className="truncate font-medium">{item.display_name || item.name || '-'}</div>
      <div className="truncate text-xs text-muted-foreground">{item.description}</div>
    </div>
  )
}

function PreviewRow({
  item,
  selection,
  onChange,
}: {
  item: SkillPreviewItem
  selection: PreviewSelection | undefined
  onChange: (selection: PreviewSelection) => void
}) {
  const t = useTranslations('platform.skills.import')
  const current = selection || { checked: false, action: 'install' as SkillInstallAction }
  const actionLabel = {
    install: t('install'),
    update: t('update'),
    skip: t('skip'),
  }[current.action]
  const hasDuplicateName = item.warnings.includes('skill_duplicate_name_in_source')
  return (
    <TableRow>
      <TableCell>
        <Checkbox
          checked={current.checked}
          onCheckedChange={(checked) => onChange({ ...current, checked: checked === true })}
        />
      </TableCell>
      <TableCell className="max-w-52 truncate">{item.package_path}</TableCell>
      <TableCell><PreviewSkillSummary item={item} /></TableCell>
      <TableCell>
        {item.conflict ? (
          <Badge variant="secondary">{t('conflict')}</Badge>
        ) : hasDuplicateName ? (
          <Badge variant="outline">{t('duplicateName')}</Badge>
        ) : (
          <span className="inline-flex items-center text-sm text-muted-foreground">
            <CheckCircle2 className="mr-1 h-4 w-4 text-green-600" />
            {t('valid')}
          </span>
        )}
      </TableCell>
      <TableCell>
        <Select value={current.action} onValueChange={(value) => onChange({ ...current, action: value as SkillInstallAction })}>
          <SelectTrigger className="w-28">
            <SelectValue>{actionLabel}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="install">{t('install')}</SelectItem>
            <SelectItem value="update">{t('update')}</SelectItem>
            <SelectItem value="skip">{t('skip')}</SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
    </TableRow>
  )
}

export function SkillsPanel() {
  const t = useTranslations('platform.skills')
  const { currentTeam } = useTeam()
  const { canPerform } = useCanPerform()

  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [importOpen, setImportOpen] = useState(false)
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [gitRef, setGitRef] = useState('')
  const [preview, setPreview] = useState<SkillImportPreviewResponse | null>(null)
  const [previewSelections, setPreviewSelections] = useState<Record<string, PreviewSelection>>({})
  const [previewLoading, setPreviewLoading] = useState(false)
  const [installLoading, setInstallLoading] = useState(false)
  const [testingSkill, setTestingSkill] = useState<Skill | null>(null)
  const [testArguments, setTestArguments] = useState('{}')
  const [testResult, setTestResult] = useState<SkillTestResponse | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteLoadingId, setDeleteLoadingId] = useState<string | null>(null)

  const loadSkills = useCallback(async () => {
    if (!currentTeam?.id) return

    setLoading(true)
    try {
      const response = await skillsApi.list({ team_id: currentTeam.id, include_system: true })
      setSkills([...response.system, ...response.team])
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [currentTeam?.id])

  useEffect(() => {
    loadSkills()
  }, [loadSkills])

  const openImportDialog = () => {
    setZipFile(null)
    setGitUrl('')
    setGitRef('')
    setPreview(null)
    setPreviewSelections({})
    setImportOpen(true)
  }

  const applyPreview = (nextPreview: SkillImportPreviewResponse) => {
    const selections: Record<string, PreviewSelection> = {}
    const selectedNames = new Set<string>()
    nextPreview.skills.forEach((item) => {
      const groupKey = getPreviewGroupKey(item)
      const checked = !item.conflict && !selectedNames.has(groupKey)
      if (checked) selectedNames.add(groupKey)
      selections[item.package_path] = {
        checked,
        action: item.conflict ? 'update' : 'install',
      }
    })
    setPreview(nextPreview)
    setPreviewSelections(selections)
  }

  const handlePreviewZip = async () => {
    if (!currentTeam?.id || !zipFile) return

    setPreviewLoading(true)
    try {
      applyPreview(await skillsApi.previewZip(currentTeam.id, zipFile))
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handlePreviewGit = async () => {
    if (!currentTeam?.id || !gitUrl.trim()) return

    setPreviewLoading(true)
    try {
      applyPreview(await skillsApi.previewGit({
        team_id: currentTeam.id,
        repo_url: gitUrl.trim(),
        ref: gitRef.trim() || null,
      }))
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setPreviewLoading(false)
    }
  }

  const updatePreviewSelection = (item: SkillPreviewItem, selection: PreviewSelection) => {
    setPreviewSelections((current) => {
      const next = { ...current, [item.package_path]: selection }
      if (selection.checked) {
        const groupKey = getPreviewGroupKey(item)
        preview?.skills.forEach((candidate) => {
          if (candidate.package_path !== item.package_path && getPreviewGroupKey(candidate) === groupKey) {
            next[candidate.package_path] = {
              ...(next[candidate.package_path] || { action: candidate.conflict ? 'update' : 'install' }),
              checked: false,
            }
          }
        })
      }
      return next
    })
  }

  const handleInstall = async () => {
    if (!preview) return

    const items = preview.skills
      .filter((item) => previewSelections[item.package_path]?.checked)
      .map((item) => ({
        package_path: item.package_path,
        action: previewSelections[item.package_path]?.action || ('install' as SkillInstallAction),
      }))

    setInstallLoading(true)
    try {
      const result = await skillsApi.install(preview.session_id, { items, is_enabled: true })
      if (result.errors.length > 0) {
        toast.error(result.errors.join('; '))
      } else {
        toast.success(t('import.installed'))
        setImportOpen(false)
        await loadSkills()
      }
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setInstallLoading(false)
    }
  }

  const handleDelete = async (skill: Skill) => {
    setDeleteLoadingId(skill.id)
    try {
      await skillsApi.delete(skill.id)
      toast.success(t('deleted'))
      await loadSkills()
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setDeleteLoadingId(null)
    }
  }

  const openTestDialog = (skill: Skill) => {
    setTestingSkill(skill)
    setTestArguments(defaultTestArguments(skill))
    setTestResult(null)
  }

  const formatImportIssue = (key: string) => {
    const messages: Record<string, string> = {
      skill_duplicate_name_in_source: t('import.errors.duplicateNameInSource'),
      skill_package_invalid: t('import.errors.invalidPackage'),
      skill_package_not_in_session: t('import.errors.packageNotInSession'),
      skill_package_path_invalid: t('import.errors.packagePathInvalid'),
      skill_name_exists: t('import.errors.nameExists'),
    }
    return messages[key] || key
  }

  const handleRunTest = async () => {
    if (!testingSkill) return

    setTestLoading(true)
    try {
      const args = parseJsonObject(testArguments, 'arguments')
      const result = await skillsApi.test(testingSkill.id, { arguments: args })
      setTestResult(result)
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setTestLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{t('title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadSkills} disabled={loading}>
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>
          <PermissionGuard permission="skill:create">
            <Button onClick={openImportDialog}>
              <Plus className="mr-2 h-4 w-4" />
              {t('import.open')}
            </Button>
          </PermissionGuard>
        </div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : skills.length === 0 ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <PackageOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <CardTitle>{t('noSkills')}</CardTitle>
            <CardDescription className="mt-2">{t('noSkillsHint')}</CardDescription>
            <PermissionGuard permission="skill:create">
              <Button className="mt-4" onClick={openImportDialog}>
                <Plus className="mr-2 h-4 w-4" />
                {t('import.open')}
              </Button>
            </PermissionGuard>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => {
            const isSystem = !skill.team_id
            const canModify = !isSystem

            return (
              <Card
                key={skill.id}
                size="sm"
                className={cn(
                  'group cursor-pointer transition-all hover:shadow-md hover:border-primary/50 py-0! h-36',
                  !skill.is_enabled && 'opacity-60'
                )}
                onClick={() => canPerform('skill:execute') && openTestDialog(skill)}
              >
                <CardContent className="flex h-full flex-col justify-between px-2.5 py-3">
                  <div className="flex items-start gap-2">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted text-base">
                      {skill.icon ? skill.icon : <PackageOpen className="h-4 w-4" />}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <CardTitle className="truncate text-sm font-medium">{skill.display_name}</CardTitle>
                        <Badge variant={skill.is_enabled ? 'default' : 'outline'} className="shrink-0 px-1.5 py-0 text-xs">
                          {skill.is_enabled ? t('enabled') : t('disabled')}
                        </Badge>
                      </div>
                      <CardDescription className="mt-0.5 line-clamp-2 text-xs">
                        {skill.description || t('noDescription')}
                      </CardDescription>
                    </div>
                  </div>

                  <div className="mt-auto flex items-center justify-between border-t pt-2">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge variant="outline" className="bg-sky-100 px-1.5 py-0 text-xs text-sky-800 dark:bg-sky-900 dark:text-sky-300">
                        {isSystem ? t('system') : t('team')}
                      </Badge>
                      <Badge variant="outline" className="px-1.5 py-0 text-xs">
                        {skill.category}
                      </Badge>
                      <Badge variant="outline" className="px-1.5 py-0 text-xs">
                        v{skill.version}
                      </Badge>
                    </div>

                    <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                      {canPerform('skill:execute') && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-6 w-6 p-0"
                          onClick={(event) => {
                            event.stopPropagation()
                            openTestDialog(skill)
                          }}
                        >
                          <Play className="h-3.5 w-3.5" />
                        </Button>
                      )}

                      {canModify && (
                        <PermissionGuard permission="skill:delete">
                          <DropdownMenu>
                            <DropdownMenuTrigger
                              render={
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  className="h-6 w-6 p-0"
                                  onClick={(event) => event.stopPropagation()}
                                  disabled={deleteLoadingId === skill.id}
                                >
                                  {deleteLoadingId === skill.id ? (
                                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                                  ) : (
                                    <MoreVertical className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                              }
                            />
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                className="text-destructive"
                                onClick={(event) => {
                                  event.stopPropagation()
                                  handleDelete(skill)
                                }}
                              >
                                <Trash2 className="mr-2 h-4 w-4" />
                                {t('delete')}
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </PermissionGuard>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-h-[90vh] overflow-x-hidden overflow-y-auto sm:max-w-5xl" open={importOpen}>
          <DialogHeader>
            <DialogTitle>{t('import.title')}</DialogTitle>
            <DialogDescription>{t('import.description')}</DialogDescription>
          </DialogHeader>

          <Tabs defaultValue="zip" className="space-y-4">
            <TabsList>
              <TabsTrigger value="zip">
                <FileArchive className="mr-2 h-4 w-4" />
                {t('import.zip')}
              </TabsTrigger>
              <TabsTrigger value="git">
                <GitBranch className="mr-2 h-4 w-4" />
                {t('import.git')}
              </TabsTrigger>
            </TabsList>
            <TabsContent value="zip" className="space-y-3">
              <Label>{t('import.zipFile')}</Label>
              <Input className="max-w-md" type="file" accept=".zip" onChange={(event) => setZipFile(event.target.files?.[0] || null)} />
              <Button onClick={handlePreviewZip} disabled={!zipFile || previewLoading}>
                {previewLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('import.scan')}
              </Button>
            </TabsContent>
            <TabsContent value="git" className="space-y-3">
              <div className="space-y-2">
                <Label>{t('import.repoUrl')}</Label>
                <Input className="max-w-md" value={gitUrl} onChange={(event) => setGitUrl(event.target.value)} placeholder="https://github.com/org/repo.git" />
              </div>
              <div className="space-y-2">
                <Label>{t('import.ref')}</Label>
                <Input className="max-w-xs" value={gitRef} onChange={(event) => setGitRef(event.target.value)} placeholder="main" />
              </div>
              <div>
                <Button onClick={handlePreviewGit} disabled={!gitUrl.trim() || previewLoading}>
                  {previewLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  {t('import.scan')}
                </Button>
              </div>
            </TabsContent>
          </Tabs>

          {preview && (
            <div className="min-w-0 max-w-full space-y-3 overflow-hidden">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="font-medium">{t('import.previewTitle')}</h3>
                  <p className="text-sm text-muted-foreground">
                    {t('import.previewSummary', { valid: preview.skills.length, invalid: preview.invalid.length })}
                  </p>
                </div>
                <Badge variant="outline">{preview.source_type}</Badge>
              </div>
              <div className="min-w-0 max-w-full overflow-x-auto rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10" />
                      <TableHead>{t('import.packagePath')}</TableHead>
                      <TableHead>{t('import.name')}</TableHead>
                      <TableHead>{t('import.status')}</TableHead>
                      <TableHead>{t('import.action')}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {preview.skills.map((item) => (
                      <PreviewRow
                        key={item.package_path}
                        item={item}
                        selection={previewSelections[item.package_path]}
                        onChange={(selection) => updatePreviewSelection(item, selection)}
                      />
                    ))}
                    {preview.invalid.map((item) => (
                      <TableRow key={item.package_path}>
                        <TableCell><AlertCircle className="h-4 w-4 text-destructive" /></TableCell>
                        <TableCell>{item.package_path}</TableCell>
                        <TableCell><PreviewSkillSummary item={item} /></TableCell>
                        <TableCell className="text-destructive">{item.errors.map(formatImportIssue).join(', ')}</TableCell>
                        <TableCell>{t('import.skip')}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setImportOpen(false)}>{t('cancel')}</Button>
            <Button onClick={handleInstall} disabled={!preview || installLoading || !Object.values(previewSelections).some((item) => item.checked)}>
              {installLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('import.installSelected')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!testingSkill} onOpenChange={(open) => !open && setTestingSkill(null)}>
        <DialogContent className="sm:max-w-2xl" open={!!testingSkill}>
          <DialogHeader>
            <DialogTitle>{t('testTitle', { name: testingSkill?.display_name || '' })}</DialogTitle>
            <DialogDescription>{t('testDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>{t('arguments')}</Label>
              <Textarea
                rows={6}
                className="font-mono text-xs"
                value={testArguments}
                onChange={(e) => setTestArguments(e.target.value)}
              />
            </div>
            {testResult && (
              <div className="rounded-lg border bg-muted/40 p-3">
                <div className="mb-2 flex items-center gap-2">
                  <Badge variant={testResult.success ? 'default' : 'destructive'}>
                    {testResult.success ? t('success') : t('failed')}
                  </Badge>
                  {testResult.duration_ms != null && (
                    <span className="text-xs text-muted-foreground">{testResult.duration_ms}ms</span>
                  )}
                </div>
                {testResult.artifacts.length > 0 && (
                  <div className="mb-3 space-y-2">
                    <div className="text-sm font-medium">{t('artifacts')}</div>
                    <div className="space-y-2">
                      {testResult.artifacts.map((artifact) => (
                        <div key={`${artifact.path}-${artifact.url || artifact.filename}`} className="flex items-center justify-between gap-3 rounded-md border bg-background px-3 py-2 text-sm">
                          <div className="min-w-0">
                            <div className="truncate font-medium">{artifact.filename || artifact.path}</div>
                            <div className="truncate text-xs text-muted-foreground">
                              {artifact.path} · {formatBytes(artifact.size)}
                            </div>
                          </div>
                          {artifact.url && (
                            <a
                              href={artifact.url}
                              target="_blank"
                              rel="noreferrer"
                              className={buttonVariants({ variant: 'outline', size: 'sm' })}
                            >
                              <Download className="mr-2 h-4 w-4" />
                              {t('download')}
                            </a>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap text-xs">
                  {JSON.stringify(testResult, null, 2)}
                </pre>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTestingSkill(null)}>{t('close')}</Button>
            <Button onClick={handleRunTest} disabled={testLoading || !canPerform('skill:execute')}>
              {testLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('runTest')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

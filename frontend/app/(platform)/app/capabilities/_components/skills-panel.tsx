'use client'

import { useCallback, useEffect, useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AlertCircle, CheckCircle2, FileArchive, GitBranch, Loader2, PackageOpen, RefreshCw, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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

import { PermissionGuard } from '@/components/permission-guard'
import { SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES } from '@/lib/constants'
import { useTeam } from '@/contexts/team-context'
import { cn } from '@/lib/utils'
import {
  ApiError,
  skillsApi,
  type Skill,
  type SkillImportPreviewResponse,
  type SkillInstallAction,
  type SkillPreviewItem,
} from '@/lib/api'

interface PreviewSelection {
  checked: boolean
  action: SkillInstallAction
}

function getPreviewGroupKey(item: SkillPreviewItem) {
  return item.name || item.package_path
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

  const handleZipFileChange = (file: File | null) => {
    if (!file) {
      setZipFile(null)
      return
    }
    if (!file.name.toLowerCase().endsWith('.zip')) {
      toast.error(t('import.zipRequired'))
      setZipFile(null)
      return
    }
    if (file.size > SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES) {
      toast.error(t('import.zipTooLarge'))
      setZipFile(null)
      return
    }
    setZipFile(file)
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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">{t('title')}</h2>
          <p className="text-sm text-muted-foreground mt-1">{t('description')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={loadSkills} disabled={loading} data-testid="skills-refresh-button">
            <RefreshCw className={`mr-2 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
            {t('refresh')}
          </Button>
          <PermissionGuard permission="skill:create">
            <Button variant="outline" onClick={openImportDialog} data-testid="skills-import-button">
              <Upload className="mr-2 h-4 w-4" />
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
                <Upload className="mr-2 h-4 w-4" />
                {t('import.open')}
              </Button>
            </PermissionGuard>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => {
            const isSystem = !skill.team_id

            return (
              <Link key={skill.id} href={`/app/capabilities/skills/${skill.id}`} className="block">
                <Card
                  size="sm"
                  className={cn(
                  'py-0! h-36 transition-all hover:border-primary/50 hover:shadow-md',
                  !skill.is_enabled && 'opacity-60'
                )}
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
                  </div>
                </CardContent>
              </Card>
              </Link>
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
              <Input className="max-w-md" type="file" accept=".zip" onChange={(event) => handleZipFileChange(event.target.files?.[0] || null)} />
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
    </div>
  )
}

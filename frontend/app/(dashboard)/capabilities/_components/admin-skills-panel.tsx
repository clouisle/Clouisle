'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useTranslations } from 'next-intl'
import { AlertCircle, CheckCircle2, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Download, FileArchive, GitBranch, Loader2, MoreHorizontal, PackageOpen, Play, Plus, RefreshCw, Search, Trash2, ToggleLeft, ToggleRight, X } from 'lucide-react'
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
import { DataTableFacetedFilter } from '@/components/ui/data-table-faceted-filter'

import { PermissionGuard, useCanPerform } from '@/components/permission-guard'
import { ApiError, type PageData, type SkillInstallAction, type SkillImportPreviewResponse, type SkillPreviewItem, type SkillSourceType, type SkillTestResponse, type ToolFilterOption } from '@/lib/api'
import { adminSkillsApi, teamsApi as adminTeamsApi, type AdminSkill } from '@/lib/api/admin'
import type { Team } from '@/lib/api/teams'
import { useUrlSearchState } from '@/hooks/use-url-search-state'

interface PreviewSelection {
  checked: boolean
  action: SkillInstallAction
}

function getPreviewGroupKey(item: SkillPreviewItem) {
  return item.name || item.package_path
}

function defaultTestArguments(skill: AdminSkill | null) {
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

export function AdminSkillsPanel() {
  const t = useTranslations('platform.skills')
  const tCommon = useTranslations('common')
  const { canPerform } = useCanPerform()

  const [skills, setSkills] = useState<AdminSkill[]>([])
  const [teams, setTeams] = useState<Team[]>([])
  const [sourceOptions, setSourceOptions] = useState<ToolFilterOption[]>([])
  const [teamOptions, setTeamOptions] = useState<ToolFilterOption[]>([])
  const [creatorOptions, setCreatorOptions] = useState<ToolFilterOption[]>([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [pageData, setPageData] = useState<PageData<AdminSkill> | null>(null)
  const [searchQuery, setSearchQuery] = useUrlSearchState()
  const [statusFilter, setStatusFilter] = useState<Set<string>>(new Set())
  const [sourceFilter, setSourceFilter] = useState<Set<string>>(new Set())
  const [teamFilter, setTeamFilter] = useState<Set<string>>(new Set())
  const [creatorFilter, setCreatorFilter] = useState<Set<string>>(new Set())
  const [importOpen, setImportOpen] = useState(false)
  const [targetTeamId, setTargetTeamId] = useState<string>('system')
  const [zipFile, setZipFile] = useState<File | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [gitRef, setGitRef] = useState('')
  const [preview, setPreview] = useState<SkillImportPreviewResponse | null>(null)
  const [previewSelections, setPreviewSelections] = useState<Record<string, PreviewSelection>>({})
  const [previewLoading, setPreviewLoading] = useState(false)
  const [installLoading, setInstallLoading] = useState(false)
  const [testingSkill, setTestingSkill] = useState<AdminSkill | null>(null)
  const [testArguments, setTestArguments] = useState('{}')
  const [testResult, setTestResult] = useState<SkillTestResponse | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [deleteLoadingId, setDeleteLoadingId] = useState<string | null>(null)
  const [toggleLoadingId, setToggleLoadingId] = useState<string | null>(null)

  const loadTeams = useCallback(async () => {
    try {
      const response = await adminTeamsApi.getTeams(1, 100)
      setTeams(response.items)
    } catch (error) {
      toast.error(getErrorMessage(error))
    }
  }, [])

  const selectedStatuses = useMemo(() => Array.from(statusFilter), [statusFilter])
  const selectedSources = useMemo(() => Array.from(sourceFilter), [sourceFilter])
  const selectedTeams = useMemo(() => Array.from(teamFilter), [teamFilter])
  const selectedCreators = useMemo(() => Array.from(creatorFilter), [creatorFilter])

  const loadSkills = useCallback(async () => {
    setLoading(true)
    try {
      const [skillsData, filterOptions] = await Promise.all([
        adminSkillsApi.list({
          page,
          pageSize,
          search: searchQuery || undefined,
          include_system: true,
          status: selectedStatuses.length > 0 ? selectedStatuses : undefined,
          source_type: selectedSources.length > 0 ? selectedSources : undefined,
          team_id: selectedTeams.length > 0 ? selectedTeams : undefined,
          creator: selectedCreators.length > 0 ? selectedCreators : undefined,
        }),
        adminSkillsApi.getFilterOptions(),
      ])
      setSkills(skillsData.items)
      setPageData(skillsData)
      setSourceOptions(filterOptions.sources)
      setTeamOptions(filterOptions.teams)
      setCreatorOptions(filterOptions.creators)
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, searchQuery, selectedStatuses, selectedSources, selectedTeams, selectedCreators])

  useEffect(() => {
    loadTeams()
    loadSkills()
  }, [loadTeams, loadSkills])

  const openImportDialog = () => {
    setTargetTeamId('system')
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

  const totalPages = pageData ? Math.max(1, Math.ceil(pageData.total / pageSize)) : 1
  const isFiltered = Boolean(searchQuery) || statusFilter.size > 0 || sourceFilter.size > 0 || teamFilter.size > 0 || creatorFilter.size > 0
  const selectedTargetTeamId = targetTeamId === 'system' ? null : targetTeamId
  const targetTeamLabel = targetTeamId === 'system'
    ? t('system')
    : teams.find((team) => team.id === targetTeamId)?.name || t('team')

  const resetToFirstPage = () => setPage(1)

  const handleStatusFilterChange = (values: Set<string>) => {
    setStatusFilter(values)
    resetToFirstPage()
  }

  const handleSourceFilterChange = (values: Set<string>) => {
    setSourceFilter(values)
    resetToFirstPage()
  }

  const handleTeamFilterChange = (values: Set<string>) => {
    setTeamFilter(values)
    resetToFirstPage()
  }

  const handleCreatorFilterChange = (values: Set<string>) => {
    setCreatorFilter(values)
    resetToFirstPage()
  }

  const resetFilters = () => {
    setSearchQuery('')
    setStatusFilter(new Set())
    setSourceFilter(new Set())
    setTeamFilter(new Set())
    setCreatorFilter(new Set())
    resetToFirstPage()
  }

  const statusOptions = [
    { value: 'enabled', label: t('enabled') },
    { value: 'disabled', label: t('disabled') },
  ]

  const sourceFilterOptions = sourceOptions.map((option) => ({
    value: option.value,
    label: t(`sources.${option.value as SkillSourceType}`),
  }))

  const handlePreviewZip = async () => {
    if (!zipFile) return
    setPreviewLoading(true)
    try {
      applyPreview(await adminSkillsApi.previewZip(selectedTargetTeamId, zipFile))
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setPreviewLoading(false)
    }
  }

  const handlePreviewGit = async () => {
    if (!gitUrl.trim()) return
    setPreviewLoading(true)
    try {
      applyPreview(await adminSkillsApi.previewGit({
        team_id: selectedTargetTeamId,
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
      const result = await adminSkillsApi.install(preview.session_id, { items, is_enabled: true })
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

  const handleToggle = async (skill: AdminSkill) => {
    setToggleLoadingId(skill.id)
    try {
      await adminSkillsApi.update(skill.id, { is_enabled: !skill.is_enabled })
      toast.success(skill.is_enabled ? t('disabled') : t('enabled'))
      await loadSkills()
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setToggleLoadingId(null)
    }
  }

  const handleDelete = async (skill: AdminSkill) => {
    setDeleteLoadingId(skill.id)
    try {
      await adminSkillsApi.delete(skill.id)
      toast.success(t('deleted'))
      await loadSkills()
    } catch (error) {
      toast.error(getErrorMessage(error))
    } finally {
      setDeleteLoadingId(null)
    }
  }

  const openTestDialog = (skill: AdminSkill) => {
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
      const result = await adminSkillsApi.test(testingSkill.id, { arguments: args })
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
          <PermissionGuard permission="admin:capability:create">
            <Button onClick={openImportDialog}>
              <Plus className="mr-2 h-4 w-4" />
              {t('import.open')}
            </Button>
          </PermissionGuard>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            placeholder={t('searchPlaceholder')}
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value)
              setPage(1)
            }}
            className="h-9 w-50 pl-8"
          />
        </div>

        <DataTableFacetedFilter
          title={tCommon('status')}
          options={statusOptions}
          selectedValues={statusFilter}
          onSelectionChange={handleStatusFilterChange}
        />

        {sourceFilterOptions.length > 0 && (
          <DataTableFacetedFilter
            title={t('source')}
            options={sourceFilterOptions}
            selectedValues={sourceFilter}
            onSelectionChange={handleSourceFilterChange}
          />
        )}

        {teamOptions.length > 1 && (
          <DataTableFacetedFilter
            title={tCommon('team')}
            options={teamOptions}
            selectedValues={teamFilter}
            onSelectionChange={handleTeamFilterChange}
            searchable
          />
        )}

        {creatorOptions.length > 0 && (
          <DataTableFacetedFilter
            title={tCommon('createdBy')}
            options={creatorOptions}
            selectedValues={creatorFilter}
            onSelectionChange={handleCreatorFilterChange}
            searchable
          />
        )}

        {isFiltered && (
          <Button variant="ghost" onClick={resetFilters} className="h-9 px-2 lg:px-3">
            {tCommon('reset')}
            <X className="ml-2 h-4 w-4" />
          </Button>
        )}
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : skills.length === 0 && !isFiltered ? (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16 text-center">
            <PackageOpen className="h-12 w-12 text-muted-foreground mb-4" />
            <CardTitle>{t('noSkills')}</CardTitle>
            <CardDescription className="mt-2">{t('noSkillsHint')}</CardDescription>
            <PermissionGuard permission="admin:capability:create">
              <Button className="mt-4" onClick={openImportDialog}>
                <Plus className="mr-2 h-4 w-4" />
                {t('import.open')}
              </Button>
            </PermissionGuard>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50">
                  <TableHead>{t('import.name')}</TableHead>
                  <TableHead>{tCommon('team')}</TableHead>
                  <TableHead>{t('version')}</TableHead>
                  <TableHead>{t('source')}</TableHead>
                  <TableHead>{tCommon('createdBy')}</TableHead>
                  <TableHead>{tCommon('status')}</TableHead>
                  <TableHead className="w-12"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {skills.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                      {t('noSkills')}
                    </TableCell>
                  </TableRow>
                ) : skills.map((skill) => {
                  const isSystem = !skill.team_id
                  const isBusy = deleteLoadingId === skill.id || toggleLoadingId === skill.id
                  const hasActions = canPerform('admin:capability:execute') || canPerform('admin:capability:update') || canPerform('admin:capability:delete')
                  return (
                    <TableRow key={skill.id} className={!skill.is_enabled ? 'opacity-60' : undefined}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted text-base">
                            {skill.icon ? skill.icon : <PackageOpen className="h-4 w-4" />}
                          </div>
                          <div className="min-w-0">
                            <button
                              type="button"
                              className="truncate text-left font-medium hover:underline"
                              onClick={() => canPerform('admin:capability:execute') && openTestDialog(skill)}
                            >
                              {skill.display_name}
                            </button>
                            <div className="max-w-md truncate text-xs text-muted-foreground">
                              {skill.description || t('noDescription')}
                            </div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-300">
                          {isSystem ? t('system') : skill.team_name || t('team')}
                        </Badge>
                      </TableCell>
                      <TableCell>v{skill.version}</TableCell>
                      <TableCell>{t(`sources.${skill.source_type}`)}</TableCell>
                      <TableCell>
                        <span className="text-muted-foreground">{skill.created_by_name || '-'}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={skill.is_enabled ? 'default' : 'outline'}>
                          {skill.is_enabled ? t('enabled') : t('disabled')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {hasActions && (
                          <DropdownMenu>
                            <DropdownMenuTrigger
                            render={
                              <Button variant="ghost" size="sm" className="h-8 w-8 p-0" disabled={isBusy}>
                                {isBusy ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <MoreHorizontal className="h-4 w-4" />
                                )}
                              </Button>
                            }
                            />
                            <DropdownMenuContent align="end">
                            {canPerform('admin:capability:execute') && (
                              <DropdownMenuItem onClick={() => openTestDialog(skill)}>
                                <Play className="mr-2 h-4 w-4" />
                                {t('test')}
                              </DropdownMenuItem>
                            )}
                            {canPerform('admin:capability:update') && (
                              <DropdownMenuItem onClick={() => handleToggle(skill)}>
                                {skill.is_enabled ? <ToggleLeft className="mr-2 h-4 w-4" /> : <ToggleRight className="mr-2 h-4 w-4" />}
                                {skill.is_enabled ? t('disable') : t('enable')}
                              </DropdownMenuItem>
                            )}
                            {canPerform('admin:capability:delete') && (
                              <DropdownMenuItem className="text-destructive" onClick={() => handleDelete(skill)}>
                                <Trash2 className="mr-2 h-4 w-4" />
                                {t('delete')}
                              </DropdownMenuItem>
                            )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
          {pageData && pageData.total > 0 && (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Select
                  value={String(pageSize)}
                  onValueChange={(value) => {
                    setPageSize(Number(value))
                    setPage(1)
                  }}
                >
                  <SelectTrigger size="sm" className="w-18">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent side="top" alignItemWithTrigger={false}>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
                <span>{t('rowsPerPage')}</span>
              </div>

              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  {t('pageInfo', { page, total: totalPages })}
                </span>

                <div className="flex items-center gap-1">
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(1)}
                    disabled={page === 1}
                  >
                    <ChevronsLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page >= totalPages}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="outline"
                    size="icon"
                    className="h-8 w-8"
                    onClick={() => setPage(totalPages)}
                    disabled={page >= totalPages}
                  >
                    <ChevronsRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      <Dialog open={importOpen} onOpenChange={setImportOpen}>
        <DialogContent className="max-h-[90vh] overflow-x-hidden overflow-y-auto sm:max-w-5xl" open={importOpen}>
          <DialogHeader>
            <DialogTitle>{t('import.title')}</DialogTitle>
            <DialogDescription>{t('import.description')}</DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label>{tCommon('team')}</Label>
            <Select value={targetTeamId} onValueChange={(value) => value && setTargetTeamId(value)}>
              <SelectTrigger className="max-w-md">
                <SelectValue>{targetTeamLabel}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">{t('system')}</SelectItem>
                {teams.map((team) => (
                  <SelectItem key={team.id} value={team.id}>{team.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

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
              <Button onClick={handlePreviewGit} disabled={!gitUrl.trim() || previewLoading}>
                {previewLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('import.scan')}
              </Button>
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
                onChange={(event) => setTestArguments(event.target.value)}
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
            <Button onClick={handleRunTest} disabled={testLoading || !canPerform('admin:capability:execute')}>
              {testLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('runTest')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

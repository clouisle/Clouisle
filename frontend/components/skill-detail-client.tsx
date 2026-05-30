'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Streamdown } from 'streamdown'
import { ArrowLeft, Loader2, PackageOpen } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ApiError, skillsApi, type SkillDetail } from '@/lib/api'
import { adminSkillsApi } from '@/lib/api/admin'
import { toast } from 'sonner'

interface SkillDetailClientProps {
  skillId: string
  mode: 'platform' | 'admin'
  backHref: string
  teamId?: string
}

function getErrorMessage(error: unknown) {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unknown error'
}

function getInputParameterNames(skill: SkillDetail) {
  const properties = (skill.input_schema?.properties as Record<string, unknown> | undefined) || {}
  return Object.keys(properties)
}

export function SkillDetailClient({ skillId, mode, backHref, teamId }: SkillDetailClientProps) {
  const t = useTranslations('platform.skills')
  const router = useRouter()
  const [skill, setSkill] = useState<SkillDetail | null>(null)
  const [loading, setLoading] = useState(true)

  const loadSkill = useCallback(async () => {
    if (mode === 'platform' && !teamId) return

    setLoading(true)
    try {
      const data = mode === 'admin'
        ? await adminSkillsApi.get(skillId)
        : await skillsApi.get(skillId, teamId)
      setSkill(data)
    } catch (error) {
      toast.error(getErrorMessage(error))
      router.push(backHref)
    } finally {
      setLoading(false)
    }
  }, [backHref, mode, router, skillId, teamId])

  useEffect(() => {
    loadSkill()
  }, [loadSkill])

  const parameterNames = useMemo(() => skill ? getInputParameterNames(skill) : [], [skill])

  if (loading || !skill) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const isSystem = !skill.team_id

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => router.push(backHref)}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted text-lg">
              {skill.icon ? skill.icon : <PackageOpen className="h-5 w-5" />}
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-semibold tracking-tight">{skill.display_name}</h1>
              <p className="text-xs text-muted-foreground">{skill.name}</p>
            </div>
          </div>
          <p className="max-w-3xl text-sm leading-5 text-muted-foreground">
            {skill.description || t('noDescription')}
          </p>
          <div className="flex flex-wrap gap-1.5">
            <Badge variant={skill.is_enabled ? 'default' : 'outline'}>
              {skill.is_enabled ? t('enabled') : t('disabled')}
            </Badge>
            <Badge variant="outline" className="bg-sky-100 text-sky-800 dark:bg-sky-900 dark:text-sky-300">
              {isSystem ? t('system') : t('team')}
            </Badge>
            <Badge variant="outline">{skill.category}</Badge>
            <Badge variant="outline">v{skill.version}</Badge>
            <Badge variant="outline">{t(`sources.${skill.source_type}`)}</Badge>
          </div>
        </div>
      </div>

      <div className="ml-11 space-y-4">
        <Card>
          <CardHeader>
            <CardTitle>{t('details')}</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <div className="text-xs font-medium text-muted-foreground">{t('source')}</div>
              <div className="mt-1 text-sm">{skill.package_path || '-'}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">{t('parameters')}</div>
              <div className="mt-1 text-sm">{parameterNames.length > 0 ? parameterNames.join(', ') : t('noParameters')}</div>
            </div>
            <div>
              <div className="text-xs font-medium text-muted-foreground">{t('updatedAt')}</div>
              <div className="mt-1 text-sm">{new Date(skill.updated_at).toLocaleString()}</div>
            </div>
          </CardContent>
        </Card>

        {skill.instructions && (
          <Card>
            <CardHeader>
              <CardTitle>{t('instructions')}</CardTitle>
            </CardHeader>
            <CardContent className="prose prose-sm max-w-none dark:prose-invert">
              <Streamdown>{skill.instructions}</Streamdown>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

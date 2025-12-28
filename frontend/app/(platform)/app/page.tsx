'use client'

import * as React from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Bot, Database, Wrench, Grid3x3, ArrowRight, Loader2 } from 'lucide-react'
import { useTeam } from '@/contexts/team-context'
import { knowledgeBasesApi, teamModelsApi, type TeamModel } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

interface StatsData {
  knowledgeBases: number
  models: number
  tools: number
  apps: number
}

function StatCard({
  title,
  value,
  icon: Icon,
  isLoading,
}: {
  title: string
  value: number
  icon: React.ElementType
  isLoading: boolean
}) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-muted-foreground">{title}</p>
            {isLoading ? (
              <Skeleton className="h-8 w-16 mt-1" />
            ) : (
              <p className="text-3xl font-bold">{value}</p>
            )}
          </div>
          <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="h-6 w-6 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

function FeatureCard({
  title,
  description,
  icon: Icon,
  href,
}: {
  title: string
  description: string
  icon: React.ElementType
  href: string
}) {
  return (
    <Link href={href}>
      <Card className="group hover:shadow-md transition-all duration-200 cursor-pointer h-full">
        <CardHeader>
          <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-3 group-hover:bg-primary/20 transition-colors">
            <Icon className="h-6 w-6 text-primary" />
          </div>
          <CardTitle className="flex items-center justify-between text-lg">
            {title}
            <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 transition-all" />
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
      </Card>
    </Link>
  )
}

export default function PlatformHomePage() {
  const t = useTranslations('platform.home')
  const { currentTeam, isLoading: isTeamLoading } = useTeam()
  const [stats, setStats] = React.useState<StatsData>({
    knowledgeBases: 0,
    models: 0,
    tools: 0,
    apps: 0,
  })
  const [isLoading, setIsLoading] = React.useState(true)

  // 加载统计数据
  const fetchStats = React.useCallback(async () => {
    if (!currentTeam) return

    try {
      setIsLoading(true)
      
      // 并行请求
      const [kbResponse, modelsResponse] = await Promise.all([
        knowledgeBasesApi.getKnowledgeBases({ pageSize: 1 }),
        teamModelsApi.getTeamModels(currentTeam.id),
      ])

      setStats({
        knowledgeBases: kbResponse.total,
        models: modelsResponse.filter((m: TeamModel) => m.is_enabled).length,
        tools: 0, // TODO: 待实现工具统计
        apps: 0, // TODO: 待实现应用统计
      })
    } catch (error) {
      console.error('Failed to fetch stats:', error)
    } finally {
      setIsLoading(false)
    }
  }, [currentTeam])

  React.useEffect(() => {
    if (currentTeam) {
      fetchStats()
    }
  }, [currentTeam, fetchStats])

  // 等待团队加载
  if (isTeamLoading) {
    return (
      <div className="py-6 px-8 flex items-center justify-center min-h-100">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const features = [
    {
      key: 'workspace',
      icon: Grid3x3,
      href: '/app/workspace',
    },
    {
      key: 'kb',
      icon: Database,
      href: '/app/kb',
    },
    {
      key: 'tools',
      icon: Wrench,
      href: '/app/tools',
    },
    {
      key: 'models',
      icon: Bot,
      href: '/app/models',
    },
  ] as const

  return (
    <div className="py-6 px-8 space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">{t('title')}</h1>
        <p className="text-muted-foreground mt-1">{t('description')}</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title={t('stats.knowledgeBases')}
          value={stats.knowledgeBases}
          icon={Database}
          isLoading={isLoading}
        />
        <StatCard
          title={t('stats.models')}
          value={stats.models}
          icon={Bot}
          isLoading={isLoading}
        />
        <StatCard
          title={t('stats.tools')}
          value={stats.tools}
          icon={Wrench}
          isLoading={isLoading}
        />
        <StatCard
          title={t('stats.apps')}
          value={stats.apps}
          icon={Grid3x3}
          isLoading={isLoading}
        />
      </div>

      {/* Quick Start */}
      <div>
        <h2 className="text-xl font-semibold mb-2">{t('quickStart')}</h2>
        <p className="text-muted-foreground text-sm mb-4">{t('quickStartDescription')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {features.map((feature) => (
            <FeatureCard
              key={feature.key}
              title={t(`features.${feature.key}.title`)}
              description={t(`features.${feature.key}.description`)}
              icon={feature.icon}
              href={feature.href}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

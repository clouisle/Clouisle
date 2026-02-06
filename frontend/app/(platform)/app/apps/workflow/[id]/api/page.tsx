'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { ArrowLeft, Loader2, ExternalLink, FileText, Activity, LayoutGrid, GitBranch } from 'lucide-react'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { workflowsApi, type Workflow } from '@/lib/api/workflows'
import { API_BASE_URL } from '@/lib/constants'
import { ApiOverview } from './_components/api-overview'
import { CodeExamples } from './_components/code-examples'
import { ApiPlayground } from './_components/api-playground'
import { ResponseSchema } from './_components/response-schema'

export default function WorkflowApiPage() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [loading, setLoading] = React.useState(true)

  const workflowId = params.id as string

  React.useEffect(() => {
    const fetchWorkflow = async () => {
      try {
        const data = await workflowsApi.getWorkflow(workflowId)
        setWorkflow(data)
      } catch (error) {
        console.error('Failed to fetch workflow:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchWorkflow()
  }, [workflowId])

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <p className="text-muted-foreground">{t('workflowNotFound')}</p>
          <Button
            variant="outline"
            className="mt-4"
            onClick={() => router.push('/app/apps/workflow')}
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            {t('backToWorkflows')}
          </Button>
        </div>
      </div>
    )
  }

  // 用于测试的相对路径（通过 Next.js 代理）
  const webhookUrl = workflow.webhook_token
    ? `/api/v1/workflows/webhook/${workflow.webhook_token}`
    : ''

  // 用于显示和外部调用的完整 URL
  const apiBaseUrl = API_BASE_URL.replace('/api/v1', '')
  const fullWebhookUrl = workflow.webhook_token
    ? `${apiBaseUrl}/api/v1/workflows/webhook/${workflow.webhook_token}`
    : ''

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <div className="absolute top-4 left-4 z-50 flex items-center gap-2">
        {/* Back Button */}
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 bg-card shadow-sm"
          onClick={() => router.push('/app/apps')}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>

        {/* Workflow Dropdown Menu */}
        <DropdownMenu>
          <DropdownMenuTrigger className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 border border-input hover:bg-accent hover:text-accent-foreground h-9 bg-card shadow-sm gap-2 px-2">
            {workflow.icon ? (
              workflow.icon.startsWith('http') || workflow.icon.startsWith('/') ? (
                <Image
                  src={workflow.icon}
                  alt={workflow.name || ''}
                  width={20}
                  height={20}
                  className="rounded object-cover"
                  unoptimized
                />
              ) : (
                <span className="text-base">{workflow.icon}</span>
              )
            ) : (
              <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10">
                <GitBranch className="h-3 w-3 text-primary" />
              </div>
            )}
            <span className="text-sm font-medium max-w-32 truncate">{workflow.name || t('untitled')}</span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}`)}
            >
              <LayoutGrid className="h-4 w-4" />
              <span>{t('orchestrate')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem className="gap-2 bg-primary/10 text-primary">
              <ExternalLink className="h-4 w-4" />
              <span>{t('accessApi')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}/logs`)}
            >
              <FileText className="h-4 w-4" />
              <span>{t('logs')}</span>
            </DropdownMenuItem>
            <DropdownMenuItem
              className="gap-2"
              onClick={() => router.push(`/app/apps/workflow/${workflowId}/monitor`)}
            >
              <Activity className="h-4 w-4" />
              <span>{t('monitor')}</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto pt-20">
        <div className="mx-auto max-w-5xl px-6 pb-20">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="overview">{t('overview')}</TabsTrigger>
              <TabsTrigger value="examples">{t('examples')}</TabsTrigger>
              <TabsTrigger value="playground">{t('playground')}</TabsTrigger>
              <TabsTrigger value="response">{t('response')}</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-6">
              <ApiOverview workflow={workflow} webhookUrl={fullWebhookUrl} />
            </TabsContent>

            <TabsContent value="examples" className="mt-6">
              <CodeExamples webhookUrl={fullWebhookUrl} variables={workflow.variables} />
            </TabsContent>

            <TabsContent value="playground" className="mt-6">
              <ApiPlayground webhookUrl={webhookUrl} variables={workflow.variables} />
            </TabsContent>

            <TabsContent value="response" className="mt-6">
              <ResponseSchema />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  )
}

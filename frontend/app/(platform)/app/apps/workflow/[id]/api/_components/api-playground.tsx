'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Send, Loader2, AlertCircle, CheckCircle, XCircle, Clock, ExternalLink, ArrowRight, SkipForward } from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { type VariableDefinition } from '@/lib/api/workflows'

interface ApiPlaygroundProps {
  webhookUrl: string
  variables: VariableDefinition[]
}

interface WorkflowEventData {
  data?: {
    duration_ms?: number
    outputs?: unknown
    error?: string
    node_label?: string
    node_type?: string
  }
  node_id?: string
  event?: string
  [key: string]: unknown
}

interface WorkflowEvent {
  type: 'workflow_start' | 'workflow_complete' | 'workflow_error' | 'node_start' | 'node_complete' | 'node_error' | 'node_skip' | 'token' | 'output'
  data?: WorkflowEventData
  timestamp: number
}

export function ApiPlayground({ webhookUrl, variables }: ApiPlaygroundProps) {
  const t = useTranslations('workflow')
  const [apiKey, setApiKey] = React.useState('')
  const [input, setInput] = React.useState('')
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [runId, setRunId] = React.useState<string | null>(null)
  const [events, setEvents] = React.useState<WorkflowEvent[]>([])
  const [status, setStatus] = React.useState<'idle' | 'running' | 'completed' | 'failed'>('idle')
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const statusRef = React.useRef<'idle' | 'running' | 'completed' | 'failed'>('idle')

  // Keep statusRef in sync with status
  React.useEffect(() => {
    statusRef.current = status
  }, [status])

  // Initialize with example input
  React.useEffect(() => {
    if (!variables || variables.length === 0) {
      setInput('{}')
      return
    }

    const example: Record<string, unknown> = {}
    variables.forEach((variable) => {
      switch (variable.type) {
        case 'text':
          example[variable.name] = 'example text'
          break
        case 'number':
          example[variable.name] = 42
          break
        case 'boolean':
          example[variable.name] = true
          break
        case 'array':
          example[variable.name] = ['item1', 'item2']
          break
        case 'object':
          example[variable.name] = { key: 'value' }
          break
        default:
          example[variable.name] = 'value'
      }
    })

    setInput(JSON.stringify(example, null, 2))
  }, [variables])

  // Auto scroll to bottom
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events])

  const handleTest = async () => {
    setLoading(true)
    setError(null)
    setEvents([])
    setRunId(null)
    setStatus('idle')

    try {
      // Validate JSON
      let parsedInput
      try {
        parsedInput = JSON.parse(input)
      } catch {
        throw new Error('Invalid JSON format')
      }

      // Trigger workflow
      const response = await fetch(webhookUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${apiKey}`,
        },
        body: JSON.stringify(parsedInput),
      })

      // Check if response is JSON
      const contentType = response.headers.get('content-type')
      if (!contentType || !contentType.includes('application/json')) {
        await response.text()
        throw new Error(`Server returned non-JSON response (${response.status})`)
      }

      const result = await response.json()

      if (!response.ok) {
        throw new Error(result.msg || 'Request failed')
      }

      // Extract run_id and start SSE connection
      const workflowRunId = result.data?.run_id
      if (!workflowRunId) {
        throw new Error('No run_id returned from server')
      }

      setRunId(workflowRunId)
      setStatus('running')

      // Add initial event
      setEvents([{
        type: 'workflow_start',
        data: { run_id: workflowRunId },
        timestamp: Date.now()
      }])

      // Connect to SSE stream - use direct backend URL for SSE
      const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
      const streamUrl = `${apiBaseUrl.replace('/api/v1', '')}/api/v1/workflows/runs/${workflowRunId}/stream`
      const eventSource = new EventSource(streamUrl)

      // Flag to track if workflow completed normally
      let workflowCompleted = false

      // Handler for all SSE events
      const handleEvent = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)

          console.log('SSE event received:', data.event, data)

          setEvents(prev => [...prev, {
            type: data.event || 'output',
            data: data,
            timestamp: Date.now()
          }])

          // Update status based on events
          if (data.event === 'workflow_complete') {
            console.log('Workflow completed, setting flag')
            workflowCompleted = true
            setStatus('completed')
            eventSource.close()
            setLoading(false)
          } else if (data.event === 'workflow_error') {
            console.log('Workflow error')
            setStatus('failed')
            setError(data.data?.error || 'Workflow execution failed')
            eventSource.close()
            setLoading(false)
          }
        } catch (err) {
          console.error('Failed to parse SSE event:', err)
        }
      }

      // Listen to all event types
      eventSource.addEventListener('workflow_start', handleEvent)
      eventSource.addEventListener('workflow_complete', handleEvent)
      eventSource.addEventListener('workflow_error', handleEvent)
      eventSource.addEventListener('node_start', handleEvent)
      eventSource.addEventListener('node_complete', handleEvent)
      eventSource.addEventListener('node_error', handleEvent)
      eventSource.addEventListener('node_skip', handleEvent)
      eventSource.addEventListener('token', handleEvent)
      eventSource.addEventListener('output', handleEvent)

      // Also listen to default message event (for events without explicit type)
      eventSource.onmessage = handleEvent

      eventSource.onerror = (err) => {
        console.log('SSE onerror triggered, workflowCompleted:', workflowCompleted)
        console.error('SSE error:', err)
        eventSource.close()

        // Only show error if workflow didn't complete normally
        if (!workflowCompleted) {
          console.log('Showing error because workflow did not complete')
          setLoading(false)
          setStatus('failed')
          setError('Connection to workflow stream lost')
        } else {
          console.log('Workflow completed normally, not showing error')
          // Normal completion, just stop loading
          setLoading(false)
        }
      }

    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Unknown error occurred'
      setError(errorMessage)
      setStatus('failed')
      setLoading(false)
    }
  }

  const getStatusIcon = () => {
    switch (status) {
      case 'running':
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />
      default:
        return <Clock className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getStatusText = () => {
    switch (status) {
      case 'running':
        return t('running')
      case 'completed':
        return t('completed')
      case 'failed':
        return t('failed')
      default:
        return t('idle')
    }
  }

  const renderEvent = (event: WorkflowEvent, index: number) => {
    const { type, data, timestamp } = event
    const time = new Date(timestamp).toLocaleTimeString()

    switch (type) {
      case 'workflow_start':
        return (
          <div key={index} className="flex items-start gap-2 text-sm">
            <Badge variant="outline" className="shrink-0">{time}</Badge>
            <div className="flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
              <span className="text-blue-600 font-medium">{t('apiPlayground.workflowStarted')}</span>
            </div>
          </div>
        )

      case 'workflow_complete':
        return (
          <div key={index} className="flex flex-col gap-2 text-sm">
            <div className="flex items-start gap-2">
              <Badge variant="outline" className="shrink-0">{time}</Badge>
              <div className="flex items-center gap-2">
                <CheckCircle className="h-3 w-3 text-green-500" />
                <span className="text-green-600 font-medium">{t('apiPlayground.workflowCompleted')}</span>
                {data?.data?.duration_ms && (
                  <span className="text-xs text-muted-foreground">
                    ({data.data.duration_ms}ms)
                  </span>
                )}
              </div>
            </div>
            {data?.data?.outputs !== undefined && (
              <pre className="ml-20 text-xs bg-muted p-2 rounded overflow-x-auto">
                {JSON.stringify(data.data.outputs, null, 2)}
              </pre>
            )}
          </div>
        )

      case 'workflow_error':
        return (
          <div key={index} className="flex items-start gap-2 text-sm">
            <Badge variant="outline" className="shrink-0">{time}</Badge>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <XCircle className="h-3 w-3 text-red-500" />
                <span className="text-red-600 font-medium">{t('apiPlayground.workflowFailed')}</span>
              </div>
              {data?.data?.error && (
                <div className="ml-5 text-xs text-red-600">{data.data.error}</div>
              )}
            </div>
          </div>
        )

      case 'node_start':
        return (
          <div key={index} className="flex items-start gap-2 text-sm ml-4">
            <Badge variant="outline" className="shrink-0 text-xs">{time}</Badge>
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-blue-500" />
              <span className="text-muted-foreground text-xs">
                {data?.data?.node_label || data?.node_id}
                <span className="text-muted-foreground/60 ml-1">({data?.data?.node_type})</span>
              </span>
            </div>
          </div>
        )

      case 'node_complete':
        return (
          <div key={index} className="flex items-start gap-2 text-sm ml-4">
            <Badge variant="outline" className="shrink-0 text-xs">{time}</Badge>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-500" />
              <span className="text-muted-foreground text-xs">
                {data?.data?.node_label || data?.node_id}
                {data?.data?.duration_ms && (
                  <span className="text-muted-foreground/60 ml-1">
                    ({data.data.duration_ms}ms)
                  </span>
                )}
              </span>
            </div>
          </div>
        )

      case 'node_error':
        return (
          <div key={index} className="flex items-start gap-2 text-sm ml-4">
            <Badge variant="outline" className="shrink-0 text-xs">{time}</Badge>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <XCircle className="h-3 w-3 text-red-500" />
                <span className="text-red-600 text-xs">{data?.data?.node_label || data?.node_id}</span>
              </div>
              {data?.data?.error && (
                <div className="ml-5 text-xs text-red-600">{data.data.error}</div>
              )}
            </div>
          </div>
        )

      case 'node_skip':
        return (
          <div key={index} className="flex items-start gap-2 text-sm ml-4">
            <Badge variant="outline" className="shrink-0 text-xs">{time}</Badge>
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <SkipForward className="h-3 w-3 text-amber-500" />
                <span className="text-amber-700 text-xs">
                  {data?.data?.node_label || data?.node_id}
                </span>
              </div>
              {data?.data?.reason && (
                <div className="ml-5 text-xs text-muted-foreground">{t('apiPlayground.nodeSkipped', { reason: String(data.data.reason) })}</div>
              )}
            </div>
          </div>
        )

      case 'output':
        return (
          <div key={index} className="flex flex-col gap-2 text-sm ml-4">
            <div className="flex items-start gap-2">
              <Badge variant="outline" className="shrink-0 text-xs">{time}</Badge>
              <div className="flex items-center gap-2">
                <ArrowRight className="h-3 w-3 text-primary" />
                <span className="text-primary text-xs">{t('apiPlayground.nodeOutput')}</span>
                <span className="text-muted-foreground text-xs">
                  {data?.node_id || '-'}
                </span>
              </div>
            </div>
            {data?.data?.output !== undefined && (
              <pre className="ml-16 text-xs bg-muted p-2 rounded overflow-x-auto">
                {JSON.stringify(data.data.output, null, 2)}
              </pre>
            )}
          </div>
        )

      case 'token':
        return null // Skip token events for cleaner display

      default:
        return null
    }
  }

  return (
    <div className="space-y-6">
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>{t('playgroundDescription')}</AlertDescription>
      </Alert>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Request */}
        <Card>
          <CardHeader>
            <CardTitle>{t('requestBody')}</CardTitle>
            <CardDescription>{t('requestBodyDescription')}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="api-key">{t('apiKey')}</Label>
                <Link href="/api-keys">
                  <Button variant="ghost" size="sm" className="h-auto p-0 text-xs">
                    <ExternalLink className="mr-1 h-3 w-3" />
                    {t('manageApiKeys')}
                  </Button>
                </Link>
              </div>
              <Input
                id="api-key"
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="clou_xxxxxxxxxxxxx"
                disabled={loading}
              />
              <p className="text-xs text-muted-foreground">
                {t('apiKeyRequired')}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="request-body">{t('requestBody')}</Label>
              <Textarea
                id="request-body"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="{}"
                className="min-h-[200px] font-mono text-sm"
                disabled={loading}
              />
            </div>
            <Button onClick={handleTest} disabled={loading || !apiKey} className="w-full">
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t('sending')}
                </>
              ) : (
                <>
                  <Send className="mr-2 h-4 w-4" />
                  {t('sendRequest')}
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Response - Real-time Events */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>{t('executionLog')}</CardTitle>
                <CardDescription>{t('executionLogDescription')}</CardDescription>
              </div>
              <div className="flex items-center gap-2">
                {getStatusIcon()}
                <span className="text-sm font-medium">{getStatusText()}</span>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {error && (
              <Alert variant="destructive" className="mb-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {runId && (
              <Alert className="mb-4">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>
                  <div className="space-y-1">
                    <p className="text-xs font-medium">Run ID: {runId}</p>
                  </div>
                </AlertDescription>
              </Alert>
            )}

            <ScrollArea className="h-[300px] w-full rounded-lg border bg-muted/50 p-4">
              <div ref={scrollRef}>
                {events.length === 0 ? (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    {t('noEventsYet')}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {events.map((event, index) => renderEvent(event, index))}
                  </div>
                )}
              </div>
            </ScrollArea>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

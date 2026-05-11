'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Check, AlertCircle, ExternalLink } from 'lucide-react'
import Link from 'next/link'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { type Workflow, type VariableDefinition } from '@/lib/api/workflows'

interface ApiOverviewProps {
  workflow: Workflow
  webhookUrl: string
}

export function ApiOverview({ workflow, webhookUrl }: ApiOverviewProps) {
  const t = useTranslations('workflow')
  const [copied, setCopied] = React.useState(false)

  const handleCopy = async () => {
    if (!webhookUrl) return
    await navigator.clipboard.writeText(webhookUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!workflow.webhook_token) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          {t('webhookNotConfigured')}
        </AlertDescription>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      {/* Webhook URL */}
      <Card>
        <CardHeader>
          <CardTitle>{t('webhookUrl')}</CardTitle>
          <CardDescription>{t('webhookUrlDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Badge variant="secondary">POST</Badge>
            <code className="flex-1 rounded bg-muted px-3 py-2 text-sm font-mono">
              {webhookUrl}
            </code>
            <Button
              variant="outline"
              size="icon"
              onClick={handleCopy}
              className="shrink-0"
            >
              {copied ? (
                <Check className="h-4 w-4 text-green-600" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Authentication */}
      <Card>
        <CardHeader>
          <CardTitle>{t('authentication')}</CardTitle>
          <CardDescription>{t('authenticationDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-2">{t('authenticationRequired')}</p>
            <p className="text-sm text-muted-foreground mb-4">
              {t('authenticationRequiredDescription')}
            </p>
            <div className="rounded-lg bg-muted p-4">
              <p className="text-xs text-muted-foreground mb-2">{t('api.authorizationHeader')}</p>
              <code className="text-sm font-mono">
                Authorization: Bearer clou_your_api_key_here
              </code>
            </div>
          </div>
          <Alert>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="flex items-center justify-between gap-2">
              <span className="text-sm flex-1">{t('apiKeyHint')}</span>
              <Link href="/api-keys" className="shrink-0">
                <Button variant="outline" size="sm">
                  <ExternalLink className="mr-2 h-4 w-4" />
                  {t('manageApiKeys')}
                </Button>
              </Link>
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>

      {/* Input Parameters */}
      {workflow.variables && workflow.variables.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>{t('inputParameters')}</CardTitle>
            <CardDescription>{t('inputParametersDescription')}</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t('parameter')}</TableHead>
                  <TableHead>{t('type')}</TableHead>
                  <TableHead>{t('required')}</TableHead>
                  <TableHead>{t('description')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {workflow.variables.map((variable: VariableDefinition, index: number) => (
                  <TableRow key={`${variable.name}-${index}`}>
                    <TableCell className="font-mono text-sm">
                      {variable.name}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{variable.type}</Badge>
                    </TableCell>
                    <TableCell>
                      {variable.required ? (
                        <Badge variant="destructive" className="text-xs">
                          {t('required')}
                        </Badge>
                      ) : (
                        <Badge variant="secondary" className="text-xs">
                          {t('optional')}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {variable.description || '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Response Format */}
      <Card>
        <CardHeader>
          <CardTitle>{t('responseFormat')}</CardTitle>
          <CardDescription>{t('responseFormatDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium mb-2">{t('initialResponse')}</p>
            <pre className="text-xs bg-muted p-4 rounded-md overflow-x-auto">
{`{
  "code": 0,
  "data": {
    "run_id": "uuid",
    "status": "pending",
    "stream_url": "/api/v1/workflows/runs/{run_id}/stream"
  },
  "msg": "workflow_triggered"
}`}
            </pre>
          </div>

          <div>
            <p className="text-sm font-medium mb-2">{t('sseStreamEvents')}</p>
            <p className="text-sm text-muted-foreground mb-3">{t('sseStreamDescription')}</p>

            <div className="space-y-3">
              <div>
                <Badge variant="outline" className="mb-2">workflow_start</Badge>
                <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
{`event: workflow_start
data: {
  "event": "workflow_start",
  "run_id": "uuid",
  "timestamp": 1234567890
}`}
                </pre>
              </div>

              <div>
                <Badge variant="outline" className="mb-2">node_start</Badge>
                <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
{`event: node_start
data: {
  "event": "node_start",
  "node_id": "node-1",
  "data": {
    "node_type": "llm",
    "node_label": "LLM Node"
  }
}`}
                </pre>
              </div>

              <div>
                <Badge variant="outline" className="mb-2">node_complete</Badge>
                <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
{`event: node_complete
data: {
  "event": "node_complete",
  "node_id": "node-1",
  "data": {
    "node_type": "llm",
    "node_label": "LLM Node",
    "duration_ms": 1500,
    "outputs": { "response": "..." }
  }
}`}
                </pre>
              </div>

              <div>
                <Badge variant="outline" className="mb-2">workflow_complete</Badge>
                <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
{`event: workflow_complete
data: {
  "event": "workflow_complete",
  "run_id": "uuid",
  "data": {
    "duration_ms": 5000,
    "outputs": { "result": "..." }
  }
}`}
                </pre>
              </div>

              <div>
                <Badge variant="destructive" className="mb-2">workflow_error</Badge>
                <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto">
{`event: workflow_error
data: {
  "event": "workflow_error",
  "run_id": "uuid",
  "data": {
    "error": "Error message",
    "node_id": "node-1"
  }
}`}
                </pre>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Important Notes */}
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          <div className="space-y-2">
            <p className="font-medium">{t('importantNotes')}</p>
            <ul className="list-inside list-disc space-y-1 text-sm">
              <li>{t('webhookNote1')}</li>
              <li>{t('webhookNote2')}</li>
              <li>{t('webhookNote3')}</li>
            </ul>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  )
}

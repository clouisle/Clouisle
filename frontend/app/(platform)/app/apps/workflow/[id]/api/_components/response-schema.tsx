'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function ResponseSchema() {
  const t = useTranslations('workflow')

  const successExample = {
    code: 0,
    data: {
      run_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
      status: 'pending',
      stream_url: '/api/v1/workflows/runs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/stream',
    },
    msg: 'workflow_triggered',
  }

  const errorExamples = [
    {
      title: t('invalidToken'),
      code: 403,
      response: {
        code: 403,
        data: null,
        msg: 'invalid_webhook_token',
      },
    },
    {
      title: t('workflowNotPublished'),
      code: 403,
      response: {
        code: 403,
        data: null,
        msg: 'workflow_not_published',
      },
    },
    {
      title: t('webhookDisabled'),
      code: 403,
      response: {
        code: 403,
        data: null,
        msg: 'webhook_trigger_disabled',
      },
    },
    {
      title: t('internalError'),
      code: 500,
      response: {
        code: 500,
        data: null,
        msg: 'workflow_execution_error',
      },
    },
  ]

  const statusCodes = [
    {
      code: 200,
      description: t('statusCode200'),
    },
    {
      code: 403,
      description: t('statusCode403'),
    },
    {
      code: 500,
      description: t('statusCode500'),
    },
  ]

  const responseFields = [
    {
      field: 'code',
      type: 'number',
      description: t('fieldCode'),
    },
    {
      field: 'data',
      type: 'object | null',
      description: t('fieldData'),
    },
    {
      field: 'data.run_id',
      type: 'string',
      description: t('fieldRunId'),
    },
    {
      field: 'data.status',
      type: 'string',
      description: t('fieldStatus'),
    },
    {
      field: 'data.stream_url',
      type: 'string',
      description: t('fieldStreamUrl'),
    },
    {
      field: 'msg',
      type: 'string',
      description: t('fieldMsg'),
    },
  ]

  return (
    <div className="space-y-6">
      {/* Success Response */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle>{t('successResponse')}</CardTitle>
            <Badge variant="default">200 OK</Badge>
          </div>
          <CardDescription>{t('successResponseDescription')}</CardDescription>
        </CardHeader>
        <CardContent>
          <pre className="overflow-x-auto rounded-lg bg-muted p-4">
            <code className="text-sm font-mono">
              {JSON.stringify(successExample, null, 2)}
            </code>
          </pre>
        </CardContent>
      </Card>

      {/* Error Responses */}
      <Card>
        <CardHeader>
          <CardTitle>{t('errorResponses')}</CardTitle>
          <CardDescription>{t('errorResponsesDescription')}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {errorExamples.map((example, index) => (
            <div key={index} className="space-y-2">
              <div className="flex items-center gap-2">
                <Badge variant="destructive">{example.code}</Badge>
                <span className="text-sm font-medium">{example.title}</span>
              </div>
              <pre className="overflow-x-auto rounded-lg bg-muted p-4">
                <code className="text-sm font-mono">
                  {JSON.stringify(example.response, null, 2)}
                </code>
              </pre>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Status Codes */}
      <Card>
        <CardHeader>
          <CardTitle>{t('statusCodes')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('code')}</TableHead>
                <TableHead>{t('description')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {statusCodes.map((status) => (
                <TableRow key={status.code}>
                  <TableCell>
                    <Badge
                      variant={
                        status.code === 200
                          ? 'default'
                          : status.code === 403
                            ? 'secondary'
                            : 'destructive'
                      }
                    >
                      {status.code}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{status.description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Response Fields */}
      <Card>
        <CardHeader>
          <CardTitle>{t('responseFields')}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('field')}</TableHead>
                <TableHead>{t('type')}</TableHead>
                <TableHead>{t('description')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {responseFields.map((field) => (
                <TableRow key={field.field}>
                  <TableCell className="font-mono text-sm">{field.field}</TableCell>
                  <TableCell>
                    <Badge variant="outline">{field.type}</Badge>
                  </TableCell>
                  <TableCell className="text-sm">{field.description}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

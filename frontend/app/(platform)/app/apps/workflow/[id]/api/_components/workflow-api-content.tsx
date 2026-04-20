'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Copy, Check, ExternalLink, Key, AlertCircle } from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import type { Workflow } from '@/lib/api/workflows'

interface WorkflowApiContentProps {
  workflow: Workflow
}

// Code block with copy button
function CodeBlock({
  code,
  language = 'bash',
  className,
}: {
  code: string
  language?: string
  className?: string
}) {
  const [copied, setCopied] = React.useState(false)
  const t = useTranslations('common')

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code)
    setCopied(true)
    toast.success(t('copiedToClipboard'))
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={cn("relative group", className)}>
      <pre className="bg-muted rounded-lg p-4 overflow-x-auto text-sm">
        <code className={`language-${language}`}>{code}</code>
      </pre>
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-2 right-2 h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={handleCopy}
      >
        {copied ? (
          <Check className="h-4 w-4 text-green-500" />
        ) : (
          <Copy className="h-4 w-4" />
        )}
      </Button>
    </div>
  )
}

// Section component
function Section({
  title,
  children,
  className,
}: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={cn("space-y-3", className)}>
      <h3 className="text-lg font-semibold">{title}</h3>
      {children}
    </section>
  )
}

export function WorkflowApiContent({ workflow }: WorkflowApiContentProps) {
  const t = useTranslations('workflow.api')

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

  const sampleInputs = workflow.variables?.reduce((acc, v) => ({
    ...acc,
    [v.name]: v.type === 'number' ? 0 : ""
  }), {}) || {}

  // API endpoint
  const webhookUrl = workflow.webhook_token
    ? `${apiBaseUrl}/api/v1/workflows/webhook/${workflow.webhook_token}`
    : ''

  // Sample request body
  const sampleRequestBody = JSON.stringify(sampleInputs, null, 2)

  // Sample cURL command
  const curlCommand = webhookUrl ? `curl -X POST "${webhookUrl}" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify(sampleInputs)}'` : ''

  // Sample Python code
  const pythonCode = webhookUrl ? `import requests

API_KEY = "YOUR_API_KEY"  # API key starting with clou_

url = "${webhookUrl}"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}
data = ${JSON.stringify(sampleInputs, null, 2)}

response = requests.post(url, headers=headers, json=data)
result = response.json()

# Get run_id and stream_url from response
if result["code"] == 0:
    run_id = result["data"]["run_id"]
    stream_url = result["data"]["stream_url"]
    print(f"Workflow triggered: {run_id}")
    print(f"Stream URL: {stream_url}")
else:
    print(f"Error: {result['msg']}")` : ''

  // Sample JavaScript code
  const javascriptCode = webhookUrl ? `const API_KEY = "YOUR_API_KEY"; // API key starting with clou_

const response = await fetch(
  "${webhookUrl}",
  {
    method: "POST",
    headers: {
      "Authorization": \`Bearer \${API_KEY}\`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(${JSON.stringify(sampleInputs, null, 2)}),
  }
);

const result = await response.json();

// Get run_id and stream_url from response
if (result.code === 0) {
  const { run_id, stream_url } = result.data;
  console.log(\`Workflow triggered: \${run_id}\`);
  console.log(\`Stream URL: \${stream_url}\`);
} else {
  console.error(\`Error: \${result.msg}\`);
}` : ''

  return (
    <div className="mx-auto max-w-4xl px-6 pb-20">
      <div className="space-y-12">
        {/* Workflow Status Alert */}
        {!workflow.webhook_token && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>{t('noWebhookTitle')}</AlertTitle>
            <AlertDescription>{t('noWebhookDescription')}</AlertDescription>
          </Alert>
        )}

        {workflow.webhook_token && (
          <>
            {/* Endpoint Info */}
            <Section title={t('endpoint')}>
              <div className="flex items-center gap-2 mb-2">
                <Badge variant="secondary">POST</Badge>
                <code className="text-sm bg-muted px-2 py-1 rounded break-all">{webhookUrl}</code>
              </div>
              <p className="text-sm text-muted-foreground">{t('endpointDescription')}</p>
            </Section>

            {/* Authentication */}
            <Section title={t('authentication')}>
              <div className="flex items-start justify-between gap-4 mb-3">
                <p className="text-sm text-muted-foreground flex-1">{t('authDescription')}</p>
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => window.open('/app/api-keys', '_blank')}
                >
                  <Key className="h-4 w-4 mr-2" />
                  {t('manageApiKeys')}
                  <ExternalLink className="h-3 w-3 ml-2" />
                </Button>
              </div>
              <CodeBlock
                code={`Authorization: Bearer YOUR_API_KEY`}
                language="http"
              />
              <Alert className="mt-3">
                <Key className="h-4 w-4" />
                <AlertDescription className="text-sm">
                  {t('authNote')}
                </AlertDescription>
              </Alert>
            </Section>

            {/* Request Body */}
            <Section title={t('requestBody')}>
              <div className="space-y-4">
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="text-sm">
                    {t('requestBodyTopLevelNote')}{' '}
                    <code className="rounded bg-muted px-1 py-0.5 text-xs">
                      {`{"query": {...}}`}
                    </code>
                  </AlertDescription>
                </Alert>

                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-2 font-medium">{t('parameter')}</th>
                        <th className="text-left px-4 py-2 font-medium">{t('type')}</th>
                        <th className="text-left px-4 py-2 font-medium">{t('required')}</th>
                        <th className="text-left px-4 py-2 font-medium">{t('paramDescription')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-t">
                        <td className="px-4 py-2"><code>{'{root}'}</code></td>
                        <td className="px-4 py-2">object</td>
                        <td className="px-4 py-2">{t('yes')}</td>
                        <td className="px-4 py-2 text-muted-foreground">{t('inputsDescription')}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {workflow.variables && workflow.variables.length > 0 ? (
                  <>
                    <p className="text-sm font-medium">{t('inputParameters')}:</p>
                    <div className="border rounded-lg overflow-hidden">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                          <tr>
                            <th className="text-left px-4 py-2 font-medium">{t('parameter')}</th>
                            <th className="text-left px-4 py-2 font-medium">{t('type')}</th>
                            <th className="text-left px-4 py-2 font-medium">{t('required')}</th>
                            <th className="text-left px-4 py-2 font-medium">{t('paramDescription')}</th>
                          </tr>
                        </thead>
                        <tbody>
                          {workflow.variables.map((variable) => (
                            <tr key={variable.name} className="border-t">
                              <td className="px-4 py-2"><code>{variable.name}</code></td>
                              <td className="px-4 py-2">{variable.type}</td>
                              <td className="px-4 py-2">{variable.required ? t('yes') : t('no')}</td>
                              <td className="px-4 py-2 text-muted-foreground">{variable.description || '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <CodeBlock code={sampleRequestBody} language="json" />
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">{t('noVariables')}</p>
                )}
              </div>
            </Section>

            {/* Response Format */}
            <Section title={t('responseFormat')}>
              <p className="text-sm text-muted-foreground mb-3">{t('responseDescription')}</p>
              <div className="space-y-4">
                <div>
                  <p className="text-sm font-medium mb-2">{t('successResponse')}:</p>
                  <CodeBlock
                    code={JSON.stringify({
                      code: 0,
                      data: {
                        run_id: "550e8400-e29b-41d4-a716-446655440000",
                        status: "pending",
                        stream_url: "/api/v1/workflows/runs/{run_id}/stream"
                      },
                      msg: "workflow_triggered"
                    }, null, 2)}
                    language="json"
                  />
                </div>

                <div className="border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-2 font-medium">{t('field')}</th>
                        <th className="text-left px-4 py-2 font-medium">{t('paramDescription')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr className="border-t">
                        <td className="px-4 py-2"><code>code</code></td>
                        <td className="px-4 py-2 text-muted-foreground">{t('codeDescription')}</td>
                      </tr>
                      <tr className="border-t">
                        <td className="px-4 py-2"><code>data.run_id</code></td>
                        <td className="px-4 py-2 text-muted-foreground">{t('runIdDescription')}</td>
                      </tr>
                      <tr className="border-t">
                        <td className="px-4 py-2"><code>data.status</code></td>
                        <td className="px-4 py-2 text-muted-foreground">{t('statusDescription')}</td>
                      </tr>
                      <tr className="border-t">
                        <td className="px-4 py-2"><code>data.stream_url</code></td>
                        <td className="px-4 py-2 text-muted-foreground">{t('streamUrlDescription')}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('errorResponse')}:</p>
                  <CodeBlock
                    code={JSON.stringify({
                      code: 2001,
                      data: null,
                      msg: "api_key_required"
                    }, null, 2)}
                    language="json"
                  />
                </div>
              </div>
            </Section>

            {/* Code Examples */}
            <Section title={t('codeExamples')}>
              <Tabs defaultValue="curl" className="w-full">
                <TabsList>
                  <TabsTrigger value="curl">{t('tabs.curl')}</TabsTrigger>
                  <TabsTrigger value="python">{t('tabs.python')}</TabsTrigger>
                  <TabsTrigger value="javascript">{t('tabs.javascript')}</TabsTrigger>
                </TabsList>
                <TabsContent value="curl" className="mt-4">
                  <CodeBlock code={curlCommand} language="bash" />
                </TabsContent>
                <TabsContent value="python" className="mt-4">
                  <CodeBlock code={pythonCode} language="python" />
                </TabsContent>
                <TabsContent value="javascript" className="mt-4">
                  <CodeBlock code={javascriptCode} language="javascript" />
                </TabsContent>
              </Tabs>
            </Section>

            {/* SSE Stream */}
            <div className="pt-8 border-t">
              <Section title={t('sseStream')}>
                <p className="text-sm text-muted-foreground mb-3">{t('sseStreamDescription')}</p>

              <div className="space-y-4">
                <div>
                  <p className="text-sm font-medium mb-2">{t('streamEndpoint')}:</p>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="secondary">GET</Badge>
                    <code className="text-sm bg-muted px-2 py-1 rounded break-all">
                      {apiBaseUrl}/api/v1/workflows/runs/{'{run_id}'}/stream
                    </code>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('queryParameters')}:</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-4 py-2 font-medium">{t('parameter')}</th>
                          <th className="text-left px-4 py-2 font-medium">{t('type')}</th>
                          <th className="text-left px-4 py-2 font-medium">{t('required')}</th>
                          <th className="text-left px-4 py-2 font-medium">{t('paramDescription')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>from_sequence</code></td>
                          <td className="px-4 py-2">integer</td>
                          <td className="px-4 py-2">{t('no')}</td>
                          <td className="px-4 py-2 text-muted-foreground">{t('fromSequenceDescription')}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('eventTypes')}:</p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50">
                        <tr>
                          <th className="text-left px-4 py-2 font-medium">{t('event')}</th>
                          <th className="text-left px-4 py-2 font-medium">{t('paramDescription')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>workflow_start</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventWorkflowStart')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>workflow_complete</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventWorkflowComplete')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>workflow_error</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventWorkflowError')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>node_start</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventNodeStart')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>node_complete</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventNodeComplete')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>node_error</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventNodeError')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>node_skip</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventNodeSkip')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>token</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventToken')}</td>
                        </tr>
                        <tr className="border-t">
                          <td className="px-4 py-2"><code>output</code></td>
                          <td className="px-4 py-2 text-muted-foreground">{t('eventOutput')}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('eventFormat')}:</p>
                  <CodeBlock
                    code={`event: workflow_start
data: {"event":"workflow_start","data":{"workflow_id":"...","workflow_name":"...","inputs":{}},"node_id":null,"timestamp":"2026-03-06T10:00:00","sequence":1}

event: node_start
data: {"event":"node_start","data":{"node_type":"llm","node_label":"LLM Node","is_streaming":true},"node_id":"node_123","timestamp":"2026-03-06T10:00:01","sequence":2}

event: token
data: {"event":"token","data":{"token":"Hello"},"node_id":"node_123","timestamp":"2026-03-06T10:00:02","sequence":3}

event: node_complete
data: {"event":"node_complete","data":{"outputs":{"result":"Hello World"},"duration_ms":1500},"node_id":"node_123","timestamp":"2026-03-06T10:00:03","sequence":4}

event: workflow_complete
data: {"event":"workflow_complete","data":{"outputs":{"result":"Hello World"},"duration_ms":3000},"node_id":null,"timestamp":"2026-03-06T10:00:04","sequence":5}`}
                    language="text"
                  />
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('pythonStreamExample')}:</p>
                  <CodeBlock
                    code={`import requests

# After triggering workflow
run_id = result["data"]["run_id"]
stream_url = f"${apiBaseUrl}/api/v1/workflows/runs/{run_id}/stream"

# Connect to SSE stream
response = requests.get(stream_url, stream=True, headers={
    "Accept": "text/event-stream"
})

current_event = None
for line in response.iter_lines():
    if not line:
        continue

    line = line.decode('utf-8')

    if line.startswith('event: '):
        current_event = line[7:]
    elif line.startswith('data: '):
        import json
        data = json.loads(line[6:])
        print(f"Event: {current_event}")
        print(f"Data: {data}")

        # Check for completion
        if current_event in ['workflow_complete', 'workflow_error']:
            break`}
                    language="python"
                  />
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">{t('javascriptStreamExample')}:</p>
                  <CodeBlock
                    code={`// After triggering workflow
const { run_id } = result.data;
const streamUrl = \`${apiBaseUrl}/api/v1/workflows/runs/\${run_id}/stream\`;

// Connect to SSE stream
const eventSource = new EventSource(streamUrl);

// Listen to specific events
eventSource.addEventListener('workflow_start', (e) => {
  const data = JSON.parse(e.data);
  console.log('Workflow started:', data);
});

eventSource.addEventListener('token', (e) => {
  const data = JSON.parse(e.data);
  console.log('Token:', data.data.token);
});

eventSource.addEventListener('node_complete', (e) => {
  const data = JSON.parse(e.data);
  console.log('Node completed:', data);
});

eventSource.addEventListener('workflow_complete', (e) => {
  const data = JSON.parse(e.data);
  console.log('Workflow completed:', data);
  eventSource.close();
});

eventSource.addEventListener('workflow_error', (e) => {
  const data = JSON.parse(e.data);
  console.error('Workflow error:', data);
  eventSource.close();
});

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
  eventSource.close();
};`}
                    language="javascript"
                  />
                </div>
              </div>
            </Section>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

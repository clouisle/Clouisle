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
import type { Agent } from '@/lib/api'
import { PermissionGuard } from '@/components/permission-guard'

interface ApiAccessContentProps {
  agent: Agent
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

export function ApiAccessContent({ agent }: ApiAccessContentProps) {
  const t = useTranslations('agents.apiAccess')
  
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
  
  // API endpoint
  const chatEndpoint = `${apiBaseUrl}/api/v1/agents/${agent.id}/chat/stream`
  
  // Sample request body
  const sampleRequestBody = JSON.stringify({
    message: "Hello, how can you help me?",
    conversation_id: null,
    variables: {},
    images: [],
    file_urls: [],
  }, null, 2)

  // Sample cURL command
  const curlCommand = `curl -X POST "${chatEndpoint}" \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -H "Accept: text/event-stream" \\
  -d '${JSON.stringify({
    message: "Hello, how can you help me?",
    conversation_id: null,
    variables: {},
    images: [],
    file_urls: [],
  })}'`

  // Sample Python code
  const pythonCode = `import requests

API_KEY = "YOUR_API_KEY"
AGENT_ID = "${agent.id}"

url = f"${apiBaseUrl}/api/v1/agents/{AGENT_ID}/chat/stream"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}
data = {
    "message": "Hello, how can you help me?",
    "conversation_id": None,
    "variables": {},
    "images": [],
    "file_urls": [],
}

response = requests.post(url, headers=headers, json=data, stream=True)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            print(line[6:])`

  // Sample JavaScript code
  const javascriptCode = `const API_KEY = "YOUR_API_KEY";
const AGENT_ID = "${agent.id}";

const response = await fetch(
  \`${apiBaseUrl}/api/v1/agents/\${AGENT_ID}/chat/stream\`,
  {
    method: "POST",
    headers: {
      "Authorization": \`Bearer \${API_KEY}\`,
      "Content-Type": "application/json",
      "Accept": "text/event-stream",
    },
    body: JSON.stringify({
      message: "Hello, how can you help me?",
      conversation_id: null,
      variables: {},
      images: [],
      file_urls: [],
    }),
  }
);

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  const lines = text.split("\\n");

  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const data = JSON.parse(line.slice(6));
      // Replace this with your own UI state update.
      console.log("SSE payload:", data);
    }
  }
}`

  // SSE events description
  const sseEvents = [
    { event: 'message_start', description: t('events.messageStart') },
    { event: 'rag_start', description: t('events.ragStart') },
    { event: 'rag_context', description: t('events.ragContext') },
    { event: 'reasoning_start', description: t('events.reasoningStart') },
    { event: 'reasoning_delta', description: t('events.reasoningDelta') },
    { event: 'reasoning_end', description: t('events.reasoningEnd') },
    { event: 'content_delta', description: t('events.contentDelta') },
    { event: 'tool_call', description: t('events.toolCall') },
    { event: 'tool_result', description: t('events.toolResult') },
    { event: 'media_result', description: t('events.mediaResult') },
    { event: 'compression_start', description: t('events.compressionStart') },
    { event: 'compression_end', description: t('events.compressionEnd') },
    { event: 'output_truncated', description: t('events.outputTruncated') },
    { event: 'iteration_cap_reached', description: t('events.iterationCapReached') },
    { event: 'message_end', description: t('events.messageEnd') },
  ]

  // Run lifecycle events
  const runEvents = [
    { event: 'run_start', description: t('events.runStart') },
    { event: 'run_status', description: t('events.runStatus') },
    { event: 'input_accepted', description: t('events.inputAccepted') },
    { event: 'run_end', description: t('events.runEnd') },
  ]

  // Answer endpoint
  const answerEndpoint = `${apiBaseUrl}/api/v1/agents/${agent.id}/chat/runs/{run_id}/answers`

  // Sample answer body
  const sampleAnswerBody = JSON.stringify({
    tool_call_id: "call-123",
    answers: {
      deployment_target: "云端"
    },
    skipped: false,
  }, null, 2)

  // Approval decision endpoints and samples
  const approvalExecutionEndpoint = `${apiBaseUrl}/api/v1/tool-executions/{execution_id}/decision`
  const approvalInboxEndpoint = `${apiBaseUrl}/api/v1/tool-approvals/{request_id}/decision`
  const approvalExecutionReadEndpoint = `${apiBaseUrl}/api/v1/tool-executions/{execution_id}`
  const approvalPendingListEndpoint = `${apiBaseUrl}/api/v1/tool-approvals?page=1&page_size=20`
  const approvalExecutionListEndpoint = `${apiBaseUrl}/api/v1/tool-executions?run_id={run_id}&status=awaiting_approval`
  const approvalStreamEndpoint = `${apiBaseUrl}/api/v1/agents/${agent.id}/chat/runs/{run_id}/stream?after_sequence={sequence}`
  const approvalRunStatusEndpoint = `${apiBaseUrl}/api/v1/agents/${agent.id}/chat/runs/{run_id}`

  const approvalToolCallEvent = `event: tool_call
data: ${JSON.stringify({
    tool_call_id: "call-123",
    tool_name: "mcp_delete_task",
    tool_display_name: "Delete task",
    arguments: { task_id: "T-42" },
  })}`

  const approvalWaitingEvent = `event: run_status
data: ${JSON.stringify({
    status: "waiting",
    pending_tool_call_id: "call-123",
    pending_tool_name: "mcp_delete_task",
    pending_tool_input: {
      interaction_kind: "tool_approval",
      execution_id: "9f1c2a7e-4b8d-4c61-9a30-2f5b8e1d7c44",
    },
  })}`

  const sampleApprovalBody = JSON.stringify({
    decision: "approve",
    reason: "checked the order id",
    idempotency_key: "decision-2026-10-28-0001",
  }, null, 2)

  const sampleApprovalResponse = JSON.stringify({
    code: 0,
    data: {
      decision: {
        id: "9c1f3a52-7d4e-4f18-b2a6-0e5c9d7b1f23",
        request_id: "5a7d2e91-0c3b-4a68-8f14-6b9e2d7c4a10",
        execution_id: "9f1c2a7e-4b8d-4c61-9a30-2f5b8e1d7c44",
        decision: "approve",
        decided_by_id: "0d9e4c61-2b7a-4f35-9c8d-1e6a3b5f7d20",
        reason: "checked the order id",
        created_at: "2026-10-28T12:00:00Z",
      },
      execution_status: "ready",
      remaining_approvals: 0,
    },
    msg: "success",
  }, null, 2)

  const sampleApprovalExecution = JSON.stringify({
    code: 0,
    data: {
      id: "9f1c2a7e-4b8d-4c61-9a30-2f5b8e1d7c44",
      tool_id: "0a6b1f2c-3d4e-4f50-8a91-2b3c4d5e6f70",
      operation: "mcp_delete_task",
      actor_user_id: "0d9e4c61-2b7a-4f35-9c8d-1e6a3b5f7d20",
      entrypoint: "api_key",
      entrypoint_id: "1c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
      run_kind: "agent",
      run_id: "6f5e4d3c-2b1a-4c9d-8e7f-6a5b4c3d2e1f",
      tool_call_id: "call-123",
      parameters_preview: { task_id: "T-42" },
      parameters_digest: "sha256:…",
      policy_hash: "sha256:…",
      status: "awaiting_approval",
      cancel_reason: null,
    },
    msg: "success",
  }, null, 2)

  const apiKeyWaitSample = `curl -N -X POST "${apiBaseUrl}/api/v1/agents/${agent.id}/chat/stream" \\
  -H "Authorization: Bearer clou_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"message":"Delete task T-42"}'

# tool_call ...
# run_status: {"status":"waiting","pending_tool_call_id":"call-123",
#   "pending_tool_input":{"interaction_kind":"tool_approval","execution_id":"…"}}`

  const apiKeyViewSample = `curl "${apiBaseUrl}/api/v1/tool-approvals?page=1&page_size=20" \\
  -H "Authorization: Bearer clou_your_key"

curl "${apiBaseUrl}/api/v1/tool-executions/{execution_id}" \\
  -H "Authorization: Bearer clou_your_key"`

  const apiKeyDecisionSample = `curl -X POST "${apiBaseUrl}/api/v1/tool-executions/{execution_id}/decision" \\
  -H "Authorization: Bearer clou_your_key" \\
  -H "Content-Type: application/json" \\
  -d '{"decision":"approve","reason":"checked the order id","idempotency_key":"decision-2026-10-28-0001"}'`

  const apiKeyResumeSample = `curl -N "${apiBaseUrl}/api/v1/agents/${agent.id}/chat/runs/{run_id}/stream?after_sequence=17" \\
  -H "Authorization: Bearer clou_your_key"`

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Header */}
      <div className="border-b px-6 py-2.5 shrink-0">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <h1 className="text-base font-medium leading-tight">{t('title')}</h1>
            <p className="text-xs text-muted-foreground truncate">{t('description')}</p>
          </div>
          <PermissionGuard permission="apikey:read">
            <a
              href="/app/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-xs font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 border border-input bg-background hover:bg-accent hover:text-accent-foreground h-7 px-2.5 shrink-0 ml-4"
            >
              <Key className="h-3 w-3" />
              {t('manageApiKeys')}
              <ExternalLink className="h-2.5 w-2.5" />
            </a>
          </PermissionGuard>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 max-w-4xl mx-auto space-y-8">

          {/* Agent Status Alert */}
          {agent.status === 'draft' && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>{t('draftWarningTitle')}</AlertTitle>
              <AlertDescription>{t('draftWarningDescription')}</AlertDescription>
            </Alert>
          )}

          {/* Endpoint Info */}
          <Section title={t('endpoint')}>
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="secondary">POST</Badge>
              <code className="text-sm bg-muted px-2 py-1 rounded">{chatEndpoint}</code>
            </div>
            <p className="text-sm text-muted-foreground">{t('endpointDescription')}</p>
          </Section>

          {/* Authentication */}
          <Section title={t('authentication')}>
            <p className="text-sm text-muted-foreground mb-3">{t('authDescription')}</p>
            <CodeBlock 
              code={`Authorization: Bearer YOUR_API_KEY`}
              language="http"
            />
          </Section>

          {/* Request Body */}
          <Section title={t('requestBody')}>
            <div className="space-y-4">
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
                      <td className="px-4 py-2"><code>message</code></td>
                      <td className="px-4 py-2">string</td>
                      <td className="px-4 py-2">{t('yes')}</td>
                      <td className="px-4 py-2 text-muted-foreground">{t('params.message')}</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-4 py-2"><code>conversation_id</code></td>
                      <td className="px-4 py-2">string | null</td>
                      <td className="px-4 py-2">{t('no')}</td>
                      <td className="px-4 py-2 text-muted-foreground">{t('params.conversationId')}</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-4 py-2"><code>variables</code></td>
                      <td className="px-4 py-2">object</td>
                      <td className="px-4 py-2">{t('no')}</td>
                      <td className="px-4 py-2 text-muted-foreground">{t('params.variables')}</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-4 py-2"><code>images</code></td>
                      <td className="px-4 py-2">array</td>
                      <td className="px-4 py-2">{t('no')}</td>
                      <td className="px-4 py-2 text-muted-foreground">{t('params.images')}</td>
                    </tr>
                    <tr className="border-t">
                      <td className="px-4 py-2"><code>file_urls</code></td>
                      <td className="px-4 py-2">array</td>
                      <td className="px-4 py-2">{t('no')}</td>
                      <td className="px-4 py-2 text-muted-foreground">{t('params.fileUrls')}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <CodeBlock code={sampleRequestBody} language="json" />
            </div>
          </Section>

          {/* Response Format */}
          <Section title={t('responseFormat')}>
            <p className="text-sm text-muted-foreground mb-3">{t('sseDescription')}</p>
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">{t('event')}</th>
                    <th className="text-left px-4 py-2 font-medium">{t('eventDescription')}</th>
                  </tr>
                </thead>
                <tbody>
                  {sseEvents.map((item) => (
                    <tr key={item.event} className="border-t">
                      <td className="px-4 py-2"><code>{item.event}</code></td>
                      <td className="px-4 py-2 text-muted-foreground">{item.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-sm text-muted-foreground mt-4 mb-2">{t('messageEndExample')}</p>
            <CodeBlock
              code={JSON.stringify({
                usage: {
                  prompt_tokens: 150,
                  completion_tokens: 25,
                  total_tokens: 175,
                },
                timing: {
                  first_token_ms: 320,
                  duration_ms: 2300,
                  tokens_per_second: 10.9,
                },
                version_number: 1,
                version_count: 1,
              }, null, 2)}
              language="json"
            />
          </Section>

          {/* Run Lifecycle Events */}
          <Section title={t('runLifecycleTitle')}>
            <p className="text-sm text-muted-foreground mb-3">{t('runLifecycleDescription')}</p>
            <div className="border rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-muted/50">
                  <tr>
                    <th className="text-left px-4 py-2 font-medium">{t('event')}</th>
                    <th className="text-left px-4 py-2 font-medium">{t('eventDescription')}</th>
                  </tr>
                </thead>
                <tbody>
                  {runEvents.map((item) => (
                    <tr key={item.event} className="border-t">
                      <td className="px-4 py-2"><code>{item.event}</code></td>
                      <td className="px-4 py-2 text-muted-foreground">{item.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {/* Tool Approvals */}
          <Section title={t('approval.title')}>
            <p className="text-sm text-muted-foreground">{t('approval.description')}</p>

            <div className="mt-4 space-y-5">
              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.pauseTitle')}</h4>
                <p className="text-sm text-muted-foreground mb-2">{t('approval.pauseDescription')}</p>
                <CodeBlock code={approvalToolCallEvent} language="text" />
                <p className="text-sm text-muted-foreground mt-3 mb-2">{t('approval.waitingPayload')}</p>
                <CodeBlock code={approvalWaitingEvent} language="text" />
              </div>

              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.viewTitle')}</h4>
                <p className="text-sm text-muted-foreground">{t('approval.viewDescription')}</p>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.listEndpoint')}</p>
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">GET</Badge>
                    <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalPendingListEndpoint}</code>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">GET</Badge>
                    <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalExecutionListEndpoint}</code>
                  </div>
                </div>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.streamEndpoint')}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">GET</Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalStreamEndpoint}</code>
                </div>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.readEndpoint')}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">GET</Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalExecutionReadEndpoint}</code>
                </div>

                <p className="text-sm text-muted-foreground mt-4 mb-2">{t('approval.viewResponse')}</p>
                <CodeBlock code={sampleApprovalExecution} language="json" />
                <p className="text-sm text-muted-foreground mt-3">{t('approval.viewResponseDescription')}</p>
              </div>

              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.decisionTitle')}</h4>
                <p className="text-sm text-muted-foreground">{t('approval.decisionDescription')}</p>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.executionEndpoint')}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">POST</Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalExecutionEndpoint}</code>
                </div>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.inboxEndpoint')}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">POST</Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalInboxEndpoint}</code>
                </div>

                <p className="text-sm text-muted-foreground mt-4 mb-2">{t('approval.decisionBody')}</p>
                <CodeBlock code={sampleApprovalBody} language="json" />
                <p className="text-sm text-muted-foreground mt-4 mb-2">{t('approval.decisionResponse')}</p>
                <CodeBlock code={sampleApprovalResponse} language="json" />
                <p className="text-sm text-muted-foreground mt-3">{t('approval.decisionResponseDescription')}</p>
                <p className="text-sm text-muted-foreground mt-3">{t('approval.previewNote')}</p>
              </div>

              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.resumeTitle')}</h4>
                <p className="text-sm text-muted-foreground">{t('approval.resumeDescription')}</p>

                <p className="text-sm text-muted-foreground mt-3 mb-1">{t('approval.statusEndpoint')}</p>
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">GET</Badge>
                  <code className="text-sm bg-muted px-2 py-1 rounded break-all">{approvalRunStatusEndpoint}</code>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.apiKeyTitle')}</h4>
                <p className="text-sm text-muted-foreground">{t('approval.apiKeyDescription')}</p>

                <p className="text-sm text-muted-foreground mt-3 mb-2">{t('approval.apiKeyWaitLabel')}</p>
                <CodeBlock code={apiKeyWaitSample} language="bash" />
                <p className="text-sm text-muted-foreground mt-3 mb-2">{t('approval.apiKeyViewLabel')}</p>
                <CodeBlock code={apiKeyViewSample} language="bash" />
                <p className="text-sm text-muted-foreground mt-3 mb-2">{t('approval.apiKeyDecisionLabel')}</p>
                <CodeBlock code={apiKeyDecisionSample} language="bash" />
                <p className="text-sm text-muted-foreground mt-3 mb-2">{t('approval.apiKeyResumeLabel')}</p>
                <CodeBlock code={apiKeyResumeSample} language="bash" />
                <p className="text-sm text-muted-foreground mt-3">{t('approval.apiKeyScopeNote')}</p>
              </div>

              <div>
                <h4 className="text-sm font-medium mb-2">{t('approval.workflowTitle')}</h4>
                <p className="text-sm text-muted-foreground">{t('approval.workflowDescription')}</p>
              </div>
            </div>
          </Section>

          {/* Submit Answers */}
          <Section title={t('answerTitle')}>
            <p className="text-sm text-muted-foreground mb-3">{t('answerDescription')}</p>
            <CodeBlock code={answerEndpoint} language="text" />
            <p className="text-sm text-muted-foreground mt-4 mb-2">{t('answerBody')}</p>
            <CodeBlock code={sampleAnswerBody} language="json" />
            <div className="mt-4 space-y-2">
              <div className="flex gap-2">
                <code className="text-sm bg-muted px-2 py-1 rounded">tool_call_id</code>
                <span className="text-sm text-muted-foreground">— {t('answerFields.toolCallId')}</span>
              </div>
              <div className="flex gap-2">
                <code className="text-sm bg-muted px-2 py-1 rounded">answers</code>
                <span className="text-sm text-muted-foreground">— {t('answerFields.answers')}</span>
              </div>
              <div className="flex gap-2">
                <code className="text-sm bg-muted px-2 py-1 rounded">skipped</code>
                <span className="text-sm text-muted-foreground">— {t('answerFields.skipped')}</span>
              </div>
            </div>
            <p className="text-sm text-muted-foreground mt-3">{t('answerNote')}</p>
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

          {/* Multi-turn Conversation */}
          <Section title={t('multiTurn.title')}>
            <p className="text-sm text-muted-foreground mb-3">{t('multiTurn.description')}</p>
            <div className="space-y-4">
              <div>
                <h4 className="text-sm font-medium mb-2">{t('multiTurn.step1Title')}</h4>
                <p className="text-sm text-muted-foreground mb-2">{t('multiTurn.step1Description')}</p>
                <CodeBlock 
                  code={JSON.stringify({
                    message: "Hello, I'd like to know about your products",
                    conversation_id: null,
                    variables: {}
                  }, null, 2)} 
                  language="json" 
                />
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2">{t('multiTurn.step2Title')}</h4>
                <p className="text-sm text-muted-foreground mb-2">{t('multiTurn.step2Description')}</p>
                <CodeBlock 
                  code={`event: message_start
data: {"conversation_id": "550e8400-e29b-41d4-a716-446655440000", "message_id": "...", "user_message_id": "..."}`} 
                  language="text" 
                />
              </div>
              <div>
                <h4 className="text-sm font-medium mb-2">{t('multiTurn.step3Title')}</h4>
                <p className="text-sm text-muted-foreground mb-2">{t('multiTurn.step3Description')}</p>
                <CodeBlock 
                  code={JSON.stringify({
                    message: "What discounts do you have?",
                    conversation_id: "550e8400-e29b-41d4-a716-446655440000",
                    variables: {}
                  }, null, 2)} 
                  language="json" 
                />
              </div>
            </div>
          </Section>

          {/* Variables Info */}
          {agent.variables && agent.variables.length > 0 && (
            <Section title={t('agentVariables')}>
              <p className="text-sm text-muted-foreground mb-3">{t('variablesDescription')}</p>
              <div className="border rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      <th className="text-left px-4 py-2 font-medium">{t('variableName')}</th>
                      <th className="text-left px-4 py-2 font-medium">{t('type')}</th>
                      <th className="text-left px-4 py-2 font-medium">{t('required')}</th>
                      <th className="text-left px-4 py-2 font-medium">{t('displayName')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agent.variables.map((variable) => (
                      <tr key={variable.name} className="border-t">
                        <td className="px-4 py-2"><code>{variable.name}</code></td>
                        <td className="px-4 py-2">{variable.type}</td>
                        <td className="px-4 py-2">{variable.required ? t('yes') : t('no')}</td>
                        <td className="px-4 py-2 text-muted-foreground">{variable.label || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <CodeBlock 
                code={JSON.stringify({
                  message: "Your question here",
                  variables: agent.variables.reduce((acc, v) => ({
                    ...acc,
                    [v.name]: v.type === 'checkbox' ? false : v.type === 'number' ? 0 : "value"
                  }), {})
                }, null, 2)} 
                language="json" 
                className="mt-4"
              />
            </Section>
          )}
        </div>
      </div>
    </div>
  )
}

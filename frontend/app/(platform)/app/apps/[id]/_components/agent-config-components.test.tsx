import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const noop = () => {}
const t = (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key
const currentTeam = { id: 'team-1', name: 'Team One' }

mock.module('next-intl', () => ({
  useTranslations: () => t,
  useLocale: () => 'en',
}))

mock.module('next/link', () => ({
  default: ({ children, href, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => <a href={href} {...props}>{children}</a>,
}))

mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/utils', () => ({ cn: (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(' ') }))
mock.module('@/lib/validation', () => ({ formatValidationSummaryMessage: (entries: unknown[]) => `summary:${entries.length}` }))

mock.module('@/lib/api', () => {
  class ApiError extends Error { code?: number; data?: unknown }
  return {
    ApiError,
    teamModelsApi: { getTeamModels: mock(async () => ({ items: [teamModel] })) },
    knowledgeBasesApi: { listKnowledgeBases: mock(async () => ({ items: [knowledgeBase] })) },
    agentsApi: { updateAgent: mock(async (_id: string, data: unknown) => ({ ...agentFixture, ...data })) },
    uploadApi: { uploadChatFile: mock(async () => ({ url: 'https://files.example.test/file.txt', name: 'file.txt' })) },
    toolsApi: { listFileParsers: mock(async () => []), listTools: mock(async () => ({ items: [] })) },
    clearValidationError: (errors: Record<string, string>, key: string) => {
      const next = { ...errors }
      delete next[key]
      return next
    },
    getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
    normalizeValidationErrors: () => ({}),
  }
})

mock.module('@/lib/api/workflows', () => ({ workflowsApi: { updateWorkflow: mock(async (_id: string, data: unknown) => data) } }))

const passthrough = (tag = 'div') => {
  function MockComponent({ children, render, value, checked, onValueChange, onClick, ...props }: Record<string, unknown>) {
  const Tag = tag as keyof JSX.IntrinsicElements
  if (render && React.isValidElement(render)) return React.cloneElement(render as React.ReactElement<Record<string, unknown>>, props)
  if (tag === 'input') return <input value={(value as string | number | undefined) ?? ''} checked={checked as boolean | undefined} onChange={(e) => onValueChange?.((e.target as HTMLInputElement).value)} {...props} />
  if (tag === 'textarea') return <textarea value={(value as string | undefined) ?? ''} onChange={(e) => onValueChange?.((e.target as HTMLTextAreaElement).value)} {...props}>{children as React.ReactNode}</textarea>
  if (tag === 'button') {
    return <button type="button" onClick={onClick as React.MouseEventHandler<HTMLButtonElement> | undefined} {...props}>{children as React.ReactNode}</button>
  }
  return <Tag {...props}>{children as React.ReactNode}</Tag>
  }
  return MockComponent
}

mock.module('@/components/ui/input', () => ({ Input: passthrough('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: passthrough('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: passthrough('label') }))
mock.module('@/components/ui/button', () => ({ Button: passthrough('button'), buttonVariants: () => '' }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough('span') }))
mock.module('@/components/ui/card', () => ({ Card: passthrough(), CardContent: passthrough(), CardDescription: passthrough(), CardHeader: passthrough(), CardTitle: passthrough('h2') }))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough('p') }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: passthrough() }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: ({ value }: { value?: string }) => <div data-testid="image-upload">{value}</div> }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked?: boolean; onCheckedChange?: (v: boolean) => void }) => <button type="button" aria-pressed={checked} onClick={() => onCheckedChange?.(!checked)} {...props} /> }))
mock.module('@/components/ui/tabs', () => ({ Tabs: passthrough(), TabsContent: passthrough(), TabsList: passthrough(), TabsTrigger: passthrough('button') }))
mock.module('@/components/ui/select', () => ({ Select: passthrough(), SelectContent: passthrough(), SelectEmpty: passthrough(), SelectItem: passthrough('option'), SelectTrigger: passthrough('button'), SelectValue: passthrough('span') }))
mock.module('@/components/ui/dialog', () => ({ Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <div>{children}</div> : null, DialogContent: passthrough(), DialogDescription: passthrough('p'), DialogHeader: passthrough(), DialogTitle: passthrough('h2') }))
mock.module('@/components/ui/sheet', () => ({ Sheet: ({ open, children }: { open: boolean; children: React.ReactNode }) => open ? <div>{children}</div> : null, SheetContent: passthrough(), SheetDescription: passthrough('p'), SheetHeader: passthrough(), SheetTitle: passthrough('h2') }))
mock.module('@/components/ui/dropdown-menu', () => ({ DropdownMenu: passthrough(), DropdownMenuContent: passthrough(), DropdownMenuItem: passthrough('button'), DropdownMenuTrigger: passthrough('button') }))
mock.module('@/components/ui/tooltip', () => ({ Tooltip: passthrough(), TooltipContent: passthrough(), TooltipTrigger: passthrough('button') }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: passthrough(), CollapsibleContent: passthrough(), CollapsibleTrigger: passthrough('button') }))

mock.module('@/components/chat', () => ({
  ChatContainer: ({ messages }: { messages: Array<{ content?: string }> }) => <div data-testid="chat-container">{messages.map((m, i) => <p key={i}>{m.content}</p>)}</div>,
  ChatInput: ({ value, placeholder, onSubmit }: { value: string; placeholder?: string; onSubmit: (v: string) => void }) => <form onSubmit={(e) => { e.preventDefault(); onSubmit(value || 'hello') }}><input aria-label="chat" placeholder={placeholder} value={value} onChange={noop} /><button type="submit">send</button></form>,
  PendingAskUserForm: () => null,
  VariableForm: () => <div data-testid="variable-form" />,
  useVariableForm: () => ({ values: {}, setValues: noop, needsInput: false, isValid: true, fieldErrors: {}, validate: () => true, reset: noop }),
}))

mock.module('@/hooks/use-chat', () => ({
  useChat: () => ({ messages: [], error: null, isLoading: false, isStreaming: false, sendMessage: mock(), regenerate: mock(), switchVersion: mock(), stop: mock(), reset: mock() }),
  getErrorMsgKey: () => 'error',
}))

mock.module('./variable-editor', () => ({ VariableEditor: () => <div />, AddVariableButton: () => <button type="button">add variable</button>, createNewVariable: () => ({ name: '', label: '', type: 'text', required: false }) }))
mock.module('./knowledge-base-selector', () => ({ KnowledgeBaseSelector: () => <div />, AddKnowledgeBaseButton: () => <button type="button">add kb</button> }))
mock.module('./tool-selector', () => ({ ToolSelector: () => <div />, AddToolButton: () => <button type="button">add tool</button>, useTools: () => ({ tools: [] }) }))
mock.module('./prompt-editor', () => ({ PromptEditor: ({ value }: { value: string }) => <textarea aria-label="prompt-editor" value={value} onChange={noop} /> }))
mock.module('@/components/ai-elements/prompt-generate-dialog', () => ({ PromptGenerateDialog: ({ open }: { open: boolean }) => open ? <div data-testid="prompt-generate-dialog" /> : null }))

const teamModel = { id: 'tm-1', model: { id: 'model-1', name: 'GPT Test' }, capabilities: ['chat'] }
const knowledgeBase = { id: 'kb-1', name: 'Handbook', document_count: 3 }
const agentFixture = {
  id: 'agent-1', name: 'Support Agent', description: 'Helps users', icon: '', avatar_url: '', visibility: 'private', status: 'published', model_id: 'tm-1', model: teamModel.model,
  system_prompt: 'Be useful', opening_message: 'Hi there', suggested_questions: ['How do I start?'], suggestedQuestions: ['How do I start?'], variables: [], knowledge_bases: [], tools_config: [], rag_mode: 'agentic',
  enable_attachments: false, enable_memory: false, memory_config: null, enable_image_generation: false, image_generation_config: null, enable_video_generation: false, video_generation_config: null,
  embed_config: { enabled: true, allowed_domains: ['https://example.com'], theme: { mode: 'auto', primary_color: '#6366f1' }, bubble: { position: 'bottom-right', icon: null, greeting: 'Hello' } },
}

function render(ui: React.ReactNode) {
  return renderToStaticMarkup(<>{ui}</>)
}

describe('agent app detail configuration components', () => {
  test('submits basic agent config without leaking secrets', async () => {
    const { AgentConfigForm } = await import('./agent-config-form')
    const onSubmit = mock(async () => {})

    const html = render(<AgentConfigForm agent={agentFixture as never} onSubmit={onSubmit} />)

    expect(html).toContain('basicInfo')
    expect(html).toContain('Support Agent')
    expect(html).toContain('Be useful')
    expect(html).not.toContain('clou_live_secret')
  })

  test('renders orchestration and preview controls from agent state', async () => {
    const { AgentOrchestrationForm } = await import('./agent-orchestration-form')
    const { AgentPreviewPanel } = await import('./agent-preview-panel')

    const html = render(<><AgentOrchestrationForm agent={agentFixture as never} onUpdate={mock()} /><AgentPreviewPanel agent={agentFixture as never} /></>)

    expect(html).toContain('prompt.title')
    expect(html).toContain('variables.title')
    expect(html).toContain('tools.title')
    expect(html).toContain('title')
  })

  test('renders the settings drawer with selected agent fields', async () => {
    const { AgentSettingsDrawer } = await import('./agent-settings-drawer')

    const html = render(<AgentSettingsDrawer open agent={agentFixture as never} onOpenChange={mock()} name="Support Agent" onNameChange={mock()} description="Helps users" onDescriptionChange={mock()} icon="" onIconChange={mock()} openingMessage="Hi there" onOpeningMessageChange={mock()} suggestedQuestions={['How do I start?']} onSuggestedQuestionsChange={mock()} visibility="private" onVisibilityChange={mock()} modelId="tm-1" onModelChange={mock()} maxIterations={5} onMaxIterationsChange={mock()} hideToolCalls={false} onHideToolCallsChange={mock()} hasToolsEnabled={false} />)

    expect(html).toContain('Support Agent')
    expect(html).toContain('basicInfo')
    expect(html).toContain('conversationConfig')
    expect(html).toContain('GPT Test')
  })

  test('saves embed config with placeholder API key only', async () => {
    const { EmbedConfigDialog } = await import('./embed-config-dialog')
    const updateAgent = mock(async (_id: string, data: unknown) => ({ ...agentFixture, ...data }))
    const onUpdate = mock()
    const onOpenChange = mock()

    const html = render(<EmbedConfigDialog open agent={agentFixture as never} onUpdate={onUpdate} onOpenChange={onOpenChange} updateAgent={updateAgent as never} />)

    expect(html).toContain('allowedDomains')
    expect(html).toContain('https://example.com')
    expect(html).toContain('YOUR_API_KEY')
    expect(html).not.toContain('clou_live_secret')
    expect(updateAgent).not.toHaveBeenCalled()
    expect(onUpdate).not.toHaveBeenCalled()
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})

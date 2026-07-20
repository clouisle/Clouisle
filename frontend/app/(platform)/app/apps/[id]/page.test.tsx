import { beforeEach, describe, expect, it, mock } from 'bun:test'
import * as ReactActual from 'react'
import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

let currentTeam: { id: string; role: string } | null = { id: 'team-1', role: 'member' }
let currentUser: { id: string; is_superuser?: boolean } | null = { id: 'user-1' }
let allowed = new Set<string>()
let stateValues: unknown[] = []
const push = mock(() => {})
const setState = mock((value: unknown) => value)
const getAgent = mock()
const updateAgent = mock()
const publishAgent = mock()
const unpublishAgent = mock()

mock.module('react', () => ({
  ...ReactActual,
  default: ReactActual,
  useEffect: (effect: () => void) => effect(),
  useState: (initial: unknown) => [stateValues.length ? stateValues.shift() : initial, setState],
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('next/navigation', () => ({
  useRouter: () => ({ push }),
  usePathname: () => '/app/apps/agent-1',
}))
mock.module('next/link', () => ({ default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a> }))
mock.module('next/image', () => ({ default: ({ alt }: { alt: string }) => <img alt={alt} /> }))
mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/hooks/use-permissions', () => ({ usePermissions: () => ({ user: currentUser }) }))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform: (permission: string) => allowed.has(permission) }) }))
mock.module('@/lib/api', () => ({ agentsApi: { getAgent, updateAgent, publishAgent, unpublishAgent }, ApiError: class ApiError extends Error {} }))
mock.module('@/lib/api/client', () => ({ ApiError: class ApiError extends Error {} }))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: ({ className }: { className?: string }) => <div className={className}>skeleton</div> }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: { children: ReactNode }) => <div>{children}</div> }))
mock.module('./_components/agent-sidebar', () => ({ AgentSidebar: ({ agent, backHref, baseUrl }: { agent: { name: string }; backHref: string; baseUrl: string }) => <aside>{agent.name}<a href={backHref}>back</a><a href={baseUrl}>orchestration</a></aside> }))
mock.module('./_components/agent-toolbar', () => ({ AgentToolbar: ({ canUpdate, canPublish, onSave, onPublish, onSettingsClick, onEmbedClick }: { canUpdate: boolean; canPublish: boolean; onSave: () => void; onPublish: () => void; onSettingsClick: () => void; onEmbedClick: () => void }) => <div><span>/chat/agent-1</span>{canUpdate && <><button data-testid="agent-save-button" onClick={onSave}>save</button><button data-testid="agent-settings-button" onClick={onSettingsClick}>settings</button><button data-testid="agent-embed-button" onClick={onEmbedClick}>embed</button></>}{canPublish && <button data-testid="agent-publish-button" onClick={onPublish}>publish</button>}</div> }))
mock.module('./_components/agent-orchestration-form', () => ({ AgentOrchestrationForm: ({ agent, onUpdate }: { agent: { system_prompt: string }; onUpdate: (data: Record<string, unknown>) => void }) => <button onClick={() => onUpdate({ system_prompt: 'changed prompt' })}>{agent.system_prompt}</button> }))
mock.module('./_components/agent-preview-panel', () => ({ AgentPreviewPanel: ({ agent }: { agent: { name: string } }) => <section>preview {agent.name}</section> }))
mock.module('./_components/agent-settings-drawer', () => ({ AgentSettingsDrawer: ({ open, name }: { open: boolean; name: string }) => open ? <div>settings {name}</div> : null }))
mock.module('./_components/embed-config-dialog', () => ({ EmbedConfigDialog: ({ open }: { open: boolean }) => open ? <div>embed dialog</div> : null }))

const { AgentEditor } = await import('./page')

const agent = {
  id: 'agent-1',
  team: { id: 'team-1', name: 'Team' },
  name: 'Support agent',
  description: 'Answers questions',
  icon: '🤖',
  model_id: 'model-1',
  model: { id: 'model-1', name: 'GPT Test', provider: 'openai', model_id: 'gpt-test' },
  system_prompt: 'Be helpful',
  max_iterations: 5,
  hide_tool_calls: false,
  tools_config: [],
  variables: [],
  opening_message: '',
  suggested_questions: [],
  knowledge_bases: [],
  enable_vision: false,
  enable_file_upload: false,
  enable_user_input_request: false,
  enable_memory: false,
  enable_image_generation: false,
  enable_video_generation: false,
  rag_mode: 'agentic',
  status: 'draft',
  visibility: 'private',
  conversation_count: 0,
  message_count: 0,
  created_by: { id: 'user-1', username: 'me' },
  created_at: '2025-01-01',
  updated_at: '2025-01-01',
}

function renderEditor() {
  return renderToStaticMarkup(<AgentEditor agentId="agent-1" />)
}

beforeEach(() => {
  currentTeam = { id: 'team-1', role: 'member' }
  currentUser = { id: 'user-1' }
  allowed = new Set<string>()
  stateValues = []
  push.mockClear()
  setState.mockClear()
  getAgent.mockReset()
  updateAgent.mockReset()
  publishAgent.mockReset()
  unpublishAgent.mockReset()
})

describe('AgentEditor', () => {
  it('shows loading while the app is absent and fetches the agent', () => {
    getAgent.mockResolvedValue(agent)

    const html = renderEditor()

    expect(html).toContain('skeleton')
    expect(html).not.toContain('Support agent')
    expect(getAgent).toHaveBeenCalledWith('agent-1')
  })

  it('renders the loaded agent and owner actions', async () => {
    stateValues = [agent, false, false, false]

    const html = renderEditor()

    expect(html).toContain('Support agent')
    expect(html).toContain('preview Support agent')
    expect(html).toContain('data-testid="agent-save-button"')
    expect(html).toContain('data-testid="agent-settings-button"')
    expect(html).not.toContain('data-testid="agent-publish-button"')
  })

  it('redirects to the apps list after a failed load', async () => {
    getAgent.mockRejectedValue(new Error('missing'))

    renderEditor()
    await Promise.resolve()

    expect(push).toHaveBeenCalledWith('/app/apps')
  })

  it('exposes publish by permission and opens editor actions', () => {
    allowed = new Set(['agent:publish'])
    currentUser = { id: 'other-user' }
    currentTeam = { id: 'team-1', role: 'admin' }
    stateValues = [agent, false, false, false]

    const html = renderEditor()

    expect(html).toContain('data-testid="agent-publish-button"')
    expect(html).toContain('data-testid="agent-save-button"')
  })
})

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
let toolbarProps: Record<string, unknown> = {}
let orchestrationProps: Record<string, unknown> = {}

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
mock.module('./_components/agent-toolbar', () => ({ AgentToolbar: (props: Record<string, unknown>) => { toolbarProps = props; const { canUpdate, canPublish, onSave, onPublish, onSettingsClick, onEmbedClick } = props as { canUpdate: boolean; canPublish: boolean; onSave: () => void; onPublish: () => void; onSettingsClick: () => void; onEmbedClick: () => void }; return <div><span>/chat/agent-1</span>{canUpdate && <><button data-testid="agent-save-button" onClick={onSave}>save</button><button data-testid="agent-settings-button" onClick={onSettingsClick}>settings</button><button data-testid="agent-embed-button" onClick={onEmbedClick}>embed</button></>}{canPublish && <button data-testid="agent-publish-button" onClick={onPublish}>publish</button>}</div> } }))
mock.module('./_components/agent-orchestration-form', () => ({ AgentOrchestrationForm: (props: Record<string, unknown>) => { orchestrationProps = props; const { agent, onUpdate } = props as { agent: { system_prompt: string }; onUpdate: (data: Record<string, unknown>) => void }; return <button onClick={() => onUpdate({ system_prompt: 'changed prompt' })}>{agent.system_prompt}</button> } }))
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
  hide_token_stats: false,
  hide_reasoning: false,
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
  toolbarProps = {}
  orchestrationProps = {}
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

  it('saves initialized values and publishes or unpublishes the agent', async () => {
    stateValues = [agent, false, false, false]
    updateAgent.mockResolvedValue(agent)
    publishAgent.mockResolvedValue({ ...agent, status: 'published' })

    renderEditor()
    await (toolbarProps.onSave as () => Promise<void>)()
    await (toolbarProps.onPublish as () => Promise<void>)()

    expect(updateAgent).toHaveBeenCalledWith('agent-1', expect.objectContaining({
      name: '',
      memory_config: null,
      file_upload_config: null,
      image_generation_config: null,
      video_generation_config: null,
    }))
    expect(publishAgent).toHaveBeenCalledWith('agent-1')

    stateValues = [{ ...agent, status: 'published' }, false, false, false]
    unpublishAgent.mockResolvedValue(agent)
    renderEditor()
    await (toolbarProps.onPublish as () => Promise<void>)()
    expect(unpublishAgent).toHaveBeenCalledWith('agent-1')
  })

  it('applies every orchestration capability update', () => {
    stateValues = [agent, false, false, false]
    renderEditor()

    ;(orchestrationProps.onUpdate as (data: Record<string, unknown>) => void)({
      system_prompt: 'updated',
      tools_config: [{ name: 'search' }],
      variables: [{ name: 'topic' }],
      knowledge_base_configs: [{ knowledge_base_id: 'kb-1' }],
      rag_mode: 'auto',
      enable_vision: true,
      enable_file_upload: true,
      enable_user_input_request: true,
      enable_memory: true,
      memory_config: { max_memories_per_retrieval: 3 },
      enable_image_generation: true,
      image_generation_config: { size: '1024x1024' },
      enable_video_generation: true,
      video_generation_config: { duration: 5 },
      file_upload_config: { max_file_size: 1024 },
    })

    expect(setState).toHaveBeenCalledTimes(16)
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

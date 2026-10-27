import { afterEach, beforeEach, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { toolsApi, type Tool, type ToolConfig } from '@/lib/api'
import { GlobalRegistrator } from '@happy-dom/global-registrator'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })

const engineLabels: Record<string, string> = { engineAuto: 'Site default', engineTavily: 'Tavily', engineBocha: 'Bocha', engineSearxng: 'SearXNG', engineDeepseek: 'DeepSeek' }
// WebSearchEngineSelect translates bare engine keys, while ToolSelector
// translates `config.*` keys, so both namespaces resolve to human copy.
const labels: Record<string, string> = {
  ...engineLabels,
  'config.engineAuto': engineLabels.engineAuto,
  'config.engineTavily': engineLabels.engineTavily,
  'config.engineBocha': engineLabels.engineBocha,
  'config.engineSearxng': engineLabels.engineSearxng,
  'config.engineDeepseek': engineLabels.engineDeepseek,
  'config.title': 'Web search',
  'config.engine': 'Provider',
  'config.settings': 'Settings',
  'config.save': 'Save',
  'config.cancel': 'Cancel',
}
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => labels[key] || key }))
// ToolSelector's ToolDisplayItem reads the active team to resolve tool
// connections. The dropdown flow under test does not use connections, but
// the hook still has to resolve, so supply a realistic team context.
const teamContext = {
  currentTeam: { id: 'team-1', name: 'Team', role: 'member' as const },
  teams: [],
  isLoading: false,
  setCurrentTeam: () => {},
  refreshTeams: async () => {},
}
mock.module('@/contexts/team-context', () => ({
  useTeam: () => teamContext,
  useOptionalTeam: () => teamContext,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: React.PropsWithChildren<{ open: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: () => null,
}))

const { WebSearchEngineSelect } = await import('./web-search-engine-select')
let renderer: ReactTestRenderer | undefined
beforeEach(() => { spyOn(toolsApi, 'getWebSearchEngines').mockResolvedValue(['searxng']) })
afterEach(() => { if (renderer) act(() => renderer!.unmount()); renderer = undefined; mock.restore() })

async function render(value = 'auto', onValueChange = mock()) {
  await act(async () => { renderer = create(<WebSearchEngineSelect value={value} onValueChange={onValueChange} />) })
  return onValueChange
}
async function openMenu() {
  const trigger = document.querySelector<HTMLButtonElement>('[role="combobox"]')!
  await act(async () => { trigger.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })) })
}

test('offers only enabled providers and selecting one updates the controlled value with human labels', async () => {
  function Controlled() {
    const [value, setValue] = React.useState('auto')
    return <WebSearchEngineSelect value={value} onValueChange={setValue} />
  }
  await act(async () => { renderer = create(<Controlled />) })
  await openMenu()
  expect(Array.from(document.querySelectorAll('[role="option"]')).map((item) => item.textContent)).toEqual(['Site default', 'SearXNG'])
  const option = Array.from(document.querySelectorAll<HTMLElement>('[role="option"]')).find((item) => item.textContent === 'SearXNG')!
  await act(async () => { option.click() })
  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('SearXNG')
  await openMenu()
  expect(document.querySelector('[role="option"][aria-selected="true"]')?.textContent).toBe('SearXNG')
})

test('keeps a saved disabled provider visible but never offers it as an option or changes it on load', async () => {
  const changed = await render('bocha')
  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('Bocha')
  await openMenu()
  expect(Array.from(document.querySelectorAll('[role="option"]')).map((item) => item.textContent)).toEqual(['Site default', 'SearXNG'])
  expect(changed).not.toHaveBeenCalled()
})

test('availability failure does not offer hardcoded provider options or rewrite the saved choice', async () => {
  spyOn(toolsApi, 'getWebSearchEngines').mockRejectedValue(new Error('offline'))
  const changed = await render('tavily')
  await openMenu()
  expect(Array.from(document.querySelectorAll('[role="option"]')).map((item) => item.textContent)).toEqual(['Site default'])
  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('Tavily')
  expect(changed).not.toHaveBeenCalled()
})

test('all disabled providers leave only the site default routing choice', async () => {
  spyOn(toolsApi, 'getWebSearchEngines').mockResolvedValue([])
  await render()
  await openMenu()
  expect(Array.from(document.querySelectorAll('[role="option"]')).map((item) => item.textContent)).toEqual(['Site default'])
})

test('Agent orchestration saves the enabled provider chosen through the real dropdown', async () => {
  // Imported dynamically (cannot be a static import) because the
  // `mock.module` registrations above must be in place before the component
  // graph, including the real Base UI Select, is loaded.
  const { ToolSelector } = await import('../../app/(platform)/app/apps/[id]/_components/tool-selector')
  const onSave = mock()
  const tool: Tool = {
    name: 'web_search',
    display_name: 'Web search',
    description: 'Search',
    type: 'builtin',
    category: 'search',
    visibility: 'team',
    parameters: [],
    is_enabled: true,
    requires_config: false,
    config_fields: [],
  }
  // Mirror the orchestration form: the updated tool config is fed back into
  // the selector, so the saved provider must survive the round trip.
  function ControlledSelector() {
    const [toolsConfig, setToolsConfig] = React.useState<ToolConfig[]>([
      { type: 'builtin', name: 'web_search', config: { engine: 'auto' } },
    ])
    return (
      <ToolSelector
        toolsConfig={toolsConfig}
        availableTools={[tool]}
        onChange={(next) => {
          setToolsConfig(next)
          onSave(next)
        }}
      />
    )
  }
  await act(async () => { renderer = create(<ControlledSelector />) })
  expect(document.body.textContent).toContain('Site default')

  await act(async () => { document.querySelector<HTMLButtonElement>('button[title="Settings"]')!.click() })
  // Let the provider availability request settle before opening the menu.
  await act(async () => {})
  await openMenu()
  expect(Array.from(document.querySelectorAll('[role="option"]')).map((item) => item.textContent)).toEqual(['Site default', 'SearXNG'])
  await act(async () => { Array.from(document.querySelectorAll<HTMLElement>('[role="option"]')).find((item) => item.textContent === 'SearXNG')!.click() })
  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('SearXNG')
  expect(onSave).not.toHaveBeenCalled()

  await act(async () => { Array.from(document.querySelectorAll('button')).find((button) => button.textContent === 'Save')!.click() })
  expect(onSave).toHaveBeenCalledWith([{ type: 'builtin', name: 'web_search', config: { engine: 'searxng' } }])
  expect(document.querySelector('[role="combobox"]')).toBeNull()
  expect(document.body.textContent).toContain('SearXNG')
})

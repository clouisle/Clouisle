import { afterEach, beforeEach, expect, mock, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import type { Tool } from '@/lib/api'
import type { ToolNodeConfig as ToolNodeConfigData } from './tool-node-config'

if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' })
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

const labels: Record<string, string> = {
  engineAuto: 'Site default',
  engineTavily: 'Tavily',
  engineBocha: 'Bocha',
  engineSearxng: 'SearXNG',
}
const webSearch: Tool = {
  id: 'builtin-web-search',
  name: 'web_search',
  display_name: 'Web Search',
  description: 'Searches the web',
  type: 'builtin',
  category: 'search',
  visibility: 'team',
  icon: '',
  parameters: [
    { name: 'query', type: 'string', required: true },
    { name: 'search_engine', type: 'string', required: false, default: 'auto' },
  ],
  is_enabled: true,
  requires_config: true,
  config_fields: [],
}
const list = mock(async () => ({ builtin: [webSearch], custom: [], mcp: [] }))
const listMcpTools = mock(async () => ({ tools: [] }))
const getWebSearchEngines = mock(async () => ['tavily', 'searxng'])
const currentTeam = { id: 'team-1' }

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => labels[key] || key }))
mock.module('next/image', () => ({ default: function Image() { return null } }))
mock.module('@/contexts/team-context', () => ({ useTeam: () => ({ currentTeam }) }))
mock.module('@/lib/api', () => ({
  toolsApi: { list, listMcpTools, getWebSearchEngines },
  isPresetToolCategory: (category: string) => ['time', 'math', 'search', 'web', 'file', 'code', 'sandbox', 'api', 'data', 'other'].includes(category),
}))

// Base UI captures the DOM environment at import time, so register happy-dom and the network mocks first.
const { ToolNodeConfig } = await import('./tool-node-config')

const queryMapping = { name: 'query', type: 'string', required: true, source: 'constant' as const, constantValue: 'cats' }
const engineMapping = { name: 'search_engine', type: 'string', required: false, source: 'constant' as const }

let renderer: ReactTestRenderer | undefined

async function renderTool(parameterMappings: ToolNodeConfigData['parameterMappings']) {
  const onConfigChange = mock(() => {})
  const config: ToolNodeConfigData = {
    toolName: 'web_search',
    toolType: 'builtin',
    parameterMappings,
    outputVariable: 'result',
  }
  await act(async () => {
    renderer = create(
      <ToolNodeConfig
        config={config}
        variables={[]}
        variableSearch=""
        openVariablePopover={null}
        onConfigChange={onConfigChange}
        onVariableSearchChange={() => {}}
        onOpenVariablePopoverChange={() => {}}
      />,
    )
    await Promise.resolve()
    await Promise.resolve()
  })
  return onConfigChange
}

async function openEngineMenu() {
  const trigger = document.querySelector<HTMLElement>('[role="combobox"]')
  expect(trigger).not.toBeNull()
  await act(async () => {
    trigger!.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
  })
  return Array.from(document.querySelectorAll<HTMLElement>('[role="option"]'))
}

beforeEach(() => {
  list.mockClear()
  listMcpTools.mockClear()
  getWebSearchEngines.mockClear()
  list.mockImplementation(async () => ({ builtin: [webSearch], custom: [], mcp: [] }))
  getWebSearchEngines.mockImplementation(async () => ['tavily', 'searxng'])
})

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
  document.body.innerHTML = ''
})

test('choosing an enabled engine updates the persisted mapping constant', async () => {
  const onConfigChange = await renderTool([queryMapping, engineMapping])

  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('Site default')
  const options = await openEngineMenu()
  expect(options.map((option) => option.textContent)).toEqual(['Site default', 'Tavily', 'SearXNG'])

  await act(async () => { options.find((option) => option.textContent === 'Tavily')!.click() })

  expect(onConfigChange).toHaveBeenCalledWith(expect.objectContaining({
    toolName: 'web_search',
    toolType: 'builtin',
    outputVariable: 'result',
    parameterMappings: [
      queryMapping,
      expect.objectContaining({ name: 'search_engine', source: 'constant', constantValue: 'tavily' }),
    ],
  }))
})

test('keeps a saved engine that is no longer enabled visible without rewriting it', async () => {
  const onConfigChange = await renderTool([queryMapping, { ...engineMapping, constantValue: 'bocha' }])

  expect(document.querySelector('[role="combobox"]')?.textContent).toContain('Bocha')
  const options = await openEngineMenu()
  expect(options.map((option) => option.textContent)).toEqual(['Site default', 'Tavily', 'SearXNG'])
  expect(onConfigChange).not.toHaveBeenCalled()
})

test('keeps the variable source for the engine parameter', async () => {
  await renderTool([{ ...engineMapping, source: 'variable', variableRef: '{{start.searchEngine}}', variableRefNodeLabel: 'Start' }])

  expect(document.querySelector('[role="combobox"]')).toBeNull()
  expect(document.body.textContent).toContain('Start / searchEngine')

  const sourceToggles = Array.from(document.querySelectorAll('button')).filter((button) => button.textContent === 'configCommon.constant')
  expect(sourceToggles).toHaveLength(1)
})

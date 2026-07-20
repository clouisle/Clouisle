import { afterEach, beforeAll, describe, expect, it, mock } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
Object.assign(globalThis, {
  window,
  document: window.document,
  navigator: window.navigator,
  HTMLElement: window.HTMLElement,
  HTMLInputElement: window.HTMLInputElement,
})
;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))
mock.module('@/lib/api', () => ({
  isPresetToolCategory: (category: string) => category === 'search',
}))
mock.module('@/components/ui/input', () => ({
  Input: ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => (
    <input {...props} onInput={onChange} />
  ),
}))

const TabContext = React.createContext<(value: string) => void>(() => {})
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) => (
    <TabContext.Provider value={onValueChange}>{children}</TabContext.Provider>
  ),
  TabsList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TabsTrigger: ({ children, value, disabled }: { children: React.ReactNode; value: string; disabled?: boolean }) => {
    const onValueChange = React.useContext(TabContext)
    return <button disabled={disabled} onClick={() => onValueChange(value)}>{children}</button>
  },
}))
mock.module('lucide-react', () => ({
  Search: () => <svg />,
  Wrench: () => <svg />,
}))
mock.module('./tool-card', () => ({
  ToolCard: ({
    tool,
    onSelect,
    onTest,
    onEdit,
    onDelete,
    onConfigure,
    onShare,
    canConfigure,
    canEdit,
    canShare,
    canDelete,
  }: {
    tool: Tool
    onSelect?: (tool: Tool) => void
    onTest?: (tool: Tool) => void
    onEdit?: (tool: Tool) => void
    onDelete?: (tool: Tool) => void
    onConfigure?: (tool: Tool) => void
    onShare?: (tool: Tool) => void
    canConfigure: boolean
    canEdit: boolean
    canShare: boolean
    canDelete: boolean
  }) => (
    <article data-tool={tool.name} data-permissions={`${canConfigure},${canEdit},${canShare},${canDelete}`}>
      <span>{tool.display_name}</span>
      <button onClick={() => onSelect?.(tool)}>select</button>
      <button onClick={() => onTest?.(tool)}>test</button>
      <button onClick={() => onEdit?.(tool)}>edit</button>
      <button onClick={() => onDelete?.(tool)}>delete</button>
      <button onClick={() => onConfigure?.(tool)}>configure</button>
      <button onClick={() => onShare?.(tool)}>share</button>
    </article>
  ),
}))

type Tool = import('@/lib/api').Tool
let ToolList: typeof import('./tool-list').ToolList

beforeAll(async () => {
  ;({ ToolList } = await import('./tool-list'))
})

const tools = [
  { id: '1', name: 'web_search', display_name: 'Web Search', description: 'Find pages', category: 'search', type: 'builtin' },
  { id: '2', name: 'summarize', display_name: 'Summarizer', description: 'Condense text', category: 'Writing', type: 'custom' },
  { id: '3', name: 'remote_docs', display_name: 'Remote Docs', description: 'Fetch manuals', category: 'search', type: 'mcp' },
] as Tool[]

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

function render(props: React.ComponentProps<typeof ToolList>) {
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(<ToolList {...props} />))
  return container
}

function button(container: HTMLElement, text: string) {
  return [...container.querySelectorAll('button')].find((item) => item.textContent === text)!
}

function enter(input: HTMLInputElement, value: string) {
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new window.Event('input', { bubbles: true }))
}

describe('ToolList', () => {
  it('groups tools, translates preset categories, and reports type counts', () => {
    const container = render({ tools })

    expect(container.textContent).toContain('categories.search')
    expect(container.textContent).toContain('Writing')
    expect(button(container, 'filters.all (3)').disabled).toBe(false)
    expect(button(container, 'filters.builtin (1)').disabled).toBe(false)
    expect(button(container, 'filters.custom (1)').disabled).toBe(false)
    expect(button(container, 'filters.mcp (1)').disabled).toBe(false)
    expect(container.querySelectorAll('article')).toHaveLength(3)
  })

  it('searches name, display name, and description case-insensitively, then shows the search empty state', () => {
    const container = render({ tools })
    const input = container.querySelector('input')!

    for (const [query, expected] of [['WEB_', 'Web Search'], ['summarizer', 'Summarizer'], ['MANUALS', 'Remote Docs']]) {
      act(() => enter(input, query))
      expect(container.querySelector('article')?.textContent).toContain(expected)
      expect(container.querySelectorAll('article')).toHaveLength(1)
    }

    act(() => enter(input, 'missing'))
    expect(container.textContent).toContain('noSearchResults')
    expect(container.querySelector('article')).toBeNull()
  })

  it('filters by tool type and distinguishes the initial empty state', () => {
    const container = render({ tools })

    act(() => button(container, 'filters.custom (1)').click())
    expect(container.querySelectorAll('article')).toHaveLength(1)
    expect(container.querySelector('article')?.dataset.tool).toBe('summarize')

    const empty = render({ tools: [] })
    expect(empty.textContent).toContain('noTools')
    expect(button(empty, 'filters.custom (0)').disabled).toBe(true)
    expect(button(empty, 'filters.mcp (0)').disabled).toBe(true)
  })

  it('forwards actions and evaluates permission gates for each tool', () => {
    const actions = {
      onSelect: mock(),
      onTest: mock(),
      onEdit: mock(),
      onDelete: mock(),
      onConfigure: mock(),
      onShare: mock(),
    }
    const container = render({
      tools: [tools[1]],
      ...actions,
      canConfigure: () => true,
      canEdit: () => false,
      canShare: () => true,
      canDelete: () => false,
    })

    expect(container.querySelector('article')?.dataset.permissions).toBe('true,false,true,false')
    for (const [name, handler] of Object.entries(actions)) {
      act(() => button(container, name.slice(2).toLowerCase()).click())
      expect(handler).toHaveBeenCalledWith(tools[1])
    }
  })
})

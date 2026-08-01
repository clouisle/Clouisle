import { afterEach, beforeAll, beforeEach, describe, expect, it, mock } from 'bun:test'
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

const listMcpTools = mock<() => Promise<{ tools: Array<{ name: string; description?: string }> }>>()
const toastInfo = mock()
const toastSuccess = mock()

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { info: toastInfo, success: toastSuccess } }))
mock.module('lucide-react', () => ({
  Loader2: () => <svg />,
  Plus: () => <svg />,
  Trash2: () => <svg />,
  Info: () => <svg />,
  Terminal: () => <svg />,
  Globe: () => <svg />,
  RefreshCw: () => <svg />,
  CheckCircle2: () => <svg />,
}))
mock.module('@/lib/api/tools', () => ({ toolsApi: { listMcpTools } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => key !== field)),
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) =>
    Object.fromEntries(Object.entries(errors).filter(([key]) => !key.startsWith(prefix))),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  mapValidationErrors: (errors: Record<string, string>) => errors,
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const passthrough = ({ children }: React.HTMLAttributes<HTMLElement>) => <div>{children}</div>
const Input = ({ onChange, ...props }: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} onInput={onChange} />
const Button = (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} />

mock.module('@/components/ui/dialog', () => ({
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
}))
mock.module('@/components/ui/button', () => ({ Button }))
mock.module('@/components/ui/input', () => ({ Input }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <span>{children}</span>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement } & Record<string, unknown>) =>
    render ? React.cloneElement(render, { ...props, ...(children !== undefined ? { children } : {}) }) : <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/label', () => ({ Label: (props: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props} /> }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ onCheckedChange, ...props }: { onCheckedChange: (value: boolean) => void }) => <button {...props} onClick={() => onCheckedChange(false)} /> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) => <div><button onClick={() => onValueChange('team-2')}>choose-team</button>{children}</div>,
  SelectContent: passthrough,
  SelectItem: passthrough,
  SelectTrigger: passthrough,
  SelectValue: passthrough,
}))
const TabContext = React.createContext<(value: string) => void>(() => undefined)
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, onValueChange }: { children: React.ReactNode; onValueChange: (value: string) => void }) => <TabContext.Provider value={onValueChange}>{children}</TabContext.Provider>,
  TabsList: passthrough,
  TabsTrigger: ({ children, value }: { children: React.ReactNode; value: string }) => {
    const changeTab = React.useContext(TabContext)
    return <button onClick={() => changeTab(value)}>{children}</button>
  },
  TabsContent: passthrough,
}))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/card', () => ({ Card: passthrough }))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: passthrough }))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: () => null }))
mock.module('./tool-category-input', () => ({ ToolCategoryInput: () => null }))

let McpToolDialog: typeof import('./mcp-tool-dialog').McpToolDialog
beforeAll(async () => ({ McpToolDialog } = await import('./mcp-tool-dialog')))

const roots: Root[] = []
afterEach(() => {
  for (const root of roots.splice(0)) act(() => root.unmount())
  document.body.replaceChildren()
})

beforeEach(() => {
  listMcpTools.mockReset()
  toastInfo.mockReset()
  toastSuccess.mockReset()
})

function render(overrides: Partial<React.ComponentProps<typeof McpToolDialog>> = {}) {
  const props = {
    open: true,
    onOpenChange: mock(),
    onSave: mock(() => Promise.resolve()),
    ...overrides,
  }
  const container = document.body.appendChild(document.createElement('div'))
  const root = createRoot(container)
  roots.push(root)
  act(() => root.render(<McpToolDialog {...props} />))
  return { container, props }
}

function setInput(container: HTMLElement, id: string, value: string) {
  const input = container.querySelector<HTMLInputElement>(`#${id}`)!
  Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, value)
  input.dispatchEvent(new window.Event('input', { bubbles: true }))
}

function button(container: HTMLElement, text: string) {
  return [...container.querySelectorAll('button')].find((item) => item.textContent?.includes(text))!
}

const flush = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)) })

describe('McpToolDialog issue #255 coverage', () => {
  it('runs team, list-editing, cancel, and required-field callbacks', () => {
    const onOpenChange = mock()
    const onSelectedTeamChange = mock()
    const { container } = render({
      onOpenChange,
      onSelectedTeamChange,
      teams: [{ id: 'team-1', name: 'Alpha' }, { id: 'team-2', name: 'Beta' }],
      selectedTeamId: 'team-1',
    })

    act(() => {
      button(container, 'choose-team').click()
      button(container, 'mcpDialog.addArg').click()
      button(container, 'mcpDialog.addEnvVar').click()
      button(container, 'cancel').click()
      button(container, 'create').click()
    })

    expect(onSelectedTeamChange).toHaveBeenCalledWith('team-2')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(container.querySelector('#name')?.getAttribute('aria-invalid')).toBe('true')
    expect(container.textContent).toContain('error.nameRequired')
  })

  it('discovers tools and saves their stdio configuration', async () => {
    listMcpTools.mockResolvedValue({ tools: [{ name: 'search', description: 'Search docs' }] })
    const onSave = mock(() => Promise.resolve())
    const { container } = render({ onSave })

    act(() => {
      setInput(container, 'name', 'docs_server')
      setInput(container, 'displayName', 'Docs Server')
      setInput(container, 'command', 'bunx')
    })
    await act(async () => button(container, 'mcpDialog.fetchTools').click())
    await flush()

    expect(listMcpTools).toHaveBeenCalledWith({ transport: 'stdio', command: 'bunx', args: [], env: {} })
    expect(toastSuccess).toHaveBeenCalledWith('mcpDialog.toolsLoaded')
    expect(container.textContent).toContain('Search docs')

    await act(async () => button(container, 'create').click())
    await flush()
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'docs_server',
      display_name: 'Docs Server',
      description: '- search: Search docs',
      type: 'mcp',
      mcp_config: { transport: 'stdio', command: 'bunx', args: [], env: {} },
    }))
  })

  it('builds HTTP config and exercises dynamic header callbacks', async () => {
    listMcpTools.mockResolvedValue({ tools: [] })
    const { container } = render()

    act(() => button(container, 'mcpDialog.httpMode').click())
    act(() => {
      setInput(container, 'http-url', 'https://mcp.test')
      button(container, 'mcpDialog.addHeader').click()
    })
    const headerInputs = [...container.querySelectorAll<HTMLInputElement>('input[placeholder="mcpDialog.headerNamePlaceholder"]')]
    act(() => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(headerInputs[0], 'Authorization')
      headerInputs[0].dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await act(async () => button(container, 'mcpDialog.fetchTools').click())
    await flush()

    expect(listMcpTools).toHaveBeenCalledWith({
      transport: 'http',
      url: 'https://mcp.test',
      headers: { Authorization: '' },
    })
    expect(toastInfo).toHaveBeenCalledWith('mcpDialog.noToolsFound')
  })

  it('maps discovery and save errors, then permits a successful retry', async () => {
    listMcpTools.mockRejectedValue({ errors: { command: 'command failed' } })
    const onSave = mock()
      .mockRejectedValueOnce({ errors: { displayName: 'already used' } })
      .mockResolvedValueOnce(undefined)
    const { container } = render({ onSave })

    act(() => {
      setInput(container, 'name', 'remote_server')
      setInput(container, 'displayName', 'Remote Server')
      setInput(container, 'command', 'node')
    })
    await act(async () => button(container, 'mcpDialog.fetchTools').click())
    await flush()
    expect(container.textContent).toContain('command failed')

    await act(async () => button(container, 'create').click())
    await flush()
    expect(container.textContent).toContain('already used')

    await act(async () => button(container, 'create').click())
    await flush()
    expect(onSave).toHaveBeenCalledTimes(2)
  })
})

import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { ApiError } from '@/lib/api/client'

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => `${namespace}.${key}`,
}))
mock.module('lucide-react', () => ({
  ChevronDown: () => null,
  Loader2: () => null,
  Plus: () => null,
  Trash2: () => null,
}))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div role="dialog">{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <footer>{children}</footer>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <p role="alert">{children}</p> : null }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: ({ onChange }: { onChange: (value: string) => void }) => <button onClick={() => onChange('https://cdn.example/icon.png')}>upload</button> }))
mock.module('@/components/ui/input', () => ({ Input: ({ onChange, ...props }: React.ComponentProps<'input'>) => <input {...props} onChange={onChange} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label> }))
let selectHandlers: Array<((value: string) => void) | undefined> = []
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, value, ...props }: React.PropsWithChildren<{ onValueChange?: (value: string) => void; value?: string }>) => {
    selectHandlers.push(onValueChange)
    return <div data-select-value={value} {...props}>{children}</div>
  },
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props} data-value={value} onClick={() => selectHandlers.at(-1)?.(String(value))}>{children}</button>,
  SelectTrigger: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
  SelectValue: ({ children }: { children?: React.ReactNode }) => <span>{children}</span>,
}))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('./tool-category-input', () => ({
  ToolCategoryInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <input id="category" value={value} onChange={(event) => onChange(event.target.value)} />,
}))

import { HttpToolDialog } from './http-tool-dialog'

const renderers: ReactTestRenderer[] = []
globalThis.IS_REACT_ACT_ENVIRONMENT = true

function text(value: React.ReactNode): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(text).join('')
  if (React.isValidElement(value)) return text(value.props.children)
  return ''
}

function render(props: Partial<React.ComponentProps<typeof HttpToolDialog>> = {}) {
  selectHandlers = []
  const onOpenChange = mock(() => {})
  const onSave = mock(async () => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<HttpToolDialog open onOpenChange={onOpenChange} onSave={onSave} {...props} />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onOpenChange, onSave }
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => text(item.props.children).includes(label))!
const input = (renderer: ReactTestRenderer, props: Record<string, unknown>) => renderer.root.findAllByType('input').find((item) => Object.entries(props).every(([key, value]) => item.props[key] === value))!
const alertText = (renderer: ReactTestRenderer) => renderer.root.findAllByProps({ role: 'alert' }).map((item) => text(item.props.children)).join(' ')

function changeInput(renderer: ReactTestRenderer, props: Record<string, unknown>, value: string) {
  act(() => input(renderer, props).props.onChange({ target: { value, selectionStart: value.length } }))
}

function fillRequired(renderer: ReactTestRenderer) {
  changeInput(renderer, { id: 'name' }, 'weather_api')
  changeInput(renderer, { id: 'displayName' }, 'Weather API')
  changeInput(renderer, { placeholder: 'platform.tools.httpDialog.urlPlaceholder' }, 'https://api.example.test/weather')
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

describe('platform HttpToolDialog', () => {
  test('validates fields, selects a team, and saves headers, params, and parameters', async () => {
    const onSelectedTeamChange = mock(() => {})
    const { renderer, onSave } = render({
      teams: [{ id: 'team-1', name: 'Core Team' }],
      selectedTeamId: 'team-1',
      onSelectedTeamChange,
    })

    await act(async () => button(renderer, 'common.create').props.onClick())
    expect(alertText(renderer)).toContain('platform.tools.error.nameRequired')

    act(() => selectHandlers[0]?.('team-1'))
    fillRequired(renderer)
    changeInput(renderer, { id: 'description' }, 'Fetches weather')
    changeInput(renderer, { id: 'category' }, 'network')
    act(() => button(renderer, 'upload').props.onClick())
    await act(async () => button(renderer, 'platform.tools.httpDialog.addParameter').props.onClick())
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.paramName' }, 'city')
    act(() => renderer.root.findAllByType('input').find((item) => item.props.type === 'checkbox' && item.props.checked === false)!.props.onChange({ target: { checked: true } }))
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.paramDescription' }, 'City name')
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.keyPlaceholder' }, 'Authorization')
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.headerValuePlaceholder' }, 'Bearer {{city}}')
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.queryValuePlaceholder' }, '{{city}}')
    const keyInputs = renderer.root.findAllByProps({ placeholder: 'platform.tools.httpDialog.keyPlaceholder' })
    act(() => keyInputs[1]!.props.onChange({ target: { value: 'city' } }))

    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(onSelectedTeamChange).toHaveBeenCalledWith('team-1')
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'weather_api',
      display_name: 'Weather API',
      description: 'Fetches weather',
      icon: 'https://cdn.example/icon.png',
      category: 'network',
      is_enabled: true,
      type: 'custom',
      custom_type: 'http',
      http_config: expect.objectContaining({
        method: 'GET',
        url: 'https://api.example.test/weather',
        headers: { city: 'Bearer {{city}}' },
        query_params: {},
        timeout: 30,
        content_type: undefined,
      }),
      parameters: [{ name: 'city', type: 'string', required: true, description: 'City name' }],
    }))
  })

  test('saves multipart form fields for POST requests', async () => {
    const { renderer, onSave } = render()

    fillRequired(renderer)
    act(() => renderer.root.findByProps({ 'data-value': 'POST' }).props.onClick())
    const selects = renderer.root.findAll((node) => node.props['data-select-value'])
    act(() => selects.at(-1)!.findByProps({ 'data-value': 'multipart/form-data' }).props.onClick())
    await act(async () => button(renderer, 'platform.tools.httpDialog.addField').props.onClick())
    changeInput(renderer, { placeholder: 'platform.tools.httpDialog.fieldName' }, 'upload')
    act(() => renderer.root.findAllByProps({ 'data-value': 'file' }).at(-1)!.props.onClick())
    changeInput(renderer, { placeholder: '{{file}}' }, '{{attachment}}')

    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      http_config: expect.objectContaining({
        method: 'POST',
        content_type: 'multipart/form-data',
        body_template: undefined,
        form_fields: [{ name: 'upload', type: 'file', value: '{{attachment}}' }],
      }),
    }))
  })

  test('hydrates an existing tool and maps backend validation errors', async () => {
    const onSave = mock(async () => { throw new ApiError(1001, 'Validation failed', { errors: { 'http_config.content_type': 'Unsupported content type', parameters: 'Bad parameter' } }) })
    const { renderer } = render({
      onSave,
      tool: {
        id: 'tool-1', name: 'existing_tool', display_name: 'Existing Tool', description: 'Existing description', icon: '🔧', category: 'api',
        type: 'custom', custom_type: 'http', is_enabled: false, parameters: [{ name: 'payload', type: 'object', required: false, description: 'Payload' }], requires_config: false, config_fields: [],
        http_config: { method: 'PATCH', url: 'https://api.example.test/update', headers: { 'X-Test': '1' }, query_params: { dry_run: 'true' }, body_template: '{"ok":true}', timeout: 45, content_type: 'application/json' },
      },
    })

    expect(input(renderer, { id: 'name' }).props.disabled).toBe(true)
    expect(input(renderer, { id: 'enabled' }).props.checked).toBe(false)
    await act(async () => button(renderer, 'common.save').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'existing_tool',
      is_enabled: false,
      http_config: expect.objectContaining({ method: 'PATCH', timeout: 45, content_type: 'application/json' }),
      parameters: [{ name: 'payload', type: 'object', required: false, description: 'Payload' }],
    }))
    expect(alertText(renderer)).toContain('Unsupported content type')
    expect(alertText(renderer)).toContain('Bad parameter')
  })
})

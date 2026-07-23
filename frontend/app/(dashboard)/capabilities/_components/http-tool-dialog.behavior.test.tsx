import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'
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
mock.module('@/components/ui/input', () => ({ Input: (props: React.ComponentProps<'input'>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/number-input', () => ({ NumberInput: (props: { value: number | ''; onChange: (value: number | '') => void } & Omit<React.ComponentProps<'input'>, 'onChange' | 'value'>) => <input type="number" {...props} value={props.value} onChange={(event) => props.onChange(event.target.value === '' ? '' : Number(event.target.value))} /> }))
let selectOnValueChange: ((value: string) => void) | undefined
mock.module('@/components/ui/select', () => ({
  Select: ({ children, onValueChange, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
    selectOnValueChange = onValueChange as ((value: string) => void) | undefined
    return <div {...props}>{children}</div>
  },
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children, value, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props} data-value={value} onClick={() => selectOnValueChange?.(String(value))}>{children}</button>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  SelectValue: () => null,
}))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) => <input type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: React.ComponentProps<'textarea'>) => <textarea {...props} /> }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-category-input', () => ({
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

function changeInput(renderer: ReactTestRenderer, props: Record<string, unknown>, value: string) {
  act(() => input(renderer, props).props.onChange({ target: { value } }))
}

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
})

describe('HttpToolDialog', () => {
  test('validates required fields and saves a GET tool payload', async () => {
    const { renderer, onSave, onOpenChange } = render()

    await act(async () => button(renderer, 'common.create').props.onClick())
    expect(renderer.root.findAllByProps({ role: 'alert' }).length).toBeGreaterThan(0)

    changeInput(renderer, { id: 'name' }, 'weather_lookup')
    changeInput(renderer, { id: 'displayName' }, 'Weather Lookup')
    changeInput(renderer, { id: 'icon' }, '☁️')
    changeInput(renderer, { id: 'description' }, 'Fetches weather')
    changeInput(renderer, { id: 'category' }, 'network')
    changeInput(renderer, { placeholder: 'tools.httpDialog.urlPlaceholder' }, 'https://api.example.test/weather')
    act(() => renderer.root.findAllByProps({ placeholder: 'Key' })[0]!.props.onChange({ target: { value: 'Authorization' } }))
    act(() => renderer.root.findAllByProps({ placeholder: 'Value' })[0]!.props.onChange({ target: { value: 'Bearer test' } }))
    act(() => renderer.root.findAllByProps({ placeholder: 'Key' })[1]!.props.onChange({ target: { value: 'city' } }))
    act(() => renderer.root.findAllByProps({ placeholder: 'Value' })[1]!.props.onChange({ target: { value: '{{city}}' } }))

    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'weather_lookup',
      display_name: 'Weather Lookup',
      description: 'Fetches weather',
      icon: '☁️',
      category: 'network',
      is_enabled: true,
      type: 'custom',
      custom_type: 'http',
      http_config: {
        method: 'GET',
        url: 'https://api.example.test/weather',
        headers: { city: '{{city}}' },
        query_params: {},
        body_template: undefined,
        timeout: 30,
      },
    }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('saves POST body and omits empty timeout', async () => {
    const { renderer, onSave } = render()

    changeInput(renderer, { id: 'name' }, 'post_event')
    changeInput(renderer, { id: 'displayName' }, 'Post Event')
    changeInput(renderer, { placeholder: 'tools.httpDialog.urlPlaceholder' }, 'https://api.example.test/events')
    act(() => renderer.root.findByProps({ 'data-value': 'POST' }).props.onClick())
    act(() => renderer.root.findByType('textarea').props.onChange({ target: { value: '{"message":"{{message}}"}' } }))
    act(() => input(renderer, { id: 'timeout' }).props.onChange({ target: { value: '' } }))
    act(() => input(renderer, { id: 'enabled' }).props.onChange({ target: { checked: false } }))

    await act(async () => button(renderer, 'common.create').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      is_enabled: false,
      http_config: expect.objectContaining({
        method: 'POST',
        body_template: '{"message":"{{message}}"}',
        timeout: undefined,
      }),
    }))
  })

  test('hydrates an existing tool, keeps name immutable, and maps server validation errors', async () => {
    const onSave = mock(async () => { throw new ApiError(1001, 'Validation failed', { errors: { 'http_config.timeout': 'Timeout is too high' } }) })
    const { renderer } = render({
      onSave,
      tool: {
        id: 'tool-1', name: 'existing_tool', display_name: 'Existing Tool', description: 'Existing description', icon: '🔧', category: 'api',
        type: 'custom', custom_type: 'http', is_enabled: false, parameters: [], requires_config: false, config_fields: [],
        http_config: { method: 'PUT', url: 'https://api.example.test/update', headers: { 'X-Test': '1' }, query_params: { dry_run: 'true' }, body_template: '{"ok":true}', timeout: 45 },
      },
    })

    expect(input(renderer, { id: 'name' }).props.disabled).toBe(true)
    changeInput(renderer, { id: 'displayName' }, 'Existing Updated')
    await act(async () => button(renderer, 'common.save').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'existing_tool',
      display_name: 'Existing Updated',
      is_enabled: false,
      http_config: expect.objectContaining({ method: 'PUT', timeout: 45 }),
    }))
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((item) => text(item.props.children)).join(' ')).toContain('Timeout is too high')
  })
})

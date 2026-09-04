import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}))

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <>{children}</> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: Record<string, unknown>) => <input {...props} /> }))
mock.module('@/components/ui/textarea', () => ({ Textarea: (props: Record<string, unknown>) => <textarea {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/field', () => ({ FieldError: ({ children }: React.PropsWithChildren) => children ? <span role="alert">{children}</span> : null }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, id }: { checked: boolean; onCheckedChange: (checked: boolean) => void; id?: string }) =>
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange: (value: string) => void }>) =>
    <select value={value} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CollapsibleTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: () => <div /> }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => field !== key)),
  clearValidationErrorsByPrefix: (errors: Record<string, string>, prefix: string) => Object.fromEntries(Object.entries(errors).filter(([field]) => !field.startsWith(prefix))),
  normalizeValidationErrors: (error: unknown) => error as Record<string, string>,
  mapValidationErrors: (errors: Record<string, string>, paths: Record<string, string>) => Object.fromEntries(Object.entries(errors).map(([field, message]) => [paths[field] ?? field, message])),
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
mock.module('./tool-category-input', () => ({
  ToolCategoryInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <select data-category value={value} onChange={(event) => onChange(event.target.value)}><option value="api">api</option><option value="data">data</option></select>,
}))

const { HttpToolDialog } = await import('./http-tool-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
let onSave = mock(async () => undefined)
let onOpenChange = mock(() => undefined)

beforeEach(() => {
  onSave = mock(async () => undefined)
  onOpenChange = mock(() => undefined)
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(props: Partial<React.ComponentProps<typeof HttpToolDialog>> = {}) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<HttpToolDialog open onSave={onSave} onOpenChange={onOpenChange} {...props} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function input(renderer: ReactTestRenderer, id: string) {
  return renderer.root.findByProps({ id })
}

function change(node: ReturnType<typeof input>, value: string) {
  act(() => node.props.onChange({ target: { value, selectionStart: value.length } }))
}

function variableInputs(renderer: ReactTestRenderer, placeholder: string) {
  return renderer.root.findAllByProps({ placeholder }).filter((node) => typeof node.type === 'string')
}

function variableInput(renderer: ReactTestRenderer, placeholder: string) {
  return variableInputs(renderer, placeholder)[0]
}

function button(renderer: ReactTestRenderer, text: string) {
  return renderer.root.findAllByType('button').find((node) => node.children.some((child) => child === text))!
}

function selects(renderer: ReactTestRenderer) {
  return renderer.root.findAllByType('select')
}

async function save(renderer: ReactTestRenderer) {
  await act(async () => button(renderer, 'create').props.onClick())
}

describe('HTTP tool dialog', () => {
  test('validates required create fields and the tool-name boundary', async () => {
    const renderer = render()

    await save(renderer)
    expect(onSave).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(''))).toEqual(expect.arrayContaining([
      'error.nameRequired', 'form.displayNameRequired', 'form.urlRequired',
    ]))

    change(input(renderer, 'name'), '1 invalid')
    change(input(renderer, 'displayName'), 'Invalid')
    change(variableInput(renderer, 'httpDialog.urlPlaceholder'), 'https://example.test')
    await save(renderer)

    expect(onSave).not.toHaveBeenCalled()
    expect(input(renderer, 'name').props['aria-invalid']).toBe(true)
    expect(renderer.root.findAllByProps({ role: 'alert' }).some((node) => node.children.includes('error.invalidName'))).toBe(true)
  })

  test('creates a GET request with auth header, query parameter, timeout, and input parameter', async () => {
    const renderer = render()
    change(input(renderer, 'name'), 'lookup_user')
    change(input(renderer, 'displayName'), 'Lookup user')
    change(input(renderer, 'description'), 'Fetches a user')
    change(variableInput(renderer, 'httpDialog.urlPlaceholder'), 'https://api.test/users/{{user_id}}')

    const keyInputs = renderer.root.findAllByProps({ placeholder: 'httpDialog.keyPlaceholder' }).filter((node) => node.type === 'input')
    change(keyInputs[0], 'Authorization')
    change(variableInputs(renderer, 'httpDialog.headerValuePlaceholder')[0], 'Bearer {{token}}')
    change(keyInputs[1], 'expand')
    change(variableInputs(renderer, 'httpDialog.queryValuePlaceholder')[0], 'profile')
    change(input(renderer, 'timeout'), '45')

    act(() => button(renderer, 'httpDialog.addParameter').props.onClick())
    change(renderer.root.findByProps({ placeholder: 'httpDialog.paramName' }), 'user_id')
    change(renderer.root.findByProps({ placeholder: 'httpDialog.paramDescription' }), 'User identifier')
    const parameterSwitch = renderer.root.findAllByType('input').find((node) => node.props.type === 'checkbox' && !node.props.id)!
    act(() => parameterSwitch.props.onChange({ target: { checked: true } }))

    await save(renderer)

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({
      name: 'lookup_user', display_name: 'Lookup user', description: 'Fetches a user', type: 'custom', custom_type: 'http',
      parameters: [{ name: 'user_id', type: 'string', required: true, description: 'User identifier' }],
      http_config: {
        method: 'GET', url: 'https://api.test/users/{{user_id}}', headers: { Authorization: 'Bearer {{token}}' },
        query_params: { expand: 'profile' }, body_template: undefined, timeout: 45, content_type: undefined, form_fields: undefined,
      },
    }))
  })

  test('builds JSON POST body and filters blank request fields', async () => {
    const renderer = render()
    change(input(renderer, 'name'), 'create_user')
    change(input(renderer, 'displayName'), 'Create user')
    change(variableInput(renderer, 'httpDialog.urlPlaceholder'), 'https://api.test/users')
    act(() => selects(renderer).find((node) => node.props.value === 'GET')!.props.onChange({ target: { value: 'POST' } }))
    change(variableInput(renderer, 'httpDialog.bodyTemplatePlaceholder'), '{"name":"{{name}}"}')
    act(() => button(renderer, 'httpDialog.addHeader').props.onClick())
    change(renderer.root.findAllByProps({ placeholder: 'httpDialog.keyPlaceholder' })[1], 'X-Trace')
    change(variableInput(renderer, 'httpDialog.headerValuePlaceholder'), 'trace-1')

    await save(renderer)

    expect(onSave.mock.calls[0][0]).toEqual(expect.objectContaining({
      http_config: expect.objectContaining({
        method: 'POST', content_type: 'application/json', body_template: '{"name":"{{name}}"}', headers: { 'X-Trace': 'trace-1' },
      }),
    }))
  })

  test('builds multipart form fields and omits JSON body at the content-type boundary', async () => {
    const renderer = render()
    change(input(renderer, 'name'), 'upload_file')
    change(input(renderer, 'displayName'), 'Upload file')
    change(variableInput(renderer, 'httpDialog.urlPlaceholder'), 'https://api.test/upload')
    act(() => selects(renderer).find((node) => node.props.value === 'GET')!.props.onChange({ target: { value: 'POST' } }))
    act(() => selects(renderer).find((node) => node.props.value === 'application/json')!.props.onChange({ target: { value: 'multipart/form-data' } }))
    act(() => button(renderer, 'httpDialog.addField').props.onClick())
    change(renderer.root.findByProps({ placeholder: 'httpDialog.fieldName' }), 'caption')
    change(variableInput(renderer, '{{value}}'), '{{caption}}')
    act(() => button(renderer, 'httpDialog.addField').props.onClick())

    await save(renderer)

    expect(onSave.mock.calls[0][0]).toEqual(expect.objectContaining({
      http_config: expect.objectContaining({
        content_type: 'multipart/form-data', body_template: undefined,
        form_fields: [{ name: 'caption', type: 'text', value: '{{caption}}' }],
      }),
    }))
  })

  test('prefills edit state, preserves identity, and maps API validation failure without closing', async () => {
    const validationError = { display_name: 'Already used', 'http_config.timeout': 'Too large' }
    onSave = mock(async () => { throw validationError })
    const renderer = render({
      tool: {
        id: 'tool-1', name: 'existing_tool', display_name: 'Existing', description: 'Old', icon: '', category: 'data', is_enabled: false,
        type: 'custom', custom_type: 'http', parameters: [{ name: 'id', type: 'number', required: true }],
        http_config: { method: 'PATCH', url: 'https://old.test/{{id}}', headers: { 'X-Key': 'secret' }, query_params: { dry: '1' }, body_template: '{}', timeout: 12, content_type: 'application/json' },
      } as React.ComponentProps<typeof HttpToolDialog>['tool'],
    })

    expect(input(renderer, 'name').props.disabled).toBe(true)
    expect(input(renderer, 'name').props.value).toBe('existing_tool')
    expect(input(renderer, 'timeout').props.value).toBe(12)
    change(input(renderer, 'displayName'), 'Renamed')
    await act(async () => button(renderer, 'save').props.onClick())

    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ name: 'existing_tool', display_name: 'Renamed' }))
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(renderer.root.findAllByProps({ role: 'alert' }).map((node) => node.children.join(''))).toEqual(expect.arrayContaining(['Already used', 'Too large']))
  })

  test('propagates an unknown API failure and cancel closes the dialog', async () => {
    const failure = new Error('network down')
    onSave = mock(async () => { throw failure })
    const renderer = render()
    change(input(renderer, 'name'), 'network_tool')
    change(input(renderer, 'displayName'), 'Network tool')
    change(variableInput(renderer, 'httpDialog.urlPlaceholder'), 'https://api.test')

    await expect(save(renderer)).rejects.toBe(failure)
    act(() => button(renderer, 'cancel').props.onClick())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

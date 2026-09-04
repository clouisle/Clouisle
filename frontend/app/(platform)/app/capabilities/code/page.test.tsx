import React from 'react'
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestInstance, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const push = mock(() => undefined)
const getById = mock(() => Promise.resolve({}))
const createTool = mock(() => Promise.resolve({}))
const updateTool = mock(() => Promise.resolve({}))
const executeCode = mock(() => Promise.resolve({ success: true, result: 'ok' }))
const toastError = mock(() => undefined)
const toastSuccess = mock(() => undefined)

let toolId: string | null = null
let teamId: string | null = 'team-1'
let permissions = new Set(['tool:create', 'tool:update', 'tool:execute'])

class TestApiError extends Error {
  constructor(
    public code: number,
    message: string,
    public data?: { errors?: Record<string, string | string[]> }
  ) {
    super(message)
  }

  isValidationError() {
    return this.code === 1001
  }

  getFieldErrors() {
    return Object.fromEntries(
      Object.entries(this.data?.errors ?? {}).map(([field, value]) => [
        field,
        Array.isArray(value) ? value.join('; ') : value,
      ])
    )
  }
}

const router = { push }
mock.module('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => ({ get: (key: string) => key === 'id' ? toolId : null }),
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) =>
    values?.value ? `${key}:${values.value}` : key,
}))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/contexts/team-context', () => ({
  useTeam: () => ({ currentTeam: teamId ? { id: teamId } : null }),
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({ canPerform: (permission: string) => permissions.has(permission) }),
}))
mock.module('@/lib/api/tools', () => ({
  toolsApi: { getById, create: createTool, update: updateTool, executeCode },
}))
mock.module('@/lib/api', () => ({ ApiError: TestApiError }))
mock.module('@/lib/validation', () => ({
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
const Icon = () => null
mock.module('lucide-react', () => ({
  ArrowLeft: Icon,
  Save: Icon,
  Play: Icon,
  Loader2: Icon,
  FileCode: Icon,
  ChevronDown: Icon,
  ChevronRight: Icon,
  X: Icon,
  Plus: Icon,
  Trash2: Icon,
}))

const passthrough = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
  <div {...props}>{children}</div>

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) =>
    <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/textarea', () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}))
mock.module('@/components/ui/label', () => ({ Label: passthrough }))
mock.module('@/components/ui/badge', () => ({ Badge: passthrough }))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, id }: { checked: boolean; onCheckedChange: (value: boolean) => void; id?: string }) =>
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />,
}))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ checked, onCheckedChange, id }: { checked?: boolean; onCheckedChange: (value: boolean) => void; id?: string }) =>
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
  Collapsible: passthrough,
  CollapsibleContent: passthrough,
  CollapsibleTrigger: passthrough,
}))
mock.module('@/components/ui/image-upload', () => ({
  ImageUpload: ({ onChange }: { onChange: (value: string) => void }) =>
    <button data-testid="image-upload" onClick={() => onChange('https://images.test/tool.png')}>image</button>,
}))
mock.module('../_components/tool-category-input', () => ({
  ToolCategoryInput: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <select data-testid="category" value={value} onChange={(event) => onChange(event.target.value)}>
      <option value="code">code</option><option value="data">data</option>
    </select>,
}))
mock.module('@monaco-editor/react', () => ({
  default: ({ value, language, onChange }: { value: string; language: string; onChange: (value?: string) => void }) =>
    <textarea data-testid="editor" data-language={language} value={value} onChange={(event) => onChange(event.target.value)} />,
}))

const { default: CodeToolPage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

beforeEach(() => {
  toolId = null
  teamId = 'team-1'
  permissions = new Set(['tool:create', 'tool:update', 'tool:execute'])
  for (const fn of [push, getById, createTool, updateTool, executeCode, toastError, toastSuccess]) fn.mockClear()
  getById.mockImplementation(() => Promise.resolve({}))
  createTool.mockImplementation(() => Promise.resolve({}))
  updateTool.mockImplementation(() => Promise.resolve({}))
  executeCode.mockImplementation(() => Promise.resolve({ success: true, result: 'ok' }))
})

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

async function render() {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<CodeToolPage />)
    await Promise.resolve()
  })
  renderers.push(renderer!)
  return renderer!
}

function input(view: ReactTestRenderer, id: string) {
  return view.root.findByProps({ id })
}

function change(node: ReactTestInstance, value: string) {
  act(() => node.props.onChange({ target: { value } }))
}

function button(view: ReactTestRenderer, text: string) {
  return view.root.findAllByType('button').find((node) =>
    node.findAll((child) => child.children.includes(text)).length > 0
  )!
}

function textareas(view: ReactTestRenderer) {
  return view.root.findAllByType('textarea')
}

function testInput(view: ReactTestRenderer) {
  return textareas(view).find((node) => node.props.placeholder === '{"input": "test value"}')!
}

function editor(view: ReactTestRenderer) {
  return view.root.findByProps({ 'data-testid': 'editor' })
}

async function click(node: ReactTestInstance) {
  await act(async () => node.props.onClick())
}

function fillIdentity(view: ReactTestRenderer, name = 'safe_tool') {
  change(input(view, 'name'), name)
  change(input(view, 'displayName'), 'Safe tool')
  change(input(view, 'description'), 'Processes test input')
}

function output(view: ReactTestRenderer) {
  return view.root.findAllByType('pre')[0]?.children.join('') ?? ''
}

describe('platform code tool page', () => {
  test('keeps platform navigation and permission boundaries isolated', async () => {
    permissions = new Set()
    const view = await render()

    expect(view.root.findAllByType('button').some((node) => node.children.includes('codeEditor.run'))).toBe(false)
    expect(view.root.findAllByType('button').some((node) => node.children.includes('save'))).toBe(false)

    await click(view.root.findAllByType('button')[0])
    expect(push).toHaveBeenCalledWith('/app/capabilities')
  })

  test('creates a code tool with normalized runtime settings and filtered values', async () => {
    const view = await render()
    fillIdentity(view)
    change(input(view, 'pythonPackageIndexUrl'), ' https://packages.test/simple/// ')
    change(input(view, 'nodePackageRegistryUrl'), 'https://registry.test/')
    change(input(view, 'timeoutSeconds'), '45')
    change(input(view, 'diskMb'), '0')
    change(input(view, 'maxStdoutKb'), '512')
    change(input(view, 'maxStderrKb'), 'not-a-number')
    change(view.root.findByProps({ id: 'pythonPackages' }), ' requests==2.32.0\n\n')
    change(view.root.findByProps({ id: 'jsPackages' }), 'zod@3.24.0')
    change(view.root.findByProps({ id: 'command' }), 'node\nscript.js')
    change(editor(view), 'return { ok: true }')
    await click(view.root.findByProps({ 'data-testid': 'image-upload' }))
    change(view.root.findByProps({ 'data-testid': 'category' }), 'data')

    await click(button(view, 'codeEditor.addArtifact'))
    const artifactPath = view.root.findByProps({ placeholder: 'codeEditor.artifactPathPlaceholder' })
    const artifactDescription = view.root.findByProps({ placeholder: 'codeEditor.artifactDescription' })
    change(artifactPath, ' /workspace/report.json ')
    change(artifactDescription, ' result file ')
    act(() => view.root.findAllByProps({ id: 'artifact-optional-0' }).find((node) => node.type === 'input')!.props.onChange({ target: { checked: true } }))

    await click(button(view, 'save'))

    expect(createTool).toHaveBeenCalledWith('team-1', expect.objectContaining({
      name: 'safe_tool',
      display_name: 'Safe tool',
      description: 'Processes test input',
      icon: 'https://images.test/tool.png',
      category: 'data',
      type: 'custom',
      custom_type: 'code',
      code_config: {
        language: 'javascript',
        code: 'return { ok: true }',
        python_packages: ['requests==2.32.0'],
        js_packages: ['zod@3.24.0'],
        python_package_index_url: 'https://packages.test/simple',
        node_package_registry_url: 'https://registry.test',
        command: ['node', 'script.js'],
        artifacts: [{ path: '/workspace/report.json', optional: true, description: 'result file' }],
        limits: { timeout_seconds: 45, disk_mb: 1024, max_stdout_kb: 512, max_stderr_kb: 256 },
      },
    }))
    expect(toastSuccess).toHaveBeenCalledWith('successMessages.created')
    expect(push).toHaveBeenCalledWith('/app/capabilities')
  })

  test('validates identity, team, duplicate parameters, packages, URLs, and artifacts', async () => {
    teamId = null
    const noTeamView = await render()
    change(input(noTeamView, 'name'), 'valid_tool')
    await click(button(noTeamView, 'save'))
    expect(toastError).toHaveBeenCalledWith('error.noTeamSelected')
    act(() => noTeamView.unmount())
    renderers.pop()

    teamId = 'team-1'
    const view = await render()
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith('error.nameRequired')
    expect(input(view, 'name').props['aria-invalid']).toBe(true)

    change(input(view, 'name'), '1 invalid')
    await click(button(view, 'save'))
    expect(view.root.findAllByType('p').some((node) => node.children.includes('error.invalidName'))).toBe(true)

    fillIdentity(view)
    await click(button(view, 'codeEditor.addParameter'))
    const parameterNames = view.root.findAllByProps({ placeholder: 'codeEditor.paramName' }).filter((node) => node.type === 'input')
    change(parameterNames[1], 'input')
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith('error.duplicateParamName')
    change(parameterNames[1], 'count')

    change(view.root.findByProps({ id: 'pythonPackages' }), 'requests')
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith('codeEditor.invalidPythonPackage:requests')
    change(view.root.findByProps({ id: 'pythonPackages' }), '')

    change(view.root.findByProps({ id: 'jsPackages' }), '@scope/pkg')
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith('codeEditor.invalidJsPackage:@scope/pkg')
    change(view.root.findByProps({ id: 'jsPackages' }), '')

    change(input(view, 'pythonPackageIndexUrl'), 'https://user:password@packages.test')
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith(expect.stringContaining('codeEditor.invalidPackageSourceUrl'))
    change(input(view, 'pythonPackageIndexUrl'), '')

    await click(button(view, 'codeEditor.addArtifact'))
    change(view.root.findByProps({ placeholder: 'codeEditor.artifactPathPlaceholder' }), '/tmp/result.txt')
    await click(button(view, 'save'))
    expect(toastError).toHaveBeenCalledWith('codeEditor.invalidArtifactPath:/tmp/result.txt')
    expect(createTool).not.toHaveBeenCalled()
  })

  test('loads and updates an existing tool while preserving edited code across language changes', async () => {
    toolId = 'tool-7'
    getById.mockImplementation(() => Promise.resolve({
      id: 'tool-7', name: 'existing_tool', display_name: 'Existing tool', description: 'Existing description',
      icon: '', category: 'code', is_enabled: false,
      parameters: [{ name: 'value', type: 'number', description: 'Value', required: true }],
      code_config: {
        language: 'python', code: 'return 7', python_packages: ['numpy==2.0.0'], js_packages: [],
        command: ['python', 'main.py'], artifacts: [], limits: { timeout_seconds: 12, disk_mb: 256, max_stdout_kb: 64, max_stderr_kb: 32 },
      },
    }))

    const view = await render()
    expect(getById).toHaveBeenCalledWith('tool-7')
    expect(input(view, 'name').props.disabled).toBe(true)
    expect(input(view, 'name').props.value).toBe('existing_tool')
    expect(editor(view).props.value).toBe('return 7')

    const languageSelect = view.root.findAllByType('select').find((node) => node.props.value === 'python')!
    act(() => languageSelect.props.onChange({ target: { value: 'javascript' } }))
    expect(editor(view).props.value).toBe('return 7')
    change(input(view, 'displayName'), 'Updated tool')
    await click(button(view, 'save'))

    expect(updateTool).toHaveBeenCalledWith('tool-7', expect.objectContaining({
      name: 'existing_tool', display_name: 'Updated tool', is_enabled: false,
      code_config: expect.objectContaining({
        language: 'javascript', code: 'return 7',
        limits: { timeout_seconds: 12, disk_mb: 256, max_stdout_kb: 64, max_stderr_kb: 32 },
      }),
    }))
    expect(toastSuccess).toHaveBeenCalledWith('successMessages.updated')
    expect(push).not.toHaveBeenCalled()
  })

  test('redirects to the platform capability list when edit loading fails', async () => {
    toolId = 'missing-tool'
    getById.mockImplementation(() => Promise.reject(new Error('not found')))

    await render()

    expect(push).toHaveBeenCalledWith('/app/capabilities')
  })

  test('runs code and formats logs, structured results, artifacts, duration, and execution errors', async () => {
    executeCode.mockImplementationOnce(() => Promise.resolve({
      success: true,
      logs: 'started',
      result: { answer: 42 },
      artifacts: [{ path: '/workspace/result.json' }],
      duration_ms: 18,
    }))
    const view = await render()
    change(input(view, 'timeoutSeconds'), '5')
    change(testInput(view), '{"input":"sample"}')

    await click(button(view, 'codeEditor.run'))

    expect(executeCode).toHaveBeenCalledWith(expect.objectContaining({
      language: 'javascript', params: { input: 'sample' }, timeout: 5, client_timeout_ms: 120000,
      limits: { timeout_seconds: 5, disk_mb: 1024, max_stdout_kb: 256, max_stderr_kb: 256 },
    }))
    expect(output(view)).toContain('codeEditor.logsLabel:\nstarted')
    expect(output(view)).toContain('"answer": 42')
    expect(output(view)).toContain('/workspace/result.json')
    expect(output(view)).toContain('codeEditor.durationLabel: 18ms')

    executeCode.mockImplementationOnce(() => Promise.resolve({ success: false, error: 'sandbox stopped' }))
    await click(button(view, 'codeEditor.run'))
    expect(output(view)).toContain('sandbox stopped')
  })

  test('handles invalid JSON, runtime rejection, API validation mapping, and unknown failures', async () => {
    const view = await render()
    change(testInput(view), '{bad json')
    await click(button(view, 'codeEditor.run'))
    expect(output(view)).toBe('codeEditor.errorLabel: codeEditor.invalidJsonInput')
    expect(executeCode).not.toHaveBeenCalled()

    change(testInput(view), '{}')
    change(view.root.findByProps({ id: 'jsPackages' }), 'invalid-package')
    await click(button(view, 'codeEditor.run'))
    expect(output(view)).toContain('codeEditor.invalidJsPackage:invalid-package')
    change(view.root.findByProps({ id: 'jsPackages' }), '')

    executeCode.mockImplementationOnce(() => Promise.reject(new TestApiError(1001, 'invalid', {
      errors: { params: 'Input is required', command: 'Command rejected', 'limits.timeout_seconds': 'Too large' },
    })))
    await click(button(view, 'codeEditor.run'))
    expect(testInput(view).props['aria-invalid']).toBe(true)
    expect(view.root.findAllByType('p').map((node) => node.children.join(''))).toEqual(expect.arrayContaining([
      'Input is required', 'Command rejected', 'Too large',
    ]))

    change(testInput(view), '{}')
    expect(testInput(view).props['aria-invalid']).toBe(false)
    executeCode.mockImplementationOnce(() => Promise.reject(new Error('network unavailable')))
    await click(button(view, 'codeEditor.run'))
    expect(output(view)).toBe('codeEditor.errorLabel: network unavailable')
  })

  test('maps save validation errors and supports parameter templates and removal interactions', async () => {
    createTool.mockImplementationOnce(() => Promise.reject(new TestApiError(1001, 'invalid', {
      errors: { display_name: 'Already used', unknown_field: ['Invalid value', 'Try another'] },
    })))
    const view = await render()
    fillIdentity(view)
    await click(button(view, 'save'))

    expect(input(view, 'displayName').props['aria-invalid']).toBe(true)
    expect(toastError).toHaveBeenCalledWith('Already used, Invalid value; Try another')
    expect(view.root.findAllByType('p').some((node) => node.children.includes('Invalid value; Try another'))).toBe(true)

    change(input(view, 'displayName'), 'Available name')
    expect(input(view, 'displayName').props['aria-invalid']).toBe(false)

    await click(button(view, 'codeEditor.addParameter'))
    const parameterNames = view.root.findAllByProps({ placeholder: 'codeEditor.paramName' })
    change(parameterNames[1], 'count')
    const parameterType = view.root.findAllByType('select').find((node) => node.props.value === 'string' && node !== view.root.findAllByType('select')[0])!
    act(() => parameterType.props.onChange({ target: { value: 'integer' } }))
    await click(button(view, 'codeEditor.generateTest'))
    expect(testInput(view).props.value).toContain('"count": 0')

    const parameterCards = view.root.findAll((node) =>
      node.type === 'div' && node.props.className === 'p-2 rounded-md border bg-background space-y-2'
    )
    const removeButton = parameterCards[1].findAllByType('button')[0]
    act(() => removeButton.props.onClick())
    expect(view.root.findAllByProps({ placeholder: 'codeEditor.paramName' }).filter((node) => node.type === 'input')).toHaveLength(1)
  })
})

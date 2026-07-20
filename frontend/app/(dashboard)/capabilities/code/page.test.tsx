import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const push = mock()
const getTeams = mock()
const getById = mock()
const createTool = mock()
const updateTool = mock()
const executeCode = mock()
const toastError = mock()
const toastSuccess = mock()
const canPerform = mock(() => true)
let query: Record<string, string | null> = { id: null, teamId: null }
const router = { push }

class ApiError extends Error {
  constructor(public code: number, message: string, public data?: { errors?: Record<string, string | string[]> }) {
    super(message)
  }
  isValidationError() { return this.code === 1001 }
  getFieldErrors() {
    return Object.fromEntries(Object.entries(this.data?.errors ?? {}).map(([field, value]) => [field, Array.isArray(value) ? value.join('; ') : value]))
  }
}

mock.module('next/navigation', () => ({
  useRouter: () => router,
  useSearchParams: () => ({ get: (key: string) => query[key] }),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string, values?: Record<string, unknown>) => values ? `${key}:${JSON.stringify(values)}` : key }))
mock.module('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }))
mock.module('@/lib/api', () => ({ ApiError }))
mock.module('@/lib/api/admin', () => ({
  adminToolsApi: { getById, create: createTool, update: updateTool, executeCode },
  teamsApi: { getTeams },
}))
mock.module('@/components/permission-guard', () => ({ useCanPerform: () => ({ canPerform }) }))
mock.module('@/components/auth/permission-guard', () => ({ RoutePermissionGuard: ({ children }: React.PropsWithChildren) => <>{children}</> }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/lib/validation', () => ({ formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}` }))
mock.module('lucide-react', () => ({
  ArrowLeft: () => null, Save: () => null, Play: () => null, Loader2: () => <span data-loader />,
  FileCode: () => null, ChevronDown: () => null, ChevronRight: () => null, X: () => null,
  Plus: () => null, Trash2: () => null,
}))

function element(tag: keyof React.JSX.IntrinsicElements) {
  return function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
}
const passthrough = ({ children }: React.PropsWithChildren) => <>{children}</>
const Select = ({ children }: React.PropsWithChildren<{ value?: string; onValueChange?: (value: string) => void }>) => <>{children}</>
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/switch', () => ({ Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (value: boolean) => void }) => <input type="checkbox" checked={checked} onChange={() => onCheckedChange(!checked)} {...props} /> }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: ({ checked, onCheckedChange, ...props }: { checked?: boolean; onCheckedChange: (value: boolean) => void }) => <input type="checkbox" checked={checked} onChange={() => onCheckedChange(!checked)} {...props} /> }))
mock.module('@/components/ui/badge', () => ({ Badge: element('span') }))
mock.module('@/components/ui/select', () => ({ Select, SelectContent: passthrough, SelectItem: passthrough, SelectTrigger: passthrough, SelectValue: passthrough }))
mock.module('@/components/ui/collapsible', () => ({ Collapsible: passthrough, CollapsibleContent: passthrough, CollapsibleTrigger: element('button') }))
mock.module('@/components/ui/image-upload', () => ({ ImageUpload: ({ onChange }: { onChange: (value: string) => void }) => <button data-image-upload onClick={() => onChange('https://cdn.example.test/icon.png')}>image</button> }))
mock.module('@/app/(platform)/app/capabilities/_components/tool-category-input', () => ({ ToolCategoryInput: ({ onChange }: { onChange: (value: string) => void }) => <button data-category onClick={() => onChange('utility')}>category</button> }))
mock.module('@monaco-editor/react', () => ({ default: ({ value, onChange, language }: { value: string; onChange: (value?: string) => void; language: string }) => <textarea data-editor={language} value={value} onChange={(event) => onChange(event.target.value)} /> }))

const { default: CodeToolPage } = await import('./page')
globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer | undefined
const teams = [{ id: 'team-1', name: 'Alpha' }, { id: 'team-2', name: 'Beta' }]

function render() {
  act(() => { renderer = create(<CodeToolPage />) })
  return renderer!
}
const flush = async () => { await act(async () => {}) }
const byId = (id: string) => renderer!.root.findByProps({ id })
const change = (id: string, value: string) => act(() => byId(id).props.onChange({ target: { value } }))
const nodeText = (node: ReactTestRenderer['root']): string => node.children.map((child) => typeof child === 'string' ? child : nodeText(child)).join('')
const buttons = (text: string) => renderer!.root.findAllByType('button').filter((node) => nodeText(node) === text)
const click = async (text: string, index = 0) => { await act(async () => buttons(text)[index].props.onClick()) }
const output = () => JSON.stringify(renderer!.toJSON())

beforeEach(() => {
  query = { id: null, teamId: null }
  for (const fn of [push, getTeams, getById, createTool, updateTool, executeCode, toastError, toastSuccess, canPerform]) fn.mockReset()
  canPerform.mockReturnValue(true)
  getTeams.mockResolvedValue({ items: teams })
  createTool.mockResolvedValue({})
  updateTool.mockResolvedValue({})
})
afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
})

describe('CodeToolPage', () => {
  test('creates a configured code tool and supports editor interactions', async () => {
    render()
    await flush()
    expect(getTeams).toHaveBeenCalledWith(1, 100)

    change('name', 'report_tool')
    change('displayName', 'Report Tool')
    change('description', ' Generates reports ')
    change('pythonPackages', ' requests==2.32.0\n\n')
    change('jsPackages', 'lodash@4.17.21')
    change('pythonPackageIndexUrl', 'https://packages.example.test///')
    change('nodePackageRegistryUrl', 'https://npm.example.test/')
    change('command', 'python\nmain.py')
    change('timeoutSeconds', '12')
    change('diskMb', '2048')
    change('maxStdoutKb', '512')
    change('maxStderrKb', '128')
    act(() => renderer!.root.findByProps({ 'data-image-upload': true }).props.onClick())
    act(() => renderer!.root.findByProps({ 'data-category': true }).props.onClick())
    act(() => renderer!.root.findAllByType('input').find((node) => node.props.id === 'enabled' && node.props.type === 'checkbox')!.props.onChange())
    act(() => renderer!.root.findByProps({ 'data-editor': 'javascript' }).props.onChange({ target: { value: 'return params' } }))

    await click('codeEditor.addArtifact')
    const artifactPath = renderer!.root.findByProps({ placeholder: 'codeEditor.artifactPathPlaceholder' })
    const artifactDescription = renderer!.root.findByProps({ placeholder: 'codeEditor.artifactDescription' })
    act(() => artifactPath.props.onChange({ target: { value: ' /workspace/report.csv ' } }))
    act(() => artifactDescription.props.onChange({ target: { value: ' report ' } }))
    act(() => renderer!.root.findAllByType('input').find((node) => node.props.id === 'artifact-optional-0')!.props.onChange())

    await click('save')

    expect(createTool).toHaveBeenCalledTimes(1)
    const [teamId, data] = createTool.mock.calls[0]
    expect(teamId).toBe('team-1')
    expect(data).toMatchObject({
      name: 'report_tool', display_name: 'Report Tool', description: 'Generates reports',
      icon: 'https://cdn.example.test/icon.png', category: 'utility', is_enabled: false,
      code_config: {
        code: 'return params', python_packages: ['requests==2.32.0'], js_packages: ['lodash@4.17.21'],
        python_package_index_url: 'https://packages.example.test', node_package_registry_url: 'https://npm.example.test',
        command: ['python', 'main.py'], limits: { timeout_seconds: 12, disk_mb: 2048, max_stdout_kb: 512, max_stderr_kb: 128 },
        artifacts: [{ path: '/workspace/report.csv', optional: true, description: 'report' }],
      },
    })
    expect(toastSuccess).toHaveBeenCalledWith('success.created')
    expect(push).toHaveBeenCalledWith('/capabilities')
  })

  test('blocks invalid names, duplicate parameters, packages, URLs, and artifact paths', async () => {
    render()
    await flush()

    await click('save')
    expect(toastError).toHaveBeenLastCalledWith('error.nameRequired')
    expect(byId('name').props['aria-invalid']).toBe(true)

    change('name', '9 invalid')
    await click('save')
    expect(output()).toContain('error.invalidName')

    change('name', 'valid_name')
    await click('codeEditor.addParameter')
    const parameterNames = renderer!.root.findAllByType('input').filter((node) => node.props.placeholder === 'codeEditor.paramName')
    act(() => parameterNames[1].props.onChange({ target: { value: 'input' } }))
    await click('save')
    expect(toastError).toHaveBeenLastCalledWith('error.duplicateParamName')

    act(() => parameterNames[1].props.onChange({ target: { value: '' } }))
    change('pythonPackages', 'requests')
    await click('save')
    expect(toastError.mock.calls.at(-1)?.[0]).toContain('codeEditor.invalidPythonPackage')

    change('pythonPackages', 'requests==2.0')
    change('jsPackages', '@scope')
    await click('save')
    expect(toastError.mock.calls.at(-1)?.[0]).toContain('codeEditor.invalidJsPackage')

    change('jsPackages', 'pkg@1.0')
    change('pythonPackageIndexUrl', 'https://user:secret@example.test')
    await click('save')
    expect(toastError.mock.calls.at(-1)?.[0]).toContain('codeEditor.invalidPackageSourceUrl')

    change('pythonPackageIndexUrl', '')
    change('nodePackageRegistryUrl', 'file:///tmp/packages')
    await click('save')
    expect(toastError.mock.calls.at(-1)?.[0]).toContain('codeEditor.invalidPackageSourceUrl')

    change('nodePackageRegistryUrl', '')
    await click('codeEditor.addArtifact')
    act(() => renderer!.root.findByProps({ placeholder: 'codeEditor.artifactPathPlaceholder' }).props.onChange({ target: { value: '/tmp/result' } }))
    await click('save')
    expect(toastError.mock.calls.at(-1)?.[0]).toContain('codeEditor.invalidArtifactPath')
    expect(createTool).not.toHaveBeenCalled()
  })

  test('runs code, applies numeric fallbacks, and formats all successful output fields', async () => {
    executeCode.mockResolvedValue({
      success: true, logs: 'safe log', result: { answer: 42 },
      artifacts: [{ path: '/workspace/result.txt' }], duration_ms: 25,
    })
    render()
    await flush()
    change('timeoutSeconds', '0')
    change('diskMb', 'NaN')
    change('maxStdoutKb', '-1')
    change('maxStderrKb', '')
    await click('codeEditor.run')

    expect(executeCode).toHaveBeenCalledWith(expect.objectContaining({
      params: { input: 'test' }, timeout: 30, client_timeout_ms: 120000,
      limits: { timeout_seconds: 30, disk_mb: 1024, max_stdout_kb: 256, max_stderr_kb: 256 },
    }))
    expect(output()).toContain('safe log')
    expect(output()).toContain('answer')
    expect(output()).toContain('/workspace/result.txt')
    expect(output()).toContain('25ms')

    const clearButton = renderer!.root.findAllByType('button').find((node) => node.props.className === 'h-5 w-5 shrink-0')!
    act(() => clearButton.props.onClick())
    expect(output()).toContain('codeEditor.noOutput')
  })

  test('handles invalid run input, runtime validation, failed results, and request failures', async () => {
    render()
    await flush()
    const testInput = renderer!.root.findByProps({ placeholder: '{"input": "test value"}' })
    act(() => testInput.props.onChange({ target: { value: '{bad' } }))
    await click('codeEditor.run')
    expect(output()).toContain('codeEditor.invalidJsonInput')
    expect(executeCode).not.toHaveBeenCalled()

    act(() => testInput.props.onChange({ target: { value: '{}' } }))
    change('pythonPackages', 'bad-package')
    await click('codeEditor.run')
    expect(output()).toContain('codeEditor.invalidPythonPackage')

    change('pythonPackages', '')
    executeCode.mockResolvedValueOnce({ success: false, error: '' })
    await click('codeEditor.run')
    expect(output()).toContain('codeEditor.executionFailed')

    executeCode.mockRejectedValueOnce(new Error('sandbox unavailable'))
    await click('codeEditor.run')
    expect(output()).toContain('sandbox unavailable')

    executeCode.mockRejectedValueOnce('unknown')
    await click('codeEditor.run')
    expect(output()).toContain('codeEditor.executionFailed')
  })

  test('maps save and execute validation errors to fields without exposing request details', async () => {
    render()
    await flush()
    change('name', 'valid_tool')
    createTool.mockRejectedValueOnce(new ApiError(1001, 'invalid', { errors: { display_name: 'Display required', unknown: ['Bad value', 'Again'] } }))
    await click('save')
    expect(toastError).toHaveBeenCalledWith('Display required, Bad value; Again')
    expect(output()).toContain('Display required')
    expect(output()).toContain('unknown: Bad value; Again')

    executeCode.mockRejectedValueOnce(new ApiError(1001, 'invalid', { errors: {
      params: 'Input required', command: 'Command invalid', 'limits.timeout_seconds': 'Too high', other: 'Other invalid',
    } }))
    await click('codeEditor.run')
    expect(renderer!.root.findByProps({ placeholder: '{"input": "test value"}' }).props['aria-invalid']).toBe(true)
    expect(byId('command').props['aria-invalid']).toBe(true)
    expect(byId('timeoutSeconds').props['aria-invalid']).toBe(true)
    expect(output()).toContain('Other invalid')
    expect(output()).toContain('Input required')
  })

  test('loads and updates an existing tool, including language and collection controls', async () => {
    query = { id: 'tool-1', teamId: 'team-2' }
    getById.mockResolvedValue({
      name: 'loaded_tool', display_name: 'Loaded Tool', description: 'Loaded', icon: 'L', category: 'code', is_enabled: true,
      parameters: [
        { name: 'text', type: 'string', default: 'hello', required: true },
        { name: 'count', type: 'number', required: false },
        { name: 'whole', type: 'integer', default: 3, required: false },
        { name: 'active', type: 'boolean', required: false },
        { name: 'items', type: 'array', required: false },
        { name: 'config', type: 'object', required: false },
        { name: 'other', type: 'unknown', required: false },
      ],
      code_config: {
        language: 'python', code: 'return 1', python_packages: ['requests==2.0'], js_packages: [],
        command: ['python', 'main.py'], limits: { timeout_seconds: 5, disk_mb: 64, max_stdout_kb: 8, max_stderr_kb: 9 },
        artifacts: [{ path: '/workspace/old.txt', optional: false }],
      },
    })
    render()
    expect(output()).toContain('data-loader')
    await flush()

    expect(getById).toHaveBeenCalledWith('tool-1')
    expect(byId('name').props.disabled).toBe(true)
    await click('codeEditor.generateTest')
    const generated = JSON.parse(renderer!.root.findByProps({ placeholder: '{"input": "test value"}' }).props.value)
    expect(generated).toEqual({ text: 'hello', count: 0, whole: 3, active: false, items: [], config: {}, other: null })

    const languageSelect = renderer!.root.findAllByType(Select).find((node) => node.props.value === 'python')!
    act(() => languageSelect.props.onValueChange('javascript'))
    expect(renderer!.root.findByProps({ 'data-editor': 'javascript' }).props.value).toBe('return 1')

    await click('codeEditor.addParameter')
    const removeButtons = renderer!.root.findAllByType('button').filter((node) => node.props.className === 'h-7 w-7 shrink-0')
    act(() => removeButtons.at(-1)!.props.onClick())
    act(() => renderer!.root.findAllByType('input').find((node) => node.props.id === 'required-0')!.props.onChange())
    act(() => renderer!.root.findAllByType('input').find((node) => node.props.placeholder === 'codeEditor.paramDescription')!.props.onChange({ target: { value: 'changed' } }))

    const artifactRemove = renderer!.root.findAllByType('button').find((node) => node.props.className === 'h-7 w-7 shrink-0')!
    act(() => artifactRemove.props.onClick())
    await click('save')
    expect(updateTool).toHaveBeenCalledWith('tool-1', expect.objectContaining({ name: 'loaded_tool' }))
    expect(toastSuccess).toHaveBeenCalledWith('success.updated')
  })

  test('redirects after a load failure and tolerates a teams API failure', async () => {
    query = { id: 'missing', teamId: null }
    getById.mockRejectedValue(new Error('not found'))
    getTeams.mockRejectedValue(new Error('offline'))
    render()
    await flush()
    expect(push).toHaveBeenCalledWith('/capabilities')
    expect(output()).not.toContain('data-loader')
  })

  test('respects action permissions and keeps back navigation available', async () => {
    canPerform.mockImplementation((permission: string) => !permission.endsWith(':create') && !permission.endsWith(':execute'))
    render()
    await flush()
    expect(buttons('save')).toHaveLength(0)
    expect(buttons('codeEditor.run')).toHaveLength(0)

    const back = renderer!.root.findAllByType('button')[0]
    act(() => back.props.onClick())
    expect(push).toHaveBeenCalledWith('/capabilities')
  })
})

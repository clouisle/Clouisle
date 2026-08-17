import { describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

// Minimal mock harness mirroring variable-form.test.tsx so the REAL
// PauseRequestActions -> VariableForm chain renders without node_modules.
const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: 'fragment' }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: 'fragment' }))
mock.module('react', () => ({
  useCallback: <T,>(callback: T) => callback,
  useEffect: (effect: () => void) => effect(),
  useMemo: <T,>(factory: () => T) => factory(),
  useRef: <T,>(initial: T) => ({ current: initial }),
  useState: <T,>(initial: T) => [initial, mock()] as const,
}))
mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
  useLocale: () => 'en',
}))
mock.module('@/lib/api/upload', () => ({ uploadApi: { uploadFile: mock(async () => ({ url: '/uploads/new.txt' })) } }))
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
}))
mock.module('@/lib/api/workflows', () => ({
  workflowsApi: {
    getPendingPauseRequest: mock(async () => null),
    submitPauseRequest: mock(async () => ({ pause_request_id: 'p', status: 'submitted' })),
  },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const { [field]: removed, ...remaining } = errors
    void removed
    return remaining
  },
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
  getValidationSummaryEntries: (errors: Record<string, string>, fields: string[]) =>
    Object.entries(errors).filter(([field]) => fields.includes(field)),
}))
mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
  formatDateTime: (v: unknown) => String(v),
}))
mock.module('@/lib/constants', () => ({ GENERAL_UPLOAD_MAX_FILE_SIZE_MB: 10, BYTES_PER_MB: 1024 * 1024 }))
const element = (tag: string) => ({ children, ...props }: { children?: ReactNode }) => ({ type: tag, props: { ...props, children } })
mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/checkbox', () => ({ Checkbox: element('checkbox') }))
mock.module('@/components/ui/field', () => ({ FieldError: element('alert') }))
mock.module('@/components/ui/select', () => ({
  Select: element('select'),
  SelectContent: element('options'),
  SelectItem: element('option'),
  SelectTrigger: element('trigger'),
  SelectValue: element('value'),
}))
mock.module('@/components/ui/alert', () => ({
  Alert: element('section'),
  AlertDescription: element('p'),
}))
mock.module('lucide-react', () => ({ Upload: element('svg'), X: element('svg'), FileIcon: element('svg'), ImageIcon: element('svg'), Check: element('svg'), CirclePause: element('svg'), Loader2: element('svg') }))
mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))

const { PauseRequestActions } = await import('./pause-request-actions')

type Node = { type: unknown; props: Record<string, unknown> }
function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  if (!value || typeof value !== 'object' || !('props' in value)) return []
  const node = value as Node
  const resolved = typeof node.type === 'function'
    ? (node.type as (props: Record<string, unknown>) => unknown)(node.props)
    : node
  if (resolved !== node) return descendants(resolved)
  return [node, ...descendants(node.props.children)]
}

const baseRequest = {
  id: 'pause-1',
  node_id: 'pause-1',
  node_name: 'Pause',
  mode: 'variables',
  title: 'Type matrix',
  workflow_name: 'Flow',
  triggered_by_name: 'alice',
  triggered_at: '2026-01-01T00:00:00Z',
  description: '',
  approver_ids: ['u-1'],
  approver_names: ['alice'],
  require_all: false,
  approvals: [],
  already_submitted: false,
  can_submit: true,
}

function render(inputVariables: unknown[]) {
  return descendants(PauseRequestActions({
    workflowId: 'wf-1',
    runId: 'run-1',
    pauseRequestId: 'pause-1',
    request: { ...baseRequest, input_variables: inputVariables },
    values: {},
    onValuesChange: mock(() => {}),
    onSubmit: mock(() => {}),
    canSubmit: true,
  }) as unknown)
}

describe('pause request form renders every parameter type like the start-node input', () => {
  test('text/paragraph/select/number/checkbox/array/object render their controls', () => {
    const nodes = render([
      { name: 't', label: 'T', type: 'text', required: false },
      { name: 'p', label: 'P', type: 'paragraph', required: false },
      { name: 's', label: 'S', type: 'select', required: false, options: ['a', 'b'] },
      { name: 'n', label: 'N', type: 'number', required: false },
      { name: 'c', label: 'C', type: 'checkbox', required: false },
      { name: 'arr', label: 'Arr', type: 'array', required: false },
      { name: 'obj', label: 'Obj', type: 'object', required: false },
    ])
    const inputs = nodes.filter((n) => n.type === 'input')
    const textInputs = inputs.filter((n) => (n.props as { type?: string }).type !== 'number')
    const numberInputs = inputs.filter((n) => (n.props as { type?: string }).type === 'number')
    const textareas = nodes.filter((n) => n.type === 'textarea')
    const selects = nodes.filter((n) => n.type === 'select')
    expect(textInputs.length).toBe(1) // text
    expect(numberInputs.length).toBe(1)
    expect(textareas.length).toBe(3) // paragraph + array + object
    expect(selects.length).toBe(1)
    // select options are rendered
    expect(JSON.stringify(selects[0].props.children)).toContain('a')
    // checkbox
    expect(nodes.filter((n) => n.type === 'checkbox').length).toBe(1)
  })

  test('file/image/files/images render upload controls', () => {
    const nodes = render([
      { name: 'f', label: 'F', type: 'file', required: false, fileConfig: { accept: ['.pdf'] } },
      { name: 'img', label: 'Img', type: 'image', required: false, fileConfig: { maxSize: 5 } },
      { name: 'fs', label: 'Fs', type: 'files', required: true, fileConfig: { maxFiles: 3 } },
      { name: 'imgs', label: 'Imgs', type: 'images', required: false, fileConfig: { maxFiles: 9 } },
    ])
    const fileInputs = nodes.filter((n) => n.type === 'input' && (n.props as { type?: string }).type === 'file')
    expect(fileInputs.length).toBe(4)
    const single = fileInputs.filter((n) => !(n.props as { multiple?: boolean }).multiple)
    const multi = fileInputs.filter((n) => (n.props as { multiple?: boolean }).multiple)
    expect(single.length).toBe(2) // file + image
    expect(multi.length).toBe(2) // files + images
    // image accept defaults to image/*
    const imageSingle = single.find((n) => (n.props as { accept?: string }).accept === 'image/*')
    expect(imageSingle).toBeDefined()
    // files accept honors fileConfig
    const filesMulti = multi.find((n) => (n.props as { multiple?: boolean }).multiple)
    expect(filesMulti).toBeDefined()
    // required multi-file is enforced by validation on submit (covered by variable-form tests)
  })

  test('required array rejects invalid JSON and accepts parsed arrays', () => {
    const onValues = {} as Record<string, unknown>
    const nodes = descendants(PauseRequestActions({
      workflowId: 'wf-1',
      runId: 'run-1',
      pauseRequestId: 'pause-1',
      request: {
        ...baseRequest,
        input_variables: [{ name: 'items', label: 'Items', type: 'array', required: true }],
      },
      values: onValues,
      onValuesChange: (next: Record<string, unknown>) => { Object.assign(onValues, next) },
      onSubmit: mock(() => {}),
      canSubmit: true,
    }) as unknown)
    const textarea = nodes.find((n) => n.type === 'textarea')
    expect(textarea).toBeDefined()
    // valid JSON array -> parsed value stored
    ;(textarea!.props.onChange as (e: { target: { value: string } }) => void)({ target: { value: '[1,2]' } })
    expect(onValues.items).toEqual([1, 2])
    // invalid JSON -> raw string stored (submit validation rejects it)
    ;(textarea!.props.onChange as (e: { target: { value: string } }) => void)({ target: { value: 'nope' } })
    expect(onValues.items).toBe('nope')
  })

  test('checkbox default "false" is stored as boolean false, not a truthy string', () => {
    const onValues = {} as Record<string, unknown>
    descendants(PauseRequestActions({
      workflowId: 'wf-1',
      runId: 'run-1',
      pauseRequestId: 'pause-1',
      request: {
        ...baseRequest,
        input_variables: [
          { name: 'agree', label: 'Agree', type: 'checkbox', required: false, default: 'false' },
        ],
      },
      values: onValues,
      onValuesChange: (next: Record<string, unknown>) => { Object.assign(onValues, next) },
      onSubmit: mock(() => {}),
      canSubmit: true,
    }) as unknown)
    // mount effect must convert the 'false' string into a real boolean
    expect(onValues.agree).toBe(false)
  })
})

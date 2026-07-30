import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const createKnowledgeBase = mock(() => Promise.resolve({}))
const updateKnowledgeBase = mock(() => Promise.resolve({}))
const getAvailableModels = mock(() => Promise.resolve([]))
const getTeams = mock(() => Promise.resolve({ items: [] }))
const toastSuccess = mock(() => {})

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))
mock.module('@/lib/api', () => ({
  adminKnowledgeBasesApi: { createKnowledgeBase, updateKnowledgeBase },
  modelsApi: { getAvailableModels },
}))
mock.module('@/lib/api/admin', () => ({ teamsApi: { getTeams } }))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, field: string) => {
    const next = { ...errors }
    delete next[field]
    return next
  },
  getValidationSummaryEntries: (errors: Record<string, string>, order: string[]) =>
    order.flatMap((field) => errors[field] ? [[field, errors[field]]] : []),
  mapValidationErrors: (errors: Record<string, string>, paths: Record<string, string>) =>
    Object.fromEntries(Object.entries(errors).map(([field, message]) => [paths[field] || field, message])),
  normalizeValidationErrors: (error: Record<string, string>) => error,
  formatValidationSummaryMessage: (field: string, message: string) => `${field}: ${message}`,
}))

function element(tag: keyof React.JSX.IntrinsicElements) {
  return function MockElement({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) {
    return React.createElement(tag, props, children)
  }
}

mock.module('@/components/ui/button', () => ({ Button: element('button') }))
mock.module('@/components/ui/input', () => ({ Input: element('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: element('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: element('label') }))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) => children ? <span>{children}</span> : null,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: element('section'),
  DialogDescription: element('p'),
  DialogFooter: element('footer'),
  DialogHeader: element('header'),
  DialogTitle: element('h2'),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, value, onValueChange, disabled }: React.PropsWithChildren<{
    value: string
    onValueChange: (value: string) => void
    disabled?: boolean
  }>) => <select value={value} disabled={disabled} onChange={(event) => onValueChange(event.target.value)}>{children}</select>,
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectEmpty: element('span'),
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: element('span'),
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: ({ value, onChange, ...props }: { value: number | ''; onChange: (value: number | '') => void }) =>
    <input {...props} value={value} onChange={(event) => onChange(event.target.value === '' ? '' : Number(event.target.value))} />,
}))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, ...props }: { checked: boolean; onCheckedChange: (checked: boolean) => void }) =>
    <button {...props} type="button" role="switch" aria-checked={checked} onClick={() => onCheckedChange(!checked)} />,
}))

const { KnowledgeBaseDialog } = await import('./knowledge-base-dialog')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

let renderer: ReactTestRenderer | undefined
const onOpenChange = mock(() => {})
const onSuccess = mock(() => {})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

async function renderDialog(knowledgeBase: Record<string, unknown> | null = null, open = true) {
  await act(async () => {
    renderer = create(
      <KnowledgeBaseDialog
        open={open}
        onOpenChange={onOpenChange}
        knowledgeBase={knowledgeBase as never}
        onSuccess={onSuccess}
      />,
    )
  })
  return renderer!
}

function text() {
  return renderer!.root.findAll(() => true)
    .flatMap((node) => node.children)
    .filter((child) => typeof child === 'string')
    .join(' ')
}

async function submit() {
  await act(async () => renderer!.root.findByType('form').props.onSubmit({ preventDefault() {} }))
}

beforeEach(() => {
  createKnowledgeBase.mockReset()
  createKnowledgeBase.mockResolvedValue({})
  updateKnowledgeBase.mockReset()
  updateKnowledgeBase.mockResolvedValue({})
  getAvailableModels.mockReset()
  getAvailableModels.mockImplementation((type: string) => Promise.resolve(type === 'embedding'
    ? [{ id: 'embed-1', name: 'Embedding One' }]
    : [{ id: 'rerank-1', name: 'Rerank One' }]))
  getTeams.mockReset()
  getTeams.mockResolvedValue({ items: [{ id: 'team-1', name: 'Team One' }, { id: 'team-2', name: 'Team Two' }] })
  toastSuccess.mockReset()
  onOpenChange.mockReset()
  onSuccess.mockReset()
})

afterEach(() => {
  if (renderer) act(() => renderer!.unmount())
  renderer = undefined
})

describe('KnowledgeBaseDialog', () => {
  test('does not load or render while closed and cancel closes an open dialog', async () => {
    await renderDialog(null, false)
    expect(renderer!.toJSON()).toBeNull()
    expect(getAvailableModels).not.toHaveBeenCalled()
    expect(getTeams).not.toHaveBeenCalled()

    await act(async () => {
      renderer!.update(
        <KnowledgeBaseDialog open onOpenChange={onOpenChange} knowledgeBase={null} onSuccess={onSuccess} />,
      )
    })
    const cancel = renderer!.root.findAllByType('button').find((button) => button.children.includes('cancel'))!
    act(() => cancel.props.onClick())
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('validates create fields before saving', async () => {
    getTeams.mockResolvedValueOnce({ items: [] })
    await renderDialog()

    await submit()
    expect(text()).toContain('nameRequired')
    expect(createKnowledgeBase).not.toHaveBeenCalled()

    act(() => renderer!.root.findByProps({ id: 'name' }).props.onChange({ target: { value: 'New KB' } }))
    await submit()
    expect(text()).toContain('teamRequired')
    expect(createKnowledgeBase).not.toHaveBeenCalled()
  })

  test('selects team and models, exposes loading, and creates with trimmed values', async () => {
    const pending = deferred<Record<string, never>>()
    createKnowledgeBase.mockReturnValueOnce(pending.promise)
    await renderDialog()

    act(() => {
      renderer!.root.findByProps({ id: 'name' }).props.onChange({ target: { value: '  New KB  ' } })
      renderer!.root.findByProps({ id: 'description' }).props.onChange({ target: { value: '  Details  ' } })
      const selects = renderer!.root.findAllByType('select')
      selects[0].props.onChange({ target: { value: 'team-2' } })
      selects[1].props.onChange({ target: { value: 'embed-1' } })
      selects[2].props.onChange({ target: { value: 'rerank-1' } })
    })

    let submitting!: Promise<void>
    act(() => { submitting = renderer!.root.findByType('form').props.onSubmit({ preventDefault() {} }) })
    const submitButton = renderer!.root.findAllByType('button').find((button) => button.props.type === 'submit')!
    expect(submitButton.props.disabled).toBe(true)
    expect(submitButton.children).toContain('loading')
    expect(createKnowledgeBase).toHaveBeenCalledWith(expect.objectContaining({
      name: 'New KB',
      description: 'Details',
      team_id: 'team-2',
      embedding_model_id: 'embed-1',
      rerank_model_id: 'rerank-1',
    }))

    await act(async () => {
      pending.resolve({})
      await submitting
    })
    expect(toastSuccess).toHaveBeenCalledWith('kbCreated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })

  test('initializes edit-only controls, maps API errors, and updates status', async () => {
    const knowledgeBase = {
      id: 'kb-1',
      name: 'Existing KB',
      description: 'Existing details',
      embedding_model_id: 'missing-embed',
      embedding_model: { name: 'Stored Embedding' },
      rerank_model_id: 'missing-rerank',
      rerank_model: { name: 'Stored Rerank' },
      settings: { chunk_size: 1200, chunk_overlap: 120, rerank_enabled: true, rerank_candidate_k: 12 },
      status: 'active',
    }
    updateKnowledgeBase.mockRejectedValueOnce({ 'settings.chunk_size': 'too large' })
    await renderDialog(knowledgeBase)

    expect(text()).toContain('editKb')
    expect(text()).toContain('Stored Embedding')
    expect(text()).toContain('Stored Rerank')
    expect(renderer!.root.findAllByType('select')).toHaveLength(2)
    expect(renderer!.root.findAllByType('select')[0].props.disabled).toBe(true)

    await submit()
    expect(text()).toContain('chunk_size: too large')
    expect(onSuccess).not.toHaveBeenCalled()

    const status = renderer!.root.findByProps({ id: 'status' })
    act(() => status.props.onCheckedChange(false))
    await submit()
    expect(updateKnowledgeBase).toHaveBeenLastCalledWith('kb-1', expect.objectContaining({ status: 'archived' }))
    expect(toastSuccess).toHaveBeenCalledWith('kbUpdated')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
  })
})

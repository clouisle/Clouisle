import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

// 直接驱动 useVariableForm hook 的行为测试（运行页起始表单/暂停表单的状态机）。
let lastForm: ReturnType<typeof useVariableForm> | null = null
function Probe({ variables }: { variables: Parameters<typeof useVariableForm>[0] }) {
  const form = useVariableForm(variables)
  React.useEffect(() => { lastForm = form })
  return <div data-probe={JSON.stringify({
    values: form.values,
    needsInput: form.needsInput,
    isValid: form.isValid,
    fieldErrors: form.fieldErrors,
  })} />
}

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
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
mock.module('@/lib/api', () => ({
  ApiError: class ApiError extends Error { code = 0 },
}))
mock.module('@/lib/constants', () => ({ GENERAL_UPLOAD_MAX_FILE_SIZE_MB: 10, BYTES_PER_MB: 1024 * 1024, API_BASE_URL: 'http://localhost:8000' }))
mock.module('@/components/ui/field', () => ({ FieldError: (p: Record<string, unknown>) => ({ type: 'alert', props: p }) }))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { useVariableForm } = await import('./variable-form')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []
afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(variables: Parameters<typeof useVariableForm>[0]) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<Probe variables={variables} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function probeState(renderer: ReactTestRenderer) {
  return { ...JSON.parse(renderer.root.findByType('div').props['data-probe']), form: lastForm! }
}

test('initializes defaults, flags required input, and validates', () => {
  const renderer = render([
    { name: 'title', type: 'text', required: true, default: 'hello' },
    { name: 'price', type: 'number', required: false, default: '42' },
    { name: 'agree', type: 'checkbox', required: false, default: 'false' },
  ])
  const initial = probeState(renderer)

  expect(initial.values).toEqual({ title: 'hello', price: 42, agree: false })
  expect(initial.needsInput).toBe(false) // required 已有默认值
  expect(initial.isValid).toBe(true)
})

test('required field without a default makes the form invalid until filled', () => {
  const renderer = render([{ name: 'title', type: 'text', required: true }])
  const state = probeState(renderer)

  expect(state.needsInput).toBe(true)
  expect(state.isValid).toBe(false)
  expect(Object.keys(state.fieldErrors)).toContain('title')

  act(() => { probeState(renderer).form.setValues({ title: 'filled' }) })
  const filled = probeState(renderer)
  expect(filled.isValid).toBe(true)
  expect(Object.keys(filled.fieldErrors)).toHaveLength(0)
})

test('validate re-checks and reset restores the initial defaults', () => {
  const renderer = render([{ name: 'title', type: 'text', required: true }])
  act(() => { probeState(renderer).form.setValues({ title: 'ok' }) })
  act(() => { probeState(renderer).form.setValues({ title: '' }) })

  const state = probeState(renderer)
  expect(state.form.validate()).toBe(false)

  act(() => { state.form.reset() })
  expect(probeState(renderer).values).toEqual({})
})

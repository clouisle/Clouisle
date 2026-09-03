import { afterEach, describe, expect, mock, test } from 'bun:test'
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
  HTMLButtonElement: window.HTMLButtonElement,
  HTMLInputElement: window.HTMLInputElement,
  Node: window.Node,
  getComputedStyle: window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})

mock.module('next-intl', () => ({
  useLocale: () => 'en',
  useTranslations: () => (key: string) => `chat.askUser.${key}`,
}))
mock.module('lucide-react', () => ({
  Loader2: (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />,
}))
mock.module('@/lib/utils', () => ({ cn: (...classes: unknown[]) => classes.filter(Boolean).join(' ') }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))

const { AskUserForm, normalizeAskUserQuestions } = await import('./ask-user-form')

let root: Root | undefined

afterEach(() => {
  act(() => root?.unmount())
  root = undefined
  document.body.replaceChildren()
})

function renderForm(props: React.ComponentProps<typeof AskUserForm>) {
  const container = document.body.appendChild(document.createElement('div'))
  root = createRoot(container)
  act(() => root?.render(<AskUserForm {...props} />))
  return container
}

function submitButton(container: HTMLElement): HTMLButtonElement {
  return Array.from(container.querySelectorAll('button')).find((button) => button.type === 'submit') as HTMLButtonElement
}

function chips(container: HTMLElement): HTMLButtonElement[] {
  return Array.from(container.querySelectorAll('button')).filter((button) => button.type === 'button')
}

describe('normalizeAskUserQuestions', () => {
  test('normalizes a single question and many questions through the same array path', () => {
    expect(normalizeAskUserQuestions({ questions: [{ id: 'a', question: 'Where?' }] })).toEqual([
      { id: 'a', question: 'Where?', required: true },
    ])
    expect(normalizeAskUserQuestions({
      questions: [
        { id: 'a', question: 'A?', options: ['1', '2'], required: false },
        { id: 'b', question: 'B?' },
      ],
    })).toEqual([
      { id: 'a', question: 'A?', options: ['1', '2'], required: false },
      { id: 'b', question: 'B?', required: true },
    ])
  })

  test('rejects malformed payloads instead of partially rendering them', () => {
    expect(normalizeAskUserQuestions({})).toEqual([])
    expect(normalizeAskUserQuestions({ questions: 'nope' })).toEqual([])
    expect(normalizeAskUserQuestions({ questions: [{ id: '', question: 'X' }, { id: 'a' }, 42] })).toEqual([])
    expect(normalizeAskUserQuestions({ questions: [{ id: 'a', question: 'A?' }, { id: 'a', question: 'Again?' }] })).toEqual([])
    expect(normalizeAskUserQuestions({ questions: [{ id: 'a', question: 'A?', options: ['ok', 1] }] })).toEqual([])
  })
})

describe('AskUserForm', () => {
  test('renders a single question through the array renderer and submits its answer', () => {
    const answers: Array<Record<string, unknown>> = []
    const container = renderForm({
      questions: [{ id: 'target', question: 'Where to deploy?', options: ['cloud', 'local'], required: true }],
      onSubmit: async (value) => { answers.push(value) },
    })

    // Required answer missing: submission is blocked with a validation message.
    act(() => submitButton(container).click())
    expect(answers).toHaveLength(0)
    expect(container.textContent).toContain('chat.askUser.answerRequired')

    act(() => chips(container)[0].click())
    act(() => submitButton(container).click())
    expect(answers).toEqual([{ target: 'cloud' }])
  })

  test('collects answers for multiple questions and validates each required field', () => {
    const answers: Array<Record<string, unknown>> = []
    const container = renderForm({
      questions: [
        { id: 'a', question: 'Target?', options: ['cloud', 'local'], required: true },
        { id: 'b', question: 'Region?', options: ['cn', 'us'], required: false },
      ],
      onSubmit: async (value) => { answers.push(value) },
    })

    act(() => submitButton(container).click())
    expect(answers).toHaveLength(0)

    // Answer only the optional question first: required question still blocks.
    act(() => chips(container)[2].click()) // b = 'cn'
    act(() => submitButton(container).click())
    expect(answers).toHaveLength(0)
    expect(container.textContent).toContain('chat.askUser.answerRequired')

    act(() => chips(container)[0].click()) // a = 'cloud'
    act(() => submitButton(container).click())
    expect(answers).toEqual([{ a: 'cloud', b: 'cn' }])
  })

  test('renders free-text questions as inputs and submits their values', () => {
    const answers: Array<Record<string, unknown>> = []
    const container = renderForm({
      questions: [{ id: 'note', question: 'Notes?', required: false }],
      onSubmit: async (value) => { answers.push(value) },
    })
    expect(container.querySelectorAll('input')).toHaveLength(1)
    act(() => submitButton(container).click())
    // Optional empty answers are not included in the submitted payload.
    expect(answers).toEqual([{}])
  })

  test('disables interaction while disabled', () => {
    const container = renderForm({
      questions: [{ id: 'q', question: 'Q?', options: ['a'] }],
      disabled: true,
      onSubmit: async () => undefined,
    })
    const option = chips(container)[0]
    expect(option.disabled).toBe(true)
    expect(submitButton(container).disabled).toBe(true)
  })

  test('reports a rejected submission as an inline error', async () => {
    const container = renderForm({
      questions: [{ id: 'q', question: 'Q?', options: ['a'] }],
      onSubmit: async () => { throw new Error('run no longer waiting') },
    })
    act(() => chips(container)[0].click())
    await act(async () => { submitButton(container).click() })
    expect(container.textContent).toContain('run no longer waiting')
  })
})

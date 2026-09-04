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
let latestInputProps: React.InputHTMLAttributes<HTMLInputElement> | undefined

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
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => {
    latestInputProps = props
    return <input {...props} />
  },
}))

// Load after module mocks; a static import would bind real dependencies first.
const {
  AskUserForm,
  PendingAskUserForm,
  getPendingAskUserRequest,
  normalizeAskUserQuestions,
} = await import('./ask-user-form')

let root: Root | undefined

afterEach(() => {
  act(() => root?.unmount())
  root = undefined
  document.body.replaceChildren()
  latestInputProps = undefined
})

function renderForm(props: React.ComponentProps<typeof AskUserForm>) {
  const container = document.body.appendChild(document.createElement('div'))
  root = createRoot(container)
  act(() => root?.render(<AskUserForm {...props} />))
  return container
}

function renderPendingForm(props: React.ComponentProps<typeof PendingAskUserForm>) {
  const container = document.body.appendChild(document.createElement('div'))
  root = createRoot(container)
  act(() => root?.render(<PendingAskUserForm {...props} />))
  return container
}

function submitButton(container: HTMLElement): HTMLButtonElement {
  return Array.from(container.querySelectorAll('button')).find((button) => button.type === 'submit') as HTMLButtonElement
}

function button(container: HTMLElement, text: string): HTMLButtonElement {
  return Array.from(container.querySelectorAll('button')).find((candidate) => candidate.textContent === text) as HTMLButtonElement
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

describe('PendingAskUserForm', () => {
  const messages = [{
    id: 'assistant-1',
    role: 'assistant',
    parts: [{
      type: 'tool-call',
      toolCallId: 'ask-1',
      toolName: 'ask_user',
      input: { questions: [{ id: 'target', question: 'Where?', options: ['cloud'] }] },
    }],
  }] as never

  test('resolves only the server-pending ask_user call', () => {
    expect(getPendingAskUserRequest(messages, 'ask-1')).toEqual({
      toolCallId: 'ask-1',
      questions: [{ id: 'target', question: 'Where?', options: ['cloud'], required: true }],
    })
    expect(getPendingAskUserRequest(messages, 'other-call')).toBeNull()
  })

  test('submits the rendered answers through the original tool call id', async () => {
    const submissions: Array<[string, { answers: Record<string, unknown>; skipped?: boolean }]> = []
    const container = renderPendingForm({
      messages,
      pendingToolCallId: 'ask-1',
      onSubmit: async (toolCallId, answer) => { submissions.push([toolCallId, answer]) },
    })
    expect(container.querySelector('[data-ask-user-form]')?.className).toContain('w-[70%]')

    act(() => button(container, 'cloud').click())
    await act(async () => {
      submitButton(container).click()
      await Promise.resolve()
    })

    expect(submissions).toEqual([['ask-1', { answers: { target: 'cloud' } }]])
  })
})

describe('AskUserForm', () => {
  test('renders a custom input alongside options and submits its value', async () => {
    const answers: Array<{ answers: Record<string, unknown>; skipped?: boolean }> = []
    const container = renderForm({
      questions: [{ id: 'target', question: 'Where to deploy?', options: ['cloud', 'local'], required: true }],
      onSubmit: async (answer) => { answers.push(answer) },
    })
    const cloudOption = button(container, 'cloud')
    expect(cloudOption.parentElement?.className).toContain('flex-col')
    expect(cloudOption.parentElement?.className).not.toContain('-ml-6')
    expect(cloudOption.className).toContain('h-9')
    expect(cloudOption.className).toContain('w-full')
    expect(cloudOption.className).toContain('rounded-md')
    expect(cloudOption.className).toContain('text-left')
    expect(latestInputProps?.className).toBe('h-9 w-full rounded-md px-2.5')
    expect(latestInputProps?.placeholder).toBe('chat.askUser.customAnswer')

    act(() => submitButton(container).click())
    expect(answers).toHaveLength(0)
    expect(container.textContent).toContain('chat.askUser.answerRequired')

    act(() => latestInputProps?.onChange?.({ target: { value: 'self-hosted' } } as React.ChangeEvent<HTMLInputElement>))
    await act(async () => {
      submitButton(container).click()
      await Promise.resolve()
    })
    expect(answers).toEqual([{ answers: { target: 'self-hosted' } }])
  })

  test('collects answers one page at a time and keeps prior answers when navigating back', async () => {
    const answers: Array<{ answers: Record<string, unknown>; skipped?: boolean }> = []
    const container = renderForm({
      questions: [
        { id: 'target', question: 'Target?', options: ['cloud', 'local'], required: true },
        { id: 'region', question: 'Region?', options: ['cn', 'us'], required: false },
      ],
      onSubmit: async (value) => { answers.push(value) },
    })

    expect(container.textContent).toContain('Target?')
    expect(container.textContent).not.toContain('Region?')
    expect(container.querySelector('[data-ask-user-form]')?.getAttribute('data-ask-user-page')).toBe('1')

    act(() => button(container, 'chat.askUser.next').click())
    expect(container.textContent).toContain('chat.askUser.answerRequired')
    expect(container.textContent).toContain('Target?')

    act(() => button(container, 'cloud').click())
    act(() => button(container, 'chat.askUser.next').click())
    expect(container.textContent).toContain('Region?')
    expect(container.textContent).not.toContain('Target?')
    expect(container.querySelector('[data-ask-user-form]')?.getAttribute('data-ask-user-page')).toBe('2')

    act(() => button(container, 'cn').click())
    act(() => button(container, 'chat.askUser.previous').click())
    expect(container.textContent).toContain('Target?')
    act(() => button(container, 'chat.askUser.next').click())
    await act(async () => {
      submitButton(container).click()
      await Promise.resolve()
    })

    expect(answers).toEqual([{ answers: { target: 'cloud', region: 'cn' } }])
  })

  test('omits empty optional answers', async () => {
    const answers: Array<{ answers: Record<string, unknown>; skipped?: boolean }> = []
    const container = renderForm({
      questions: [{ id: 'note', question: 'Notes?', required: false }],
      onSubmit: async (answer) => { answers.push(answer) },
    })
    expect(container.querySelectorAll('input')).toHaveLength(1)
    await act(async () => {
      submitButton(container).click()
      await Promise.resolve()
    })
    expect(answers).toEqual([{ answers: {} }])
  })


  test('skips every question with an explicit empty result', async () => {
    const submissions: Array<{ answers: Record<string, unknown>; skipped?: boolean }> = []
    const container = renderForm({
      questions: [
        { id: 'target', question: 'Where?', options: ['cloud'], required: true },
        { id: 'region', question: 'Which region?', required: true },
      ],
      onSubmit: async (answer) => { submissions.push(answer) },
    })

    await act(async () => {
      button(container, 'chat.askUser.skipAll').click()
      await Promise.resolve()
    })

    expect(submissions).toEqual([{ answers: {}, skipped: true }])
  })
  test('disables interaction while disabled', () => {
    const container = renderForm({
      questions: [{ id: 'q', question: 'Q?', options: ['a'] }],
      disabled: true,
      onSubmit: async () => undefined,
    })
    expect(button(container, 'a').disabled).toBe(true)
    expect(submitButton(container).disabled).toBe(true)
    expect(button(container, 'chat.askUser.skipAll').disabled).toBe(true)
  })

  test('reports a rejected final submission as an inline error', async () => {
    const container = renderForm({
      questions: [{ id: 'q', question: 'Q?', options: ['a'] }],
      onSubmit: async () => { throw new Error('run no longer waiting') },
    })
    act(() => button(container, 'a').click())
    await act(async () => { submitButton(container).click() })
    expect(container.textContent).toContain('run no longer waiting')
  })
})

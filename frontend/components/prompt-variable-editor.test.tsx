import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import React from 'react'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button>,
}))
mock.module('lucide-react', () => ({
  AlertCircle: () => null,
  Plus: () => null,
  Variable: () => null,
}))

const { PromptVariableEditor } = await import('./prompt-variable-editor')

const variables = [
  { ref: 'system.date', name: 'Current date', label: 'System', isSystem: true },
  { ref: 'user.name', name: 'User name', label: 'Profile' },
]

let window: Window
let root: Root
let container: HTMLDivElement

beforeEach(() => {
  window = new Window()
  Object.assign(globalThis, {
    window,
    document: window.document,
    navigator: window.navigator,
    Node: window.Node,
    HTMLElement: window.HTMLElement,
    Event: window.Event,
    MouseEvent: window.MouseEvent,
    InputEvent: window.InputEvent,
  })
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  window.close()
})

function typeInEditor(text: string) {
  const editor = container.querySelector('[contenteditable]') as HTMLDivElement
  editor.textContent = text
  const range = document.createRange()
  range.setStart(editor.firstChild!, text.length)
  range.collapse(true)
  const selection = window.getSelection()!
  selection.removeAllRanges()
  selection.addRange(range)
  act(() => editor.dispatchEvent(new Event('input', { bubbles: true })))
  act(() => {})
  return editor
}

function render(props: Partial<React.ComponentProps<typeof PromptVariableEditor>> = {}) {
  const onChange = mock(() => {})
  act(() => {
    root.render(
      <PromptVariableEditor
        value=""
        onChange={onChange}
        variables={variables}
        noVariablesText="No matching variables"
        {...props}
      />
    )
  })
  return onChange
}

describe('PromptVariableEditor', () => {
  test('discovers matching variables and inserts the selected reference', () => {
    const onChange = render()
    typeInEditor('Hello {{user')

    expect(container.textContent).toContain('User name')
    expect(container.textContent).not.toContain('Current date')

    const suggestion = container.querySelector('[data-suggestion-index="0"]') as HTMLButtonElement
    act(() => suggestion.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true })))

    expect(onChange).toHaveBeenLastCalledWith('Hello {{user.name}}')
    expect(container.querySelector('[data-suggestion-index]')).toBeNull()
  })

  test('reports unmatched input through the create callback without creating a duplicate suggestion', () => {
    const onCreateVariable = mock(() => {})
    render({ allowCreateVariable: true, onCreateVariable, createVariableText: (name) => `Create ${name}` })
    typeInEditor('{{missing')

    expect(container.textContent).toContain('No matching variables')
    expect(container.querySelectorAll('[data-suggestion-index]')).toHaveLength(0)

    const createButton = [...container.querySelectorAll('button')].find((button) => button.textContent === 'Create missing')!
    act(() => createButton.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true })))
    expect(onCreateVariable).toHaveBeenCalledWith('missing')
  })

  test('deduplicates undefined references and sends their callback payload', () => {
    const onUndefinedVariableClick = mock(() => {})
    render({
      value: '{{missing}} {{missing}} {{another}}',
      showUndefinedWarnings: true,
      undefinedVariablesHintText: 'Undefined variables',
      onUndefinedVariableClick,
    })

    expect(container.textContent).toContain('Undefined variables')
    const undefinedButtons = [...container.querySelectorAll('button')].filter((button) => button.textContent?.startsWith('{{'))
    expect(undefinedButtons.map((button) => button.textContent)).toEqual(['{{missing}}', '{{another}}'])

    act(() => undefinedButtons[0].click())
    expect(onUndefinedVariableClick).toHaveBeenCalledWith('missing')
  })

  test('removes its document click listener on unmount', () => {
    const removeEventListener = mock(document.removeEventListener.bind(document))
    document.removeEventListener = removeEventListener as typeof document.removeEventListener
    render()

    act(() => root.unmount())

    expect(removeEventListener).toHaveBeenCalledWith('mousedown', expect.any(Function))
  })
})

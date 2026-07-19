import { afterEach, describe, expect, test } from 'bun:test'
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
  Node: window.Node,
  getComputedStyle: window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})

const { UserInputRequestCard } = await import('./user-input-request-card')

let root: Root | undefined

afterEach(() => {
  act(() => root?.unmount())
  root = undefined
  document.body.replaceChildren()
})

function renderCard(props: React.ComponentProps<typeof UserInputRequestCard>) {
  const container = document.body.appendChild(document.createElement('div'))
  root = createRoot(container)
  act(() => root?.render(<UserInputRequestCard {...props} />))
  return container
}

describe('UserInputRequestCard', () => {
  test('selects an option once and disables the remaining choices', () => {
    const selected: string[] = []
    const container = renderCard({
      question: 'Choose one',
      options: ['First', 'Second'],
      onSelectOption: (option) => selected.push(option),
    })
    const [first, second] = Array.from(container.querySelectorAll('button'))

    expect(container.textContent).toContain('Click an option above or type your own response')
    expect(first.disabled).toBe(false)

    act(() => first.click())
    act(() => first.click())

    expect(selected).toEqual(['First'])
    expect(first.disabled).toBe(true)
    expect(second.disabled).toBe(true)
    expect(container.textContent).not.toContain('Click an option above or type your own response')
  })

  test('renders an answered request as non-interactive with its selected option', () => {
    const container = renderCard({
      question: 'Already answered',
      options: ['Accepted', 'Declined'],
      state: 'answered',
      selectedOption: 'Accepted',
    })
    const [accepted, declined] = Array.from(container.querySelectorAll('button'))

    expect(accepted.className).toContain('bg-primary')
    expect(accepted.disabled).toBe(true)
    expect(declined.disabled).toBe(true)
    expect(container.textContent).not.toContain('Click an option above or type your own response')
  })

  test('keeps pending options disabled while the response is streaming', () => {
    const selected: string[] = []
    const container = renderCard({
      question: 'Wait',
      options: ['Later'],
      isStreaming: true,
      onSelectOption: (option) => selected.push(option),
    })
    const [option] = Array.from(container.querySelectorAll('button'))

    expect(option.disabled).toBe(true)
    expect(container.textContent).toContain('Waiting for response to complete...')

    act(() => option.click())
    expect(selected).toEqual([])
  })
})

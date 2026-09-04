import { afterEach, describe, expect, jest, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))

const {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtHeader,
  ChainOfThoughtImage,
  ChainOfThoughtSearchResult,
  ChainOfThoughtSearchResults,
  ChainOfThoughtStep,
  useChainOfThought,
} = await import('./chain-of-thought')

globalThis.IS_REACT_ACT_ENVIRONMENT = true
const renderers: ReactTestRenderer[] = []

function render(element: React.ReactNode) {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(element) })
  renderers.push(renderer!)
  return renderer!
}

const text = (renderer: ReactTestRenderer) => JSON.stringify(renderer.toJSON())

afterEach(() => {
  for (const renderer of renderers.splice(0)) act(() => renderer.unmount())
  jest.useRealTimers()
})

describe('chain of thought AI element', () => {
  test('toggles accessible content and reports uncontrolled state changes', () => {
    const changes: boolean[] = []
    const renderer = render(
      <ChainOfThought defaultOpen={false} onOpenChange={(open) => changes.push(open)}>
        <ChainOfThoughtHeader title="Reasoning" />
        <ChainOfThoughtContent>Hidden details</ChainOfThoughtContent>
      </ChainOfThought>,
    )
    const trigger = renderer.root.findByType('button')

    expect(trigger.props['aria-expanded']).toBe(false)
    expect(text(renderer)).toContain('hidden')
    act(() => trigger.props.onClick())
    expect(renderer.root.findByType('button').props['aria-expanded']).toBe(true)
    expect(changes).toEqual([true])
  })

  test('auto-closes once after streaming ends', () => {
    jest.useFakeTimers()
    const changes: boolean[] = []
    const renderer = render(
      <ChainOfThought onOpenChange={(open) => changes.push(open)}>
        <ChainOfThoughtHeader />
      </ChainOfThought>,
    )

    act(() => jest.advanceTimersByTime(3000))

    expect(changes).toEqual([false])
    expect(renderer.root.findByType('button').props['aria-expanded']).toBe(false)
  })

  test('contains native wheel propagation only while more content is scrollable', () => {
    const listeners = new Map<string, (event: WheelEvent) => void>()
    const node = {
      scrollTop: 2,
      scrollHeight: 100,
      clientHeight: 20,
      addEventListener: mock((name: string, listener: (event: WheelEvent) => void) => listeners.set(name, listener)),
      removeEventListener: mock((name: string) => listeners.delete(name)),
    }
    let renderer: ReactTestRenderer
    act(() => {
      renderer = create(
        <ChainOfThought><ChainOfThoughtContent containScroll /></ChainOfThought>,
        { createNodeMock: () => node },
      )
    })
    renderers.push(renderer!)
    const stopPropagation = mock(() => {})

    listeners.get('wheel')?.({ deltaY: 1, stopPropagation } as unknown as WheelEvent)
    listeners.get('wheel')?.({ deltaY: -1, stopPropagation } as unknown as WheelEvent)
    expect(stopPropagation).toHaveBeenCalledTimes(2)

    node.scrollTop = 0
    node.scrollHeight = 20
    listeners.get('wheel')?.({ deltaY: 1, stopPropagation } as unknown as WheelEvent)
    expect(stopPropagation).toHaveBeenCalledTimes(2)
  })

  test('renders streaming, step, search, and image variants', () => {
    const Icon = (props: React.ComponentProps<'i'>) => <i {...props} />
    const renderer = render(
      <ChainOfThought isStreaming defaultOpen={false}>
        <ChainOfThoughtHeader icon={Icon}>Working</ChainOfThoughtHeader>
        <ChainOfThoughtContent containScroll onWheel={() => {}}>
          <ChainOfThoughtStep label="Search" status="active" icon={Icon}>Details</ChainOfThoughtStep>
          <ChainOfThoughtStep label="Done" status="complete" />
          <ChainOfThoughtSearchResults><ChainOfThoughtSearchResult>Result</ChainOfThoughtSearchResult></ChainOfThoughtSearchResults>
          <ChainOfThoughtImage caption="Diagram"><span>Image</span></ChainOfThoughtImage>
          <ChainOfThoughtImage><span>No caption</span></ChainOfThoughtImage>
        </ChainOfThoughtContent>
      </ChainOfThought>,
    )

    expect(text(renderer)).toContain('Working')
    expect(text(renderer)).toContain('animate-spin')
    expect(text(renderer)).toContain('text-green-600')
    expect(text(renderer)).toContain('Result')
    expect(renderer.root.findAllByType('figcaption')).toHaveLength(1)
  })

  test('rejects context consumers outside the container', () => {
    function Consumer() {
      useChainOfThought()
      return null
    }

    expect(() => render(<Consumer />)).toThrow('ChainOfThought components must be used within ChainOfThought')
  })
})

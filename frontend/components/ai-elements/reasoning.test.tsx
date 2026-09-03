import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('@/components/ui/collapsible', () => ({
  Collapsible: ({ children, open, onOpenChange }: { children: React.ReactNode; open: boolean; onOpenChange: (open: boolean) => void }) => (
    <div data-open={open}>
      {children}
      <button data-testid="close" onClick={() => onOpenChange(false)}>close</button>
    </div>
  ),
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
}))
mock.module('lucide-react', () => ({ BrainIcon: () => <svg />, ChevronDownIcon: () => <svg /> }))
mock.module('streamdown', () => ({ Streamdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))
mock.module('./shimmer', () => ({ Shimmer: ({ children }: { children: React.ReactNode }) => <span>{children}</span> }))

let Reasoning: typeof import('./reasoning').Reasoning
let ReasoningTrigger: typeof import('./reasoning').ReasoningTrigger

beforeAll(async () => {
  ({ Reasoning, ReasoningTrigger } = await import('./reasoning'))
})

describe('Reasoning', () => {
  let renderer: ReactTestRenderer | undefined
  const originalNow = Date.now
  const originalSetTimeout = globalThis.setTimeout
  const originalClearTimeout = globalThis.clearTimeout

  afterEach(() => {
    renderer?.unmount()
    renderer = undefined
    Date.now = originalNow
    globalThis.setTimeout = originalSetTimeout
    globalThis.clearTimeout = originalClearTimeout
  })

  test('records completed streaming duration and auto-closes once', () => {
    let now = 1_000
    let autoClose: (() => void) | undefined
    Date.now = () => now
    globalThis.setTimeout = ((callback: () => void) => {
      autoClose = callback
      return 1 as unknown as ReturnType<typeof setTimeout>
    }) as typeof setTimeout
    globalThis.clearTimeout = (() => {}) as typeof clearTimeout

    act(() => {
      renderer = create(<Reasoning isStreaming><ReasoningTrigger /></Reasoning>)
    })
    expect(renderer!.root.findByType('div').props['data-open']).toBe(true)
    expect(renderer!.root.findByType('span').children).toContain('Thinking...')

    now = 3_400
    act(() => {
      renderer!.update(<Reasoning isStreaming={false}><ReasoningTrigger /></Reasoning>)
    })
    expect(renderer!.root.findByType('p').children.join('')).toBe('Thought for 3 seconds')
    expect(autoClose).toBeDefined()

    act(() => autoClose!())
    expect(renderer!.root.findByType('div').props['data-open']).toBe(false)
  })
})

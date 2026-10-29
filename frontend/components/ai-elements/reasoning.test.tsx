import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import * as React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('@/components/ui/trace', () => ({
  Trace: ({ children, ...props }: React.ComponentProps<'div'>) => <div data-slot="trace" {...props}>{children}</div>,
  TraceCollapsible: ({ children, open, onOpenChange, ...props }: React.ComponentProps<'div'> & { open?: boolean; onOpenChange?: (open: boolean) => void }) => (
    <div data-slot="trace-collapsible" data-open={open} {...props}>
      {children}
      <button data-testid="close" onClick={() => onOpenChange?.(false)}>close</button>
    </div>
  ),
  TraceCollapsibleContent: ({ children, forceMount, ...props }: React.ComponentProps<'div'> & { forceMount?: boolean }) => { void forceMount; return <div data-slot="trace-collapsible-content" {...props}>{children}</div> },
  TraceCollapsibleTrigger: ({ children }: React.ComponentProps<'button'>) => <button data-slot="trace-collapsible-trigger">{children}</button>,
  TraceIcon: ({ children, ...props }: React.ComponentProps<'span'>) => <span data-slot="trace-icon" {...props}>{children}</span>,
  TraceLine: ({ children, status, ...props }: React.ComponentProps<'span'> & { status?: string }) => <span data-slot="trace-line" data-status={status} {...props}>{children}</span>,
  TraceTitle: ({ children, ...props }: React.ComponentProps<'span'>) => <span data-slot="trace-title" {...props}>{children}</span>,
  TraceDescription: ({ children, ...props }: React.ComponentProps<'span'>) => <span data-slot="trace-description" {...props}>{children}</span>,
}))
mock.module('streamdown', () => ({ Streamdown: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }))

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
    act(() => renderer?.unmount())
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
    expect(renderer!.root.findByProps({ 'data-slot': 'trace-collapsible' }).props['data-open']).toBe(true)
    expect(renderer!.root.findByProps({ 'data-slot': 'trace-title' }).children).toContain('Thinking...')

    now = 3_400
    act(() => {
      renderer!.update(<Reasoning isStreaming={false}><ReasoningTrigger /></Reasoning>)
    })
    expect(renderer!.root.findByProps({ 'data-slot': 'trace-title' }).children).toContain('Thought for 3 seconds')
    expect(autoClose).toBeDefined()

    act(() => autoClose!())
    expect(renderer!.root.findByProps({ 'data-slot': 'trace-collapsible' }).props['data-open']).toBe(false)
  })
})

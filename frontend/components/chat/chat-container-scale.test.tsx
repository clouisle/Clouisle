/** Client-side rendering tests for the user-message scale (TOC) in ChatContainer.
 *  Uses happy-dom + react-dom/client (no layout engine): row offsets and scroller
 *  metrics are assigned manually, then a resize event recomputes the ticks. */
import { afterEach, beforeEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { Window } from 'happy-dom'
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'

const window = new Window({ url: 'http://localhost' })
globalThis.window = window as unknown as Window & typeof globalThis
globalThis.document = window.document
globalThis.navigator = window.navigator
globalThis.HTMLElement = window.HTMLElement
globalThis.Element = window.Element
globalThis.Node = window.Node
globalThis.getComputedStyle = window.getComputedStyle
globalThis.requestAnimationFrame = ((cb: FrameRequestCallback) => setTimeout(() => cb(0), 0)) as typeof requestAnimationFrame
;(globalThis as Record<string, unknown>).IS_REACT_ACT_ENVIRONMENT = true
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) => `${key}:${values?.ordinal ?? ''}`,
}))
mock.module('lucide-react', () => ({
  ArrowDown: () => <svg data-icon="arrow-down" />,
  ChevronDown: () => <svg data-icon="chevron-down" />,
  ChevronUp: () => <svg data-icon="chevron-up" />,
  Download: () => <svg data-icon="download" />,
  Eye: () => <svg data-icon="eye" />,
  FileAudio: () => <svg data-icon="file-audio" />,
  FileCode: () => <svg data-icon="file-code" />,
  FileIcon: () => <svg data-icon="file-icon" />,
  FileImage: () => <svg data-icon="file-image" />,
  FileText: () => <svg data-icon="file-text" />,
  FileType: () => <svg data-icon="file-type" />,
  FileVideo: () => <svg data-icon="file-video" />,
  Link: () => <svg data-icon="link" />,
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  TooltipTrigger: ({ render, children, ...props }: { render?: React.ReactElement; children?: React.ReactNode } & Record<string, unknown>) => {
    const element = render ?? <button />
    return React.cloneElement(element as React.ReactElement, props, children)
  },
  TooltipContent: ({ children }: { children: React.ReactNode }) => <span data-tooltip-content>{children}</span>,
}))
mock.module('./message', () => ({
  Message: ({ message }: { message: { id: string; role: string } }) => (
    <div data-message-id={message.id} data-role={message.role}>row</div>
  ),
}))

const { ChatContainer } = await import('./chat-container')
import type { ChatMessage } from './types'

const textMessage = (id: string, role: ChatMessage['role'], text: string): ChatMessage => ({ id, role, parts: [{ type: 'text', text }] })

let root: Root | null = null
let container: HTMLElement

beforeEach(() => {
  window.document.body.innerHTML = '<div id="root"></div>'
  container = window.document.getElementById('root')!
  root = createRoot(container)
})

afterEach(async () => {
  await act(async () => root?.unmount())
})

// happy-dom performs no layout: give the scroller the clientHeight a browser
// would report so the uniform tick list can be computed.
function assignLayoutMetrics() {
  const firstRow = container.querySelector('[data-message-id]')
  const scroller = firstRow?.parentElement?.parentElement?.parentElement as HTMLElement | null
  if (scroller) {
    Object.defineProperty(scroller, 'clientHeight', { configurable: true, value: 400 })
  }
}

async function renderScale(messages: ChatMessage[]) {
  await act(async () => {
    root!.render(<ChatContainer messages={messages} showUserMessageScale />)
  })
  assignLayoutMetrics()
  // Resize recomputes ticks from the (now measured) layout.
  const WindowEvent = globalThis.window.Event
  await act(async () => {
    window.dispatchEvent(new WindowEvent('resize'))
  })
}

describe('ChatContainer user-message scale', () => {
  test('renders one visible tick per user message at 12px pitch, current highlighted', async () => {
    const messages = [
      textMessage('u1', 'user', 'first'),
      textMessage('a1', 'assistant', 'answer one'),
      textMessage('u2', 'user', 'second'),
      textMessage('a2', 'assistant', 'answer two'),
      textMessage('u3', 'user', 'third'),
      textMessage('a3', 'assistant', 'answer three'),
    ]

    await renderScale(messages)

    const ticks = Array.from(container.querySelectorAll('[data-user-message-tick]')) as HTMLElement[]
    expect(ticks).toHaveLength(3)
    // 400px track, 3 entries → 12px pitch, cluster centered (188 / 200 / 212).
    const tops = ticks.map((tick) => Number.parseFloat(tick.style.top))
    expect(tops[1] - tops[0]).toBe(12)
    expect(tops[2] - tops[1]).toBe(12)
    expect(tops[0]).toBeGreaterThanOrEqual(182)

    // Every tick's line must have a width class — a missing base width renders
    // zero-width (invisible) lines for all but the current tick.
    const lines = Array.from(container.querySelectorAll('[data-user-message-tick] span')) as HTMLElement[]
    expect(lines).toHaveLength(3)
    for (const line of lines) {
      expect(line.className).toMatch(/\bw-\d+\b/)
    }

    // The last user message is in view (no scroll yet) → highlighted; others gray.
    const current = ticks.find((tick) => tick.getAttribute('data-current') === 'true')
    expect(current).toBeDefined()
    expect(current!.getAttribute('data-ordinal')).toBe('3')
    const currentLine = current!.querySelector('span')!
    expect(currentLine.className).toMatch(/\bw-7\b/)
    expect(currentLine.className).toContain('bg-primary')
    for (const other of ticks.filter((tick) => tick !== current)) {
      expect(other.getAttribute('data-current')).toBeNull()
      expect(other.querySelector('span')!.className).toContain('bg-muted-foreground')
    }

    // Tooltip shows only the message content — no ordinal label.
    const tooltipTexts = Array.from(container.querySelectorAll('[data-tooltip-content]')).map((node) => node.textContent)
    expect(tooltipTexts).toContain('second')
    for (const text of tooltipTexts) {
      expect(text).not.toContain('userMessageScaleTick')
    }
  })

  test('moves the highlighted tick as the viewport scrolls (scrollspy)', async () => {
    const messages = Array.from({ length: 30 }, (_, index) => (
      index % 2 === 0
        ? textMessage(`u${index / 2 + 1}`, 'user', `question ${index / 2 + 1}`)
        : textMessage(`a${(index + 1) / 2}`, 'assistant', 'answer')
    ))

    await renderScale(messages)

    // 40px rows → user message k sits at top 80 * (k - 1). Give the scroller a
    // scrollTop of 600 so the viewport bottom (600 + 400 = 1000) lands past
    // user message 13 (960) but before 14 (1040).
    const scroller = container.querySelector('[data-message-id]')?.parentElement?.parentElement?.parentElement as HTMLElement | null
    expect(scroller).not.toBeNull()
    Object.defineProperty(scroller!, 'scrollTop', { configurable: true, value: 600 })
    const rows = Array.from(container.querySelectorAll('[data-message-id]')) as HTMLElement[]
    rows.forEach((row) => {
      // u<k> is global row 2(k-1), a<k> is global row 2k-1 → 40px each.
      const id = row.getAttribute('data-message-id')!
      const isUser = id.startsWith('u')
      const k = Number.parseInt(id.slice(1), 10)
      const globalIndex = isUser ? 2 * (k - 1) : 2 * k - 1
      Object.defineProperty(row.parentElement!, 'offsetTop', { configurable: true, value: globalIndex * 40 })
    })

    await act(async () => {
      scroller!.dispatchEvent(new (globalThis.window as unknown as { Event: typeof Event }).Event('scroll'))
    })

    // viewport bottom = 600 + 400 = 1000 → last user message with top <= 1000.
    const current = Array.from(container.querySelectorAll('[data-user-message-tick][data-current="true"]')) as HTMLElement[]
    expect(current).toHaveLength(1)
    expect(current[0].getAttribute('data-ordinal')).toBe('13')
  })

  test('renders no scale when disabled and no ticks for assistant-only conversations', async () => {
    await act(async () => {
      root!.render(<ChatContainer messages={[textMessage('u1', 'user', 'hello')]} />)
    })
    expect(container.querySelector('[data-user-message-scale]')).toBeNull()

    await renderScale([textMessage('a1', 'assistant', 'only assistant')])
    expect(container.querySelector('[data-user-message-tick]')).toBeNull()
  })
})

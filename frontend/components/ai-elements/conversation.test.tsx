import { describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { NextIntlClientProvider } from 'next-intl'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from './conversation'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('@/components/ui/message-scroller', () => ({
  MessageScroller: ({ className, children, ...props }: Record<string, unknown>) =>
    createElement('div', { 'data-slot': 'message-scroller', className, ...props }, children as React.ReactNode),
  MessageScrollerButton: ({ children, label, render, onClick, className, ref, ...props }: Record<string, unknown>) => {
    const renderProps = (render as { props?: Record<string, unknown> } | undefined)?.props ?? {}
    const { ref: renderedRef, ...buttonProps } = renderProps
    return createElement(
      'button',
      {
        ...buttonProps,
        ...props,
        onClick,
        className,
        ref: ref ?? renderedRef,
      },
      (children ?? label) as React.ReactNode,
    )
  },
  MessageScrollerItem: ({ children, ...props }: Record<string, unknown>) =>
    createElement('div', { 'data-slot': 'message-scroller-item', ...props }, children as React.ReactNode),
  MessageScrollerContent: ({ className, children, ...props }: Record<string, unknown>) =>
    createElement('div', { 'data-slot': 'message-scroller-content', className, ...props }, children as React.ReactNode),
  MessageScrollerProvider: ({ children, ...props }: Record<string, unknown>) =>
    createElement('div', { 'data-provider': true, ...props }, children as React.ReactNode),
  MessageScrollerViewport: ({ children, ...props }: Record<string, unknown>) =>
    createElement('div', { 'data-slot': 'message-scroller-viewport', ...props }, children as React.ReactNode),
}))

mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) =>
    createElement('button', props, children as React.ReactNode),
}))

mock.module('@/lib/utils', () => ({
  cn: (...values: unknown[]) => values.filter(Boolean).join(' '),
}))

describe('Conversation', () => {
  test('provides auto-scrolling message log and forwards real scroller props', () => {
    const tree = Conversation({
      className: 'custom',
      'aria-label': 'Messages',
      role: 'region',
    }) as { props: Record<string, unknown> }
    const root = tree.props.children as { props: Record<string, unknown> }

    expect(tree.props.autoScroll).toBe(true)
    expect(root.props).toMatchObject({
      'aria-label': 'Messages',
      className: 'relative flex-1 overflow-y-hidden custom',
      role: 'region',
    })
  })

  test('renders default empty-state guidance and allows custom content', () => {
    const fallback = renderToStaticMarkup(createElement(ConversationEmptyState))
    const custom = renderToStaticMarkup(
      createElement(
        ConversationEmptyState,
        { title: 'Ignored fallback', description: 'Ignored description' },
        createElement('p', null, 'Ask your first question'),
      ),
    )

    expect(fallback).toContain('No messages yet')
    expect(fallback).toContain('Start a conversation to see messages here')
    expect(custom).toContain('Ask your first question')
    expect(custom).not.toContain('Ignored fallback')
    expect(custom).not.toContain('Ignored description')
  })


  test('applies message IDs and scroll anchors to wrapped children', () => {
    const first = createElement('article', { key: 'message-1' }, 'first')
    const second = createElement('article', { key: 'message-2' }, 'second')
    const viewport = ConversationContent({
      children: [first, second],
      messageIds: ['message-1', 'message-2'],
      scrollAnchorIndex: 1,
    }) as { props: Record<string, unknown> }
    const content = viewport.props.children as { props: Record<string, unknown> }
    const items = content.props.children as Array<{
      key: string | null
      props: Record<string, unknown>
    }>

    expect(items[0].key).toContain('message-1')
    expect(items[0].props.messageId).toBe('message-1')
    expect(items[0].props.scrollAnchor).toBe(false)
    expect(items[0].props.children).toBe(first)
    expect(items[1].props.messageId).toBe('message-2')
    expect(items[1].props.scrollAnchor).toBe(true)
    expect(items[1].props.children).toBe(second)
  })
  test('renders the localized scroll control', () => {
    const html = renderToStaticMarkup(createElement(NextIntlClientProvider, {
      locale: 'zh', messages: { chat: { message: { scrollToStart: '滚动到开头', scrollToEnd: '滚动到底部' } } },
    }, createElement(ConversationScrollButton, { direction: 'start' })))
    expect(html).toContain('滚动到开头')
  })
})

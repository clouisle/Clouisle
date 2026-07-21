import { beforeEach, describe, expect, mock, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { act, create } from 'react-test-renderer'
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from './conversation'

const scrollToBottom = mock()
let isAtBottom = false

globalThis.IS_REACT_ACT_ENVIRONMENT = true

mock.module('use-stick-to-bottom', () => ({
  useStickToBottomContext: () => ({ isAtBottom, scrollToBottom }),
}))

beforeEach(() => {
  isAtBottom = false
  scrollToBottom.mockReset()
})

describe('Conversation', () => {
  test('exposes an accessible message log with smooth scrolling defaults', () => {
    const element = Conversation({ className: 'custom', 'aria-label': 'Messages' })

    expect(element.props).toMatchObject({
      'aria-label': 'Messages',
      className: 'relative flex-1 overflow-y-hidden custom',
      initial: 'smooth',
      resize: 'smooth',
      role: 'log',
    })
  })

  test('renders default empty-state guidance and allows custom content', () => {
    const fallback = renderToStaticMarkup(createElement(ConversationEmptyState))
    const custom = renderToStaticMarkup(
      createElement(
        ConversationEmptyState,
        { title: 'Ignored fallback', description: 'Ignored description' },
        createElement('p', null, 'Ask your first question')
      )
    )

    expect(fallback).toContain('No messages yet')
    expect(fallback).toContain('Start a conversation to see messages here')
    expect(custom).toContain('Ask your first question')
    expect(custom).not.toContain('Ignored fallback')
    expect(custom).not.toContain('Ignored description')
  })

  test('preserves content attributes while applying conversation spacing', () => {
    const element = ConversationContent({ className: 'compact', id: 'messages' })

    expect(element.props).toMatchObject({
      className: 'flex flex-col gap-8 p-4 compact',
      id: 'messages',
    })
  })

  test('scroll button only renders away from the bottom and triggers scroll', () => {
    let renderer: ReturnType<typeof create>
    act(() => {
      renderer = create(createElement(ConversationScrollButton, { className: 'floating', 'aria-label': 'Jump to bottom' }))
    })

    const button = renderer!.root.findByType('button')
    expect(button.props['aria-label']).toBe('Jump to bottom')
    expect(button.props.className).toContain('rounded-full')
    expect(button.props.className).toContain('floating')
    act(() => button.props.onClick())
    expect(scrollToBottom).toHaveBeenCalledTimes(1)
    act(() => renderer!.unmount())

    isAtBottom = true
    act(() => {
      renderer = create(createElement(ConversationScrollButton))
    })
    expect(renderer!.toJSON()).toBeNull()
    act(() => renderer!.unmount())
  })
})

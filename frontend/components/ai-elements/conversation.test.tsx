import { describe, expect, test } from 'bun:test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
} from './conversation'

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
})

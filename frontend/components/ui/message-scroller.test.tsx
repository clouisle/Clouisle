import { expect, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MessageScroller, MessageScrollerButton, MessageScrollerContent, MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport } from './message-scroller'

test('renders a message thread with an accessible return-to-bottom control', () => {
  const html = renderToStaticMarkup(<MessageScrollerProvider autoScroll>
    <MessageScroller>
      <MessageScrollerViewport aria-label="Conversation">
        <MessageScrollerContent>
          <MessageScrollerItem messageId="first">First message</MessageScrollerItem>
          <MessageScrollerItem messageId="second" scrollAnchor>Second message</MessageScrollerItem>
        </MessageScrollerContent>
      </MessageScrollerViewport>
      <MessageScrollerButton />
    </MessageScroller>
  </MessageScrollerProvider>)
  expect(html).toContain('Conversation')
  expect(html).toContain('First message')
  expect(html).toContain('Second message')
  expect(html).toContain('Scroll to end')
})

test('points the start-direction button upward and accepts a localized label', () => {
  const html = renderToStaticMarkup(<MessageScrollerProvider autoScroll>
    <MessageScroller>
      <MessageScrollerButton direction="start" label="Scroll to beginning" />
    </MessageScroller>
  </MessageScrollerProvider>)
  expect(html).toContain('rotate-180')
  expect(html).toContain('Scroll to beginning')
  expect(html).not.toContain('Scroll to start')
})

test('keeps the default end-direction icon unrotated', () => {
  const html = renderToStaticMarkup(<MessageScrollerProvider autoScroll>
    <MessageScroller>
      <MessageScrollerButton />
    </MessageScroller>
  </MessageScrollerProvider>)
  expect(html).toContain('Scroll to end')
  expect(html).not.toContain('rotate-180')
})

test('retains the start-direction fallback label and custom children', () => {
  const defaultLabel = renderToStaticMarkup(<MessageScrollerProvider autoScroll>
    <MessageScroller>
      <MessageScrollerButton direction="start" />
    </MessageScroller>
  </MessageScrollerProvider>)
  expect(defaultLabel).toContain('rotate-180')
  expect(defaultLabel).toContain('Scroll to start')

  const customContent = renderToStaticMarkup(<MessageScrollerProvider autoScroll>
    <MessageScroller>
      <MessageScrollerButton direction="start"><span>Custom action</span></MessageScrollerButton>
    </MessageScroller>
  </MessageScrollerProvider>)
  expect(customContent).toContain('Custom action')
  expect(customContent).not.toContain('rotate-180')
  expect(customContent).not.toContain('Scroll to start')
})

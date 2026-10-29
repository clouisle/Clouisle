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

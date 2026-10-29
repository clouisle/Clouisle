import { expect, test } from 'bun:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { Message, MessageAvatar, MessageContent, MessageFooter, MessageGroup, MessageHeader } from './message'
import { Bubble, BubbleContent, BubbleGroup, BubbleReactions } from './bubble'
import { Attachment, AttachmentAction, AttachmentActions, AttachmentContent, AttachmentDescription, AttachmentGroup, AttachmentMedia, AttachmentTitle, AttachmentTrigger } from './attachment'

test('renders a user message with an actionable bubble and reaction', () => {
  const html = renderToStaticMarkup(<MessageGroup><Message align="end">
    <MessageAvatar>U</MessageAvatar><MessageContent><MessageHeader>Me</MessageHeader>
      <BubbleGroup><Bubble align="end" variant="muted">
        <BubbleContent render={<button type="button" />}>Open response</BubbleContent>
        <BubbleReactions><button type="button" aria-label="Helpful">Like</button></BubbleReactions>
      </Bubble></BubbleGroup><MessageFooter>Sent</MessageFooter>
    </MessageContent>
  </Message></MessageGroup>)
  expect(html).toContain('Open response')
  expect(html).toContain('aria-label="Helpful"')
  expect(html).toContain('Sent')
  expect(html).toContain('data-align="end"')
})

test('renders attachment preview and a separately actionable remove control', () => {
  const html = renderToStaticMarkup(<AttachmentGroup><Attachment state="error">
    <AttachmentMedia>PDF</AttachmentMedia><AttachmentContent>
      <AttachmentTitle>report.pdf</AttachmentTitle><AttachmentDescription>Upload failed</AttachmentDescription>
    </AttachmentContent>
    <AttachmentTrigger render={<a href="/report.pdf" />} aria-label="Open report" />
    <AttachmentActions><AttachmentAction aria-label="Remove report">Remove</AttachmentAction></AttachmentActions>
  </Attachment></AttachmentGroup>)
  expect(html).toContain('report.pdf')
  expect(html).toContain('Upload failed')
  expect(html).toContain('href="/report.pdf"')
  expect(html).toContain('aria-label="Remove report"')
})

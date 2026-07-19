import { describe, expect, it } from 'bun:test'
import { convertBackendMessage, convertBackendMessages, type BackendMessage } from './message-converter'

function message(overrides: Partial<BackendMessage>): BackendMessage {
  return {
    id: 'message-1',
    conversation_id: 'conversation-1',
    role: 'assistant',
    content: 'Hello',
    created_at: '2026-07-19T00:00:00.000Z',
    ...overrides,
  }
}

describe('message converter', () => {
  it('skips system, tool, and empty assistant messages', () => {
    expect(convertBackendMessage(message({ role: 'system' }))).toBeNull()
    expect(convertBackendMessage(message({ role: 'tool' }))).toBeNull()
    expect(convertBackendMessage(message({ content: '', tool_calls: null, steps: null }))).toBeNull()
  })

  it('converts user text, images, and files in order', () => {
    const converted = convertBackendMessage(message({
      role: 'user',
      content: 'See attachments',
      images: [{ type: 'image', url: 'https://example.com/image.png' }],
      file_urls: [{ filename: 'notes.txt', url: 'https://example.com/notes.txt', size: 42, mime_type: 'text/plain' }],
    }))

    expect(converted?.parts).toEqual([
      { type: 'text', text: 'See attachments', state: 'done' },
      { type: 'image', url: 'https://example.com/image.png' },
      { type: 'file', filename: 'notes.txt', url: 'https://example.com/notes.txt', size: 42, mimeType: 'text/plain' },
    ])
  })

  it('attaches failed legacy tool results and marks their calls as errors', () => {
    const converted = convertBackendMessages([
      message({
        tool_calls: [{ id: 'call-1', name: 'search', arguments: { query: 'test' } }],
      }),
      message({
        id: 'tool-result',
        role: 'tool',
        content: JSON.stringify({ success: false, error: 'Unavailable' }),
        tool_call_id: 'call-1',
        tool_name: 'search',
      }),
    ])

    expect(converted[0].parts).toEqual([
      { type: 'text', text: 'Hello', state: 'done' },
      { type: 'tool-call', toolCallId: 'call-1', toolName: 'search', toolDisplayName: undefined, input: { query: 'test' }, state: 'error' },
      { type: 'tool-result', toolCallId: 'call-1', toolName: 'search', output: { success: false, error: 'Unavailable' }, isError: true },
    ])
  })

  it('renders successful media tool results as media parts', () => {
    const converted = convertBackendMessages([
      message({
        tool_calls: [{ id: 'call-1', name: 'generate_image', arguments: {} }],
      }),
      message({
        id: 'tool-result',
        role: 'tool',
        content: JSON.stringify({
          kind: 'media.image',
          success: true,
          prompt: 'a cat',
          images: [{ image: { url: 'https://example.com/cat.png' } }],
        }),
        tool_call_id: 'call-1',
      }),
    ])

    expect(converted[0].parts.at(-1)).toEqual({
      type: 'media-result',
      output: {
        kind: 'media.image',
        success: true,
        prompt: 'a cat',
        images: [{ image: { url: 'https://example.com/cat.png' } }],
      },
    })
    expect(converted[0].parts.some((part) => part.type === 'tool-result')).toBe(false)
  })
})

import { describe, expect, it } from 'bun:test'
import {
  convertBackendMessage,
  convertBackendMessages,
  isBackendMessage,
  type BackendMessage,
} from './message-converter'

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

  it('converts assistant reasoning, user input requests, status, and metadata', () => {
    const converted = convertBackendMessage(message({
      content: `Partial answer
<user_input_request>
  <question>Choose a path</question>
  <options><option>Alpha</option><option>Beta</option></options>
</user_input_request>`,
      reasoning_content: 'Consider both paths',
      duration_ms: 1250,
      round_status: 'max_iterations_reached',
      is_manually_stopped: true,
      version_number: 2,
      version_count: 3,
    }))

    expect(converted).toMatchObject({
      parts: [
        { type: 'reasoning', text: 'Consider both paths', state: 'done', duration: 1250 },
        { type: 'text', text: 'Partial answer', state: 'done' },
        { type: 'user-input-request', question: 'Choose a path', options: ['Alpha', 'Beta'], state: 'answered' },
        { type: 'iteration-cap-reached' },
        { type: 'stopped' },
      ],
      metadata: { isManuallyStopped: true, isError: false, preservedPartialProgress: false },
      versionNumber: 2,
      versionCount: 3,
    })
  })

  it('reconstructs usage and timing metadata from persisted token fields', () => {
    const converted = convertBackendMessage(message({
      token_usage: { prompt: 120, completion: 45, cache_read: 30, cache_creation: 10, total_input: 40 },
      duration_ms: 2000,
      first_token_ms: 300,
    }))

    expect(converted?.metadata).toEqual({
      isManuallyStopped: false,
      isError: false,
      preservedPartialProgress: false,
      usage: {
        prompt_tokens: 120,
        completion_tokens: 45,
        total_tokens: 165,
        cache_read_tokens: 30,
        cache_creation_tokens: 10,
        total_input_tokens: 40,
      },
      timing: {
        first_token_ms: 300,
        duration_ms: 2000,
        tokens_per_second: 22.5,
      },
    })
  })

  it('omits usage/timing metadata when no token usage was recorded', () => {
    const converted = convertBackendMessage(message({ duration_ms: 2000 }))

    expect(converted?.metadata).toEqual({
      isManuallyStopped: false,
      isError: false,
      preservedPartialProgress: false,
    })
  })

  it('omits timing.duration_ms when usage was persisted without a duration', () => {
    const converted = convertBackendMessage(message({
      token_usage: { prompt: 120, completion: 45 },
      first_token_ms: 300,
    }))

    expect(converted?.metadata).toEqual({
      isManuallyStopped: false,
      isError: false,
      preservedPartialProgress: false,
      usage: {
        prompt_tokens: 120,
        completion_tokens: 45,
        total_tokens: 165,
        cache_read_tokens: 0,
        cache_creation_tokens: 0,
        total_input_tokens: 120,
      },
      timing: {
        first_token_ms: 300,
        tokens_per_second: null,
      },
    })
    // The renderer types timing.duration_ms as a number; null must never be emitted.
    expect(converted?.metadata?.timing).not.toHaveProperty('duration_ms')
  })

  it('keeps malformed user input request XML as text', () => {
    const content = '<user_input_request><question>Choose one</question><options><option>Only</option></options></user_input_request>'

    expect(convertBackendMessage(message({ content }))?.parts).toEqual([
      { type: 'text', text: content, state: 'done' },
    ])
  })

  it('converts ordered assistant steps and their tool results', () => {
    const converted = convertBackendMessage(message({
      content: 'Final answer',
      steps: [
        {
          id: 'tool-step',
          role: 'tool',
          content: JSON.stringify({ answer: 42 }),
          tool_call_id: 'call-1',
          tool_name: 'calculator',
          created_at: '2026-07-19T00:00:02.000Z',
          round_index: 2,
        },
        {
          id: 'assistant-step',
          role: 'assistant',
          content: 'Using calculator',
          reasoning_content: 'Need arithmetic',
          tool_calls: [{ id: 'call-1', name: 'calculate', display_name: 'Calculator', arguments: { expression: '6 * 7' } }],
          created_at: '2026-07-19T00:00:01.000Z',
          round_index: 1,
        },
      ],
    }))

    expect(converted?.parts).toEqual([
      { type: 'reasoning', text: 'Need arithmetic', state: 'done' },
      { type: 'text', text: 'Using calculator', state: 'done' },
      { type: 'tool-call', toolCallId: 'call-1', toolName: 'calculate', toolDisplayName: 'Calculator', input: { expression: '6 * 7' }, state: 'done' },
      { type: 'tool-result', toolCallId: 'call-1', toolName: 'calculator', output: { answer: 42 }, isError: false },
      { type: 'text', text: 'Final answer', state: 'done' },
    ])
  })

  it('reconstructs multiple persisted iterations and keeps the final answer last', () => {
    const converted = convertBackendMessage(message({
      content: 'Final answer',
      reasoning_content: 'Final reasoning',
      steps: [
        {
          id: 'assistant-step-1',
          role: 'assistant',
          content: 'Answer A',
          reasoning_content: 'Reasoning A',
          tool_calls: [{ id: 'call-a', name: 'lookup', arguments: { q: 'a' } }],
          duration_ms: 100,
          created_at: '2026-07-19T00:00:01.000Z',
          round_index: 1,
        },
        {
          id: 'tool-step-1',
          role: 'tool',
          content: JSON.stringify({ result: 'A' }),
          tool_call_id: 'call-a',
          tool_name: 'lookup',
          created_at: '2026-07-19T00:00:02.000Z',
          round_index: 2,
        },
        {
          id: 'assistant-step-2',
          role: 'assistant',
          content: 'Answer B',
          reasoning_content: 'Reasoning B',
          tool_calls: [{ id: 'call-b', name: 'lookup', arguments: { q: 'b' } }],
          duration_ms: 200,
          created_at: '2026-07-19T00:00:03.000Z',
          round_index: 3,
        },
        {
          id: 'tool-step-2',
          role: 'tool',
          content: JSON.stringify({ result: 'B' }),
          tool_call_id: 'call-b',
          tool_name: 'lookup',
          created_at: '2026-07-19T00:00:04.000Z',
          round_index: 4,
        },
      ],
    }))

    expect(converted?.parts.map((part) => part.type)).toEqual([
      'reasoning',
      'text',
      'tool-call',
      'tool-result',
      'reasoning',
      'text',
      'tool-call',
      'tool-result',
      'reasoning',
      'text',
    ])
    expect(converted?.parts.filter((part) => part.type === 'reasoning').map((part) => part.text)).toEqual([
      'Reasoning A',
      'Reasoning B',
      'Final reasoning',
    ])
    expect(converted?.parts.filter((part) => part.type === 'tool-call').map((part) => part.toolCallId)).toEqual([
      'call-a',
      'call-b',
    ])
    expect(converted?.parts.filter((part) => part.type === 'text').map((part) => part.text)).toEqual([
      'Answer A',
      'Answer B',
      'Final answer',
    ])
  })

  it('maps per-step duration_ms onto step reasoning parts', () => {
    const converted = convertBackendMessage(message({
      content: 'Final answer',
      duration_ms: 5000,
      steps: [
        {
          id: 'step-1',
          role: 'assistant',
          content: '',
          reasoning_content: 'First reasoning round',
          duration_ms: 1200,
          created_at: '2026-07-19T00:00:00.000Z',
        },
        {
          id: 'step-2',
          role: 'assistant',
          content: 'Interim text',
          reasoning_content: 'Second reasoning round',
          created_at: '2026-07-19T00:00:01.000Z',
        },
      ],
    }))

    expect(converted?.parts).toEqual([
      { type: 'reasoning', text: 'First reasoning round', state: 'done', duration: 1200 },
      // Last step with no explicit duration: anchored at final created_at +
      // duration_ms (streaming flow), 00:00:00 + 5000ms − 00:00:01 = 4000ms.
      { type: 'reasoning', text: 'Second reasoning round', state: 'done', duration: 4000 },
      { type: 'text', text: 'Interim text', state: 'done' },
      { type: 'text', text: 'Final answer', state: 'done' },
    ])
  })

  it('falls back to created_at deltas when steps lack duration_ms', () => {
    const converted = convertBackendMessage(message({
      content: 'Final answer',
      created_at: '2026-07-19T00:00:06.000Z',
      steps: [
        {
          id: 'step-1',
          role: 'assistant',
          content: '',
          reasoning_content: 'First reasoning round',
          created_at: '2026-07-19T00:00:01.000Z',
        },
        {
          id: 'step-2',
          role: 'assistant',
          content: 'Interim text',
          reasoning_content: 'Second reasoning round',
          created_at: '2026-07-19T00:00:04.000Z',
        },
      ],
    }))

    expect(converted?.parts).toEqual([
      { type: 'reasoning', text: 'First reasoning round', state: 'done', duration: 3000 },
      { type: 'reasoning', text: 'Second reasoning round', state: 'done', duration: 2000 },
      { type: 'text', text: 'Interim text', state: 'done' },
      { type: 'text', text: 'Final answer', state: 'done' },
    ])
  })

  it('renders media results from assistant step traces', () => {
    const output = {
      kind: 'media.image',
      success: true,
      images: [{ image: { url: 'https://example.com/step.png' } }],
    }
    const converted = convertBackendMessage(message({
      content: '',
      steps: [
        {
          id: 'assistant-step',
          role: 'assistant',
          content: '',
          tool_calls: [{ id: 'call-1', name: 'generate_image', arguments: {} }],
          created_at: '2026-07-19T00:00:01.000Z',
        },
        {
          id: 'tool-step',
          role: 'tool',
          content: JSON.stringify(output),
          tool_call_id: 'call-1',
          created_at: '2026-07-19T00:00:02.000Z',
        },
      ],
    }))

    expect(converted?.parts).toEqual([
      { type: 'tool-call', toolCallId: 'call-1', toolName: 'generate_image', toolDisplayName: undefined, input: {}, state: 'done' },
      { type: 'media-result', output },
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

  it('aggregates RAG chunks onto the next assistant response', () => {
    const converted = convertBackendMessages([
      message({
        role: 'user',
        content: 'Question',
        rag_context: [
          { document_id: 'doc-1', document_name: 'Guide', content: 'First chunk', kb_id: 'kb-1', score: 0.4 },
          { document_id: 'doc-1', document_name: 'Guide', content: 'Second chunk', kb_id: 'kb-1', kb_name: 'Docs', score: 0.9 },
          { document_id: 'doc-2', document_name: 'FAQ', content: 'Other answer' },
        ],
      }),
      message({ id: 'assistant-1', content: 'Answer' }),
      message({ id: 'assistant-2', content: 'Follow-up' }),
    ])

    expect(converted[1].parts.slice(-2)).toEqual([
      {
        type: 'source-document',
        sourceId: 'doc-1',
        documentId: 'doc-1',
        documentName: 'Guide',
        content: 'First chunk\n\nSecond chunk',
        metadata: { kb_id: 'kb-1', kb_name: undefined, score: 0.9 },
      },
      {
        type: 'source-document',
        sourceId: 'doc-2',
        documentId: 'doc-2',
        documentName: 'FAQ',
        content: 'Other answer',
        metadata: { kb_id: undefined, kb_name: undefined, score: undefined },
      },
    ])
    expect(converted[2].parts.some((part) => part.type === 'source-document')).toBe(false)
  })

  it('marks error metadata and preserved partial progress', () => {
    const converted = convertBackendMessage(message({
      content: 'Provider unavailable',
      reasoning_content: 'Partial reasoning',
      round_status: 'error',
    }))

    expect(converted?.metadata).toEqual({
      isManuallyStopped: false,
      isError: true,
      preservedPartialProgress: true,
      errorMessage: 'Provider unavailable',
    })
  })

  it('keeps empty failed assistant turns so the historical error diagnostic renders', () => {
    // A failure before content/reasoning/steps were persisted must not be
    // dropped: the UI renders the error banner from metadata alone.
    const converted = convertBackendMessage(message({
      content: null,
      reasoning_content: null,
      tool_calls: null,
      steps: null,
      round_status: 'error',
    }))

    expect(converted).not.toBeNull()
    expect(converted).toMatchObject({
      role: 'assistant',
      parts: [],
      metadata: { isError: true, errorMessage: undefined, preservedPartialProgress: false },
    })
  })

  it('recognizes only message-shaped objects', () => {
    expect(isBackendMessage(message({}))).toBe(true)
    expect(isBackendMessage(null)).toBe(false)
    expect(isBackendMessage({ id: 'message-1', role: 'assistant' })).toBe(false)
  })
})

import { afterEach, describe, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import * as React from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { act } from 'react'

import { ApiAccessContent } from './_components/api-access-content'
import type { Agent } from '@/lib/api'

const messages: Record<string, string> = {
  'agents.apiAccess.title': 'API Access',
  'agents.apiAccess.description': 'Use this agent from your own code.',
  'agents.apiAccess.manageApiKeys': 'Manage API keys',
  'agents.apiAccess.draftWarningTitle': 'Draft agent',
  'agents.apiAccess.draftWarningDescription': 'Publish this agent before API traffic can use it.',
  'agents.apiAccess.endpoint': 'Endpoint',
  'agents.apiAccess.endpointDescription': 'Send streaming chat requests to this endpoint.',
  'agents.apiAccess.authentication': 'Authentication',
  'agents.apiAccess.authDescription': 'Use an API key bearer token.',
  'agents.apiAccess.requestBody': 'Request body',
  'agents.apiAccess.parameter': 'Parameter',
  'agents.apiAccess.type': 'Type',
  'agents.apiAccess.required': 'Required',
  'agents.apiAccess.paramDescription': 'Description',
  'agents.apiAccess.yes': 'Yes',
  'agents.apiAccess.no': 'No',
  'agents.apiAccess.params.message': 'User message',
  'agents.apiAccess.params.conversationId': 'Conversation id',
  'agents.apiAccess.params.variables': 'Variables',
  'agents.apiAccess.params.images': 'Images',
  'agents.apiAccess.params.fileUrls': 'File URLs',
  'agents.apiAccess.responseFormat': 'Response format',
  'agents.apiAccess.sseDescription': 'Responses are server-sent events.',
  'agents.apiAccess.event': 'Event',
  'agents.apiAccess.eventDescription': 'Description',
  'agents.apiAccess.messageEndExample': 'message_end example',
  'agents.apiAccess.codeExamples': 'Code examples',
  'agents.apiAccess.tabs.curl': 'cURL',
  'agents.apiAccess.tabs.python': 'Python',
  'agents.apiAccess.tabs.javascript': 'JavaScript',
  'agents.apiAccess.multiTurn.title': 'Multi-turn conversation',
  'agents.apiAccess.multiTurn.description': 'Reuse the conversation id.',
  'agents.apiAccess.multiTurn.step1Title': 'Start',
  'agents.apiAccess.multiTurn.step1Description': 'Start without conversation_id.',
  'agents.apiAccess.multiTurn.step2Title': 'Read id',
  'agents.apiAccess.multiTurn.step2Description': 'Read conversation_id from stream.',
  'agents.apiAccess.multiTurn.step3Title': 'Continue',
  'agents.apiAccess.multiTurn.step3Description': 'Send it on later requests.',
  'agents.apiAccess.agentVariables': 'Agent variables',
  'agents.apiAccess.variablesDescription': 'Include variables in the request.',
  'agents.apiAccess.variableName': 'Variable name',
  'agents.apiAccess.displayName': 'Display name',
  'agents.apiAccess.events.messageStart': 'Message started',
  'agents.apiAccess.events.ragStart': 'RAG started',
  'agents.apiAccess.events.ragContext': 'RAG context',
  'agents.apiAccess.events.reasoningStart': 'Reasoning started',
  'agents.apiAccess.events.reasoningDelta': 'Reasoning delta',
  'agents.apiAccess.events.reasoningEnd': 'Reasoning ended',
  'agents.apiAccess.events.contentDelta': 'Content delta',
  'agents.apiAccess.events.toolCall': 'Tool call',
  'agents.apiAccess.events.toolResult': 'Tool result',
  'agents.apiAccess.events.mediaResult': 'Media result',
  'agents.apiAccess.events.compressionStart': 'Compression started',
  'agents.apiAccess.events.compressionEnd': 'Compression ended',
  'agents.apiAccess.events.outputTruncated': 'Output truncated',
  'agents.apiAccess.events.iterationCapReached': 'Iteration cap reached',
  'agents.apiAccess.events.messageEnd': 'Message ended',
  'agents.apiAccess.events.error': 'Error event',
  'common.copiedToClipboard': 'Copied',
}

mock.module('next-intl', () => ({
  useTranslations: (namespace: string) => (key: string) => messages[`${namespace}.${key}`] ?? key,
}))

const toastSuccess = mock(() => {})
mock.module('sonner', () => ({ toast: { success: toastSuccess } }))

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const baseAgent = {
  id: 'agent-123',
  team: { id: 'team-1', name: 'Team' },
  name: 'Support bot',
  max_iterations: 3,
  hide_tool_calls: false,
  hide_message_actions: false,
  hide_reasoning: false,
  tools_config: [],
  variables: [],
  suggested_questions: [],
  knowledge_bases: [],
  enable_vision: false,
  enable_file_upload: false,
  enable_user_input_request: false,
  enable_memory: false,
  enable_image_generation: false,
  enable_video_generation: false,
  rag_mode: 'vector',
  status: 'published',
  visibility: 'team',
  conversation_count: 0,
  message_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
} satisfies Agent

let root: Root | null = null
let container: HTMLElement | null = null
let cleanupWindow: Window | null = null

async function renderApiContent(agent: Partial<Agent> = {}) {
  cleanupWindow = new Window()
  const { document, navigator } = cleanupWindow
  const writeText = mock(async () => {})
  Object.assign(globalThis, {
    window: cleanupWindow,
    document,
    navigator: {
      ...navigator,
      clipboard: { writeText },
    },
    HTMLElement: cleanupWindow.HTMLElement,
    SVGElement: cleanupWindow.SVGElement,
    MouseEvent: cleanupWindow.MouseEvent,
  })

  container = document.createElement('div')
  document.body.appendChild(container)
  root = createRoot(container)

  await act(async () => {
    root!.render(<ApiAccessContent agent={{ ...baseAgent, ...agent }} />)
  })

  return { container, document, writeText }
}

afterEach(async () => {
  if (root) {
    await act(async () => root!.unmount())
  }
  root = null
  container = null
  cleanupWindow?.close()
  cleanupWindow = null
  toastSuccess.mockClear()
})

describe('ApiAccessContent', () => {
  test('shows endpoint, token guidance, events, and variables for a published agent', async () => {
    const { container } = await renderApiContent({
      variables: [
        { name: 'customer_id', type: 'text', required: true, label: 'Customer ID' },
        { name: 'vip', type: 'checkbox', required: false, label: null },
      ],
    })

    expect(container.textContent).toContain('API Access')
    expect(container.textContent).toContain('POST')
    expect(container.textContent).toContain('http://localhost:8000/api/v1/agents/agent-123/chat/stream')
    expect(container.textContent).toContain('Authorization: Bearer YOUR_API_KEY')
    expect(container.textContent).toContain('message_end')
    expect(container.textContent).toContain('customer_id')
    expect(container.textContent).toContain('Customer ID')
    expect(container.textContent).not.toContain('Draft agent')
  })

  test('uses configured API base URL in endpoint and examples', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://api.example.test'
    const { container } = await renderApiContent()

    expect(container.textContent).toContain('https://api.example.test/api/v1/agents/agent-123/chat/stream')
    expect(container.textContent).toContain('curl -X POST "https://api.example.test/api/v1/agents/agent-123/chat/stream"')

    delete process.env.NEXT_PUBLIC_API_URL
  })

  test('warns draft agents instead of hiding API documentation', async () => {
    const { container } = await renderApiContent({ status: 'draft' })

    expect(container.textContent).toContain('Draft agent')
    expect(container.textContent).toContain('Publish this agent before API traffic can use it.')
    expect(container.textContent).toContain('Authorization: Bearer YOUR_API_KEY')
  })

  test('copies the nearest code block content', async () => {
    const { document, writeText } = await renderApiContent()
    const copyButton = document.querySelector('button') as HTMLButtonElement

    await act(async () => {
      copyButton.click()
    })

    expect(writeText).toHaveBeenCalledWith('Authorization: Bearer YOUR_API_KEY')
    expect(toastSuccess).toHaveBeenCalledWith('Copied')
  })
})

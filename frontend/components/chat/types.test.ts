import { describe, expect, test } from 'bun:test'

import {
  isFilePart,
  isImagePart,
  isIterationCapReachedPart,
  isMcpPart,
  isMcpToolCallPart,
  isMcpToolResultPart,
  isMediaResultPart,
  isReasoningPart,
  isSourceDocumentPart,
  isSourcePart,
  isSourceUrlPart,
  isStepStartPart,
  isStoppedPart,
  isTaskPart,
  isTextPart,
  isToolCallPart,
  isToolPart,
  isToolResultPart,
  isTruncatedPart,
  isUserInputRequestPart,
  type MessagePart,
} from './types'

type Guard = (part: MessagePart) => boolean

const cases: Array<[string, Guard, string[]]> = [
  ['text', isTextPart, ['text']],
  ['reasoning', isReasoningPart, ['reasoning']],
  ['tool call', isToolCallPart, ['tool-call']],
  ['tool result', isToolResultPart, ['tool-result']],
  ['MCP tool call', isMcpToolCallPart, ['mcp-tool-call']],
  ['MCP tool result', isMcpToolResultPart, ['mcp-tool-result']],
  ['URL source', isSourceUrlPart, ['source-url']],
  ['document source', isSourceDocumentPart, ['source-document']],
  ['file', isFilePart, ['file']],
  ['image', isImagePart, ['image']],
  ['media result', isMediaResultPart, ['media-result']],
  ['step start', isStepStartPart, ['step-start']],
  ['task', isTaskPart, ['task']],
  ['user input request', isUserInputRequestPart, ['user-input-request']],
  ['truncated', isTruncatedPart, ['truncated']],
  ['stopped', isStoppedPart, ['stopped']],
  ['iteration cap', isIterationCapReachedPart, ['iteration-cap-reached']],
  ['source', isSourcePart, ['source-url', 'source-document']],
  ['tool', isToolPart, ['tool-call', 'tool-result']],
  ['MCP', isMcpPart, ['mcp-tool-call', 'mcp-tool-result']],
]

const parts = [
  'text',
  'reasoning',
  'tool-call',
  'tool-result',
  'mcp-tool-call',
  'mcp-tool-result',
  'source-url',
  'source-document',
  'file',
  'image',
  'media-result',
  'step-start',
  'task',
  'user-input-request',
  'truncated',
  'stopped',
  'iteration-cap-reached',
].map((type) => ({ type }) as MessagePart)

describe('message part type guards', () => {
  test.each(cases)('recognizes only %s parts', (_name, guard, matchingTypes) => {
    for (const part of parts) {
      expect(guard(part)).toBe(matchingTypes.includes(part.type))
    }
  })
})

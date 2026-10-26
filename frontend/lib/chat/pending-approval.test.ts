import { describe, expect, test } from 'bun:test'

import {
  getPendingAskUserToolCallId,
  getPendingToolApproval,
  isRunOpenForInteractions,
} from './pending-approval'

describe('getPendingToolApproval', () => {
  test('extracts the bound execution from a waiting tool approval marker', () => {
    expect(
      getPendingToolApproval({
        status: 'waiting',
        pending_tool_call_id: 'call-1',
        pending_tool_name: 'mcp_calendar_delete_event',
        pending_tool_input: {
          interaction_kind: 'tool_approval',
          execution_id: 'execution-1',
        },
      })
    ).toEqual({
      executionId: 'execution-1',
      toolCallId: 'call-1',
      toolName: 'mcp_calendar_delete_event',
    })
  })

  test('ignores non-waiting states, ask_user pauses and missing execution ids', () => {
    expect(
      getPendingToolApproval({
        status: 'running',
        pending_tool_input: { interaction_kind: 'tool_approval', execution_id: 'execution-1' },
      })
    ).toBeNull()
    expect(
      getPendingToolApproval({
        status: 'waiting',
        pending_tool_name: 'ask_user',
        pending_tool_input: { questions: [] },
      })
    ).toBeNull()
    expect(
      getPendingToolApproval({
        status: 'waiting',
        pending_tool_input: { interaction_kind: 'tool_approval', execution_id: '  ' },
      })
    ).toBeNull()
  })
})

describe('getPendingAskUserToolCallId', () => {
  test('only returns the ask_user call id', () => {
    expect(
      getPendingAskUserToolCallId({
        status: 'waiting',
        pending_tool_call_id: 'call-ask',
        pending_tool_name: 'ask_user',
        pending_tool_input: { questions: [] },
      })
    ).toBe('call-ask')
    expect(
      getPendingAskUserToolCallId({
        status: 'waiting',
        pending_tool_call_id: 'call-approval',
        pending_tool_name: 'mcp_tool',
        pending_tool_input: { interaction_kind: 'tool_approval', execution_id: 'execution-1' },
      })
    ).toBeNull()
    expect(
      getPendingAskUserToolCallId({
        status: 'completed',
        pending_tool_call_id: 'call-ask',
        pending_tool_name: 'ask_user',
        pending_tool_input: { questions: [] },
      })
    ).toBeNull()
  })
})

describe('isRunOpenForInteractions', () => {
  test('accepts active and waiting runs only', () => {
    for (const status of ['queued', 'running', 'stopping', 'completing', 'waiting']) {
      expect(isRunOpenForInteractions(status)).toBe(true)
    }
    for (const status of ['completed', 'stopped', 'failed', 'interrupted', null]) {
      expect(isRunOpenForInteractions(status)).toBe(false)
    }
  })
})

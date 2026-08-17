'use client'

import * as React from 'react'
import type { SourceDocumentPart } from '@/components/chat/types'
import { TextWithCitations } from '@/components/chat/message'

export interface WorkflowResultNode {
  nodeType: string
  outputs?: Record<string, unknown> | null
  order: number
  status: string
}

interface WorkflowResultRendererProps {
  outputs?: Record<string, unknown> | null
  nodes?: WorkflowResultNode[]
  answerText?: string
  isStreaming?: boolean
}

const EMPTY_SOURCES: SourceDocumentPart[] = []

function hasOutputs(outputs: Record<string, unknown> | null | undefined): outputs is Record<string, unknown> {
  return !!outputs && Object.keys(outputs).length > 0
}

function answerFrom(outputs: Record<string, unknown> | null | undefined): string | null {
  return typeof outputs?.answer === 'string' && outputs.answer ? outputs.answer : null
}

export type WorkflowResultSelection =
  | { kind: 'markdown'; text: string }
  | { kind: 'json'; outputs: Record<string, unknown> }
  | { kind: 'empty' }

/**
 * Select the result blocks to render. Only the special output node type
 * (answer) is displayed — intermediate node outputs (llm/code/tool/...) are
 * deliberately excluded.
 *
 * - Live: the accumulated answer stream (all answer nodes' tokens already
 *   concatenated by the run hook) renders as one markdown block.
 * - History: every completed answer node renders as its own markdown block,
 *   stacked in execution order, so multiple output nodes accumulate.
 * - No answer node at all: falls back to the canonical persisted answer,
 *   then JSON outputs, then empty.
 */
export function selectWorkflowResults(
  outputs: Record<string, unknown> | null | undefined,
  nodes: WorkflowResultNode[],
  answerText?: string
): WorkflowResultSelection[] {
  if (answerText) {
    return [{ kind: 'markdown', text: answerText }]
  }

  const selections: WorkflowResultSelection[] = []

  const answerNodes = [...nodes]
    .filter((node) => node.status === 'success' || node.status === 'completed')
    .filter((node) => node.nodeType === 'answer')
    .filter((node) => hasOutputs(node.outputs))
    .sort((a, b) => a.order - b.order)

  for (const node of answerNodes) {
    const nodeAnswer = answerFrom(node.outputs)
    if (nodeAnswer) {
      selections.push({ kind: 'markdown', text: nodeAnswer })
    }
  }

  if (selections.length === 0) {
    const finalAnswer = answerFrom(outputs)
    if (finalAnswer) {
      selections.push({ kind: 'markdown', text: finalAnswer })
    } else if (hasOutputs(outputs)) {
      selections.push({ kind: 'json', outputs })
    }
  }

  if (selections.length === 0) {
    selections.push({ kind: 'empty' })
  }

  return selections
}

export function WorkflowResultRenderer({
  outputs,
  nodes = [],
  answerText,
  isStreaming = false,
}: WorkflowResultRendererProps) {
  const markdown = React.useCallback((text: string) => (
    <TextWithCitations
      text={text}
      sources={EMPTY_SOURCES}
      isStreaming={isStreaming}
    />
  ), [isStreaming])

  const selections = selectWorkflowResults(outputs, nodes, answerText)

  const renderedBlocks = selections
    .map((selection, index) => {
      if (selection.kind === 'markdown') {
        return <div key={index}>{markdown(selection.text)}</div>
      }

      if (selection.kind === 'json') {
        return (
          <pre key={index} className="max-h-[calc(100dvh-18rem)] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-5 text-sm leading-6">
            {JSON.stringify(selection.outputs, null, 2)}
          </pre>
        )
      }

      return null
    })
    .filter((block) => block !== null)

  if (renderedBlocks.length === 0) {
    return null
  }

  return <div className="space-y-6">{renderedBlocks}</div>
}

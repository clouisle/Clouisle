'use client'

import * as React from 'react'
import type { SourceDocumentPart } from '@/components/chat/types'
import { TextWithCitations } from '@/components/chat/message'
import { renderNodeOutput } from '@/app/(platform)/app/apps/workflow/[id]/_components/node-output-renderer'

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
  t: (key: string) => string
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
  | { kind: 'node'; node: WorkflowResultNode }
  | { kind: 'json'; outputs: Record<string, unknown> }
  | { kind: 'empty' }

// Node types that only echo inputs / start data; never rendered as output.
const NON_OUTPUT_NODE_TYPES = new Set(['start', 'user_input', 'trigger'])

/**
 * Select the result blocks to render. Unlike the previous single-selection
 * behavior, every completed output node is included: the primary answer text
 * (accumulated live stream or canonical persisted answer) plus each remaining
 * non-answer output node stacked in execution order. Answer nodes are not
 * stacked separately because their text is already rendered by the markdown
 * block (the live accumulation covers all of them; the persisted one covers
 * the canonical final answer).
 */
export function selectWorkflowResults(
  outputs: Record<string, unknown> | null | undefined,
  nodes: WorkflowResultNode[],
  answerText?: string
): WorkflowResultSelection[] {
  const selections: WorkflowResultSelection[] = []

  const completedNodes = [...nodes]
    .filter((node) => node.status === 'success' || node.status === 'completed')
    .filter((node) => hasOutputs(node.outputs))

  const primaryAnswer = answerText || answerFrom(outputs)
  if (primaryAnswer) {
    selections.push({ kind: 'markdown', text: primaryAnswer })
  } else {
    // Persisted runs without outputs.answer: fall back to the last-executed
    // answer node's text so history keeps showing the final answer.
    const lastAnswer = [...completedNodes]
      .sort((a, b) => b.order - a.order)
      .find((node) => node.nodeType === 'answer')
    const nodeAnswer = answerFrom(lastAnswer?.outputs)
    if (nodeAnswer) {
      selections.push({ kind: 'markdown', text: nodeAnswer })
    }
  }

  const outputNodes = completedNodes
    .filter((node) => node.nodeType !== 'answer')
    .filter((node) => !NON_OUTPUT_NODE_TYPES.has(node.nodeType))
    .sort((a, b) => a.order - b.order)

  for (const node of outputNodes) {
    selections.push({ kind: 'node', node })
  }

  if (selections.length === 0 && hasOutputs(outputs)) {
    selections.push({ kind: 'json', outputs })
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
  t,
}: WorkflowResultRendererProps) {
  const markdown = React.useCallback((text: string) => (
    <TextWithCitations
      text={text}
      sources={EMPTY_SOURCES}
      isStreaming={isStreaming}
    />
  ), [isStreaming])

  const selections = selectWorkflowResults(outputs, nodes, answerText)

  const renderedBlocks = selections.map((selection, index) => {
    if (selection.kind === 'markdown') {
      return <div key={index}>{markdown(selection.text)}</div>
    }

    if (selection.kind === 'node' && selection.node.outputs) {
      return <div key={index}>{renderNodeOutput(selection.node.nodeType, selection.node.outputs, t, markdown)}</div>
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

  if (renderedBlocks.length === 0) {
    return null
  }

  return <div className="space-y-6">{renderedBlocks}</div>
}

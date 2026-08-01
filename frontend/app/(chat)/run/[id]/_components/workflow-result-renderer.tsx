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

export function selectWorkflowResult(
  outputs: Record<string, unknown> | null | undefined,
  nodes: WorkflowResultNode[],
  answerText?: string
): WorkflowResultSelection {
  if (answerText) {
    return { kind: 'markdown', text: answerText }
  }

  const finalAnswer = answerFrom(outputs)
  if (finalAnswer) {
    return { kind: 'markdown', text: finalAnswer }
  }

  const completedNodes = [...nodes]
    .filter((node) => node.status === 'success' || node.status === 'completed')
    .filter((node) => hasOutputs(node.outputs))
    .sort((a, b) => b.order - a.order)

  const answerNode = completedNodes.find((node) => node.nodeType === 'answer')
  const nodeAnswer = answerFrom(answerNode?.outputs)
  if (nodeAnswer) {
    return { kind: 'markdown', text: nodeAnswer }
  }

  const outputNode = completedNodes.find((node) => node.nodeType !== 'start')
  if (outputNode) {
    return { kind: 'node', node: outputNode }
  }

  return hasOutputs(outputs)
    ? { kind: 'json', outputs }
    : { kind: 'empty' }
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

  const selection = selectWorkflowResult(outputs, nodes, answerText)

  if (selection.kind === 'markdown') {
    return markdown(selection.text)
  }

  if (selection.kind === 'node' && selection.node.outputs) {
    return renderNodeOutput(selection.node.nodeType, selection.node.outputs, t, markdown)
  }

  if (selection.kind === 'json') {
    return (
      <pre className="max-h-[calc(100dvh-18rem)] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-5 text-sm leading-6">
        {JSON.stringify(selection.outputs, null, 2)}
      </pre>
    )
  }

  return null
}

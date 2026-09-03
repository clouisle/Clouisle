import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, params?: Record<string, string | number>) =>
    params ? `${key}:${params.count}` : key,
}))

mock.module('@xyflow/react', () => ({
  Handle: (props: Record<string, unknown>) => <handle {...props} />,
  Position: { Left: 'left', Right: 'right' },
}))

const { ValidationChecklist } = await import('./validation-checklist')
const { CodeNode } = await import('./nodes/code-node')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
})

function render(element: React.ReactElement) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(element)
  })
  renderers.push(renderer!)
  return renderer!
}

describe('workflow UI boundaries', () => {
  test('renders the publish-ready boundary without a summary', () => {
    const renderer = render(
      <ValidationChecklist issues={[]} onClose={() => {}} onSelectNode={() => {}} />,
    )

    const output = JSON.stringify(renderer.toJSON())
    expect(output).toContain('checklist.allPassed')
    expect(output).toContain('checklist.readyToPublish')
    expect(output).not.toContain('checklist.errorCount')
    expect(output).not.toContain('checklist.warningCount')
  })

  test('groups validation states and sends only node actions', () => {
    const onClose = mock(() => {})
    const onSelectNode = mock(() => {})
    const renderer = render(
      <ValidationChecklist
        onClose={onClose}
        onSelectNode={onSelectNode}
        issues={[
          {
            id: 'missing-model', nodeId: 'llm-1', nodeLabel: 'Writer', nodeLabelKey: 'nodesLLM.label',
            nodeType: 'llm', severity: 'error', message: 'unused', messageKey: 'errors.model',
          },
          {
            id: 'missing-prompt', nodeId: 'llm-1', nodeLabel: 'Writer', nodeLabelKey: 'nodesLLM.label',
            nodeType: 'llm', severity: 'warning', message: 'unused', messageKey: 'warnings.prompt',
          },
          {
            id: 'workflow-name', nodeId: 'workflow', nodeLabel: 'workflow.name', nodeLabelKey: 'workflow.name',
            nodeType: 'unknown', severity: 'error', message: 'unused', messageKey: 'errors.name',
          },
        ]}
      />,
    )

    const buttons = renderer.root.findAllByType('button')
    act(() => buttons[0].props.onClick())
    act(() => buttons[1].props.onClick())
    act(() => buttons[2].props.onClick())

    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onSelectNode).toHaveBeenCalledTimes(1)
    expect(onSelectNode).toHaveBeenCalledWith('llm-1')
    const output = JSON.stringify(renderer.toJSON())
    expect(output).toContain('checklist.errorCount:2')
    expect(output).toContain('checklist.warningCount:1')
    expect(output).toContain('errors.model')
    expect(output).toContain('warnings.prompt')
  })

  test('renders normal and exception output handles for error-branch nodes', () => {
    const renderer = render(
      <CodeNode
        id="code-1"
        selected
        data={{
          type: 'code', label: 'Normalize', config: {},
          codeConfig: {
            language: 'python', code: '', inputs: [], outputs: [], outputVariable: 'result',
            retry: { enabled: false, maxRetries: 3, retryInterval: 1000 },
            errorHandling: { type: 'error_branch' },
          },
        }}
      />,
    )

    expect(renderer.root.findAllByType('handle')).toHaveLength(3)
    expect(renderer.root.findByProps({ id: 'error' }).props).toMatchObject({
      type: 'source', position: 'right', style: { top: 56 },
    })
    expect(JSON.stringify(renderer.toJSON())).toContain('nodesCode.exceptionBranch')
  })

  test('keeps a standard code node to one input and output', () => {
    const renderer = render(
      <CodeNode
        id="code-2"
        data={{
          type: 'code', label: '', config: {},
          codeConfig: {
            language: 'javascript', code: '', inputs: [], outputs: [], outputVariable: 'result',
            retry: { enabled: false, maxRetries: 3, retryInterval: 1000 },
            errorHandling: { type: 'none' },
          },
        }}
      />,
    )

    expect(renderer.root.findAllByType('handle')).toHaveLength(2)
    expect(renderer.root.findAllByProps({ id: 'error' })).toHaveLength(0)
    expect(JSON.stringify(renderer.toJSON())).toContain('nodesCode.label')
  })
})

import { describe, expect, mock, test } from 'bun:test'
import * as React from 'react'

mock.module('@xyflow/react', () => ({
  Handle: ({ type }: { type: string }) => <span data-handle={type} />,
  Position: { Left: 'left', Right: 'right' },
}))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string) => ({
    'nodesSubWorkflow.label': 'Sub-workflow',
    'nodesSubWorkflow.notSelected': 'Choose a workflow',
  })[key] ?? key,
}))

const { SubWorkflowNode } = await import('./sub-workflow-node')

function childrenText(element: React.ReactNode): string {
  if (typeof element === 'string') return element
  if (typeof element === 'number') return String(element)
  if (Array.isArray(element)) return element.map(childrenText).join('')
  if (React.isValidElement<{ children?: React.ReactNode }>(element)) return childrenText(element.props.children)
  return ''
}

function findByClass(element: React.ReactNode, className: string): React.ReactElement | undefined {
  if (!React.isValidElement<{ children?: React.ReactNode; className?: string }>(element)) return undefined
  if (element.props.className?.split(' ').includes(className)) return element
  return React.Children.toArray(element.props.children)
    .map((child) => findByClass(child, className))
    .find(Boolean)
}

describe('SubWorkflowNode', () => {
  test('shows the configured workflow and selected state', () => {
    const node = SubWorkflowNode({
      id: 'node-1',
      selected: true,
      data: {
        type: 'sub_workflow',
        label: 'Send report',
        config: {},
        subWorkflowConfig: {
          workflowId: 'workflow-1',
          workflowName: 'Daily reporting',
          inputMappings: [],
          outputVariable: 'report',
        },
      },
    })

    expect(childrenText(node)).toContain('Send report')
    expect(childrenText(node)).toContain('Daily reporting')
    expect(childrenText(node)).not.toContain('Choose a workflow')
    expect(findByClass(node, 'border-primary')).toBeDefined()
  })

  test('uses the fallback label and prompts for a workflow when unconfigured', () => {
    const node = SubWorkflowNode({ id: 'node-2', data: { type: 'sub_workflow', label: '', config: {} } })

    expect(childrenText(node)).toContain('Sub-workflow')
    expect(childrenText(node)).toContain('Choose a workflow')
    expect(findByClass(node, 'border-border')).toBeDefined()
  })
})

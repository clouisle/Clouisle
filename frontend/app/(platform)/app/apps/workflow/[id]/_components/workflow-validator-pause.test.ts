import { expect, mock, test } from 'bun:test'

mock.module('./node-config/utils', () => ({
  isValidVariableName: (value: string) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(value),
}))

const { validateWorkflow, getNodeTypeLabelKey } = await import('./workflow-validator')

test('rejects unconfigured and nested variable pause nodes', () => {
  const issues = validateWorkflow([
    {
      id: 'pause', type: 'pause', position: { x: 0, y: 0 }, parentId: 'iteration',
      data: {
        type: 'pause', label: 'Pause', config: {},
        pauseConfig: { mode: 'variables', inputVariables: [] },
      },
    },
  ], [])

  expect(issues.map((issue) => issue.message)).toEqual(expect.arrayContaining([
    'pauseInsideContainer',
    'pauseVariablesRequired',
  ]))
  expect(getNodeTypeLabelKey('pause')).toBe('nodeLabels.pause')
})

test('warns when a tool node sits inside a loop', () => {
  const issues = validateWorkflow(
    [
      {
        id: 'tool', type: 'tool', position: { x: 0, y: 0 }, parentId: 'loop',
        data: {
          type: 'tool', label: 'Tool', config: {},
          toolConfig: { toolId: 'tool-1', toolName: 'get_current_time', toolType: 'builtin' },
        },
      },
    ],
    []
  )

  // A warning, not an error: whether it is refused depends on the tool's policy,
  // which the backend enforces at save time.
  const issue = issues.find((item) => item.message === 'toolInContainer')
  expect(issue?.severity).toBe('warning')
  expect(issue?.nodeId).toBe('tool')
})

test('does not warn about a tool node outside a container', () => {
  const issues = validateWorkflow(
    [
      {
        id: 'tool', type: 'tool', position: { x: 0, y: 0 },
        data: {
          type: 'tool', label: 'Tool', config: {},
          toolConfig: { toolId: 'tool-1', toolName: 'get_current_time', toolType: 'builtin' },
        },
      },
    ],
    []
  )

  expect(issues.some((item) => item.message === 'toolInContainer')).toBe(false)
})

test('accepts downstream references to configured pause variables', () => {
  const issues = validateWorkflow(
    [
      {
        id: 'pause', type: 'pause', position: { x: 0, y: 0 },
        data: {
          type: 'pause', label: 'Pause', config: {},
          pauseConfig: {
            mode: 'variables',
            inputVariables: [{ name: 'approved_price', type: 'number', required: true }],
          },
        },
      },
      {
        id: 'answer', type: 'answer', position: { x: 200, y: 0 },
        data: {
          type: 'answer', label: 'Answer', config: {},
          answerConfig: { outputs: [{ id: 'price', sourceVariable: '{{pause.approved_price}}' }] },
        },
      },
    ],
    [{ id: 'pause-answer', source: 'pause', target: 'answer' }],
  )

  expect(issues.some((issue) => issue.message === 'variableNotAvailable')).toBe(false)
})

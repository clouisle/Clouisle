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

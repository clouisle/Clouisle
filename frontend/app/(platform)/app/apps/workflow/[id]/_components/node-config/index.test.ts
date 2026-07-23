import { expect, mock, test } from 'bun:test'

mock.module('./types', () => ({ extractVariableDisplayName: (value: string) => value }))
mock.module('./constants', () => ({ systemParameters: [] }))
mock.module('./utils', () => ({ isValidVariableName: () => true }))
mock.module('./variable-selector', () => ({ VariableSelector: 'VariableSelector' }))
mock.module('./components', () => ({ CodeEditor: 'CodeEditor' }))
mock.module('./configs', () => ({
  StartNodeConfig: 'StartNodeConfig',
  LLMNodeConfig: 'LLMNodeConfig',
  defaultLLMNodeConfig: { model: 'llm' },
  ToolNodeConfig: 'ToolNodeConfig',
  defaultToolNodeConfig: { tool: 'tool' },
  SubWorkflowNodeConfig: 'SubWorkflowNodeConfig',
  defaultSubWorkflowNodeConfig: { workflow: 'sub' },
  AgentNodeConfig: 'AgentNodeConfig',
  defaultAgentNodeConfig: { agent: 'agent' },
  KnowledgeRetrievalNodeConfig: 'KnowledgeRetrievalNodeConfig',
  defaultKnowledgeRetrievalNodeConfig: { knowledge: 'kb' },
}))
mock.module('./dialogs', () => ({ ParameterEditDialog: 'ParameterEditDialog', CodeInputDialog: 'CodeInputDialog' }))

const nodeConfig = await import('./index')

test('exposes the node configuration public API', () => {
  expect(nodeConfig.VariableSelector).toBe('VariableSelector')
  expect(nodeConfig.CodeEditor).toBe('CodeEditor')
  expect(nodeConfig.StartNodeConfig).toBe('StartNodeConfig')
  expect(nodeConfig.defaultLLMNodeConfig).toEqual({ model: 'llm' })
  expect(nodeConfig.defaultToolNodeConfig).toEqual({ tool: 'tool' })
  expect(nodeConfig.defaultSubWorkflowNodeConfig).toEqual({ workflow: 'sub' })
  expect(nodeConfig.ParameterEditDialog).toBe('ParameterEditDialog')
  expect(nodeConfig.CodeInputDialog).toBe('CodeInputDialog')
})

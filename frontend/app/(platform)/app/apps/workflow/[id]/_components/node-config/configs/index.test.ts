import { expect, mock, test } from 'bun:test'

const modules = [
  'start-node-config', 'code-node-config', 'llm-node-config', 'media-generation-node-config',
  'condition-node-config', 'iteration-node-config', 'loop-node-config', 'template-node-config',
  'file-to-url-node-config', 'variable-aggregator-node-config', 'variable-assignment-node-config',
  'parameter-extractor-node-config', 'question-classifier-node-config', 'answer-node-config',
  'tool-node-config', 'sub-workflow-node-config', 'agent-node-config', 'knowledge-retrieval-node-config',
]

for (const name of modules) {
  const componentName = name.split('-').map((part) => part[0].toUpperCase() + part.slice(1)).join('').replace('Config', 'Config')
  mock.module(`./${name}`, () => ({
    [componentName]: componentName,
    ...(name === 'llm-node-config' ? { LLMNodeConfig: 'LLMNodeConfig', defaultLLMNodeConfig: { model: 'llm' } } : {}),
    ...(name === 'tool-node-config' ? { ToolNodeConfig: 'ToolNodeConfig', defaultToolNodeConfig: { tool: 'tool' } } : {}),
    ...(name === 'sub-workflow-node-config' ? { SubWorkflowNodeConfig: 'SubWorkflowNodeConfig', defaultSubWorkflowNodeConfig: { workflow: 'sub' } } : {}),
    ...(name === 'agent-node-config' ? { AgentNodeConfig: 'AgentNodeConfig', defaultAgentNodeConfig: { agent: 'agent' } } : {}),
    ...(name === 'knowledge-retrieval-node-config' ? { KnowledgeRetrievalNodeConfig: 'KnowledgeRetrievalNodeConfig', defaultKnowledgeRetrievalNodeConfig: { knowledge: 'kb' } } : {}),
    ...(name === 'media-generation-node-config' ? { MediaGenerationNodeConfig: 'MediaGenerationNodeConfig', defaultMediaGenerationConfig: { model: 'media' } } : {}),
  }))
}

const configs = await import('./index')

test('exposes workflow node configuration components and defaults', () => {
  expect(configs.StartNodeConfig).toBe('StartNodeConfig')
  expect(configs.LLMNodeConfig).toBe('LLMNodeConfig')
  expect(configs.defaultLLMNodeConfig).toEqual({ model: 'llm' })
  expect(configs.defaultToolNodeConfig).toEqual({ tool: 'tool' })
  expect(configs.defaultSubWorkflowNodeConfig).toEqual({ workflow: 'sub' })
  expect(configs.defaultAgentNodeConfig).toEqual({ agent: 'agent' })
  expect(configs.defaultKnowledgeRetrievalNodeConfig).toEqual({ knowledge: 'kb' })
  expect(configs.defaultMediaGenerationConfig).toEqual({ model: 'media' })
})

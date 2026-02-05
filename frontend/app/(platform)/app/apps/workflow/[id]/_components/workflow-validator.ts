'use client'

import type { Node, Edge } from '@xyflow/react'

// 校验问题类型
export interface ValidationIssue {
  id: string
  nodeId: string
  nodeLabel: string
  nodeType: string
  severity: 'error' | 'warning'
  message: string
  field?: string
}

// 节点数据类型
interface WorkflowNodeData {
  [key: string]: unknown
  type: string
  label: string
  config: Record<string, unknown>
  // LLM 节点
  llmConfig?: {
    modelId?: string
    modelName?: string
    prompt?: string
    systemPrompt?: string
    inputVariable?: string
    outputVariable?: string
    outputVariables?: {
      response?: string
      reasoning?: string
      usage?: string
    }
  }
  // 问题分类器节点
  questionClassifierConfig?: {
    sourceVariable?: string
    modelId?: string
    modelName?: string
    categories?: Array<{ id: string; name: string }>
  }
  // 输出节点
  answerConfig?: {
    outputs?: Array<{ id: string; name: string; sourceVariable?: string }>
    streaming?: { enabled: boolean; variable?: string }
  }
  // 条件节点
  branches?: Array<{
    id: string
    type: 'if' | 'else_if' | 'else'
    conditions: Array<{ variable: string; operator: string; value?: string }>
  }>
  // 代码节点
  codeConfig?: {
    code?: string
    language?: string
    inputs?: Array<{ name: string; value?: string }>
    outputs?: Array<{ name: string; type?: string }>
  }
  // 模板节点
  templateConfig?: {
    template?: string
    variables?: Array<{ name: string; variable?: string }>
    outputVariable?: string
  }
  // 工具节点
  toolConfig?: {
    toolId?: string
    toolName?: string
    inputs?: Array<{ name: string; value?: string; required?: boolean }>
    outputVariable?: string
  }
  // 参数提取器
  parameterExtractorConfig?: {
    sourceVariable?: string
    modelId?: string
    extractionMethod?: string
    parameters?: Array<{ name: string; type: string; required?: boolean }>
  }
  // 变量聚合器
  variableAggregatorConfig?: {
    variables?: Array<{ id: string; sourceVariable?: string }>
    outputVariable?: string
    mode?: string
  }
  // 变量赋值
  variableAssignmentConfig?: {
    assignments?: Array<{ targetVariable: string; sourceVariable?: string; value?: string }>
  }
  // 迭代节点
  iterationConfig?: {
    iterateVariable?: string
    itemVariable?: string
    indexVariable?: string
    outputVariable?: string
  }
  // 循环节点
  loopConfig?: {
    conditionVariable?: string
    maxIterations?: number
    outputVariable?: string
    indexVariable?: string
    loopVariables?: Array<{ name: string; type: string }>
  }
  // 子工作流
  subWorkflowConfig?: {
    workflowId?: string
    workflowName?: string
    inputMappings?: Array<{ name: string; sourceVariable?: string }>
    outputVariable?: string
  }
  // Agent 节点
  agentConfig?: {
    agentId?: string
    agentName?: string
    inputVariable?: string
    outputVariable?: string
  }
  // 文件转URL
  fileToUrlConfig?: {
    inputs?: Array<{ name: string; sourceVariable?: string; sourceType?: string }>
  }
  // 用户输入节点参数
  parameters?: Array<{ name: string; type: string; required?: boolean }>
  // 触发器节点
  triggerConfig?: {
    triggerType?: string
    schedule?: string
    webhookPath?: string
  }
}

type WorkflowNode = Node<WorkflowNodeData>

// 节点类型显示名称
const nodeTypeLabels: Record<string, string> = {
  user_input: '开始',
  trigger: '触发器',
  llm: 'LLM',
  condition: '条件分支',
  sub_workflow: '子工作流',
  tool: '工具',
  iteration: '迭代',
  iteration_start: '迭代开始',
  iteration_exit: '迭代结束',
  loop: '循环',
  loop_start: '循环开始',
  loop_exit: '循环结束',
  code: '代码',
  template: '模板',
  file_to_url: '文件转URL',
  variable_aggregator: '变量聚合',
  variable_assignment: '变量赋值',
  parameter_extractor: '参数提取',
  question_classifier: '问题分类器',
  answer: '输出',
  start: '开始',
  end: '结束',
}

// 获取节点类型图标颜色
export const getNodeTypeColor = (nodeType: string): string => {
  const colors: Record<string, string> = {
    user_input: 'bg-cyan-500',
    trigger: 'bg-cyan-500',
    llm: 'bg-blue-500',
    condition: 'bg-blue-500',
    question_classifier: 'bg-violet-500',
    answer: 'bg-emerald-500',
    tool: 'bg-orange-500',
    code: 'bg-slate-500',
    template: 'bg-indigo-500',
    parameter_extractor: 'bg-purple-500',
    variable_aggregator: 'bg-teal-500',
    variable_assignment: 'bg-teal-500',
    iteration: 'bg-amber-500',
    loop: 'bg-amber-500',
    sub_workflow: 'bg-pink-500',
    file_to_url: 'bg-gray-500',
  }
  return colors[nodeType] || 'bg-gray-500'
}

// 系统变量列表
const systemVariables = ['sys.user_id', 'sys.app_id', 'sys.workflow_id', 'sys.run_id', 'sys.timestamp']

// 获取节点的上游节点 ID 集合
function getUpstreamNodeIds(nodeId: string, edges: Edge[]): Set<string> {
  const upstreamIds = new Set<string>()
  const visited = new Set<string>()
  const queue: string[] = []
  
  // 找到所有指向当前节点的边的 source 节点
  edges.forEach(edge => {
    if (edge.target === nodeId) {
      queue.push(edge.source)
    }
  })
  
  // BFS 遍历所有上游节点
  while (queue.length > 0) {
    const currentId = queue.shift()!
    if (visited.has(currentId)) continue
    visited.add(currentId)
    upstreamIds.add(currentId)
    
    // 继续查找 currentId 的上游节点
    edges.forEach(edge => {
      if (edge.target === currentId && !visited.has(edge.source)) {
        queue.push(edge.source)
      }
    })
  }
  
  return upstreamIds
}

// 获取节点提供的输出变量 ID 列表
function getNodeOutputVariables(node: WorkflowNode): string[] {
  const nodeType = node.type || node.data.type
  const variables: string[] = []
  
  switch (nodeType) {
    case 'user_input':
    case 'trigger':
    case 'start': {
      const params = node.data.parameters || []
      params.forEach(p => {
        if (p.name) variables.push(`${node.id}.${p.name}`)
      })
      break
    }
    
    case 'llm': {
      const config = node.data.llmConfig
      const outputVars = config?.outputVariables || { response: 'response', reasoning: 'reasoning', usage: 'usage' }
      if (outputVars.response) variables.push(`${node.id}.${outputVars.response}`)
      if (outputVars.reasoning) variables.push(`${node.id}.${outputVars.reasoning}`)
      if (outputVars.usage) variables.push(`${node.id}.${outputVars.usage}`)
      break
    }
    
    case 'code': {
      const config = node.data.codeConfig
      const outputs = config?.outputs || []
      outputs.forEach(o => {
        if (o.name) variables.push(`${node.id}.${o.name}`)
      })
      break
    }
    
    case 'template': {
      const config = node.data.templateConfig
      const outputVar = config?.outputVariable || 'output'
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'tool': {
      const config = node.data.toolConfig
      const outputVar = config?.outputVariable || 'result'
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'parameter_extractor': {
      const config = node.data.parameterExtractorConfig
      const params = config?.parameters || []
      params.forEach(p => {
        if (p.name) variables.push(`${node.id}.${p.name}`)
      })
      break
    }
    
    case 'variable_aggregator': {
      const config = node.data.variableAggregatorConfig
      const outputVar = config?.outputVariable || 'result'
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'iteration': {
      const config = node.data.iterationConfig
      const itemVar = config?.itemVariable || 'item'
      const indexVar = config?.indexVariable || 'index'
      const outputVar = config?.outputVariable || 'results'

      variables.push(`${node.id}.${itemVar}`)
      variables.push(`${node.id}.${indexVar}`)
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'loop': {
      const config = node.data.loopConfig
      const outputVar = config?.outputVariable || 'results'
      const indexVar = config?.indexVariable || 'index'
      variables.push(`${node.id}.${outputVar}`)
      variables.push(`${node.id}.${indexVar}`)
      // 循环变量
      const loopVars = config?.loopVariables || []
      loopVars.forEach(v => {
        if (v.name) variables.push(`${node.id}.${v.name}`)
      })
      break
    }
    
    case 'sub_workflow': {
      const config = node.data.subWorkflowConfig
      const outputVar = config?.outputVariable || 'result'
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'agent': {
      const config = node.data.agentConfig
      const outputVar = config?.outputVariable || 'response'
      variables.push(`${node.id}.${outputVar}`)
      break
    }
    
    case 'file_to_url': {
      const config = node.data.fileToUrlConfig
      const inputs = config?.inputs || []
      inputs.forEach(input => {
        if (input.name) variables.push(`${node.id}.${input.name}`)
      })
      break
    }
    
    case 'question_classifier': {
      // 问题分类器输出匹配的分类 ID
      variables.push(`${node.id}.matched_category`)
      break
    }
  }
  
  return variables
}

// 获取节点可用的上游变量列表
function getAvailableVariables(nodeId: string, nodes: WorkflowNode[], edges: Edge[]): Set<string> {
  const availableVars = new Set<string>()
  
  // 添加系统变量
  systemVariables.forEach(v => availableVars.add(v))
  
  // 获取当前节点
  const currentNode = nodes.find(n => n.id === nodeId)
  
  // 如果节点在循环/迭代内部（有 parentId），需要添加父节点的循环变量
  if (currentNode?.parentId) {
    const parentNode = nodes.find(n => n.id === currentNode.parentId)
    if (parentNode) {
      const parentType = parentNode.type || parentNode.data.type
      
      if (parentType === 'iteration') {
        // 迭代节点提供变量
        const config = parentNode.data.iterationConfig
        const itemVar = config?.itemVariable || 'item'
        const indexVar = config?.indexVariable || 'index'
        const outputVar = config?.outputVariable || 'results'

        availableVars.add(`${parentNode.id}.${itemVar}`)
        availableVars.add(`${parentNode.id}.${indexVar}`)
        availableVars.add(`${parentNode.id}.${outputVar}`)
      } else if (parentType === 'loop') {
        // 循环节点提供 index 和循环变量
        const config = parentNode.data.loopConfig
        const indexVar = config?.indexVariable || 'index'
        availableVars.add(`${parentNode.id}.${indexVar}`)
        // 循环变量
        const loopVars = config?.loopVariables || []
        loopVars.forEach(v => {
          if (v.name) availableVars.add(`${parentNode.id}.${v.name}`)
        })
      }
      
      // 递归获取父节点的可用变量（父节点能用的，子节点也能用）
      const parentAvailableVars = getAvailableVariables(parentNode.id, nodes, edges)
      parentAvailableVars.forEach(v => availableVars.add(v))
    }
  }
  
  // 获取上游节点
  const upstreamNodeIds = getUpstreamNodeIds(nodeId, edges)
  
  // 收集上游节点的输出变量
  nodes.forEach(node => {
    if (upstreamNodeIds.has(node.id)) {
      const outputs = getNodeOutputVariables(node)
      outputs.forEach(v => availableVars.add(v))
    }
  })
  
  return availableVars
}

// 清理变量引用，去除 {{ }} 包裹
function cleanVariableRef(variableRef: string): string {
  if (!variableRef) return ''
  let cleanRef = variableRef
  if (cleanRef.startsWith('{{')) {
    cleanRef = cleanRef.slice(2)
  }
  if (cleanRef.endsWith('}}')) {
    cleanRef = cleanRef.slice(0, -2)
  }
  return cleanRef.trim()
}

// 检查变量引用是否有效
function isVariableAvailable(variableRef: string, availableVars: Set<string>): boolean {
  if (!variableRef) return true // 空引用不检查
  
  const cleanRef = cleanVariableRef(variableRef)
  if (!cleanRef) return true
  
  // 系统变量直接检查
  if (cleanRef.startsWith('sys.')) {
    return systemVariables.includes(cleanRef)
  }
  
  // 对话变量暂不检查（conversation.xxx）
  if (cleanRef.startsWith('conversation.')) {
    return true
  }
  
  return availableVars.has(cleanRef)
}

// 从变量引用中提取变量名用于显示
function extractVariableName(variableRef: string): string {
  if (!variableRef) return ''
  const cleanRef = cleanVariableRef(variableRef)
  const parts = cleanRef.split('.')
  return parts.length > 1 ? parts.slice(1).join('.') : cleanRef
}

// 校验工作流
export function validateWorkflow(nodes: WorkflowNode[], edges: Edge[]): ValidationIssue[] {
  const issues: ValidationIssue[] = []
  let issueId = 0

  const createIssue = (
    node: WorkflowNode,
    severity: 'error' | 'warning',
    message: string,
    field?: string
  ): ValidationIssue => ({
    id: `issue-${++issueId}`,
    nodeId: node.id,
    nodeLabel: node.data.label || nodeTypeLabels[node.type || ''] || node.type || '未知节点',
    nodeType: node.type || '',
    severity,
    message,
    field,
  })

  // 排除注释节点
  const workflowNodes = nodes.filter(n => n.type !== 'comment' && n.data.type !== 'comment')

  // 遍历所有节点进行校验
  for (const node of workflowNodes) {
    const nodeType = node.type || node.data.type
    
    // 获取当前节点可用的上游变量
    const availableVars = getAvailableVariables(node.id, workflowNodes, edges)

    switch (nodeType) {
      // ========== 问题分类器 ==========
      case 'question_classifier': {
        const config = node.data.questionClassifierConfig
        
        // 检查输入变量
        if (!config?.sourceVariable) {
          issues.push(createIssue(node, 'error', '输入变量 不能为空', 'sourceVariable'))
        } else if (!isVariableAvailable(config.sourceVariable, availableVars)) {
          issues.push(createIssue(node, 'error', `变量 "${extractVariableName(config.sourceVariable)}" 不存在或不可用`, 'sourceVariable'))
        }
        
        // 检查模型
        if (!config?.modelId) {
          issues.push(createIssue(node, 'error', '未选择模型', 'modelId'))
        }
        
        // 检查分类类别
        if (!config?.categories || config.categories.length === 0) {
          issues.push(createIssue(node, 'error', '至少需要一个分类类别', 'categories'))
        } else {
          // 检查每个类别是否有名称
          const unnamedCategories = config.categories.filter(c => !c.name?.trim())
          if (unnamedCategories.length > 0) {
            issues.push(createIssue(node, 'warning', `${unnamedCategories.length} 个分类类别未命名`, 'categories'))
          }
        }
        break
      }

      // ========== 输出节点 ==========
      case 'answer': {
        const config = node.data.answerConfig
        
        // 检查输出变量
        if (!config?.outputs || config.outputs.length === 0) {
          issues.push(createIssue(node, 'error', '输出变量 不能为空', 'outputs'))
        } else {
          // 检查每个输出变量是否有源变量
          const missingSource = config.outputs.filter(o => !o.sourceVariable)
          if (missingSource.length > 0) {
            issues.push(createIssue(node, 'error', `${missingSource.length} 个输出变量未设置来源`, 'outputs'))
          }
          
          // 检查变量名
          const unnamedOutputs = config.outputs.filter(o => !o.name?.trim())
          if (unnamedOutputs.length > 0) {
            issues.push(createIssue(node, 'warning', `${unnamedOutputs.length} 个输出变量未命名`, 'outputs'))
          }
          
          // 检查源变量是否存在
          const invalidVars = config.outputs.filter(o => o.sourceVariable && !isVariableAvailable(o.sourceVariable, availableVars))
          if (invalidVars.length > 0) {
            invalidVars.forEach(v => {
              issues.push(createIssue(node, 'error', `变量 "${extractVariableName(v.sourceVariable!)}" 不存在或不可用`, 'outputs'))
            })
          }
        }
        break
      }

      // ========== LLM 节点 ==========
      case 'llm': {
        const config = node.data.llmConfig
        
        // 检查模型
        if (!config?.modelId) {
          issues.push(createIssue(node, 'error', '未选择模型', 'modelId'))
        }
        
        // 检查提示词
        if (!config?.prompt?.trim() && !config?.systemPrompt?.trim()) {
          issues.push(createIssue(node, 'warning', '建议配置提示词', 'prompt'))
        }
        break
      }

      // ========== 条件分支 ==========
      case 'condition': {
        const branches = node.data.branches
        
        if (!branches || branches.length === 0) {
          issues.push(createIssue(node, 'error', '至少需要配置一个条件分支', 'branches'))
        } else {
          // 检查 IF 分支的条件
          const ifBranches = branches.filter(b => b.type !== 'else')
          for (const branch of ifBranches) {
            if (!branch.conditions || branch.conditions.length === 0) {
              issues.push(createIssue(node, 'error', `分支 "${branch.type.toUpperCase()}" 没有配置条件`, 'branches'))
            } else {
              // 检查条件是否完整
              const incompleteConditions = branch.conditions.filter(
                c => !c.variable || !c.operator
              )
              if (incompleteConditions.length > 0) {
                issues.push(createIssue(node, 'error', `分支 "${branch.type.toUpperCase()}" 有不完整的条件`, 'branches'))
              }
              
              // 检查条件中的变量是否存在
              for (const condition of branch.conditions) {
                if (condition.variable && !isVariableAvailable(condition.variable, availableVars)) {
                  issues.push(createIssue(node, 'error', `条件变量 "${extractVariableName(condition.variable)}" 不存在或不可用`, 'branches'))
                }
              }
            }
          }
        }
        break
      }

      // ========== 代码节点 ==========
      case 'code': {
        const config = node.data.codeConfig
        
        // 检查代码
        if (!config?.code?.trim()) {
          issues.push(createIssue(node, 'error', '代码不能为空', 'code'))
        }
        
        // 检查输入变量
        if (config?.inputs && config.inputs.length > 0) {
          const missingInputs = config.inputs.filter(i => !i.value)
          if (missingInputs.length > 0) {
            issues.push(createIssue(node, 'warning', `${missingInputs.length} 个输入变量未设置来源`, 'inputs'))
          }
          
          // 检查输入变量是否存在
          for (const input of config.inputs) {
            if (input.value && !isVariableAvailable(input.value, availableVars)) {
              issues.push(createIssue(node, 'error', `输入变量 "${input.name}" 引用的 "${extractVariableName(input.value)}" 不存在`, 'inputs'))
            }
          }
        }
        break
      }

      // ========== 模板节点 ==========
      case 'template': {
        const config = node.data.templateConfig
        
        // 检查模板
        if (!config?.template?.trim()) {
          issues.push(createIssue(node, 'error', '模板内容不能为空', 'template'))
        }
        
        // 检查变量
        if (config?.variables && config.variables.length > 0) {
          const missingVars = config.variables.filter(v => !v.variable)
          if (missingVars.length > 0) {
            issues.push(createIssue(node, 'warning', `${missingVars.length} 个模板变量未设置来源`, 'variables'))
          }
          
          // 检查变量是否存在
          for (const v of config.variables) {
            if (v.variable && !isVariableAvailable(v.variable, availableVars)) {
              issues.push(createIssue(node, 'error', `模板变量 "${v.name}" 引用的 "${extractVariableName(v.variable)}" 不存在`, 'variables'))
            }
          }
        }
        break
      }

      // ========== 工具节点 ==========
      case 'tool': {
        const config = node.data.toolConfig
        
        // 检查工具
        if (!config?.toolId) {
          issues.push(createIssue(node, 'error', '未选择工具', 'toolId'))
        }
        
        // 检查必填输入
        if (config?.inputs) {
          const missingRequired = config.inputs.filter(i => i.required && !i.value)
          if (missingRequired.length > 0) {
            issues.push(createIssue(node, 'error', `${missingRequired.length} 个必填参数未设置`, 'inputs'))
          }
          
          // 检查输入变量是否存在
          for (const input of config.inputs) {
            if (input.value && !isVariableAvailable(input.value, availableVars)) {
              issues.push(createIssue(node, 'error', `参数 "${input.name}" 引用的 "${extractVariableName(input.value)}" 不存在`, 'inputs'))
            }
          }
        }
        break
      }

      // ========== 参数提取器 ==========
      case 'parameter_extractor': {
        const config = node.data.parameterExtractorConfig
        
        // 检查输入变量
        if (!config?.sourceVariable) {
          issues.push(createIssue(node, 'error', '输入变量 不能为空', 'sourceVariable'))
        } else if (!isVariableAvailable(config.sourceVariable, availableVars)) {
          issues.push(createIssue(node, 'error', `变量 "${extractVariableName(config.sourceVariable)}" 不存在或不可用`, 'sourceVariable'))
        }
        
        // 检查模型（LLM 和 JSONPath 需要模型）
        const method = config?.extractionMethod || 'llm'
        if ((method === 'llm' || method === 'jsonpath') && !config?.modelId) {
          issues.push(createIssue(node, 'error', '未选择模型', 'modelId'))
        }
        
        // 检查参数
        if (!config?.parameters || config.parameters.length === 0) {
          issues.push(createIssue(node, 'error', '至少需要配置一个提取参数', 'parameters'))
        }
        break
      }

      // ========== 变量聚合器 ==========
      case 'variable_aggregator': {
        const config = node.data.variableAggregatorConfig
        
        if (!config?.variables || config.variables.length === 0) {
          issues.push(createIssue(node, 'error', '至少需要配置一个聚合变量', 'variables'))
        } else {
          const missingSource = config.variables.filter(v => !v.sourceVariable)
          if (missingSource.length > 0) {
            issues.push(createIssue(node, 'error', `${missingSource.length} 个变量未设置来源`, 'variables'))
          }
          
          // 检查源变量是否存在
          for (const v of config.variables) {
            if (v.sourceVariable && !isVariableAvailable(v.sourceVariable, availableVars)) {
              issues.push(createIssue(node, 'error', `聚合变量引用的 "${extractVariableName(v.sourceVariable)}" 不存在`, 'variables'))
            }
          }
        }
        break
      }

      // ========== 变量赋值 ==========
      case 'variable_assignment': {
        const config = node.data.variableAssignmentConfig

        if (!config?.assignments || config.assignments.length === 0) {
          issues.push(createIssue(node, 'error', '至少需要配置一个赋值', 'assignments'))
        } else {
          // 检查赋值配置是否完整
          const incomplete = config.assignments.filter(a => {
            if (!a.targetVariable) return true
            // 需要源变量或值
            return !a.sourceVariable && !a.value
          })
          if (incomplete.length > 0) {
            issues.push(createIssue(node, 'error', `${incomplete.length} 个赋值配置不完整`, 'assignments'))
          }

          // 检查源变量是否存在
          for (const assignment of config.assignments) {
            if (assignment.sourceVariable && !isVariableAvailable(assignment.sourceVariable, availableVars)) {
              issues.push(createIssue(node, 'error', `赋值引用的 "${extractVariableName(assignment.sourceVariable)}" 不存在`, 'assignments'))
            }
          }
        }
        break
      }

    case 'iteration': {
      const config = node.data.iterationConfig

      // 检查迭代源变量
      const iteratorVar = config?.iterateVariable
      if (!iteratorVar) {
        issues.push(createIssue(node, 'error', '迭代源变量不能为空', 'iteratorVariable'))
      } else if (!isVariableAvailable(iteratorVar, availableVars)) {
        issues.push(createIssue(node, 'error', `迭代源变量 "${extractVariableName(iteratorVar)}" 不存在或不可用`, 'iteratorVariable'))
      }

      // 检查是否有子节点（iteration_start）
      const hasStartNode = workflowNodes.some(n =>
        (n.type === 'iteration_start' || n.data.type === 'iteration_start') &&
        n.parentId === node.id
      )
      if (!hasStartNode) {
        issues.push(createIssue(node, 'error', '迭代容器缺少开始节点', 'structure'))
      }

      // 检查容器内是否有其他节点
      const childNodes = workflowNodes.filter(n => n.parentId === node.id && n.type !== 'iteration_start')
      if (childNodes.length === 0) {
        issues.push(createIssue(node, 'warning', '迭代容器内没有处理节点', 'structure'))
      }

      break
    }

      // ========== 循环节点 ==========
      case 'loop': {
        const config = node.data.loopConfig

        if (!config?.conditionVariable && !config?.maxIterations) {
          issues.push(createIssue(node, 'warning', '建议设置循环条件或最大迭代次数', 'condition'))
        }

        // 检查条件变量是否存在
        if (config?.conditionVariable && !isVariableAvailable(config.conditionVariable, availableVars)) {
          issues.push(createIssue(node, 'error', `条件变量 "${extractVariableName(config.conditionVariable)}" 不存在或不可用`, 'conditionVariable'))
        }

        // 检查是否有子节点（loop_start）
        const hasStartNode = workflowNodes.some(n =>
          (n.type === 'loop_start' || n.data.type === 'loop_start') &&
          n.parentId === node.id
        )
        if (!hasStartNode) {
          issues.push(createIssue(node, 'error', '循环容器缺少开始节点', 'structure'))
        }

        // 检查容器内是否有其他节点
        const childNodes = workflowNodes.filter(n => n.parentId === node.id && n.type !== 'loop_start')
        if (childNodes.length === 0) {
          issues.push(createIssue(node, 'warning', '循环容器内没有处理节点', 'structure'))
        }

        break
      }

      // ========== 子工作流 ==========
      case 'sub_workflow': {
        const config = node.data.subWorkflowConfig
        
        if (!config?.workflowId) {
          issues.push(createIssue(node, 'error', '未选择子工作流', 'workflowId'))
        }
        
        // 检查输入映射的源变量是否存在
        if (config?.inputMappings) {
          for (const mapping of config.inputMappings) {
            if (mapping.sourceVariable && !isVariableAvailable(mapping.sourceVariable, availableVars)) {
              issues.push(createIssue(node, 'error', `输入映射 "${mapping.name}" 引用的 "${extractVariableName(mapping.sourceVariable)}" 不存在`, 'inputMappings'))
            }
          }
        }
        break
      }

      // ========== 用户输入节点 ==========
      case 'user_input': {
        // 用户输入节点使用 data.parameters 存储输入变量
        const parameters = node.data.parameters as Array<{ name: string; type: string; required?: boolean }> | undefined
        
        if (!parameters || parameters.length === 0) {
          issues.push(createIssue(node, 'warning', '建议配置输入变量', 'parameters'))
        }
        break
      }

      // ========== 触发器节点 ==========
      case 'trigger': {
        const config = node.data.triggerConfig
        
        if (!config?.triggerType) {
          issues.push(createIssue(node, 'error', '未选择触发类型', 'triggerType'))
        }
        break
      }

      // ========== 文件转URL节点 ==========
      case 'file_to_url': {
        const config = node.data.fileToUrlConfig
        
        // 检查输入配置
        if (config?.inputs && config.inputs.length > 0) {
          for (const input of config.inputs) {
            if (input.sourceVariable && !isVariableAvailable(input.sourceVariable, availableVars)) {
              issues.push(createIssue(node, 'error', `输入 "${input.name}" 引用的 "${extractVariableName(input.sourceVariable)}" 不存在`, 'inputs'))
            }
          }
        }
        break
      }

      // ========== Agent 节点 ==========
      case 'agent': {
        const config = node.data.agentConfig
        
        // 检查是否选择了 Agent
        if (!config?.agentId) {
          issues.push(createIssue(node, 'error', '未选择 Agent', 'agentId'))
        }
        
        // 检查输入变量是否存在
        if (config?.inputVariable && !isVariableAvailable(config.inputVariable, availableVars)) {
          issues.push(createIssue(node, 'error', `输入变量 "${extractVariableName(config.inputVariable)}" 不存在或不可用`, 'inputVariable'))
        }
        break
      }
    }
  }

  // ========== 检查连接问题 ==========

  // 检查孤立节点（无连接的节点）
  const connectedNodeIds = new Set<string>()
  for (const edge of edges) {
    connectedNodeIds.add(edge.source)
    connectedNodeIds.add(edge.target)
  }

  // 排除开始节点、特殊节点和注释节点
  const excludeTypes = ['start', 'user_input', 'trigger', 'iteration_start', 'loop_start', 'comment']
  for (const node of workflowNodes) {
    const nodeType = node.type || node.data.type
    if (!excludeTypes.includes(nodeType)) {
      // 如果节点在容器内（有 parentId），检查是否与容器内的其他节点连接
      if (node.parentId) {
        const hasInput = edges.some(e => e.target === node.id)
        if (!hasInput) {
          // 容器内的节点必须有输入连接（通常来自 iteration_start 或 loop_start）
          issues.push(createIssue(node, 'warning', '容器内节点没有输入连接', 'connection'))
        }
      } else {
        // 顶层节点检查是否有输入连接
        const hasInput = edges.some(e => e.target === node.id)
        if (!hasInput && nodes.length > 1) {
          issues.push(createIssue(node, 'warning', '节点没有输入连接', 'connection'))
        }
      }
    }
  }

  // 检查输出节点（answer）是否存在
  const hasAnswerNode = workflowNodes.some(n => n.type === 'answer' || n.data.type === 'answer')
  if (!hasAnswerNode && workflowNodes.length > 1) {
    // 如果有多个节点但没有输出节点，添加警告
    const startNode = workflowNodes.find(n => 
      n.type === 'start' || n.type === 'user_input' || n.type === 'trigger' ||
      n.data.type === 'start' || n.data.type === 'user_input' || n.data.type === 'trigger'
    )
    if (startNode) {
      issues.push({
        id: `issue-${++issueId}`,
        nodeId: 'workflow',
        nodeLabel: '工作流',
        nodeType: 'workflow',
        severity: 'warning',
        message: '工作流没有输出节点',
      })
    }
  }

  return issues
}

// 获取节点类型标签
export function getNodeTypeLabel(nodeType: string): string {
  return nodeTypeLabels[nodeType] || nodeType
}

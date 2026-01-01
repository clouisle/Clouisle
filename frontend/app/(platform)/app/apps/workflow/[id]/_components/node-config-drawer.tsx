'use client'

import * as React from 'react'
import { Node, Edge } from '@xyflow/react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { ConditionBranch } from './nodes/condition-node'
import { IterationConfig, defaultIterationConfig } from './nodes/iteration-node'
import { LoopConfig, defaultLoopConfig } from './nodes/loop-node'
import { CodeConfig, CodeInput, defaultCodeConfig } from './nodes/code-node'
import { TemplateConfig, defaultTemplateConfig } from './nodes/template-node'
import { FileToUrlConfig, defaultFileToUrlConfig } from './nodes/file-to-url-node'
import { VariableAggregatorConfig, defaultVariableAggregatorConfig, aggregationModeConfig } from './nodes/variable-aggregator-node'
import { VariableAssignmentConfig, defaultVariableAssignmentConfig } from './nodes/variable-assignment-node'
import { ParameterExtractorConfig, defaultParameterExtractorConfig } from './nodes/parameter-extractor-node'
import { QuestionClassifierConfig, defaultQuestionClassifierConfig } from './nodes/question-classifier-node'
import { AnswerNodeConfig as AnswerNodeConfigData, defaultAnswerNodeConfig } from './nodes/answer-node'
import { ToolNodeConfig as ToolNodeConfigData, defaultToolNodeConfig } from './nodes/tool-node'
import {
  Parameter,
  AvailableVariable,
  nodeTypeInfo,
  systemParameters,
  defaultStartParameters,
  getTypeName,
  getLoopVarTypeName,
  StartNodeConfig,
  LLMNodeConfig,
  LLMNodeConfigData,
  defaultLLMNodeConfig,
  CodeNodeConfig,
  ConditionNodeConfig,
  IterationNodeConfig,
  LoopNodeConfig,
  TemplateNodeConfig,
  FileToUrlNodeConfig,
  VariableAggregatorNodeConfig,
  VariableAssignmentNodeConfig,
  ParameterExtractorNodeConfig,
  QuestionClassifierNodeConfig,
  AnswerNodeConfig,
  ToolNodeConfig,
  ParameterEditDialog,
  CodeInputDialog,
} from './node-config'

interface NodeConfigDrawerProps {
  node: Node | null
  allNodes: Node[]
  allEdges: Edge[]
  open: boolean
  onClose: () => void
  onUpdate: (nodeId: string, data: Record<string, unknown>) => void
}

export function NodeConfigDrawer({ node, allNodes, allEdges, open, onClose, onUpdate }: NodeConfigDrawerProps) {
  const [label, setLabel] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [parameters, setParameters] = React.useState<Parameter[]>([])
  
  // 参数编辑模态框状态
  const [editingParam, setEditingParam] = React.useState<Parameter | null>(null)
  const [isParamDialogOpen, setIsParamDialogOpen] = React.useState(false)

  // 条件分支状态
  const [branches, setBranches] = React.useState<ConditionBranch[]>([])
  const [expandedBranches, setExpandedBranches] = React.useState<Set<string>>(new Set(['if']))
  
  // 迭代配置状态
  const [iterationConfig, setIterationConfig] = React.useState<IterationConfig>(defaultIterationConfig)
  
  // 循环配置状态
  const [loopConfig, setLoopConfig] = React.useState<LoopConfig>(defaultLoopConfig)
  
  // LLM 配置状态
  const [llmConfig, setLlmConfig] = React.useState<LLMNodeConfigData>(defaultLLMNodeConfig)
  
  // 代码节点配置状态
  const [codeConfig, setCodeConfig] = React.useState<CodeConfig>(defaultCodeConfig)
  
  // 模板转换配置状态
  const [templateConfig, setTemplateConfig] = React.useState<TemplateConfig>(defaultTemplateConfig)
  
  // 文件转URL配置状态
  const [fileToUrlConfig, setFileToUrlConfig] = React.useState<FileToUrlConfig>(defaultFileToUrlConfig)
  
  // 变量聚合器配置状态
  const [variableAggregatorConfig, setVariableAggregatorConfig] = React.useState<VariableAggregatorConfig>(defaultVariableAggregatorConfig)
  
  // 变量赋值配置状态
  const [variableAssignmentConfig, setVariableAssignmentConfig] = React.useState<VariableAssignmentConfig>(defaultVariableAssignmentConfig)
  
  // 参数提取器配置状态
  const [parameterExtractorConfig, setParameterExtractorConfig] = React.useState<ParameterExtractorConfig>(defaultParameterExtractorConfig)
  
  // 问题分类器配置状态
  const [questionClassifierConfig, setQuestionClassifierConfig] = React.useState<QuestionClassifierConfig>(defaultQuestionClassifierConfig)
  
  // 输出节点配置状态
  const [answerConfig, setAnswerConfig] = React.useState<AnswerNodeConfigData>(defaultAnswerNodeConfig)
  
  // 工具节点配置状态
  const [toolConfig, setToolConfig] = React.useState<ToolNodeConfigData>(defaultToolNodeConfig)
  
  // 代码输入变量编辑模态框状态
  const [editingCodeInput, setEditingCodeInput] = React.useState<CodeInput | null>(null)
  const [isCodeInputDialogOpen, setIsCodeInputDialogOpen] = React.useState(false)
  
  // 变量选择器状态
  const [variableSearch, setVariableSearch] = React.useState('')
  const [openVariablePopover, setOpenVariablePopover] = React.useState<string | null>(null)

  // 加载节点数据
  React.useEffect(() => {
    if (node) {
      setLabel((node.data as { label?: string })?.label || '')
      setDescription((node.data as { description?: string })?.description || '')
      
      const nodeType = node.type || (node.data as { type?: string })?.type || 'user_input'
      const isStartNode = nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start'
      const existingParams = (node.data as { parameters?: Parameter[] })?.parameters
      
      if (existingParams && existingParams.length > 0) {
        setParameters(existingParams)
      } else if (isStartNode) {
        setParameters(defaultStartParameters)
      } else {
        setParameters([])
      }

      if (nodeType === 'condition') {
        const existingBranches = (node.data as { branches?: ConditionBranch[] })?.branches
        if (existingBranches && existingBranches.length > 0) {
          setBranches(existingBranches)
        } else {
          setBranches([
            { id: 'if', type: 'if', name: 'IF', conditions: [], logicOperator: 'and' },
            { id: 'else', type: 'else', name: 'ELSE', conditions: [], logicOperator: 'and' },
          ])
        }
      }
      
      if (nodeType === 'iteration') {
        const existingConfig = (node.data as { iterationConfig?: IterationConfig })?.iterationConfig
        setIterationConfig(existingConfig || defaultIterationConfig)
      }
      
      if (nodeType === 'loop') {
        const existingConfig = (node.data as { loopConfig?: LoopConfig })?.loopConfig
        setLoopConfig(existingConfig || defaultLoopConfig)
      }
      
      if (nodeType === 'llm') {
        const existingConfig = (node.data as { llmConfig?: LLMNodeConfigData })?.llmConfig
        setLlmConfig(existingConfig || defaultLLMNodeConfig)
      }
      
      if (nodeType === 'code') {
        const existingConfig = (node.data as { codeConfig?: CodeConfig })?.codeConfig
        setCodeConfig(existingConfig || defaultCodeConfig)
      }
      
      if (nodeType === 'template') {
        const existingConfig = (node.data as { templateConfig?: TemplateConfig })?.templateConfig
        setTemplateConfig(existingConfig || defaultTemplateConfig)
      }
      
      if (nodeType === 'file_to_url') {
        const existingConfig = (node.data as { fileToUrlConfig?: FileToUrlConfig })?.fileToUrlConfig
        setFileToUrlConfig(existingConfig || defaultFileToUrlConfig)
      }
      
      if (nodeType === 'variable_aggregator') {
        const existingConfig = (node.data as { variableAggregatorConfig?: VariableAggregatorConfig })?.variableAggregatorConfig
        setVariableAggregatorConfig(existingConfig || defaultVariableAggregatorConfig)
      }
      
      if (nodeType === 'variable_assignment') {
        const existingConfig = (node.data as { variableAssignmentConfig?: VariableAssignmentConfig })?.variableAssignmentConfig
        setVariableAssignmentConfig(existingConfig || defaultVariableAssignmentConfig)
      }
      
      if (nodeType === 'parameter_extractor') {
        const existingConfig = (node.data as { parameterExtractorConfig?: ParameterExtractorConfig })?.parameterExtractorConfig
        setParameterExtractorConfig(existingConfig || defaultParameterExtractorConfig)
      }
      
      if (nodeType === 'question_classifier') {
        const existingConfig = (node.data as { questionClassifierConfig?: QuestionClassifierConfig })?.questionClassifierConfig
        setQuestionClassifierConfig(existingConfig || defaultQuestionClassifierConfig)
      }
      
      if (nodeType === 'answer') {
        const existingConfig = (node.data as { answerConfig?: AnswerNodeConfigData })?.answerConfig
        setAnswerConfig(existingConfig || defaultAnswerNodeConfig)
      }
      
      if (nodeType === 'tool') {
        const existingConfig = (node.data as { toolConfig?: ToolNodeConfigData })?.toolConfig
        setToolConfig(existingConfig || defaultToolNodeConfig)
      }
    }
  }, [node])

  // 自动保存
  React.useEffect(() => {
    if (node && (label || description || parameters.length >= 0)) {
      const timer = setTimeout(() => {
        const nodeType = node.type || (node.data as { type?: string })?.type || 'user_input'
        const updateData: Record<string, unknown> = {
          ...node.data as Record<string, unknown>,
          label,
          description,
          parameters,
        }
        
        if (nodeType === 'condition') updateData.branches = branches
        if (nodeType === 'iteration') updateData.iterationConfig = iterationConfig
        if (nodeType === 'loop') updateData.loopConfig = loopConfig
        if (nodeType === 'llm') updateData.llmConfig = llmConfig
        if (nodeType === 'code') updateData.codeConfig = codeConfig
        if (nodeType === 'template') updateData.templateConfig = templateConfig
        if (nodeType === 'file_to_url') updateData.fileToUrlConfig = fileToUrlConfig
        if (nodeType === 'variable_aggregator') updateData.variableAggregatorConfig = variableAggregatorConfig
        if (nodeType === 'variable_assignment') updateData.variableAssignmentConfig = variableAssignmentConfig
        if (nodeType === 'parameter_extractor') updateData.parameterExtractorConfig = parameterExtractorConfig
        if (nodeType === 'question_classifier') updateData.questionClassifierConfig = questionClassifierConfig
        if (nodeType === 'answer') updateData.answerConfig = answerConfig
        if (nodeType === 'tool') updateData.toolConfig = toolConfig
        
        onUpdate(node.id, updateData)
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [label, description, parameters, branches, iterationConfig, loopConfig, llmConfig, codeConfig, templateConfig, fileToUrlConfig, variableAggregatorConfig, variableAssignmentConfig, parameterExtractorConfig, questionClassifierConfig, answerConfig, toolConfig, node, onUpdate])

  // 获取上游节点 ID 集合（当前节点可以引用的节点）
  const getUpstreamNodeIds = React.useCallback((): Set<string> => {
    if (!node) return new Set()
    
    const upstreamIds = new Set<string>()
    const visited = new Set<string>()
    const queue: string[] = []
    
    // 从当前节点开始，向上游遍历
    // 找到所有指向当前节点的边的 source 节点
    allEdges.forEach(edge => {
      if (edge.target === node.id) {
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
      allEdges.forEach(edge => {
        if (edge.target === currentId && !visited.has(edge.source)) {
          queue.push(edge.source)
        }
      })
    }
    
    return upstreamIds
  }, [node, allEdges])

  // 获取可用变量列表
  const getAvailableVariables = React.useCallback((filterType?: 'iterable' | 'all'): AvailableVariable[] => {
    const variables: AvailableVariable[] = []
    const upstreamNodeIds = getUpstreamNodeIds()
    
    allNodes.forEach(n => {
      // 只包含上游节点的变量（排除当前节点和下游节点）
      if (!upstreamNodeIds.has(n.id)) return
      const nodeType = n.type || (n.data as { type?: string })?.type
      const nodeData = n.data as { parameters?: Parameter[]; label?: string }
      const nodeLabel = nodeData.label || nodeType || '节点'
      
      if (nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start') {
        const params = nodeData.parameters || []
        params.forEach(p => {
          const isArray = p.type === 'array' || p.type === 'files' || p.type === 'images'
          const isObject = p.type === 'object'
          const isFile = p.type === 'file' || p.type === 'image' || p.type === 'files' || p.type === 'images'
          const isIterable = isArray || isObject
          
          if (filterType === 'iterable' && !isIterable) return
          
          variables.push({
            id: `${n.id}.${p.name}`,
            name: p.name,
            type: getTypeName(p.type),
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray,
            isIterable,
            isFile, // 标记文件类型变量
          })
        })
      }
      
      if (nodeType === 'iteration') {
        const iterConfig = (n.data as { iterationConfig?: IterationConfig })?.iterationConfig || defaultIterationConfig
        const outputVar = iterConfig.outputVariable || 'results'
        
        variables.push({
          id: `${n.id}.${outputVar}`,
          name: outputVar,
          type: 'Array',
          group: n.id,
          groupLabel: nodeLabel,
          isSystem: false,
          isArray: true,
          isIterable: true,
        })
      }
      
      if (nodeType === 'loop') {
        const lpConfig = (n.data as { loopConfig?: LoopConfig })?.loopConfig || defaultLoopConfig
        const outputVar = lpConfig.outputVariable || 'results'
        const indexVar = lpConfig.indexVariable || 'index'
        const loopVars = lpConfig.loopVariables || []
        
        variables.push({
          id: `${n.id}.${outputVar}`,
          name: outputVar,
          type: 'Array',
          group: n.id,
          groupLabel: nodeLabel,
          isSystem: false,
          isArray: true,
          isIterable: true,
        })
        
        if (filterType !== 'iterable') {
          variables.push({
            id: `${n.id}.${indexVar}`,
            name: indexVar,
            type: 'Number',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: false,
            isIterable: false,
          })
        }
        
        loopVars.forEach(loopVar => {
          const isLoopVarArray = loopVar.type === 'array'
          const isLoopVarObject = loopVar.type === 'object'
          const isLoopVarIterable = isLoopVarArray || isLoopVarObject
          
          if (filterType === 'iterable' && !isLoopVarIterable) return
          
          variables.push({
            id: `${n.id}.${loopVar.name}`,
            name: loopVar.name,
            type: getLoopVarTypeName(loopVar.type),
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: isLoopVarArray,
            isIterable: isLoopVarIterable,
          })
        })
      }
      
      // 代码节点输出变量
      if (nodeType === 'code') {
        const cdConfig = (n.data as { codeConfig?: CodeConfig })?.codeConfig || defaultCodeConfig
        const outputs = cdConfig.outputs || []
        
        outputs.forEach(output => {
          if (!output.name) return // 跳过空名称
          
          const isOutputArray = output.type === 'array'
          const isOutputObject = output.type === 'object'
          const isOutputIterable = isOutputArray || isOutputObject
          
          if (filterType === 'iterable' && !isOutputIterable) return
          
          const typeMap: Record<string, string> = {
            'string': 'String',
            'number': 'Number',
            'boolean': 'Boolean',
            'array': 'Array',
            'object': 'Object',
          }
          
          variables.push({
            id: `${n.id}.${output.name}`,
            name: output.name,
            type: typeMap[output.type] || 'String',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: isOutputArray,
            isIterable: isOutputIterable,
          })
        })
      }
      
      // LLM 节点输出变量（三个：response、reasoning、usage）
      if (nodeType === 'llm') {
        const llmCfg = (n.data as { llmConfig?: LLMNodeConfigData })?.llmConfig || defaultLLMNodeConfig
        const outputVars = llmCfg.outputVariables || defaultLLMNodeConfig.outputVariables
        
        if (filterType !== 'iterable') {
          // 模型回复
          if (outputVars?.response) {
            variables.push({
              id: `${n.id}.${outputVars.response}`,
              name: outputVars.response,
              type: 'String',
              group: n.id,
              groupLabel: nodeLabel,
              isSystem: false,
              isArray: false,
              isIterable: false,
            })
          }
          
          // 推理过程
          if (outputVars?.reasoning) {
            variables.push({
              id: `${n.id}.${outputVars.reasoning}`,
              name: outputVars.reasoning,
              type: 'String',
              group: n.id,
              groupLabel: nodeLabel,
              isSystem: false,
              isArray: false,
              isIterable: false,
            })
          }
          
          // 用量统计（总 token 数）
          if (outputVars?.usage) {
            variables.push({
              id: `${n.id}.${outputVars.usage}`,
              name: outputVars.usage,
              type: 'Number',
              group: n.id,
              groupLabel: nodeLabel,
              isSystem: false,
              isArray: false,
              isIterable: false,
            })
          }
        }
      }
      
      // 模板转换节点输出变量
      if (nodeType === 'template') {
        const tplConfig = (n.data as { templateConfig?: TemplateConfig })?.templateConfig || defaultTemplateConfig
        const outputVar = tplConfig.outputVariable || 'output'
        
        if (filterType !== 'iterable') {
          variables.push({
            id: `${n.id}.${outputVar}`,
            name: outputVar,
            type: 'String',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: false,
            isIterable: false,
          })
        }
      }
      
      // 文件转URL节点输出变量
      if (nodeType === 'file_to_url') {
        const ftuConfig = (n.data as { fileToUrlConfig?: FileToUrlConfig })?.fileToUrlConfig || defaultFileToUrlConfig
        const inputs = ftuConfig.inputs || []
        
        inputs.forEach(input => {
          if (!input.name) return
          
          const isMultiple = input.sourceType === 'files' || input.sourceType === 'images'
          const isOutputArray = isMultiple
          
          if (filterType === 'iterable' && !isOutputArray) return
          
          variables.push({
            id: `${n.id}.${input.name}`,
            name: input.name,
            type: isMultiple ? 'Array' : 'String',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: isOutputArray,
            isIterable: isOutputArray,
          })
        })
      }
      
      // 变量聚合器节点输出变量
      if (nodeType === 'variable_aggregator') {
        const aggConfig = (n.data as { variableAggregatorConfig?: VariableAggregatorConfig })?.variableAggregatorConfig || defaultVariableAggregatorConfig
        const outputVar = aggConfig.outputVariable || 'result'
        const modeConfig = aggregationModeConfig[aggConfig.mode]
        const outputType = modeConfig.outputType
        const isOutputArray = outputType === 'Array'
        const isOutputObject = outputType === 'Object'
        const isOutputIterable = isOutputArray || isOutputObject
        
        if (filterType === 'iterable' && !isOutputIterable) return
        
        variables.push({
          id: `${n.id}.${outputVar}`,
          name: outputVar,
          type: outputType,
          group: n.id,
          groupLabel: nodeLabel,
          isSystem: false,
          isArray: isOutputArray,
          isIterable: isOutputIterable,
        })
      }
      
      // 参数提取器节点输出变量（每个参数是独立的输出变量）
      if (nodeType === 'parameter_extractor') {
        const peConfig = (n.data as { parameterExtractorConfig?: ParameterExtractorConfig })?.parameterExtractorConfig || defaultParameterExtractorConfig
        const params = peConfig.parameters || []
        
        params.forEach(param => {
          if (!param.name) return
          
          // 映射参数类型到变量类型
          const typeMap: Record<string, string> = {
            'string': 'String',
            'number': 'Number', 
            'boolean': 'Boolean',
            'array': 'Array',
            'object': 'Object',
          }
          const varType = typeMap[param.type] || 'String'
          const isArray = param.type === 'array'
          const isIterable = param.type === 'array' || param.type === 'object'
          
          if (filterType === 'iterable' && !isIterable) return
          
          variables.push({
            id: `${n.id}.${param.name}`,
            name: param.name,
            type: varType,
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray,
            isIterable,
          })
        })
      }
      
      // 工具节点输出变量
      if (nodeType === 'tool') {
        const tConfig = (n.data as { toolConfig?: ToolNodeConfigData })?.toolConfig || defaultToolNodeConfig
        const outputVar = tConfig.outputVariable || 'result'
        
        // Any 类型不做过滤，因为无法预知工具的返回类型
        variables.push({
          id: `${n.id}.${outputVar}`,
          name: outputVar,
          type: 'Any',
          group: n.id,
          groupLabel: nodeLabel,
          isSystem: false,
          isArray: false,
          isIterable: true, // Any 类型视为可迭代，以便能在任何场景使用
        })
      }
    })
    
    if (filterType !== 'iterable') {
      systemParameters.forEach(p => {
        variables.push({
          id: p.name,
          name: p.name,
          type: p.valueType,
          group: 'system',
          groupLabel: 'SYSTEM',
          isSystem: true,
          isArray: false,
          isIterable: false,
        })
      })
    }
    
    return variables
  }, [allNodes, getUpstreamNodeIds])

  // 获取对话变量（可写入的目标变量，来自开始节点的参数）
  const getConversationVariables = React.useCallback((): AvailableVariable[] => {
    const variables: AvailableVariable[] = []
    
    // 从开始节点获取参数作为对话变量
    allNodes.forEach(n => {
      const nodeType = n.type || (n.data as { type?: string })?.type
      
      if (nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start') {
        const nodeData = n.data as { parameters?: Parameter[]; label?: string }
        const params = nodeData.parameters || []
        
        params.forEach(p => {
          variables.push({
            id: `conversation.${p.name}`,
            name: p.name,
            type: getTypeName(p.type),
            group: 'conversation',
            groupLabel: '对话变量',
            isSystem: false,
            isArray: p.type === 'array',
            isIterable: p.type === 'array' || p.type === 'object',
          })
        })
      }
    })
    
    return variables
  }, [allNodes])

  // 检查输出变量名是否与系统变量冲突
  const isSystemVariableConflict = React.useCallback((varName: string) => {
    if (!varName) return false
    const lowerName = varName.toLowerCase()
    
    for (const p of systemParameters) {
      if (p.name.toLowerCase() === lowerName) return true
    }
    
    return false
  }, [])

  // 检查节点名称是否重复
  const isNodeLabelDuplicate = (labelName: string) => {
    if (!labelName || !node) return false
    const lowerName = labelName.toLowerCase()
    
    for (const n of allNodes) {
      if (n.id === node.id) continue
      const nLabel = (n.data as { label?: string })?.label
      if (nLabel && nLabel.toLowerCase() === lowerName) return true
    }
    
    return false
  }

  if (!node || !open) return null

  const nodeType = node.type || (node.data as { type?: string })?.type || 'user_input'
  const isStartNode = nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start'
  const info = nodeTypeInfo[nodeType] || nodeTypeInfo.user_input
  const Icon = info.icon

  const renderConfigFields = () => {
    switch (nodeType) {
      case 'user_input':
      case 'trigger':
      case 'start':
        return (
          <StartNodeConfig
            parameters={parameters}
            onAddParameter={() => {
              setEditingParam(null)
              setIsParamDialogOpen(true)
            }}
            onEditParameter={(param) => {
              setEditingParam(param)
              setIsParamDialogOpen(true)
            }}
            onRemoveParameter={(id) => setParameters(parameters.filter(p => p.id !== id))}
          />
        )
      
      case 'llm':
        return (
          <LLMNodeConfig
            config={llmConfig}
            onChange={setLlmConfig}
            getAvailableVariables={getAvailableVariables}
          />
        )
      
      case 'condition':
        return (
          <ConditionNodeConfig
            branches={branches}
            expandedBranches={expandedBranches}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onBranchesChange={setBranches}
            onExpandedBranchesChange={setExpandedBranches}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'iteration':
        return (
          <IterationNodeConfig
            config={iterationConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setIterationConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'loop':
        return (
          <LoopNodeConfig
            config={loopConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setLoopConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'code':
        return (
          <CodeNodeConfig
            config={codeConfig}
            onConfigChange={setCodeConfig}
            onAddInput={() => {
              setEditingCodeInput(null)
              setIsCodeInputDialogOpen(true)
            }}
          />
        )
      
      case 'template':
        return (
          <TemplateNodeConfig
            config={templateConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setTemplateConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'file_to_url':
        return (
          <FileToUrlNodeConfig
            config={fileToUrlConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setFileToUrlConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'variable_aggregator':
        return (
          <VariableAggregatorNodeConfig
            config={variableAggregatorConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setVariableAggregatorConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'variable_assignment':
        return (
          <VariableAssignmentNodeConfig
            config={variableAssignmentConfig}
            variables={getAvailableVariables()}
            conversationVariables={getConversationVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setVariableAssignmentConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'parameter_extractor':
        return (
          <ParameterExtractorNodeConfig
            config={parameterExtractorConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setParameterExtractorConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'question_classifier':
        return (
          <QuestionClassifierNodeConfig
            config={questionClassifierConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setQuestionClassifierConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'sub_workflow':
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>选择工作流</Label>
              <p className="text-xs text-muted-foreground">选择要调用的子工作流</p>
              <Button variant="outline" size="sm" className="w-full">选择工作流</Button>
            </div>
          </div>
        )
      
      case 'tool':
        return (
          <ToolNodeConfig
            config={toolConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setToolConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'answer':
        return (
          <AnswerNodeConfig
            config={answerConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setAnswerConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      default:
        return null
    }
  }

  return (
    <div
      className={cn(
        'absolute top-2 right-2 bottom-2 w-[360px] bg-card border border-border rounded-xl shadow-xl z-40',
        'transform transition-all duration-200 ease-out',
        open ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0 pointer-events-none'
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        <div className="flex items-center gap-3">
          <div className={cn('flex h-8 w-8 items-center justify-center rounded-lg text-white', info.color)}>
            <Icon className="h-4 w-4" />
          </div>
          <h3 className="text-sm font-medium">{info.title}</h3>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="h-[calc(100%-72px)]">
        <div className="p-4 pt-0 space-y-4">
          <div className="space-y-2">
            {!isStartNode && (
              <div className="space-y-2">
                <Label htmlFor="node-label">节点名称</Label>
                <Input
                  id="node-label"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="输入节点名称"
                  className={cn(isNodeLabelDuplicate(label) && '!border-destructive !ring-destructive/20')}
                />
                {isNodeLabelDuplicate(label) && (
                  <p className="text-[10px] text-destructive">节点名称与其他节点重复</p>
                )}
              </div>
            )}
            <Textarea
              id="node-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="添加描述..."
              className="min-h-[32px] h-8 text-xs resize-none border-transparent bg-transparent px-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus:border-border focus:bg-muted/30 focus:px-2 focus:rounded-md transition-all"
            />
          </div>

          <Tabs defaultValue="settings" className="w-full">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="settings" className="text-xs">设置</TabsTrigger>
              <TabsTrigger value="last-run" className="text-xs">上次执行</TabsTrigger>
            </TabsList>
            <TabsContent value="settings" className="mt-3">
              {renderConfigFields()}
            </TabsContent>
            <TabsContent value="last-run" className="mt-3">
              <div className="text-center py-6 text-muted-foreground text-xs">
                暂无执行记录
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </ScrollArea>

      {/* 参数编辑模态框 */}
      <ParameterEditDialog
        open={isParamDialogOpen}
        onOpenChange={setIsParamDialogOpen}
        editingParam={editingParam}
        existingParams={parameters}
        onSave={(param) => {
          if (editingParam) {
            setParameters(parameters.map(p => p.id === param.id ? param : p))
          } else {
            setParameters([...parameters, param])
          }
        }}
      />

      {/* 代码输入变量编辑对话框 */}
      <CodeInputDialog
        open={isCodeInputDialogOpen}
        onOpenChange={setIsCodeInputDialogOpen}
        editingInput={editingCodeInput}
        existingInputs={codeConfig.inputs}
        variables={getAvailableVariables()}
        variableSearch={variableSearch}
        openVariablePopover={openVariablePopover}
        onVariableSearchChange={setVariableSearch}
        onOpenVariablePopoverChange={setOpenVariablePopover}
        onSave={(input) => {
          if (editingCodeInput) {
            setCodeConfig(prev => ({
              ...prev,
              inputs: prev.inputs.map(i => i.id === input.id ? input : i)
            }))
          } else {
            setCodeConfig(prev => ({
              ...prev,
              inputs: [...prev.inputs, input]
            }))
          }
        }}
      />
    </div>
  )
}

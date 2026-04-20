'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Node, Edge } from '@xyflow/react'
import { X, Check, Copy, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { type NodeTrace, nodeStatusConfig, renderNodeOutput } from './node-output-renderer'
import { ConditionBranch } from './nodes/condition-node'
import { IterationConfig, defaultIterationConfig } from './nodes/iteration-node'
import { LoopConfig, defaultLoopConfig } from './nodes/loop-node'
import { CodeConfig, CodeInput, defaultCodeConfig } from './nodes/code-node'
import { TemplateConfig, defaultTemplateConfig } from './nodes/template-node'
import { FileToUrlConfig, defaultFileToUrlConfig } from './nodes/file-to-url-node'
import { VariableAggregatorConfig, defaultVariableAggregatorConfig, aggregationModeOutputTypes } from './nodes/variable-aggregator-node'
import { VariableAssignmentConfig, defaultVariableAssignmentConfig } from './nodes/variable-assignment-node'
import { ParameterExtractorConfig, defaultParameterExtractorConfig } from './nodes/parameter-extractor-node'
import { QuestionClassifierConfig, defaultQuestionClassifierConfig } from './nodes/question-classifier-node'
import { AnswerNodeConfig as AnswerNodeConfigData, defaultAnswerNodeConfig } from './nodes/answer-node'
import { ToolNodeConfig as ToolNodeConfigData, defaultToolNodeConfig } from './nodes/tool-node'
import { COMMENT_COLORS, type CommentColor } from './nodes/comment-node'
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
  SubWorkflowNodeConfig,
  type SubWorkflowNodeConfigType,
  defaultSubWorkflowNodeConfig,
  AgentNodeConfig,
  type AgentNodeConfigType,
  defaultAgentNodeConfig,
  KnowledgeRetrievalNodeConfig,
  type KnowledgeRetrievalNodeConfigType,
  defaultKnowledgeRetrievalNodeConfig,
} from './node-config'

interface NodeConfigDrawerProps {
  node: Node | null
  allNodes: Node[]
  allEdges: Edge[]
  open: boolean
  onClose: () => void
  onUpdate: (nodeId: string, data: Record<string, unknown>) => void
  readOnly?: boolean
  lastRunTrace?: NodeTrace | null
}

export function NodeConfigDrawer({ node, allNodes, allEdges, open, onClose, onUpdate, readOnly = false, lastRunTrace }: NodeConfigDrawerProps) {
  const t = useTranslations('workflow')
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
  
  // 子工作流节点配置状态
  const [subWorkflowConfig, setSubWorkflowConfig] = React.useState<SubWorkflowNodeConfigType>(defaultSubWorkflowNodeConfig)
  
  // Agent 节点配置状态
  const [agentConfig, setAgentConfig] = React.useState<AgentNodeConfigType>(defaultAgentNodeConfig)

  // 知识库检索节点配置状态
  const [knowledgeRetrievalConfig, setKnowledgeRetrievalConfig] = React.useState<KnowledgeRetrievalNodeConfigType>(defaultKnowledgeRetrievalNodeConfig)

  // 注释节点配置状态
  const [commentColor, setCommentColor] = React.useState<CommentColor>('amber')
  const [commentContent, setCommentContent] = React.useState('')

  
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
      
      if (nodeType === 'sub_workflow') {
        const existingConfig = (node.data as { subWorkflowConfig?: SubWorkflowNodeConfigType })?.subWorkflowConfig
        setSubWorkflowConfig(existingConfig || defaultSubWorkflowNodeConfig)
      }
      
      if (nodeType === 'agent') {
        const existingConfig = (node.data as { agentConfig?: AgentNodeConfigType })?.agentConfig
        setAgentConfig(existingConfig || defaultAgentNodeConfig)
      }

      if (nodeType === 'knowledge_retrieval') {
        const existingConfig = (node.data as { knowledgeRetrievalConfig?: KnowledgeRetrievalNodeConfigType })?.knowledgeRetrievalConfig
        setKnowledgeRetrievalConfig(existingConfig || defaultKnowledgeRetrievalNodeConfig)
      }

      if (nodeType === 'comment') {
        const existingColor = (node.data as { color?: CommentColor })?.color
        const existingContent = (node.data as { content?: string })?.content
        setCommentColor(existingColor || 'amber')
        setCommentContent(existingContent || '')
      }
    }
  }, [node])

  // 自动保存
  React.useEffect(() => {
    // 只读模式下不自动保存
    if (readOnly) return

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
        if (nodeType === 'sub_workflow') updateData.subWorkflowConfig = subWorkflowConfig
        if (nodeType === 'agent') updateData.agentConfig = agentConfig
        if (nodeType === 'knowledge_retrieval') updateData.knowledgeRetrievalConfig = knowledgeRetrievalConfig
        if (nodeType === 'comment') {
          updateData.color = commentColor
          updateData.content = commentContent
        }

        onUpdate(node.id, updateData)
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [label, description, parameters, branches, iterationConfig, loopConfig, llmConfig, codeConfig, templateConfig, fileToUrlConfig, variableAggregatorConfig, variableAssignmentConfig, parameterExtractorConfig, questionClassifierConfig, answerConfig, toolConfig, subWorkflowConfig, agentConfig, knowledgeRetrievalConfig, commentColor, commentContent, node, onUpdate, readOnly])

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

    // 从 allNodes 中获取当前节点的最新信息（包含 parentId）
    const currentNode = node ? allNodes.find(n => n.id === node.id) : null

    // 查找当前节点的父容器（循环/迭代节点）
    // 优先使用 parentId，如果没有则尝试通过 data.parentIterationId 或 data.parentLoopId 查找
    let parentNodeId = currentNode?.parentId
    if (!parentNodeId && currentNode?.data) {
      const nodeData = currentNode.data as { parentIterationId?: string; parentLoopId?: string }
      parentNodeId = nodeData.parentIterationId || nodeData.parentLoopId
    }
    
    // 如果当前节点在循环/迭代容器内部，添加父节点的内部变量
    if (parentNodeId) {
      const parentNode = allNodes.find(n => n.id === parentNodeId)
      if (parentNode) {
        const parentType = parentNode.type || (parentNode.data as { type?: string })?.type
        const parentLabel = (parentNode.data as { label?: string })?.label || parentType || t('nodeLabels.loop')

        if (parentType === 'iteration') {
          // 迭代节点提供变量给子节点
          const iterConfig = (parentNode.data as { iterationConfig?: IterationConfig })?.iterationConfig || defaultIterationConfig
          const iteratorType = iterConfig.iteratorType || 'array'
          const outputVar = iterConfig.outputVariable || 'results'

          if (iteratorType === 'object') {
            // 对象迭代：提供 key 和 value 变量
            const keyVar = iterConfig.keyVariable || 'key'
            const valueVar = iterConfig.valueVariable || 'value'

            variables.push({
              id: `${parentNode.id}.${keyVar}`,
              name: keyVar,
              type: 'String',
              group: parentNode.id,
              groupLabel: `${parentLabel} (${t('nodeConfig.iterationVars')})`,
              isSystem: false,
              isArray: false,
              isIterable: false,
            })

            variables.push({
              id: `${parentNode.id}.${valueVar}`,
              name: valueVar,
              type: 'Any',
              group: parentNode.id,
              groupLabel: `${parentLabel} (${t('nodeConfig.iterationVars')})`,
              isSystem: false,
              isArray: false,
              isIterable: true,
            })
          } else {
            // 数组迭代：提供 item 和 index 变量
            const itemVar = iterConfig.itemVariable || 'item'
            const indexVar = iterConfig.indexVariable || 'index'

            variables.push({
              id: `${parentNode.id}.${itemVar}`,
              name: itemVar,
              type: 'Any',
              group: parentNode.id,
              groupLabel: `${parentLabel} (${t('nodeConfig.iterationVars')})`,
              isSystem: false,
              isArray: false,
              isIterable: true,
            })

            if (filterType !== 'iterable') {
              variables.push({
                id: `${parentNode.id}.${indexVar}`,
                name: indexVar,
                type: 'Number',
                group: parentNode.id,
                groupLabel: `${parentLabel} (${t('nodeConfig.iterationVars')})`,
                isSystem: false,
                isArray: false,
                isIterable: false,
              })
            }
          }

          // 添加 results 变量（累积的结果数组）
          variables.push({
            id: `${parentNode.id}.${outputVar}`,
            name: outputVar,
            type: 'Array',
            group: parentNode.id,
            groupLabel: `${parentLabel} (${t('nodeConfig.iterationVars')})`,
            isSystem: false,
            isArray: true,
            isIterable: true,
          })
        } else if (parentType === 'loop') {
          // 循环节点提供 index 和循环变量给子节点
          const lpConfig = (parentNode.data as { loopConfig?: LoopConfig })?.loopConfig || defaultLoopConfig
          const indexVar = lpConfig.indexVariable || 'index'
          const loopVars = lpConfig.loopVariables || []
          
          if (filterType !== 'iterable') {
            variables.push({
              id: `${parentNode.id}.${indexVar}`,
              name: indexVar,
              type: 'Number',
              group: parentNode.id,
              groupLabel: `${parentLabel} (${t('nodeConfig.loopVars')})`,
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
              id: `${parentNode.id}.${loopVar.name}`,
              name: loopVar.name,
              type: getLoopVarTypeName(loopVar.type),
              group: parentNode.id,
              groupLabel: `${parentLabel} (${t('nodeConfig.loopVars')})`,
              isSystem: false,
              isArray: isLoopVarArray,
              isIterable: isLoopVarIterable,
            })
          })
        }
        
        // 添加父节点的上游节点到可用集合（父节点能引用的，子节点也能引用）
        allEdges.forEach(edge => {
          if (edge.target === parentNode.id) {
            // 递归地找父节点的所有上游
            const findUpstream = (nodeId: string, visited: Set<string>) => {
              if (visited.has(nodeId)) return
              visited.add(nodeId)
              upstreamNodeIds.add(nodeId)
              allEdges.forEach(e => {
                if (e.target === nodeId) {
                  findUpstream(e.source, visited)
                }
              })
            }
            findUpstream(edge.source, new Set())
          }
        })

        // 递归查找子图内的所有上游节点
        const findSubgraphUpstream = (nodeId: string, visited: Set<string>) => {
          if (visited.has(nodeId)) return
          visited.add(nodeId)

          allEdges.forEach(edge => {
            if (edge.target === nodeId) {
              const sourceNode = allNodes.find(n => n.id === edge.source)
              if (!sourceNode) return

              // 检查源节点是否在同一个子图内
              const sourceParentId = sourceNode.parentId ||
                (sourceNode.data as { parentIterationId?: string; parentLoopId?: string })?.parentIterationId ||
                (sourceNode.data as { parentIterationId?: string; parentLoopId?: string })?.parentLoopId

              if (sourceParentId === parentNodeId) {
                upstreamNodeIds.add(edge.source)
                findSubgraphUpstream(edge.source, visited)
              }
            }
          })
        }

        // 从当前节点开始，查找子图内的所有上游节点
        if (node) {
          findSubgraphUpstream(node.id, new Set())
        }
      }
    }
    
    allNodes.forEach(n => {
      // 只包含上游节点的变量（排除当前节点和下游节点）
      if (!upstreamNodeIds.has(n.id)) return
      const nodeType = n.type || (n.data as { type?: string })?.type
      const nodeData = n.data as { parameters?: Parameter[]; label?: string }
      const nodeLabel = nodeData.label || nodeType || t('nodeConfig.node')
      
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
        const modeConfig = aggregationModeOutputTypes[aggConfig.mode]
        const outputType = modeConfig
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
      
      // 子工作流节点输出变量
      if (nodeType === 'sub_workflow') {
        const swConfig = (n.data as { subWorkflowConfig?: SubWorkflowNodeConfigType })?.subWorkflowConfig || defaultSubWorkflowNodeConfig
        const outputVar = swConfig.outputVariable || 'result'
        
        // Object 类型，因为子工作流输出是对象
        variables.push({
          id: `${n.id}.${outputVar}`,
          name: outputVar,
          type: 'Object',
          group: n.id,
          groupLabel: nodeLabel,
          isSystem: false,
          isArray: false,
          isIterable: true,
        })
      }
      
      // Agent 节点输出变量
      if (nodeType === 'agent') {
        const aConfig = (n.data as { agentConfig?: AgentNodeConfigType })?.agentConfig || defaultAgentNodeConfig
        const outputVar = aConfig.outputVariable || 'response'

        // String 类型，因为 Agent 输出是回复字符串
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

      // 知识库检索节点输出变量
      if (nodeType === 'knowledge_retrieval') {
        const krConfig = (n.data as { knowledgeRetrievalConfig?: KnowledgeRetrievalNodeConfigType })?.knowledgeRetrievalConfig || defaultKnowledgeRetrievalNodeConfig
        const outputVar = krConfig.outputVariable || 'results'

        // results 是数组类型
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

        // context 是字符串类型（合并的上下文）
        if (filterType !== 'iterable') {
          variables.push({
            id: `${n.id}.context`,
            name: 'context',
            type: 'String',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: false,
            isIterable: false,
          })

          // totalFound 是数字类型（结果总数）
          variables.push({
            id: `${n.id}.totalFound`,
            name: 'totalFound',
            type: 'Number',
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray: false,
            isIterable: false,
          })
        }
      }
    })
    
    if (filterType !== 'iterable') {
      systemParameters.forEach(p => {
        variables.push({
          id: p.name,
          name: p.name,
          type: p.valueType,
          group: 'system',
          groupLabel: t('nodesCommon.system'),
          isSystem: true,
          isArray: false,
          isIterable: false,
        })
      })
    }
    
    return variables
  }, [allNodes, allEdges, node, getUpstreamNodeIds, t])

  // 获取对话变量（可写入的目标变量，来自开始节点的参数和子图内部变量）
  const getConversationVariables = React.useCallback((): AvailableVariable[] => {
    const variables: AvailableVariable[] = []

    // 从开始节点获取参数作为对话变量
    allNodes.forEach(n => {
      const nodeType = n.type || (n.data as { type?: string })?.type

      if (nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start') {
        const nodeData = n.data as { parameters?: Parameter[]; label?: string }
        // 如果开始节点没有配置参数，使用默认参数
        const params = (nodeData.parameters && nodeData.parameters.length > 0)
          ? nodeData.parameters
          : defaultStartParameters

        params.forEach(p => {
          variables.push({
            id: `conversation.${p.name}`,
            name: p.name,
            type: getTypeName(p.type),
            group: 'conversation',
            groupLabel: t('nodeConfig.conversationVars'),
            isSystem: false,
            isArray: p.type === 'array',
            isIterable: p.type === 'array' || p.type === 'object',
          })
        })
      }
    })

    // 如果当前节点在子图内（迭代/循环），添加 results 变量作为可写目标
    if (node) {
      const currentNode = allNodes.find(n => n.id === node.id)
      let parentNodeId = currentNode?.parentId
      if (!parentNodeId && currentNode?.data) {
        const nodeData = currentNode.data as { parentIterationId?: string; parentLoopId?: string }
        parentNodeId = nodeData.parentIterationId || nodeData.parentLoopId
      }

      if (parentNodeId) {
        const parentNode = allNodes.find(n => n.id === parentNodeId)
        const parentType = parentNode?.type || (parentNode?.data as { type?: string })?.type

        if (parentType === 'iteration' || parentType === 'loop') {
          variables.push({
            id: `${parentNodeId}.results`,
            name: 'results',
            type: 'Array',
            group: 'subgraph',
            groupLabel: parentType === 'iteration' ? t('nodeConfig.iterationVars') : t('nodeConfig.loopVars'),
            isSystem: false,
            isArray: true,
            isIterable: true,
          })
        }
      }
    }

    return variables
  }, [allNodes, node, t])

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
            nodeId={node?.id || ''}
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
          <SubWorkflowNodeConfig
            config={subWorkflowConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setSubWorkflowConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
        )
      
      case 'agent':
        return (
          <AgentNodeConfig
            config={agentConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setAgentConfig}
            onVariableSearchChange={setVariableSearch}
            onOpenVariablePopoverChange={setOpenVariablePopover}
          />
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

      case 'knowledge_retrieval':
        return (
          <KnowledgeRetrievalNodeConfig
            config={knowledgeRetrievalConfig}
            variables={getAvailableVariables()}
            variableSearch={variableSearch}
            openVariablePopover={openVariablePopover}
            onConfigChange={setKnowledgeRetrievalConfig}
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
      
      case 'comment':
        return (
          <div className="space-y-4">
            {/* 内容编辑 */}
            <div className="space-y-2">
              <Label>{t('nodeConfig.commentContent')}</Label>
              <Textarea
                placeholder={t('nodeConfig.commentPlaceholder')}
                value={commentContent}
                onChange={(e) => setCommentContent(e.target.value)}
                className="min-h-[120px] text-sm resize-none font-mono"
              />
              <p className="text-[10px] text-muted-foreground">
                {t('nodeConfig.commentMarkdownHint')}
              </p>
            </div>

            {/* 便签颜色 */}
            <div className="space-y-2">
              <Label>{t('nodeConfig.stickyColor')}</Label>
              <div className="grid grid-cols-6 gap-1.5">
                {(Object.keys(COMMENT_COLORS) as CommentColor[]).map((colorKey) => {
                  const colorConfig = COMMENT_COLORS[colorKey]
                  return (
                    <button
                      key={colorKey}
                      type="button"
                      onClick={() => setCommentColor(colorKey)}
                      className={cn(
                        'w-7 h-7 rounded-md border-2 transition-all flex items-center justify-center',
                        colorConfig.bg,
                        commentColor === colorKey
                          ? colorConfig.borderSelected
                          : 'border-transparent hover:scale-110'
                      )}
                    >
                      {commentColor === colorKey && (
                        <Check className="h-3.5 w-3.5 text-foreground/70" />
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
        )
      
      default:
        return null
    }
  }

  return (
    <div
      className={cn(
        'absolute top-14 right-2 bottom-2 w-[380px] min-w-[380px] bg-card border border-border rounded-xl shadow-xl z-40 flex flex-col overflow-hidden',
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
          <h3 className="text-sm font-medium">{t(`nodeLabels.${info.titleKey}`)}</h3>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Content */}
      <ScrollArea className="h-[calc(100%-72px)]">
        <div className="p-4 pt-0 space-y-4">
          {/* 只读模式提示 */}
          {readOnly && (
            <div className="bg-muted/50 rounded-lg px-3 py-2 text-xs text-muted-foreground">
              {t('nodeConfig.readOnlyNotice')}
            </div>
          )}
          {/* 注释节点不需要显示节点名称和描述 */}
          {nodeType !== 'comment' && (
            <div className="space-y-2">
              {!isStartNode && (
                <div className="space-y-2">
                  <Label htmlFor="node-label">{t('nodeConfig.nodeName')}</Label>
                  <Input
                    id="node-label"
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder={t('nodeConfig.nodeNamePlaceholder')}
                    className={cn(isNodeLabelDuplicate(label) && '!border-destructive !ring-destructive/20')}
                    disabled={readOnly}
                  />
                  {isNodeLabelDuplicate(label) && (
                    <p className="text-[10px] text-destructive">{t('nodeConfig.nodeNameDuplicate')}</p>
                  )}
                </div>
              )}
              <Textarea
                id="node-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={t('nodeConfig.addDescription')}
                className="min-h-[32px] h-8 text-xs resize-none border-transparent bg-transparent px-0 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 focus:border-border focus:bg-muted/30 focus:px-2 focus:rounded-md transition-all"
                disabled={readOnly}
              />
            </div>
          )}

          {/* 注释节点直接显示配置，不需要 Tabs */}
          {nodeType === 'comment' ? (
            renderConfigFields()
          ) : (
            <Tabs defaultValue="settings" className="w-full">
              <TabsList className="w-full grid grid-cols-2">
                <TabsTrigger value="settings" className="text-xs">{t('nodeConfig.settings')}</TabsTrigger>
                <TabsTrigger value="last-run" className="text-xs">{t('nodeConfig.lastRun')}</TabsTrigger>
              </TabsList>
              <TabsContent value="settings" className="mt-3">
                {renderConfigFields()}
              </TabsContent>
              <TabsContent value="last-run" className="mt-3">
                {lastRunTrace ? (
                  <LastRunContent trace={lastRunTrace} t={t} />
                ) : (
                  <div className="text-center py-6 text-muted-foreground text-xs">
                    {t('nodeConfig.noRunHistory')}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          )}
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

// 上次执行内容组件
function LastRunContent({ trace, t }: { trace: NodeTrace; t: (key: string) => string }) {
  const StatusIcon = nodeStatusConfig[trace.status]?.icon
  const statusClassName = nodeStatusConfig[trace.status]?.className || ''

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  return (
    <div className="space-y-3">
      {/* 状态栏 */}
      <div className="flex items-center gap-3 p-2.5 rounded-lg bg-muted/50">
        {StatusIcon && <StatusIcon className={cn('h-4 w-4', statusClassName)} />}
        <span className={cn(
          'text-xs font-medium',
          trace.status === 'success' && 'text-green-600',
          trace.status === 'failed' && 'text-red-600',
          trace.status === 'running' && 'text-blue-600',
          trace.status === 'skipped' && 'text-muted-foreground',
        )}>
          {trace.status}
        </span>
        {trace.durationMs !== undefined && (
          <span className="text-xs text-muted-foreground ml-auto">
            {trace.durationMs.toFixed(3)} ms
          </span>
        )}
      </div>

      {/* Token 信息 */}
      {trace.tokens && (trace.tokens.total ?? 0) > 0 && (
        <div className="flex items-center gap-4 text-xs p-2.5 bg-muted/30 rounded-lg">
          <div>
            <span className="text-muted-foreground">{t('runDrawer.tokenPrompt')}</span>
            <span>{trace.tokens.prompt || 0}</span>
          </div>
          <div>
            <span className="text-muted-foreground">{t('runDrawer.tokenCompletion')}</span>
            <span>{trace.tokens.completion || 0}</span>
          </div>
          <div>
            <span className="text-muted-foreground">{t('runDrawer.tokenTotal')}</span>
            <span className="font-medium">{trace.tokens.total || 0}</span>
          </div>
        </div>
      )}

      {/* 流式内容（运行中的 LLM 节点） */}
      {trace.nodeType === 'llm' && trace.status === 'running' && trace.streamingContent && (
        <div className="space-y-1">
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <Loader2 className="h-3 w-3 animate-spin" />
            <span>{t('runDrawer.generating')}</span>
          </div>
          <div className="p-2 bg-muted rounded text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">
            {trace.streamingContent}
            <span className="animate-pulse">▌</span>
          </div>
        </div>
      )}

      {/* 输出 */}
      {trace.outputs && Object.keys(trace.outputs).length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">{t('runDrawer.outputLabel')}</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1"
              onClick={() => copyToClipboard(JSON.stringify(trace.outputs, null, 2))}
            >
              <Copy className="h-3 w-3" />
            </Button>
          </div>
          {renderNodeOutput(trace.nodeType, trace.outputs, t)}
        </div>
      )}

      {/* 错误信息 */}
      {trace.error && (
        <div className="space-y-1">
          <span className="text-xs text-red-500 font-medium">{t('runDrawer.errorLabel')}</span>
          <div className="p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-600 dark:text-red-400">
            {(() => {
              const message = typeof trace.error === 'string' ? trace.error.trim() : ''
              if (
                !message
                || message.length > 200
                || /^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(message)
                || message.includes('\n')
                || message.includes('Traceback')
                || message.includes('Exception')
                || message.includes('HTTP ')
                || message.includes('Failed to fetch')
              ) {
                return t('runDrawer.unknownError')
              }
              return message
            })()}
          </div>
        </div>
      )}
    </div>
  )
}

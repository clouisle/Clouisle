'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  Play,
  Bug,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  StopCircle,
  ChevronDown,
  ChevronRight,
  Copy,
  Zap,
  Bot,
  Home,
  GitBranch,
  Wrench,
  Code,
  FileText,
  MessageSquareText,
  RefreshCw,
  Infinity,
  Tags,
  Variable,
  Combine,
  Braces,
  Link,
  Workflow as WorkflowIcon,
  Sparkles,
  SkipForward,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import {
  workflowsApi,
  Workflow,
  VariableDefinition,
  WorkflowEvent,
  RunStatus,
} from '@/lib/api/workflows'

interface WorkflowRunDrawerProps {
  workflow: Workflow | null
  variables: VariableDefinition[]  // 向后兼容，但优先从节点提取
  open: boolean
  onClose: () => void
}

// 从工作流定义中提取开始节点的输入参数
function extractInputVariables(workflow: Workflow | null): VariableDefinition[] {
  if (!workflow?.definition?.nodes) return []
  
  // 找到开始节点 (user_input 或 trigger)
  const startNode = workflow.definition.nodes.find(
    n => n.type === 'user_input' || n.type === 'trigger' || n.type === 'start'
  )
  
  if (!startNode) return []
  
  // 从节点数据中提取 parameters
  const nodeData = startNode.data as { parameters?: Array<{
    name: string
    type: string
    required?: boolean
    defaultValue?: string
    description?: string
  }> }
  
  const params = nodeData?.parameters || []
  
  return params.map(p => ({
    name: p.name,
    type: p.type || 'string',
    required: p.required ?? true,
    default: p.defaultValue,
    description: p.description,
  }))
}

// 节点执行追踪数据
interface NodeTrace {
  nodeId: string
  nodeType: string
  nodeLabel: string
  status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'
  startTime?: string
  endTime?: string
  durationMs?: number
  inputs?: Record<string, unknown>
  outputs?: Record<string, unknown>
  error?: string
  tokens?: {
    prompt?: number
    completion?: number
    total?: number
  }
  streamingContent?: string
}

// 节点图标映射
const nodeTypeIcons: Record<string, React.ElementType> = {
  user_input: Home,
  trigger: Zap,
  llm: Bot,
  condition: GitBranch,
  iteration: RefreshCw,
  loop: Infinity,
  question_classifier: Tags,
  answer: MessageSquareText,
  sub_workflow: WorkflowIcon,
  agent: Sparkles,
  tool: Wrench,
  code: Code,
  template: FileText,
  file_to_url: Link,
  variable_aggregator: Combine,
  variable_assignment: Variable,
  parameter_extractor: Braces,
}

// 节点颜色映射
const nodeTypeColors: Record<string, string> = {
  user_input: 'bg-primary',
  trigger: 'bg-amber-500',
  llm: 'bg-blue-500',
  condition: 'bg-cyan-500',
  iteration: 'bg-cyan-500',
  loop: 'bg-cyan-500',
  question_classifier: 'bg-violet-500',
  answer: 'bg-emerald-500',
  sub_workflow: 'bg-purple-500',
  agent: 'bg-indigo-500',
  tool: 'bg-emerald-500',
  code: 'bg-blue-500',
  template: 'bg-blue-500',
  file_to_url: 'bg-teal-500',
  variable_aggregator: 'bg-blue-500',
  variable_assignment: 'bg-blue-500',
  parameter_extractor: 'bg-blue-500',
}

const statusConfig: Record<
  RunStatus,
  { label: string; icon: React.ReactNode; className: string }
> = {
  pending: {
    label: 'statusPending',
    icon: <Clock className="h-4 w-4" />,
    className: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  },
  running: {
    label: 'statusRunning',
    icon: <Loader2 className="h-4 w-4 animate-spin" />,
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
  },
  success: {
    label: 'statusSuccess',
    icon: <CheckCircle2 className="h-4 w-4" />,
    className: 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
  },
  failed: {
    label: 'statusFailed',
    icon: <XCircle className="h-4 w-4" />,
    className: 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
  },
  cancelled: {
    label: 'statusCancelled',
    icon: <StopCircle className="h-4 w-4" />,
    className: 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
  },
  timeout: {
    label: 'statusTimeout',
    icon: <Clock className="h-4 w-4" />,
    className: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300',
  },
}

const nodeStatusConfig = {
  pending: { icon: Clock, className: 'text-gray-400' },
  running: { icon: Loader2, className: 'text-blue-500 animate-spin' },
  success: { icon: CheckCircle2, className: 'text-green-500' },
  failed: { icon: XCircle, className: 'text-red-500' },
  skipped: { icon: SkipForward, className: 'text-gray-400' },
}

export function WorkflowRunDrawer({
  workflow,
  variables: propVariables,
  open,
  onClose,
}: WorkflowRunDrawerProps) {
  const t = useTranslations('workflow')

  // 从工作流节点中提取输入变量，优先级：节点 parameters > prop variables
  const variables = React.useMemo(() => {
    const extracted = extractInputVariables(workflow)
    return extracted.length > 0 ? extracted : propVariables
  }, [workflow, propVariables])

  // 标签页状态
  const [activeTab, setActiveTab] = React.useState<string>('input')

  // 输入值状态
  const [inputValues, setInputValues] = React.useState<Record<string, string>>({})

  // 运行状态
  const [isRunning, setIsRunning] = React.useState(false)
  const [runId, setRunId] = React.useState<string | null>(null)
  const [runStatus, setRunStatus] = React.useState<RunStatus | null>(null)
  const [outputs, setOutputs] = React.useState<Record<string, unknown> | null>(null)
  const [totalDurationMs, setTotalDurationMs] = React.useState<number | null>(null)
  const [totalTokens, setTotalTokens] = React.useState<number>(0)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  
  // 统一的流式输出（按执行顺序追加所有 answer 节点的输出）
  const [streamingOutput, setStreamingOutput] = React.useState<string>('')

  // 节点追踪状态
  const [nodeTraces, setNodeTraces] = React.useState<Map<string, NodeTrace>>(new Map())
  const [expandedNodes, setExpandedNodes] = React.useState<Set<string>>(new Set())

  // SSE 连接关闭函数
  const closeStreamRef = React.useRef<(() => void) | null>(null)

  // 运行开始时间
  const runStartTimeRef = React.useRef<string | null>(null)
  
  // 使用 ref 存储节点类型映射，避免闭包问题
  const nodeTypesRef = React.useRef<Map<string, string>>(new Map())

  // 初始化输入值
  React.useEffect(() => {
    if (variables.length > 0) {
      const initialValues: Record<string, string> = {}
      for (const variable of variables) {
        initialValues[variable.name] = variable.default?.toString() || ''
      }
      setInputValues(initialValues)
    }
  }, [variables])

  // 清理 SSE 连接
  React.useEffect(() => {
    return () => {
      if (closeStreamRef.current) {
        closeStreamRef.current()
      }
    }
  }, [])

  // 重置状态
  const resetState = () => {
    setRunStatus(null)
    setOutputs(null)
    setTotalDurationMs(null)
    setTotalTokens(0)
    setErrorMessage(null)
    setNodeTraces(new Map())
    setExpandedNodes(new Set())
    setStreamingOutput('')
    runStartTimeRef.current = null
    nodeTypesRef.current.clear()
  }

  // 处理 SSE 事件
  const handleStreamEvent = React.useCallback((event: WorkflowEvent) => {
    const data = event.data as Record<string, unknown>
    const nodeId = data.node_id as string | undefined

    switch (event.type) {
      case 'workflow_start':
        setRunStatus('running')
        runStartTimeRef.current = event.timestamp
        break

      case 'workflow_complete':
        setRunStatus('success')
        setOutputs((data.outputs as Record<string, unknown>) || null)
        setTotalDurationMs(data.duration_ms as number || null)
        setIsRunning(false)
        // 完成时切换到结果标签页
        setActiveTab('result')
        break

      case 'workflow_error':
        setRunStatus('failed')
        setErrorMessage(data.error as string || t('runDrawer.unknownError'))
        setIsRunning(false)
        // 失败时切换到详情标签页查看错误信息
        setActiveTab('detail')
        break

      case 'node_start': {
        if (nodeId) {
          const nodeType = data.node_type as string || 'unknown'
          
          // 记录节点类型到 ref（用于 token 事件处理）
          nodeTypesRef.current.set(nodeId, nodeType)
          
          setNodeTraces((prev) => {
            const next = new Map(prev)
            next.set(nodeId, {
              nodeId,
              nodeType,
              nodeLabel: data.node_label as string || nodeId,
              status: 'running',
              startTime: event.timestamp,
              streamingContent: '',
            })
            return next
          })
        }
        break
      }

      case 'node_complete': {
        if (nodeId) {
          const nodeOutputs = data.outputs as Record<string, unknown>
          const isStreaming = data.is_streaming as boolean || false
          const nodeType = data.node_type as string || 'unknown'
          
          // 非流式 answer 节点完成 → 一次性追加到流（作为一个大的流片段）
          // 流式 answer 节点的内容已通过 token 事件追加，不需要再追加
          if (nodeType === 'answer' && nodeOutputs && !isStreaming) {
            const textOutputs = Object.values(nodeOutputs)
              .filter((v): v is string => typeof v === 'string')
              .join('')
            if (textOutputs) {
              setStreamingOutput((prev) => prev + textOutputs)
            }
          }
          
          // 更新 outputs 状态（用于详情标签页）
          if (nodeType === 'answer' && nodeOutputs) {
            setOutputs((prevOutputs) => ({
              ...prevOutputs,
              ...nodeOutputs,
            }))
          }
          
          // 更新节点追踪
          setNodeTraces((prev) => {
            const next = new Map(prev)
            const existing = next.get(nodeId)
            next.set(nodeId, {
              ...existing,
              nodeId,
              nodeType: existing?.nodeType || nodeType,
              nodeLabel: existing?.nodeLabel || nodeId,
              status: 'success',
              endTime: event.timestamp,
              durationMs: data.duration_ms as number,
              outputs: nodeOutputs,
              tokens: existing?.tokens,
            })
            return next
          })
          
          // 累加 tokens
          if (nodeOutputs?.usage) {
            const usage = nodeOutputs.usage as number
            setTotalTokens((prev) => prev + usage)
          }
        }
        break
      }

      case 'node_error': {
        if (nodeId) {
          setNodeTraces((prev) => {
            const next = new Map(prev)
            const existing = next.get(nodeId)
            next.set(nodeId, {
              ...existing,
              nodeId,
              nodeType: existing?.nodeType || 'unknown',
              nodeLabel: existing?.nodeLabel || nodeId,
              status: 'failed',
              endTime: event.timestamp,
              error: data.error as string,
            })
            return next
          })
        }
        break
      }

      case 'node_skip': {
        if (nodeId) {
          setNodeTraces((prev) => {
            const next = new Map(prev)
            next.set(nodeId, {
              nodeId,
              nodeType: data.node_type as string || 'unknown',
              nodeLabel: data.node_label as string || nodeId,
              status: 'skipped',
            })
            return next
          })
        }
        break
      }

      case 'token': {
        const token = data.token as string || ''
        if (nodeId && token) {
          // 使用 ref 获取节点类型（避免闭包问题）
          const nodeType = nodeTypesRef.current.get(nodeId)
          
          // 更新节点追踪中的流式内容（始终更新，用于追踪标签页显示）
          setNodeTraces((prev) => {
            const next = new Map(prev)
            const existing = next.get(nodeId)
            if (existing) {
              next.set(nodeId, {
                ...existing,
                streamingContent: (existing.streamingContent || '') + token,
              })
            }
            return next
          })
          
          // 只有当 token 来自 answer 节点时，才追加到结果区
          // LLM 的 token 只在追踪区显示，不会出现在结果区
          if (nodeType === 'answer') {
            setStreamingOutput((prev) => {
              // 当收到第一个 answer token 时，切换到结果页面
              if (prev === '') {
                setActiveTab('result')
              }
              return prev + token
            })
          }
        }
        break
      }

      case 'output':
        setOutputs((data.outputs as Record<string, unknown>) || null)
        break
    }
  }, [t])

  // 运行工作流
  const handleRun = async (isDebug: boolean = false) => {
    if (!workflow) return

    try {
      resetState()
      setIsRunning(true)
      setRunStatus('pending')

      // 构建输入参数
      const inputs: Record<string, unknown> = {}
      for (const variable of variables) {
        const value = inputValues[variable.name]
        if (value !== undefined && value !== '') {
          switch (variable.type) {
            case 'number':
              inputs[variable.name] = Number(value)
              break
            case 'boolean':
              inputs[variable.name] = value === 'true'
              break
            case 'array':
            case 'object':
              try {
                inputs[variable.name] = JSON.parse(value)
              } catch {
                inputs[variable.name] = value
              }
              break
            default:
              inputs[variable.name] = value
          }
        } else if (variable.required) {
          toast.error(t('runDrawer.fillRequiredParam', { name: variable.name }))
          setIsRunning(false)
          setRunStatus(null)
          return
        }
      }

      // 调用 API
      const response = isDebug
        ? await workflowsApi.debugWorkflow(workflow.id, { inputs })
        : await workflowsApi.runWorkflow(workflow.id, { inputs })

      setRunId(response.run_id)

      // 连接 SSE
      closeStreamRef.current = workflowsApi.streamWorkflowRun(response.run_id, {
        onEvent: handleStreamEvent,
        onError: (error) => {
          console.error('Stream error:', error)
          toast.error(t('runDrawer.streamConnectionFailed'))
          setRunStatus('failed')
          setErrorMessage(t('runDrawer.streamConnectionFailed'))
          setIsRunning(false)
        },
        onComplete: () => {
          setIsRunning(false)
        },
      })
    } catch (error) {
      console.error('Run error:', error)
      toast.error(isDebug ? t('runDrawer.debugFailed') : t('runDrawer.runFailed'))
      setIsRunning(false)
      setRunStatus('failed')
      setErrorMessage(error instanceof Error ? error.message : t('runDrawer.runFailed'))
    }
  }

  // 取消运行
  const handleCancel = async () => {
    if (!runId) return

    try {
      const result = await workflowsApi.cancelWorkflowRun(runId)
      if (result.cancelled) {
        toast.success(t('runDrawer.cancelledRun'))
        setRunStatus('cancelled')
      } else {
        toast.info(t('runDrawer.cannotCancelRun'))
      }
    } catch {
      toast.error(t('runDrawer.cancelFailed'))
    }

    if (closeStreamRef.current) {
      closeStreamRef.current()
      closeStreamRef.current = null
    }
    setIsRunning(false)
  }

  // 切换节点展开
  const toggleNodeExpand = (nodeId: string) => {
    setExpandedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(nodeId)) {
        next.delete(nodeId)
      } else {
        next.add(nodeId)
      }
      return next
    })
  }

  // 复制到剪贴板
  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(t('editor.copiedToClipboard'))
    } catch {
      toast.error(t('editor.copyFailed'))
    }
  }

  // 根据节点类型渲染输出
  const renderNodeOutput = (nodeType: string, outputs: Record<string, unknown>) => {
    // LLM 节点 - 显示文本内容
    if (nodeType === 'llm') {
      const text = outputs.text || outputs.content || outputs.response || ''
      if (typeof text === 'string' && text) {
        return (
          <div className="p-2 bg-background rounded text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">
            {text}
          </div>
        )
      }
    }

    // Answer 节点 - 显示所有文本输出
    if (nodeType === 'answer') {
      const textOutputs = Object.entries(outputs)
        .filter(([, v]) => typeof v === 'string')
        .map(([k, v]) => ({ key: k, value: v as string }))
      
      if (textOutputs.length > 0) {
        return (
          <div className="space-y-2">
            {textOutputs.map(({ key, value }) => (
              <div key={key} className="space-y-1">
                <span className="text-[10px] text-muted-foreground">{key}</span>
                <div className="p-2 bg-background rounded text-sm whitespace-pre-wrap max-h-32 overflow-y-auto">
                  {value}
                </div>
              </div>
            ))}
          </div>
        )
      }
    }

    // Code 节点 - 显示代码执行结果
    if (nodeType === 'code') {
      return (
        <div className="space-y-2">
          {Object.entries(outputs).map(([key, value]) => (
            <div key={key} className="space-y-1">
              <span className="text-[10px] text-muted-foreground font-mono">{key}</span>
              <pre className="p-2 bg-background rounded text-[10px] overflow-x-auto max-h-32 font-mono">
                {typeof value === 'string' ? value : JSON.stringify(value, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      )
    }

    // Condition / Question Classifier 节点 - 显示匹配的分支
    if (nodeType === 'condition' || nodeType === 'question_classifier') {
      const matchedBranch = outputs.matched_branch || outputs.matched_category || outputs.branch
      const matchedHandle = outputs.matched_handle || outputs.handle
      return (
        <div className="p-2 bg-background rounded space-y-1">
          {!!matchedBranch && (
            <div className="text-sm">
              <span className="text-muted-foreground">{t('runDrawer.matchedBranch')}</span>
              <span className="font-medium ml-1">{String(matchedBranch)}</span>
            </div>
          )}
          {!!matchedHandle && (
            <div className="text-[10px] text-muted-foreground font-mono">
              Handle: {String(matchedHandle)}
            </div>
          )}
        </div>
      )
    }

    // HTTP 请求节点 - 显示状态码和响应
    if (nodeType === 'http_request') {
      const statusCode = outputs.status_code || outputs.statusCode
      const body = outputs.body || outputs.response
      return (
        <div className="space-y-2">
          {!!statusCode && (
            <div className="text-sm">
              <span className="text-muted-foreground">{t('runDrawer.statusCode')}</span>
              <span className={cn(
                'font-medium ml-1',
                Number(statusCode) >= 200 && Number(statusCode) < 300 ? 'text-green-600' : 'text-red-600'
              )}>
                {String(statusCode)}
              </span>
            </div>
          )}
          {!!body && (
            <pre className="p-2 bg-background rounded text-[10px] overflow-x-auto max-h-32">
              {typeof body === 'string' ? body : JSON.stringify(body, null, 2)}
            </pre>
          )}
        </div>
      )
    }

    // Tool 节点 - 显示工具执行结果
    if (nodeType === 'tool') {
      const result = outputs.result || outputs.output
      return (
        <pre className="p-2 bg-background rounded text-[10px] overflow-x-auto max-h-32">
          {typeof result === 'string' ? result : JSON.stringify(outputs, null, 2)}
        </pre>
      )
    }

    // 默认 - JSON 格式显示
    return (
      <pre className="p-2 bg-background rounded text-[10px] overflow-x-auto max-h-32">
        {JSON.stringify(outputs, null, 2)}
      </pre>
    )
  }

  const isPublished = workflow?.status === 'published'
  const nodeTraceArray = Array.from(nodeTraces.values())

  return (
    <div className={cn(
      'absolute top-14 right-2 bottom-2 w-[380px] min-w-[380px] bg-card border border-border rounded-xl shadow-xl z-40 flex flex-col overflow-hidden',
      'transform transition-all duration-200 ease-out',
      open ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0 pointer-events-none'
    )}>
      {/* Header */}
      <div className="flex items-center justify-between p-4">
        <div className="flex items-center gap-2">
          <Play className="h-5 w-5 text-primary" />
          <span className="font-medium text-sm">
            {t('runDrawer.testRun')} {runStartTimeRef.current && (
              <span className="text-muted-foreground text-xs ml-1">
                ({new Date(runStartTimeRef.current).toLocaleTimeString()})
              </span>
            )}
          </span>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex-1 flex flex-col overflow-hidden px-4 pt-2">
        <TabsList className="w-full grid grid-cols-4">
          <TabsTrigger value="input" className="text-xs">{t('runDrawer.input')}</TabsTrigger>
          <TabsTrigger value="result" className="text-xs">{t('runDrawer.result')}</TabsTrigger>
          <TabsTrigger value="detail" className="text-xs">{t('runDrawer.detail')}</TabsTrigger>
          <TabsTrigger value="trace" className="text-xs">{t('runDrawer.trace')}</TabsTrigger>
        </TabsList>

        {/* 输入标签 */}
        <TabsContent value="input" className="flex-1 m-0 mt-3 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="space-y-4 p-4">
              {variables.length > 0 ? (
                variables.map((variable) => (
                  <div key={variable.name} className="space-y-2">
                    <Label className="flex items-center gap-1">
                      {variable.name}
                      {variable.required && (
                        <span className="text-red-500">*</span>
                      )}
                    </Label>
                    {variable.description && (
                      <p className="text-xs text-muted-foreground">
                        {variable.description}
                      </p>
                    )}
                    {variable.type === 'boolean' ? (
                      <select
                        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        value={inputValues[variable.name] || 'false'}
                        onChange={(e) =>
                          setInputValues((prev) => ({
                            ...prev,
                            [variable.name]: e.target.value,
                          }))
                        }
                        disabled={isRunning}
                      >
                        <option value="true">true</option>
                        <option value="false">false</option>
                      </select>
                    ) : variable.type === 'array' || variable.type === 'object' ? (
                      <Textarea
                        placeholder={t('runDrawer.inputJsonPlaceholder', { type: variable.type === 'array' ? t('varTypes.array') : t('varTypes.object') })}
                        value={inputValues[variable.name] || ''}
                        onChange={(e) =>
                          setInputValues((prev) => ({
                            ...prev,
                            [variable.name]: e.target.value,
                          }))
                        }
                        disabled={isRunning}
                        rows={3}
                      />
                    ) : variable.type === 'paragraph' ? (
                      <Textarea
                        placeholder={t('runDrawer.inputPlaceholder', { name: variable.name })}
                        value={inputValues[variable.name] || ''}
                        onChange={(e) =>
                          setInputValues((prev) => ({
                            ...prev,
                            [variable.name]: e.target.value,
                          }))
                        }
                        disabled={isRunning}
                        rows={3}
                      />
                    ) : (
                      <Input
                        type={variable.type === 'number' ? 'number' : 'text'}
                        placeholder={t('runDrawer.inputPlaceholder', { name: variable.name })}
                        value={inputValues[variable.name] || ''}
                        onChange={(e) =>
                          setInputValues((prev) => ({
                            ...prev,
                            [variable.name]: e.target.value,
                          }))
                        }
                        disabled={isRunning}
                      />
                    )}
                  </div>
                ))
              ) : (
                <div className="text-sm text-muted-foreground text-center py-8">
                  {t('runDrawer.noInputParams')}
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* 结果标签 */}
        <TabsContent value="result" className="flex-1 m-0 mt-3 overflow-hidden">
          <ScrollArea className="h-full p-4">
            {/* 统一的流式输出 */}
            {runStatus === 'running' && streamingOutput ? (
              <div className="space-y-2">
                <div className="p-3 bg-muted rounded-md text-sm whitespace-pre-wrap">
                  {streamingOutput}
                  <span className="animate-pulse text-primary">▌</span>
                </div>
              </div>
            ) : streamingOutput ? (
              <div className="space-y-2">
                <div className="flex items-center justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2"
                    onClick={() => copyToClipboard(streamingOutput)}
                  >
                    <Copy className="h-3 w-3 mr-1" />
                    {t('copy')}
                  </Button>
                </div>
                <div className="p-3 bg-muted rounded-md text-sm whitespace-pre-wrap">
                  {streamingOutput}
                </div>
              </div>
            ) : runStatus === 'success' && (outputs || nodeTraces.size > 0) ? (
              // 没有流式输出但有结果 - 显示 outputs 或最后一个节点的输出
              <div className="space-y-2">
                {(() => {
                  // 如果有 outputs（来自 Answer 节点），显示它
                  if (outputs && Object.keys(outputs).length > 0) {
                    const outputText = Object.values(outputs)
                      .filter((v): v is string => typeof v === 'string')
                      .join('\n')
                    if (outputText) {
                      return (
                        <>
                          <div className="flex items-center justify-end">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-6 px-2"
                              onClick={() => copyToClipboard(outputText)}
                            >
                              <Copy className="h-3 w-3 mr-1" />
                              {t('copy')}
                            </Button>
                          </div>
                          <div className="p-3 bg-muted rounded-md text-sm whitespace-pre-wrap">
                            {outputText}
                          </div>
                        </>
                      )
                    }
                  }

                  // 否则，找最后一个成功执行的节点（非开始节点）的输出
                  const successNodes = Array.from(nodeTraces.values())
                    .filter(n => n.status === 'success' && n.outputs && n.nodeType !== 'start' && n.nodeType !== 'user_input' && n.nodeType !== 'trigger')

                  if (successNodes.length > 0) {
                    const lastNode = successNodes[successNodes.length - 1]
                    const outputKeys = Object.keys(lastNode.outputs || {})
                    // 如果只有一个输出变量，直接显示其值；否则显示整个对象
                    const outputValue = outputKeys.length === 1
                      ? lastNode.outputs![outputKeys[0]]
                      : lastNode.outputs
                    const outputJson = JSON.stringify(outputValue, null, 2)
                    return (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="text-xs text-muted-foreground">
                            {t('runDrawer.fromNode', { name: lastNode.nodeLabel })}{outputKeys.length === 1 && ` (${outputKeys[0]})`}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2"
                            onClick={() => copyToClipboard(outputJson)}
                          >
                            <Copy className="h-3 w-3 mr-1" />
                            {t('copy')}
                          </Button>
                        </div>
                        <pre className="p-3 bg-muted rounded-md text-xs overflow-x-auto whitespace-pre-wrap">
                          {outputJson}
                        </pre>
                      </>
                    )
                  }
                  
                  return (
                    <div className="text-sm text-muted-foreground text-center py-8">
                      {t('runDrawer.noOutputResult')}
                    </div>
                  )
                })()}
              </div>
            ) : runStatus === 'failed' ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <XCircle className="h-12 w-12 text-red-500 mb-4" />
                <p className="text-sm text-red-500 font-medium">{t('runDrawer.executionFailed')}</p>
                {errorMessage && (
                  <p className="text-xs text-muted-foreground mt-2 max-w-full break-all">
                    {errorMessage}
                  </p>
                )}
              </div>
            ) : runStatus === 'running' ? (
              <div className="flex flex-col items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-sm text-muted-foreground">{t('runDrawer.executing')}</p>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                {t('runDrawer.resultPlaceholder')}
              </div>
            )}
          </ScrollArea>
        </TabsContent>

        {/* 详情标签 */}
        <TabsContent value="detail" className="flex-1 m-0 mt-3 overflow-hidden">
          <ScrollArea className="h-full p-4">
            <div className="space-y-4">
              {/* 状态卡片 */}
              {runStatus && (
                <div className="p-3 rounded-lg bg-muted/50">
                  <div className="grid grid-cols-3 gap-4 text-center">
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">{t('runDrawer.statusLabel')}</div>
                      <div className={cn(
                        'inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium',
                        runStatus === 'success' && 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300',
                        runStatus === 'failed' && 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300',
                        runStatus === 'running' && 'bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300',
                        runStatus === 'pending' && 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
                        runStatus === 'cancelled' && 'bg-orange-100 text-orange-700 dark:bg-orange-900 dark:text-orange-300',
                      )}>
                        {statusConfig[runStatus].icon}
                        {t('runDrawer.' + statusConfig[runStatus].label).toUpperCase()}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">{t('runDrawer.runTime')}</div>
                      <div className="text-sm font-medium">
                        {totalDurationMs !== null ? `${(totalDurationMs / 1000).toFixed(3)}s` : '-'}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground mb-1">{t('nodeConfig.totalTokens')}</div>
                      <div className="text-sm font-medium">
                        {totalTokens > 0 ? `${totalTokens} Tokens` : '0 Tokens'}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* 输入 JSON */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">{t('runDrawer.inputSection')}</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2"
                    onClick={() => copyToClipboard(JSON.stringify(
                      Object.fromEntries(
                        variables.map(v => [v.name, inputValues[v.name] || v.default || ''])
                      ),
                      null,
                      2
                    ))}
                  >
                    <Copy className="h-3 w-3" />
                  </Button>
                </div>
                <pre className="p-3 bg-muted rounded-md text-xs overflow-x-auto max-h-40">
                  {JSON.stringify(
                    Object.fromEntries(
                      variables.map(v => [v.name, inputValues[v.name] || v.default || ''])
                    ),
                    null,
                    2
                  )}
                </pre>
              </div>

              {/* 输出 JSON */}
              {outputs && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">{t('runDrawer.outputSection')}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2"
                      onClick={() => copyToClipboard(JSON.stringify(outputs, null, 2))}
                    >
                      <Copy className="h-3 w-3" />
                    </Button>
                  </div>
                  <pre className="p-3 bg-muted rounded-md text-xs overflow-x-auto max-h-60">
                    {JSON.stringify(outputs, null, 2)}
                  </pre>
                </div>
              )}

              {/* 错误信息 */}
              {errorMessage && (
                <div className="space-y-2">
                  <span className="text-sm font-medium text-red-500">{t('runDrawer.errorInfo')}</span>
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-md text-xs text-red-600 dark:text-red-400">
                    {errorMessage}
                  </div>
                </div>
              )}

              {/* 元数据 */}
              {runId && (
                <div className="space-y-2 pt-4 border-t">
                  <span className="text-sm font-medium">{t('runDrawer.metadata')}</span>
                  <div className="grid grid-cols-2 gap-y-2 text-xs">
                    <div className="text-muted-foreground">{t('runDrawer.runIdLabel')}</div>
                    <div className="font-mono truncate" title={runId}>{runId}</div>
                    {runStartTimeRef.current && (
                      <>
                        <div className="text-muted-foreground">{t('runDrawer.startTime')}</div>
                        <div>{new Date(runStartTimeRef.current).toLocaleString()}</div>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* 追踪标签 */}
        <TabsContent value="trace" className="flex-1 m-0 mt-3 overflow-hidden">
          <ScrollArea className="h-full p-4">
            {nodeTraceArray.length > 0 ? (
              <div className="space-y-2">
                {nodeTraceArray.map((trace) => {
                  const IconComponent = nodeTypeIcons[trace.nodeType] || FileText
                  const colorClass = nodeTypeColors[trace.nodeType] || 'bg-gray-500'
                  const StatusIcon = nodeStatusConfig[trace.status]?.icon || Clock
                  const isExpanded = expandedNodes.has(trace.nodeId)

                  return (
                    <div
                      key={trace.nodeId}
                      className="border rounded-lg overflow-hidden"
                    >
                      {/* 节点头部 */}
                      <div
                        className="flex items-center gap-2 p-3 cursor-pointer hover:bg-muted/50 transition-colors"
                        onClick={() => toggleNodeExpand(trace.nodeId)}
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        )}
                        <div className={cn(
                          'h-7 w-7 rounded-lg flex items-center justify-center text-white',
                          colorClass
                        )}>
                          <IconComponent className="h-4 w-4" />
                        </div>
                        <span className="flex-1 text-sm font-medium truncate">
                          {trace.nodeLabel}
                        </span>
                        <span className="text-xs text-muted-foreground mr-2">
                          {trace.durationMs !== undefined
                            ? `${trace.durationMs.toFixed(3)} ms`
                            : trace.status === 'running'
                            ? '...'
                            : ''}
                        </span>
                        <StatusIcon className={cn('h-4 w-4', nodeStatusConfig[trace.status]?.className)} />
                      </div>

                      {/* 展开详情 */}
                      {isExpanded && (
                        <div className="border-t bg-muted/30 p-3 space-y-3">
                          {/* 状态信息 */}
                          <div className="flex items-center gap-4 text-xs">
                            <div>
                              <span className="text-muted-foreground">{t('runDrawer.nodeType')}</span>
                              <span className="font-medium">{trace.nodeType}</span>
                            </div>
                            <div>
                              <span className="text-muted-foreground">{t('runDrawer.nodeStatus')}</span>
                              <span className={cn(
                                'font-medium',
                                trace.status === 'success' && 'text-green-600',
                                trace.status === 'failed' && 'text-red-600',
                                trace.status === 'running' && 'text-blue-600',
                                trace.status === 'skipped' && 'text-gray-400',
                              )}>
                                {trace.status}
                              </span>
                            </div>
                            {trace.durationMs !== undefined && (
                              <div>
                                <span className="text-muted-foreground">{t('runDrawer.nodeTime')}</span>
                                <span className="font-medium">{trace.durationMs.toFixed(3)}ms</span>
                              </div>
                            )}
                          </div>

                          {/* Token 信息（LLM 节点） */}
                          {trace.tokens && (trace.tokens.total ?? 0) > 0 && (
                            <div className="flex items-center gap-4 text-xs">
                              <div>
                                <span className="text-muted-foreground">Prompt：</span>
                                <span>{trace.tokens.prompt || 0}</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">Completion：</span>
                                <span>{trace.tokens.completion || 0}</span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">Total：</span>
                                <span className="font-medium">{trace.tokens.total || 0}</span>
                              </div>
                            </div>
                          )}

                          {/* 流式输出（LLM 节点运行中） */}
                          {trace.nodeType === 'llm' && trace.status === 'running' && trace.streamingContent && (
                            <div className="space-y-1">
                              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                                <Loader2 className="h-3 w-3 animate-spin" />
                                <span>{t('runDrawer.generating')}</span>
                              </div>
                              <div className="p-2 bg-background rounded text-sm whitespace-pre-wrap max-h-40 overflow-y-auto">
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
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    copyToClipboard(JSON.stringify(trace.outputs, null, 2))
                                  }}
                                >
                                  <Copy className="h-3 w-3" />
                                </Button>
                              </div>
                              {renderNodeOutput(trace.nodeType, trace.outputs)}
                            </div>
                          )}

                          {/* 错误信息 */}
                          {trace.error && (
                            <div className="space-y-1">
                              <span className="text-xs text-red-500 font-medium">{t('runDrawer.errorLabel')}</span>
                              <div className="p-2 bg-red-50 dark:bg-red-900/20 rounded text-xs text-red-600 dark:text-red-400">
                                {trace.error}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ) : runStatus === 'running' ? (
              <div className="flex flex-col items-center justify-center py-8">
                <Loader2 className="h-8 w-8 animate-spin text-primary mb-4" />
                <p className="text-sm text-muted-foreground">{t('runDrawer.waitingForNodes')}</p>
              </div>
            ) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                {t('runDrawer.traceResultPlaceholder')}
              </div>
            )}
          </ScrollArea>
        </TabsContent>
      </Tabs>

      {/* Footer Actions */}
      <div className="p-4 border-t rounded-b-xl space-y-2">
        {isRunning ? (
          <Button
            variant="destructive"
            className="w-full"
            onClick={handleCancel}
          >
            <StopCircle className="h-4 w-4 mr-2" />
            {t('runDrawer.cancelRun')}
          </Button>
        ) : (
          <>
            <Button
              className="w-full"
              onClick={() => handleRun(false)}
              disabled={!isPublished}
            >
              <Play className="h-4 w-4 mr-2" />
              {isPublished ? t('runDrawer.startRun') : t('runDrawer.publishFirst')}
            </Button>
            <Button
              variant="outline"
              className="w-full"
              onClick={() => handleRun(true)}
            >
              <Bug className="h-4 w-4 mr-2" />
              {t('runDrawer.debugDraft')}
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

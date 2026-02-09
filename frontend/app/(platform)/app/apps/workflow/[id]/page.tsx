'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  ReactFlow,
  Background,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  BackgroundVariant,
  SelectionMode,
  useReactFlow,
  useViewport,
  ReactFlowProvider,
  OnConnectStart,
  OnConnectEnd,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  ArrowLeft,
  Save,
  Play,
  Settings,
  Loader2,
  Minus,
  Plus,
  PlusCircle,
  MousePointer2,
  Hand,
  Sparkles,
  Maximize,
  StickyNote,
  ClipboardCheck,
  Globe,
  GlobeLock,
  LayoutGrid,
  ExternalLink,
  FileText,
  Activity,
  GitBranch,
} from 'lucide-react'
import Image from 'next/image'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { workflowsApi, Workflow, VariableDefinition } from '@/lib/api/workflows'
import { authApi, User } from '@/lib/api/auth'
import { useCanPerform } from '@/components/permission-guard'

// Custom Node Types
import { UserInputNode } from './_components/nodes/user-input-node'
import { TriggerNode } from './_components/nodes/trigger-node'
import { LLMNode } from './_components/nodes/llm-node'
import { ConditionNode } from './_components/nodes/condition-node'
import { SubWorkflowNode } from './_components/nodes/sub-workflow-node'
import { AgentNode } from './_components/nodes/agent-node'
import { ToolNode } from './_components/nodes/tool-node'
import { IterationNode, IterationStartNode, IterationExitNode } from './_components/nodes/iteration-node'
import { LoopNode, LoopStartNode, LoopExitNode } from './_components/nodes/loop-node'
// 转换节点
import { CodeNode } from './_components/nodes/code-node'
import { TemplateNode } from './_components/nodes/template-node'
import { FileToUrlNode } from './_components/nodes/file-to-url-node'
import { VariableAggregatorNode } from './_components/nodes/variable-aggregator-node'
import { VariableAssignmentNode } from './_components/nodes/variable-assignment-node'
import { ParameterExtractorNode } from './_components/nodes/parameter-extractor-node'
import { QuestionClassifierNode } from './_components/nodes/question-classifier-node'
import { AnswerNode } from './_components/nodes/answer-node'
import { CommentNode, type CommentColor } from './_components/nodes/comment-node'

// Workflow Run Drawer
import { WorkflowRunDrawer } from './_components/workflow-run-drawer'

// Components
import { StartNodeSelector, StartNodeType } from './_components/start-node-selector'
import { NodeConfigDrawer } from './_components/node-config-drawer'
import { WorkflowSettingsDrawer } from './_components/workflow-settings-drawer'
import { AddNodePopover } from './_components/add-node-popover'
import { ValidationChecklist } from './_components/validation-checklist'
import { validateWorkflow, ValidationIssue } from './_components/workflow-validator'

// Define custom node data type
type WorkflowNodeData = {
  type: string
  label: string
  description?: string
  config: Record<string, unknown>
  parentIterationId?: string
  parentLoopId?: string
  // 注释节点字段
  content?: string
  author?: string
  color?: CommentColor
}

type WorkflowNode = Node<WorkflowNodeData>
type WorkflowEdge = Edge

const nodeTypes = {
  user_input: UserInputNode,
  trigger: TriggerNode,
  llm: LLMNode,
  condition: ConditionNode,
  sub_workflow: SubWorkflowNode,
  agent: AgentNode,
  tool: ToolNode,
  iteration: IterationNode,
  iteration_start: IterationStartNode,
  iteration_exit: IterationExitNode,
  loop: LoopNode,
  loop_start: LoopStartNode,
  loop_exit: LoopExitNode,
  // 转换节点
  code: CodeNode,
  template: TemplateNode,
  file_to_url: FileToUrlNode,
  variable_aggregator: VariableAggregatorNode,
  variable_assignment: VariableAssignmentNode,
  parameter_extractor: ParameterExtractorNode,
  question_classifier: QuestionClassifierNode,
  answer: AnswerNode,
  comment: CommentNode,
  // 兼容旧版本节点类型
  start: UserInputNode,
}

// 可以作为父节点的类型
const parentableNodeTypes = ['iteration', 'loop']

// 计算迭代节点内部子图区域的边界（用于限制子节点拖拽范围）
// 子图区域样式: left-3 right-3 bottom-3 top-10 (12px, 12px, 12px, 40px)
const getSubGraphExtent = (parentWidth: number, parentHeight: number): [[number, number], [number, number]] => {
  const padding = { top: 14, left: 12, right: 12, bottom: 12 }
  return [
    [padding.left, padding.top],
    [parentWidth - padding.right, parentHeight - padding.bottom]
  ]
}

// Add node popover state type
type AddNodePopoverState = {
  show: boolean
  position: { x: number; y: number } // 屏幕坐标（用于弹窗定位）
  canvasPosition?: { x: number; y: number } // 画布坐标（用于节点定位）
  sourceNodeId: string
  sourceHandleId?: string
  isInsideIteration?: boolean
  isInsideLoop?: boolean
} | null

// 自定义缩放控件组件（包含 MiniMap）
function ZoomControl() {
  const { zoomIn, zoomOut } = useReactFlow()
  const { zoom } = useViewport()
  const t = useTranslations('workflow')
  const zoomPercent = Math.round(zoom * 100)

  return (
    <Panel position="bottom-right" className="mb-4! mr-3!">
      <div className="flex flex-col items-center gap-2">
        {/* MiniMap */}
        <div className="bg-card border border-border rounded-lg overflow-hidden shadow-sm">
          <MiniMap
            nodeStrokeWidth={2}
            zoomable
            pannable
            style={{ position: 'relative', width: 100, height: 50 }}
            className="bg-card!"
          />
        </div>
        {/* Zoom Controls */}
        <div className="flex items-center gap-1 bg-card border border-border rounded-lg px-1 py-0.5 shadow-sm">
          <button
            onClick={() => zoomOut()}
            className="p-1 hover:bg-accent rounded cursor-pointer transition-colors"
            title={t('editor.zoomOut')}
          >
            <Minus className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
          <span className="text-xs text-muted-foreground min-w-9 text-center tabular-nums">
            {zoomPercent}%
          </span>
          <button
            onClick={() => zoomIn()}
            className="p-1 hover:bg-accent rounded cursor-pointer transition-colors"
            title={t('editor.zoomIn')}
          >
            <Plus className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        </div>
      </div>
    </Panel>
  )
}

function WorkflowEditorContent() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const tCommon = useTranslations('common')
  const { canPerform } = useCanPerform()
  const canUpdateWorkflow = canPerform('workflow:update')

  const workflowId = params.id as string

  // State
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [currentUser, setCurrentUser] = React.useState<User | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isSaving, setIsSaving] = React.useState(false)
  const [isPublishing, setIsPublishing] = React.useState(false)
  const [hasChanges, setHasChanges] = React.useState(false)
  const [lastSavedAt, setLastSavedAt] = React.useState<Date | null>(null)
  
  // UI State
  const [showStartSelector, setShowStartSelector] = React.useState(false)
  const [selectedNode, setSelectedNode] = React.useState<WorkflowNode | null>(null)
  const [configDrawerOpen, setConfigDrawerOpen] = React.useState(false)
  const [settingsDrawerOpen, setSettingsDrawerOpen] = React.useState(false)
  const [testRunDrawerOpen, setTestRunDrawerOpen] = React.useState(false)
  const [addNodePopover, setAddNodePopover] = React.useState<AddNodePopoverState>(null)
  const [editorMode, setEditorMode] = React.useState<'pointer' | 'hand'>('hand')
  const [isFullscreen, setIsFullscreen] = React.useState(false)
  const [showExitConfirm, setShowExitConfirm] = React.useState(false)
  const [showValidationChecklist, setShowValidationChecklist] = React.useState(false)
  const [validationIssues, setValidationIssues] = React.useState<ValidationIssue[]>([])

  // ReactFlow instance
  const reactFlowInstance = useReactFlow()
  const connectStartRef = React.useRef<{ nodeId: string; handleId?: string; time: number } | null>(null)

  // Handle connect start - track for click detection
  const onConnectStart: OnConnectStart = React.useCallback(
    (_, params) => {
      if (params.nodeId && params.handleType === 'source') {
        connectStartRef.current = {
          nodeId: params.nodeId,
          handleId: params.handleId || undefined,
          time: Date.now(),
        }
      }
    },
    []
  )

  // ReactFlow state
  const [nodes, setNodes, onNodesChangeBase] = useNodesState<WorkflowNode>([])
  const [edges, setEdges, onEdgesChangeBase] = useEdgesState<WorkflowEdge>([])

  // 检查节点是否是开始节点
  const isStartNode = React.useCallback((nodeId: string) => {
    const node = nodes.find((n) => n.id === nodeId)
    const nodeType = node?.type || (node?.data as { type?: string })?.type
    return nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start'
  }, [nodes])

  // 自定义边变化处理 - 保护开始节点的连线不被删除
  const onEdgesChange = React.useCallback(
    (changes: Parameters<typeof onEdgesChangeBase>[0]) => {
      // 过滤掉与开始节点相连的边的删除操作
      const filteredChanges = changes.filter((change) => {
        if (change.type === 'remove') {
          const edge = edges.find((e) => e.id === change.id)
          if (edge && isStartNode(edge.source)) {
            // 不阻止边删除，因为这可能是用户删除目标节点导致的
            // 只有当用户直接尝试删除开始节点时才阻止
          }
        }
        return true
      })
      
      onEdgesChangeBase(filteredChanges)
    },
    [edges, isStartNode, onEdgesChangeBase]
  )

  // 自定义节点变化处理 - 当父节点大小变化时更新子节点的extent，并保护开始节点不被删除
  const onNodesChange = React.useCallback(
    (changes: Parameters<typeof onNodesChangeBase>[0]) => {
      // 检查是否有尝试删除开始节点的操作
      const hasStartNodeRemoval = changes.some((change) => {
        if (change.type === 'remove') {
          return isStartNode(change.id)
        }
        return false
      })
      
      // 如果尝试删除开始节点，显示提示
      if (hasStartNodeRemoval) {
        toast.error(t('editor.cannotDeleteStart'))
      }
      
      // 过滤掉开始节点的删除操作
      const filteredChanges = changes.filter((change) => {
        if (change.type === 'remove') {
          // 不允许删除开始类型的节点
          if (isStartNode(change.id)) {
            return false
          }
        }
        return true
      })
      
      // 检查是否有迭代节点的大小变化
      const dimensionChanges = filteredChanges.filter(
        (change) => change.type === 'dimensions' && change.resizing
      )
      
      if (dimensionChanges.length > 0) {
        // 找出受影响的父节点及其新尺寸
        const parentUpdates = new Map<string, { width: number; height: number }>()
        for (const change of dimensionChanges) {
          if (change.type === 'dimensions' && change.dimensions) {
            const node = nodes.find((n) => n.id === change.id)
            if (node && parentableNodeTypes.includes(node.type || '')) {
              parentUpdates.set(change.id, {
                width: change.dimensions.width,
                height: change.dimensions.height,
              })
            }
          }
        }
        
        // 更新子节点的extent
        if (parentUpdates.size > 0) {
          setNodes((nds) =>
            nds.map((n) => {
              if (n.parentId && parentUpdates.has(n.parentId)) {
                const { width, height } = parentUpdates.get(n.parentId)!
                return {
                  ...n,
                  extent: getSubGraphExtent(width, height),
                }
              }
              return n
            })
          )
        }
      }
      
      onNodesChangeBase(filteredChanges)
    },
    [nodes, setNodes, onNodesChangeBase, isStartNode]
  )

  // Load workflow and current user
  React.useEffect(() => {
    const loadData = async () => {
      try {
        setIsLoading(true)
        const [workflowData, userData] = await Promise.all([
          workflowsApi.getWorkflow(workflowId),
          authApi.getCurrentUser({ skipAuthRedirect: true }),
        ])
        setWorkflow(workflowData)
        setCurrentUser(userData)

        // Initialize ReactFlow nodes and edges from workflow definition
        if (workflowData.definition && workflowData.definition.nodes && workflowData.definition.nodes.length > 0) {
          setNodes(workflowData.definition.nodes as unknown as WorkflowNode[])
          setEdges(workflowData.definition.edges as unknown as WorkflowEdge[])
        } else {
          // New workflow - show start node selector
          setShowStartSelector(true)
        }
      } catch {
        // toast handled by API interceptor
        router.push('/app/apps')
      } finally {
        setIsLoading(false)
      }
    }

    if (workflowId) {
      loadData()
    }
  }, [workflowId, router, t, setNodes, setEdges])

  // Handle start node type selection
  const handleStartNodeSelect = React.useCallback((type: StartNodeType) => {
    const startNode: WorkflowNode = {
      id: `${type}-1`,
      type: type,
      position: { x: 250, y: 100 },
      data: {
        type: type,
        label: type === 'user_input' ? t('editor.startLabel') : t('editor.triggerLabel'),
        config: {},
      },
    }
    setNodes([startNode])
    setShowStartSelector(false)
    setHasChanges(true)
  }, [setNodes])

  // Handle connection (edge creation)
  const onConnect = React.useCallback(
    (connection: Connection) => {
      setEdges((eds) => addEdge(connection, eds))
      setHasChanges(true)
    },
    [setEdges]
  )

  // Handle node click - open config drawer
  const onNodeClick = React.useCallback((event: React.MouseEvent, node: WorkflowNode) => {
    setSelectedNode(node)
    setSettingsDrawerOpen(false)
    setConfigDrawerOpen(true)
  }, [])

  // Handle clicking on a source handle to show add node popover
  const onConnectEnd: OnConnectEnd = React.useCallback(
    (event, connectionState) => {
      // If connection was made to a valid target, don't show popover
      if (connectionState.isValid) {
        connectStartRef.current = null
        return
      }
      
      // Check if this was a quick click (not a drag)
      const startInfo = connectStartRef.current
      if (!startInfo) return
      
      // Get the position from mouse/touch event
      const clientX = 'touches' in event ? event.touches[0]?.clientX : event.clientX
      const clientY = 'touches' in event ? event.touches[0]?.clientY : event.clientY
      
      // Show popover for quick click or when dropping on empty space
      if (startInfo.nodeId && clientX && clientY) {
        // 检查源节点是否在容器内
        const sourceNode = nodes.find((n) => n.id === startInfo.nodeId)
        const parentId = sourceNode?.parentId
        let isInsideIteration = false
        let isInsideLoop = false
        
        if (parentId) {
          const parentNode = nodes.find((n) => n.id === parentId)
          if (parentNode?.type === 'iteration') {
            isInsideIteration = true
          } else if (parentNode?.type === 'loop') {
            isInsideLoop = true
          }
        }
        
        // 将屏幕坐标转换为画布坐标
        const canvasPosition = reactFlowInstance.screenToFlowPosition({
          x: clientX,
          y: clientY,
        })
        
        setAddNodePopover({
          show: true,
          position: { x: clientX, y: clientY },
          canvasPosition, // 保存画布坐标用于节点定位
          sourceNodeId: startInfo.nodeId,
          sourceHandleId: startInfo.handleId,
          isInsideIteration,
          isInsideLoop,
        })
      }
      
      connectStartRef.current = null
    },
    [nodes, reactFlowInstance]
  )

  // Handle adding node from popover
  const handleAddNodeFromPopover = React.useCallback(
    (type: string, sourceNodeId: string, sourceHandleId?: string) => {
      // Get source node to calculate new position (may be undefined if adding from toolbar)
      const sourceNode = sourceNodeId ? nodes.find((n) => n.id === sourceNodeId) : null

      const newNodeId = `${type}-${Date.now()}`
      const isIterationNode = type === 'iteration'
      const isLoopNode = type === 'loop'
      const isContainerNode = isIterationNode || isLoopNode

      // 检查源节点是否在容器内（有 parentId）
      // 优先使用 addNodePopover 中的信息，因为它在 onConnectEnd 时已经正确计算了
      const isInsideIteration = addNodePopover?.isInsideIteration || false
      const isInsideLoop = addNodePopover?.isInsideLoop || false
      const sourceParentId = sourceNode?.parentId
      const isInsideContainer = isInsideIteration || isInsideLoop || !!sourceParentId
      
      // 节点尺寸估算（用于计算重叠）
      const estimatedNodeWidth = isContainerNode ? 500 : 200
      const estimatedNodeHeight = isContainerNode ? 280 : 100
      
      // 计算新节点位置
      let newNodePosition: { x: number; y: number }
      
      if (sourceNodeId && addNodePopover?.canvasPosition) {
        // 有源节点（从连线拖出来的）：使用鼠标释放位置
        newNodePosition = {
          x: addNodePopover.canvasPosition.x - estimatedNodeWidth / 2,
          y: addNodePopover.canvasPosition.y - estimatedNodeHeight / 2,
        }
      } else {
        // 从工具栏添加：找一个不重叠的位置
        const viewport = reactFlowInstance.getViewport()
        
        // 获取视口边界（画布坐标）
        const viewportBounds = {
          left: -viewport.x / viewport.zoom,
          top: -viewport.y / viewport.zoom,
          right: (window.innerWidth - viewport.x) / viewport.zoom,
          bottom: (window.innerHeight - viewport.y) / viewport.zoom,
        }
        
        // 检查位置是否与现有节点重叠
        const isOverlapping = (x: number, y: number, width: number, height: number) => {
          return nodes.some((node) => {
            if (node.type === 'comment') return false // 忽略注释节点
            const nodeWidth = node.measured?.width || node.width || 200
            const nodeHeight = node.measured?.height || node.height || 100
            return !(
              x + width < node.position.x ||
              x > node.position.x + nodeWidth ||
              y + height < node.position.y ||
              y > node.position.y + nodeHeight
            )
          })
        }
        
        // 从视口中心开始，螺旋式寻找不重叠的位置
        const centerX = (viewportBounds.left + viewportBounds.right) / 2 - estimatedNodeWidth / 2
        const centerY = (viewportBounds.top + viewportBounds.bottom) / 2 - estimatedNodeHeight / 2
        
        newNodePosition = { x: centerX, y: centerY }
        
        // 如果中心位置重叠，尝试找其他位置
        if (isOverlapping(centerX, centerY, estimatedNodeWidth, estimatedNodeHeight)) {
          const step = 50
          const maxAttempts = 100
          let found = false
          
          // 螺旋式搜索
          for (let ring = 1; ring <= maxAttempts && !found; ring++) {
            const offsets = [
              { x: ring * step, y: 0 },
              { x: ring * step, y: ring * step },
              { x: 0, y: ring * step },
              { x: -ring * step, y: ring * step },
              { x: -ring * step, y: 0 },
              { x: -ring * step, y: -ring * step },
              { x: 0, y: -ring * step },
              { x: ring * step, y: -ring * step },
            ]
            
            for (const offset of offsets) {
              const testX = centerX + offset.x
              const testY = centerY + offset.y
              
              // 确保在视口内
              if (
                testX >= viewportBounds.left &&
                testX + estimatedNodeWidth <= viewportBounds.right &&
                testY >= viewportBounds.top &&
                testY + estimatedNodeHeight <= viewportBounds.bottom
              ) {
                if (!isOverlapping(testX, testY, estimatedNodeWidth, estimatedNodeHeight)) {
                  newNodePosition = { x: testX, y: testY }
                  found = true
                  break
                }
              }
            }
          }
        }
      }
      
      // 获取父容器信息
      let parentNode: WorkflowNode | undefined
      let actualParentId = sourceParentId

      // 如果 sourceParentId 为空但 isInsideContainer 为 true，需要从 sourceNode 的 data 中获取
      if (!actualParentId && isInsideContainer && sourceNode) {
        const sourceData = sourceNode.data as { parentIterationId?: string; parentLoopId?: string }
        actualParentId = sourceData.parentIterationId || sourceData.parentLoopId
      }

      if (isInsideContainer && actualParentId) {
        parentNode = nodes.find((n) => n.id === actualParentId)
      }

      // 确定是迭代还是循环容器
      const parentType = parentNode?.type || (parentNode?.data as { type?: string })?.type

      const newNode: WorkflowNode = {
        id: newNodeId,
        type: type,
        position: newNodePosition,
        // 如果在容器内，设置 parentId 和 extent
        ...(isInsideContainer && actualParentId && parentNode && {
          parentId: actualParentId,
          extent: getSubGraphExtent(
            parentNode.measured?.width || parentNode.width || 500,
            parentNode.measured?.height || parentNode.height || 280
          ),
        }),
        ...(isContainerNode && {
          style: { width: 500, height: 280 },
          width: 500,
          height: 280,
        }),
        data: {
          type: type,
          label: getUniqueNodeLabel(type, nodes, t),
          config: {},
          // 标记父容器ID（根据容器类型设置不同的属性）
          ...(isInsideContainer && actualParentId && {
            ...(parentType === 'iteration' || isInsideIteration ? { parentIterationId: actualParentId } : {}),
            ...(parentType === 'loop' || isInsideLoop ? { parentLoopId: actualParentId } : {}),
          }),
        },
      }

      // 如果是迭代节点，同时创建内嵌的迭代开始子节点
      if (isIterationNode) {
        const startNodeId = `iteration_start-${Date.now()}`
        const parentWidth = 500
        const parentHeight = 280
        const extent = getSubGraphExtent(parentWidth, parentHeight)
        
        const startNode: WorkflowNode = {
          id: startNodeId,
          type: 'iteration_start',
          position: { x: 20, y: 80 }, // 相对于父节点子图区域内部
          parentId: newNodeId,
          extent,
          draggable: false,
          data: {
            type: 'iteration_start',
            label: t('editor.iterationStartLabel'),
            parentIterationId: newNodeId,
            config: {},
          },
        }

        setNodes((nds) => [...nds, newNode, startNode])
      } else if (isLoopNode) {
        // 如果是循环节点，同时创建内嵌的循环开始子节点
        const startNodeId = `loop_start-${Date.now()}`
        const parentWidth = 500
        const parentHeight = 280
        const extent = getSubGraphExtent(parentWidth, parentHeight)
        
        const startNode: WorkflowNode = {
          id: startNodeId,
          type: 'loop_start',
          position: { x: 20, y: 80 }, // 相对于父节点子图区域内部
          parentId: newNodeId,
          extent,
          draggable: false,
          data: {
            type: 'loop_start',
            label: t('editor.loopStartLabel'),
            parentLoopId: newNodeId,
            config: {},
          },
        }

        setNodes((nds) => [...nds, newNode, startNode])
      } else {
        setNodes((nds) => [...nds, newNode])
      }

      // 只有在有源节点时才创建连线
      if (sourceNodeId) {
        const newEdge: WorkflowEdge = {
          id: `${sourceNodeId}-${newNodeId}`,
          source: sourceNodeId,
          sourceHandle: sourceHandleId,
          target: newNodeId,
        }
        setEdges((eds) => [...eds, newEdge])
      }
      
      setHasChanges(true)
      setAddNodePopover(null)
    },
    [nodes, setNodes, setEdges, addNodePopover, reactFlowInstance]
  )

  // Handle node update from config drawer
  const handleNodeUpdate = React.useCallback((nodeId: string, data: Record<string, unknown>) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === nodeId) {
          return { ...n, data: data as WorkflowNodeData }
        }
        // 如果是迭代/循环节点的子节点，同步更新 iterationConfig/loopConfig
        const nodeData = n.data as { parentIterationId?: string; parentLoopId?: string }
        if (nodeData.parentIterationId === nodeId && (data as { iterationConfig?: unknown }).iterationConfig) {
          return {
            ...n,
            data: {
              ...n.data,
              iterationConfig: (data as { iterationConfig: unknown }).iterationConfig,
            } as WorkflowNodeData,
          }
        }
        if (nodeData.parentLoopId === nodeId && (data as { loopConfig?: unknown }).loopConfig) {
          return {
            ...n,
            data: {
              ...n.data,
              loopConfig: (data as { loopConfig: unknown }).loopConfig,
            } as WorkflowNodeData,
          }
        }
        return n
      })
    )
    setHasChanges(true)
  }, [setNodes])

  // Check if a point is inside a node bounds
  const isInsideNode = React.useCallback((point: { x: number; y: number }, node: WorkflowNode) => {
    const nodeWidth = node.measured?.width || node.width || 280
    const nodeHeight = node.measured?.height || node.height || 200
    return (
      point.x >= node.position.x &&
      point.x <= node.position.x + nodeWidth &&
      point.y >= node.position.y &&
      point.y <= node.position.y + nodeHeight
    )
  }, [])

  // Handle node drag stop - check for parent assignment
  const onNodeDragStop = React.useCallback(
    (_: React.MouseEvent, draggedNode: WorkflowNode) => {
      // 已经有父节点的子节点不允许脱离（extent: 'parent' 会限制拖拽范围）
      if (draggedNode.parentId) {
        return
      }
      
      // Find potential parent nodes (iteration containers)
      const potentialParents = nodes.filter(
        (n) => 
          parentableNodeTypes.includes(n.type || '') && 
          n.id !== draggedNode.id
      )

      // Check if dragged node is inside any parent node
      for (const parent of potentialParents) {
        if (isInsideNode(draggedNode.position, parent)) {
          // 检查是否与内部开始节点有连接
          const isIteration = parent.type === 'iteration'
          const isLoop = parent.type === 'loop'
          const startNodeType = isIteration ? 'iteration_start' : isLoop ? 'loop_start' : null
          
          if (startNodeType) {
            // 找到父容器内的开始节点
            const startNode = nodes.find(
              n => n.type === startNodeType && n.parentId === parent.id
            )
            
            if (startNode) {
              // 检查是否有从开始节点到被拖拽节点的连接
              const hasConnectionFromStart = edges.some(
                edge => edge.source === startNode.id && edge.target === draggedNode.id
              )
              
              // 如果没有与开始节点的连接，不允许加入子图
              if (!hasConnectionFromStart) {
                return
              }
            }
          }
          
          // Calculate relative position within parent
          const relativePosition = {
            x: draggedNode.position.x - parent.position.x,
            y: draggedNode.position.y - parent.position.y,
          }

          // Update node with parent reference
          const parentWidth = parent.measured?.width || parent.width || 500
          const parentHeight = parent.measured?.height || parent.height || 280
          setNodes((nds) =>
            nds.map((n) =>
              n.id === draggedNode.id
                ? {
                    ...n,
                    parentId: parent.id,
                    position: relativePosition,
                    extent: getSubGraphExtent(parentWidth, parentHeight),
                  }
                : n
            )
          )
          setHasChanges(true)
          return
        }
      }
    },
    [nodes, edges, setNodes, isInsideNode]
  )

  // Mark changes when nodes or edges change
  React.useEffect(() => {
    if (!isLoading && workflow) {
      setHasChanges(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges])

  // Auto validate when nodes or edges change
  React.useEffect(() => {
    if (!isLoading && nodes.length > 0) {
      const issues = validateWorkflow(nodes, edges)
      setValidationIssues(issues)
    }
  }, [nodes, edges, isLoading])

  // 从开始节点提取输入变量定义
  const extractVariablesFromNodes = React.useCallback(() => {
    // 找到开始节点（user_input 或 trigger）
    const startNode = nodes.find(n => 
      n.type === 'user_input' || n.type === 'trigger' || n.type === 'start'
    )
    
    if (!startNode) return []
    
    // 获取参数列表
    const nodeData = startNode.data as { parameters?: Array<{
      name: string
      type: string
      required: boolean
      defaultValue?: string
      description?: string
    }> }
    
    const parameters = nodeData.parameters || []
    
    // 转换为 VariableDefinition 格式
    return parameters.map(p => ({
      name: p.name,
      type: p.type,
      required: p.required,
      default: p.defaultValue || undefined,
      description: p.description || null,
    }))
  }, [nodes])

  // Save workflow
  const handleSave = React.useCallback(async () => {
    if (!workflow) return

    try {
      setIsSaving(true)
      
      // 提取开始节点的输入变量
      const variables = extractVariablesFromNodes()
      
      await workflowsApi.updateWorkflow(workflowId, {
        definition: {
          nodes: nodes as never[],
          edges: edges as never[],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
        variables,
      })
      setHasChanges(false)
      setLastSavedAt(new Date())
      toast.success(t('saved'))
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsSaving(false)
    }
  }, [workflow, workflowId, nodes, edges, t, extractVariablesFromNodes])

  // Publish/Unpublish workflow
  const handlePublish = React.useCallback(async () => {
    if (!workflow) return

    try {
      setIsPublishing(true)
      
      // 提取开始节点的输入变量
      const variables = extractVariablesFromNodes()
      
      // 如果有未保存的更改，先保存
      if (hasChanges) {
        await workflowsApi.updateWorkflow(workflowId, {
          definition: {
            nodes: nodes as never[],
            edges: edges as never[],
            viewport: { x: 0, y: 0, zoom: 1 },
          },
          variables,
        })
        setHasChanges(false)
        setLastSavedAt(new Date())
      }
      
      // 发布或取消发布
      if (workflow.status === 'published') {
        const updated = await workflowsApi.unpublishWorkflow(workflowId)
        setWorkflow(updated)
        toast.success(t('unpublished'))
      } else {
        const updated = await workflowsApi.publishWorkflow(workflowId)
        setWorkflow(updated)
        toast.success(t('published'))
      }
    } catch {
      // toast handled by API interceptor
    } finally {
      setIsPublishing(false)
    }
  }, [workflow, workflowId, nodes, edges, hasChanges, t, extractVariablesFromNodes])

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        handleSave()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleSave])

  // 监听 ESC 退出页面全屏
  React.useEffect(() => {
    const handleEscKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsFullscreen(false)
      }
    }
    if (isFullscreen) {
      window.addEventListener('keydown', handleEscKey)
      return () => window.removeEventListener('keydown', handleEscKey)
    }
  }, [isFullscreen])

  if (isLoading) {
    return (
      <div className="flex h-full">
        <div className="flex-1 p-4">
          <div className="flex items-center gap-4 mb-4">
            <Skeleton className="h-10 w-10" />
            <Skeleton className="h-8 w-48" />
          </div>
          <Skeleton className="h-[calc(100%-80px)] w-full" />
        </div>
      </div>
    )
  }

  // Show start node selector for new workflows
  if (showStartSelector) {
    return (
      <div className="flex h-full bg-background items-center justify-center">
        <StartNodeSelector
          onSelect={handleStartNodeSelect}
          onCancel={() => router.push('/app/apps')}
        />
      </div>
    )
  }

  return (
    <div className={`flex h-full bg-background ${isFullscreen ? 'fixed inset-0 z-50' : ''}`}>
      {/* Main Canvas Area */}
      <div className="flex-1 flex flex-col relative">
        {/* Floating Toolbar - 全屏时隐藏 */}
        {!isFullscreen && (
          <div className="absolute top-3 left-3 right-3 z-10 flex items-center justify-between pointer-events-none">
            {/* Left - Back Button & Workflow Menu */}
            <div className="flex items-center gap-2 pointer-events-auto">
              <Button
                variant="outline"
                size="icon"
                className="bg-card shadow-sm"
                onClick={() => {
                  if (hasChanges) {
                    setShowExitConfirm(true)
                  } else {
                    router.push('/app/apps')
                  }
                }}
              >
                <ArrowLeft className="h-4 w-4" />
              </Button>

              {/* Workflow Dropdown Menu */}
              <DropdownMenu>
                <DropdownMenuTrigger className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 border border-input hover:bg-accent hover:text-accent-foreground h-9 bg-card shadow-sm gap-2 px-2">
                  {workflow?.icon ? (
                    workflow.icon.startsWith('http') || workflow.icon.startsWith('/') ? (
                      <Image
                        src={workflow.icon}
                        alt={workflow.name || ''}
                        width={20}
                        height={20}
                        className="rounded object-cover"
                        unoptimized
                      />
                    ) : (
                      <span className="text-base">{workflow.icon}</span>
                    )
                  ) : (
                    <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-primary/10">
                      <GitBranch className="h-3 w-3 text-primary" />
                    </div>
                  )}
                  <span className="text-sm font-medium max-w-32 truncate">{workflow?.name || t('untitled')}</span>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-48">
                  <DropdownMenuItem className="gap-2 bg-primary/10 text-primary">
                    <LayoutGrid className="h-4 w-4" />
                    <span>{t('orchestrate')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={() => router.push(`/app/apps/workflow/${workflowId}/api`)}
                  >
                    <ExternalLink className="h-4 w-4" />
                    <span>{t('accessApi')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={() => router.push(`/app/apps/workflow/${workflowId}/logs`)}
                  >
                    <FileText className="h-4 w-4" />
                    <span>{t('logs')}</span>
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    className="gap-2"
                    onClick={() => router.push(`/app/apps/workflow/${workflowId}/monitor`)}
                  >
                    <Activity className="h-4 w-4" />
                    <span>{t('monitor')}</span>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            {/* Right - Action Buttons */}
            <div className="flex items-center gap-2 pointer-events-auto h-8">
              {/* Test Run Button */}
              <Button
                variant="outline"
                size="sm"
                className="bg-card shadow-sm h-8"
                onClick={() => {
                  setConfigDrawerOpen(false)
                  setSettingsDrawerOpen(false)
                  setSelectedNode(null)
                  setTestRunDrawerOpen(true)
                }}
              >
                <Play className="h-4 w-4 mr-1" />
                {t('run')}
              </Button>
              {/* Validation Checklist Button */}
              {canUpdateWorkflow && (
                <Button
                  variant="outline"
                  size="icon"
                  className="bg-card shadow-sm relative h-8 w-8"
                  onClick={() => {
                    // 执行校验
                    const issues = validateWorkflow(nodes, edges)
                    setValidationIssues(issues)
                    setShowValidationChecklist(!showValidationChecklist)
                  }}
                >
                  <ClipboardCheck className="h-4 w-4" />
                  {validationIssues.length > 0 && (
                    <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] text-white font-medium">
                      {validationIssues.length > 9 ? '9+' : validationIssues.length}
                    </span>
                  )}
                </Button>
              )}
              {canUpdateWorkflow && (
                <Button
                  variant="outline"
                  size="sm"
                  className="bg-card shadow-sm h-8"
                  onClick={handleSave}
                  disabled={isSaving || !hasChanges}
                >
                  {isSaving ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : (
                    <Save className="h-4 w-4 mr-1" />
                  )}
                  {tCommon('save')}
                </Button>
              )}
              {canUpdateWorkflow && (
                <Button
                  variant={workflow?.status === 'published' ? 'default' : 'outline'}
                  size="sm"
                  className={workflow?.status === 'published' ? 'h-8' : 'bg-card shadow-sm h-8'}
                  onClick={handlePublish}
                  disabled={isPublishing}
                >
                  {isPublishing ? (
                    <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                  ) : workflow?.status === 'published' ? (
                    <Globe className="h-4 w-4 mr-1" />
                  ) : (
                    <GlobeLock className="h-4 w-4 mr-1" />
                  )}
                  {workflow?.status === 'published' ? t('published') : t('publish')}
                </Button>
              )}
              {canUpdateWorkflow && (
                <Button
                  variant="outline"
                  size="icon"
                  className="bg-card shadow-sm h-8 w-8"
                  onClick={() => {
                    setConfigDrawerOpen(false)
                    setSelectedNode(null)
                    setSettingsDrawerOpen(true)
                  }}
                >
                  <Settings className="h-4 w-4" />
                </Button>
              )}
          </div>
        </div>
        )}

        {/* Left Floating Toolbar */}
        <div className="absolute left-3 top-1/2 -translate-y-1/2 z-10 pointer-events-auto">
          <div className="flex flex-col items-center gap-0.5 bg-card border border-border rounded-lg p-1 shadow-sm">
            {canUpdateWorkflow && (
              <>
                <button
                  className="p-1.5 rounded-md hover:bg-accent transition-colors cursor-pointer"
                  title={t('editor.addNode')}
                  onClick={(e) => {
                    // 获取按钮位置，在按钮右侧显示弹窗
                    const rect = e.currentTarget.getBoundingClientRect()
                    setAddNodePopover({
                      show: true,
                      position: { x: rect.right + 8, y: rect.top },
                      sourceNodeId: '',
                    })
                  }}
                >
                  <PlusCircle className="h-4 w-4 text-muted-foreground" />
                </button>
                <button
                  className="p-1.5 rounded-md hover:bg-accent transition-colors cursor-pointer"
                  title={t('editor.addComment')}
                  onClick={() => {
                    // 在视口中心位置添加注释节点
                    const viewport = reactFlowInstance.getViewport()
                    const centerX = (window.innerWidth / 2 - viewport.x) / viewport.zoom
                    const centerY = (window.innerHeight / 2 - viewport.y) / viewport.zoom

                    const newNodeId = `comment-${Date.now()}`
                    const newNode: WorkflowNode = {
                      id: newNodeId,
                      type: 'comment',
                      position: { x: centerX - 120, y: centerY - 80 },
                      style: { width: 240, height: 160 },
                      zIndex: -1, // 置于最底层
                      data: {
                        type: 'comment',
                        label: t('editor.comment'),
                        content: '',
                        author: currentUser?.username || '',
                        config: {},
                      },
                    }
                    setNodes((nds) => [...nds, newNode])
                    setHasChanges(true)
                  }}
                >
                  <StickyNote className="h-4 w-4 text-muted-foreground" />
                </button>
                <div className="w-full h-px bg-border my-0.5" />
              </>
            )}
            <button
              className={`p-1.5 rounded-md transition-colors cursor-pointer ${
                editorMode === 'pointer' ? 'bg-accent' : 'hover:bg-accent'
              }`}
              title={t('editor.pointerMode')}
              onClick={() => setEditorMode('pointer')}
            >
              <MousePointer2 className={`h-4 w-4 ${
                editorMode === 'pointer' ? 'text-primary' : 'text-muted-foreground'
              }`} />
            </button>
            <button
              className={`p-1.5 rounded-md transition-colors cursor-pointer ${
                editorMode === 'hand' ? 'bg-accent' : 'hover:bg-accent'
              }`}
              title={t('editor.editMode')}
              onClick={() => setEditorMode('hand')}
            >
              <Hand className={`h-4 w-4 ${
                editorMode === 'hand' ? 'text-primary' : 'text-muted-foreground'
              }`} />
            </button>
            {canUpdateWorkflow && (
              <>
                <div className="w-full h-px bg-border my-0.5" />
                <button
                  className="p-1.5 rounded-md hover:bg-accent transition-colors cursor-pointer"
                  title={t('editor.autoLayout')}
                  onClick={() => {
                    // 自动整理节点布局
                    if (nodes.length === 0) return

                    // 简单的水平排列布局
                    const sortedNodes = [...nodes].sort((a, b) => {
                      // 根据节点位置排序，从左到右
                      return a.position.x - b.position.x
                    })

                    const startX = 100
                    const startY = 100
                    const gapX = 280
                    const gapY = 150

                    // 按照连接关系分层
                    const updatedNodes = sortedNodes.map((node, index) => {
                      // 跳过子节点（它们相对于父节点定位）
                      if (node.parentId) return node

                      return {
                        ...node,
                        position: {
                          x: startX + (index * gapX),
                          y: startY + (index % 2 === 0 ? 0 : gapY / 2),
                        },
                      }
                    })

                    setNodes(updatedNodes)
                    setHasChanges(true)

                    // 自动适应视图
                    setTimeout(() => {
                      reactFlowInstance.fitView({ padding: 0.2, duration: 300 })
                    }, 100)

                    toast.success(t('editor.nodesArranged'))
                  }}
                >
                  <Sparkles className="h-4 w-4 text-muted-foreground" />
                </button>
              </>
            )}
            <button
              className="p-1.5 rounded-md hover:bg-accent transition-colors cursor-pointer"
              title={isFullscreen ? t('editor.exitFullscreen') : t('editor.fullscreen')}
              onClick={() => setIsFullscreen(!isFullscreen)}
            >
              <Maximize className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>

        {/* ReactFlow Canvas */}
        <div className={`flex-1 relative ${editorMode === 'hand' ? '[&_.react-flow__pane]:cursor-default!' : ''}`}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onNodeClick={onNodeClick}
            onNodeDragStop={onNodeDragStop}
            nodeTypes={nodeTypes}
            fitView
            snapToGrid
            snapGrid={[15, 15]}
            defaultEdgeOptions={{
              type: 'default',
              animated: false,
              style: { stroke: '#93c5fd', strokeWidth: 2 },
            }}
            connectionLineStyle={{ stroke: '#3b82f6', strokeWidth: 2 }}
            proOptions={{ hideAttribution: true }}
            minZoom={0.15}
            maxZoom={2}
            elevateNodesOnSelect={false}
            panOnScroll={editorMode === 'hand'}
            panOnDrag={editorMode === 'hand'}
            selectionOnDrag={editorMode === 'pointer'}
            selectionMode={editorMode === 'pointer' ? SelectionMode.Partial : SelectionMode.Full}
            zoomOnScroll={false}
            zoomOnPinch
            zoomActivationKeyCode="Meta"
            panActivationKeyCode={null}
            deleteKeyCode={['Backspace', 'Delete']}
          >
            <Background variant={BackgroundVariant.Dots} gap={15} size={1} />
            <ZoomControl />
            {/* Bottom Center - Last Saved Time */}
            <Panel position="bottom-center" className="mb-4!">
              <span className="text-xs text-muted-foreground">
                {lastSavedAt
                  ? t('editor.lastSaved', { time: lastSavedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) })
                  : t('editor.notSavedYet')
                }
              </span>
            </Panel>
          </ReactFlow>

          {/* Node Config Panel - floating inside canvas */}
          <NodeConfigDrawer
            node={selectedNode}
            allNodes={nodes}
            allEdges={edges}
            open={configDrawerOpen}
            onClose={() => {
              setConfigDrawerOpen(false)
              setSelectedNode(null)
            }}
            onUpdate={handleNodeUpdate}
            readOnly={!canUpdateWorkflow}
          />

          {/* Workflow Settings Panel - floating inside canvas */}
          <WorkflowSettingsDrawer
            workflow={workflow}
            open={settingsDrawerOpen}
            onClose={() => setSettingsDrawerOpen(false)}
            onUpdate={(updated) => setWorkflow(updated)}
            readOnly={!canUpdateWorkflow}
          />

          {/* Test Run Panel - floating inside canvas */}
          <WorkflowRunDrawer
            workflow={workflow}
            variables={workflow?.variables as VariableDefinition[] || []}
            open={testRunDrawerOpen}
            onClose={() => setTestRunDrawerOpen(false)}
          />
        </div>
      </div>

      {/* Add Node Popover */}
      {addNodePopover?.show && canUpdateWorkflow && (
        <AddNodePopover
          position={addNodePopover.position}
          sourceNodeId={addNodePopover.sourceNodeId}
          sourceHandleId={addNodePopover.sourceHandleId}
          isInsideIteration={addNodePopover.isInsideIteration}
          isInsideLoop={addNodePopover.isInsideLoop}
          onSelect={handleAddNodeFromPopover}
          onClose={() => setAddNodePopover(null)}
        />
      )}

      {/* Validation Checklist Popover */}
      {showValidationChecklist && (
        <div className="absolute top-16 right-3 z-20">
          <ValidationChecklist
            issues={validationIssues}
            onClose={() => setShowValidationChecklist(false)}
            onSelectNode={(nodeId) => {
              // 选中并聚焦到指定节点
              const targetNode = nodes.find(n => n.id === nodeId)
              if (targetNode) {
                setSelectedNode(targetNode)
                setConfigDrawerOpen(true)
                setShowValidationChecklist(false)
                
                // 移动视图到节点位置
                reactFlowInstance.setCenter(
                  targetNode.position.x + 100,
                  targetNode.position.y + 50,
                  { zoom: 1, duration: 300 }
                )
              }
            }}
          />
        </div>
      )}

      {/* Exit Confirmation Dialog */}
      <AlertDialog open={showExitConfirm} onOpenChange={setShowExitConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('editor.confirmLeaveTitle')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('editor.confirmLeaveDescription')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon('cancel')}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => router.push('/app/apps')}
            >
              {t('editor.leaveWithoutSaving')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

// Wrapper component with ReactFlowProvider
export default function WorkflowEditorPage() {
  return (
    <ReactFlowProvider>
      <WorkflowEditorContent />
    </ReactFlowProvider>
  )
}

// Helper function to get node label by type
function getNodeLabel(type: string, t: (key: string) => string): string {
  const key = `nodeLabels.${type}`
  const translated = t(key)
  // If the translation returns the key itself, fall back to the type
  return translated !== key ? translated : type
}

// Helper function to get unique node label (auto-increment if duplicate)
function getUniqueNodeLabel(type: string, existingNodes: WorkflowNode[], t: (key: string) => string): string {
  const baseLabel = getNodeLabel(type, t)

  // 获取所有同类型节点的名称
  const existingLabels = existingNodes
    .filter(n => n.type === type || n.data?.type === type)
    .map(n => n.data?.label || '')

  // 如果没有重复，直接返回基本名称
  if (!existingLabels.includes(baseLabel)) {
    return baseLabel
  }

  // 找到可用的编号
  let counter = 1
  while (existingLabels.includes(`${baseLabel} ${counter}`)) {
    counter++
  }

  return `${baseLabel} ${counter}`
}

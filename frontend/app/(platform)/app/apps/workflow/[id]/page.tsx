'use client'

import * as React from 'react'
import { useParams, useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  addEdge,
  Connection,
  BackgroundVariant,
  useReactFlow,
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
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { workflowsApi, Workflow } from '@/lib/api/workflows'

// Custom Node Types
import { UserInputNode } from './_components/nodes/user-input-node'
import { TriggerNode } from './_components/nodes/trigger-node'
import { LLMNode } from './_components/nodes/llm-node'
import { ConditionNode } from './_components/nodes/condition-node'
import { SubWorkflowNode } from './_components/nodes/sub-workflow-node'
import { ToolNode } from './_components/nodes/tool-node'
import { IterationNode, IterationStartNode, IterationExitNode } from './_components/nodes/iteration-node'
import { LoopNode, LoopStartNode, LoopExitNode } from './_components/nodes/loop-node'

// Components
import { StartNodeSelector, StartNodeType } from './_components/start-node-selector'
import { NodeConfigDrawer } from './_components/node-config-drawer'
import { NodePanel } from './_components/node-panel'
import { AddNodePopover } from './_components/add-node-popover'

// Define custom node data type
type WorkflowNodeData = {
  type: string
  label: string
  description?: string
  config: Record<string, unknown>
  parentIterationId?: string
  parentLoopId?: string
}

type WorkflowNode = Node<WorkflowNodeData>
type WorkflowEdge = Edge

const nodeTypes = {
  user_input: UserInputNode,
  trigger: TriggerNode,
  llm: LLMNode,
  condition: ConditionNode,
  sub_workflow: SubWorkflowNode,
  tool: ToolNode,
  iteration: IterationNode,
  iteration_start: IterationStartNode,
  iteration_exit: IterationExitNode,
  loop: LoopNode,
  loop_start: LoopStartNode,
  loop_exit: LoopExitNode,
  // 兼容旧版本节点类型
  start: UserInputNode,
}

// 可以作为父节点的类型
const parentableNodeTypes = ['iteration', 'loop']

// 子节点的默认大小
const childNodeDimensions = { width: 200, height: 100 }

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
  position: { x: number; y: number }
  sourceNodeId: string
  sourceHandleId?: string
  isInsideIteration?: boolean
  isInsideLoop?: boolean
} | null

function WorkflowEditorContent() {
  const params = useParams()
  const router = useRouter()
  const t = useTranslations('workflow')
  const tCommon = useTranslations('common')

  const workflowId = params.id as string

  // State
  const [workflow, setWorkflow] = React.useState<Workflow | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [isSaving, setIsSaving] = React.useState(false)
  const [hasChanges, setHasChanges] = React.useState(false)
  
  // UI State
  const [showStartSelector, setShowStartSelector] = React.useState(false)
  const [selectedNode, setSelectedNode] = React.useState<WorkflowNode | null>(null)
  const [configDrawerOpen, setConfigDrawerOpen] = React.useState(false)
  const [addNodePopover, setAddNodePopover] = React.useState<AddNodePopoverState>(null)

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
  const [edges, setEdges, onEdgesChange] = useEdgesState<WorkflowEdge>([])

  // 自定义节点变化处理 - 当父节点大小变化时更新子节点的extent
  const onNodesChange = React.useCallback(
    (changes: Parameters<typeof onNodesChangeBase>[0]) => {
      // 检查是否有迭代节点的大小变化
      const dimensionChanges = changes.filter(
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
      
      onNodesChangeBase(changes)
    },
    [nodes, setNodes, onNodesChangeBase]
  )

  // Load workflow
  React.useEffect(() => {
    const loadWorkflow = async () => {
      try {
        setIsLoading(true)
        const data = await workflowsApi.getWorkflow(workflowId)
        setWorkflow(data)

        // Initialize ReactFlow nodes and edges from workflow definition
        if (data.definition && data.definition.nodes && data.definition.nodes.length > 0) {
          setNodes(data.definition.nodes as unknown as WorkflowNode[])
          setEdges(data.definition.edges as unknown as WorkflowEdge[])
        } else {
          // New workflow - show start node selector
          setShowStartSelector(true)
        }
      } catch {
        toast.error(t('loadFailed'))
        router.push('/app/apps')
      } finally {
        setIsLoading(false)
      }
    }

    if (workflowId) {
      loadWorkflow()
    }
  }, [workflowId, router, t, setNodes, setEdges])

  // Handle start node type selection
  const handleStartNodeSelect = React.useCallback((type: StartNodeType) => {
    const startNode: WorkflowNode = {
      id: 'start-1',
      type: type,
      position: { x: 250, y: 100 },
      data: {
        type: type,
        label: type === 'user_input' ? '用户输入' : '触发器',
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
  const onNodeClick = React.useCallback((_: React.MouseEvent, node: WorkflowNode) => {
    setSelectedNode(node)
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
        
        setAddNodePopover({
          show: true,
          position: { x: clientX, y: clientY },
          sourceNodeId: startInfo.nodeId,
          sourceHandleId: startInfo.handleId,
          isInsideIteration,
          isInsideLoop,
        })
      }
      
      connectStartRef.current = null
    },
    [nodes]
  )

  // Handle adding node from popover
  const handleAddNodeFromPopover = React.useCallback(
    (type: string, sourceNodeId: string, sourceHandleId?: string) => {
      // Get source node to calculate new position
      const sourceNode = nodes.find((n) => n.id === sourceNodeId)
      if (!sourceNode) return

      const newNodeId = `${type}-${Date.now()}`
      const isIterationNode = type === 'iteration'
      const isLoopNode = type === 'loop'
      const isContainerNode = isIterationNode || isLoopNode
      
      // 检查源节点是否在容器内（有 parentId）
      const sourceParentId = sourceNode.parentId
      const isInsideContainer = !!sourceParentId
      
      // 如果源节点在容器内，新节点也应该在同一个容器内
      let newNodePosition = {
        x: sourceNode.position.x + 200,
        y: sourceNode.position.y,
      }
      
      // 获取父容器信息
      let parentNode: WorkflowNode | undefined
      if (isInsideContainer && sourceParentId) {
        parentNode = nodes.find((n) => n.id === sourceParentId)
      }

      const newNode: WorkflowNode = {
        id: newNodeId,
        type: type,
        position: newNodePosition,
        // 如果在容器内，设置 parentId 和 extent
        ...(isInsideContainer && sourceParentId && parentNode && {
          parentId: sourceParentId,
          extent: getSubGraphExtent(
            parentNode.measured?.width || parentNode.width || 500,
            parentNode.measured?.height || parentNode.height || 280
          ),
        }),
        // 容器节点设置默认尺寸
        ...(isContainerNode && {
          style: { width: 500, height: 280 },
          width: 500,
          height: 280,
        }),
        data: {
          type: type,
          label: getNodeLabel(type),
          config: {},
          // 标记父容器ID
          ...(isInsideContainer && sourceParentId && {
            parentIterationId: sourceParentId,
          }),
        },
      }

      // Add edge
      const newEdge: WorkflowEdge = {
        id: `${sourceNodeId}-${newNodeId}`,
        source: sourceNodeId,
        sourceHandle: sourceHandleId,
        target: newNodeId,
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
            label: '迭代开始',
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
            label: '循环开始',
            parentLoopId: newNodeId,
            config: {},
          },
        }
        
        setNodes((nds) => [...nds, newNode, startNode])
      } else {
        setNodes((nds) => [...nds, newNode])
      }

      setEdges((eds) => [...eds, newEdge])
      setHasChanges(true)
      setAddNodePopover(null)
    },
    [nodes, setNodes, setEdges]
  )

  // Handle node update from config drawer
  const handleNodeUpdate = React.useCallback((nodeId: string, data: Record<string, unknown>) => {
    setNodes((nds) =>
      nds.map((n) => (n.id === nodeId ? { ...n, data: data as WorkflowNodeData } : n))
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
    [nodes, setNodes, isInsideNode]
  )

  // Add new node
  const handleAddNode = React.useCallback((type: string) => {
    const newNodeId = `${type}-${Date.now()}`
    const isIterationNode = type === 'iteration'
    
    const newNode: WorkflowNode = {
      id: newNodeId,
      type: type,
      position: { x: 300, y: 200 + nodes.length * 150 },
      // 迭代节点设置默认尺寸
      ...(isIterationNode && {
        style: { width: 500, height: 280 },
        width: 500,
        height: 280,
      }),
      data: {
        type: type,
        label: getNodeLabel(type),
        config: {},
      },
    }
    
    // 如果是迭代节点，同时创建内嵌的迭代开始子节点
    if (isIterationNode) {
      const startNodeId = `iteration_start-${Date.now()}`
      const startNode: WorkflowNode = {
        id: startNodeId,
        type: 'iteration_start',
        position: { x: 30, y: 60 }, // 相对于父节点容器内部
        parentId: newNodeId,
        extent: 'parent',
        draggable: false, // 迭代开始节点不可拖动
        data: {
          type: 'iteration_start',
          label: '迭代开始',
          parentIterationId: newNodeId,
          config: {},
        },
      }
      setNodes((nds) => [...nds, newNode, startNode])
    } else {
      setNodes((nds) => [...nds, newNode])
    }
    
    setHasChanges(true)
  }, [nodes.length, setNodes])

  // Mark changes when nodes or edges change
  React.useEffect(() => {
    if (!isLoading && workflow) {
      setHasChanges(true)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges])

  // Save workflow
  const handleSave = React.useCallback(async () => {
    if (!workflow) return

    try {
      setIsSaving(true)
      await workflowsApi.updateWorkflow(workflowId, {
        definition: {
          nodes: nodes as never[],
          edges: edges as never[],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
      })
      setHasChanges(false)
      toast.success(t('saved'))
    } catch {
      toast.error(t('saveFailed'))
    } finally {
      setIsSaving(false)
    }
  }, [workflow, workflowId, nodes, edges, t])

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
    <div className="flex h-full bg-background">
      {/* Main Canvas Area */}
      <div className="flex-1 flex flex-col relative">
        {/* Toolbar */}
        <div className="h-14 border-b bg-card flex items-center justify-between px-4">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => router.push('/app/apps')}
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div>
              <h1 className="font-semibold">{workflow?.name}</h1>
              <p className="text-xs text-muted-foreground">
                {workflow?.description || t('noDescription')}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" disabled>
              <Play className="h-4 w-4 mr-1" />
              {t('run')}
            </Button>
            <Button
              variant="outline"
              size="sm"
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
            <Button variant="outline" size="icon">
              <Settings className="h-4 w-4" />
            </Button>
          </div>
        </div>

        {/* ReactFlow Canvas */}
        <div className="flex-1 relative">
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
              type: 'smoothstep',
              animated: true,
              style: { stroke: '#3b82f6', strokeWidth: 2 },
            }}
            connectionLineStyle={{ stroke: '#3b82f6', strokeWidth: 2 }}
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={15} size={1} />
            <Controls />
            <MiniMap
              nodeStrokeWidth={3}
              zoomable
              pannable
              className="bg-card!"
            />
            <Panel position="bottom-center" className="mb-4!">
              <div className="text-xs text-muted-foreground bg-card/80 px-2 py-1 rounded">
                {t('canvasHint')}
              </div>
            </Panel>
          </ReactFlow>

          {/* Node Config Panel - floating inside canvas */}
          <NodeConfigDrawer
            node={selectedNode}
            allNodes={nodes}
            open={configDrawerOpen}
            onClose={() => {
              setConfigDrawerOpen(false)
              setSelectedNode(null)
            }}
            onUpdate={handleNodeUpdate}
          />
        </div>
      </div>

      {/* Add Node Popover */}
      {addNodePopover?.show && (
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
function getNodeLabel(type: string): string {
  const labels: Record<string, string> = {
    llm: 'LLM',
    condition: '条件分支',
    sub_workflow: '子工作流',
    tool: '工具',
    code: '代码',
  }
  return labels[type] || type
}

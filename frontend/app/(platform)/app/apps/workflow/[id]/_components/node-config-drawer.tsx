'use client'

import * as React from 'react'
import { Node } from '@xyflow/react'
import { X, Home, Zap, Bot, GitBranch, Workflow, Wrench, Code, Plus, Trash2, Pencil, Type, AlignLeft, ListChecks, Hash, CheckSquare, RefreshCw, Infinity, ChevronDown, ChevronUp, GripVertical, Search, Brackets, Braces } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'
import { 
  ConditionBranch, 
  ConditionRule, 
  ConditionOperator, 
  conditionOperatorLabels,
  conditionOperatorShortLabels,
  noValueOperators 
} from './nodes/condition-node'
import { IterationConfig, IteratorType, defaultIterationConfig } from './nodes/iteration-node'
import { LoopConfig, LoopVariable, LoopVariableType, defaultLoopConfig } from './nodes/loop-node'

// 循环变量类型配置
const loopVariableTypeConfig: Record<LoopVariableType, { label: string; icon: React.ElementType; placeholder: string; valueType: string }> = {
  string: { label: '文本', icon: Type, placeholder: '如：hello', valueType: 'String' },
  number: { label: '数字', icon: Hash, placeholder: '如：0', valueType: 'Number' },
  boolean: { label: '布尔', icon: CheckSquare, placeholder: '如：false', valueType: 'Boolean' },
  array: { label: '数组', icon: Brackets, placeholder: '如：[]', valueType: 'Array' },
  object: { label: '对象', icon: Braces, placeholder: '如：{}', valueType: 'Object' },
}

// 参数类型定义
type ParameterType = 'text' | 'paragraph' | 'select' | 'number' | 'checkbox' | 'array' | 'object'

interface Parameter {
  id: string
  name: string
  type: ParameterType
  required: boolean
  defaultValue?: string
  description?: string
  isSystem?: boolean  // 系统参数标识，不可删除
  options?: string[]  // 下拉选项的选项列表
}

// 参数类型配置
const parameterTypeConfig: Record<ParameterType, { label: string; icon: React.ElementType; valueType: string }> = {
  text: { label: '文本', icon: Type, valueType: 'string' },
  paragraph: { label: '段落', icon: AlignLeft, valueType: 'string' },
  select: { label: '下拉选项', icon: ListChecks, valueType: 'string' },
  number: { label: '数字', icon: Hash, valueType: 'number' },
  checkbox: { label: '复选框', icon: CheckSquare, valueType: 'boolean' },
  array: { label: '数组', icon: Brackets, valueType: 'array' },
  object: { label: '对象', icon: Braces, valueType: 'object' },
}

interface NodeConfigDrawerProps {
  node: Node | null
  allNodes: Node[]  // 所有节点，用于获取可用变量
  open: boolean
  onClose: () => void
  onUpdate: (nodeId: string, data: Record<string, unknown>) => void
}

const nodeTypeInfo: Record<string, { icon: React.ElementType; color: string; title: string }> = {
  user_input: { icon: Home, color: 'bg-primary', title: '用户输入' },
  trigger: { icon: Zap, color: 'bg-amber-500', title: '触发器' },
  llm: { icon: Bot, color: 'bg-blue-500', title: 'LLM' },
  condition: { icon: GitBranch, color: 'bg-cyan-500', title: '条件分支' },
  iteration: { icon: RefreshCw, color: 'bg-cyan-500', title: '迭代' },
  loop: { icon: Infinity, color: 'bg-cyan-500', title: '循环' },
  sub_workflow: { icon: Workflow, color: 'bg-purple-500', title: '子工作流' },
  tool: { icon: Wrench, color: 'bg-emerald-500', title: '工具' },
  code: { icon: Code, color: 'bg-gray-500', title: '代码' },
}

// 系统默认参数（不可删除）- 使用固定的值类型显示
interface SystemParameter {
  id: string
  name: string
  valueType: 'String' | 'Number'
  description: string
}

const systemParameters: SystemParameter[] = [
  { id: 'sys.user_id', name: 'sys.user_id', valueType: 'String', description: '当前用户ID' },
  { id: 'sys.app_id', name: 'sys.app_id', valueType: 'String', description: '应用ID' },
  { id: 'sys.workflow_id', name: 'sys.workflow_id', valueType: 'String', description: '工作流ID' },
  { id: 'sys.workflow_run_id', name: 'sys.workflow_run_id', valueType: 'String', description: '工作流运行ID' },
  { id: 'sys.timestamp', name: 'sys.timestamp', valueType: 'Number', description: '当前时间戳' },
]

// 开始节点的默认用户参数
const defaultStartParameters: Parameter[] = [
  { id: 'query', name: 'query', type: 'text', required: true, defaultValue: '', description: '用户输入的查询内容' },
]

export function NodeConfigDrawer({ node, allNodes, open, onClose, onUpdate }: NodeConfigDrawerProps) {
  const [label, setLabel] = React.useState('')
  const [description, setDescription] = React.useState('')
  const [parameters, setParameters] = React.useState<Parameter[]>([])
  
  // 参数编辑模态框状态
  const [editingParam, setEditingParam] = React.useState<Parameter | null>(null)
  const [isParamDialogOpen, setIsParamDialogOpen] = React.useState(false)
  const [paramForm, setParamForm] = React.useState<Partial<Parameter>>({})

  // 条件分支状态
  const [branches, setBranches] = React.useState<ConditionBranch[]>([])
  const [expandedBranches, setExpandedBranches] = React.useState<Set<string>>(new Set(['if']))
  
  // 迭代配置状态
  const [iterationConfig, setIterationConfig] = React.useState<IterationConfig>(defaultIterationConfig)
  
  // 循环配置状态
  const [loopConfig, setLoopConfig] = React.useState<LoopConfig>(defaultLoopConfig)
  
  // 循环变量编辑模态框状态
  const [editingLoopVar, setEditingLoopVar] = React.useState<LoopVariable | null>(null)
  const [isLoopVarDialogOpen, setIsLoopVarDialogOpen] = React.useState(false)
  const [loopVarForm, setLoopVarForm] = React.useState<Partial<LoopVariable>>({})
  
  // 变量选择器状态
  const [variableSearch, setVariableSearch] = React.useState('')
  const [openVariablePopover, setOpenVariablePopover] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (node) {
      setLabel((node.data as { label?: string })?.label || '')
      setDescription((node.data as { description?: string })?.description || '')
      
      // 加载参数，如果是开始节点且没有参数则使用默认参数
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

      // 加载条件分支
      if (nodeType === 'condition') {
        const existingBranches = (node.data as { branches?: ConditionBranch[] })?.branches
        if (existingBranches && existingBranches.length > 0) {
          setBranches(existingBranches)
        } else {
          // 默认分支
          setBranches([
            { id: 'if', type: 'if', name: 'IF', conditions: [], logicOperator: 'and' },
            { id: 'else', type: 'else', name: 'ELSE', conditions: [], logicOperator: 'and' },
          ])
        }
      }
      
      // 加载迭代配置
      if (nodeType === 'iteration') {
        const existingConfig = (node.data as { iterationConfig?: IterationConfig })?.iterationConfig
        if (existingConfig) {
          setIterationConfig(existingConfig)
        } else {
          setIterationConfig(defaultIterationConfig)
        }
      }
      
      // 加载循环配置
      if (nodeType === 'loop') {
        const existingConfig = (node.data as { loopConfig?: LoopConfig })?.loopConfig
        if (existingConfig) {
          setLoopConfig(existingConfig)
        } else {
          setLoopConfig(defaultLoopConfig)
        }
      }
    }
  }, [node])

  // Auto-save on change
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
        
        // 条件节点保存分支数据
        if (nodeType === 'condition') {
          updateData.branches = branches
        }
        
        // 迭代节点保存迭代配置
        if (nodeType === 'iteration') {
          updateData.iterationConfig = iterationConfig
        }
        
        // 循环节点保存循环配置
        if (nodeType === 'loop') {
          updateData.loopConfig = loopConfig
        }
        
        onUpdate(node.id, updateData)
      }, 300)
      return () => clearTimeout(timer)
    }
  }, [label, description, parameters, branches, iterationConfig, loopConfig, node, onUpdate])

  // 打开添加参数模态框
  const openAddParamDialog = () => {
    setEditingParam(null)
    setParamForm({
      name: '',
      type: 'text',
      required: false,
      defaultValue: '',
      description: '',
    })
    setIsParamDialogOpen(true)
  }

  // 打开编辑参数模态框
  const openEditParamDialog = (param: Parameter) => {
    setEditingParam(param)
    setParamForm({ ...param })
    setIsParamDialogOpen(true)
  }

  // 验证变量名格式（只允许字母、数字、下划线，且不能以数字开头）
  const isValidVariableName = (name: string): boolean => {
    return /^[a-zA-Z_][a-zA-Z0-9_]*$/.test(name)
  }

  // 检查变量名是否重复
  const isVariableNameDuplicate = (name: string): boolean => {
    // 编辑时排除自身
    const existingNames = parameters
      .filter(p => editingParam ? p.id !== editingParam.id : true)
      .map(p => p.name.toLowerCase())
    return existingNames.includes(name.toLowerCase())
  }

  // 获取变量名验证错误信息
  const getVariableNameError = (): string | null => {
    const name = paramForm.name?.trim() || ''
    if (!name) return null // 空值由保存按钮 disabled 控制
    if (!isValidVariableName(name)) {
      return '变量名只能包含字母、数字、下划线，且不能以数字开头'
    }
    if (isVariableNameDuplicate(name)) {
      return '变量名已存在'
    }
    return null
  }

  const variableNameError = getVariableNameError()

  // 保存参数
  const saveParameter = () => {
    const name = paramForm.name?.trim()
    if (!name) return
    if (variableNameError) return
    
    if (editingParam) {
      // 更新现有参数
      setParameters(parameters.map(p => 
        p.id === editingParam.id ? { ...p, ...paramForm, name } as Parameter : p
      ))
    } else {
      // 添加新参数
      const newParam: Parameter = {
        id: `param_${Date.now()}`,
        name,
        type: (paramForm.type as Parameter['type']) || 'text',
        required: paramForm.required || false,
        defaultValue: paramForm.defaultValue || '',
        description: paramForm.description || '',
      }
      setParameters([...parameters, newParam])
    }
    setIsParamDialogOpen(false)
  }

  // 删除参数
  const removeParameter = (id: string) => {
    setParameters(parameters.filter(p => p.id !== id))
  }

  // ============ 条件分支相关函数 ============
  
  // 切换分支展开/收起
  const toggleBranchExpand = (branchId: string) => {
    setExpandedBranches(prev => {
      const next = new Set(prev)
      if (next.has(branchId)) {
        next.delete(branchId)
      } else {
        next.add(branchId)
      }
      return next
    })
  }

  // 添加 ELSE IF 分支
  const addElseIfBranch = () => {
    const elseIndex = branches.findIndex(b => b.type === 'else')
    const newBranch: ConditionBranch = {
      id: `else_if_${Date.now()}`,
      type: 'else_if',
      name: `ELIF ${branches.filter(b => b.type === 'else_if').length + 1}`,
      conditions: [],
      logicOperator: 'and',
    }
    
    const newBranches = [...branches]
    if (elseIndex !== -1) {
      newBranches.splice(elseIndex, 0, newBranch)
    } else {
      newBranches.push(newBranch)
    }
    setBranches(newBranches)
    setExpandedBranches(prev => new Set(prev).add(newBranch.id))
  }

  // 删除分支
  const removeBranch = (branchId: string) => {
    setBranches(branches.filter(b => b.id !== branchId))
  }

  // 更新分支名称
  const updateBranchName = (branchId: string, name: string) => {
    setBranches(branches.map(b => b.id === branchId ? { ...b, name } : b))
  }

  // 更新分支逻辑操作符
  const updateBranchLogicOperator = (branchId: string, logicOperator: 'and' | 'or') => {
    setBranches(branches.map(b => b.id === branchId ? { ...b, logicOperator } : b))
  }

  // 添加条件规则
  const addConditionRule = (branchId: string) => {
    const newRule: ConditionRule = {
      id: `rule_${Date.now()}`,
      variable: '',
      variableSource: '用户输入',
      operator: 'equals',
      value: '',
    }
    setBranches(branches.map(b => 
      b.id === branchId 
        ? { ...b, conditions: [...b.conditions, newRule] }
        : b
    ))
  }

  // 更新条件规则
  const updateConditionRule = (branchId: string, ruleId: string, updates: Partial<ConditionRule>) => {
    setBranches(branches.map(b => 
      b.id === branchId 
        ? { 
            ...b, 
            conditions: b.conditions.map(r => 
              r.id === ruleId ? { ...r, ...updates } : r
            ) 
          }
        : b
    ))
  }

  // 删除条件规则
  const removeConditionRule = (branchId: string, ruleId: string) => {
    setBranches(branches.map(b => 
      b.id === branchId 
        ? { ...b, conditions: b.conditions.filter(r => r.id !== ruleId) }
        : b
    ))
  }

  // ============ 循环退出条件相关函数 ============
  
  // 添加循环退出条件规则
  const addLoopExitConditionRule = () => {
    const newRule: ConditionRule = {
      id: `rule_${Date.now()}`,
      variable: '',
      variableSource: '',
      operator: 'equals',
      value: '',
    }
    setLoopConfig(prev => ({
      ...prev,
      exitConditions: [...(prev.exitConditions || []), newRule]
    }))
  }

  // 更新循环退出条件规则
  const updateLoopExitConditionRule = (ruleId: string, updates: Partial<ConditionRule>) => {
    setLoopConfig(prev => ({
      ...prev,
      exitConditions: (prev.exitConditions || []).map(r => 
        r.id === ruleId ? { ...r, ...updates } : r
      )
    }))
  }

  // 删除循环退出条件规则
  const removeLoopExitConditionRule = (ruleId: string) => {
    setLoopConfig(prev => ({
      ...prev,
      exitConditions: (prev.exitConditions || []).filter(r => r.id !== ruleId)
    }))
  }

  // ============ 循环变量相关函数 ============
  
  // 打开添加循环变量模态框
  const openAddLoopVarDialog = () => {
    setEditingLoopVar(null)
    setLoopVarForm({
      name: '',
      type: 'string',
      defaultValue: '',
      description: '',
    })
    setIsLoopVarDialogOpen(true)
  }

  // 打开编辑循环变量模态框
  const openEditLoopVarDialog = (loopVar: LoopVariable) => {
    setEditingLoopVar(loopVar)
    setLoopVarForm({ ...loopVar })
    setIsLoopVarDialogOpen(true)
  }

  // 验证循环变量名是否重复
  const isLoopVarNameDuplicate = (name: string): boolean => {
    const existingNames = (loopConfig.loopVariables || [])
      .filter(v => editingLoopVar ? v.id !== editingLoopVar.id : true)
      .map(v => v.name.toLowerCase())
    
    // 也检查是否与索引变量重复
    if (loopConfig.indexVariable?.toLowerCase() === name.toLowerCase()) {
      return true
    }
    
    return existingNames.includes(name.toLowerCase())
  }

  // 获取循环变量名验证错误信息
  const getLoopVarNameError = (): string | null => {
    const name = loopVarForm.name?.trim() || ''
    if (!name) return null
    if (!isValidVariableName(name)) {
      return '变量名只能包含字母、数字、下划线，且不能以数字开头'
    }
    if (isLoopVarNameDuplicate(name)) {
      return '变量名已存在'
    }
    return null
  }

  const loopVarNameError = getLoopVarNameError()

  // 保存循环变量
  const saveLoopVariable = () => {
    const name = loopVarForm.name?.trim()
    if (!name) return
    if (loopVarNameError) return
    
    if (editingLoopVar) {
      // 更新现有变量
      setLoopConfig(prev => ({
        ...prev,
        loopVariables: (prev.loopVariables || []).map(v => 
          v.id === editingLoopVar.id ? { ...v, ...loopVarForm, name } as LoopVariable : v
        )
      }))
    } else {
      // 添加新变量
      const newVar: LoopVariable = {
        id: `loopvar_${Date.now()}`,
        name,
        type: (loopVarForm.type as LoopVariableType) || 'string',
        defaultValue: loopVarForm.defaultValue || '',
        description: loopVarForm.description || '',
      }
      setLoopConfig(prev => ({
        ...prev,
        loopVariables: [...(prev.loopVariables || []), newVar]
      }))
    }
    setIsLoopVarDialogOpen(false)
  }

  // 删除循环变量
  const removeLoopVariable = (id: string) => {
    setLoopConfig(prev => ({
      ...prev,
      loopVariables: (prev.loopVariables || []).filter(v => v.id !== id)
    }))
  }

  // 获取可用变量列表（从所有节点提取用户参数 + 系统参数）
  const getAvailableVariables = (filterType?: 'iterable' | 'all') => {
    const variables: {
      id: string
      name: string
      type: string
      group: string
      groupLabel: string
      isSystem: boolean
      isArray: boolean
      isIterable: boolean
    }[] = []
    
    // 从所有节点中提取变量
    allNodes.forEach(n => {
      const nodeType = n.type || (n.data as { type?: string })?.type
      const nodeData = n.data as { parameters?: Parameter[]; label?: string }
      const nodeLabel = nodeData.label || nodeType || '节点'
      
      // 开始节点的参数
      if (nodeType === 'user_input' || nodeType === 'trigger' || nodeType === 'start') {
        const params = nodeData.parameters || []
        params.forEach(p => {
          const isArray = p.type === 'array'
          const isObject = p.type === 'object'
          const isIterable = isArray || isObject
          
          // 如果指定了过滤类型，则只返回匹配的变量
          if (filterType === 'iterable' && !isIterable) return
          
          // 根据参数类型确定显示的类型名
          const getTypeName = (type: string) => {
            switch (type) {
              case 'number': return 'Number'
              case 'checkbox': return 'Boolean'
              case 'array': return 'Array'
              case 'object': return 'Object'
              default: return 'String'
            }
          }
          
          variables.push({
            id: `${n.id}.${p.name}`,
            name: p.name,
            type: getTypeName(p.type),
            group: n.id,
            groupLabel: nodeLabel,
            isSystem: false,
            isArray,
            isIterable,
          })
        })
      }
      
      // 迭代节点的输出变量
      if (nodeType === 'iteration') {
        const iterConfig = (n.data as { iterationConfig?: IterationConfig })?.iterationConfig || defaultIterationConfig
        const outputVar = iterConfig.outputVariable || 'results'
        
        // 迭代结果是数组类型
        if (filterType !== 'iterable' || true) { // 迭代结果本身也是数组，可以被迭代
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
      }
      
      // 循环节点的输出变量
      if (nodeType === 'loop') {
        const lpConfig = (n.data as { loopConfig?: LoopConfig })?.loopConfig || defaultLoopConfig
        const outputVar = lpConfig.outputVariable || 'results'
        const indexVar = lpConfig.indexVariable || 'index'
        const loopVars = lpConfig.loopVariables || []
        
        // 根据循环变量类型获取显示类型名
        const getLoopVarTypeName = (type: string) => {
          switch (type) {
            case 'number': return 'Number'
            case 'boolean': return 'Boolean'
            case 'array': return 'Array'
            case 'object': return 'Object'
            default: return 'String'
          }
        }
        
        // 循环结果是数组类型
        if (filterType !== 'iterable' || true) { // 循环结果本身也是数组，可以被迭代
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
        
        // 循环索引变量
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
        
        // 循环内部变量列表 - 使用配置的类型
        loopVars.forEach(loopVar => {
          const isLoopVarArray = loopVar.type === 'array'
          const isLoopVarObject = loopVar.type === 'object'
          const isLoopVarIterable = isLoopVarArray || isLoopVarObject
          
          // 如果筛选可迭代类型且当前变量不可迭代，则跳过
          if (filterType === 'iterable' && !isLoopVarIterable) {
            return
          }
          
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
      
      // TODO: 未来可以添加其他节点的输出变量（如 LLM 输出、工具调用结果等）
    })
    
    // 系统参数（系统参数不是可迭代类型，所以在过滤可迭代类型时不显示）
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
  }

  // 过滤变量
  const filterVariables = (search: string, filterType?: 'iterable' | 'all') => {
    const variables = getAvailableVariables(filterType)
    if (!search) return variables
    return variables.filter(v => 
      v.name.toLowerCase().includes(search.toLowerCase())
    )
  }

  // 选择变量
  const selectVariable = (branchId: string, ruleId: string, variableName: string) => {
    updateConditionRule(branchId, ruleId, { 
      variable: `{{${variableName}}}`,
      variableSource: variableName.startsWith('sys.') ? 'SYSTEM' : '用户输入'
    })
    setOpenVariablePopover(null)
    setVariableSearch('')
  }

  // 检查输出变量名是否与其他节点的变量名重复
  const isOutputVariableDuplicate = (varName: string) => {
    if (!varName || !node) return false
    const lowerName = varName.toLowerCase()
    
    // 获取所有其他节点的输出变量
    for (const n of allNodes) {
      if (n.id === node.id) continue // 跳过当前节点
      
      const nType = n.type || (n.data as { type?: string })?.type
      const nData = n.data as Record<string, unknown>
      
      // 检查开始节点的参数
      if (nType === 'user_input' || nType === 'trigger' || nType === 'start') {
        const params = (nData.parameters as Parameter[]) || []
        for (const p of params) {
          if (p.name.toLowerCase() === lowerName) return true
        }
      }
      
      // 检查其他迭代节点的输出变量
      if (nType === 'iteration') {
        const iterConfig = (nData.iterationConfig as IterationConfig) || defaultIterationConfig
        const outputVar = iterConfig.outputVariable || 'results'
        if (outputVar.toLowerCase() === lowerName) return true
      }
      
      // 检查其他循环节点的输出变量
      if (nType === 'loop') {
        const lpConfig = (nData.loopConfig as LoopConfig) || defaultLoopConfig
        const outputVar = lpConfig.outputVariable || 'results'
        if (outputVar.toLowerCase() === lowerName) return true
      }
    }
    
    // 检查系统参数
    for (const p of systemParameters) {
      if (p.name.toLowerCase() === lowerName) return true
    }
    
    return false
  }

  // 检查节点名称是否与其他节点重复
  const isNodeLabelDuplicate = (labelName: string) => {
    if (!labelName || !node) return false
    const lowerName = labelName.toLowerCase()
    
    for (const n of allNodes) {
      if (n.id === node.id) continue // 跳过当前节点
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
          <div className="space-y-4">
            {/* 系统参数（只读） */}
            <div className="space-y-2">
              <Label className="text-xs font-medium text-muted-foreground">SYSTEM</Label>
              <div className="space-y-1">
                {systemParameters.map((param) => (
                  <div 
                    key={param.id} 
                    className="flex items-center justify-between py-1 px-2 text-xs"
                  >
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <span className="w-3 h-3 rounded border border-orange-400 flex items-center justify-center text-[8px] text-orange-400 font-medium">S</span>
                      {param.name}
                    </span>
                    <span className="text-muted-foreground/60">
                      {param.valueType}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* 用户输入参数 */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">输入参数</Label>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-6 px-2 text-xs"
                  onClick={openAddParamDialog}
                >
                  <Plus className="h-3 w-3 mr-1" />
                  添加
                </Button>
              </div>
              
              {parameters.length === 0 ? (
                <p className="text-xs text-muted-foreground py-4 text-center">
                  暂无参数，点击添加按钮创建
                </p>
              ) : (
                <div className="space-y-1">
                  {parameters.map((param) => {
                    const typeConfig = parameterTypeConfig[param.type] || parameterTypeConfig.text
                    const TypeIcon = typeConfig.icon
                    return (
                      <div 
                        key={param.id} 
                        className="group flex items-center justify-between py-1.5 px-2 rounded-md hover:bg-muted/50 transition-colors cursor-pointer"
                        onClick={() => openEditParamDialog(param)}
                      >
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <TypeIcon className="h-4 w-4 text-primary/70 shrink-0" />
                          <span className="text-xs font-medium truncate">{param.name || '未命名'}</span>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {param.required && (
                            <span className="text-xs text-muted-foreground group-hover:hidden">必填</span>
                          )}
                          <span className="text-xs text-muted-foreground px-1.5 py-0.5 rounded border border-border group-hover:hidden">
                            {typeConfig.valueType}
                          </span>
                          {/* 悬浮显示的操作按钮 */}
                          <div className="hidden group-hover:flex items-center gap-0.5">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5"
                              onClick={(e) => {
                                e.stopPropagation()
                                openEditParamDialog(param)
                              }}
                            >
                              <Pencil className="h-3 w-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-5 w-5 text-destructive hover:text-destructive"
                              onClick={(e) => {
                                e.stopPropagation()
                                removeParameter(param.id)
                              }}
                            >
                              <Trash2 className="h-3 w-3" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )
      
      case 'llm':
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>模型</Label>
              <p className="text-xs text-muted-foreground">
                选择要使用的语言模型
              </p>
              <Button variant="outline" size="sm" className="w-full">
                选择模型
              </Button>
            </div>
            <div className="space-y-2">
              <Label>系统提示词</Label>
              <Textarea
                placeholder="输入系统提示词..."
                className="min-h-[100px]"
              />
            </div>
            <div className="space-y-2">
              <Label>用户提示词</Label>
              <Textarea
                placeholder="输入用户提示词模板，可以使用 {{变量名}} 引用上游变量"
                className="min-h-[100px]"
              />
            </div>
          </div>
        )
      
      case 'condition':
        return (
          <div className="space-y-3">
            {/* 分支列表 */}
            {branches.map((branch, index) => {
              const isExpanded = expandedBranches.has(branch.id)
              const isElse = branch.type === 'else'
              const canDelete = branch.type === 'else_if'
              
              return (
                <div 
                  key={branch.id} 
                  className={cn(
                    'rounded-lg border',
                    isElse ? 'border-muted bg-muted/30' : 'border-cyan-500/30 bg-cyan-500/5'
                  )}
                >
                  {/* 分支头部 */}
                  <div 
                    className="flex items-center gap-2 px-3 py-2 cursor-pointer"
                    onClick={() => !isElse && toggleBranchExpand(branch.id)}
                  >
                    {!isElse && (
                      <button className="p-0.5 hover:bg-muted rounded">
                        {isExpanded ? (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </button>
                    )}
                    {isElse ? (
                      <span className="h-6 text-xs font-medium text-muted-foreground flex items-center">
                        {branch.name}
                      </span>
                    ) : (
                      <Input
                        value={branch.name}
                        onChange={(e) => updateBranchName(branch.id, e.target.value)}
                        onClick={(e) => e.stopPropagation()}
                        className="h-6 text-xs font-medium border-0 bg-transparent p-0 shadow-none focus-visible:ring-0 text-cyan-600 dark:text-cyan-400"
                      />
                    )}
                    <div className="flex-1" />
                    {branch.conditions.length > 0 && (
                      <span className="text-[10px] text-muted-foreground">
                        {branch.conditions.length} 条件
                      </span>
                    )}
                    {canDelete && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 text-destructive hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeBranch(branch.id)
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                  
                  {/* 条件规则列表（非ELSE分支） */}
                  {!isElse && isExpanded && (
                    <div className="px-3 pb-3 space-y-2">
                      {/* 逻辑操作符选择 */}
                      {branch.conditions.length > 1 && (
                        <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                          <span>满足</span>
                          <Select
                            value={branch.logicOperator}
                            onValueChange={(v) => updateBranchLogicOperator(branch.id, v as 'and' | 'or')}
                          >
                            <SelectTrigger className="h-6 w-16 text-xs bg-background">
                              <SelectValue>
                                {branch.logicOperator === 'and' ? '全部' : '任一'}
                              </SelectValue>
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="and">全部</SelectItem>
                              <SelectItem value="or">任一</SelectItem>
                            </SelectContent>
                          </Select>
                          <span>条件时执行</span>
                        </div>
                      )}
                      
                      {/* 条件规则 */}
                      {branch.conditions.map((rule, ruleIndex) => (
                        <div key={rule.id} className="flex items-start gap-1.5">
                          {ruleIndex > 0 && (
                            <span className="text-[10px] text-muted-foreground pt-2 w-6 shrink-0 text-center">
                              {branch.logicOperator === 'and' ? '且' : '或'}
                            </span>
                          )}
                          <div className={cn('flex-1 space-y-1.5', ruleIndex === 0 && 'ml-7')}>
                            {/* 变量选择 Popover */}
                            <Popover 
                              open={openVariablePopover === `${branch.id}-${rule.id}`} 
                              onOpenChange={(open) => {
                                setOpenVariablePopover(open ? `${branch.id}-${rule.id}` : null)
                                if (!open) setVariableSearch('')
                              }}
                            >
                              <PopoverTrigger
                                className="w-full h-8 flex items-center justify-start px-3 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                              >
                                {rule.variable ? (
                                  <span className="flex items-center gap-1">
                                    <span className="text-primary/80 font-mono">{'{x}'}</span>
                                    <span>{rule.variable.replace(/\{\{|\}\}/g, '')}</span>
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">变量，如：{'{{query}}'}</span>
                                )}
                              </PopoverTrigger>
                              <PopoverContent className="w-72 p-0" align="start">
                                {/* 搜索框 */}
                                <div className="p-2 border-b">
                                  <div className="relative">
                                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                                    <Input
                                      placeholder="搜索变量"
                                      value={variableSearch}
                                      onChange={(e) => setVariableSearch(e.target.value)}
                                      className="h-8 pl-8 text-xs"
                                    />
                                  </div>
                                </div>
                                {/* 变量列表 - 按节点分组 */}
                                <div className="max-h-64 overflow-y-auto p-1">
                                  {(() => {
                                    const filtered = filterVariables(variableSearch)
                                    // 按 group 分组
                                    const groups = filtered.reduce((acc, v) => {
                                      if (!acc[v.group]) {
                                        acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
                                      }
                                      acc[v.group].items.push(v)
                                      return acc
                                    }, {} as Record<string, { label: string; isSystem: boolean; items: typeof filtered }>)
                                    
                                    const groupEntries = Object.entries(groups)
                                    // 非系统组在前，系统组在后
                                    groupEntries.sort((a, b) => {
                                      if (a[1].isSystem && !b[1].isSystem) return 1
                                      if (!a[1].isSystem && b[1].isSystem) return -1
                                      return 0
                                    })
                                    
                                    if (groupEntries.length === 0) {
                                      return (
                                        <div className="py-4 text-center text-xs text-muted-foreground">
                                          未找到匹配的变量
                                        </div>
                                      )
                                    }
                                    
                                    return groupEntries.map(([groupId, group]) => (
                                      <div key={groupId} className="mb-1">
                                        <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                                          {group.label}
                                        </div>
                                        {group.items.map(variable => (
                                          <button
                                            key={variable.id}
                                            className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                            onClick={() => selectVariable(branch.id, rule.id, variable.name)}
                                          >
                                            <span className="flex items-center gap-1.5">
                                              <span className={cn(
                                                'font-mono',
                                                variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                                              )}>{'{x}'}</span>
                                              <span>{variable.name}</span>
                                            </span>
                                            <span className="text-muted-foreground">{variable.type}</span>
                                          </button>
                                        ))}
                                      </div>
                                    ))
                                  })()}
                                </div>
                              </PopoverContent>
                            </Popover>
                            {/* 操作符选择 */}
                            <Select
                              value={rule.operator}
                              onValueChange={(v) => updateConditionRule(branch.id, rule.id, { operator: v as ConditionOperator })}
                            >
                              <SelectTrigger className="w-full h-8 text-xs bg-background">
                                <SelectValue>
                                  {conditionOperatorLabels[rule.operator]}
                                </SelectValue>
                              </SelectTrigger>
                              <SelectContent>
                                {Object.entries(conditionOperatorLabels).map(([key, label]) => (
                                  <SelectItem key={key} value={key} className="text-xs">
                                    {label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            {/* 值输入（部分操作符不需要） */}
                            {!noValueOperators.includes(rule.operator) && (
                              <Input
                                value={rule.value}
                                onChange={(e) => updateConditionRule(branch.id, rule.id, { value: e.target.value })}
                                placeholder="比较值"
                                className="h-8 text-xs bg-background"
                              />
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8 shrink-0 text-destructive hover:text-destructive"
                            onClick={() => removeConditionRule(branch.id, rule.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      ))}
                      
                      {/* 添加条件按钮 */}
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full h-8 text-xs bg-background"
                        onClick={() => addConditionRule(branch.id)}
                      >
                        <Plus className="h-3 w-3 mr-1" />
                        添加条件
                      </Button>
                    </div>
                  )}
                </div>
              )
            })}
            
            {/* 添加 ELSE IF 按钮 */}
            <Button
              variant="outline"
              size="sm"
              className="w-full h-8 text-xs border-dashed"
              onClick={addElseIfBranch}
            >
              <Plus className="h-3 w-3 mr-1" />
              添加 ELSE IF 分支
            </Button>
          </div>
        )
      
      case 'sub_workflow':
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>选择工作流</Label>
              <p className="text-xs text-muted-foreground">
                选择要调用的子工作流
              </p>
              <Button variant="outline" size="sm" className="w-full">
                选择工作流
              </Button>
            </div>
          </div>
        )
      
      case 'tool':
        return (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>选择工具</Label>
              <p className="text-xs text-muted-foreground">
                选择要调用的工具
              </p>
              <Button variant="outline" size="sm" className="w-full">
                选择工具
              </Button>
            </div>
          </div>
        )
      
      case 'iteration':
        return (
          <div className="space-y-4">
            {/* 迭代对象选择 */}
            <div className="space-y-2">
              <Label className="text-xs font-medium">迭代对象</Label>
              <p className="text-xs text-muted-foreground">
                选择要遍历的数组变量
              </p>
              <Popover 
                open={openVariablePopover === 'iteration-source'} 
                onOpenChange={(open) => {
                  setOpenVariablePopover(open ? 'iteration-source' : null)
                  if (!open) setVariableSearch('')
                }}
              >
                <PopoverTrigger
                  className="w-full h-9 flex items-center justify-start px-3 text-sm bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                >
                  {iterationConfig.iteratorVariable ? (
                    <div className="flex items-center gap-2">
                      <span className="text-primary/80 font-mono text-xs">{'[]'}</span>
                      <span>{iterationConfig.iteratorVariable.replace(/\{\{|\}\}/g, '')}</span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">选择数组变量...</span>
                  )}
                </PopoverTrigger>
                <PopoverContent className="w-64 p-0" align="start">
                  <div className="p-2 border-b">
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                      <Input 
                        placeholder="搜索数组变量..." 
                        className="h-8 pl-7 text-xs"
                        value={variableSearch}
                        onChange={(e) => setVariableSearch(e.target.value)}
                      />
                    </div>
                  </div>
                  <ScrollArea className="h-[200px]">
                    <div className="p-1">
                      {(() => {
                        // 只过滤可迭代类型的变量（数组和对象）
                        const filtered = filterVariables(variableSearch, 'iterable')
                        
                        if (filtered.length === 0) {
                          return (
                            <div className="py-6 text-center text-xs text-muted-foreground">
                              <p>暂无可迭代变量</p>
                              <p className="text-[10px] mt-1">请在开始节点添加数组或对象类型参数</p>
                            </div>
                          )
                        }
                        
                        const grouped = filtered.reduce((acc, v) => {
                          if (!acc[v.group]) acc[v.group] = { label: v.groupLabel, items: [] }
                          acc[v.group].items.push(v)
                          return acc
                        }, {} as Record<string, { label: string; items: typeof filtered }>)
                        
                        return Object.entries(grouped).map(([group, { label, items }]) => (
                          <div key={group} className="mb-2">
                            <div className="text-[10px] font-medium text-muted-foreground px-2 py-1">
                              {label}
                            </div>
                            {items.map(v => (
                              <button
                                key={v.id}
                                className="w-full flex items-center gap-2 px-2 py-1.5 text-xs hover:bg-muted rounded-md text-left"
                                onClick={() => {
                                  // 根据变量类型设置迭代器类型
                                  const iteratorType: IteratorType = v.type === 'Object' ? 'object' : 'array'
                                  setIterationConfig(prev => ({
                                    ...prev,
                                    iteratorVariable: `{{${v.name}}}`,
                                    iteratorSource: v.groupLabel,
                                    iteratorType,
                                  }))
                                  setOpenVariablePopover(null)
                                  setVariableSearch('')
                                }}
                              >
                                <span className="text-cyan-500 font-mono text-[10px] shrink-0">
                                  {v.type === 'Array' ? '[]' : '{}'}
                                </span>
                                <span className="flex-1 truncate">{v.name}</span>
                                <span className="text-muted-foreground/60 text-[10px]">{v.type}</span>
                              </button>
                            ))}
                          </div>
                        ))
                      })()}
                    </div>
                  </ScrollArea>
                </PopoverContent>
              </Popover>
            </div>
            
            {/* 输出变量配置 - 根据迭代类型显示不同字段 */}
            <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground">输出变量</Label>
                <span className="text-[10px] text-muted-foreground">
                  {iterationConfig.iteratorType === 'object' ? '对象迭代' : '数组迭代'}
                </span>
              </div>
              
              {iterationConfig.iteratorType === 'object' ? (
                // 对象迭代：key + value
                <div className="space-y-2">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Label className="text-xs w-16 shrink-0">键名</Label>
                      <Input 
                        value={iterationConfig.keyVariable}
                        onChange={(e) => setIterationConfig(prev => ({ ...prev, keyVariable: e.target.value }))}
                        placeholder="key"
                        className={cn(
                          'h-8 text-xs font-mono',
                          (iterationConfig.keyVariable && !isValidVariableName(iterationConfig.keyVariable)) && '!border-destructive !ring-destructive/20'
                        )}
                      />
                    </div>
                    {iterationConfig.keyVariable && !isValidVariableName(iterationConfig.keyVariable) && (
                      <p className="text-[10px] text-destructive ml-18">格式无效</p>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Label className="text-xs w-16 shrink-0">键值</Label>
                      <Input 
                        value={iterationConfig.valueVariable}
                        onChange={(e) => setIterationConfig(prev => ({ ...prev, valueVariable: e.target.value }))}
                        placeholder="value"
                        className={cn(
                          'h-8 text-xs font-mono',
                          ((iterationConfig.valueVariable && !isValidVariableName(iterationConfig.valueVariable)) ||
                           (iterationConfig.keyVariable && iterationConfig.valueVariable && 
                            iterationConfig.keyVariable.toLowerCase() === iterationConfig.valueVariable.toLowerCase())) && '!border-destructive !ring-destructive/20'
                        )}
                      />
                    </div>
                    {iterationConfig.valueVariable && !isValidVariableName(iterationConfig.valueVariable) && (
                      <p className="text-[10px] text-destructive ml-18">格式无效</p>
                    )}
                    {iterationConfig.keyVariable && iterationConfig.valueVariable && 
                     iterationConfig.keyVariable.toLowerCase() === iterationConfig.valueVariable.toLowerCase() && (
                      <p className="text-[10px] text-destructive ml-18">变量名不能重复</p>
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground">只能包含字母、数字、下划线，且不能以数字开头</p>
                </div>
              ) : (
                // 数组迭代：item + index
                <div className="space-y-2">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Label className="text-xs w-16 shrink-0">当前项</Label>
                      <Input 
                        value={iterationConfig.itemVariable}
                        onChange={(e) => setIterationConfig(prev => ({ ...prev, itemVariable: e.target.value }))}
                        placeholder="item"
                        className={cn(
                          'h-8 text-xs font-mono',
                          (iterationConfig.itemVariable && !isValidVariableName(iterationConfig.itemVariable)) && '!border-destructive !ring-destructive/20'
                        )}
                      />
                    </div>
                    {iterationConfig.itemVariable && !isValidVariableName(iterationConfig.itemVariable) && (
                      <p className="text-[10px] text-destructive ml-18">格式无效</p>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Label className="text-xs w-16 shrink-0">索引</Label>
                      <Input 
                        value={iterationConfig.indexVariable}
                        onChange={(e) => setIterationConfig(prev => ({ ...prev, indexVariable: e.target.value }))}
                        placeholder="index"
                        className={cn(
                          'h-8 text-xs font-mono',
                          ((iterationConfig.indexVariable && !isValidVariableName(iterationConfig.indexVariable)) ||
                           (iterationConfig.itemVariable && iterationConfig.indexVariable && 
                            iterationConfig.itemVariable.toLowerCase() === iterationConfig.indexVariable.toLowerCase())) && '!border-destructive !ring-destructive/20'
                        )}
                      />
                    </div>
                    {iterationConfig.indexVariable && !isValidVariableName(iterationConfig.indexVariable) && (
                      <p className="text-[10px] text-destructive ml-18">格式无效</p>
                    )}
                    {iterationConfig.itemVariable && iterationConfig.indexVariable && 
                     iterationConfig.itemVariable.toLowerCase() === iterationConfig.indexVariable.toLowerCase() && (
                      <p className="text-[10px] text-destructive ml-18">变量名不能重复</p>
                    )}
                  </div>
                  <p className="text-[10px] text-muted-foreground">只能包含字母、数字、下划线，且不能以数字开头</p>
                </div>
              )}
            </div>
            
            {/* 并行执行配置 */}
            <div className="space-y-3 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="text-xs font-medium">并行执行</Label>
                  <p className="text-[10px] text-muted-foreground">同时执行多个迭代</p>
                </div>
                <Switch 
                  checked={iterationConfig.parallel}
                  onCheckedChange={(checked) => setIterationConfig(prev => ({ ...prev, parallel: checked }))}
                />
              </div>
              
              {iterationConfig.parallel && (
                <div className="flex items-center gap-2">
                  <Label className="text-xs w-20 shrink-0">最大并行数</Label>
                  <Input 
                    type="number"
                    value={iterationConfig.maxParallel}
                    onChange={(e) => setIterationConfig(prev => ({ ...prev, maxParallel: parseInt(e.target.value) || 10 }))}
                    className="h-8 text-xs w-20"
                    min={1}
                    max={100}
                  />
                </div>
              )}
            </div>
            
            {/* 迭代结果输出配置 */}
            <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground">迭代结果</Label>
                <span className="text-[10px] text-muted-foreground">
                  Array
                </span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Label className="text-xs w-16 shrink-0">输出变量</Label>
                  <Input 
                    value={iterationConfig.outputVariable || ''}
                    onChange={(e) => setIterationConfig(prev => ({ ...prev, outputVariable: e.target.value }))}
                    placeholder="results"
                    className={cn(
                      'h-8 text-xs font-mono',
                      ((iterationConfig.outputVariable && !isValidVariableName(iterationConfig.outputVariable)) ||
                       isOutputVariableDuplicate(iterationConfig.outputVariable || '')) && '!border-destructive !ring-destructive/20'
                    )}
                  />
                </div>
                {iterationConfig.outputVariable && !isValidVariableName(iterationConfig.outputVariable) && (
                  <p className="text-[10px] text-destructive ml-18">格式无效，只能包含字母、数字、下划线，且不能以数字开头</p>
                )}
                {iterationConfig.outputVariable && isValidVariableName(iterationConfig.outputVariable) && 
                 isOutputVariableDuplicate(iterationConfig.outputVariable) && (
                  <p className="text-[10px] text-destructive ml-18">变量名与其他节点冲突</p>
                )}
              </div>
              <p className="text-[10px] text-muted-foreground">
                每次迭代执行完成后的返回值将收集到此数组中
              </p>
            </div>
          </div>
        )
      
      case 'loop':
        return (
          <div className="space-y-4">
            {/* 最大循环次数配置 */}
            <div className="space-y-2">
              <Label className="text-xs font-medium">最大循环次数</Label>
              <p className="text-xs text-muted-foreground">
                防止无限循环，达到此次数后自动退出
              </p>
              <Input 
                type="number" 
                value={loopConfig.maxIterations}
                onChange={(e) => setLoopConfig(prev => ({ ...prev, maxIterations: parseInt(e.target.value) || 10 }))}
                placeholder="10" 
                className="h-9"
                min={1}
                max={1000}
              />
            </div>
            
            {/* 循环内部变量配置 */}
            <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground">循环变量</Label>
              </div>
              
              <div className="space-y-2">
                {/* 索引变量 - 固定为 Number 类型 */}
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <Label className="text-xs w-16 shrink-0">索引</Label>
                    <Input 
                      value={loopConfig.indexVariable}
                      onChange={(e) => setLoopConfig(prev => ({ ...prev, indexVariable: e.target.value }))}
                      placeholder="index"
                      className={cn(
                        'h-8 text-xs font-mono flex-1',
                        (loopConfig.indexVariable && !isValidVariableName(loopConfig.indexVariable)) && '!border-destructive !ring-destructive/20'
                      )}
                    />
                    <span className="text-[10px] text-muted-foreground w-12 text-right">Number</span>
                  </div>
                  {loopConfig.indexVariable && !isValidVariableName(loopConfig.indexVariable) && (
                    <p className="text-[10px] text-destructive ml-18">格式无效</p>
                  )}
                </div>
                
                <p className="text-[10px] text-muted-foreground">
                  循环变量在每次迭代中可被内部节点更新
                </p>
              </div>
            </div>
            
            {/* 内部变量列表 */}
            <div className="space-y-3 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">内部变量</Label>
                <span className="text-[10px] text-muted-foreground">
                  {(loopConfig.loopVariables || []).length} 个变量
                </span>
              </div>
              
              {/* 变量列表 */}
              <div className="space-y-1.5">
                {(loopConfig.loopVariables || []).map((loopVar) => {
                  const typeConfig = loopVariableTypeConfig[loopVar.type] || loopVariableTypeConfig.string
                  const TypeIcon = typeConfig.icon
                  return (
                    <div
                      key={loopVar.id}
                      className="group flex items-center gap-2 px-2 py-1.5 bg-muted/50 rounded-md hover:bg-muted transition-colors cursor-pointer"
                      onClick={() => openEditLoopVarDialog(loopVar)}
                    >
                      <span className="text-[10px] text-muted-foreground shrink-0">
                        <TypeIcon className="h-3 w-3" />
                      </span>
                      <span className="text-xs font-mono text-primary/80 truncate flex-1">
                        {loopVar.name}
                      </span>
                      <span className="text-[10px] text-muted-foreground bg-background px-1.5 py-0.5 rounded shrink-0">
                        {typeConfig.label}
                      </span>
                      {loopVar.defaultValue && (
                        <span className="text-[10px] text-muted-foreground truncate max-w-16">
                          = {loopVar.defaultValue}
                        </span>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-5 w-5 shrink-0 opacity-0 group-hover:opacity-100 text-destructive hover:text-destructive transition-opacity"
                        onClick={(e) => {
                          e.stopPropagation()
                          removeLoopVariable(loopVar.id)
                        }}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    </div>
                  )
                })}
              </div>
              
              {/* 添加变量按钮 */}
              <Button
                variant="outline"
                size="sm"
                className="w-full h-8 text-xs bg-background"
                onClick={openAddLoopVarDialog}
              >
                <Plus className="h-3 w-3 mr-1" />
                添加变量
              </Button>
            </div>
            
            {/* 退出条件配置 - 参考条件分支 */}
            <div className="space-y-3 rounded-lg border p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">退出条件</Label>
                <span className="text-[10px] text-muted-foreground">满足条件时提前退出</span>
              </div>
              
              {/* 逻辑操作符选择 */}
              {(loopConfig.exitConditions?.length || 0) > 1 && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>满足</span>
                  <Select
                    value={loopConfig.exitLogicOperator || 'and'}
                    onValueChange={(v) => setLoopConfig(prev => ({ ...prev, exitLogicOperator: v as 'and' | 'or' }))}
                  >
                    <SelectTrigger className="h-6 w-16 text-xs bg-background">
                      <SelectValue>
                        {loopConfig.exitLogicOperator === 'and' ? '全部' : '任一'}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="and">全部</SelectItem>
                      <SelectItem value="or">任一</SelectItem>
                    </SelectContent>
                  </Select>
                  <span>条件时退出</span>
                </div>
              )}
              
              {/* 条件规则列表 */}
              <div className="space-y-2">
                {(loopConfig.exitConditions || []).map((rule, ruleIndex) => (
                  <div key={rule.id} className="flex items-start gap-1.5">
                    {ruleIndex > 0 && (
                      <span className="text-[10px] text-muted-foreground pt-2 w-6 shrink-0 text-center">
                        {loopConfig.exitLogicOperator === 'and' ? '且' : '或'}
                      </span>
                    )}
                    <div className={cn('flex-1 space-y-1.5', ruleIndex === 0 && 'ml-7')}>
                      {/* 变量选择 Popover */}
                      <Popover 
                        open={openVariablePopover === `loop-exit-${rule.id}`} 
                        onOpenChange={(open) => {
                          setOpenVariablePopover(open ? `loop-exit-${rule.id}` : null)
                          if (!open) setVariableSearch('')
                        }}
                      >
                        <PopoverTrigger
                          className="w-full h-8 flex items-center justify-start px-3 text-xs bg-background border border-input rounded-md cursor-pointer hover:bg-accent hover:text-accent-foreground"
                        >
                          {rule.variable ? (
                            <span className="flex items-center gap-1">
                              <span className="text-primary/80 font-mono">{'{x}'}</span>
                              <span>{rule.variable.replace(/\{\{|\}\}/g, '')}</span>
                            </span>
                          ) : (
                            <span className="text-muted-foreground">变量，如：{'{{current}}'}</span>
                          )}
                        </PopoverTrigger>
                        <PopoverContent className="w-72 p-0" align="start">
                          {/* 搜索框 */}
                          <div className="p-2 border-b">
                            <div className="relative">
                              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                              <Input
                                placeholder="搜索变量"
                                value={variableSearch}
                                onChange={(e) => setVariableSearch(e.target.value)}
                                className="h-8 pl-8 text-xs"
                              />
                            </div>
                          </div>
                          {/* 变量列表 */}
                          <div className="max-h-64 overflow-y-auto p-1">
                            {(() => {
                              const filtered = filterVariables(variableSearch)
                              const groups = filtered.reduce((acc, v) => {
                                if (!acc[v.group]) {
                                  acc[v.group] = { label: v.groupLabel, isSystem: v.isSystem, items: [] }
                                }
                                acc[v.group].items.push(v)
                                return acc
                              }, {} as Record<string, { label: string; isSystem: boolean; items: typeof filtered }>)
                              
                              const groupEntries = Object.entries(groups)
                              groupEntries.sort((a, b) => {
                                if (a[1].isSystem && !b[1].isSystem) return 1
                                if (!a[1].isSystem && b[1].isSystem) return -1
                                return 0
                              })
                              
                              if (groupEntries.length === 0) {
                                return (
                                  <div className="py-4 text-center text-xs text-muted-foreground">
                                    未找到匹配的变量
                                  </div>
                                )
                              }
                              
                              return groupEntries.map(([groupId, group]) => (
                                <div key={groupId} className="mb-1">
                                  <div className="px-2 py-1 text-xs text-muted-foreground font-medium">
                                    {group.label}
                                  </div>
                                  {group.items.map(variable => (
                                    <button
                                      key={variable.id}
                                      className="w-full flex items-center justify-between px-2 py-1.5 text-xs hover:bg-muted rounded-md"
                                      onClick={() => {
                                        updateLoopExitConditionRule(rule.id, { 
                                          variable: `{{${variable.name}}}`,
                                          variableSource: variable.isSystem ? 'SYSTEM' : variable.groupLabel
                                        })
                                        setOpenVariablePopover(null)
                                        setVariableSearch('')
                                      }}
                                    >
                                      <span className="flex items-center gap-1.5">
                                        <span className={cn(
                                          'font-mono',
                                          variable.isSystem ? 'text-orange-500' : 'text-primary/80'
                                        )}>{'{x}'}</span>
                                        <span>{variable.name}</span>
                                      </span>
                                      <span className="text-muted-foreground">{variable.type}</span>
                                    </button>
                                  ))}
                                </div>
                              ))
                            })()}
                          </div>
                        </PopoverContent>
                      </Popover>
                      {/* 操作符选择 */}
                      <Select
                        value={rule.operator}
                        onValueChange={(v) => updateLoopExitConditionRule(rule.id, { operator: v as ConditionOperator })}
                      >
                        <SelectTrigger className="w-full h-8 text-xs bg-background">
                          <SelectValue>
                            {conditionOperatorLabels[rule.operator]}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(conditionOperatorLabels).map(([key, label]) => (
                            <SelectItem key={key} value={key} className="text-xs">
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {/* 值输入（部分操作符不需要） */}
                      {!noValueOperators.includes(rule.operator) && (
                        <Input
                          value={rule.value}
                          onChange={(e) => updateLoopExitConditionRule(rule.id, { value: e.target.value })}
                          placeholder="比较值"
                          className="h-8 text-xs bg-background"
                        />
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-destructive hover:text-destructive"
                      onClick={() => removeLoopExitConditionRule(rule.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
              
              {/* 添加条件按钮 */}
              <Button
                variant="outline"
                size="sm"
                className="w-full h-8 text-xs bg-background"
                onClick={addLoopExitConditionRule}
              >
                <Plus className="h-3 w-3 mr-1" />
                添加退出条件
              </Button>
            </div>
            
            {/* 循环结果输出配置 */}
            <div className="space-y-3 rounded-lg border bg-muted/30 p-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium text-muted-foreground">循环结果</Label>
                <span className="text-[10px] text-muted-foreground">
                  Array
                </span>
              </div>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Label className="text-xs w-16 shrink-0">输出变量</Label>
                  <Input 
                    value={loopConfig.outputVariable || ''}
                    onChange={(e) => setLoopConfig(prev => ({ ...prev, outputVariable: e.target.value }))}
                    placeholder="results"
                    className={cn(
                      'h-8 text-xs font-mono',
                      ((loopConfig.outputVariable && !isValidVariableName(loopConfig.outputVariable)) ||
                       isOutputVariableDuplicate(loopConfig.outputVariable || '')) && '!border-destructive !ring-destructive/20'
                    )}
                  />
                </div>
                {loopConfig.outputVariable && !isValidVariableName(loopConfig.outputVariable) && (
                  <p className="text-[10px] text-destructive ml-18">格式无效，只能包含字母、数字、下划线，且不能以数字开头</p>
                )}
                {loopConfig.outputVariable && isValidVariableName(loopConfig.outputVariable) && 
                 isOutputVariableDuplicate(loopConfig.outputVariable) && (
                  <p className="text-[10px] text-destructive ml-18">变量名与其他节点冲突</p>
                )}
              </div>
              <p className="text-[10px] text-muted-foreground">
                每次循环执行完成后的返回值将收集到此数组中
              </p>
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
          {/* Basic Info - hide name field for start nodes */}
          <div className="space-y-2">
            {!isStartNode && (
              <div className="space-y-2">
                <Label htmlFor="node-label">节点名称</Label>
                <Input
                  id="node-label"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="输入节点名称"
                  className={cn(
                    isNodeLabelDuplicate(label) && '!border-destructive !ring-destructive/20'
                  )}
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

          {/* Tabs */}
          <Tabs defaultValue="settings" className="w-full">
            <TabsList className="w-full grid grid-cols-2">
              <TabsTrigger value="settings" className="text-xs">设置</TabsTrigger>
              <TabsTrigger value="last-run" className="text-xs">上次执行</TabsTrigger>
            </TabsList>
            <TabsContent value="settings" className="mt-3">
              {/* Type-specific Config */}
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
      <Dialog open={isParamDialogOpen} onOpenChange={setIsParamDialogOpen}>
        <DialogContent className="sm:max-w-[400px] max-h-[85vh] flex flex-col overflow-hidden">
          <DialogHeader className="shrink-0">
            <DialogTitle className="text-base">
              {editingParam ? '编辑变量' : '添加变量'}
            </DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto -mx-6 px-6">
            <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="param-name" className="text-xs">变量名</Label>
              <Input
                id="param-name"
                value={paramForm.name || ''}
                onChange={(e) => setParamForm({ ...paramForm, name: e.target.value })}
                placeholder="输入变量名（如：query）"
                className={cn('h-9', variableNameError && paramForm.name && '!border-destructive !ring-destructive/20')}
              />
              {variableNameError && paramForm.name && (
                <p className="text-[11px] text-destructive">{variableNameError}</p>
              )}
              <p className="text-[10px] text-muted-foreground">只能包含字母、数字、下划线，且不能以数字开头</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="param-type" className="text-xs">类型</Label>
              <Select
                value={paramForm.type || 'text'}
                onValueChange={(value) => setParamForm({ ...paramForm, type: value as Parameter['type'] })}
              >
                <SelectTrigger className="h-9 w-full">
                  <SelectValue>
                    {paramForm.type && (
                      <span className="flex items-center gap-2">
                        {paramForm.type === 'text' && <><Type className="h-4 w-4" /> 文本</>}
                        {paramForm.type === 'paragraph' && <><AlignLeft className="h-4 w-4" /> 段落</>}
                        {paramForm.type === 'select' && <><ListChecks className="h-4 w-4" /> 下拉选项</>}
                        {paramForm.type === 'number' && <><Hash className="h-4 w-4" /> 数字</>}
                        {paramForm.type === 'checkbox' && <><CheckSquare className="h-4 w-4" /> 复选框</>}
                        {paramForm.type === 'array' && <><Brackets className="h-4 w-4" /> 数组</>}
                        {paramForm.type === 'object' && <><Braces className="h-4 w-4" /> 对象</>}
                      </span>
                    )}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="text">
                    <span className="flex items-center gap-2"><Type className="h-4 w-4" /> 文本</span>
                  </SelectItem>
                  <SelectItem value="paragraph">
                    <span className="flex items-center gap-2"><AlignLeft className="h-4 w-4" /> 段落</span>
                  </SelectItem>
                  <SelectItem value="select">
                    <span className="flex items-center gap-2"><ListChecks className="h-4 w-4" /> 下拉选项</span>
                  </SelectItem>
                  <SelectItem value="number">
                    <span className="flex items-center gap-2"><Hash className="h-4 w-4" /> 数字</span>
                  </SelectItem>
                  <SelectItem value="checkbox">
                    <span className="flex items-center gap-2"><CheckSquare className="h-4 w-4" /> 复选框</span>
                  </SelectItem>
                  <SelectItem value="array">
                    <span className="flex items-center gap-2"><Brackets className="h-4 w-4" /> 数组</span>
                  </SelectItem>
                  <SelectItem value="object">
                    <span className="flex items-center gap-2"><Braces className="h-4 w-4" /> 对象</span>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* 根据类型显示不同的默认值表单 */}
            {paramForm.type === 'text' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">默认值</Label>
                <Input
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder="输入默认文本（可选）"
                  className="h-9"
                />
              </div>
            )}

            {paramForm.type === 'paragraph' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">默认值</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder="输入默认段落内容（可选）"
                  className="min-h-20 resize-none"
                />
              </div>
            )}

            {paramForm.type === 'select' && (
              <div className="space-y-2">
                <Label className="text-xs">选项列表</Label>
                <div className="space-y-1.5">
                  {(paramForm.options || ['']).map((option, index) => (
                    <div key={index} className="flex items-center gap-2">
                      <Input
                        value={option}
                        onChange={(e) => {
                          const newOptions = [...(paramForm.options || [''])]
                          newOptions[index] = e.target.value
                          setParamForm({ ...paramForm, options: newOptions })
                        }}
                        placeholder={`选项 ${index + 1}`}
                        className="h-8 text-sm flex-1"
                      />
                      {(paramForm.options || ['']).length > 1 && (
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 shrink-0"
                          onClick={() => {
                            const newOptions = (paramForm.options || ['']).filter((_, i) => i !== index)
                            setParamForm({ ...paramForm, options: newOptions })
                          }}
                        >
                          <Trash2 className="h-3 w-3 text-destructive" />
                        </Button>
                      )}
                    </div>
                  ))}
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full h-8 text-xs"
                    onClick={() => {
                      setParamForm({ ...paramForm, options: [...(paramForm.options || ['']), ''] })
                    }}
                  >
                    <Plus className="h-3 w-3 mr-1" />
                    添加选项
                  </Button>
                </div>
                <div className="space-y-2 pt-2">
                  <Label htmlFor="param-default" className="text-xs">默认选中</Label>
                  <Select
                    value={paramForm.defaultValue || ''}
                    onValueChange={(value) => setParamForm({ ...paramForm, defaultValue: value ?? undefined })}
                  >
                    <SelectTrigger className="h-9 w-full">
                      <SelectValue>{paramForm.defaultValue || '选择默认值（可选）'}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {(paramForm.options || []).filter(Boolean).map((option, index) => (
                        <SelectItem key={index} value={option}>
                          {option}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            )}

            {paramForm.type === 'number' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">默认值</Label>
                <Input
                  id="param-default"
                  type="number"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder="输入默认数字（可选）"
                  className="h-9"
                />
              </div>
            )}

            {paramForm.type === 'checkbox' && (
              <div className="flex items-center justify-between">
                <Label htmlFor="param-default" className="text-xs">默认选中</Label>
                <Switch
                  id="param-default"
                  checked={paramForm.defaultValue === 'true'}
                  onCheckedChange={(checked) => setParamForm({ ...paramForm, defaultValue: checked ? 'true' : 'false' })}
                />
              </div>
            )}

            {paramForm.type === 'array' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">默认值 (JSON)</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder='["item1", "item2", "item3"]'
                  className="min-h-24 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">输入 JSON 数组格式</p>
              </div>
            )}

            {paramForm.type === 'object' && (
              <div className="space-y-2">
                <Label htmlFor="param-default" className="text-xs">默认值 (JSON)</Label>
                <Textarea
                  id="param-default"
                  value={paramForm.defaultValue || ''}
                  onChange={(e) => setParamForm({ ...paramForm, defaultValue: e.target.value })}
                  placeholder='{"key": "value"}'
                  className="min-h-24 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">输入 JSON 对象格式</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="param-desc" className="text-xs">描述</Label>
              <Input
                id="param-desc"
                value={paramForm.description || ''}
                onChange={(e) => setParamForm({ ...paramForm, description: e.target.value })}
                placeholder="输入描述（可选）"
                className="h-9"
              />
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="param-required" className="text-xs">必填</Label>
              <Switch
                id="param-required"
                checked={paramForm.required || false}
                onCheckedChange={(checked) => setParamForm({ ...paramForm, required: checked })}
              />
            </div>
            </div>
          </div>
          <DialogFooter className="shrink-0">
            <Button variant="outline" size="sm" onClick={() => setIsParamDialogOpen(false)}>
              取消
            </Button>
            <Button size="sm" onClick={saveParameter} disabled={!paramForm.name?.trim() || !!variableNameError}>
              {editingParam ? '保存' : '添加'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 循环变量编辑对话框 */}
      <Dialog open={isLoopVarDialogOpen} onOpenChange={setIsLoopVarDialogOpen}>
        <DialogContent className="sm:max-w-[400px] flex flex-col max-h-[85vh]">
          <DialogHeader>
            <DialogTitle className="text-sm">{editingLoopVar ? '编辑变量' : '添加变量'}</DialogTitle>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto py-2 px-1 -mx-1">
            <div className="space-y-4 px-0.5">
            <div className="space-y-2">
              <Label htmlFor="loopvar-name" className="text-xs">变量名 *</Label>
              <Input
                id="loopvar-name"
                value={loopVarForm.name || ''}
                onChange={(e) => setLoopVarForm({ ...loopVarForm, name: e.target.value })}
                placeholder="例如: counter, total, result"
                className={cn(
                  'h-9 font-mono',
                  loopVarNameError && '!border-destructive !ring-destructive/20'
                )}
              />
              {loopVarNameError && (
                <p className="text-[10px] text-destructive">{loopVarNameError}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="loopvar-type" className="text-xs">类型</Label>
              <Select
                value={loopVarForm.type || 'string'}
                onValueChange={(v) => setLoopVarForm({ ...loopVarForm, type: v as LoopVariableType, defaultValue: '' })}
              >
                <SelectTrigger id="loopvar-type" className="h-9 w-full">
                  <SelectValue>
                    {(() => {
                      const currentType = loopVarForm.type || 'string'
                      const config = loopVariableTypeConfig[currentType]
                      const CurrentIcon = config.icon
                      return (
                        <span className="flex items-center gap-2">
                          <CurrentIcon className="h-3.5 w-3.5 text-muted-foreground" />
                          <span>{config.label}</span>
                        </span>
                      )
                    })()}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(loopVariableTypeConfig).map(([key, config]) => {
                    const OptionIcon = config.icon
                    return (
                      <SelectItem key={key} value={key} className="text-sm">
                        <span className="flex items-center gap-2">
                          <OptionIcon className="h-3.5 w-3.5 text-muted-foreground" />
                          <span>{config.label}</span>
                        </span>
                      </SelectItem>
                    )
                  })}
                </SelectContent>
              </Select>
            </div>

            {/* 默认值 - 根据类型显示不同输入 */}
            {(loopVarForm.type === 'string' || !loopVarForm.type) && (
              <div className="space-y-2">
                <Label htmlFor="loopvar-default" className="text-xs">默认值</Label>
                <Input
                  id="loopvar-default"
                  value={loopVarForm.defaultValue || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                  placeholder="可选"
                  className="h-9"
                />
              </div>
            )}

            {loopVarForm.type === 'number' && (
              <div className="space-y-2">
                <Label htmlFor="loopvar-default" className="text-xs">默认值</Label>
                <Input
                  id="loopvar-default"
                  type="number"
                  value={loopVarForm.defaultValue || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                  placeholder="0"
                  className="h-9"
                />
              </div>
            )}

            {loopVarForm.type === 'boolean' && (
              <div className="flex items-center justify-between">
                <Label htmlFor="loopvar-default" className="text-xs">默认值</Label>
                <Switch
                  id="loopvar-default"
                  checked={loopVarForm.defaultValue === 'true'}
                  onCheckedChange={(checked) => setLoopVarForm({ ...loopVarForm, defaultValue: checked ? 'true' : 'false' })}
                />
              </div>
            )}

            {loopVarForm.type === 'array' && (
              <div className="space-y-2">
                <Label htmlFor="loopvar-default" className="text-xs">默认值 (JSON)</Label>
                <Textarea
                  id="loopvar-default"
                  value={loopVarForm.defaultValue || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                  placeholder='["item1", "item2"]'
                  className="min-h-20 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">输入 JSON 数组格式</p>
              </div>
            )}

            {loopVarForm.type === 'object' && (
              <div className="space-y-2">
                <Label htmlFor="loopvar-default" className="text-xs">默认值 (JSON)</Label>
                <Textarea
                  id="loopvar-default"
                  value={loopVarForm.defaultValue || ''}
                  onChange={(e) => setLoopVarForm({ ...loopVarForm, defaultValue: e.target.value })}
                  placeholder='{"key": "value"}'
                  className="min-h-20 resize-none font-mono text-xs"
                />
                <p className="text-[10px] text-muted-foreground">输入 JSON 对象格式</p>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="loopvar-desc" className="text-xs">描述</Label>
              <Input
                id="loopvar-desc"
                value={loopVarForm.description || ''}
                onChange={(e) => setLoopVarForm({ ...loopVarForm, description: e.target.value })}
                placeholder="输入描述（可选）"
                className="h-9"
              />
            </div>
            </div>
          </div>
          <DialogFooter className="shrink-0">
            <Button variant="outline" size="sm" onClick={() => setIsLoopVarDialogOpen(false)}>
              取消
            </Button>
            <Button size="sm" onClick={saveLoopVariable} disabled={!loopVarForm.name?.trim() || !!loopVarNameError}>
              {editingLoopVar ? '保存' : '添加'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

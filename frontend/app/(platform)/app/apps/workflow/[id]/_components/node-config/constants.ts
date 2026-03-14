import {
  Home, Zap, Bot, GitBranch, Workflow, Wrench, Code,
  Type, AlignLeft, ListChecks, Hash, CheckSquare, RefreshCw, Infinity,
  Brackets, Braces, FileText, Combine, Variable, Image, File, Files, Images, Link, Tags, MessageSquareText, StickyNote, Sparkles, Database
} from 'lucide-react'
import type { ParameterType, SystemParameter, Parameter } from './types'

// 循环变量类型配置 - labelKey references workflow.varTypes.*
export const loopVariableTypeConfig = {
  string: { labelKey: 'text', icon: Type, placeholder: 'e.g. hello', valueType: 'String' },
  number: { labelKey: 'number', icon: Hash, placeholder: 'e.g. 0', valueType: 'Number' },
  boolean: { labelKey: 'boolean', icon: CheckSquare, placeholder: 'e.g. false', valueType: 'Boolean' },
  array: { labelKey: 'array', icon: Brackets, placeholder: 'e.g. []', valueType: 'Array' },
  object: { labelKey: 'object', icon: Braces, placeholder: 'e.g. {}', valueType: 'Object' },
} as const

// 参数类型配置 - labelKey references workflow.varTypes.*
export const parameterTypeConfig: Record<ParameterType, { labelKey: string; icon: React.ElementType; valueType: string }> = {
  text: { labelKey: 'text', icon: Type, valueType: 'string' },
  paragraph: { labelKey: 'paragraph', icon: AlignLeft, valueType: 'string' },
  select: { labelKey: 'select', icon: ListChecks, valueType: 'string' },
  number: { labelKey: 'number', icon: Hash, valueType: 'number' },
  checkbox: { labelKey: 'checkbox', icon: CheckSquare, valueType: 'boolean' },
  array: { labelKey: 'array', icon: Brackets, valueType: 'array' },
  object: { labelKey: 'object', icon: Braces, valueType: 'object' },
  file: { labelKey: 'file', icon: File, valueType: 'file' },
  image: { labelKey: 'image', icon: Image, valueType: 'file' },
  files: { labelKey: 'files', icon: Files, valueType: 'array' },
  images: { labelKey: 'images', icon: Images, valueType: 'array' },
}

// 节点类型信息 - titleKey references workflow.nodeLabels.*
export const nodeTypeInfo: Record<string, { icon: React.ElementType; color: string; titleKey: string }> = {
  user_input: { icon: Home, color: 'bg-primary', titleKey: 'user_input' },
  trigger: { icon: Zap, color: 'bg-amber-500', titleKey: 'trigger' },
  llm: { icon: Bot, color: 'bg-blue-500', titleKey: 'llm' },
  condition: { icon: GitBranch, color: 'bg-cyan-500', titleKey: 'condition' },
  iteration: { icon: RefreshCw, color: 'bg-cyan-500', titleKey: 'iteration' },
  loop: { icon: Infinity, color: 'bg-cyan-500', titleKey: 'loop' },
  question_classifier: { icon: Tags, color: 'bg-violet-500', titleKey: 'question_classifier' },
  answer: { icon: MessageSquareText, color: 'bg-emerald-500', titleKey: 'answer' },
  sub_workflow: { icon: Workflow, color: 'bg-purple-500', titleKey: 'sub_workflow' },
  agent: { icon: Sparkles, color: 'bg-indigo-500', titleKey: 'agent' },
  tool: { icon: Wrench, color: 'bg-emerald-500', titleKey: 'tool' },
  code: { icon: Code, color: 'bg-blue-500', titleKey: 'code' },
  template: { icon: FileText, color: 'bg-blue-500', titleKey: 'template' },
  file_to_url: { icon: Link, color: 'bg-teal-500', titleKey: 'file_to_url' },
  variable_aggregator: { icon: Combine, color: 'bg-blue-500', titleKey: 'variable_aggregator' },
  variable_assignment: { icon: Variable, color: 'bg-blue-500', titleKey: 'variable_assignment' },
  parameter_extractor: { icon: Braces, color: 'bg-blue-500', titleKey: 'parameter_extractor' },
  knowledge_retrieval: { icon: Database, color: 'bg-purple-500', titleKey: 'knowledge_retrieval' },
  comment: { icon: StickyNote, color: 'bg-amber-400', titleKey: 'comment' },
}

// 系统参数 - descriptionKey references workflow.systemParams.*
export const systemParameters: SystemParameter[] = [
  { id: 'sys_user_id', name: 'sys_user_id', valueType: 'String', descriptionKey: 'userId' },
  { id: 'sys_workflow_id', name: 'sys_workflow_id', valueType: 'String', descriptionKey: 'workflowId' },
  { id: 'sys_workflow_run_id', name: 'sys_workflow_run_id', valueType: 'String', descriptionKey: 'workflowRunId' },
  { id: 'sys_timestamp', name: 'sys_timestamp', valueType: 'Number', descriptionKey: 'timestamp' },
]

// 开始节点的默认用户参数 - descriptionKey references workflow.defaultParams.*
export const defaultStartParameters: Parameter[] = [
  { id: 'query', name: 'query', type: 'text', required: true, defaultValue: '', descriptionKey: 'queryDescription' },
]

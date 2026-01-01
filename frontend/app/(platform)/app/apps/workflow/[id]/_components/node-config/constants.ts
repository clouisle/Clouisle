import { 
  Home, Zap, Bot, GitBranch, Workflow, Wrench, Code, 
  Type, AlignLeft, ListChecks, Hash, CheckSquare, RefreshCw, Infinity,
  Brackets, Braces, FileText, Combine, Variable, Image, File, Files, Images, Link, Tags, MessageSquareText
} from 'lucide-react'
import type { ParameterType, SystemParameter, Parameter } from './types'

// 循环变量类型配置
export const loopVariableTypeConfig = {
  string: { label: '文本', icon: Type, placeholder: '如：hello', valueType: 'String' },
  number: { label: '数字', icon: Hash, placeholder: '如：0', valueType: 'Number' },
  boolean: { label: '布尔', icon: CheckSquare, placeholder: '如：false', valueType: 'Boolean' },
  array: { label: '数组', icon: Brackets, placeholder: '如：[]', valueType: 'Array' },
  object: { label: '对象', icon: Braces, placeholder: '如：{}', valueType: 'Object' },
} as const

// 参数类型配置
export const parameterTypeConfig: Record<ParameterType, { label: string; icon: React.ElementType; valueType: string }> = {
  text: { label: '文本', icon: Type, valueType: 'string' },
  paragraph: { label: '段落', icon: AlignLeft, valueType: 'string' },
  select: { label: '下拉选项', icon: ListChecks, valueType: 'string' },
  number: { label: '数字', icon: Hash, valueType: 'number' },
  checkbox: { label: '复选框', icon: CheckSquare, valueType: 'boolean' },
  array: { label: '数组', icon: Brackets, valueType: 'array' },
  object: { label: '对象', icon: Braces, valueType: 'object' },
  file: { label: '文件', icon: File, valueType: 'file' },
  image: { label: '图片', icon: Image, valueType: 'file' },
  files: { label: '多文件', icon: Files, valueType: 'array' },
  images: { label: '多图片', icon: Images, valueType: 'array' },
}

// 节点类型信息
export const nodeTypeInfo: Record<string, { icon: React.ElementType; color: string; title: string }> = {
  user_input: { icon: Home, color: 'bg-primary', title: '用户输入' },
  trigger: { icon: Zap, color: 'bg-amber-500', title: '触发器' },
  llm: { icon: Bot, color: 'bg-blue-500', title: 'LLM' },
  condition: { icon: GitBranch, color: 'bg-cyan-500', title: '条件分支' },
  iteration: { icon: RefreshCw, color: 'bg-cyan-500', title: '迭代' },
  loop: { icon: Infinity, color: 'bg-cyan-500', title: '循环' },
  question_classifier: { icon: Tags, color: 'bg-violet-500', title: '问题分类' },
  answer: { icon: MessageSquareText, color: 'bg-emerald-500', title: '输出' },
  sub_workflow: { icon: Workflow, color: 'bg-purple-500', title: '子工作流' },
  tool: { icon: Wrench, color: 'bg-emerald-500', title: '工具' },
  code: { icon: Code, color: 'bg-blue-500', title: '代码执行' },
  template: { icon: FileText, color: 'bg-blue-500', title: '模板转换' },
  file_to_url: { icon: Link, color: 'bg-teal-500', title: '文件转URL' },
  variable_aggregator: { icon: Combine, color: 'bg-blue-500', title: '变量聚合器' },
  variable_assignment: { icon: Variable, color: 'bg-blue-500', title: '变量赋值' },
  parameter_extractor: { icon: Braces, color: 'bg-blue-500', title: '参数提取器' },
}

// 系统参数
export const systemParameters: SystemParameter[] = [
  { id: 'sys.user_id', name: 'sys.user_id', valueType: 'String', description: '当前用户ID' },
  { id: 'sys.app_id', name: 'sys.app_id', valueType: 'String', description: '应用ID' },
  { id: 'sys.workflow_id', name: 'sys.workflow_id', valueType: 'String', description: '工作流ID' },
  { id: 'sys.workflow_run_id', name: 'sys.workflow_run_id', valueType: 'String', description: '工作流运行ID' },
  { id: 'sys.timestamp', name: 'sys.timestamp', valueType: 'Number', description: '当前时间戳' },
]

// 开始节点的默认用户参数
export const defaultStartParameters: Parameter[] = [
  { id: 'query', name: 'query', type: 'text', required: true, defaultValue: '', description: '用户输入的查询内容' },
]

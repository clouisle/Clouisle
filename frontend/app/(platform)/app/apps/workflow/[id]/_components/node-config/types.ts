// 参数类型定义
export type ParameterType = 'text' | 'paragraph' | 'select' | 'number' | 'checkbox' | 'array' | 'object' | 'file' | 'image' | 'files' | 'images'

export interface Parameter {
  id: string
  name: string
  type: ParameterType
  required: boolean
  defaultValue?: string
  description?: string
  isSystem?: boolean  // 系统参数标识，不可删除
  options?: string[]  // 下拉选项的选项列表
  // 文件类型专用配置
  fileConfig?: FileParameterConfig
}

// 文件参数配置
export interface FileParameterConfig {
  maxSize?: number        // 最大文件大小 (MB)
  accept?: string[]       // 允许的文件类型 (MIME types 或扩展名)
  maxFiles?: number       // 最大文件数量 (仅 files 类型)
}

// 文件变量结构
export interface FileVariable {
  id: string              // 文件唯一标识
  name: string            // 原始文件名
  type: string            // MIME 类型
  size: number            // 文件大小 (bytes)
  url: string             // 临时访问 URL
  base64?: string         // 可选：Base64 内容（小文件）
}

// 系统默认参数（不可删除）- 使用固定的值类型显示
export interface SystemParameter {
  id: string
  name: string
  valueType: 'String' | 'Number'
  description: string
}

// 可用变量类型
export interface AvailableVariable {
  id: string
  name: string
  type: string
  group: string
  groupLabel: string
  isSystem: boolean
  isArray: boolean
  isIterable: boolean
  isFile?: boolean  // 文件类型标记
}
/**
 * 从变量引用中提取显示名称
 * 
 * @param variableRef 变量引用，如 "{{nodeId.paramName}}" 或 "nodeId.paramName"
 * @returns 显示名称，如 "paramName"
 */
export function extractVariableDisplayName(variableRef: string): string {
  if (!variableRef) return ''
  // 移除 {{ 和 }}
  const cleaned = variableRef.replace(/\{\{|\}\}/g, '')
  // 取最后一部分作为显示名
  return cleaned.split('.').pop() || cleaned
}
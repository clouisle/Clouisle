'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Code, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'

// 代码语言类型
export type CodeLanguage = 'python' | 'javascript'

// 输出变量类型
export type OutputVariableType = 'string' | 'number' | 'boolean' | 'array' | 'object'

// 异常处理类型
export type ErrorHandlingType = 'none' | 'default_value' | 'error_branch'

// 代码输出变量
export interface CodeOutputVariable {
  id: string
  name: string                   // 变量名
  type: OutputVariableType       // 变量类型
}

// 重试配置
export interface RetryConfig {
  enabled: boolean               // 是否启用重试
  maxRetries: number             // 最大重试次数
  retryInterval: number          // 重试间隔（毫秒）
}

// 异常处理配置
export interface ErrorHandlingConfig {
  type: ErrorHandlingType        // 异常处理类型
  defaultValue?: string          // 默认值（当 type 为 default_value 时）
}

// 代码节点配置
export interface CodeConfig {
  language: CodeLanguage         // 代码语言
  code: string                   // 代码内容
  inputs: CodeInput[]            // 输入变量映射
  outputs: CodeOutputVariable[]  // 输出变量列表
  outputVariable: string         // 主输出变量名（兼容旧版）
  retry: RetryConfig             // 重试配置
  errorHandling: ErrorHandlingConfig  // 异常处理配置
}

// 代码输入变量
export interface CodeInput {
  id: string
  name: string                   // 变量名（在代码中使用）
  value: string                  // 变量值（引用上游变量，如 {{query}}）
  valueSource?: string           // 变量来源节点
}

// 默认重试配置
export const defaultRetryConfig: RetryConfig = {
  enabled: false,
  maxRetries: 3,
  retryInterval: 1000,
}

// 默认异常处理配置
export const defaultErrorHandlingConfig: ErrorHandlingConfig = {
  type: 'none',
  defaultValue: '',
}

// 默认代码配置
export const defaultCodeConfig: CodeConfig = {
  language: 'python',
  code: `def main(inputs: dict) -> dict:
    # 在这里编写你的代码
    # inputs 包含所有输入变量
    # 返回一个字典作为输出
    
    result = inputs.get("input", "")
    
    return {
        "output": result
    }`,
  inputs: [],
  outputs: [{ id: 'default', name: 'result', type: 'string' }],
  outputVariable: 'result',
  retry: defaultRetryConfig,
  errorHandling: defaultErrorHandlingConfig,
}

// Python 示例代码
export const pythonTemplate = `def main(inputs: dict) -> dict:
    # 在这里编写你的代码
    # inputs 包含所有输入变量
    # 返回一个字典作为输出
    
    result = inputs.get("input", "")
    
    return {
        "output": result
    }`

// JavaScript 示例代码
export const javascriptTemplate = `function main(inputs) {
    // 在这里编写你的代码
    // inputs 包含所有输入变量
    // 返回一个对象作为输出
    
    const result = inputs.input || "";
    
    return {
        output: result
    };
}`

interface CodeNodeData {
  type: string
  label: string
  codeConfig?: CodeConfig
  config: Record<string, unknown>
}

interface CodeNodeProps {
  id: string
  selected?: boolean
  data: CodeNodeData
}

export function CodeNode({ id, selected, data }: CodeNodeProps) {
  // 检查是否启用了异常分支
  const hasErrorBranch = data.codeConfig?.errorHandling?.type === 'error_branch'

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">代码执行</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      {/* Node Card */}
      <div
        className={cn(
          'relative flex flex-col rounded-xl border bg-card shadow-sm transition-all',
          'min-w-[180px] max-w-[240px]',
          selected 
            ? 'border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0"
          style={{ top: hasErrorBranch ? 22 : '50%' }}
        />

        {/* Main Content */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-white">
            <Code className="h-3.5 w-3.5" />
          </div>
          
          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || '代码执行'}
          </span>
        </div>

        {/* Error Branch Row - 只在启用异常分支时显示 */}
        {hasErrorBranch && (
          <div className="flex items-center justify-between px-2.5 pb-2 pt-0.5">
            <span className="text-xs text-muted-foreground">异常时</span>
            <span className="text-xs text-orange-500 font-medium">异常分支</span>
          </div>
        )}

        {/* Normal Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          id="output"
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0"
          style={{ top: hasErrorBranch ? 22 : '50%' }}
        />

        {/* Error Branch Handle - 只在启用异常分支时显示 */}
        {hasErrorBranch && (
          <Handle
            type="source"
            position={Position.Right}
            id="error"
            className="!w-2 !h-2 !rounded-full !bg-orange-500 !border-0"
            style={{ top: 56 }}
          />
        )}
      </div>
    </div>
  )
}

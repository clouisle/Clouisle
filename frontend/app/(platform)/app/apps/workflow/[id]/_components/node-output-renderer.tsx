import * as React from 'react'
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  SkipForward,
} from 'lucide-react'
import { cn } from '@/lib/utils'

// 节点执行追踪数据
export interface NodeTrace {
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

// 节点状态配置
export const nodeStatusConfig: Record<string, { icon: React.ElementType; className: string }> = {
  pending: { icon: Clock, className: 'text-gray-400' },
  running: { icon: Loader2, className: 'text-blue-500 animate-spin' },
  success: { icon: CheckCircle2, className: 'text-green-500' },
  failed: { icon: XCircle, className: 'text-red-500' },
  skipped: { icon: SkipForward, className: 'text-gray-400' },
}

// 节点输出渲染函数
export function renderNodeOutput(
  nodeType: string,
  outputs: Record<string, unknown>,
  t: (key: string) => string
): React.ReactNode {
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

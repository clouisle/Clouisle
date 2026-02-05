'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Tags, MoreHorizontal, Play, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'

// 分类类别定义
export interface ClassifierCategory {
  id: string
  name: string           // 类别名称
  description: string    // 类别描述（帮助 LLM 理解）
}

// 问题分类器配置
export interface QuestionClassifierConfig {
  // 源变量（问题文本）
  sourceVariable: string
  sourceNodeLabel?: string
  // 模型配置
  modelId?: string
  modelName?: string
  // 分类指令
  instruction?: string   // 额外的分类指令
  // 类别列表
  categories: ClassifierCategory[]
}

// 默认配置
export const defaultQuestionClassifierConfig: QuestionClassifierConfig = {
  sourceVariable: '',
  sourceNodeLabel: '',
  modelId: '',
  modelName: '',
  instruction: '',
  categories: [],
}

interface QuestionClassifierNodeData {
  type: string
  label: string
  questionClassifierConfig?: QuestionClassifierConfig
  config: Record<string, unknown>
}

interface QuestionClassifierNodeProps {
  id: string
  selected?: boolean
  data: QuestionClassifierNodeData
}

export function QuestionClassifierNode({ id, selected, data }: QuestionClassifierNodeProps) {
  const config = data.questionClassifierConfig || defaultQuestionClassifierConfig
  const categories = config.categories || []
  const hasModel = !!config.modelId

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">问题分类</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background" title="调试运行">
            <Play className="h-3 w-3 text-muted-foreground" />
          </button>
          <button className="p-1 rounded hover:bg-background">
            <MoreHorizontal className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
      
      {/* Node Card */}
      <div
        className={cn(
          'relative flex flex-col rounded-xl border bg-card shadow-sm transition-all',
          'min-w-44 max-w-56',
          selected 
            ? 'border-primary' 
            : 'border-border hover:border-primary/50'
        )}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-violet-500 text-white">
            <Tags className="h-3.5 w-3.5" />
          </div>
          
          {/* Label & Model */}
          <div className="flex-1 min-w-0">
            <span className="block text-sm font-medium truncate">
              {data.label || '问题分类'}
            </span>
            {hasModel ? (
              <div className="flex items-center gap-1 mt-0.5">
                <Sparkles className="h-3 w-3 text-violet-500" />
                <span className="text-xs text-muted-foreground truncate">{config.modelName}</span>
              </div>
            ) : (
              <span className="text-xs text-amber-500">未选择模型</span>
            )}
          </div>
        </div>

        {/* Categories List */}
        <div className="px-2.5 pb-2 pt-0.5 flex flex-col gap-1">
          {categories.length > 0 ? (
            categories.map((category, index) => (
              <div 
                key={category.id}
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 bg-violet-500/10"
              >
                <span className="text-[10px] text-violet-500 font-medium shrink-0">
                  {index + 1}
                </span>
                <span className="text-[11px] text-foreground/80 font-medium truncate flex-1">
                  {category.name || '(未命名)'}
                </span>
              </div>
            ))
          ) : (
            <div className="flex items-center justify-center py-2 text-[11px] text-muted-foreground">
              点击添加分类
            </div>
          )}
        </div>

        {/* Category Handles - 每个类别对应一个输出分支 */}
        {categories.map((category, index) => {
          // 计算位置：header(44px) + padding(8px) + 每个类别的位置
          const top = 44 + 8 + index * 28 + 14 // 28px 每个类别，14px 居中
          
          return (
            <Handle
              key={category.id}
              type="source"
              position={Position.Right}
              id={category.id}
              className="!w-2 !h-2 !rounded-full !bg-violet-500 !border-0 transition-transform group-hover:scale-150"
              style={{ top }}
            />
          )
        })}
        
        {/* 如果没有类别，显示一个默认的输出 Handle */}
        {categories.length === 0 && (
          <Handle
            type="source"
            position={Position.Right}
            className="!w-2 !h-2 !rounded-full !bg-primary !border-0 transition-transform group-hover:scale-150"
            style={{ top: 50 }}
          />
        )}
      </div>
    </div>
  )
}

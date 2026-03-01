'use client'

import * as React from 'react'
import { Handle, Position } from '@xyflow/react'
import { Database, MoreHorizontal, AlertCircle, Play } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { cn } from '@/lib/utils'
import type { KnowledgeRetrievalNodeConfig } from '../node-config/configs/knowledge-retrieval-node-config'

interface KnowledgeRetrievalNodeData {
  type: string
  label: string
  config: Record<string, unknown>
  knowledgeRetrievalConfig?: KnowledgeRetrievalNodeConfig
}

interface KnowledgeRetrievalNodeProps {
  id: string
  selected?: boolean
  data: KnowledgeRetrievalNodeData
}

export function KnowledgeRetrievalNode({ selected, data }: KnowledgeRetrievalNodeProps) {
  const t = useTranslations('workflow')

  const config = data.knowledgeRetrievalConfig
  const hasKnowledgeBase = !!config?.knowledgeBaseId
  const hasQuery = config?.querySource === 'variable'
    ? !!config?.queryVariableRef
    : !!config?.queryConstantValue

  return (
    <div className="group relative">
      {/* Node Label */}
      <div className="flex items-center justify-between mb-2 px-1 h-5">
        <span className="text-xs text-muted-foreground">{t('nodeLabels.knowledge_retrieval')}</span>
        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity bg-muted rounded-lg px-1 py-0.5">
          <button className="p-1 rounded hover:bg-background" title={t('nodesCommon.debugRun')}>
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
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />

        {/* Header */}
        <div className="flex items-center gap-2 px-2.5 py-2">
          {/* Icon */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-purple-500 text-white">
            <Database className="h-3.5 w-3.5" />
          </div>

          {/* Label */}
          <span className="flex-1 text-sm font-medium truncate">
            {data.label || t('nodeLabels.knowledge_retrieval')}
          </span>

          {/* Warning if not configured */}
          {(!hasKnowledgeBase || !hasQuery) && (
            <AlertCircle className="h-4 w-4 text-amber-500" />
          )}
        </div>

        {/* Knowledge Base Info */}
        {hasKnowledgeBase && config ? (
          <div className="px-2.5 pb-2 pt-0.5">
            {/* 知识库名称 */}
            <p className="text-[11px] font-medium text-purple-600 dark:text-purple-400 truncate mb-0.5">
              {config.knowledgeBaseName}
            </p>

            {/* 检索模式 */}
            <div className="flex items-center gap-1.5 text-[10px] mb-1">
              <span className="text-muted-foreground">{t('configKnowledgeRetrieval.searchMode')}:</span>
              <span className="text-purple-600 dark:text-purple-400">
                {config.searchMode === 'vector' && t('configKnowledgeRetrieval.searchModeVector')}
                {config.searchMode === 'fulltext' && t('configKnowledgeRetrieval.searchModeFulltext')}
                {config.searchMode === 'hybrid' && t('configKnowledgeRetrieval.searchModeHybrid')}
              </span>
            </div>

            {/* 配置参数 */}
            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
              <span>Top {config.topK}</span>
              <span>•</span>
              <span>{t('configKnowledgeRetrieval.threshold')}: {config.threshold.toFixed(1)}</span>
            </div>
          </div>
        ) : (
          /* Empty State */
          <div className="px-2.5 pb-2 pt-0.5">
            <p className="text-[10px] text-muted-foreground">
              {t('nodesKnowledgeRetrieval.clickToConfigure')}
            </p>
          </div>
        )}

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          className="w-2! h-2! rounded-full! bg-primary! border-0! transition-transform group-hover:scale-150"
          style={{ top: 24 }}
        />
      </div>
    </div>
  )
}

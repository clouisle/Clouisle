import * as React from 'react'
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  SkipForward,
} from 'lucide-react'
import { ImageLightbox, VideoLightbox, useLightbox } from '@/components/chat/image-lightbox'
import { cn } from '@/lib/utils'
import { getImageAssetUrl, getVideoAssetUrl, isMediaImageToolResult, isMediaVideoToolResult } from '@/lib/utils/tool-result'

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

function MediaPreview({ imageUrls = [], videoUrl }: { imageUrls?: string[]; videoUrl?: string | null }) {
  const imageLightbox = useLightbox()
  const [videoLightboxOpen, setVideoLightboxOpen] = React.useState(false)

  return (
    <>
      {imageUrls.length > 0 && (
        <div className={cn('grid gap-2', imageUrls.length > 1 && 'sm:grid-cols-2')}>
          {imageUrls.map((url, index) => (
            <button
              key={`${url}-${index}`}
              type="button"
              className="flex aspect-video items-center justify-center overflow-hidden rounded-lg border bg-muted/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              onClick={() => imageLightbox.openLightbox(url)}
            >
              <img
                src={url}
                alt={`generated media ${index + 1}`}
                className="h-full w-full object-contain"
              />
            </button>
          ))}
        </div>
      )}
      {videoUrl && (
        <button
          type="button"
          className="flex aspect-video w-full items-center justify-center overflow-hidden rounded-lg border bg-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          onClick={() => setVideoLightboxOpen(true)}
        >
          <video src={videoUrl} muted playsInline preload="metadata" className="h-full w-full object-contain" />
        </button>
      )}
      <ImageLightbox
        src={imageLightbox.imageSrc}
        alt={imageLightbox.imageAlt}
        isOpen={imageLightbox.isOpen}
        onClose={imageLightbox.closeLightbox}
      />
      {videoUrl && (
        <VideoLightbox
          src={videoUrl}
          isOpen={videoLightboxOpen}
          onClose={() => setVideoLightboxOpen(false)}
        />
      )}
    </>
  )
}

// 节点输出渲染函数
export function renderNodeOutput(
  nodeType: string,
  outputs: Record<string, unknown>,
  t: (key: string) => string,
  renderText?: (text: string) => React.ReactNode
): React.ReactNode {
  // LLM 节点 - 显示文本内容
  if (nodeType === 'llm') {
    const text = outputs.text || outputs.content || outputs.response || ''
    if (typeof text === 'string' && text) {
      return (
        <div className="max-h-40 min-w-0 overflow-y-auto break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-sm">
          {renderText ? renderText(text) : text}
        </div>
      )
    }
  }
  if (nodeType === 'agent') {
    const response = typeof outputs.response === 'string' ? outputs.response : ''
    const detailEntries = [
      ['dialogue', outputs.dialogue],
      ['artifacts', outputs.artifacts],
      ['toolCalls', outputs.toolCalls],
      ['usage', outputs.usage],
    ] as Array<[string, unknown]>
    const visibleDetailEntries = detailEntries.filter(([, value]) => value !== undefined && value !== null)
    return (
      <div className="space-y-2">
        {response && (
          <div className="max-h-40 min-w-0 overflow-y-auto break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-sm">
            {renderText ? renderText(response) : response}
          </div>
        )}
        {visibleDetailEntries.map(([key, value]) => (
          <div key={key} className="space-y-1">
            <span className="text-[10px] font-mono text-muted-foreground">{key}</span>
            <pre className="max-h-40 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-[10px] font-mono">
              {JSON.stringify(value, null, 2)}
            </pre>
          </div>
        ))}
      </div>
    )
  }


  if (nodeType === 'media_generation') {
    const result = outputs.result || outputs.output
    if (Array.isArray(result) && result.every(url => typeof url === 'string')) {
      return <MediaPreview imageUrls={result} />
    }
    if (typeof result === 'string' && result) {
      return <MediaPreview videoUrl={result} />
    }
    if (isMediaImageToolResult(result)) {
      return (
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">{t('runDrawer.result')}</div>
          <MediaPreview
            imageUrls={result.images
              .map(item => getImageAssetUrl(item.image))
              .filter((url): url is string => !!url)}
          />
        </div>
      )
    }
    if (isMediaVideoToolResult(result)) {
      return (
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">{t('runDrawer.result')}</div>
          <MediaPreview videoUrl={getVideoAssetUrl(result.video)} />
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
              <div className="max-h-32 min-w-0 overflow-y-auto break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-sm">
                {renderText ? renderText(value) : value}
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
            <pre className="max-h-32 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-[10px] font-mono">
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
            {t('runDrawer.handle')} {String(matchedHandle)}
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
          <pre className="max-h-32 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-[10px]">
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
      <pre className="max-h-32 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-[10px]">
        {typeof result === 'string' ? result : JSON.stringify(outputs, null, 2)}
      </pre>
    )
  }

  // 默认 - JSON 格式显示
  return (
    <pre className="max-h-32 min-w-0 max-w-full overflow-auto whitespace-pre-wrap break-words [overflow-wrap:anywhere] rounded bg-background p-2 text-[10px]">
      {JSON.stringify(outputs, null, 2)}
    </pre>
  )
}

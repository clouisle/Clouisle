'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useTranslations } from 'next-intl'
import { useRouter } from 'next/navigation'
import { useTheme } from 'next-themes'
import {
  ArrowLeft,
  Search,
  FileText,
  Loader2,
  Send,
  Settings2,
  ChevronDown,
  ChevronUp,
  Zap,
  FileSearch,
  Sparkles,
} from 'lucide-react'
import { knowledgeBasesApi, type KnowledgeBase, type SearchResult, type SearchMode } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  ToggleGroup,
  ToggleGroupItem,
} from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'
import { API_BASE_URL } from '@/lib/constants'

interface SearchTestClientProps {
  knowledgeBaseId: string
}

const MDPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), { ssr: false })

function resolveMediaUrl(src: string): string {
  if (src.startsWith('/api/v1/')) {
    return `${API_BASE_URL.replace(/\/api\/v1\/?$/, '')}${src}`
  }
  return src
}

function AuthenticatedMarkdownImage({ src = '', alt = '' }: { src?: string, alt?: string }) {
  const [objectUrl, setObjectUrl] = React.useState<string | null>(null)
  const [failed, setFailed] = React.useState(false)

  React.useEffect(() => {
    setFailed(false)
    if (!src) {
      setObjectUrl(null)
      return
    }
    if (src.startsWith('data:') || src.startsWith('javascript:')) {
      setObjectUrl(null)
      setFailed(true)
      return
    }
    if (!src.startsWith('/api/v1/knowledge-bases/')) {
      setObjectUrl(src)
      return
    }

    setObjectUrl(null)
    const controller = new AbortController()
    const token = localStorage.getItem('access_token')
    const headers = token ? { Authorization: `Bearer ${token}` } : undefined
    let currentObjectUrl: string | null = null

    fetch(resolveMediaUrl(src), { headers, signal: controller.signal })
      .then(response => {
        if (!response.ok) throw new Error('image_load_failed')
        return response.blob()
      })
      .then(blob => {
        currentObjectUrl = URL.createObjectURL(blob)
        setObjectUrl(currentObjectUrl)
      })
      .catch(error => {
        if ((error as Error).name !== 'AbortError') setFailed(true)
      })

    return () => {
      controller.abort()
      if (currentObjectUrl) URL.revokeObjectURL(currentObjectUrl)
    }
  }, [src])

  if (failed || !objectUrl) {
    return <span className="text-muted-foreground">{alt || src}</span>
  }

  return <img src={objectUrl} alt={alt} loading="lazy" />
}

export function SearchTestClient({ knowledgeBaseId }: SearchTestClientProps) {
  const t = useTranslations('knowledgeBases')
  const router = useRouter()
  const { resolvedTheme } = useTheme()
  
  // 知识库信息
  const [knowledgeBase, setKnowledgeBase] = React.useState<KnowledgeBase | null>(null)
  const [isLoadingKb, setIsLoadingKb] = React.useState(true)
  const [mounted, setMounted] = React.useState(false)
  
  // 搜索状态
  const [query, setQuery] = React.useState('')
  const [results, setResults] = React.useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = React.useState(false)
  const [hasSearched, setHasSearched] = React.useState(false)
  
  // 搜索参数
  const [searchMode, setSearchMode] = React.useState<SearchMode>('hybrid')
  const [topK, setTopK] = React.useState(5)
  const [thresholdInput, setThresholdInput] = React.useState('0')
  const [rerankEnabled, setRerankEnabled] = React.useState(true)
  const [rerankCandidateK, setRerankCandidateK] = React.useState(10)
  const [rerankFailOpen, setRerankFailOpen] = React.useState(true)
  const [rerankThresholdInput, setRerankThresholdInput] = React.useState('')
  const [showSettings, setShowSettings] = React.useState(false)
  
  // 展开的结果
  const [expandedResults, setExpandedResults] = React.useState<Set<string>>(new Set())

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const colorMode = mounted ? (resolvedTheme === 'dark' ? 'dark' : 'light') : 'light'

  // 加载知识库信息
  React.useEffect(() => {
    const loadKnowledgeBase = async () => {
      try {
        const kb = await knowledgeBasesApi.getKnowledgeBase(knowledgeBaseId)
        setKnowledgeBase(kb)
        setRerankEnabled(kb.settings?.rerank_enabled ?? true)
        setRerankCandidateK(kb.settings?.rerank_candidate_k ?? 10)
        setRerankFailOpen(kb.settings?.rerank_fail_open ?? true)
        setRerankThresholdInput(
          kb.settings?.rerank_score_threshold?.toString() || ''
        )
      } catch {
        router.push('/app/kb')
      } finally {
        setIsLoadingKb(false)
      }
    }
    loadKnowledgeBase()
  }, [knowledgeBaseId, router])

  const hasRerankModel = !!knowledgeBase?.rerank_model
  
  // 执行搜索
  const handleSearch = async () => {
    if (!query.trim()) return
    
    setIsSearching(true)
    setHasSearched(true)
    setExpandedResults(new Set()) // 重置展开状态
    try {
      const response = await knowledgeBasesApi.search(knowledgeBaseId, {
        query: query.trim(),
        search_mode: searchMode,
        top_k: topK,
        threshold: parseFloat(thresholdInput) || 0,
        rerank_enabled: hasRerankModel ? rerankEnabled : false,
        rerank_candidate_k: hasRerankModel && rerankEnabled ? rerankCandidateK : undefined,
        rerank_fail_open: hasRerankModel && rerankEnabled ? rerankFailOpen : undefined,
        rerank_score_threshold: hasRerankModel && rerankEnabled
          ? (rerankThresholdInput === '' ? null : parseFloat(rerankThresholdInput) || 0)
          : undefined,
      })
      setResults(response.results)
      // 默认展开第一个结果
      if (response.results.length > 0) {
        setExpandedResults(new Set([response.results[0].chunk_id]))
      }
    } catch {
      setResults([])
    } finally {
      setIsSearching(false)
    }
  }
  
  // 回车搜索
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // 中文输入法组合状态下不触发
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSearch()
    }
  }
  
  // 切换结果展开
  const toggleExpanded = (chunkId: string) => {
    setExpandedResults(prev => {
      const next = new Set(prev)
      if (next.has(chunkId)) {
        next.delete(chunkId)
      } else {
        next.add(chunkId)
      }
      return next
    })
  }
  
  // 格式化相似度分数
  const formatScore = (score: number) => {
    return (score * 100).toFixed(1) + '%'
  }
  
  // 获取分数颜色
  const getScoreColor = (score: number) => {
    if (score >= 0.8) return 'text-emerald-500'
    if (score >= 0.6) return 'text-blue-500'
    if (score >= 0.4) return 'text-amber-500'
    return 'text-muted-foreground'
  }
  
  if (isLoadingKb) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }
  
  return (
    <div className="flex flex-col px-8" style={{ height: 'calc(100vh - 56px)' }}>
      {/* 页头 */}
      <div className="flex-none flex items-center gap-3 py-3">
        <Button 
          variant="ghost" 
          size="icon" 
          className="h-8 w-8"
          onClick={() => router.push(`/app/kb/${knowledgeBaseId}`)}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="text-lg font-semibold">{t('searchTest')}</h1>
          <p className="text-xs text-muted-foreground">
            {knowledgeBase?.name}
          </p>
        </div>
      </div>
      
      {/* 搜索结果区域 - 可滚动 */}
      <div className="flex-1 min-h-0 overflow-auto px-4 pb-4">
        {!hasSearched ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Search className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <h3 className="text-base font-medium text-muted-foreground">
              {t('searchTestHint')}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              {t('searchTestDescription')}
            </p>
          </div>
        ) : isSearching ? (
          <div className="flex h-full flex-col items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground mb-3" />
            <p className="text-sm text-muted-foreground">{t('searching')}</p>
          </div>
        ) : results.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <FileText className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <h3 className="text-base font-medium text-muted-foreground">
              {t('noResults')}
            </h3>
            <p className="text-xs text-muted-foreground mt-1">
              {t('noResultsHint')}
            </p>
          </div>
        ) : (
          <div className="space-y-2 max-w-3xl mx-auto">
            <p className="text-xs text-muted-foreground mb-3">
              {t('searchResultsCount', { count: results.length })}
            </p>
            
            {results.map((result, index) => {
              const isExpanded = expandedResults.has(result.chunk_id)
              return (
                <Card 
                  key={result.chunk_id} 
                  className={cn(
                    "overflow-hidden transition-all cursor-pointer hover:shadow-sm",
                    isExpanded && "ring-1 ring-primary/20"
                  )}
                  onClick={() => toggleExpanded(result.chunk_id)}
                >
                  <CardHeader className="py-2 px-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <Badge variant="outline" className="shrink-0 text-[10px] h-5 px-1.5">
                          #{index + 1}
                        </Badge>
                        <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-xs font-medium truncate">
                          {result.document_name}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Badge 
                          variant="secondary" 
                          className={cn("text-[10px] h-5 px-1.5", getScoreColor(result.score))}
                        >
                          {formatScore(result.score)}
                        </Badge>
                        {isExpanded ? (
                          <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                        )}
                      </div>
                    </div>
                    {/* 折叠时显示预览 */}
                    {!isExpanded && (
                      <div className="mt-1.5 space-y-1">
                        <p className="text-xs text-muted-foreground line-clamp-2">
                          {result.content}
                        </p>
                        {(result.original_score !== undefined || result.rerank_score !== undefined) && (
                          <div className="flex items-center gap-3 text-[10px] text-muted-foreground">
                            {result.original_score !== undefined && (
                              <span>{t('originalScore')}: {formatScore(result.original_score)}</span>
                            )}
                            {result.rerank_score !== undefined && (
                              <span>{t('rerankScore')}: {formatScore(result.rerank_score)}</span>
                            )}
                          </div>
                        )}
                      </div>
                    )}
                  </CardHeader>
                  {/* 展开时显示完整内容 */}
                  {isExpanded && (
                    <CardContent className="pt-0 px-3 pb-3">
                      {(result.original_score !== undefined || result.rerank_score !== undefined) && (
                        <div className="mb-2 flex items-center gap-3 text-[10px] text-muted-foreground">
                          {result.original_score !== undefined && (
                            <span>{t('originalScore')}: {formatScore(result.original_score)}</span>
                          )}
                          {result.rerank_score !== undefined && (
                            <span>{t('rerankScore')}: {formatScore(result.rerank_score)}</span>
                          )}
                        </div>
                      )}
                      <div className="rounded bg-muted/50 p-3" data-color-mode={colorMode}>
                        <div className="wmde-markdown text-xs leading-relaxed [&_img]:max-h-80 [&_img]:rounded-md [&_img]:border [&_img]:object-contain">
                          <MDPreview
                            source={result.content}
                            components={{
                              img: ({ src, alt }) => (
                                <AuthenticatedMarkdownImage
                                  src={typeof src === 'string' ? src : undefined}
                                  alt={alt}
                                />
                              ),
                            }}
                          />
                        </div>
                      </div>
                      {result.rerank_reason && (
                        <p className="mt-2 text-[11px] text-muted-foreground">
                          {t('rerankReason')}: {result.rerank_reason}
                        </p>
                      )}
                    </CardContent>
                  )}
                </Card>
              )
            })}
          </div>
        )}
      </div>
      
      {/* 底部搜索输入区 */}
      <div className="sticky bottom-0 px-4 py-4">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-center gap-2 rounded-full border bg-background shadow-sm px-3 py-1.5">
            {/* 搜索输入框 */}
            <div className="relative flex-1">
              <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t('searchPlaceholder')}
                className="pl-8 pr-3 h-9 text-sm border-0 shadow-none focus-visible:ring-0"
                disabled={isSearching}
              />
            </div>
            
            {/* 高级设置按钮 */}
            <Popover open={showSettings} onOpenChange={setShowSettings}>
              <PopoverTrigger
                render={
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0 shrink-0">
                    <Settings2 className="h-3.5 w-3.5" />
                  </Button>
                }
              />
              <PopoverContent className="w-72" align="end">
                <div className="grid gap-3">
                  {/* 搜索模式切换 */}
                  <div className="space-y-1.5">
                    <Label className="text-xs font-medium">
                      {t('searchMode')}
                    </Label>
                    <ToggleGroup 
                      type="single" 
                      value={searchMode} 
                      onValueChange={(v: string) => v && setSearchMode(v as SearchMode)}
                      size="sm"
                      className="w-full justify-start"
                    >
                      <ToggleGroupItem value="hybrid" aria-label={t('hybridSearch')} className="gap-1 text-xs px-2 h-8">
                        <Zap className="h-3 w-3" />
                        {t('hybridSearch')}
                      </ToggleGroupItem>
                      <ToggleGroupItem value="vector" aria-label={t('vectorSearch')} className="gap-1 text-xs px-2 h-8">
                        <Sparkles className="h-3 w-3" />
                        {t('vectorSearch')}
                      </ToggleGroupItem>
                      <ToggleGroupItem value="fulltext" aria-label={t('fulltextSearch')} className="gap-1 text-xs px-2 h-8">
                        <FileSearch className="h-3 w-3" />
                        {t('fulltextSearch')}
                      </ToggleGroupItem>
                    </ToggleGroup>
                  </div>
                  
                  <div className="space-y-1.5">
                    <Label htmlFor="topK" className="text-xs font-medium">
                      {t('topK')}
                    </Label>
                    <Input
                      id="topK"
                      type="number"
                      min={1}
                      max={20}
                      value={topK}
                      onChange={(e) => setTopK(Math.min(20, Math.max(1, Number(e.target.value) || 1)))}
                      className="h-8"
                    />
                  </div>
                  
                  <div className="space-y-1.5">
                    <Label htmlFor="threshold" className="text-xs font-medium">
                      {t('threshold')}
                    </Label>
                    <Input
                      id="threshold"
                      type="text"
                      inputMode="decimal"
                      value={thresholdInput}
                      onChange={(e) => {
                        const val = e.target.value
                        // 允许输入空字符串、数字和小数点
                        if (val === '' || /^\d*\.?\d*$/.test(val)) {
                          const num = parseFloat(val)
                          if (val === '' || (num >= 0 && num <= 1)) {
                            setThresholdInput(val)
                          }
                        }
                      }}
                      onBlur={() => {
                        // 失去焦点时规范化值
                        const num = parseFloat(thresholdInput) || 0
                        setThresholdInput(String(Math.min(1, Math.max(0, num))))
                      }}
                      className="h-8"
                      placeholder="0 - 1"
                    />
                  </div>

                  <div className="border-t pt-3 space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs font-medium">{t('rerankModel')}</Label>
                      {knowledgeBase?.rerank_model ? (
                        <div className="rounded-md border px-2.5 py-2 text-xs">
                          <div className="font-medium">{knowledgeBase.rerank_model.name}</div>
                          <div className="text-muted-foreground">
                            {knowledgeBase.rerank_model.provider}
                          </div>
                        </div>
                      ) : (
                        <p className="text-xs text-muted-foreground">
                          {t('rerankNotConfigured')}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center justify-between gap-3 rounded-md border px-2.5 py-2">
                      <div className="space-y-0.5">
                        <Label htmlFor="rerankEnabled" className="text-xs font-medium">
                          {t('rerankEnabled')}
                        </Label>
                        <p className="text-[11px] text-muted-foreground">
                          {t('rerankEnabledHint')}
                        </p>
                      </div>
                      <Switch
                        id="rerankEnabled"
                        checked={hasRerankModel && rerankEnabled}
                        onCheckedChange={setRerankEnabled}
                        disabled={!hasRerankModel}
                      />
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="rerankCandidateK" className="text-xs font-medium">
                        {t('rerankCandidateK')}
                      </Label>
                      <Input
                        id="rerankCandidateK"
                        type="number"
                        min={1}
                        max={100}
                        value={rerankCandidateK}
                        onChange={(e) =>
                          setRerankCandidateK(
                            Math.min(100, Math.max(topK, Number(e.target.value) || topK))
                          )
                        }
                        className="h-8"
                        disabled={!hasRerankModel || !rerankEnabled}
                      />
                      <p className="text-[11px] text-muted-foreground">
                        {t('rerankCandidateKHint')}
                      </p>
                    </div>

                    <div className="space-y-1.5">
                      <Label htmlFor="rerankThreshold" className="text-xs font-medium">
                        {t('rerankScoreThreshold')}
                      </Label>
                      <Input
                        id="rerankThreshold"
                        type="text"
                        inputMode="decimal"
                        value={rerankThresholdInput}
                        onChange={(e) => {
                          const val = e.target.value
                          if (val === '' || /^\d*\.?\d*$/.test(val)) {
                            const num = parseFloat(val)
                            if (val === '' || (num >= 0 && num <= 1)) {
                              setRerankThresholdInput(val)
                            }
                          }
                        }}
                        onBlur={() => {
                          if (rerankThresholdInput === '') return
                          const num = parseFloat(rerankThresholdInput) || 0
                          setRerankThresholdInput(
                            String(Math.min(1, Math.max(0, num)))
                          )
                        }}
                        className="h-8"
                        placeholder={t('rerankScoreThresholdPlaceholder')}
                        disabled={!hasRerankModel || !rerankEnabled}
                      />
                      <p className="text-[11px] text-muted-foreground">
                        {t('rerankScoreThresholdHint')}
                      </p>
                    </div>

                    <div className="flex items-center justify-between gap-3 rounded-md border px-2.5 py-2">
                      <div className="space-y-0.5">
                        <Label htmlFor="rerankFailOpen" className="text-xs font-medium">
                          {t('rerankFailOpen')}
                        </Label>
                        <p className="text-[11px] text-muted-foreground">
                          {t('rerankFailOpenHint')}
                        </p>
                      </div>
                      <Switch
                        id="rerankFailOpen"
                        checked={rerankFailOpen}
                        onCheckedChange={setRerankFailOpen}
                        disabled={!hasRerankModel || !rerankEnabled}
                      />
                    </div>
                  </div>
                </div>
              </PopoverContent>
            </Popover>
            
            {/* 搜索按钮 */}
            <Button 
              onClick={handleSearch} 
              disabled={!query.trim() || isSearching}
              size="icon"
              className="h-8 w-8 shrink-0 rounded-full"
            >
              {isSearching ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

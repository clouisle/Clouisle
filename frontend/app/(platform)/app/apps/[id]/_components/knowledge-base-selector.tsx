'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import {
  Database,
  Plus,
  Settings2,
  Trash2,
} from 'lucide-react'
import { type KnowledgeBase, type AgentKnowledgeBaseConfig } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'

interface AddKnowledgeBaseButtonProps {
  knowledgeBases: KnowledgeBase[]
  selectedIds: string[]
  onAdd: (kb: KnowledgeBase) => void
}

export function AddKnowledgeBaseButton({ knowledgeBases, selectedIds, onAdd }: AddKnowledgeBaseButtonProps) {
  const t = useTranslations('agents.orchestration.knowledgeBase')
  const [open, setOpen] = React.useState(false)
  const availableKbs = knowledgeBases.filter(kb => !selectedIds.includes(kb.id))

  if (availableKbs.length === 0) {
    return (
      <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 cursor-not-allowed" disabled>
        <Plus className="h-3 w-3" />
        {t('add')}
      </Button>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="sm" className="h-7 text-xs gap-1 cursor-pointer">
            <Plus className="h-3 w-3" />
            {t('add')}
          </Button>
        }
      />
      <PopoverContent className="w-64 p-1" align="end">
        <div className="max-h-64 overflow-y-auto">
          {availableKbs.map((kb) => (
            <button
              key={kb.id}
              className="w-full flex items-center gap-2 px-2 py-2 rounded hover:bg-muted transition-colors text-left cursor-pointer"
              onClick={() => {
                onAdd(kb)
                setOpen(false)
              }}
            >
              <Database className="h-4 w-4 text-emerald-500 shrink-0" />
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate">{kb.name}</div>
                <div className="text-xs text-muted-foreground">
                  {t('documents', { count: kb.document_count })} · {t('chunks', { count: kb.total_chunks })}
                </div>
              </div>
            </button>
          ))}
        </div>
        {availableKbs.length === 0 && (
          <p className="text-xs text-muted-foreground px-2 py-3 text-center">
            {t('noAvailable')}
          </p>
        )}
      </PopoverContent>
    </Popover>
  )
}

interface KnowledgeBaseConfigDialogProps {
  item: { config: AgentKnowledgeBaseConfig; knowledgeBase: KnowledgeBase } | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSave: (config: { retrieval_top_k: number; score_threshold: number }) => void
}

function KnowledgeBaseConfigDialog({ item, open, onOpenChange, onSave }: KnowledgeBaseConfigDialogProps) {
  const t = useTranslations('agents.orchestration.knowledgeBase')
  const [topK, setTopK] = React.useState(item?.config.retrieval_top_k ?? 3)
  const [threshold, setThreshold] = React.useState(item?.config.score_threshold ?? 0.3)

  React.useEffect(() => {
    if (item) {
      setTopK(item.config.retrieval_top_k)
      setThreshold(item.config.score_threshold)
    }
  }, [item])

  const handleSave = () => {
    onSave({ retrieval_top_k: topK, score_threshold: threshold })
    onOpenChange(false)
  }

  if (!item) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Database className="h-4 w-4 text-emerald-500" />
            {item.knowledgeBase.name}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-6 py-4">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm">{t('dialog.topK')}</Label>
              <span className="text-sm font-mono text-muted-foreground">{topK}</span>
            </div>
            <Slider
              value={[topK]}
              onValueChange={(v) => setTopK(Array.isArray(v) ? v[0] : v)}
              min={1}
              max={10}
              step={1}
            />
            <p className="text-xs text-muted-foreground">
              {t('dialog.topKHint')}
            </p>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm">{t('dialog.threshold')}</Label>
              <span className="text-sm font-mono text-muted-foreground">{threshold.toFixed(2)}</span>
            </div>
            <Slider
              value={[threshold]}
              onValueChange={(v) => setThreshold(Array.isArray(v) ? v[0] : v)}
              min={0}
              max={1}
              step={0.05}
            />
            <p className="text-xs text-muted-foreground">
              {t('dialog.thresholdHint')}
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t('dialog.cancel')}</Button>
          <Button onClick={handleSave}>{t('dialog.save')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface KnowledgeBaseDisplayItemProps {
  item: { config: AgentKnowledgeBaseConfig; knowledgeBase: KnowledgeBase }
  onConfigure: () => void
  onDelete: () => void
}

function KnowledgeBaseDisplayItem({ item, onConfigure, onDelete }: KnowledgeBaseDisplayItemProps) {
  const t = useTranslations('agents.orchestration.knowledgeBase')
  const [isDeleteHover, setIsDeleteHover] = React.useState(false)

  return (
    <div className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border transition-colors group ${
      isDeleteHover ? 'bg-destructive/10 border-destructive/30' : 'bg-background hover:bg-muted/30'
    }`}>
      <Database className="h-4 w-4 text-emerald-500 shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-sm font-medium">{item.knowledgeBase.name}</span>
      </div>
      <div className="flex items-center gap-1.5">
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 cursor-pointer hover:bg-primary/10 hover:text-primary"
            onClick={(e) => {
              e.stopPropagation()
              onConfigure()
            }}
          >
            <Settings2 className="h-3 w-3 text-muted-foreground hover:text-primary" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 cursor-pointer hover:bg-destructive/10 hover:text-destructive"
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            onMouseEnter={() => setIsDeleteHover(true)}
            onMouseLeave={() => setIsDeleteHover(false)}
          >
            <Trash2 className="h-3 w-3 text-muted-foreground" />
          </Button>
        </div>
        <div className="flex items-center gap-1.5 group-hover:hidden">
          <span className="text-[10px] text-muted-foreground">Top {item.config.retrieval_top_k}</span>
          <Badge variant="outline" className="text-[10px] h-4 px-1.5 font-normal">
            {t('documents', { count: item.knowledgeBase.document_count })}
          </Badge>
        </div>
      </div>
    </div>
  )
}

interface KnowledgeBaseSelectorProps {
  configs: AgentKnowledgeBaseConfig[]
  availableKnowledgeBases: KnowledgeBase[]
  onChange: (configs: AgentKnowledgeBaseConfig[]) => void
}

// 内部用于显示的数据结构
interface DisplayKnowledgeBase {
  config: AgentKnowledgeBaseConfig
  knowledgeBase: KnowledgeBase
}

export function KnowledgeBaseSelector({ 
  configs, 
  availableKnowledgeBases, 
  onChange 
}: KnowledgeBaseSelectorProps) {
  const t = useTranslations('agents.orchestration.knowledgeBase')
  const [configuringId, setConfiguringId] = React.useState<string | null>(null)

  // 根据 configs 和 availableKnowledgeBases 构建显示数据
  const displayItems: DisplayKnowledgeBase[] = React.useMemo(() => {
    return configs
      .map(config => {
        const kb = availableKnowledgeBases.find(kb => kb.id === config.knowledge_base_id)
        if (!kb) return null
        return { config, knowledgeBase: kb }
      })
      .filter((item): item is DisplayKnowledgeBase => item !== null)
  }, [configs, availableKnowledgeBases])

  const configuringItem = configuringId 
    ? displayItems.find(item => item.knowledgeBase.id === configuringId) 
    : null

  const handleDelete = (kbId: string) => {
    onChange(configs.filter(c => c.knowledge_base_id !== kbId))
  }

  const handleConfigSave = (config: { retrieval_top_k: number; score_threshold: number }) => {
    if (!configuringId) return
    const newConfigs = configs.map(c => 
      c.knowledge_base_id === configuringId 
        ? { ...c, ...config }
        : c
    )
    onChange(newConfigs)
  }

  if (displayItems.length === 0) {
    return (
      <p className="text-xs text-muted-foreground py-2">
        {t('empty')}
      </p>
    )
  }

  return (
    <>
      <div className="space-y-2">
        {displayItems.map((item) => (
          <KnowledgeBaseDisplayItem
            key={item.knowledgeBase.id}
            item={item}
            onConfigure={() => setConfiguringId(item.knowledgeBase.id)}
            onDelete={() => handleDelete(item.knowledgeBase.id)}
          />
        ))}
      </div>
      {configuringItem && (
        <KnowledgeBaseConfigDialog
          item={configuringItem}
          open={true}
          onOpenChange={(open) => !open && setConfiguringId(null)}
          onSave={handleConfigSave}
        />
      )}
    </>
  )
}

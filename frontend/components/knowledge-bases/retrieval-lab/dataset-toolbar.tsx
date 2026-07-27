import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Plus, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import type { EvaluationDataset, EvaluationCaseInput } from '@/lib/api'
import type { RetrievalApi } from './shared'

interface DatasetToolbarProps {
  datasets: EvaluationDataset[]
  selectedDatasetId: string | null
  onSelectDataset: (id: string | null) => void
  onDatasetsChange: () => void
  api: RetrievalApi
  knowledgeBaseId: string
  canEvaluate: boolean
}

export function DatasetToolbar({
  datasets,
  selectedDatasetId,
  onSelectDataset,
  onDatasetsChange,
  api,
  knowledgeBaseId,
  canEvaluate,
}: DatasetToolbarProps) {
  const t = useTranslations('knowledgeBases')
  const [creating, setCreating] = React.useState(false)
  const [dialogOpen, setDialogOpen] = React.useState(false)
  const [newDatasetName, setNewDatasetName] = React.useState('')

  const handleCreate = async () => {
    const name = newDatasetName.trim()
    if (!name) return

    setCreating(true)
    try {
      const dataset = await api.createEvaluationDataset(knowledgeBaseId, { name })
      onSelectDataset(dataset.id)
      onDatasetsChange()
      setDialogOpen(false)
      setNewDatasetName('')
      toast.success(t('datasetCreated'))
    } catch {
      toast.error(t('datasetCreateFailed'))
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <Label className="text-xs text-muted-foreground">{t('targetDataset')}</Label>
        <Select
          value={selectedDatasetId ?? ''}
          onValueChange={value => onSelectDataset(value || null)}
          disabled={!canEvaluate}
        >
          <SelectTrigger className="mt-1">
            <SelectValue>{selectedDatasetId ? datasets.find(d => d.id === selectedDatasetId)?.name : t('selectDataset')}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {datasets.map(dataset => (
              <SelectItem key={dataset.id} value={dataset.id}>
                {dataset.name} ({dataset.cases.length} {t('cases')})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogTrigger
          render={
            <Button
              variant="outline"
              size="sm"
              className="mt-5"
              disabled={!canEvaluate}
            />
          }
        >
          <Plus className="h-4 w-4 mr-1" />
          {t('newDataset')}
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('createNewDataset')}</DialogTitle>
            <DialogDescription>{t('createDatasetDescription')}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="dataset-name">{t('datasetName')}</Label>
              <Input
                id="dataset-name"
                value={newDatasetName}
                onChange={e => setNewDatasetName(e.target.value)}
                placeholder={t('datasetNamePlaceholder')}
                className="mt-1"
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    void handleCreate()
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDialogOpen(false)
                setNewDatasetName('')
              }}
            >
              {t('cancel')}
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!newDatasetName.trim() || creating}
            >
              {creating && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              {t('create')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

interface PromotionToolbarProps {
  selectedDatasetId: string | null
  query: string
  chunkRelevance: Record<string, number>
  documentRelevance: Record<string, number>
  expectedEmpty: boolean
  onExpectedEmptyChange: (value: boolean) => void
  poolDepth: number
  poolStrategies: string[]
  candidateCount: number
  judgedCount: number
  api: RetrievalApi
  knowledgeBaseId: string
  canEvaluate: boolean
  onSuccess: () => void
}

export function PromotionToolbar({
  selectedDatasetId,
  query,
  chunkRelevance,
  documentRelevance,
  expectedEmpty,
  onExpectedEmptyChange,
  poolDepth,
  poolStrategies,
  candidateCount,
  judgedCount,
  api,
  knowledgeBaseId,
  canEvaluate,
  onSuccess,
}: PromotionToolbarProps) {
  const t = useTranslations('knowledgeBases')
  const [promoting, setPromoting] = React.useState(false)
  const [willCreate, setWillCreate] = React.useState(false)

  // Check if query exists in dataset
  React.useEffect(() => {
    if (!selectedDatasetId) {
      setWillCreate(false)
      return
    }

    api.getEvaluationDataset(knowledgeBaseId, selectedDatasetId)
      .then(dataset => {
        const normalized = query.normalize('NFKC').trim().replace(/\s+/g, ' ')
        const existing = dataset.cases.find(c =>
          c.query.normalize('NFKC').trim().replace(/\s+/g, ' ') === normalized
        )
        setWillCreate(!existing)
      })
      .catch(() => {
        setWillCreate(false)
      })
  }, [selectedDatasetId, query, api, knowledgeBaseId])

  const handlePromote = async () => {
    if (!selectedDatasetId) {
      toast.error(t('selectDatasetFirst'))
      return
    }

    const caseInput: EvaluationCaseInput = {
      query,
      chunk_relevance: chunkRelevance,
      document_relevance: documentRelevance,
      expected_empty: expectedEmpty,
    }

    setPromoting(true)
    try {
      await api.upsertEvaluationCaseByQuery(knowledgeBaseId, selectedDatasetId, caseInput)
      toast.success(willCreate ? t('caseCreated') : t('caseUpdated'))
      onSuccess()
    } catch {
      toast.error(t('caseUpsertFailed'))
    } finally {
      setPromoting(false)
    }
  }

  const hasRelevance = Object.keys(chunkRelevance).length > 0 || Object.keys(documentRelevance).length > 0

  return (
    <div className="space-y-3 rounded-lg border bg-muted/40 p-4">
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium">
            {t('promotionPreview')}: {willCreate ? t('createNewCase') : t('updateExistingCase')}
          </p>
          <p className="text-xs text-muted-foreground">
            {t('poolStats', {
              depth: poolDepth,
              strategies: poolStrategies.join(', '),
              candidates: candidateCount,
              judged: judgedCount,
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="expected-empty"
            checked={expectedEmpty}
            onCheckedChange={onExpectedEmptyChange}
            disabled={!canEvaluate || hasRelevance}
          />
          <Label htmlFor="expected-empty" className="text-sm cursor-pointer">
            {t('expectedEmpty')}
          </Label>
        </div>
      </div>

      <Button
        onClick={handlePromote}
        disabled={!canEvaluate || !selectedDatasetId || promoting || (!hasRelevance && !expectedEmpty)}
        className="w-full"
      >
        {promoting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
        {willCreate ? t('addToDataset') : t('updateInDataset')}
      </Button>
    </div>
  )
}

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import type { WorkflowRunPagePresentation } from '@/lib/api/workflows'

interface WorkflowPublishDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  presentation: WorkflowRunPagePresentation
  isPublishing: boolean
  onPublish: (presentation: WorkflowRunPagePresentation) => Promise<void>
}

const PRESENTATIONS: WorkflowRunPagePresentation[] = ['simple', 'result_first']

export function WorkflowPublishDialog({
  open,
  onOpenChange,
  presentation,
  isPublishing,
  onPublish,
}: WorkflowPublishDialogProps) {
  const t = useTranslations('workflow.publishSettings')
  const tCommon = useTranslations('common')
  const [selected, setSelected] = React.useState(presentation)

  React.useEffect(() => {
    if (open) setSelected(presentation)
  }, [open, presentation])

  return (
    <Dialog open={open} onOpenChange={isPublishing ? undefined : onOpenChange}>
      <DialogContent data-testid="workflow-publish-dialog" className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <RadioGroup
          value={selected}
          onValueChange={(value) => setSelected(value as WorkflowRunPagePresentation)}
          className="gap-2 py-2"
        >
          {PRESENTATIONS.map((mode) => (
            <label
              key={mode}
              className="flex cursor-pointer items-start gap-3 rounded-lg border p-4 transition-colors hover:bg-muted/50 has-[[data-checked]]:border-primary has-[[data-checked]]:bg-primary/5"
            >
              <RadioGroupItem value={mode} className="mt-0.5" />
              <span className="space-y-1">
                <span className="block text-sm font-medium">{t(`${mode}.title`)}</span>
                <span className="block text-sm text-muted-foreground">
                  {t(`${mode}.description`)}
                </span>
              </span>
            </label>
          ))}
        </RadioGroup>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isPublishing}>
            {tCommon('cancel')}
          </Button>
          <Button onClick={() => void onPublish(selected)} disabled={isPublishing}>
            {isPublishing && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('publish')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

'use client'

import { ArrowRight, AudioLines, File, Image, Type, Video } from 'lucide-react'
import { useTranslations } from 'next-intl'

const modalities = {
  text: { icon: Type, color: 'bg-blue-500/10 text-blue-500' },
  image: { icon: Image, color: 'bg-green-500/10 text-green-600' },
  video: { icon: Video, color: 'bg-orange-500/10 text-orange-600' },
  file: { icon: File, color: 'bg-amber-500/10 text-amber-600' },
  audio: { icon: AudioLines, color: 'bg-violet-500/10 text-violet-600' },
} as const

type Modality = keyof typeof modalities

export function ModelModalities({ capabilities }: { capabilities?: Record<string, unknown> | null }) {
  const t = useTranslations('models')
  const getModalities = (value: unknown): Modality[] =>
    Array.isArray(value) ? value.filter((item): item is Modality => typeof item === 'string' && Object.hasOwn(modalities, item)) : []
  const input = getModalities(capabilities?.input_modalities)
  const output = getModalities(capabilities?.output_modalities)

  if (!input.length && !output.length) return <span className="text-muted-foreground">—</span>

  const renderModalities = (items: Modality[], direction: string) => items.map((item, index) => {
    const { icon: Icon, color } = modalities[item]
    const label = `${direction}: ${t(`modality.${item}`)}`
    return <span key={`${item}-${index}`} title={label} aria-label={label} className={`inline-flex rounded-md p-1.5 ${color}`}><Icon aria-hidden="true" className="h-4 w-4" /></span>
  })

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {renderModalities(input, t('inputModalities'))}
      <ArrowRight aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
      {renderModalities(output, t('outputModalities'))}
    </div>
  )
}

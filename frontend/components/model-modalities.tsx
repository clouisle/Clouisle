'use client'

import { ArrowDownWideNarrow, ArrowRight, AudioLines, Boxes, File, Gavel, Image, Type, Video } from 'lucide-react'
import { useTranslations } from 'next-intl'

const modalities = {
  text: { icon: Type, color: 'bg-blue-500/10 text-blue-500' },
  image: { icon: Image, color: 'bg-green-500/10 text-green-600' },
  video: { icon: Video, color: 'bg-orange-500/10 text-orange-600' },
  file: { icon: File, color: 'bg-amber-500/10 text-amber-600' },
  audio: { icon: AudioLines, color: 'bg-violet-500/10 text-violet-600' },
  embedding: { icon: Boxes, color: 'bg-fuchsia-500/10 text-fuchsia-600' },
  decision: { icon: Gavel, color: 'bg-lime-500/10 text-lime-700' },
  ranking: { icon: ArrowDownWideNarrow, color: 'bg-cyan-500/10 text-cyan-600' },
} as const

type Modality = keyof typeof modalities

const defaults: Record<string, { input: Modality[]; output: Modality[] }> = {
  chat: { input: ['text'], output: ['text'] },
  embedding: { input: ['text'], output: ['embedding'] },
  rerank: { input: ['text'], output: ['ranking'] },
  decision: { input: ['text'], output: ['decision'] },
  tts: { input: ['text'], output: ['audio'] },
  stt: { input: ['audio'], output: ['text'] },
  audio_generation: { input: ['text'], output: ['audio'] },
  text_to_image: { input: ['text'], output: ['image'] },
  text_to_video: { input: ['text'], output: ['video'] },
}

export function ModelModalities({ capabilities, modelType }: { capabilities?: Record<string, unknown> | null; modelType: string }) {
  const t = useTranslations('models')
  const getModalities = (value: unknown): Modality[] =>
    Array.isArray(value) ? value.filter((item): item is Modality => typeof item === 'string' && Object.hasOwn(modalities, item)) : []
  const input = [...new Set([...(defaults[modelType]?.input ?? []), ...getModalities(capabilities?.input_modalities)])]
  const output = [...new Set([...(defaults[modelType]?.output ?? []), ...getModalities(capabilities?.output_modalities)])]

  if (!input.length && !output.length) return <span className="text-muted-foreground">—</span>

  const renderModalities = (items: Modality[], direction: string) => items.map((item, index) => {
    const { icon: Icon, color } = modalities[item]
    const label = `${direction}: ${t(`modality.${item}`)}`
    return <span key={`${item}-${index}`} title={label} aria-label={label} className={`inline-flex rounded p-1 ${color}`}><Icon aria-hidden="true" className="h-3 w-3" /></span>
  })

  return (
    <div className="flex flex-wrap items-center gap-1">
      {renderModalities(input, t('inputModalities'))}
      <ArrowRight aria-hidden="true" className="h-3 w-3 text-muted-foreground" />
      {renderModalities(output, t('outputModalities'))}
    </div>
  )
}

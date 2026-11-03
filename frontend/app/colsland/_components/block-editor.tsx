'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { CheckSquare, Heading1, Heading2, List, Plus, Trash2, Type } from 'lucide-react'
import { Button } from '@/components/ui/button'

type BlockType = 'paragraph' | 'heading1' | 'heading2' | 'bullet' | 'todo'
interface Block { id: number; type: BlockType; text: string; checked: boolean }

const blockTypes = [
  { type: 'paragraph', icon: Type },
  { type: 'heading1', icon: Heading1 },
  { type: 'heading2', icon: Heading2 },
  { type: 'bullet', icon: List },
  { type: 'todo', icon: CheckSquare },
] as const

export function BlockEditor() {
  const t = useTranslations('platform.colslandEditor')
  const [title, setTitle] = React.useState('')
  const [blocks, setBlocks] = React.useState<Block[]>([{ id: 0, type: 'paragraph', text: '', checked: false }])
  const [menu, setMenu] = React.useState<number | null>(null)
  const nextId = React.useRef(1)
  const fields = React.useRef(new Map<number, HTMLTextAreaElement>())
  const focus = React.useRef<{ id: number; offset: number } | null>(null)

  React.useLayoutEffect(() => {
    const target = focus.current
    if (!target) return
    const field = fields.current.get(target.id)
    field?.focus()
    field?.setSelectionRange(target.offset, target.offset)
    focus.current = null
  }, [blocks])

  const update = (id: number, patch: Partial<Block>) => {
    setBlocks(current => current.map(block => block.id === id ? { ...block, ...patch } : block))
  }

  const add = (after: number, type: BlockType = 'paragraph', text = '') => {
    const id = nextId.current++
    focus.current = { id, offset: 0 }
    setBlocks(current => {
      const index = current.findIndex(block => block.id === after)
      const next = [...current]
      next.splice(index + 1, 0, { id, type, text, checked: false })
      return next
    })
    setMenu(null)
  }

  const remove = (id: number) => {
    if (blocks.length === 1) {
      focus.current = { id, offset: 0 }
      update(id, { type: 'paragraph', text: '', checked: false })
    } else {
      const index = blocks.findIndex(block => block.id === id)
      const previous = blocks[index - 1] ?? blocks[index + 1]
      focus.current = { id: previous.id, offset: previous.text.length }
      setBlocks(current => current.filter(block => block.id !== id))
    }
    setMenu(null)
  }

  return (
    <section className="mx-auto w-full max-w-4xl px-5 pb-36 pt-12 sm:px-12 sm:pt-20" aria-label={t('document')}>
      <div className="mb-8 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Colsland</span>
        <span aria-hidden="true">/</span>
        <span>{t('document')}</span>
        <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-700 dark:text-amber-300">{t('unsaved')}</span>
      </div>
      <input aria-label={t('title')} placeholder={t('untitled')} value={title} onChange={event => setTitle(event.target.value)}
        className="mb-8 w-full border-0 bg-transparent px-2 text-4xl font-semibold tracking-tight outline-none placeholder:text-muted-foreground/45 sm:text-5xl" />
      <div className="space-y-1">
        {blocks.map(block => (
          <div key={block.id} className="group relative py-1">
            <div className="absolute right-full top-1 z-10 mr-1">
              <Button type="button" variant="ghost" size="icon" className={`size-8 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 [@media(hover:none)]:opacity-100 ${menu === block.id ? 'opacity-100' : ''}`} aria-label={t('blockActions')} aria-expanded={menu === block.id}
                onClick={() => setMenu(menu === block.id ? null : block.id)}><Plus className="size-4" /></Button>
              {menu === block.id && (
                <div className="absolute left-0 top-full z-20 w-52 rounded-lg border bg-popover p-1 text-popover-foreground shadow-lg" role="menu">
                  {blockTypes.map(({ type, icon: Icon }) => (
                    <button key={type} type="button" role="menuitem" className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm hover:bg-accent focus-visible:bg-accent"
                      onClick={() => { update(block.id, { type }); setMenu(null); focus.current = { id: block.id, offset: block.text.length } }}>
                      <Icon className="size-4 text-muted-foreground" />{t(type)}
                    </button>
                  ))}
                  <div className="my-1 border-t" />
                  <button type="button" role="menuitem" className="flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm text-destructive hover:bg-accent"
                    onClick={() => remove(block.id)}><Trash2 className="size-4" />{t('deleteBlock')}</button>
                </div>
              )}
            </div>
            <div className="mx-2 flex min-w-0 items-start gap-2 rounded-lg border border-transparent px-2 transition-colors focus-within:border-border">
              {block.type === 'bullet' && <span className="mt-2.5 shrink-0 text-muted-foreground" aria-hidden="true">•</span>}
              {block.type === 'todo' && <input type="checkbox" aria-label={t('toggleTodo')} checked={block.checked} onChange={event => update(block.id, { checked: event.target.checked })} className="mt-2.5 size-4 shrink-0 accent-primary" />}
            <textarea ref={element => { if (element) fields.current.set(block.id, element); else fields.current.delete(block.id) }}
              rows={1} aria-label={t(block.type)} placeholder={block.type === 'paragraph' ? t('placeholder') : t(block.type)} value={block.text}
              onChange={event => update(block.id, { text: event.target.value })}
              onKeyDown={event => {
                if (event.nativeEvent.isComposing) return
                if (event.key === 'Enter' && event.shiftKey) {
                  event.preventDefault()
                  const start = event.currentTarget.selectionStart
                  const end = event.currentTarget.selectionEnd
                  update(block.id, { text: block.text.slice(0, start) })
                  add(block.id, block.type === 'bullet' || block.type === 'todo' ? block.type : 'paragraph', block.text.slice(end))
                } else if (event.key === 'Backspace' && !block.text && blocks.length > 1) {
                  event.preventDefault()
                  remove(block.id)
                } else if (event.key === 'Escape') {
                  setMenu(null)
                }
              }}
              className={`colsland-block-input min-w-0 flex-1 resize-none overflow-hidden border-0 bg-transparent py-1.5 leading-6 outline-none placeholder:text-muted-foreground/50 ${block.type === 'heading1' ? 'text-3xl font-semibold leading-10' : block.type === 'heading2' ? 'text-2xl font-semibold leading-8' : 'text-base'} ${block.checked && block.type === 'todo' ? 'text-muted-foreground line-through' : ''}`}
              style={{ fieldSizing: 'content' }} />
            </div>
          </div>
        ))}
      </div>
      <Button type="button" variant="ghost" size="sm" className="mt-4 gap-2 bg-muted/60 text-muted-foreground hover:bg-muted" onClick={() => add(blocks[blocks.length - 1].id)}>
        <Plus className="size-4" />{t('addBlock')}
      </Button>
    </section>
  )
}

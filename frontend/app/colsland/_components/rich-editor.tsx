'use client'

import * as React from 'react'
import { useLocale, useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import type { Block } from '@blocknote/core'
import { en, zh } from '@blocknote/core/locales'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import './rich-editor.css'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { colslandShortcuts } from './editor-shortcuts'

export function RichEditor() {
  const t = useTranslations('platform.colslandEditor')
  const locale = useLocale()
  const { resolvedTheme } = useTheme()
  const content = React.useRef<Block[] | undefined>(undefined)
  const urls = React.useRef(new Set<string>())
  const uploadFile = React.useCallback(async (file: File) => {
    const url = URL.createObjectURL(file)
    urls.current.add(url)
    return url
  }, [])
  React.useEffect(() => {
    const ownedUrls = urls.current
    return () => { ownedUrls.forEach(url => URL.revokeObjectURL(url)); ownedUrls.clear() }
  }, [])
  const editor = useCreateBlockNote({
    dictionary: locale.startsWith('zh') ? zh : en,
    initialContent: content.current,
    uploadFile,
    extensions: [colslandShortcuts()],
  }, [locale])

  return <>
    <BlockNoteView key={locale} className="colsland-rich-editor" editor={editor}
      theme={resolvedTheme === 'dark' ? 'dark' : 'light'} onChange={() => { content.current = editor.document }} />
    <Button type="button" variant="ghost" size="sm" className="mt-4 gap-2 bg-muted/60 text-muted-foreground hover:bg-muted" onClick={() => {
      const blocks = editor.document
      const [block] = editor.insertBlocks([{ type: 'paragraph' }], blocks[blocks.length - 1], 'after')
      editor.setTextCursorPosition(block, 'start')
      editor.focus()
    }}><Plus className="size-4" />{t('addBlock')}</Button>
  </>
}

'use client'

import * as React from 'react'
import { useLocale } from 'next-intl'
import { useTheme } from 'next-themes'
import type { Block } from '@blocknote/core'
import { en, zh } from '@blocknote/core/locales'
import { useCreateBlockNote } from '@blocknote/react'
import { BlockNoteView } from '@blocknote/mantine'
import '@blocknote/mantine/style.css'
import './rich-editor.css'
import { colslandShortcuts } from './editor-shortcuts'

export function RichEditor() {
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

  React.useEffect(() => {
    const updateFocusedBlock = () => {
      const root = editor.domElement
      if (!root) return
      root.querySelector('[data-colsland-focused-block]')?.removeAttribute('data-colsland-focused-block')
      if (!editor.isFocused()) return
      const id = editor.getTextCursorPosition().block.id
      const block = root.querySelector(`[data-node-type="blockContainer"][data-id="${CSS.escape(id)}"]`)
      block?.setAttribute('data-colsland-focused-block', '')
    }
    const unsubscribeFocus = editor.onFocusChange(updateFocusedBlock)
    const unsubscribeSelection = editor.onSelectionChange(updateFocusedBlock)
    const unsubscribeChange = editor.onChange(updateFocusedBlock)
    updateFocusedBlock()
    return () => {
      unsubscribeFocus()
      unsubscribeSelection()
      unsubscribeChange()
      editor.domElement?.querySelector('[data-colsland-focused-block]')?.removeAttribute('data-colsland-focused-block')
    }
  }, [editor])

  return <BlockNoteView key={locale} className="colsland-rich-editor" editor={editor}
    theme={resolvedTheme === 'dark' ? 'dark' : 'light'} onChange={() => { content.current = editor.document }} />
}

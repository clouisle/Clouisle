import { afterAll, beforeAll, describe, expect, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { BlockNoteEditor } from '@blocknote/core'
import { colslandShortcuts } from './editor-shortcuts'

beforeAll(() => { if (!GlobalRegistrator.isRegistered) GlobalRegistrator.register({ url: 'http://localhost' }) })
afterAll(async () => { if (GlobalRegistrator.isRegistered) await GlobalRegistrator.unregister() })

function createEditor() {
  const editor = BlockNoteEditor.create({ extensions: [colslandShortcuts()] })
  const element = document.createElement('div')
  document.body.appendChild(element)
  editor.mount(element)
  return { editor, cleanup: () => { editor.unmount(); element.remove() } }
}

describe('rich document editor', () => {
  test('preserves rich text, links and table data across undo and redo', () => {
    const { editor, cleanup } = createEditor()
    try {
      editor.insertBlocks([
        { type: 'paragraph', content: [{ type: 'text', text: 'Bold', styles: { bold: true } }, { type: 'link', href: 'https://example.com', content: 'link' }] },
        { type: 'table', content: { type: 'tableContent', rows: [{ cells: ['A', 'B'] }] } },
      ], editor.document[0], 'after')
      const saved = editor.document
      expect(saved[1].content).toMatchObject([{ text: 'Bold', styles: { bold: true } }, { type: 'link', href: 'https://example.com' }])
      expect(saved[2]).toMatchObject({ type: 'table', content: { rows: [{ cells: [{ content: [{ text: 'A' }] }, { content: [{ text: 'B' }] }] }] } })
      editor.undo()
      expect(editor.document).toHaveLength(1)
      editor.redo()
      expect(editor.document).toEqual(saved)
    } finally { cleanup() }
  })

  test('Enter inserts a line break and Shift+Enter splits at the cursor', () => {
    const { editor, cleanup } = createEditor()
    try {
      editor.insertInlineContent('Hello world')
      editor.focus()
      const dom = editor.prosemirrorView.dom
      dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      expect(editor.document).toHaveLength(1)
      expect(editor.document[0].content).toMatchObject([{ text: 'Hello world\n' }])
      dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', shiftKey: true, bubbles: true, cancelable: true }))
      expect(editor.document).toHaveLength(2)
      expect(editor.document[0].content).toMatchObject([{ text: 'Hello world\n' }])
      expect(editor.document[1].content).toEqual([])
    } finally { cleanup() }
  })

  test('Enter starts a new list item instead of a line break inside a list', () => {
    const { editor, cleanup } = createEditor()
    try {
      editor.replaceBlocks(editor.document, [
        { type: 'bulletListItem', content: '模块规划' },
        { type: 'paragraph', content: '普通段落' },
      ])
      editor.setTextCursorPosition(editor.document[0], 'end')
      editor.focus()
      const dom = editor.prosemirrorView.dom
      dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      expect(editor.document.map(block => block.type)).toEqual(['bulletListItem', 'bulletListItem', 'paragraph'])
      expect(editor.document[1].content).toEqual([])
      editor.setTextCursorPosition(editor.document[2], 'end')
      dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
      expect(editor.document).toHaveLength(3)
      expect(editor.document[2].content).toMatchObject([{ text: '普通段落\n' }])
    } finally { cleanup() }
  })
})

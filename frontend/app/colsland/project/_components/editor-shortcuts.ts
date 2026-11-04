import { createExtension } from '@blocknote/core'
import { Plugin } from '@tiptap/pm/state'
import type { EditorView } from '@tiptap/pm/view'

const LIST_ITEM_TYPES: Record<string, true> = { bulletListItem: true, numberedListItem: true, checkListItem: true, toggleListItem: true }

function contentTypeAt(view: EditorView, pos: number) {
  const node = view.domAtPos(pos).node
  const element = node instanceof Element ? node : node.parentElement
  return element?.closest('[data-content-type]')?.getAttribute('data-content-type') ?? undefined
}

export const colslandShortcuts = createExtension(() => {
  let forwarding = false
  const forwardEnter = (view: EditorView) => {
    forwarding = true
    try {
      return view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })) === false
    } finally {
      forwarding = false
    }
  }
  return {
    key: 'colsland-shortcuts',
    runsBefore: ['default'],
    prosemirrorPlugins: [new Plugin({
      props: {
        handleKeyDown(view, event) {
          if (forwarding || event.key !== 'Enter' || event.isComposing || view.composing || event.altKey || event.ctrlKey || event.metaKey) return false
          const { $from, $to } = view.state.selection
          if (!$from.sameParent($to) || !$from.parent.inlineContent || $from.parent.type.spec.code) return false
          const listItem = LIST_ITEM_TYPES[contentTypeAt(view, $from.pos) ?? ''] === true
          if (event.shiftKey || listItem) return forwardEnter(view)
          const hardBreak = view.state.schema.nodes.hardBreak
          if (!hardBreak) return false
          view.dispatch(view.state.tr.replaceSelectionWith(hardBreak.create()).scrollIntoView())
          return true
        },
      },
    })],
  }
})

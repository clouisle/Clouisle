import { createExtension } from '@blocknote/core'
import { Plugin } from '@tiptap/pm/state'

export const colslandShortcuts = createExtension(() => {
  let forwarding = false
  return {
    key: 'colsland-shortcuts',
    runsBefore: ['default'],
    prosemirrorPlugins: [new Plugin({
      props: {
        handleKeyDown(view, event) {
          if (forwarding || event.key !== 'Enter' || event.isComposing || view.composing || event.altKey || event.ctrlKey || event.metaKey) return false
          const { $from, $to } = view.state.selection
          if (!$from.sameParent($to) || !$from.parent.inlineContent || $from.parent.type.spec.code) return false
          if (event.shiftKey) {
            forwarding = true
            try {
              return view.dom.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })) === false
            } finally {
              forwarding = false
            }
          }
          const hardBreak = view.state.schema.nodes.hardBreak
          if (!hardBreak) return false
          view.dispatch(view.state.tr.replaceSelectionWith(hardBreak.create()).scrollIntoView())
          return true
        },
      },
    })],
  }
})

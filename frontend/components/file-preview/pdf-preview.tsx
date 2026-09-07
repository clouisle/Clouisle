'use client'

import * as React from 'react'
import EmbedPDF, {
  custom,
  defineChrome,
  group,
  item,
  type EmbedPdfViewerElement,
  type ViewerHandle,
} from '@embedpdf/viewer'

interface PdfPreviewProps {
  blob: Blob
  locale?: string
  onError?: () => void
}

const pdfViewerStrings = {
  zh: {
    commands: {
      sidebar: '侧边栏',
    },
    demo: {
      thumbnails: '缩略图',
      outline: '大纲',
    },
  },
} as const

// Clean, read-only PDF viewing toolbar without annotation, form, or redaction edit modes
const readOnlyPdfChrome = defineChrome({
  frame: {
    tabs: 'never',
    header: false,
  },
  bars: {
    main: {
      id: 'main',
      sections: {
        start: [
          group('workspace', { importance: 4 }, [
            item('panel:sidebar', { importance: 5 }),
            item('page:settings'),
          ]),
          group('zoom', { importance: 4 }, [
            custom('zoom-controls', {
              variants: ['inline', 'button'],
              terminal: 'zoom:menu',
            }),
          ]),
          group('tools', { importance: 2 }, ['pan:toggle', 'pointer:toggle']),
        ],
        center: [],
        end: [
          group('panels', { importance: 5 }, ['panel:search']),
        ],
      },
    },
  },
  menus: {
    zoom: {
      id: 'zoom',
      sections: [
        {
          labelKey: 'commands.zoom.level',
          items: ['zoom:50', 'zoom:100', 'zoom:150', 'zoom:200', 'zoom:400'],
        },
        { items: ['zoom:in', 'zoom:out'] },
        {
          items: ['zoom:fit-page', 'zoom:fit-width', 'zoom:automatic'],
        },
      ],
    },
    'page-settings': {
      id: 'page-settings',
      sections: [
        {
          labelKey: 'commands.spread.group',
          items: ['spread:none', 'spread:odd', 'spread:even'],
        },
        {
          labelKey: 'commands.scroll.group',
          items: ['scroll:vertical', 'scroll:horizontal'],
        },
        {
          labelKey: 'commands.rotate.group',
          items: ['rotate:clockwise', 'rotate:counter-clockwise'],
        },
        { items: ['document:fullscreen'] },
      ],
    },
  },
})

function subscribeToDocumentErrors(
  element: EmbedPdfViewerElement,
  onError: (() => void) | undefined,
) {
  if (!onError) return () => {}

  let unsubscribe: (() => void) | null = null
  const subscribe = (viewer: ViewerHandle | null) => {
    if (!viewer || unsubscribe) return
    const hasDocumentError = () =>
      viewer.documents.list().some(({ status }) => status === 'error')
    if (hasDocumentError()) {
      onError()
    }

    unsubscribe = viewer.watch(
      hasDocumentError,
      (hasError, hadError) => {
        if (hasError && !hadError) {
          onError()
        }
      },
    )
  }

  const handleReady = (event: Event) => {
    const viewer =
      (event as CustomEvent<{ viewer?: ViewerHandle }>).detail?.viewer ??
      element.viewer
    subscribe(viewer)
  }

  element.addEventListener('epdf:ready', handleReady)
  subscribe(element.viewer)

  return () => {
    element.removeEventListener('epdf:ready', handleReady)
    unsubscribe?.()
  }
}

export function PdfPreview({ blob, locale, onError }: PdfPreviewProps) {
  const containerRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const container = containerRef.current
    let objectUrl: string | null = null
    let element: EmbedPdfViewerElement | null = null
    let unsubscribeFromDocumentErrors: (() => void) | null = null

    if (!container) return

    try {
      objectUrl = URL.createObjectURL(blob)
      container.replaceChildren()
      element = EmbedPDF.init({
        target: container,
        src: objectUrl,
        strings: pdfViewerStrings,
        locale: locale || 'auto',
        disabledCategories: ['annotate', 'shapes', 'insert', 'form', 'redact', 'comment'],
        chrome: readOnlyPdfChrome,
      })
      unsubscribeFromDocumentErrors = subscribeToDocumentErrors(element, onError)
    } catch {
      onError?.()
    }

    return () => {
      unsubscribeFromDocumentErrors?.()
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
      if (element && element.parentNode) {
        element.parentNode.removeChild(element)
      }
      if (container) {
        container.replaceChildren()
      }
    }
  }, [blob, locale, onError])

  return (
    <div className="h-full w-full overflow-hidden bg-muted/10">
      <div ref={containerRef} className="h-full w-full" />
    </div>
  )
}

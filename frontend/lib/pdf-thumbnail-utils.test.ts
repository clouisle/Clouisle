import { afterAll, expect, mock, test } from 'bun:test'
import { Window } from 'happy-dom'
import {
  getPdfPageCount,
  loadPdfDocument,
  loadSharedPdfEngine,
  renderPdfThumbnailUrl,
  resolvePdfiumWasmUrl,
} from './pdf-thumbnail-utils'

const originalWindow = globalThis.window
const window = new Window({ url: 'http://localhost:3000/chat/1' })
Object.assign(globalThis, { window })

const page = { size: { width: 100, height: 200 } }
const document = { pageCount: 2, pages: [page, page] }
const engine = {
  openDocumentUrl: () => ({ toPromise: async () => document }),
  renderThumbnail: () => ({ toPromise: async () => new Blob(['thumbnail']) }),
}
let failNext = true

mock.module('@embedpdf/engines/pdfium-worker-engine', () => ({
  createPdfiumEngine: () => {
    if (failNext) {
      failNext = false
      throw new Error('engine failed')
    }
    return engine
  },
}))

afterAll(() => {
  Object.assign(globalThis, { window: originalWindow })
})

test('resolves the self-hosted wasm path against the page origin', () => {
  expect(resolvePdfiumWasmUrl()).toBe('http://localhost:3000/pdfium/pdfium.wasm')
})

test('retries the engine after a rejected initialization', async () => {
  await expect(loadSharedPdfEngine()).rejects.toThrow('engine failed')
  await expect(loadSharedPdfEngine()).resolves.toBe(engine)
})

test('loads documents and reads their page count', async () => {
  expect(await loadPdfDocument('blob:document')).toBe(document)
  expect(await getPdfPageCount('blob:document')).toBe(2)
})

test('renders a thumbnail object URL', async () => {
  const originalCreateObjectURL = globalThis.URL.createObjectURL
  globalThis.URL.createObjectURL = mock(() => 'blob:thumbnail-url')

  try {
    expect(
      await renderPdfThumbnailUrl({
        pageIndex: 0,
        width: 92,
        url: 'blob:document',
      })
    ).toBe('blob:thumbnail-url')
  } finally {
    globalThis.URL.createObjectURL = originalCreateObjectURL
  }
})

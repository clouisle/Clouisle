import { afterAll, expect, test } from 'bun:test'
import { Window } from 'happy-dom'
import { resolvePdfiumWasmUrl } from './pdf-thumbnail-utils'

const originalWindow = globalThis.window
const window = new Window({ url: 'http://localhost:3000/chat/1' })
Object.assign(globalThis, { window })

afterAll(() => {
  Object.assign(globalThis, { window: originalWindow })
})

test('resolves the self-hosted wasm path against the page origin', () => {
  expect(resolvePdfiumWasmUrl()).toBe('http://localhost:3000/pdfium/pdfium.wasm')
})

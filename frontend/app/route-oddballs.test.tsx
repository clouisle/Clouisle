import { describe, expect, mock, test } from 'bun:test'

mock.module('next/font/local', () => ({
  default: () => ({ className: 'font-local', variable: 'font-local' }),
}))

mock.module('@monaco-editor/react', () => ({
  default: () => null,
}))

describe('route/canvas oddball imports', () => {
  test('imports public chat page', async () => {
    const page = await import('./(chat)/chat/[id]/page')
    expect(page.default).toBeFunction()
  })

  test('imports dashboard code capability page', async () => {
    const page = await import('./(dashboard)/capabilities/code/page')
    expect(page.default).toBeFunction()
  })

  test('imports platform capabilities page', async () => {
    const page = await import('./(platform)/app/capabilities/page')
    expect(page.default).toBeFunction()
  })

  test('imports platform code capability page', async () => {
    const page = await import('./(platform)/app/capabilities/code/page')
    expect(page.default).toBeFunction()
  })

  test('imports memory graph canvas', async () => {
    const canvas = await import('./(platform)/app/memories/_components/memory-graph-canvas')
    expect(canvas.MemoryGraphCanvas).toBeFunction()
  })
})

import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
const openLightbox = mock(() => {})
const closeLightbox = mock(() => {})
const setVideoLightboxOpen = mock(() => {})

mock.module('react', () => ({
  useState: (value: unknown) => [value, setVideoLightboxOpen],
}))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('lucide-react', () => ({ Clock: element, Loader2: element, CheckCircle2: element, XCircle: element, SkipForward: element }))
mock.module('@/components/chat/image-lightbox', () => ({
  ImageLightbox: element,
  VideoLightbox: element,
  useLightbox: () => ({ imageSrc: 'selected.png', imageAlt: 'selected', isOpen: true, openLightbox, closeLightbox }),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { nodeStatusConfig, renderNodeOutput } = await import('./node-output-renderer')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  if (typeof current.type === 'function' && current.type !== element) {
    return findAll(current.type(current.props), predicate)
  }
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) {
    const current = node as TreeNode
    if (typeof current.type === 'function' && current.type !== element) return text(current.type(current.props))
    return text(current.props.children)
  }
  return ''
}

const t = (key: string) => key

function render(type: string, outputs: Record<string, unknown>) {
  return renderNodeOutput(type, outputs, t) as TreeNode
}

test('renders text, branch, request, tool, code, and fallback outputs', () => {
  expect(text(render('llm', { content: 'Generated answer' }))).toBe('Generated answer')
  expect(text(render('answer', { answer: 'Done', ignored: 2 }))).toBe('answerDone')
  expect(text(render('code', { message: 'ok', data: { count: 2 } }))).toContain('data{\n  "count": 2\n}')

  const branch = render('question_classifier', { matched_category: 'billing', handle: 'category-1' })
  expect(text(branch)).toContain('runDrawer.matchedBranchbilling')
  expect(text(branch)).toContain('runDrawer.handle category-1')

  const success = render('http_request', { statusCode: 201, response: { id: 1 } })
  expect(text(success)).toContain('runDrawer.statusCode201')
  expect(findAll(success, (node) => node.props.className?.toString().includes('text-green-600'))).toHaveLength(1)
  const failure = render('http_request', { status_code: 500, body: 'failed' })
  expect(findAll(failure, (node) => node.props.className?.toString().includes('text-red-600'))).toHaveLength(1)

  expect(text(render('tool', { output: 'tool result' }))).toBe('tool result')
  expect(text(render('tool', { result: { ok: true } }))).toContain('"ok": true')
  expect(text(render('unknown', { value: 3 }))).toContain('"value": 3')
  expect(Object.keys(nodeStatusConfig)).toEqual(['pending', 'running', 'success', 'failed', 'skipped'])
})

test('renders Agent response, artifacts, and dialogue details', () => {
  const output = render('agent', {
    response: 'Generated answer',
    artifacts: [{ url: 'https://example.test/report.csv' }],
    dialogue: [{ role: 'assistant', content: 'Generated answer' }],
    toolCalls: [{ name: 'export_report' }],
    usage: { total_tokens: 12 },
  })

  expect(text(output)).toContain('Generated answer')
  expect(text(output)).toContain('artifacts')
  expect(text(output)).toContain('dialogue')
  expect(text(output)).toContain('toolCalls')
  expect(text(output)).toContain('usage')
  expect(text(output)).toContain('report.csv')
})

test('renders image and video media previews with lightbox actions', () => {
  const images = render('media_generation', { result: ['one.png', 'two.png'] })
  const imageButtons = findAll(images, (node) => node.type === 'button')
  expect(findAll(images, (node) => node.type === 'img').map((node) => [node.props.src, node.props.alt])).toEqual([
    ['one.png', 'generated media 1'],
    ['two.png', 'generated media 2'],
  ])
  ;(imageButtons[0].props.onClick as () => void)()
  expect(openLightbox).toHaveBeenCalledWith('one.png')

  const video = render('media_generation', { output: 'clip.mp4' })
  ;(findAll(video, (node) => node.type === 'button')[0].props.onClick as () => void)()
  expect(setVideoLightboxOpen).toHaveBeenCalledWith(true)
  ;(findAll(video, (node) => node.type === element && node.props.src === 'clip.mp4')[0].props.onClose as () => void)()
  expect(setVideoLightboxOpen).toHaveBeenCalledWith(false)
})

test('renders structured media results and empty output fallbacks', () => {
  const images = render('media_generation', { result: {
    kind: 'media.image', success: true, prompt: 'draw', images: [
      { image: { url: 'asset.png' } },
      { image: { base64: 'abc', format: 'webp' } },
      { image: {} },
    ],
  } })
  expect(text(images)).toContain('runDrawer.result')
  expect(findAll(images, (node) => node.type === 'img').map((node) => node.props.src)).toEqual([
    'asset.png',
    'data:image/webp;base64,abc',
  ])

  const video = render('media_generation', { result: {
    kind: 'media.video', success: true, prompt: 'animate', status: 'completed', video: { base64: 'xyz' },
  } })
  expect(text(video)).toContain('runDrawer.result')
  expect(findAll(video, (node) => node.type === 'video')[0].props.src).toBe('data:video/mp4;base64,xyz')

  expect(text(render('llm', { text: 1 }))).toContain('"text": 1')
  expect(text(render('answer', { count: 2 }))).toContain('"count": 2')
  expect(text(render('condition', {}))).toBe('')
  expect(text(render('http_request', {}))).toBe('')
})

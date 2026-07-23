import { expect, mock, test } from 'bun:test'

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
const element = function Element() {}
const openLightbox = mock(() => {})
const closeLightbox = mock(() => {})
const setVideoLightboxOpen = mock(() => {})

mock.module('react', () => ({ useState: (value: unknown) => [value, setVideoLightboxOpen] }))
mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@xyflow/react', () => ({ Handle: element, Position: { Left: 'left', Right: 'right' } }))
mock.module('lucide-react', () => ({ Image: element, Loader2: element, Video: element, XCircle: element }))
mock.module('@/components/chat/image-lightbox', () => ({
  ImageLightbox: element,
  VideoLightbox: element,
  useLightbox: () => ({ imageSrc: 'selected.png', imageAlt: 'Selected', isOpen: true, openLightbox, closeLightbox }),
}))
mock.module('@/lib/utils', () => ({ cn: (...values: unknown[]) => values.filter(Boolean).join(' ') }))

const { MediaGenerationNode, defaultMediaGenerationConfig } = await import('./media-generation-node')

type TreeNode = { type?: unknown, props: Record<string, unknown> }

function findAll(node: unknown, predicate: (node: TreeNode) => boolean): TreeNode[] {
  if (Array.isArray(node)) return node.flatMap((child) => findAll(child, predicate))
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const current = node as TreeNode
  return [...(predicate(current) ? [current] : []), ...findAll(current.props.children, predicate)]
}

function text(node: unknown): string {
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(text).join('')
  if (node && typeof node === 'object' && 'props' in node) return text((node as TreeNode).props.children)
  return ''
}

test('renders selected running image output and opens its preview', () => {
  const tree = MediaGenerationNode({
    id: 'media', selected: true,
    data: {
      type: 'media_generation', label: 'Create images', config: {},
      mediaGenerationConfig: { ...defaultMediaGenerationConfig, outputVariable: 'images' },
      runtimeTrace: { status: 'running', outputs: { images: ['one.png', '', 42, 'two.png'] } },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.className?.toString().includes('border-primary')).length).toBeGreaterThan(0)
  expect(findAll(tree, (node) => node.props.children === 'Create images')).toHaveLength(1)
  expect(findAll(tree, (node) => node.props.children === 'nodesMediaGeneration.imageMode')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'runDrawer.statusRunning')).toHaveLength(1)
  const imageButtons = findAll(tree, (node) => node.props['aria-label']?.toString().startsWith('Generated image'))
  expect(imageButtons).toHaveLength(2)
  expect(findAll(tree, (node) => node.type === 'img').map((node) => node.props.src)).toEqual(['one.png', 'two.png'])
  ;(imageButtons[0].props.onClick as () => void)()
  expect(openLightbox).toHaveBeenCalledWith('one.png')
  expect(findAll(tree, (node) => node.props.type === 'target')[0].props.position).toBe('left')
  expect(findAll(tree, (node) => node.props.type === 'source')[0].props.position).toBe('right')
})

test('renders failed video output and opens and closes its preview', () => {
  const tree = MediaGenerationNode({
    id: 'media',
    data: {
      type: 'media_generation', label: '', config: {},
      mediaGenerationConfig: { ...defaultMediaGenerationConfig, mode: 'video', outputVariable: 'video' },
      runtimeTrace: { status: 'failed', outputs: { video: 'result.mp4' } },
    },
  }) as TreeNode

  expect(findAll(tree, (node) => node.props.children === 'nodesMediaGeneration.label')).toHaveLength(2)
  expect(findAll(tree, (node) => node.props.children === 'nodesMediaGeneration.videoMode')).toHaveLength(1)
  expect(findAll(tree, (node) => text(node) === 'runDrawer.statusFailed')).toHaveLength(1)
  expect(findAll(tree, (node) => node.type === 'video')[0].props.src).toBe('result.mp4')
  const preview = findAll(tree, (node) => node.props['aria-label'] === 'Open generated video')[0]
  ;(preview.props.onClick as () => void)()
  expect(setVideoLightboxOpen).toHaveBeenCalledWith(true)
  const lightbox = findAll(tree, (node) => node.type === element && node.props.src === 'result.mp4')[0]
  ;(lightbox.props.onClose as () => void)()
  expect(setVideoLightboxOpen).toHaveBeenCalledWith(false)
})

test('uses default image configuration without a preview', () => {
  const tree = MediaGenerationNode({ id: 'media', data: { type: 'media_generation', label: '', config: {} } }) as TreeNode

  expect(defaultMediaGenerationConfig).toEqual({ mode: 'image', prompt: '', numImages: 1, duration: 5, aspectRatio: '16:9', outputVariable: 'result' })
  expect(tree.props.className).toContain('w-[180px]')
  expect(findAll(tree, (node) => node.type === 'img' || node.type === 'video')).toHaveLength(0)
})

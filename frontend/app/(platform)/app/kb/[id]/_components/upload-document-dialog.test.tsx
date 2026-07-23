import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactElement, ReactNode } from 'react'

const uploadDocument = mock()
const getPublic = mock()
const push = mock()
const toastSuccess = mock()
const toastError = mock()

const jsx = (type: unknown, props: Record<string, unknown>) => ({ type, props })
mock.module('react/jsx-runtime', () => ({ Fragment: 'fragment', jsx, jsxs: jsx }))
mock.module('react/jsx-dev-runtime', () => ({ Fragment: 'fragment', jsxDEV: jsx }))

let state: unknown[] = []
let stateIndex = 0
let effectDependencies: unknown[][] = []
let effectIndex = 0
mock.module('react', () => ({
  useEffect: (effect: () => void, dependencies: unknown[]) => {
    const index = effectIndex++
    const previous = effectDependencies[index]
    if (!previous || dependencies.some((value, position) => !Object.is(value, previous[position]))) {
      effectDependencies[index] = dependencies
      effect()
    }
  },
  useRef: <T,>(initial: T) => ({ current: initial }),
  useState: <T,>(initial: T) => {
    const index = stateIndex++
    state[index] ??= initial
    return [state[index] as T, (value: T | ((previous: T) => T)) => {
      state[index] = typeof value === 'function'
        ? (value as (previous: T) => T)(state[index] as T)
        : value
    }] as const
  },
}))

mock.module('next-intl', () => ({
  useTranslations: () => (key: string, values?: Record<string, unknown>) =>
    values ? `${key}:${Object.values(values).join(',')}` : key,
}))
mock.module('next/navigation', () => ({ useRouter: () => ({ push }) }))
mock.module('sonner', () => ({ toast: { success: toastSuccess, error: toastError } }))
mock.module('@/lib/api', () => ({ knowledgeBasesApi: { uploadDocument } }))
mock.module('@/lib/api/site-settings', () => ({ siteSettingsApi: { getPublic } }))
mock.module('@/lib/constants', () => ({
  BYTES_PER_MB: 1,
  KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES: ['.pdf', '.txt'],
  KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB: 10,
}))
mock.module('@/components/ui/dialog', () => ({
  Dialog: 'dialog',
  DialogContent: 'section',
  DialogDescription: 'p',
  DialogFooter: 'footer',
  DialogHeader: 'header',
  DialogTitle: 'h2',
}))
mock.module('@/components/ui/button', () => ({ Button: 'button' }))
mock.module('@/components/ui/progress', () => ({ Progress: 'progress' }))
mock.module('lucide-react', () => ({
  Upload: 'upload-icon',
  FileText: 'file-icon',
  X: 'x-icon',
  Loader2: 'loader-icon',
}))

const { UploadDocumentDialog } = await import('./upload-document-dialog')
type Props = React.ComponentProps<typeof UploadDocumentDialog>

const baseProps = (overrides: Partial<Props> = {}): Props => ({
  open: true,
  onOpenChange: mock(),
  knowledgeBaseId: 'kb-1',
  onSuccess: mock(),
  ...overrides,
})

function render(props: Props) {
  stateIndex = 0
  effectIndex = 0
  return UploadDocumentDialog(props)
}

function elements(node: ReactNode): ReactElement[] {
  if (Array.isArray(node)) return node.flatMap(elements)
  if (!node || typeof node !== 'object' || !('props' in node)) return []
  const element = node as ReactElement<{ children?: ReactNode }>
  return [element, ...elements(element.props.children)]
}

function text(node: ReactNode): string {
  if (Array.isArray(node)) return node.map(text).join(' ')
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (!node || typeof node !== 'object' || !('props' in node)) return ''
  return text((node as ReactElement<{ children?: ReactNode }>).props.children)
}

function find(tree: ReactNode, predicate: (element: ReactElement) => boolean) {
  const element = elements(tree).find(predicate)
  if (!element) throw new Error('Expected element')
  return element
}

function file(name: string, size: number) {
  return { name, size } as File
}

function select(props: Props, files: File[]) {
  const input = find(render(props), element => element.type === 'input' && element.props.type === 'file')
  ;(input.props.onChange as (event: { target: { files: FileList } }) => void)({
    target: { files: files as unknown as FileList },
  })
}

function uploadButton(tree: ReactNode) {
  return find(tree, element => element.type === 'button' && text(element).includes('upload'))
}

beforeEach(() => {
  state = []
  effectDependencies = []
  for (const fn of [uploadDocument, getPublic, push, toastSuccess, toastError]) fn.mockReset()
  getPublic.mockResolvedValue({ kb_document_max_upload_size_mb: 5 })
})

describe('platform UploadDocumentDialog', () => {
  test('uploads valid files through the platform API and follows the platform preview route', async () => {
    const onOpenChange = mock()
    const onSuccess = mock()
    const props = baseProps({ onOpenChange, onSuccess })
    uploadDocument
      .mockResolvedValueOnce({ id: 'doc-1' })
      .mockResolvedValueOnce({ id: 'doc-2' })
    render(props)
    await Promise.resolve()

    const first = file('guide.pdf', 0)
    const second = file('notes.TXT', 4)
    select(props, [first, second])
    const tree = render(props)

    expect(text(tree)).toContain('guide.pdf')
    expect(text(tree)).toContain('0 B')
    await (uploadButton(tree).props.onClick as () => Promise<void>)()

    expect(uploadDocument).toHaveBeenNthCalledWith(1, 'kb-1', first)
    expect(uploadDocument).toHaveBeenNthCalledWith(2, 'kb-1', second)
    expect(toastSuccess).toHaveBeenCalledWith('uploadSuccess:2')
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onSuccess).toHaveBeenCalledTimes(1)
    expect(push).toHaveBeenCalledWith('/app/kb/kb-1/documents/preview?docs=doc-1,doc-2')
  })

  test('rejects unsupported and oversized files at the input boundary', async () => {
    const props = baseProps()
    render(props)
    await Promise.resolve()

    select(props, [file('script.exe', 1), file('large.pdf', 6)])
    const tree = render(props)

    expect(toastError).toHaveBeenCalledWith(
      'script.exe: unsupportedFileType:.exe\nlarge.pdf: fileTooLarge:5MB'
    )
    expect(uploadButton(tree).props.disabled).toBe(true)
    expect(uploadDocument).not.toHaveBeenCalled()
  })

  test('keeps controls locked during upload and cleans loading state after API failure', async () => {
    let rejectUpload!: (error: Error) => void
    uploadDocument.mockImplementation(() => new Promise((_, reject) => { rejectUpload = reject }))
    const onOpenChange = mock()
    const props = baseProps({ onOpenChange })
    render(props)
    await Promise.resolve()
    select(props, [file('guide.pdf', 2)])

    const pending = (uploadButton(render(props)).props.onClick as () => Promise<void>)()
    const loadingTree = render(props)
    expect(text(loadingTree)).toContain('0 %')
    expect(elements(loadingTree).filter(element => element.type === 'button').every(element => element.props.disabled)).toBe(true)

    rejectUpload(new Error('offline'))
    await pending
    const settledTree = render(props)
    expect(text(settledTree)).not.toContain('uploading (')
    expect(uploadButton(settledTree).props.disabled).toBe(false)
    expect(toastError).toHaveBeenCalledWith('uploadFailed:1')
    expect(onOpenChange).not.toHaveBeenCalled()
    expect(push).not.toHaveBeenCalled()
  })

  test('supports removing files, canceling, and resets selection when closed', async () => {
    const onOpenChange = mock()
    const props = baseProps({ onOpenChange })
    render(props)
    await Promise.resolve()
    select(props, [file('guide.pdf', 2)])

    let tree = render(props)
    const remove = find(tree, element => element.type === 'button' && element.props.size === 'icon')
    ;(remove.props.onClick as () => void)()
    expect(uploadButton(render(props)).props.disabled).toBe(true)

    select(props, [file('guide.pdf', 2)])
    tree = render(props)
    const cancel = find(tree, element => element.type === 'button' && text(element).includes('cancel'))
    ;(cancel.props.onClick as () => void)()
    expect(onOpenChange).toHaveBeenCalledWith(false)

    render({ ...props, open: false })
    tree = render({ ...props, open: true })
    expect(text(tree)).not.toContain('guide.pdf')
    expect(uploadButton(tree).props.disabled).toBe(true)
  })

  test('does not fetch settings while closed and falls back to the default validation limit', async () => {
    const props = baseProps({ open: false })
    render(props)
    expect(getPublic).not.toHaveBeenCalled()

    getPublic.mockRejectedValueOnce(new Error('offline'))
    const openProps = { ...props, open: true }
    render(openProps)
    await Promise.resolve()
    select(openProps, [file('fallback.pdf', 11)])

    expect(toastError).toHaveBeenCalledWith('fallback.pdf: fileTooLarge:10MB')
  })
})

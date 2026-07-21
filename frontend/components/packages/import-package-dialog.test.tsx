import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from 'react-test-renderer'

const toast = { error: mock(() => undefined), success: mock(() => undefined) }

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign((key: string) => key, { has: () => false }),
}))
mock.module('sonner', () => ({ toast }))
mock.module('lucide-react', () => ({ Loader2: () => null }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <>{children}</>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (() => {
    const Input = React.forwardRef((props: Record<string, unknown>, ref: React.ForwardedRef<HTMLInputElement>) => <input ref={ref} {...props} />)
    Input.displayName = 'Input'
    return Input
  })(),
}))
mock.module('@/components/ui/badge', () => ({ Badge: ({ children }: React.PropsWithChildren) => <span>{children}</span> }))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => <div {...props}>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))

import { ImportPackageDialog } from './import-package-dialog'

const preview = {
  session_id: 'session-1', package_id: 'package-1', resource_type: 'workflow' as const,
  resource_name: 'Imported workflow', source_resource_id: 'source-1', format_version: '1',
  app_version: '1', exported_at: '2026-01-01T00:00:00Z', valid: true, errors: [], warnings: [],
  dependencies: [], allowed_actions: ['install'] as const, default_action: 'install' as const,
}
const renderers: ReactTestRenderer[] = []

globalThis.IS_REACT_ACT_ENVIRONMENT = true

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.clearAllMocks()
})

function render(api: { preview: ReturnType<typeof mock>; install: ReturnType<typeof mock> }, props = {}) {
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<ImportPackageDialog open onOpenChange={mock(() => undefined)} teamId="team-1" api={api as never} {...props} />)
  })
  renderers.push(renderer!)
  return renderer!
}

function selectFile(renderer: ReactTestRenderer, file: File) {
  const input = renderer.root.findByProps({ type: 'file' })
  return act(async () => input.props.onChange({ target: { files: [file] } }))
}

describe('ImportPackageDialog', () => {
  test('previews a valid package and installs it', async () => {
    const api = { preview: mock(() => Promise.resolve(preview)), install: mock(() => Promise.resolve({ installed: 'workflow-1', skipped: false, errors: [], warnings: [] })) }
    const onOpenChange = mock(() => undefined)
    const onImported = mock(() => undefined)
    const renderer = render(api, { onOpenChange, onImported })
    const file = new File(['package'], 'workflow.clouisle')

    await selectFile(renderer, file)
    expect(api.preview).toHaveBeenCalledWith('team-1', file)
    expect(JSON.stringify(renderer.toJSON())).toContain('Imported workflow')

    await act(async () => renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.onClick())

    expect(api.install).toHaveBeenCalledWith('session-1', { action: 'install', target_name: undefined, dependency_mapping: {} })
    expect(toast.success).toHaveBeenCalledWith('packageImported')
    expect(onImported).toHaveBeenCalledWith('workflow-1')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('rejects non-package files without previewing', async () => {
    const api = { preview: mock(() => Promise.resolve(preview)), install: mock(() => Promise.resolve({ skipped: false, errors: [], warnings: [] })) }
    const renderer = render(api)

    await selectFile(renderer, new File(['not a package'], 'workflow.json'))

    expect(toast.error).toHaveBeenCalledWith('selectClouisleFile')
    expect(api.preview).not.toHaveBeenCalled()
  })

  test('clears stale preview after preview failure', async () => {
    const api = { preview: mock(() => Promise.reject(new Error('preview failed'))), install: mock(() => Promise.resolve({ skipped: false, errors: [], warnings: [] })) }
    const renderer = render(api)

    await selectFile(renderer, new File(['package'], 'workflow.clouisle'))

    expect(JSON.stringify(renderer.toJSON())).not.toContain('Imported workflow')
    expect(renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.disabled).toBe(true)
  })

  test('keeps the dialog open when installation fails', async () => {
    const api = { preview: mock(() => Promise.resolve(preview)), install: mock(() => Promise.reject(new Error('install failed'))) }
    const onOpenChange = mock(() => undefined)
    const renderer = render(api, { onOpenChange })

    await selectFile(renderer, new File(['package'], 'workflow.clouisle'))
    await act(async () => renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.onClick())

    expect(onOpenChange).not.toHaveBeenCalled()
    expect(renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.disabled).toBe(false)
  })

  test('cleans preview state when the dialog closes', async () => {
    const api = { preview: mock(() => Promise.resolve(preview)), install: mock(() => Promise.resolve({ skipped: false, errors: [], warnings: [] })) }
    const renderer = render(api)

    await selectFile(renderer, new File(['package'], 'workflow.clouisle'))
    act(() => renderer.update(<ImportPackageDialog open={false} onOpenChange={mock(() => undefined)} teamId="team-1" api={api as never} />))

    expect(JSON.stringify(renderer.toJSON())).not.toContain('Imported workflow')
    expect(JSON.stringify(renderer.toJSON())).toContain('noFileSelected')
  })

  test('requires a target team before previewing', async () => {
    const api = { preview: mock(() => Promise.resolve(preview)), install: mock(() => Promise.resolve({ skipped: false, errors: [], warnings: [] })) }
    const renderer = render(api, { teamId: undefined, teams: [] })

    await selectFile(renderer, new File(['package'], 'workflow.clouisle'))

    expect(toast.error).toHaveBeenCalledWith('selectTargetTeam')
    expect(api.preview).not.toHaveBeenCalled()
  })

  test('renders preview problems and blocks mismatched resource imports', async () => {
    const problematicPreview = {
      ...preview,
      resource_type: 'agent' as const,
      valid: false,
      errors: ['broken_schema'],
      warnings: ['missing_optional_icon'],
      dependencies: [
        { type: 'model', source_id: 'model-1', name: 'GPT', status: 'resolved' as const, required: true },
        { type: 'custom', source_id: 'custom-1', name: '', status: 'missing' as const, required: false },
      ],
    }
    const api = { preview: mock(() => Promise.resolve(problematicPreview)), install: mock(() => Promise.resolve({ skipped: false, errors: [], warnings: [] })) }
    const renderer = render(api, { expectedResourceType: 'workflow' })

    await selectFile(renderer, new File(['package'], 'agent.clouisle'))
    const text = JSON.stringify(renderer.toJSON())

    expect(toast.error).toHaveBeenCalledWith('typeMismatch')
    expect(text).toContain('invalid')
    expect(text).toContain('broken_schema')
    expect(text).toContain('missing_optional_icon')
    expect(text).toContain('dependencyLabel')
    expect(text).toContain('dependencyStatus.resolved')
    expect(text).toContain('dependencyStatus.missing')
    expect(renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.disabled).toBe(true)
  })

  test('renames conflicting packages and reports skipped imports', async () => {
    const conflictPreview = {
      ...preview,
      conflict: { type: 'name' as const, existing_name: 'Imported workflow' },
      allowed_actions: ['rename', 'skip'] as const,
      default_action: 'rename' as const,
    }
    const api = { preview: mock(() => Promise.resolve(conflictPreview)), install: mock(() => Promise.resolve({ installed: null, updated: null, skipped: true, errors: [], warnings: [] })) }
    const onImported = mock(() => undefined)
    const onOpenChange = mock(() => undefined)
    const renderer = render(api, { onImported, onOpenChange })

    await selectFile(renderer, new File(['package'], 'workflow.clouisle'))
    const input = renderer.root.findAllByType('input').find((node) => node.props.value === 'Imported workflow')!
    act(() => input.props.onChange({ target: { value: 'Imported workflow copy' } }))
    await act(async () => renderer.root.findAllByType('button').find((button) => button.children.includes('install'))!.props.onClick())

    expect(api.install).toHaveBeenCalledWith('session-1', { action: 'rename', target_name: 'Imported workflow copy', dependency_mapping: {} })
    expect(toast.success).toHaveBeenCalledWith('importSkipped')
    expect(onImported).toHaveBeenCalledWith(null)
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })
})

import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const settings = {
  audit_log_retention_days: 365,
  audit_log_archive_path: '/tmp/audit-archives',
  kb_document_max_upload_size_mb: 10,
  upload_storage_backend: 'local',
  object_storage_endpoint: '',
  object_storage_bucket: '',
  object_storage_region: '',
  object_storage_access_key: '',
  object_storage_secret_key: '',
  object_storage_force_path_style: true,
  object_storage_secure: true,
}
const getAll = mock(() => Promise.resolve(settings))
const bulkUpdate = mock(() => Promise.resolve())
let canUpdate = true

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success: mock(() => {}), error: mock(() => {}) } }))
mock.module('lucide-react', () => ({
  Loader2: () => null,
  Archive: () => null,
  Database: () => null,
  FileText: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}))
mock.module('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input {...props} type="checkbox" />,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectTrigger: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  SelectValue: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/number-input', () => ({
  NumberInput: (props: Record<string, unknown>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children }: React.PropsWithChildren) => <label>{children}</label>,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button {...props}>{children}</button>
  ),
}))
mock.module('@/components/ui/skeleton', () => ({ Skeleton: () => <div /> }))
mock.module('@/components/ui/field', () => ({
  FieldError: ({ children }: React.PropsWithChildren) =>
    children ? <p role="alert">{children}</p> : null,
}))
mock.module('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: React.PropsWithChildren) => <>{children}</>,
  AlertDialogAction: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogCancel: ({ children }: React.PropsWithChildren) => <button>{children}</button>,
  AlertDialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: React.PropsWithChildren) => <footer>{children}</footer>,
  AlertDialogHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  AlertDialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: {
    getAll,
    bulkUpdate,
    archiveAuditLogs: mock(() => Promise.resolve({ task_id: 'task-1' })),
  },
}))
mock.module('@/components/permission-guard', () => ({
  useCanPerform: () => ({
    canPerform: (permission: string) => permission === 'audit:export' || canUpdate,
  }),
}))

const { default: SiteSettingsStoragePage } = await import('./page')

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const render = async () => {
  let renderer: ReactTestRenderer
  await act(async () => {
    renderer = create(<SiteSettingsStoragePage />)
  })
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
  settings.audit_log_retention_days = 365
})

test('blocks invalid audit retention before saving storage settings', async () => {
  settings.audit_log_retention_days = 29
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())

  expect(bulkUpdate).not.toHaveBeenCalled()
  expect(renderer.root.findByProps({ id: 'retentionDays' }).props['aria-invalid']).toBe(true)
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(1)
  act(() => renderer.unmount())
})

test('hides storage saves from viewers without update permission', async () => {
  canUpdate = false
  const renderer = await render()

  expect(renderer.root.findByProps({ id: 'retentionDays' }).props.disabled).toBe(true)
  expect(
    renderer.root.findAllByType('button').some((button) => button.children.includes('saveChanges')),
  ).toBe(false)
  act(() => renderer.unmount())
})

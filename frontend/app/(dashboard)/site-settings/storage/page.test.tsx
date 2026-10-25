import { afterEach, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const settings = {
  audit_log_retention_days: 365,
  audit_log_archive_path: '/tmp/audit-archives',
  kb_document_max_upload_size_mb: 50,
  upload_storage_backend: 'local',
  object_storage_endpoint: '',
  object_storage_bucket: '',
  object_storage_region: '',
  object_storage_access_key: '',
  object_storage_secret_key: '',
  object_storage_force_path_style: true,
  object_storage_secure: true,
}
const getAll = mock(() => Promise.resolve({ ...settings }))
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
  Switch: ({ checked, onCheckedChange, ...props }: Record<string, unknown>) => (
    <input
      {...props}
      type="checkbox"
      checked={Boolean(checked)}
      onChange={(event) => (onCheckedChange as ((value: boolean) => void) | undefined)?.(event.target.checked)}
    />
  ),
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
    <select
      id={props.id as string | undefined}
      value={String(props.value ?? '')}
      disabled={Boolean(props.disabled)}
      onChange={(event) => (props.onValueChange as ((value: string) => void) | undefined)?.(event.target.value)}
    >{children}</select>
  ),
  SelectContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value?: string }>) => <option value={value}>{children}</option>,
  SelectTrigger: () => null,
  SelectValue: () => null,
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
    await Promise.resolve()
    await Promise.resolve()
  })
  return renderer!
}

const saveButton = (renderer: ReactTestRenderer) =>
  renderer.root.findAllByType('button').find((button) => button.children.includes('saveChanges'))!

afterEach(() => {
  mock.clearAllMocks()
  canUpdate = true
  Object.assign(settings, {
    audit_log_retention_days: 365,
    audit_log_archive_path: '/tmp/audit-archives',
    kb_document_max_upload_size_mb: 50,
    upload_storage_backend: 'local',
    object_storage_endpoint: '',
    object_storage_bucket: '',
    object_storage_region: '',
    object_storage_access_key: '',
    object_storage_secret_key: '',
    object_storage_force_path_style: true,
    object_storage_secure: true,
  })
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

test('loads and saves object-storage configuration after editing its fields', async () => {
  Object.assign(settings, {
    upload_storage_backend: 's3',
    object_storage_endpoint: 'https://storage.example.test',
    object_storage_bucket: 'documents',
    object_storage_region: 'us-east-1',
    object_storage_access_key: 'old-access-key',
    object_storage_secret_key: 'old-secret-key',
    object_storage_force_path_style: false,
    object_storage_secure: true,
  })
  const renderer = await render()

  const backendSelect = renderer.root.findAllByType('select').find((node) => node.props.value === 'object')!
  expect(backendSelect.props.value).toBe('object')
  expect(renderer.root.findByProps({ id: 'objectStorageEndpoint' }).props.value).toBe('https://storage.example.test')
  expect(renderer.root.findByProps({ id: 'objectStorageSecretKey' }).props.type).toBe('password')

  await act(async () => {
    renderer.root.findByProps({ id: 'objectStorageEndpoint' }).props.onChange({ target: { value: 'https://new.example.test' } })
    renderer.root.findByProps({ id: 'objectStorageBucket' }).props.onChange({ target: { value: 'new-documents' } })
    renderer.root.findByProps({ id: 'objectStorageAccessKey' }).props.onChange({ target: { value: 'new-access-key' } })
    renderer.root.findByProps({ id: 'objectStorageSecretKey' }).props.onChange({ target: { value: 'new-secret-key' } })
    renderer.root.findByProps({ id: 'objectStorageSecure' }).props.onCheckedChange(false)
    renderer.root.findByProps({ id: 'objectStorageForcePathStyle' }).props.onCheckedChange(true)
  })

  await act(async () => saveButton(renderer).props.onClick())

  expect(bulkUpdate).toHaveBeenCalledWith(expect.objectContaining({
    upload_storage_backend: 'object',
    object_storage_endpoint: 'https://new.example.test',
    object_storage_bucket: 'new-documents',
    object_storage_region: 'us-east-1',
    object_storage_access_key: 'new-access-key',
    object_storage_secret_key: 'new-secret-key',
    object_storage_secure: false,
    object_storage_force_path_style: true,
  }))
  act(() => renderer.unmount())
})

test('requires each object-storage credential and clears its field error when corrected', async () => {
  settings.upload_storage_backend = 'object'
  const renderer = await render()

  await act(async () => saveButton(renderer).props.onClick())

  expect(bulkUpdate).not.toHaveBeenCalled()
  for (const id of ['objectStorageEndpoint', 'objectStorageBucket', 'objectStorageAccessKey', 'objectStorageSecretKey']) {
    expect(renderer.root.findByProps({ id }).props['aria-invalid']).toBe(true)
  }
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(4)

  await act(async () => {
    renderer.root.findByProps({ id: 'objectStorageEndpoint' }).props.onChange({ target: { value: 'https://storage.test' } })
  })
  expect(renderer.root.findByProps({ id: 'objectStorageEndpoint' }).props['aria-invalid']).toBe(false)
  expect(renderer.root.findAllByProps({ role: 'alert' })).toHaveLength(3)
  act(() => renderer.unmount())
})

test('normalizes unknown storage backend values to local and uses defaults for missing settings', async () => {
  Object.assign(settings, {
    upload_storage_backend: 'unknown',
    audit_log_retention_days: undefined,
    audit_log_archive_path: undefined,
    kb_document_max_upload_size_mb: undefined,
    object_storage_force_path_style: undefined,
    object_storage_secure: undefined,
  })
  const renderer = await render()

  const backendSelect = renderer.root.findAllByType('select')[0]
  expect(backendSelect.props.value).toBe('local')
  expect(renderer.root.findByProps({ id: 'retentionDays' }).props.value).toBe(365)
  expect(renderer.root.findByProps({ id: 'archivePath' }).props.value).toBe('/var/log/clouisle/audit_archives')
  expect(renderer.root.findByProps({ id: 'kbDocumentMaxUploadSize' }).props.value).toBe(50)
  expect(renderer.root.findAllByProps({ id: 'objectStorageSecure' })).toHaveLength(0)
  expect(renderer.root.findAllByProps({ id: 'objectStorageForcePathStyle' })).toHaveLength(0)

  await act(async () => backendSelect.props.onChange({ target: { value: 'object' } }))
  expect(renderer.root.findByProps({ id: 'objectStorageSecure' }).props.checked).toBe(true)
  expect(renderer.root.findByProps({ id: 'objectStorageForcePathStyle' }).props.checked).toBe(true)
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

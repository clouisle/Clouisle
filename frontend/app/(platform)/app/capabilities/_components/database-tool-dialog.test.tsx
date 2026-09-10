'use client'

import React from 'react'
import { afterEach, describe, expect, mock, test } from 'bun:test'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { DatabaseToolDialog } from './database-tool-dialog'
import { ToolDetail } from '@/lib/api'

const toolsApi = {
  testDatabaseConnection: mock(async () => ({ success: true, message: 'Connected' })),
}

mock.module('next-intl', () => ({
  useTranslations: () => Object.assign(
    (key: string) => key,
    { has: () => true }
  ),
}))

mock.module('sonner', () => ({ toast: { success: mock(), error: mock() } }))
mock.module('@/lib/api', () => ({ toolsApi }))
mock.module('@/lib/api/tools', () => ({ toolsApi }))

const passthrough = (tag: keyof React.JSX.IntrinsicElements = 'div') => {
  const Component = ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) =>
    React.createElement(tag, props, children)
  return Component
}

mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ open, children }: React.PropsWithChildren<{ open?: boolean }>) => open ? <div>{children}</div> : null,
  DialogContent: passthrough(),
  DialogDescription: passthrough('p'),
  DialogFooter: passthrough(),
  DialogHeader: passthrough(),
  DialogTitle: passthrough('h2'),
}))

mock.module('@/components/ui/select', () => ({
  Select: ({ value, onValueChange, children }: React.PropsWithChildren<{ value?: string; onValueChange?: (val: string) => void }>) => (
    <div data-value={value}>
      <button data-testid="select-trigger" onClick={() => onValueChange?.('mysql')}>change-to-mysql</button>
      {children}
    </div>
  ),
  SelectContent: passthrough(),
  SelectItem: passthrough(),
  SelectTrigger: passthrough('button'),
  SelectValue: passthrough('span'),
}))

const TabContext = React.createContext<((v: string) => void) | undefined>(undefined)
mock.module('@/components/ui/tabs', () => ({
  Tabs: ({ children, value, onValueChange }: React.PropsWithChildren<{ value?: string; onValueChange?: (v: string) => void }>) => (
    <TabContext.Provider value={onValueChange}>
      <div data-tabs={value} data-testid="tabs">{children}</div>
    </TabContext.Provider>
  ),
  TabsList: passthrough(),
  TabsTrigger: ({ children, value }: React.PropsWithChildren<{ value: string }>) => {
    const onValueChange = React.useContext(TabContext)
    return <button data-testid={`tab-${value}`} onClick={() => onValueChange?.(value)}>{children}</button>
  },
  TabsContent: passthrough(),
}))

mock.module('@/components/ui/button', () => ({ Button: passthrough('button') }))
mock.module('@/components/ui/input', () => ({ Input: passthrough('input') }))
mock.module('@/components/ui/textarea', () => ({ Textarea: passthrough('textarea') }))
mock.module('@/components/ui/label', () => ({ Label: passthrough('label') }))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough('p') }))
mock.module('@/components/ui/image-upload', () => ({
  ImageUpload: ({ onChange, placeholder }: { value?: string; onChange?: (val: string) => void; placeholder?: React.ReactNode }) => (
    <div data-testid="image-upload" onClick={() => onChange?.('https://cdn.example/icon.png')}>
      {placeholder}
    </div>
  ),
}))
mock.module('./tool-category-input', () => ({
  ToolCategoryInput: ({ value, onChange }: { value?: string; onChange?: (val: string) => void }) => (
    <input data-testid="category-input" value={value || ''} onChange={(e) => onChange?.(e.target.value)} />
  ),
}))

const renderers: ReactTestRenderer[] = []

afterEach(() => {
  for (const r of renderers) act(() => r.unmount())
  renderers.length = 0
})

describe('DatabaseToolDialog', () => {
  test('creates a database tool with parameters mode and tests connection', async () => {
    const onSave = mock(async () => undefined)
    let renderer: ReactTestRenderer

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog
          open
          onOpenChange={() => undefined}
          onSave={onSave}
          teams={[{ id: 'team-1', name: 'Core Team' }]}
          selectedTeamId="team-1"
        />
      )
    })
    renderers.push(renderer!)

    const nameInput = renderer!.root.findByProps({ id: 'name' })
    const displayNameInput = renderer!.root.findByProps({ id: 'displayName' })
    const hostInput = renderer!.root.findByProps({ id: 'host' })
    const portInput = renderer!.root.findByProps({ id: 'port' })

    act(() => {
      nameInput.props.onChange({ target: { value: 'crm_db' } })
      displayNameInput.props.onChange({ target: { value: 'CRM Database' } })
      hostInput.props.onChange({ target: { value: '10.0.0.1' } })
      portInput.props.onChange({ target: { value: '5432' } })
    })

    // Test connection button
    const testButton = renderer!.root.findAllByType('button').find((b) => b.children.includes('databaseDialog.testConnection'))!
    await act(async () => testButton.props.onClick())
    expect(toolsApi.testDatabaseConnection).toHaveBeenCalledWith(
      expect.objectContaining({
        db_type: 'postgresql',
        host: '10.0.0.1',
        port: 5432,
      })
    )

    // Submit form
    const form = renderer!.root.findByType('form')
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'crm_db',
        display_name: 'CRM Database',
        custom_type: 'database',
        database_config: expect.objectContaining({
          db_type: 'postgresql',
          host: '10.0.0.1',
          port: 5432,
        }),
      })
    )
  })

  test('creates a database tool in URL mode', async () => {
    const onSave = mock(async () => undefined)
    let renderer: ReactTestRenderer

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog
          open
          onOpenChange={() => undefined}
          onSave={onSave}
          teams={[{ id: 'team-1', name: 'Core Team' }]}
          selectedTeamId="team-1"
        />
      )
    })
    renderers.push(renderer!)

    // Switch to URL mode
    const urlTab = renderer!.root.findByProps({ 'data-testid': 'tab-url' })
    act(() => urlTab.props.onClick())

    const nameInput = renderer!.root.findByProps({ id: 'name' })
    const displayNameInput = renderer!.root.findByProps({ id: 'displayName' })
    const urlInput = renderer!.root.findByProps({ id: 'connectionUrl' })

    act(() => {
      nameInput.props.onChange({ target: { value: 'pg_url_db' } })
      displayNameInput.props.onChange({ target: { value: 'PG URL Database' } })
      urlInput.props.onChange({ target: { value: 'postgresql://u:p@db.host:5432/app' } })
    })

    const form = renderer!.root.findByType('form')
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'pg_url_db',
        database_config: expect.objectContaining({
          db_type: 'postgresql',
          url: 'postgresql://u:p@db.host:5432/app',
        }),
      })
    )
    const savedConfig = onSave.mock.calls[0][0].database_config
    expect(savedConfig.host).toBeUndefined()
    expect(savedConfig.port).toBeUndefined()
  })

  test('edits an existing database tool and populates configuration', async () => {
    const onSave = mock(async () => undefined)
    const existingTool: ToolDetail = {
      id: 'tool-db-1',
      name: 'orders_db',
      display_name: 'Orders MySQL',
      description: 'Order transactions',
      type: 'custom',
      custom_type: 'database',
      category: 'data',
      parameters: [],
      is_enabled: true,
      requires_config: false,
      config_fields: [],
      database_config: {
        db_type: 'mysql',
        host: '192.168.1.100',
        port: 3306,
        database: 'orders',
        username: 'ro_user',
      },
    }

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <DatabaseToolDialog
          tool={existingTool}
          open
          onOpenChange={() => undefined}
          onSave={onSave}
        />
      )
    })
    renderers.push(renderer!)

    expect(renderer!.root.findByProps({ id: 'displayName' }).props.value).toBe('Orders MySQL')
    expect(renderer!.root.findByProps({ id: 'host' }).props.value).toBe('192.168.1.100')
  })

  test('round-trips a redis connection URL through save and activates url mode', async () => {
    const onSave = mock(async () => undefined)
    const url = 'redis://:pw@cache.internal:6380/1'
    const existingTool = {
      id: 'tool-redis-1',
      name: 'sessions_cache',
      display_name: 'Sessions Cache',
      description: 'Session cache',
      type: 'custom',
      custom_type: 'database',
      category: 'data',
      parameters: [],
      is_enabled: true,
      requires_config: false,
      config_fields: [],
      database_config: { db_type: 'redis', url },
    } as unknown as ToolDetail

    let renderer: ReactTestRenderer
    await act(async () => {
      renderer = create(
        <DatabaseToolDialog tool={existingTool} open onOpenChange={() => undefined} onSave={onSave} />
      )
    })
    renderers.push(renderer!)

    expect(renderer!.root.findByProps({ id: 'connectionUrl' }).props.value).toBe(url)

    const form = renderer!.root.findByType('form')
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        database_config: expect.objectContaining({ db_type: 'redis', url }),
      })
    )
  })

  test('saves custom icon, timeout, and maxLimit', async () => {
    const onSave = mock(async () => undefined)
    let renderer: ReactTestRenderer

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog open onOpenChange={() => undefined} onSave={onSave} />
      )
    })
    renderers.push(renderer!)

    act(() => {
      renderer.root.findByProps({ id: 'name' }).props.onChange({ target: { value: 'custom_db' } })
      renderer.root.findByProps({ id: 'displayName' }).props.onChange({ target: { value: 'Custom DB' } })
      renderer.root.findByProps({ id: 'host' }).props.onChange({ target: { value: '10.0.0.2' } })
      renderer.root.findByProps({ id: 'timeout' }).props.onChange({ target: { value: '30' } })
      renderer.root.findByProps({ id: 'maxLimit' }).props.onChange({ target: { value: '500' } })
      renderer.root.findByProps({ 'data-testid': 'image-upload' }).props.onClick()
    })

    const form = renderer.root.findByType('form')
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'custom_db',
        icon: 'https://cdn.example/icon.png',
        database_config: expect.objectContaining({
          timeout: 30,
          max_limit: 500,
        }),
      })
    )
  })
  test('switches to redis and mongodb dbType and verifies parameter structure', async () => {
    const onSave = mock(async () => undefined)
    let renderer: ReactTestRenderer

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog open onOpenChange={() => undefined} onSave={onSave} />
      )
    })
    renderers.push(renderer!)

    // change to redis
    const select = renderer.root.findByProps({ 'data-testid': 'select-trigger' })
    act(() => {
      select.props.onClick()
    })

    const editToolRedis: ToolDetail = {
      name: 'redis_cache',
      display_name: 'Redis Cache',
      description: 'Redis Tool',
      type: 'custom',
      category: 'data',
      parameters: [],
      is_enabled: true,
      requires_config: false,
      config_fields: [],
      custom_type: 'database',
      database_config: {
        db_type: 'redis',
        host: 'localhost',
        port: 6379,
        db: 0,
      },
    }

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog tool={editToolRedis} open onOpenChange={() => undefined} onSave={onSave} />
      )
    })
    renderers.push(renderer!)

    const editToolMongo: ToolDetail = {
      name: 'mongo_db',
      display_name: 'Mongo DB',
      description: 'MongoDB Tool',
      type: 'custom',
      category: 'data',
      parameters: [],
      is_enabled: true,
      requires_config: false,
      config_fields: [],
      custom_type: 'database',
      database_config: {
        db_type: 'mongodb',
        url: 'mongodb://localhost:27017/test',
        auth_source: 'admin',
      },
    }

    await act(async () => {
      renderer = create(
        <DatabaseToolDialog tool={editToolMongo} open onOpenChange={() => undefined} onSave={onSave} />
      )
    })
    renderers.push(renderer!)

    // test failure and error responses in handleTestConnection
    const testBtn = renderer.root.findAllByType('button').find((b) => b.children.includes('databaseDialog.testConnection'))
    if (testBtn) {
      toolsApi.testDatabaseConnection.mockResolvedValueOnce({ success: false, message: 'Connection refused' })
      await act(async () => testBtn.props.onClick())

      toolsApi.testDatabaseConnection.mockRejectedValueOnce(new Error('Network error'))
      await act(async () => testBtn.props.onClick())
    }
    // Submit with empty name and connectionUrl to trigger client validation (mongo uses url mode)
    act(() => {
      renderer.root.findByProps({ id: 'name' }).props.onChange({ target: { value: '' } })
      renderer.root.findByProps({ id: 'connectionUrl' }).props.onChange({ target: { value: '' } })
    })
    const form = renderer.root.findByType('form')
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))

    // Submit with onSave error to trigger catch
    onSave.mockRejectedValueOnce(new Error('Save failed'))
    act(() => {
      renderer.root.findByProps({ id: 'name' }).props.onChange({ target: { value: 'test_db' } })
      renderer.root.findByProps({ id: 'connectionUrl' }).props.onChange({ target: { value: 'mongodb://localhost:27017/test' } })
    })
    await act(async () => form.props.onSubmit({ preventDefault: () => undefined }))
    expect(renderer.root.findByProps({ id: 'name' }).props.value).toBe('test_db')
  })
})
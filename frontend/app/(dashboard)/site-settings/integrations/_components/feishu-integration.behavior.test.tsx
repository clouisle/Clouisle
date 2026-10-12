import { afterEach, describe, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

const success = mock(() => {})
const error = mock(() => {})

const translateCalls: Array<[string, Record<string, unknown> | undefined]> = []
const translate = (key: string, values?: Record<string, unknown>) => {
  translateCalls.push([key, values])
  return key
}

mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('sonner', () => ({ toast: { success, error } }))
mock.module('lucide-react', () => ({
  ChevronDown: () => null,
  ChevronRight: () => null,
  Loader2: () => null,
  MessageSquareText: () => null,
  RefreshCw: () => null,
  Save: () => null,
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <section>{children}</section>,
  CardContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  CardDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
  CardHeader: ({ children }: React.PropsWithChildren) => <header>{children}</header>,
  CardTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
}))
mock.module('@/components/ui/input', () => ({ Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: ({ children, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props}>{children}</label> }))
mock.module('@/components/ui/button', () => ({ Button: ({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props}>{children}</button> }))
mock.module('@/components/ui/checkbox', () => ({
  Checkbox: ({ onCheckedChange, checked, ...props }: { onCheckedChange?: (value: boolean) => void; checked?: boolean }) => (
    <input
      type="checkbox"
      checked={Boolean(checked)}
      onChange={(event) => onCheckedChange?.(event.target.checked)}
      {...props}
    />
  ),
}))
mock.module('@/components/ui/scroll-area', () => ({ ScrollArea: ({ children }: React.PropsWithChildren) => <div>{children}</div> }))

import { siteSettingsApi, type FeishuConfig } from '@/lib/api/admin/site-settings'
import { ApiError } from '@/lib/api/client'
import { FeishuIntegrationTab } from './feishu-integration'

globalThis.IS_REACT_ACT_ENVIRONMENT = true

const config: FeishuConfig = { app_id: 'cli_1', app_secret_configured: true, department_ids: ['dept-a'] }

const renderers: ReactTestRenderer[] = []

function render() {
  const onConfigChange = mock(() => {})
  let renderer: ReactTestRenderer
  act(() => {
    renderer = create(<FeishuIntegrationTab config={config} onConfigChange={onConfigChange} canUpdate />)
  })
  renderers.push(renderer!)
  return { renderer: renderer!, onConfigChange }
}

const button = (renderer: ReactTestRenderer, label: string) => renderer.root.findAllByType('button').find((item) => item.children.includes(label))!

afterEach(() => {
  for (const renderer of renderers) act(() => renderer.unmount())
  renderers.length = 0
  mock.restore()
  success.mockClear()
  error.mockClear()
  translateCalls.length = 0
})

describe('FeishuIntegrationTab', () => {
  test('reports account and team counts after a successful sync', async () => {
    spyOn(siteSettingsApi, 'getFeishuDepartments').mockResolvedValue([])
    const syncFeishuContacts = spyOn(siteSettingsApi, 'syncFeishuContacts')
      .mockResolvedValue({ created: 3, updated: 1, skipped: 2, teams_created: 4 })
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(syncFeishuContacts).toHaveBeenCalledTimes(1)
    expect(translateCalls).toContainEqual(['integrations.feishuSyncResult', { created: 3, updated: 1, skipped: 2, teams_created: 4 }])
    expect(success).toHaveBeenCalledWith('integrations.feishuSyncResult')
    expect(error).not.toHaveBeenCalled()
  })

  test('leaves backend-reported sync failures to the global error toast', async () => {
    spyOn(siteSettingsApi, 'getFeishuDepartments').mockResolvedValue([])
    spyOn(siteSettingsApi, 'syncFeishuContacts').mockRejectedValue(new ApiError(1002, 'Feishu API HTTP 400 (code 41050): no user authority error'))
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(error).not.toHaveBeenCalled()
    expect(success).not.toHaveBeenCalled()
  })

  test('shows a localized fallback when the sync fails before the API answers', async () => {
    spyOn(siteSettingsApi, 'getFeishuDepartments').mockResolvedValue([])
    spyOn(siteSettingsApi, 'syncFeishuContacts').mockRejectedValue(new Error('Failed to fetch'))
    const { renderer } = render()

    await act(async () => button(renderer, 'integrations.feishuSync').props.onClick())

    expect(error).toHaveBeenCalledWith('integrations.feishuSyncFailed')
  })

  test('shows the Feishu company name returned by the department API', async () => {
    spyOn(siteSettingsApi, 'getFeishuDepartments').mockResolvedValue([
      { department_id: '0', name: 'Acme Ltd.', parent_department_id: null, children: [] },
    ])
    const { renderer } = render()

    await act(async () => {})

    expect(renderer.root.findAllByType('span').some((item) => item.children.includes('Acme Ltd.'))).toBe(true)
    expect(renderer.root.findAllByType('span').some((item) => item.children.includes('integrations.feishuCompany'))).toBe(false)
  })

})

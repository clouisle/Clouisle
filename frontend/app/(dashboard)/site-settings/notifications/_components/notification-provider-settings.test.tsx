import { expect, mock, test } from 'bun:test'

const elements: Record<string, unknown>[] = []
const jsx = (type: unknown, props: Record<string, unknown>) => {
  elements.push(props)
  return { type, props }
}
const success = mock(() => {})
const updateSlack = mock(async () => {})
const sendTestSlack = mock(async () => {})
const updateFeishu = mock(async () => {})
const sendTestFeishu = mock(async () => {})
const updateDingTalk = mock(async () => {})
const sendTestDingTalk = mock(async () => {})
const updateWeChat = mock(async () => {})
const sendTestWeChat = mock(async () => {})

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({
  useState: <T,>(value: T) => [value, mock(() => {})],
  useMemo: <T,>(factory: () => T) => factory(),
}))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('sonner', () => ({ toast: { success } }))
mock.module('lucide-react', () => ({ Loader2: () => null, ExternalLink: () => null }))
const passthrough = ({ children }: { children?: unknown }) => children
const render = (node: unknown): void => {
  if (!node || typeof node !== 'object') return
  const { type, props } = node as { type?: (props: Record<string, unknown>) => unknown; props?: Record<string, unknown> }
  if (typeof type === 'function') render(type(props ?? {}))
  for (const child of Array.isArray(props?.children) ? props.children : [props?.children]) render(child)
}
mock.module('@/components/ui/card', () => ({
  Card: passthrough, CardContent: passthrough, CardDescription: passthrough, CardHeader: passthrough, CardTitle: passthrough,
}))
mock.module('@/components/ui/input', () => ({ Input: () => null }))
mock.module('@/components/ui/label', () => ({ Label: passthrough }))
mock.module('@/components/ui/button', () => ({ Button: passthrough }))
mock.module('@/components/ui/switch', () => ({ Switch: () => null }))
mock.module('@/components/ui/select', () => ({
  Select: passthrough, SelectContent: passthrough, SelectItem: passthrough, SelectTrigger: passthrough, SelectValue: passthrough,
}))
mock.module('@/components/ui/field', () => ({ FieldError: passthrough }))
mock.module('@/lib/api/admin/site-settings', () => ({
  siteSettingsApi: { updateSlack, sendTestSlack, updateFeishu, sendTestFeishu, updateDingTalk, sendTestDingTalk, updateWeChat, sendTestWeChat },
}))
mock.module('@/lib/validation', () => ({
  clearValidationError: (errors: Record<string, string>, key: string) => {
    const { [key]: _error, ...remaining } = errors
    return remaining
  },
  getValidationSummaryEntries: (errors: Record<string, string>) => Object.entries(errors),
  normalizeValidationErrors: (error: { errors?: Record<string, string> }) => error.errors ?? {},
  mapValidationErrors: (errors: Record<string, string>) => errors,
  formatValidationSummaryMessage: (_field: string, message: string) => message,
}))

const { SlackSettingsTab } = await import('./slack-settings')
const { FeishuSettingsTab } = await import('./feishu-settings')
const { DingTalkSettingsTab } = await import('./dingtalk-settings')
const { WeChatSettingsTab } = await import('./wechat-settings')

type Node = { props?: Record<string, unknown> }

function find(node: unknown, predicate: (props: Record<string, unknown>) => boolean): Record<string, unknown> {
  if (!node || typeof node !== 'object') throw new Error('element not found')
  const { props, type } = node as Node & { type?: unknown }
  if (props && predicate(props)) return props
  if (typeof type === 'function') {
    try { return find((type as (props: Record<string, unknown>) => unknown)(props ?? {}), predicate) } catch { /* continue */ }
  }
  if (typeof type === 'function' && props?.children) {
    try { return find(props.children, predicate) } catch { /* continue */ }
  }
  for (const child of Array.isArray(props?.children) ? props.children : [props?.children]) {
    try { return find(child, predicate) } catch { /* continue */ }
  }
  throw new Error('element not found')
}

const click = async (tree: unknown, label: string) => {
  render(tree)
  const props = elements.findLast((props) =>
    props.children === label || (Array.isArray(props.children) && props.children.includes(label))
  )
  if (!props) throw new Error(`missing ${label}`)
  await (props.onClick as () => Promise<void>)()
}

const slack = { slack_enabled: true, slack_webhook_url: '' }
const feishu = { feishu_enabled: true, feishu_notification_type: 'app' as const, feishu_webhook_url: '', feishu_secret: '', feishu_app_id: '', feishu_app_secret: '' }
const dingtalk = { dingtalk_enabled: true, dingtalk_notification_type: 'app' as const, dingtalk_webhook_url: '', dingtalk_secret: '', dingtalk_app_key: '', dingtalk_app_secret: '', dingtalk_agent_id: '' }
const wechat = { wechat_enabled: true, wechat_notification_type: 'webhook' as const, wechat_webhook_url: 'https://wechat.example', wechat_corp_id: '', wechat_agent_id: '', wechat_secret: '' }

test('Slack validates before provider APIs and saves valid settings', async () => {
  const invalid = SlackSettingsTab({ settings: slack, onSettingsChange: mock(() => {}), canUpdate: true })
  await click(invalid, 'save')
  await click(invalid, 'slack.sendTest')
  expect(updateSlack).not.toHaveBeenCalled()
  expect(sendTestSlack).not.toHaveBeenCalled()

  const validSettings = { ...slack, slack_webhook_url: 'https://hooks.slack.com/test' }
  const valid = SlackSettingsTab({ settings: validSettings, onSettingsChange: mock(() => {}), canUpdate: true })
  await click(valid, 'save')
  expect(updateSlack).toHaveBeenCalledWith(validSettings)
  expect(success).toHaveBeenCalledWith('saveSuccess')
})

test('Feishu and DingTalk enforce app credentials before saving or testing', async () => {
  const feishuTree = FeishuSettingsTab({ settings: feishu, onSettingsChange: mock(() => {}), canUpdate: true })
  const dingtalkTree = DingTalkSettingsTab({ settings: dingtalk, onSettingsChange: mock(() => {}), canUpdate: true })
  await click(feishuTree, 'feishu.sendTest')
  await click(dingtalkTree, 'save')
  expect(sendTestFeishu).not.toHaveBeenCalled()
  expect(updateDingTalk).not.toHaveBeenCalled()
})

test('WeChat saves and sends a mocked provider test without a network request', async () => {
  const tree = WeChatSettingsTab({ settings: wechat, onSettingsChange: mock(() => {}), canUpdate: true })
  await click(tree, 'save')
  await click(tree, 'wechat.sendTest')
  expect(updateWeChat).toHaveBeenCalledWith(wechat)
  expect(sendTestWeChat).toHaveBeenCalledTimes(1)
  expect(success).toHaveBeenCalledWith('wechat.testSent')
})

test('provider API failures stay contained and do not show success', async () => {
  const error = { errors: { slack_webhook_url: 'rejected' } }
  updateSlack.mockImplementationOnce(async () => { throw error })
  const tree = SlackSettingsTab({ settings: { ...slack, slack_webhook_url: 'https://hooks.slack.com/test' }, onSettingsChange: mock(() => {}), canUpdate: true })
  const previousSuccesses = success.mock.calls.length
  await click(tree, 'save')
  expect(success.mock.calls.length).toBe(previousSuccesses)
})

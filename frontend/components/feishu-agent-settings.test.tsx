import { afterEach, beforeEach, expect, mock, spyOn, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'
import { feishuAgentApi, type FeishuAgentPreference } from '@/lib/api/feishu-agent'

const translate = (key: string) => key
mock.module('next-intl', () => ({ useTranslations: () => translate }))
mock.module('lucide-react', () => ({ HelpCircle: () => null, Loader2: () => null, RefreshCw: () => null }))
mock.module('@/components/ui/button', () => ({ Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} /> }))
mock.module('@/components/ui/label', () => ({ Label: (props: React.LabelHTMLAttributes<HTMLLabelElement>) => <label {...props} /> }))
mock.module('@/components/ui/alert', () => ({
  Alert: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  AlertDescription: 'p',
}))
mock.module('@/components/ui/card', () => ({
  Card: ({ children }: React.PropsWithChildren) => <>{children}</>,
  CardContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/switch', () => ({ Switch: ({ onCheckedChange, checked, ...props }: { onCheckedChange: (value: boolean) => void; checked: boolean }) => <button role="switch" aria-checked={checked} onClick={() => onCheckedChange(!checked)} {...props} /> }))
mock.module('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} />,
  TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
}))
mock.module('@/components/ui/select', () => ({
  Select: ({ children, ...props }: React.PropsWithChildren) => <div data-testid="select" {...props}>{children}</div>,
  SelectTrigger: (props: React.ButtonHTMLAttributes<HTMLButtonElement>) => <button {...props} />,
  SelectValue: ({ children }: React.PropsWithChildren) => <span data-testid="value">{children}</span>,
  SelectContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  SelectItem: ({ children, value }: React.PropsWithChildren<{ value: string }>) => <div data-option={value}>{children}</div>,
}))
import { FeishuAgentSettings } from './feishu-agent-settings'
const initial: FeishuAgentPreference = { enabled: true, is_enabled: true, linked: true, agent_id: 'a', agent_name: 'Support', agent_available: true }
const renderers: ReactTestRenderer[] = []
async function render() {
  let renderer: ReactTestRenderer
  act(() => { renderer = create(<FeishuAgentSettings />) })
  renderers.push(renderer!)
  await act(async () => {})
  return renderer!
}
const button = (r: ReactTestRenderer, text: string) => r.root.findAllByType('button').find(b => b.children.includes(text))!
beforeEach(() => {
  spyOn(feishuAgentApi, 'config').mockResolvedValue(initial)
  spyOn(feishuAgentApi, 'agents').mockResolvedValue([
    { id: 'a', name: 'Support', team_name: 'Team', description: '' },
    { id: 'b', name: 'Sales', team_name: 'Team', description: '' },
  ])
})
afterEach(() => { for (const r of renderers) act(() => r.unmount()); renderers.length = 0; mock.restore() })

test('uses human labels and preserves saved choice on failed save', async () => {
  const update = spyOn(feishuAgentApi, 'update').mockRejectedValue(new Error('offline'))
  const r = await render()
  expect(r.root.findByProps({ 'data-testid': 'value' }).children).toEqual(['Support · Team'])
  expect(r.root.findByProps({ 'data-option': 'a' }).children).toEqual(['Support · Team'])
  expect(button(r, 'save').props.disabled).toBe(true)
  act(() => r.root.findByProps({ 'data-testid': 'select' }).props.onValueChange('b'))
  await act(async () => button(r, 'save').props.onClick())
  expect(update).toHaveBeenCalledWith('b')
  expect(r.root.findByProps({ role: 'alert' }).children).toEqual(['failed'])
  expect(button(r, 'save').props.disabled).toBe(false)
  update.mockResolvedValue({ ...initial, agent_id: 'b', agent_name: 'Sales' })
  await act(async () => button(r, 'save').props.onClick())
  expect(button(r, 'save').props.disabled).toBe(true)
  expect(r.root.findByProps({ 'data-testid': 'value' }).children).toEqual(['Sales · Team'])
})

test('clearing a selection remains available when channel is paused', async () => {
  spyOn(feishuAgentApi, 'config').mockResolvedValue({ ...initial, enabled: false })
  spyOn(feishuAgentApi, 'agents').mockResolvedValue([])
  const update = spyOn(feishuAgentApi, 'update').mockResolvedValue({ ...initial, enabled: false, agent_id: null, agent_name: null, agent_available: false })
  const r = await render()
  expect(r.root.findByProps({ 'data-testid': 'select' }).props.disabled).toBe(true)
  await act(async () => button(r, 'clear').props.onClick())
  expect(update).toHaveBeenCalledWith(null)
  expect(button(r, 'clear').props.disabled).toBe(true)
})

test('unlinked users cannot select or save an Agent', async () => {
  spyOn(feishuAgentApi, 'config').mockResolvedValue({ ...initial, linked: false, agent_id: null, agent_available: false })
  const r = await render()
  expect(r.root.findByProps({ 'data-testid': 'select' }).props.disabled).toBe(true)
  expect(button(r, 'save').props.disabled).toBe(true)
  expect(button(r, 'clear').props.disabled).toBe(true)
})

test('personal switch persists immediately without clearing the selected Agent', async () => {
  const toggle = spyOn(feishuAgentApi, 'setEnabled').mockResolvedValue({ ...initial, is_enabled: false })
  const r = await render()
  await act(async () => r.root.findByProps({ role: 'switch' }).props.onClick())
  expect(toggle).toHaveBeenCalledWith(false)
  expect(r.root.findByProps({ role: 'switch' }).props['aria-checked']).toBe(false)
  expect(r.root.findByProps({ 'data-testid': 'value' }).children).toEqual(['Support · Team'])
  toggle.mockResolvedValue(initial)
  await act(async () => r.root.findByProps({ role: 'switch' }).props.onClick())
  expect(r.root.findByProps({ role: 'switch' }).props['aria-checked']).toBe(true)
})

test('failed switch update retains saved state and permits retry', async () => {
  spyOn(feishuAgentApi, 'setEnabled').mockRejectedValue(new Error('offline'))
  const r = await render()
  await act(async () => r.root.findByProps({ role: 'switch' }).props.onClick())
  expect(r.root.findByProps({ role: 'switch' }).props['aria-checked']).toBe(true)
  expect(r.root.findByProps({ role: 'switch' }).props.disabled).toBe(false)
  expect(r.root.findByProps({ role: 'alert' }).children).toEqual(['failed'])
})

test.each([
  [{ enabled: false, linked: false, agent_id: null, agent_available: false, is_enabled: false }, 'disabled'],
  [{ linked: false, agent_id: null, agent_available: false, is_enabled: false }, 'unlinked'],
  [{ agent_available: false, is_enabled: false }, 'unavailable'],
  [{ agent_id: null, agent_available: false, is_enabled: false }, 'selectBeforeEnable'],
] as const)('shows only the first actionable setup blocker: %j', async (overrides, expected) => {
  spyOn(feishuAgentApi, 'config').mockResolvedValue({ ...initial, ...overrides })
  const r = await render()
  const statuses = r.root.findAllByProps({ role: 'status' })
  expect(statuses).toHaveLength(1)
  expect(statuses[0]!.children).toEqual([expected])
})

test('reports an empty candidate list instead of suggesting an impossible selection', async () => {
  spyOn(feishuAgentApi, 'config').mockResolvedValue({ ...initial, agent_id: null, agent_available: false, is_enabled: false })
  spyOn(feishuAgentApi, 'agents').mockResolvedValue([])
  const r = await render()
  expect(r.root.findByProps({ role: 'status' }).children).toEqual(['empty'])
  expect(r.root.findByProps({ role: 'switch' }).props.disabled).toBe(true)
  expect(button(r, 'save').props.disabled).toBe(true)
})

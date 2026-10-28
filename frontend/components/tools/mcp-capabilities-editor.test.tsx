import { afterEach, describe, expect, mock, test } from 'bun:test'
import React from 'react'
import { act, create, type ReactTestRenderer } from '@/test-utils/rtl-renderer'

mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('lucide-react', () => ({
  AlertCircle: () => null, ChevronDown: () => null, Loader2: () => null,
  Plus: () => null, RefreshCw: () => null, Trash2: () => null,
}))
mock.module('@/components/ui/button', () => ({
  Button: ({ children, ...props }: React.ComponentProps<'button'>) => <button {...props}>{children}</button>,
}))
mock.module('@/components/ui/input', () => ({
  Input: (props: React.ComponentProps<'input'>) => <input {...props} />,
}))
mock.module('@/components/ui/label', () => ({
  Label: ({ children, ...props }: React.ComponentProps<'label'>) => <label {...props}>{children}</label>,
}))
mock.module('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange, id }: { checked: boolean; onCheckedChange: (value: boolean) => void; id?: string }) => (
    <input id={id} type="checkbox" checked={checked} onChange={(event) => onCheckedChange(event.target.checked)} />
  ),
}))

// Dynamic import applies the module mocks before the editor loads.
const {
  DEFAULT_MCP_CAPABILITIES,
  McpCapabilitiesEditor,
  getMcpCapabilities,
  hasMcpCapabilityErrors,
  mcpCapabilitiesConfig,
  validateMcpCapabilities,
} = await import('./mcp-capabilities-editor')

const messages = {
  invalidRoot: 'invalid-root',
  invalidHost: 'invalid-host',
  missingAllowlist: 'missing-allowlist',
  rootNotAllowed: 'root-not-allowed',
}

let renderer: ReactTestRenderer | undefined
let latest = getMcpCapabilities(null)

afterEach(() => {
  if (renderer) act(() => renderer.unmount())
  renderer = undefined
  latest = getMcpCapabilities(null)
})

function Harness() {
  const [value, setValue] = React.useState(getMcpCapabilities(null))
  React.useEffect(() => {
    latest = value
  }, [value])
  return <McpCapabilitiesEditor value={value} onChange={setValue} />
}

async function render() {
  await act(async () => {
    renderer = create(<Harness />)
  })
}

describe('McpCapabilitiesEditor', () => {
  test('keeps capabilities off and omits default fields from saved config', async () => {
    await render()
    expect(latest.enable_sampling).toBe(false)
    expect(latest.enable_elicitation).toBe(false)
    expect(mcpCapabilitiesConfig(DEFAULT_MCP_CAPABILITIES)).toEqual({})

    const sampling = renderer!.root.findByProps({ id: 'mcp-enable-sampling' })
    await act(async () => sampling.props.onCheckedChange(true))
    expect(latest.enable_sampling).toBe(true)
    expect(mcpCapabilitiesConfig(latest)).toEqual(expect.objectContaining({ enable_sampling: true }))
  })

  test('rejects non-host elicitation entries and roots outside the allowlist', async () => {
    await render()
    const hosts = renderer!.root.findByProps({ id: 'mcp-elicitation-hosts' })
    await act(async () => hosts.props.onChange({ target: { value: 'https://evil.example/path' } }))
    expect(latest.elicitation_url_hosts).toEqual(['https://evil.example/path'])
    expect(validateMcpCapabilities(latest, messages)).toEqual({
      roots: {},
      hosts: [0],
      allowlist: null,
    })

    await act(async () => hosts.props.onChange({ target: { value: 'auth.example.com\n' } }))
    expect(hasMcpCapabilityErrors(validateMcpCapabilities(latest, messages))).toBe(false)

    await act(async () => (Array.from(document.querySelectorAll('button')).find((button) => button.textContent === 'addRoot')!).click())
    const uri = renderer!.root.findByProps({ placeholder: 'rootUriPlaceholder' })
    await act(async () => uri.props.onChange({ target: { value: 'relative/path' } }))
    expect(validateMcpCapabilities(latest, messages).roots[0]).toBe('invalid-root')

    await act(async () => uri.props.onChange({ target: { value: 'file:///workspace/project' } }))
    expect(validateMcpCapabilities(latest, messages).allowlist).toBe('missing-allowlist')

    const allowlist = renderer!.root.findByProps({ id: 'mcp-roots-allowlist' })
    await act(async () => allowlist.props.onChange({ target: { value: 'file:///workspace' } }))
    expect(hasMcpCapabilityErrors(validateMcpCapabilities(latest, messages))).toBe(false)
    expect(document.body.textContent).not.toContain('invalid-root')
  })
})

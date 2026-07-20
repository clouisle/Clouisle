import { beforeEach, describe, expect, mock, test } from 'bun:test'
import type { ReactNode } from 'react'

interface Node {
  type: unknown
  props: Record<string, unknown>
}

const jsx = (type: unknown, props: Record<string, unknown>): Node => ({ type, props })
const preloadLegalMarkdown = mock()

mock.module('react/jsx-runtime', () => ({ jsx, jsxs: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react/jsx-dev-runtime', () => ({ jsxDEV: jsx, Fragment: Symbol.for('react.fragment') }))
mock.module('react', () => ({ useEffect: (effect: () => void) => effect() }))
mock.module('next/image', () => ({ default: (props: Record<string, unknown>) => jsx('next-image', props) }))
mock.module('next-intl', () => ({ useTranslations: () => (key: string) => key }))
mock.module('@/components/locale-switcher', () => ({ LocaleSwitcher: () => jsx('locale-switcher', {}) }))
mock.module('@/components/default-site-icon', () => ({ DefaultSiteIcon: (props: Record<string, unknown>) => jsx('default-site-icon', props) }))
mock.module('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: ReactNode }) => jsx('dialog', { children }),
  DialogTrigger: ({ children, ...props }: { children: ReactNode }) => jsx('button', { ...props, children }),
}))
mock.module('./legal-markdown', () => ({
  LegalMarkdownDialogContent: (props: Record<string, unknown>) => jsx('legal-markdown', props),
  preloadLegalMarkdown,
}))

const { AuthLayoutShell } = await import('./auth-layout-shell')

const legalSettings = {
  icp_record_number: '', icp_record_url: '', terms_enabled: false, terms_url: '', terms_text: '',
  privacy_enabled: false, privacy_url: '', privacy_text: '',
}
const brandingSettings = {
  site_name: 'Acme', site_description: 'Knowledge for everyone', site_icon: '/acme.png',
  theme_branding_display: 'full' as const,
}

function resolve(value: unknown): unknown {
  if (!value || typeof value !== 'object' || !('type' in value)) return value
  const node = value as Node
  return typeof node.type === 'function'
    ? resolve((node.type as (props: Record<string, unknown>) => unknown)(node.props))
    : node
}

function descendants(value: unknown): Node[] {
  if (Array.isArray(value)) return value.flatMap(descendants)
  const resolved = resolve(value)
  if (!resolved || typeof resolved !== 'object' || !('type' in resolved)) return []
  const node = resolved as Node
  return [node, ...descendants(node.props.children)]
}

function render(overrides: Partial<Parameters<typeof AuthLayoutShell>[0]> = {}) {
  return AuthLayoutShell({
    layout: 'centered',
    previewImageAlt: 'Product preview',
    brandingSettings,
    legalSettings,
    children: jsx('section', { id: 'auth-form', children: 'Form' }),
    ...overrides,
  }) as Node
}

beforeEach(() => preloadLegalMarkdown.mockClear())

describe('AuthLayoutShell', () => {
  test('centers children and honors each branding visibility boundary', () => {
    const full = descendants(render())
    expect(full[0].props.className).toContain('bg-muted/50')
    expect(full.some(node => node.type === 'main' || node.type === 'aside')).toBe(false)
    expect(full.find(node => node.type === 'next-image')?.props).toMatchObject({
      src: '/acme.png', alt: 'Acme', width: 56, height: 56, unoptimized: true,
    })
    expect(full.find(node => node.type === 'h1')?.props.children).toBe('Acme')
    expect(full.find(node => node.type === 'p')?.props.children).toBe('Knowledge for everyone')
    expect(full.find(node => node.props.id === 'auth-form')).toBeDefined()
    expect(full.filter(node => node.type === 'locale-switcher')).toHaveLength(1)

    const iconOnly = descendants(render({
      brandingSettings: { ...brandingSettings, site_icon: '', theme_branding_display: 'icon_only' },
    }))
    expect(iconOnly.some(node => node.type === 'default-site-icon')).toBe(true)
    expect(iconOnly.some(node => node.type === 'h1')).toBe(false)

    const nameOnly = descendants(render({
      brandingSettings: { ...brandingSettings, site_name: '', theme_branding_display: 'name_only' },
    }))
    expect(nameOnly.find(node => node.type === 'h1')?.props.children).toBe('Clouisle')
    expect(nameOnly.some(node => node.type === 'next-image' || node.type === 'default-site-icon')).toBe(false)

    const hidden = descendants(render({
      brandingSettings: { ...brandingSettings, theme_branding_display: 'hidden' },
    }))
    expect(hidden.some(node => node.type === 'h1' || node.type === 'next-image')).toBe(false)
    expect(hidden.find(node => node.props.id === 'auth-form')).toBeDefined()
  })

  test('builds the split layout with a responsive preview and inline footer boundary', () => {
    const nodes = descendants(render({
      layout: 'split',
      legalSettings: { ...legalSettings, icp_record_number: 'ICP 123' },
    }))
    const main = nodes.find(node => node.type === 'main')
    const aside = nodes.find(node => node.type === 'aside')
    const preview = nodes.find(node => node.type === 'img')
    const footer = nodes.find(node => node.props.className === ' flex items-center justify-center gap-x-3 gap-y-1 pb-4 text-center text-xs text-muted-foreground')

    expect(nodes[0].props.className).toContain('lg:flex')
    expect(main?.props.className).toContain('lg:w-[48%]')
    expect(nodes.find(node => String(node.props.className).includes('auth-layout-split'))).toBeDefined()
    expect(nodes.find(node => node.props.id === 'auth-form')).toBeDefined()
    expect(aside?.props.className).toContain('hidden')
    expect(aside?.props.className).toContain('lg:block')
    expect(preview?.props).toMatchObject({
      src: '/clouisle.png', alt: 'Product preview', style: { height: '80vh', width: 'auto' },
    })
    expect(footer).toBeDefined()
    expect(footer?.props.className).not.toContain('fixed')
  })

  test('preloads only enabled inline legal content and preserves external-link behavior', () => {
    const inline = descendants(render({
      legalSettings: { ...legalSettings, terms_enabled: true, terms_text: '# Terms' },
    }))
    expect(preloadLegalMarkdown).toHaveBeenCalledTimes(1)
    expect(inline.find(node => node.type === 'button')?.props.children).toBe('termsOfService')
    expect(inline.find(node => node.type === 'legal-markdown')?.props).toMatchObject({
      title: 'termsOfService', source: '# Terms',
    })

    preloadLegalMarkdown.mockClear()
    const external = descendants(render({
      legalSettings: {
        ...legalSettings,
        privacy_enabled: true,
        privacy_url: 'https://example.com/privacy',
        privacy_text: '# Ignored',
      },
    }))
    const link = external.find(node => node.type === 'a')
    expect(preloadLegalMarkdown).not.toHaveBeenCalled()
    expect(link?.props).toMatchObject({
      href: 'https://example.com/privacy', target: '_blank', rel: 'noreferrer',
      children: 'privacyPolicy',
    })
    expect(external.some(node => node.type === 'legal-markdown')).toBe(false)
  })
})

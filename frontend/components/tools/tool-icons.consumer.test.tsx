import { describe, expect, test } from 'bun:test'
import type { ComponentType, ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  Calculator,
  ChartColumn,
  Clock3,
  Code2,
  FolderOpen,
  Globe,
  Link,
  Search,
  Wrench,
} from 'lucide-react'
import {
  CodeToolIcon,
  HttpToolIcon,
  McpToolIcon,
  MongoIcon,
  MysqlIcon,
  PostgresIcon,
  RedisIcon,
  renderToolIcon,
  type ToolIconProps,
} from './tool-icons'

function markupOf(node: ReactNode): string {
  return renderToStaticMarkup(<>{node}</>)
}

function markOf(
  Icon: ComponentType<ToolIconProps>,
  size: number | string = 16,
  className?: string,
): string {
  return markupOf(<Icon size={size} className={className} />)
}

function lucideMark(
  Icon: ComponentType<{ className?: string; style?: { width: number; height: number } }>,
  size = 16,
  className?: string,
): string {
  return markupOf(<Icon className={className} style={{ width: size, height: size }} />)
}

const PROVIDERS = [
  ['postgresql', 'postgresql_query', PostgresIcon],
  ['mysql', 'mysql_query', MysqlIcon],
  ['redis', 'redis_query', RedisIcon],
  ['mongodb', 'mongodb_query', MongoIcon],
] as const

const CATEGORY_ICONS = {
  time: Clock3,
  math: Calculator,
  search: Search,
  web: Globe,
  file: FolderOpen,
  code: Code2,
  sandbox: Code2,
  api: Link,
  data: ChartColumn,
} as const

describe('tool-icons (consumer rendering)', () => {
  test('resolves every supported provider to its own brand mark via icon, builtin name and bare name', () => {
    for (const [iconKey, builtinName, Icon] of PROVIDERS) {
      const expected = markOf(Icon)

      expect(markupOf(renderToolIcon({ icon: iconKey }))).toBe(expected)
      expect(markupOf(renderToolIcon({ name: builtinName }))).toBe(expected)
      expect(markupOf(renderToolIcon({ name: iconKey }))).toBe(expected)
    }
  })

  test('renders a visually distinct brand mark per provider', () => {
    const rendered = new Set<string>()

    for (const [iconKey, , Icon] of PROVIDERS) {
      const html = markupOf(renderToolIcon({ icon: iconKey }))
      expect(html).toContain('<svg')
      expect(html).toContain('aria-hidden="true"')
      expect(html).toBe(markOf(Icon))
      rendered.add(html)
    }

    expect(rendered.size).toBe(PROVIDERS.length)
  })

  test('unknown providers never fall back to a provider brand mark', () => {
    const providerMarkups = PROVIDERS.map(([, , Icon]) => markOf(Icon))

    const unknownProviderOutputs = [
      markupOf(renderToolIcon({ icon: 'snowflake' })),
      markupOf(renderToolIcon({ name: 'snowflake_query' })),
      markupOf(renderToolIcon({ name: 'snowflake', icon: 'snowflake' })),
    ]

    for (const html of unknownProviderOutputs) {
      expect(providerMarkups).not.toContain(html)
    }
  })

  test('unknown icon, name, custom type and category all render the same generic fallback', () => {
    const generic = lucideMark(Wrench)

    expect(markupOf(renderToolIcon({ icon: 'snowflake' }))).toBe(generic)
    expect(markupOf(renderToolIcon({ name: 'snowflake_query' }))).toBe(generic)
    expect(markupOf(renderToolIcon({ type: 'custom', custom_type: 'snowflake' }))).toBe(generic)
    expect(markupOf(renderToolIcon({ category: 'nonexistent' }))).toBe(generic)
    expect(markupOf(renderToolIcon({}))).toBe(generic)
  })

  test('maps every known category to its category icon', () => {
    for (const [category, Icon] of Object.entries(CATEGORY_ICONS)) {
      expect(markupOf(renderToolIcon({ category }))).toBe(lucideMark(Icon))
    }
  })

  test('renders http, code and mcp marks for the matching tool type', () => {
    expect(markupOf(renderToolIcon({ type: 'custom', custom_type: 'http' }))).toBe(markOf(HttpToolIcon))
    expect(markupOf(renderToolIcon({ type: 'custom', custom_type: 'code' }))).toBe(markOf(CodeToolIcon))
    expect(markupOf(renderToolIcon({ type: 'mcp' }))).toBe(markOf(McpToolIcon))
    expect(markupOf(renderToolIcon({ type: 'mcp', category: 'search' }))).toBe(markOf(McpToolIcon))
  })

  test('custom_type marks are only used when type is custom', () => {
    const generic = lucideMark(Wrench)
    const search = lucideMark(Search)

    expect(markupOf(renderToolIcon({ custom_type: 'http' }))).toBe(generic)
    expect(markupOf(renderToolIcon({ type: 'builtin', custom_type: 'http' }))).toBe(generic)
    expect(markupOf(renderToolIcon({ type: 'builtin', custom_type: 'code', category: 'search' }))).toBe(search)
    expect(markupOf(renderToolIcon({ type: 'custom', custom_type: 'snowflake', category: 'time' }))).toBe(
      lucideMark(Clock3),
    )
  })

  test('icon identifier wins over tool name, protocol type and category', () => {
    expect(markupOf(renderToolIcon({ icon: 'mysql', name: 'postgresql_query' }))).toBe(markOf(MysqlIcon))
    expect(markupOf(renderToolIcon({ icon: 'mongodb', type: 'mcp' }))).toBe(markOf(MongoIcon))
    expect(markupOf(renderToolIcon({ icon: 'redis', category: 'search' }))).toBe(markOf(RedisIcon))
  })

  test('tool name wins over custom type and category', () => {
    expect(markupOf(renderToolIcon({ name: 'redis_query', type: 'custom', custom_type: 'http' }))).toBe(
      markOf(RedisIcon),
    )
    expect(markupOf(renderToolIcon({ name: 'postgresql_query', category: 'time' }))).toBe(markOf(PostgresIcon))
  })

  test('forwards size and className for brand, protocol and fallback marks', () => {
    const brand = markupOf(renderToolIcon({ icon: 'postgresql', size: 24, className: 'shrink-0' }))
    expect(brand).toContain('width="24"')
    expect(brand).toContain('height="24"')
    expect(brand).toContain('class="shrink-0"')

    const protocol = markupOf(renderToolIcon({ type: 'mcp', size: 20, className: 'text-muted' }))
    expect(protocol).toContain('width="20"')
    expect(protocol).toContain('height="20"')
    expect(protocol).toContain('class="text-muted"')

    const fallback = markupOf(renderToolIcon({ category: 'search', size: 18, className: 'shrink-0' }))
    expect(fallback).toContain('style="width:18px;height:18px"')
    expect(fallback).toContain('shrink-0')
  })

  test('defaults to a 16px decorative icon', () => {
    const brand = markupOf(renderToolIcon({ icon: 'mysql' }))
    expect(brand).toContain('width="16"')
    expect(brand).toContain('height="16"')
    expect(brand).toContain('aria-hidden="true"')

    const fallback = markupOf(renderToolIcon({}))
    expect(fallback).toContain('style="width:16px;height:16px"')
    expect(fallback).toContain('aria-hidden="true"')
  })
})

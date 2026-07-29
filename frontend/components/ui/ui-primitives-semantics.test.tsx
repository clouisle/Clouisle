import { describe, expect, test } from 'bun:test'
import { renderToStaticMarkup } from 'react-dom/server'

import { Avatar, AvatarFallback } from './avatar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
  BreadcrumbEllipsis,
} from './breadcrumb'
import { AvatarBadge, AvatarGroup, AvatarGroupCount } from './avatar'
import { RadioGroup, RadioGroupItem } from './radio-group'
import { Switch } from './switch'
import { ToggleGroup, ToggleGroupItem } from './toggle-group'

describe('simple UI primitive semantics', () => {
  test('renders avatar fallback content and size metadata', () => {
    const html = renderToStaticMarkup(
      <Avatar size="lg">
        <AvatarFallback>YL</AvatarFallback>
      </Avatar>,
    )

    expect(html).toContain('data-slot="avatar"')
    expect(html).toContain('data-size="lg"')
    expect(html).toContain('data-slot="avatar-fallback"')
    expect(html).toContain('YL')
  })

  test('renders avatar image, grouping, count, and badge semantics', () => {
    const html = renderToStaticMarkup(
      <AvatarGroup className="team">
        <Avatar size="sm">
          <AvatarBadge>+</AvatarBadge>
        </Avatar>
        <AvatarGroupCount>2</AvatarGroupCount>
      </AvatarGroup>,
    )

    expect(html).toContain('data-slot="avatar-group"')
    expect(html).toContain('data-slot="avatar-badge"')
    expect(html).toContain('data-slot="avatar-group-count"')
  })

  test('renders an accessible breadcrumb trail', () => {
    const html = renderToStaticMarkup(
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink href="/home">Home</BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator>→</BreadcrumbSeparator>
          <BreadcrumbEllipsis />
          <BreadcrumbItem>
            <BreadcrumbPage>Settings</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>,
    )

    expect(html).toContain('<nav aria-label="breadcrumb"')
    expect(html).toContain('href="/home"')
    expect(html).toContain('aria-current="page"')
    expect(html).toContain('aria-hidden="true"')
    expect(html).toContain('→')
    expect(html).toContain('More')
  })

  test('exposes radio, switch, and toggle state semantics', () => {
    const radioHtml = renderToStaticMarkup(
      <RadioGroup defaultValue="weekly" aria-label="Frequency">
        <RadioGroupItem value="daily" aria-label="Daily" />
        <RadioGroupItem value="weekly" aria-label="Weekly" />
      </RadioGroup>,
    )
    const switchHtml = renderToStaticMarkup(
      <Switch defaultChecked aria-label="Notifications" />,
    )
    const toggleHtml = renderToStaticMarkup(
      <ToggleGroup type="single" defaultValue="grid" aria-label="View">
        <ToggleGroupItem value="list">List</ToggleGroupItem>
        <ToggleGroupItem value="grid">Grid</ToggleGroupItem>
      </ToggleGroup>,
    )

    expect(radioHtml).toContain('role="radiogroup"')
    expect(radioHtml).toContain('aria-checked="true"')
    expect(switchHtml).toContain('role="switch"')
    expect(switchHtml).toContain('aria-checked="true"')
    expect(toggleHtml).toContain('role="radiogroup"')
    expect(toggleHtml).toContain('data-state="on"')
  })
})

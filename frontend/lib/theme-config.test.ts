import { describe, expect, test } from 'bun:test'

import {
  BRAND_CSS_VARIABLES,
  getBrandCssVariables,
  getBrandingVisibility,
  shouldApplySiteThemeMode,
} from './theme-config'

describe('theme config helpers', () => {
  test('maps branding display modes to actual visibility flags', () => {
    expect(getBrandingVisibility('full')).toEqual({ showIcon: true, showName: true })
    expect(getBrandingVisibility('name_only')).toEqual({ showIcon: false, showName: true })
    expect(getBrandingVisibility('icon_only')).toEqual({ showIcon: true, showName: false })
    expect(getBrandingVisibility('hidden')).toEqual({ showIcon: false, showName: false })
  })

  test('only forced site modes override user theme preference', () => {
    expect(shouldApplySiteThemeMode('light')).toBe(true)
    expect(shouldApplySiteThemeMode('dark')).toBe(true)
    expect(shouldApplySiteThemeMode('system')).toBe(false)
  })

  test('applies primary colors to primary and sidebar brand tokens', () => {
    expect(BRAND_CSS_VARIABLES).toContain('--sidebar-primary')
    expect(BRAND_CSS_VARIABLES).toContain('--sidebar-primary-foreground')
    expect(getBrandCssVariables({
      theme_primary_color: '#123456',
      theme_primary_foreground_color: '#ffffff',
    })).toEqual({
      '--primary': '#123456',
      '--sidebar-primary': '#123456',
      '--primary-foreground': '#ffffff',
      '--sidebar-primary-foreground': '#ffffff',
    })
  })
})

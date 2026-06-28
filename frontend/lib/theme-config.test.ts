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

  test('maps core theme settings to CSS variables', () => {
    expect(BRAND_CSS_VARIABLES).toContain('--sidebar-primary')
    expect(BRAND_CSS_VARIABLES).toContain('--card')
    expect(BRAND_CSS_VARIABLES).toContain('--chart-5')
    expect(BRAND_CSS_VARIABLES).toContain('--navbar')
    expect(getBrandCssVariables({
      theme_primary_color: '#123456',
      theme_primary_foreground_color: '#ffffff',
      theme_background_color: '#f8fafc',
      theme_foreground_color: '#0f172a',
      theme_card_color: '#ffffff',
      theme_card_foreground_color: '#111827',
      theme_border_color: '#e5e7eb',
      theme_ring_color: '#2563eb',
      theme_sidebar_color: '#020617',
      theme_sidebar_foreground_color: '#f8fafc',
      theme_sidebar_primary_color: '',
      theme_sidebar_primary_foreground_color: '',
      theme_sidebar_accent_color: '#1e293b',
      theme_sidebar_accent_foreground_color: '#f8fafc',
      theme_sidebar_border_color: '#334155',
      theme_navbar_color: '#ffffffcc',
      theme_navbar_foreground_color: '#0f172a',
      theme_navbar_hover_color: '#e0f2fe99',
      theme_navbar_hover_foreground_color: '#0c4a6e',
      theme_accent_color: '#eef2ff',
      theme_accent_foreground_color: '#312e81',
      theme_muted_color: '#f1f5f9',
      theme_muted_foreground_color: '#64748b',
      theme_chart_1_color: '#2563eb',
      theme_chart_2_color: '#16a34a',
      theme_chart_3_color: '#f97316',
      theme_chart_4_color: '#9333ea',
      theme_chart_5_color: '#dc2626',
    })).toMatchObject({
      '--primary': '#123456',
      '--sidebar-primary': '#123456',
      '--primary-foreground': '#ffffff',
      '--sidebar-primary-foreground': '#ffffff',
      '--background': '#f8fafc',
      '--card': '#ffffff',
      '--sidebar': '#020617',
      '--navbar': '#ffffffcc',
      '--navbar-hover': '#e0f2fe99',
      '--chart-5': '#dc2626',
    })
  })
})

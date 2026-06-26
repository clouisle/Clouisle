import type { PublicSiteSettings, ThemeBrandingDisplay, ThemeMode } from '@/lib/api/site-settings'

export const BRAND_CSS_VARIABLES = [
  '--primary',
  '--primary-foreground',
  '--sidebar-primary',
  '--sidebar-primary-foreground',
] as const

export function shouldApplySiteThemeMode(themeMode: ThemeMode): boolean {
  return themeMode === 'light' || themeMode === 'dark'
}

export function getBrandingVisibility(display: ThemeBrandingDisplay): {
  showIcon: boolean
  showName: boolean
} {
  return {
    showIcon: display === 'full' || display === 'icon_only',
    showName: display === 'full' || display === 'name_only',
  }
}

export function getBrandCssVariables(settings: Pick<
  PublicSiteSettings,
  'theme_primary_color' | 'theme_primary_foreground_color'
>): Partial<Record<(typeof BRAND_CSS_VARIABLES)[number], string>> {
  return {
    '--primary': settings.theme_primary_color,
    '--sidebar-primary': settings.theme_primary_color,
    '--primary-foreground': settings.theme_primary_foreground_color,
    '--sidebar-primary-foreground': settings.theme_primary_foreground_color,
  }
}

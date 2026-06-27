import type { PublicSiteSettings, ThemeBrandingDisplay, ThemeMode } from '@/lib/api/site-settings'

export const BRAND_CSS_VARIABLES = [
  '--primary',
  '--primary-foreground',
  '--background',
  '--foreground',
  '--card',
  '--card-foreground',
  '--border',
  '--ring',
  '--sidebar',
  '--sidebar-foreground',
  '--sidebar-primary',
  '--sidebar-primary-foreground',
  '--sidebar-accent',
  '--sidebar-accent-foreground',
  '--sidebar-border',
  '--navbar',
  '--navbar-foreground',
  '--navbar-hover',
  '--navbar-hover-foreground',
  '--accent',
  '--accent-foreground',
  '--muted',
  '--muted-foreground',
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
] as const

const THEME_COLOR_VARIABLES = {
  theme_primary_color: '--primary',
  theme_primary_foreground_color: '--primary-foreground',
  theme_background_color: '--background',
  theme_foreground_color: '--foreground',
  theme_card_color: '--card',
  theme_card_foreground_color: '--card-foreground',
  theme_border_color: '--border',
  theme_ring_color: '--ring',
  theme_sidebar_color: '--sidebar',
  theme_sidebar_foreground_color: '--sidebar-foreground',
  theme_sidebar_primary_color: '--sidebar-primary',
  theme_sidebar_primary_foreground_color: '--sidebar-primary-foreground',
  theme_sidebar_accent_color: '--sidebar-accent',
  theme_sidebar_accent_foreground_color: '--sidebar-accent-foreground',
  theme_sidebar_border_color: '--sidebar-border',
  theme_navbar_color: '--navbar',
  theme_navbar_foreground_color: '--navbar-foreground',
  theme_navbar_hover_color: '--navbar-hover',
  theme_navbar_hover_foreground_color: '--navbar-hover-foreground',
  theme_accent_color: '--accent',
  theme_accent_foreground_color: '--accent-foreground',
  theme_muted_color: '--muted',
  theme_muted_foreground_color: '--muted-foreground',
  theme_chart_1_color: '--chart-1',
  theme_chart_2_color: '--chart-2',
  theme_chart_3_color: '--chart-3',
  theme_chart_4_color: '--chart-4',
  theme_chart_5_color: '--chart-5',
} as const satisfies Record<string, (typeof BRAND_CSS_VARIABLES)[number]>

type ThemeColorSettingKey = keyof typeof THEME_COLOR_VARIABLES

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
  ThemeColorSettingKey
>): Partial<Record<(typeof BRAND_CSS_VARIABLES)[number], string>> {
  const variables: Partial<Record<(typeof BRAND_CSS_VARIABLES)[number], string>> = {}

  for (const [settingKey, cssVariable] of Object.entries(THEME_COLOR_VARIABLES)) {
    variables[cssVariable] = settings[settingKey as ThemeColorSettingKey]
  }

  if (!settings.theme_sidebar_primary_color) {
    variables['--sidebar-primary'] = settings.theme_primary_color
  }
  if (!settings.theme_sidebar_primary_foreground_color) {
    variables['--sidebar-primary-foreground'] = settings.theme_primary_foreground_color
  }
  if (!settings.theme_navbar_color) {
    variables['--navbar'] = settings.theme_card_color || settings.theme_background_color
  }
  if (!settings.theme_navbar_foreground_color) {
    variables['--navbar-foreground'] = settings.theme_foreground_color
  }
  if (!settings.theme_navbar_hover_color) {
    variables['--navbar-hover'] = settings.theme_muted_color
  }
  if (!settings.theme_navbar_hover_foreground_color) {
    variables['--navbar-hover-foreground'] = settings.theme_foreground_color
  }

  return variables
}

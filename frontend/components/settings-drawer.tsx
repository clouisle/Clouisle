'use client'

import * as React from 'react'
import { useTheme } from 'next-themes'
import { useLocale, useTranslations } from 'next-intl'
import { Check } from 'lucide-react'

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { locales, localeNames, type Locale } from '@/i18n/config'
import { useSettings } from '@/hooks/use-settings'
import { useLocaleChange } from '@/hooks/use-locale-change'

interface SettingsDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 是否显示侧边栏样式设置，默认为 true */
  showSidebarStyle?: boolean
  /** 是否显示中台 header 导航布局设置，默认为 false */
  showPlatformHeader?: boolean
}

export function SettingsDrawer({ open, onOpenChange, showSidebarStyle = true, showPlatformHeader = false }: SettingsDrawerProps) {
  const { theme, setTheme } = useTheme()
  const locale = useLocale()
  const t = useTranslations('settings')
  const { changeLocale } = useLocaleChange()

  const {
    sidebarVariant,
    layoutVariant,
    direction,
    platformHeaderVariant,
    mounted,
    setSidebarVariant,
    setLayoutVariant,
    setDirection,
    setPlatformHeaderVariant,
    resetSettings,
  } = useSettings()

  // 使用默认值直到 mounted，避免水合不匹配
  const effectiveSidebarVariant = mounted ? sidebarVariant : 'inset'
  const effectiveLayoutVariant = mounted ? layoutVariant : 'default'
  const effectiveDirection = mounted ? direction : 'ltr'
  const effectivePlatformHeaderVariant = mounted ? platformHeaderVariant : 'default'

  const handleReset = () => {
    setTheme('system')
    resetSettings()
  }

  // 抽屉位置根据 direction 改变
  const drawerSide = effectiveDirection === 'rtl' ? 'left' : 'right'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={drawerSide} className="w-[360px] flex flex-col">
        <SheetHeader>
          <SheetTitle>{t('themeSettings')}</SheetTitle>
          <SheetDescription>{t('themeSettingsDescription')}</SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-4 space-y-6">
          {/* Theme Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium text-primary">{t('theme')}</Label>
            <div className="grid grid-cols-3 gap-2">
              <ThemeCard
                selected={theme === 'system'}
                onClick={() => setTheme('system')}
                label={t('system')}
                variant="system"
              />
              <ThemeCard
                selected={theme === 'light'}
                onClick={() => setTheme('light')}
                label={t('light')}
                variant="light"
              />
              <ThemeCard
                selected={theme === 'dark'}
                onClick={() => setTheme('dark')}
                label={t('dark')}
                variant="dark"
              />
            </div>
          </div>

          {/* Sidebar Selection - 仅在 showSidebarStyle 为 true 时显示 */}
          {showSidebarStyle && (
            <div className="space-y-3">
              <Label className="text-sm font-medium text-primary">{t('sidebar')}</Label>
              <div className="grid grid-cols-3 gap-2">
                <SidebarCard
                  selected={effectiveSidebarVariant === 'inset'}
                  onClick={() => setSidebarVariant('inset')}
                  label={t('sidebarInset')}
                  variant="inset"
                />
                <SidebarCard
                  selected={effectiveSidebarVariant === 'floating'}
                  onClick={() => setSidebarVariant('floating')}
                  label={t('sidebarFloating')}
                  variant="floating"
                />
                <SidebarCard
                  selected={effectiveSidebarVariant === 'sidebar'}
                  onClick={() => setSidebarVariant('sidebar')}
                  label={t('sidebarDefault')}
                  variant="sidebar"
                />
              </div>
            </div>
          )}

          {/* Layout Selection - 仅在不显示中台 header 时显示 */}
          {!showPlatformHeader && (
            <div className="space-y-3">
              <Label className="text-sm font-medium text-primary">{t('layout')}</Label>
              <div className="grid grid-cols-3 gap-2">
                <LayoutCard
                  selected={effectiveLayoutVariant === 'default'}
                  onClick={() => setLayoutVariant('default')}
                  label={t('layoutDefault')}
                  variant="default"
                />
                <LayoutCard
                  selected={effectiveLayoutVariant === 'compact'}
                  onClick={() => setLayoutVariant('compact')}
                  label={t('layoutCompact')}
                  variant="compact"
                />
                <LayoutCard
                  selected={effectiveLayoutVariant === 'full'}
                  onClick={() => setLayoutVariant('full')}
                  label={t('layoutFull')}
                  variant="full"
                />
              </div>
            </div>
          )}

          {/* Platform Header Layout - 仅在 showPlatformHeader 为 true 时显示 */}
          {showPlatformHeader && (
            <div className="space-y-3">
              <Label className="text-sm font-medium text-primary">{t('headerLayout')}</Label>
              <div className="grid grid-cols-3 gap-2">
                <PlatformHeaderCard
                  selected={effectivePlatformHeaderVariant === 'default'}
                  onClick={() => setPlatformHeaderVariant('default')}
                  label={t('headerDefault')}
                  variant="default"
                />
                <PlatformHeaderCard
                  selected={effectivePlatformHeaderVariant === 'centered'}
                  onClick={() => setPlatformHeaderVariant('centered')}
                  label={t('headerCentered')}
                  variant="centered"
                />
                <PlatformHeaderCard
                  selected={effectivePlatformHeaderVariant === 'minimal'}
                  onClick={() => setPlatformHeaderVariant('minimal')}
                  label={t('headerMinimal')}
                  variant="minimal"
                />
              </div>
            </div>
          )}

          {/* Direction Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium text-primary">{t('direction')}</Label>
            <div className="grid grid-cols-3 gap-2">
              <DirectionCard
                selected={effectiveDirection === 'ltr'}
                onClick={() => setDirection('ltr')}
                label={t('directionLTR')}
                variant="ltr"
              />
              <DirectionCard
                selected={effectiveDirection === 'rtl'}
                onClick={() => setDirection('rtl')}
                label={t('directionRTL')}
                variant="rtl"
              />
            </div>
          </div>

          {/* Language Selection */}
          <div className="space-y-3">
            <Label className="text-sm font-medium text-primary">{t('language')}</Label>
            <div className="grid grid-cols-2 gap-2">
              {locales.map((l) => (
                <button
                  key={l}
                  onClick={() => changeLocale(l)}
                  className={cn(
                    'relative flex items-center justify-center rounded-md border-2 px-3 py-2 text-sm transition-colors hover:bg-muted',
                    locale === l ? 'border-primary' : 'border-transparent'
                  )}
                >
                  {locale === l && (
                    <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
                      <Check className="h-2.5 w-2.5 text-primary-foreground" />
                    </div>
                  )}
                  <span>{localeNames[l]}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <SheetFooter>
          <Button variant="destructive" className="w-full" onClick={handleReset}>
            {t('reset')}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

// Theme Preview Card
function ThemeCard({
  selected,
  onClick,
  label,
  variant,
}: {
  selected: boolean
  onClick: () => void
  label: string
  variant: 'system' | 'light' | 'dark'
}) {
  const bgClass = variant === 'dark' ? 'bg-slate-800' : 'bg-gray-100'
  const barClass = variant === 'dark' ? 'bg-slate-600' : 'bg-gray-300'
  const contentClass = variant === 'dark' ? 'bg-slate-700' : 'bg-white'
  
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-1.5 rounded-md border-2 p-1.5 transition-colors hover:bg-muted',
        selected ? 'border-primary' : 'border-transparent'
      )}
    >
      {selected && (
        <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
          <Check className="h-2.5 w-2.5 text-primary-foreground" />
        </div>
      )}
      <div className={cn('w-full aspect-[5/3] rounded overflow-hidden', bgClass)}>
        <div className="h-full p-1 flex gap-0.5">
          <div className={cn('w-1/4 rounded-sm', barClass)} />
          <div className={cn('flex-1 rounded-sm', contentClass)}>
            <div className="p-0.5 space-y-0.5">
              <div className={cn('h-0.5 w-2/3 rounded-full', barClass)} />
              <div className={cn('h-0.5 w-1/2 rounded-full', barClass)} />
            </div>
          </div>
        </div>
      </div>
      <span className="text-[10px]">{label}</span>
    </button>
  )
}

// Sidebar Preview Card
function SidebarCard({
  selected,
  onClick,
  label,
  variant,
}: {
  selected: boolean
  onClick: () => void
  label: string
  variant: 'inset' | 'floating' | 'sidebar'
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-1.5 rounded-md border-2 p-1.5 transition-colors hover:bg-muted',
        selected ? 'border-primary' : 'border-transparent'
      )}
    >
      {selected && (
        <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
          <Check className="h-2.5 w-2.5 text-primary-foreground" />
        </div>
      )}
      <div className="w-full aspect-[5/3] rounded bg-gray-100 overflow-hidden p-1">
        <div className="h-full flex gap-0.5">
          {variant === 'inset' && (
            <>
              <div className="w-1/4 bg-white rounded-sm p-0.5 space-y-0.5">
                <div className="h-0.5 w-full bg-gray-300 rounded-full" />
                <div className="h-0.5 w-2/3 bg-gray-300 rounded-full" />
              </div>
              <div className="flex-1 bg-white rounded-sm" />
            </>
          )}
          {variant === 'floating' && (
            <>
              <div className="w-1/4 bg-gray-200 rounded-sm p-0.5 space-y-0.5 shadow-sm">
                <div className="h-0.5 w-full bg-gray-400 rounded-full" />
                <div className="h-0.5 w-2/3 bg-gray-400 rounded-full" />
              </div>
              <div className="flex-1 bg-white rounded-sm" />
            </>
          )}
          {variant === 'sidebar' && (
            <>
              <div className="w-1/4 bg-slate-600 rounded-sm p-0.5 space-y-0.5">
                <div className="h-0.5 w-full bg-slate-400 rounded-full" />
                <div className="h-0.5 w-2/3 bg-slate-400 rounded-full" />
              </div>
              <div className="flex-1 bg-gray-200 rounded-sm" />
            </>
          )}
        </div>
      </div>
      <span className="text-[10px]">{label}</span>
    </button>
  )
}

// Layout Preview Card
function LayoutCard({
  selected,
  onClick,
  label,
  variant,
}: {
  selected: boolean
  onClick: () => void
  label: string
  variant: 'default' | 'compact' | 'full'
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-1.5 rounded-md border-2 p-1.5 transition-colors hover:bg-muted',
        selected ? 'border-primary' : 'border-transparent'
      )}
    >
      {selected && (
        <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
          <Check className="h-2.5 w-2.5 text-primary-foreground" />
        </div>
      )}
      <div className="w-full aspect-[5/3] rounded bg-gray-100 overflow-hidden p-1">
        <div className="h-full flex gap-0.5">
          <div className={cn(
            'bg-slate-600 rounded-sm',
            variant === 'full' ? 'hidden' : variant === 'compact' ? 'w-[15%]' : 'w-1/4'
          )} />
          <div className="flex-1 bg-white rounded-sm p-0.5 space-y-0.5">
            <div className="h-1 w-full bg-gray-200 rounded-full" />
            <div className="flex gap-0.5 mt-0.5">
              <div className="flex-1 h-3 bg-gray-200 rounded" />
              <div className="flex-1 h-3 bg-gray-200 rounded" />
            </div>
          </div>
        </div>
      </div>
      <span className="text-[10px]">{label}</span>
    </button>
  )
}

// Direction Preview Card
function DirectionCard({
  selected,
  onClick,
  label,
  variant,
}: {
  selected: boolean
  onClick: () => void
  label: string
  variant: 'ltr' | 'rtl'
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-1.5 rounded-md border-2 p-1.5 transition-colors hover:bg-muted',
        selected ? 'border-primary' : 'border-transparent'
      )}
    >
      {selected && (
        <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
          <Check className="h-2.5 w-2.5 text-primary-foreground" />
        </div>
      )}
      <div className="w-full aspect-[5/3] rounded bg-gray-100 overflow-hidden p-1">
        <div className={cn('h-full flex gap-0.5', variant === 'rtl' && 'flex-row-reverse')}>
          <div className="w-1/4 bg-slate-500 rounded-sm p-0.5 space-y-0.5">
            <div className="h-0.5 w-full bg-slate-300 rounded-full" />
            <div className={cn('h-0.5 w-2/3 bg-slate-300 rounded-full', variant === 'rtl' && 'ml-auto')} />
          </div>
          <div className="flex-1 bg-white rounded-sm p-0.5 space-y-0.5">
            <div className={cn('h-0.5 w-2/3 bg-gray-300 rounded-full', variant === 'rtl' && 'ml-auto')} />
            <div className={cn('h-0.5 w-1/2 bg-gray-300 rounded-full', variant === 'rtl' && 'ml-auto')} />
          </div>
        </div>
      </div>
      <span className="text-[10px]">{label}</span>
    </button>
  )
}

// Platform Header Preview Card
function PlatformHeaderCard({
  selected,
  onClick,
  label,
  variant,
}: {
  selected: boolean
  onClick: () => void
  label: string
  variant: 'default' | 'centered' | 'minimal'
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-center gap-1.5 rounded-md border-2 p-1.5 transition-colors hover:bg-muted',
        selected ? 'border-primary' : 'border-transparent'
      )}
    >
      {selected && (
        <div className="absolute -top-1 -right-1 rounded-full bg-primary p-0.5">
          <Check className="h-2.5 w-2.5 text-primary-foreground" />
        </div>
      )}
      <div className="w-full aspect-[5/3] rounded bg-gray-100 overflow-hidden p-0.5">
        {/* Header bar */}
        <div className="h-2 bg-white rounded-t-sm flex items-center px-0.5 gap-0.5 border-b border-gray-200">
          {variant === 'default' && (
            <>
              {/* Logo left, nav left, actions right */}
              <div className="w-1 h-1 bg-slate-600 rounded-sm" />
              <div className="flex gap-0.5 ml-0.5">
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
              </div>
              <div className="ml-auto flex gap-0.5">
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
              </div>
            </>
          )}
          {variant === 'centered' && (
            <>
              {/* Logo left, nav centered, actions right */}
              <div className="w-1 h-1 bg-slate-600 rounded-sm" />
              <div className="flex-1 flex justify-center gap-0.5">
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
                <div className="w-2 h-0.5 bg-gray-400 rounded-full" />
              </div>
              <div className="flex gap-0.5">
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
              </div>
            </>
          )}
          {variant === 'minimal' && (
            <>
              {/* Logo left, nav icons only, actions right */}
              <div className="w-1 h-1 bg-slate-600 rounded-sm" />
              <div className="flex gap-0.5 ml-0.5">
                <div className="w-1 h-1 bg-gray-400 rounded-full" />
                <div className="w-1 h-1 bg-gray-400 rounded-full" />
                <div className="w-1 h-1 bg-gray-400 rounded-full" />
              </div>
              <div className="ml-auto flex gap-0.5">
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
                <div className="w-1 h-1 bg-gray-300 rounded-full" />
              </div>
            </>
          )}
        </div>
        {/* Content area */}
        <div className="flex-1 bg-white rounded-b-sm p-0.5">
          <div className="flex gap-0.5 mt-0.5">
            <div className="flex-1 h-2 bg-gray-200 rounded" />
            <div className="flex-1 h-2 bg-gray-200 rounded" />
          </div>
        </div>
      </div>
      <span className="text-[10px]">{label}</span>
    </button>
  )
}


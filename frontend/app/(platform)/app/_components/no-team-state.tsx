'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Mail, Clock, Rocket, ChevronRight } from 'lucide-react'

const steps = [
  { icon: Mail, color: 'text-blue-500', bg: 'bg-blue-500/10', border: 'border-blue-500/20', key: 'step1' },
  { icon: Clock, color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20', key: 'step2' },
  { icon: Rocket, color: 'text-green-500', bg: 'bg-green-500/10', border: 'border-green-500/20', key: 'step3' },
] as const

export function NoTeamState() {
  const t = useTranslations('platform.noTeam')

  return (
    <div className="min-h-[calc(100vh-4rem)] flex flex-col items-center justify-center bg-gradient-to-b from-background to-muted/20 p-6">
      <div className="max-w-xl w-full text-center space-y-8">
        {/* Title & Description */}
        <div className="space-y-3">
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-br from-foreground to-foreground/70 bg-clip-text text-transparent">
            {t('title')}
          </h1>
          <p className="text-muted-foreground leading-relaxed max-w-sm mx-auto">
            {t('description')}
          </p>
        </div>

        {/* Steps - horizontal flow */}
        <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2 pt-2">
          {steps.map(({ icon: Icon, color, bg, border, key }, index) => (
            <React.Fragment key={key}>
              <div
                className={`rounded-xl border ${border} bg-card p-4 text-left h-full transition-all hover:shadow-md hover:-translate-y-0.5`}
              >
                <div className="space-y-2.5">
                  <div className={`h-9 w-9 rounded-lg ${bg} flex items-center justify-center`}>
                    <Icon className={`h-4.5 w-4.5 ${color}`} />
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className={`text-[10px] font-semibold ${color} opacity-80`}>{String(index + 1).padStart(2, '0')}</span>
                      <h3 className="font-semibold text-sm">{t(`steps.${key}.title`)}</h3>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed mt-1">
                      {t(`steps.${key}.description`)}
                    </p>
                  </div>
                </div>
              </div>
              {index < steps.length - 1 && (
                <ChevronRight className="h-4 w-4 text-muted-foreground/40" />
              )}
            </React.Fragment>
          ))}
        </div>

      </div>
    </div>
  )
}

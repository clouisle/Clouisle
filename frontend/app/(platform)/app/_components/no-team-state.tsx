'use client'

import { useTranslations } from 'next-intl'
import { Users, Mail, HelpCircle, ArrowRight } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

export function NoTeamState() {
  const t = useTranslations('platform.noTeam')

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-6">
      <div className="max-w-2xl w-full space-y-6">
        {/* Main Card */}
        <Card className="border-2">
          <CardContent className="pt-12 pb-10 px-8">
            <div className="text-center space-y-6">
              {/* Icon */}
              <div className="relative inline-block">
                <div className="h-20 w-20 rounded-2xl bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center mx-auto">
                  <Users className="h-10 w-10 text-primary" />
                </div>
                <div className="absolute -top-1 -right-1 h-6 w-6 rounded-full bg-yellow-500 flex items-center justify-center">
                  <HelpCircle className="h-4 w-4 text-white" />
                </div>
              </div>

              {/* Title & Description */}
              <div className="space-y-3">
                <h1 className="text-3xl font-bold tracking-tight">
                  {t('title')}
                </h1>
                <p className="text-muted-foreground text-lg max-w-md mx-auto">
                  {t('description')}
                </p>
              </div>

              {/* Status Badge */}
              <div className="flex justify-center">
                <Badge variant="secondary" className="px-4 py-1.5 text-sm">
                  {t('status')}
                </Badge>
              </div>

              {/* Action Button */}
              <div className="pt-4">
                <a href="mailto:admin@example.com">
                  <Button size="lg" className="gap-2">
                    <Mail className="h-5 w-5" />
                    {t('contactAdmin')}
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </a>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Help Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="pt-6 pb-5 px-5">
              <div className="space-y-3">
                <div className="h-10 w-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Users className="h-5 w-5 text-blue-500" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm mb-1">
                    {t('steps.step1.title')}
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t('steps.step1.description')}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="pt-6 pb-5 px-5">
              <div className="space-y-3">
                <div className="h-10 w-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                  <Mail className="h-5 w-5 text-green-500" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm mb-1">
                    {t('steps.step2.title')}
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t('steps.step2.description')}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="hover:shadow-md transition-shadow">
            <CardContent className="pt-6 pb-5 px-5">
              <div className="space-y-3">
                <div className="h-10 w-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                  <ArrowRight className="h-5 w-5 text-purple-500" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm mb-1">
                    {t('steps.step3.title')}
                  </h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {t('steps.step3.description')}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Additional Info */}
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            {t('helpText')}{' '}
            <a
              href="mailto:support@example.com"
              className="text-primary hover:underline font-medium"
            >
              {t('supportEmail')}
            </a>
          </p>
        </div>
      </div>
    </div>
  )
}

import { getTranslations } from 'next-intl/server'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ForgotPasswordForm } from './_components'

export default async function ForgotPasswordPage() {
  const t = await getTranslations('auth')

  return (
    <Card className="bg-transparent shadow-none ring-0">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <span className="font-bold text-xl">C</span>
          </div>
        </div>
        <CardTitle className="text-2xl">{t('forgotPasswordTitle')}</CardTitle>
        <CardDescription>{t('forgotPasswordDescription')}</CardDescription>
      </CardHeader>
      <CardContent>
        <ForgotPasswordForm />
      </CardContent>
    </Card>
  )
}

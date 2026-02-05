import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { LoginForm } from './_components'
import { LoginRedirect } from './_components/login-redirect'

export default async function LoginPage() {
  const t = await getTranslations('auth')

  return (
    <Card>
      <LoginRedirect />
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{t('loginTitle')}</CardTitle>
        <CardDescription>{t('loginDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <LoginForm />
      </CardContent>
      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          {t('noAccount')}{' '}
          <Link href="/register" className="text-primary hover:underline">
            {t('register')}
          </Link>
        </p>
      </CardFooter>
    </Card>
  )
}

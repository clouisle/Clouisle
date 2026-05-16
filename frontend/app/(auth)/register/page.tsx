import Link from 'next/link'
import { getTranslations } from 'next-intl/server'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { RegisterForm } from './_components'

export default async function RegisterPage() {
  const t = await getTranslations('auth')

  return (
    <Card className="bg-transparent shadow-none ring-0">
      <CardHeader className="text-center">
        <CardTitle className="text-2xl">{t('registerTitle')}</CardTitle>
        <CardDescription>{t('registerDescription')}</CardDescription>
      </CardHeader>
      <CardContent>
        <RegisterForm />
      </CardContent>
      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          {t('hasAccount')}{' '}
          <Link href="/login" className="text-primary hover:underline">
            {t('login')}
          </Link>
        </p>
      </CardFooter>
    </Card>
  )
}

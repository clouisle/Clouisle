'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { Label } from '@/components/ui/label'
import { Loader2, ShieldCheck, Download, Copy, Check, Info } from 'lucide-react'
import { TOTPQRCode } from '@/components/totp-qr-code'
import { api } from '@/lib/api/client'
import type { TOTPSetupResponse } from '@/lib/api/users'

interface TOTPSetupWizardForcedProps {
  tempToken: string
  onComplete: () => void
  onCancel: () => void
}

type Step = 1 | 2 | 3 | 4 | 5

export function TOTPSetupWizardForced({ tempToken, onComplete, onCancel }: TOTPSetupWizardForcedProps) {
  const t = useTranslations('auth')
  const tCommon = useTranslations('common')

  const [step, setStep] = React.useState<Step>(1)
  const [loading, setLoading] = React.useState(false)
  const [setupData, setSetupData] = React.useState<TOTPSetupResponse | null>(null)
  const [verificationCode, setVerificationCode] = React.useState('')
  const [backupCodesCopied, setBackupCodesCopied] = React.useState(false)

  // 使用临时token调用API
  const callApiWithTempToken = async <T,>(endpoint: string, method: 'GET' | 'POST' = 'GET', body?: unknown): Promise<T> => {
    const headers: Record<string, string> = {
      'Authorization': `Bearer ${tempToken}`,
    }

    const options: RequestInit = {
      method,
      headers,
    }

    if (body) {
      headers['Content-Type'] = 'application/json'
      options.body = JSON.stringify(body)
    }

    const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ''}${endpoint}`, options)

    if (!response.ok) {
      const error = await response.json()
      throw new Error(error.msg || 'API call failed')
    }

    const data = await response.json()
    return data.data as T
  }

  const handleStartSetup = async () => {
    try {
      setLoading(true)
      const data = await callApiWithTempToken<TOTPSetupResponse>('/api/v1/totp/setup', 'POST')
      setSetupData(data)
      setStep(2)
    } catch (error) {
      toast.error(t('setupFailed'))
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyCode = async () => {
    if (verificationCode.length !== 6) {
      toast.error(t('verificationCodeInvalid'))
      return
    }

    try {
      setLoading(true)
      await callApiWithTempToken('/api/v1/totp/enable', 'POST', { code: verificationCode })
      toast.success(t('twoFactorEnabledSuccess'))
      setStep(4)
    } catch (error) {
      toast.error(t('twoFactorInvalid'))
    } finally {
      setLoading(false)
    }
  }

  const handleDownloadCodes = () => {
    if (!setupData) return

    const content = setupData.backup_codes.join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'totp-backup-codes.txt'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    setBackupCodesCopied(true)
  }

  const handleCopyCodes = () => {
    if (!setupData) return

    const content = setupData.backup_codes.join('\n')
    navigator.clipboard.writeText(content)
    toast.success(t('setupStep4CodesCopied'))
    setBackupCodesCopied(true)
  }

  const handleFinish = () => {
    onComplete()
  }

  return (
    <Card className="border-2">
      <CardHeader className="text-center space-y-4 pb-8">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10">
          <ShieldCheck className="h-8 w-8 text-primary" />
        </div>
        <div className="space-y-2">
          <CardTitle className="text-2xl">{t('setupTwoFactorTitle')}</CardTitle>
          <CardDescription className="text-base">
            {t('totpSetupRequiredByAdmin')}
          </CardDescription>
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Step 1: Introduction */}
        {step === 1 && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{t('setupStep1Title')}</h3>
              <p className="text-muted-foreground leading-relaxed">{t('setupStep1Description')}</p>
            </div>
            <div className="flex gap-3">
              <Button onClick={handleStartSetup} disabled={loading} className="flex-1" size="lg">
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('setupStepNext')}
              </Button>
              <Button variant="outline" onClick={onCancel} size="lg">
                {tCommon('cancel')}
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: QR Code */}
        {step === 2 && setupData && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{t('setupStep2Title')}</h3>
              <p className="text-muted-foreground leading-relaxed">{t('setupStep2Description')}</p>
            </div>
            <TOTPQRCode secret={setupData.secret} qrCode={setupData.qr_code} />
            <div className="flex gap-3">
              <Button onClick={() => setStep(3)} className="flex-1" size="lg">
                {t('setupStepNext')}
              </Button>
              <Button variant="outline" onClick={() => setStep(1)} size="lg">
                {t('setupStepBack')}
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Verification */}
        {step === 3 && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{t('setupStep3Title')}</h3>
              <p className="text-muted-foreground leading-relaxed">{t('setupStep3Description')}</p>
            </div>
            <div className="space-y-4">
              <Label className="text-base">{t('verificationCode6Digit')}</Label>
              <div className="flex justify-center py-4">
                <InputOTP
                  maxLength={6}
                  value={verificationCode}
                  onChange={setVerificationCode}
                >
                  <InputOTPGroup>
                    <InputOTPSlot index={0} className="h-14 w-14 text-lg" />
                    <InputOTPSlot index={1} className="h-14 w-14 text-lg" />
                    <InputOTPSlot index={2} className="h-14 w-14 text-lg" />
                    <InputOTPSlot index={3} className="h-14 w-14 text-lg" />
                    <InputOTPSlot index={4} className="h-14 w-14 text-lg" />
                    <InputOTPSlot index={5} className="h-14 w-14 text-lg" />
                  </InputOTPGroup>
                </InputOTP>
              </div>
            </div>
            <div className="flex gap-3">
              <Button
                onClick={handleVerifyCode}
                disabled={loading || verificationCode.length !== 6}
                className="flex-1"
                size="lg"
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('verifyCode')}
              </Button>
              <Button variant="outline" onClick={() => setStep(2)} size="lg">
                {t('setupStepBack')}
              </Button>
            </div>
          </div>
        )}

        {/* Step 4: Backup Codes */}
        {step === 4 && setupData && (
          <div className="space-y-6">
            <div className="space-y-3">
              <h3 className="text-lg font-semibold">{t('setupStep4Title')}</h3>
              <p className="text-muted-foreground leading-relaxed">{t('setupStep4Description')}</p>
            </div>
            <div className="rounded-lg border bg-muted/50 p-4">
              <div className="grid grid-cols-2 gap-2 font-mono text-sm">
                {setupData.backup_codes.map((code, index) => (
                  <div key={index} className="rounded bg-background px-3 py-2.5 text-center font-medium">
                    {code}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4 flex gap-3">
              <Info className="h-5 w-5 text-yellow-600 dark:text-yellow-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-yellow-700 dark:text-yellow-400 leading-relaxed">
                {t('setupStep4Warning')}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Button variant="outline" onClick={handleDownloadCodes} size="lg">
                <Download className="mr-2 h-4 w-4" />
                {t('setupStep4Download')}
              </Button>
              <Button variant="outline" onClick={handleCopyCodes} size="lg">
                {backupCodesCopied ? (
                  <Check className="mr-2 h-4 w-4" />
                ) : (
                  <Copy className="mr-2 h-4 w-4" />
                )}
                {t('setupStep4Copy')}
              </Button>
            </div>
            <Button onClick={() => setStep(5)} className="w-full" size="lg">
              {t('setupStepNext')}
            </Button>
          </div>
        )}

        {/* Step 5: Completion */}
        {step === 5 && (
          <div className="space-y-6 py-4">
            <div className="flex justify-center">
              <div className="rounded-full bg-green-500/10 p-6">
                <ShieldCheck className="h-16 w-16 text-green-500" />
              </div>
            </div>
            <div className="space-y-3 text-center">
              <h3 className="text-xl font-semibold">{t('setupStep5Title')}</h3>
              <p className="text-muted-foreground leading-relaxed max-w-md mx-auto">
                {t('setupStep5Description')}
              </p>
            </div>
            <Button onClick={handleFinish} className="w-full" size="lg">
              {tCommon('done')}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Loader2, Download, Copy, Check, Shield, Key, CheckCircle2 } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { TOTPQRCode } from './totp-qr-code'
import { totpApi, type TOTPSetupResponse } from '@/lib/api/users'

interface TOTPSetupWizardProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess?: () => void
}

type Step = 1 | 2 | 3 | 4 | 5

export function TOTPSetupWizard({ open, onOpenChange, onSuccess }: TOTPSetupWizardProps) {
  const t = useTranslations('auth')
  const tCommon = useTranslations('common')

  const [step, setStep] = React.useState<Step>(1)
  const [loading, setLoading] = React.useState(false)
  const [setupData, setSetupData] = React.useState<TOTPSetupResponse | null>(null)
  const [verificationCode, setVerificationCode] = React.useState('')
  const [backupCodesCopied, setBackupCodesCopied] = React.useState(false)

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setStep(1)
      setSetupData(null)
      setVerificationCode('')
      setBackupCodesCopied(false)
    }
  }, [open])

  // Step 1: Introduction
  const handleStartSetup = async () => {
    try {
      setLoading(true)
      const data = await totpApi.setup()
      setSetupData(data)
      setStep(2)
    } catch {
      // Error handled by API client
    } finally {
      setLoading(false)
    }
  }

  // Step 3: Verify code
  const handleVerifyCode = async () => {
    if (verificationCode.length !== 6) {
      return
    }

    try {
      setLoading(true)
      await totpApi.enable(verificationCode)
      toast.success(t('twoFactorEnabledSuccess'))
      setStep(4)
    } catch {
      // Error handled by API client
      setVerificationCode('')
    } finally {
      setLoading(false)
    }
  }

  // Step 4: Download backup codes
  const handleDownloadCodes = () => {
    if (!setupData) return

    const content = setupData.backup_codes.join('\n')
    const blob = new Blob([content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'clouisle-backup-codes.txt'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleCopyCodes = async () => {
    if (!setupData) return

    await navigator.clipboard.writeText(setupData.backup_codes.join('\n'))
    setBackupCodesCopied(true)
    toast.success(t('setupStep4CodesCopied'))
    setTimeout(() => setBackupCodesCopied(false), 2000)
  }

  // Step 5: Finish
  const handleFinish = () => {
    onOpenChange(false)
    onSuccess?.()
  }

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <div className="space-y-6">
            <div className="flex justify-center">
              <div className="rounded-full bg-primary/10 p-6">
                <Shield className="h-12 w-12 text-primary" />
              </div>
            </div>
            <div className="space-y-2 text-center">
              <h3 className="text-lg font-semibold">{t('setupStep1Title')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('setupStep1Description')}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {tCommon('cancel')}
              </Button>
              <Button onClick={handleStartSetup} disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('setupStepNext')}
              </Button>
            </div>
          </div>
        )

      case 2:
        return (
          <div className="space-y-6">
            <div className="space-y-2 text-center">
              <h3 className="text-lg font-semibold">{t('setupStep2Title')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('setupStep2Description')}
              </p>
            </div>
            {setupData && (
              <TOTPQRCode secret={setupData.secret} qrCode={setupData.qr_code} />
            )}
            <div className="flex justify-between gap-2">
              <Button variant="outline" onClick={() => setStep(1)}>
                {t('setupStepBack')}
              </Button>
              <Button onClick={() => setStep(3)}>
                {t('setupStepNext')}
              </Button>
            </div>
          </div>
        )

      case 3:
        return (
          <div className="space-y-6">
            <div className="space-y-2 text-center">
              <h3 className="text-lg font-semibold">{t('setupStep3Title')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('setupStep3Description')}
              </p>
            </div>
            <div className="flex justify-center">
              <InputOTP
                maxLength={6}
                value={verificationCode}
                onChange={setVerificationCode}
                onComplete={handleVerifyCode}
              >
                <InputOTPGroup>
                  <InputOTPSlot index={0} />
                  <InputOTPSlot index={1} />
                  <InputOTPSlot index={2} />
                  <InputOTPSlot index={3} />
                  <InputOTPSlot index={4} />
                  <InputOTPSlot index={5} />
                </InputOTPGroup>
              </InputOTP>
            </div>
            <div className="flex justify-between gap-2">
              <Button variant="outline" onClick={() => setStep(2)}>
                {t('setupStepBack')}
              </Button>
              <Button
                onClick={handleVerifyCode}
                disabled={verificationCode.length !== 6 || loading}
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('verifyCode')}
              </Button>
            </div>
          </div>
        )

      case 4:
        return (
          <div className="space-y-6">
            <div className="space-y-2 text-center">
              <h3 className="text-lg font-semibold">{t('setupStep4Title')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('setupStep4Description')}
              </p>
            </div>
            <Alert>
              <Key className="h-4 w-4" />
              <AlertDescription>{t('setupStep4Warning')}</AlertDescription>
            </Alert>
            {setupData && (
              <div className="rounded-lg border bg-muted/50 p-4">
                <div className="grid grid-cols-2 gap-2 font-mono text-sm">
                  {setupData.backup_codes.map((code, index) => (
                    <div key={index} className="rounded bg-background p-2 text-center">
                      {code}
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={handleDownloadCodes}
              >
                <Download className="mr-2 h-4 w-4" />
                {t('setupStep4Download')}
              </Button>
              <Button
                variant="outline"
                className="flex-1"
                onClick={handleCopyCodes}
              >
                {backupCodesCopied ? (
                  <Check className="mr-2 h-4 w-4 text-green-600" />
                ) : (
                  <Copy className="mr-2 h-4 w-4" />
                )}
                {t('setupStep4Copy')}
              </Button>
            </div>
            <div className="flex justify-end">
              <Button onClick={() => setStep(5)}>
                {t('setupStepNext')}
              </Button>
            </div>
          </div>
        )

      case 5:
        return (
          <div className="space-y-6">
            <div className="flex justify-center">
              <div className="rounded-full bg-green-100 p-6 dark:bg-green-950">
                <CheckCircle2 className="h-12 w-12 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <div className="space-y-2 text-center">
              <h3 className="text-lg font-semibold">{t('setupStep5Title')}</h3>
              <p className="text-sm text-muted-foreground">
                {t('setupStep5Description')}
              </p>
            </div>
            <div className="flex justify-end">
              <Button onClick={handleFinish}>
                {t('setupStepFinish')}
              </Button>
            </div>
          </div>
        )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] z-[60]" overlayClassName="z-[60]" open={open}>
        <DialogHeader>
          <DialogTitle>{t('setupTwoFactorTitle')}</DialogTitle>
          <DialogDescription>
            Step {step} of 5
          </DialogDescription>
        </DialogHeader>
        {renderStep()}
      </DialogContent>
    </Dialog>
  )
}

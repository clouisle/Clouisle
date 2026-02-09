'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { authApi, ApiError } from '@/lib/api'
import { isValidEmail } from '@/lib/utils'
import { Loader2, Mail, CheckCircle2, ArrowLeft, KeyRound, ChevronDown } from 'lucide-react'

type Step = 'email' | 'reset' | 'success'

export function ForgotPasswordForm() {
  const t = useTranslations('auth')
  const router = useRouter()

  const [step, setStep] = React.useState<Step>('email')
  const [email, setEmail] = React.useState('')
  const [verificationCode, setVerificationCode] = React.useState('')
  const [newPassword, setNewPassword] = React.useState('')
  const [confirmPassword, setConfirmPassword] = React.useState('')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)
  const [resendCooldown, setResendCooldown] = React.useState(0)
  const [showCodeInput, setShowCodeInput] = React.useState(false)
  
  // 倒计时
  React.useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCooldown])
  
  // 清除单个字段错误
  const clearFieldError = (field: string) => {
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const next = { ...prev }
        delete next[field]
        return next
      })
    }
  }

  // 步骤1：发送重置密码邮件
  const handleSendEmail = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    if (!email) {
      setFieldErrors({ email: t('emailRequired') })
      return
    }

    if (!isValidEmail(email)) {
      setFieldErrors({ email: t('invalidEmail') })
      return
    }

    setLoading(true)

    try {
      await authApi.forgotPassword(email)
      setResendCooldown(60)
      setStep('reset')
      toast.success(t('resetPasswordEmailSent'))
    } catch (err) {
      if (err instanceof ApiError && err.isValidationError()) {
        setFieldErrors(err.getFieldErrors())
      }
    } finally {
      setLoading(false)
    }
  }

  // 步骤2：重置密码
  const handleResetPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    // 验证密码匹配
    if (newPassword !== confirmPassword) {
      setFieldErrors({ confirmPassword: t('passwordMismatch') })
      return
    }

    // 验证密码长度
    if (newPassword.length < 6) {
      setFieldErrors({ newPassword: t('passwordTooShort') })
      return
    }

    // 验证验证码
    if (verificationCode.length !== 6) {
      setFieldErrors({ code: t('verificationCodeRequired') })
      return
    }

    setLoading(true)

    try {
      await authApi.resetPassword(email, verificationCode, newPassword)
      toast.success(t('passwordResetSuccess'))
      setStep('success')
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isValidationError()) {
          setFieldErrors(err.getFieldErrors())
        } else if (err.code === 5005) {
          // VERIFICATION_CODE_INVALID
          setFieldErrors({ code: t('verificationCodeInvalid') })
        }
      }
    } finally {
      setLoading(false)
    }
  }

  // 重新发送邮件
  const handleResend = async () => {
    if (resendCooldown > 0) return
    
    try {
      await authApi.forgotPassword(email)
      setResendCooldown(60)
      toast.success(t('resetPasswordEmailSent'))
    } catch {
      // 错误已由拦截器处理
    }
  }

  // 返回上一步
  const handleBack = () => {
    setStep('email')
    setVerificationCode('')
    setNewPassword('')
    setConfirmPassword('')
    setFieldErrors({})
  }

  // 跳转到登录页
  const handleGoToLogin = () => {
    router.push('/login')
  }

  // 步骤1：输入邮箱
  if (step === 'email') {
    return (
      <form onSubmit={handleSendEmail} className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="email">{t('email')}</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              clearFieldError('email')
            }}
            placeholder="john@example.com"
            required
            disabled={loading}
            aria-invalid={!!fieldErrors.email}
          />
          {fieldErrors.email && (
            <p className="text-sm text-destructive">{fieldErrors.email}</p>
          )}
        </div>
        
        <Button type="submit" className="w-full" disabled={loading}>
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {t('sendResetEmail')}
        </Button>
        
        <div className="text-center">
          <button
            type="button"
            onClick={handleGoToLogin}
            className="text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="inline-block mr-1 h-4 w-4" />
            {t('backToLogin')}
          </button>
        </div>
      </form>
    )
  }

  // 步骤2：输入验证码和新密码
  if (step === 'reset') {
    return (
      <div className="space-y-6">
        <button
          type="button"
          onClick={handleBack}
          className="flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          {t('changeEmail')}
        </button>

        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Mail className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-semibold">{t('checkYourEmail')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('resetPasswordEmailSentTo')} <span className="font-medium text-foreground">{email}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            {t('checkEmailForLink')}
          </p>
        </div>

        <div className="space-y-4">
          <div className="text-center">
            <button
              type="button"
              onClick={() => setShowCodeInput(!showCodeInput)}
              className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {t('orEnterCodeManually')}
              <ChevronDown className={`ml-1 h-4 w-4 transition-transform ${showCodeInput ? 'rotate-180' : ''}`} />
            </button>
          </div>

          {showCodeInput && (
            <form onSubmit={handleResetPassword} className="space-y-4">
              <div className="space-y-2">
                <Label>{t('verificationCode')}</Label>
                <div className="flex justify-center">
                  <InputOTP
                    maxLength={6}
                    value={verificationCode}
                    onChange={(value) => {
                      setVerificationCode(value)
                      clearFieldError('code')
                    }}
                    disabled={loading}
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
                {fieldErrors.code && (
                  <p className="text-sm text-destructive text-center">{fieldErrors.code}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="newPassword">{t('newPassword')}</Label>
                <Input
                  id="newPassword"
                  type="password"
                  value={newPassword}
                  onChange={(e) => {
                    setNewPassword(e.target.value)
                    clearFieldError('newPassword')
                  }}
                  required
                  disabled={loading}
                  aria-invalid={!!fieldErrors.newPassword}
                />
                {fieldErrors.newPassword && (
                  <p className="text-sm text-destructive">{fieldErrors.newPassword}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword">{t('confirmNewPassword')}</Label>
                <Input
                  id="confirmPassword"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => {
                    setConfirmPassword(e.target.value)
                    clearFieldError('confirmPassword')
                  }}
                  required
                  disabled={loading}
                  aria-invalid={!!fieldErrors.confirmPassword}
                />
                {fieldErrors.confirmPassword && (
                  <p className="text-sm text-destructive">{fieldErrors.confirmPassword}</p>
                )}
              </div>

              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('resetPassword')}
              </Button>
            </form>
          )}

          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              {t('didntReceiveEmail')}{' '}
              {resendCooldown > 0 ? (
                <span className="text-muted-foreground">
                  {t('resendIn', { seconds: resendCooldown })}
                </span>
              ) : (
                <button
                  onClick={handleResend}
                  className="text-primary hover:underline"
                  type="button"
                >
                  {t('resendEmail')}
                </button>
              )}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // 步骤3：成功
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center space-y-2">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
          <CheckCircle2 className="h-6 w-6 text-green-500" />
        </div>
        <h3 className="font-semibold">{t('passwordResetComplete')}</h3>
        <p className="text-sm text-muted-foreground">
          {t('passwordResetSuccessMessage')}
        </p>
      </div>
      
      <Button onClick={handleGoToLogin} className="w-full">
        <KeyRound className="mr-2 h-4 w-4" />
        {t('goToLogin')}
      </Button>
    </div>
  )
}

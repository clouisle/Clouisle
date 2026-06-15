'use client'

import * as React from 'react'
import dynamic from 'next/dynamic'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { useTheme } from 'next-themes'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { authApi, ApiError, User, siteSettingsApi, type PublicSiteSettings } from '@/lib/api'
import {
  clearValidationError,
  formatValidationSummaryMessage,
  getValidationSummaryEntries,
  normalizeValidationErrorsRaw,
} from '@/lib/validation'
import { isValidEmail } from '@/lib/utils'
import { Checkbox } from '@/components/ui/checkbox'
import { FieldError } from '@/components/ui/field'
import { Loader2, Mail, CheckCircle2, ArrowLeft, ChevronDown } from 'lucide-react'

type Step = 'form' | 'verification' | 'success'

const MarkdownPreview = dynamic(() => import('@uiw/react-md-editor').then(mod => mod.default.Markdown), { ssr: false })

function LegalMarkdown({ source }: { source: string }) {
  const { resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="wmde-markdown text-sm" data-color-mode={mounted && resolvedTheme === 'dark' ? 'dark' : 'light'}>
      <MarkdownPreview source={source} />
    </div>
  )
}

/**
 * 解析带参数的错误 key，如 "password_min_length:8" -> { key: "password_min_length", params: { length: "8" } }
 */
function parseErrorKey(errorKey: string): { key: string; params: Record<string, string> } {
  const parts = errorKey.split(':')
  const key = parts[0]
  const params: Record<string, string> = {}
  if (parts.length > 1) {
    // 对于 password_min_length:8，参数名为 length
    if (key === 'password_min_length') {
      params.length = parts[1]
    } else {
      params.value = parts[1]
    }
  }
  return { key, params }
}

function RegisterLegalEntry({ label, url, text }: { label: string; url: string; text: string }) {
  if (url) {
    return (
      <a href={url} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-foreground">
        {label}
      </a>
    )
  }

  if (!text) {
    return null
  }

  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="bg-transparent border-none p-0 underline underline-offset-4 hover:text-foreground"
        >
          {label}
        </button>
      </DialogTrigger>
      <DialogContent className="max-h-[80vh] overflow-hidden sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{label}</DialogTitle>
        </DialogHeader>
        <div className="max-h-[60vh] overflow-y-auto text-sm text-foreground">
          <LegalMarkdown source={text} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

export function RegisterForm() {
  const t = useTranslations('auth')
  const router = useRouter()

  const [step, setStep] = React.useState<Step>('form')
  const [username, setUsername] = React.useState('')
  const [email, setEmail] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [confirmPassword, setConfirmPassword] = React.useState('')
  const [verificationCode, setVerificationCode] = React.useState('')
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)
  const [resendCooldown, setResendCooldown] = React.useState(0)
  const [registeredUser, setRegisteredUser] = React.useState<User | null>(null)
  const [showCodeInput, setShowCodeInput] = React.useState(false)
  const [termsAccepted, setTermsAccepted] = React.useState(false)
  const [siteSettings, setSiteSettings] = React.useState<PublicSiteSettings | null>(null)

  // 倒计时
  React.useEffect(() => {
    siteSettingsApi.getPublic()
      .then(setSiteSettings)
      .catch(() => setSiteSettings(null))
  }, [])

  React.useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCooldown])

  // 翻译错误消息
  const translateErrors = (errors: Record<string, string[]>): Record<string, string> => {
    const result: Record<string, string> = {}
    for (const [field, errorKeys] of Object.entries(errors)) {
      const translatedErrors = errorKeys.map(errorKey => {
        const { key, params } = parseErrorKey(errorKey)
        try {
          return t(key, params)
        } catch {
          return errorKey
        }
      })
      result[field] = translatedErrors.join('; ')
    }
    return result
  }

  const summaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['username', 'email', 'password', 'confirmPassword', 'terms_accepted', 'code']),
    [fieldErrors]
  )
  const summaryFieldLabels = React.useMemo(
    () => ({
      username: t('username'),
      email: t('email'),
      password: t('password'),
      confirmPassword: t('confirmPassword'),
      terms_accepted: t('agreement'),
      code: t('verificationCode'),
    }),
    [t]
  )

  // 步骤1：提交注册表单
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})

    // 验证邮箱格式
    if (!isValidEmail(email)) {
      setFieldErrors({ email: t('invalidEmail') })
      return
    }

    // 验证密码匹配
    if (password !== confirmPassword) {
      setFieldErrors({ confirmPassword: t('passwordMismatch') })
      return
    }

    // 验证密码长度
    if (password.length < 6) {
      setFieldErrors({ password: t('passwordTooShort') })
      return
    }

    if (siteSettings?.require_terms_acceptance_on_register && !termsAccepted) {
      setFieldErrors({ terms_accepted: t('termsAcceptanceRequired') })
      return
    }

    setLoading(true)

    try {
      const user = await authApi.register({
        username,
        email,
        password,
        terms_accepted: siteSettings?.require_terms_acceptance_on_register ? termsAccepted : undefined,
      })
      setRegisteredUser(user)

      // 如果是第一个用户（超级管理员），直接成功
      if (user.is_superuser) {
        toast.success(t('registerSuccessActive'))
        setStep('success')
      } else if (user.email_verified) {
        // 邮箱已验证（不需要验证的情况）
        setStep('success')
      } else {
        // 需要邮箱验证，发送验证邮件
        try {
          await authApi.sendVerification(email, 'register')
          setResendCooldown(60)
          setStep('verification')
          toast.success(t('verificationEmailSent'))
        } catch {
          // 如果发送失败（如 SMTP 未配置），仍然进入验证步骤
          setStep('verification')
        }
      }
    } catch (err) {
      const rawErrors = normalizeValidationErrorsRaw(err)
      if (Object.keys(rawErrors).length > 0) {
        setFieldErrors(translateErrors(rawErrors))
      }
    } finally {
      setLoading(false)
    }
  }

  // 步骤2：验证邮箱
  const handleVerify = async () => {
    if (verificationCode.length !== 6) return
    
    setLoading(true)
    setFieldErrors({})

    try {
      await authApi.verifyEmail(email, verificationCode, 'register')
      toast.success(t('emailVerified'))
      setStep('success')
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors({ code: t('verificationCodeInvalid') })
      }
    } finally {
      setLoading(false)
    }
  }

  // 重新发送验证邮件
  const handleResend = async () => {
    if (resendCooldown > 0) return
    
    try {
      await authApi.resendVerification(email)
      setResendCooldown(60)
      toast.success(t('verificationEmailSent'))
    } catch {
      // 错误已由拦截器处理
    }
  }

  // 返回上一步
  const handleBack = () => {
    setStep('form')
    setVerificationCode('')
    setFieldErrors({})
  }

  // 跳转到登录页
  const handleGoToLogin = () => {
    router.push('/login')
  }

  // 步骤1：注册表单
  if (step === 'form') {
    return (
      <form onSubmit={handleSubmit} className="space-y-4">
        {summaryEntries.length > 0 && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
            {summaryEntries.map(([field, message]) => (
              <FieldError key={field}>
                {formatValidationSummaryMessage(field, message, summaryFieldLabels)}
              </FieldError>
            ))}
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="username">{t('username')}</Label>
          <Input
            id="username"
            type="text"
            value={username}
            onChange={(e) => {
              setUsername(e.target.value)
              setFieldErrors((prev) => clearValidationError(prev, 'username'))
            }}
            placeholder={t('usernamePlaceholder')}
            required
            disabled={loading}
            aria-invalid={!!fieldErrors.username}
          />
          <FieldError>{fieldErrors.username}</FieldError>
        </div>
        
        <div className="space-y-2">
          <Label htmlFor="email">{t('email')}</Label>
          <Input
            id="email"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value)
              setFieldErrors((prev) => clearValidationError(prev, 'email'))
            }}
            placeholder={t('emailPlaceholder')}
            required
            disabled={loading}
            aria-invalid={!!fieldErrors.email}
          />
          <FieldError>{fieldErrors.email}</FieldError>
        </div>

        <div className="space-y-2">
          <Label htmlFor="password">{t('password')}</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value)
              setFieldErrors((prev) => clearValidationError(prev, 'password'))
            }}
            required
            placeholder={t('passwordPlaceholder')}
            disabled={loading}
            aria-invalid={!!fieldErrors.password}
          />
          <FieldError>{fieldErrors.password}</FieldError>
        </div>

        <div className="space-y-2">
          <Label htmlFor="confirmPassword">{t('confirmPassword')}</Label>
          <Input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value)
              setFieldErrors((prev) => clearValidationError(prev, 'confirmPassword'))
            }}
            required
            placeholder={t('confirmPasswordPlaceholder')}
            disabled={loading}
            aria-invalid={!!fieldErrors.confirmPassword}
          />
          <FieldError>{fieldErrors.confirmPassword}</FieldError>
        </div>
        {siteSettings?.require_terms_acceptance_on_register && (
          <div className="space-y-2">
            <div className="flex items-start gap-2">
              <Checkbox
                id="termsAccepted"
                checked={termsAccepted}
                onCheckedChange={(checked) => {
                  setTermsAccepted(checked === true)
                  setFieldErrors((prev) => clearValidationError(prev, 'terms_accepted'))
                }}
                disabled={loading}
                aria-invalid={!!fieldErrors.terms_accepted}
                className="mt-0.5"
              />
              <Label htmlFor="termsAccepted" className="text-sm font-normal leading-relaxed">
                {t('agreeToLegalEntries')}
                {siteSettings.terms_enabled && (siteSettings.terms_url || siteSettings.terms_text) && (
                  <>
                    {' '}
                    <RegisterLegalEntry
                      label={t('termsOfService')}
                      url={siteSettings.terms_url}
                      text={siteSettings.terms_text}
                    />
                  </>
                )}
                {siteSettings.privacy_enabled && (siteSettings.privacy_url || siteSettings.privacy_text) && (
                  <>
                    {' '}
                    <RegisterLegalEntry
                      label={t('privacyPolicy')}
                      url={siteSettings.privacy_url}
                      text={siteSettings.privacy_text}
                    />
                  </>
                )}
              </Label>
            </div>
            <FieldError>{fieldErrors.terms_accepted}</FieldError>
          </div>
        )}

        <Button type="submit" className="w-full" disabled={loading}>
          {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {loading ? t('registering') : t('register')}
        </Button>
      </form>
    )
  }

  // 步骤2：邮箱验证
  if (step === 'verification') {
    return (
      <div className="space-y-6">
        <button
          onClick={handleBack}
          className="flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          {t('backToRegister')}
        </button>

        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Mail className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-semibold">{t('verifyYourEmail')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('verificationEmailSentTo')} <span className="font-medium text-foreground">{email}</span>
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
            <>
              <FieldError className="text-center">{fieldErrors.code}</FieldError>
              <div className="space-y-2">
                <Label>{t('verificationCode')}</Label>
                <div className="flex justify-center">
                  <InputOTP
                    maxLength={6}
                    value={verificationCode}
                    onChange={(value) => {
                      setVerificationCode(value)
                      setFieldErrors((prev) => clearValidationError(prev, 'code'))
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
              </div>

              <Button
                onClick={handleVerify}
                className="w-full"
                disabled={loading || verificationCode.length !== 6}
              >
                {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t('verifyEmail')}
              </Button>
            </>
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

  // 步骤3：注册成功
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center text-center space-y-2">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-green-500/10">
          <CheckCircle2 className="h-6 w-6 text-green-500" />
        </div>
        <h3 className="font-semibold">{t('registrationComplete')}</h3>
        <p className="text-sm text-muted-foreground">
          {registeredUser?.is_active 
            ? t('accountActivated')
            : t('accountPendingApproval')
          }
        </p>
      </div>
      
      <Button onClick={handleGoToLogin} className="w-full">
        {t('goToLogin')}
      </Button>
    </div>
  )
}

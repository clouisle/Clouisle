'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { FieldError } from '@/components/ui/field'
import { Label } from '@/components/ui/label'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { authApi, usersApi, siteSettingsApi, ssoApi, ApiError, type CaptchaPointerPoint, type CaptchaResponse, type SSOProvider } from '@/lib/api'
import { clearValidationError, formatValidationSummaryMessage, getValidationSummaryEntries } from '@/lib/validation'
import { Loader2, Mail, ArrowLeft, ChevronDown } from 'lucide-react'
import { Separator } from '@/components/ui/separator'

type LoginStep = 'login' | 'verification' | 'totp'

type ClickChallenge = {
  type: 'click-choice'
  options: string[]
  created_at: number
}

function parseClickChallenge(challenge: string): ClickChallenge | null {
  try {
    const parsed = JSON.parse(challenge) as Partial<ClickChallenge>
    if (
      parsed.type !== 'click-choice' ||
      !Array.isArray(parsed.options) ||
      typeof parsed.created_at !== 'number'
    ) {
      return null
    }
    return parsed as ClickChallenge
  } catch {
    return null
  }
}

export function LoginForm() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [step, setStep] = React.useState<LoginStep>('login')
  const [username, setUsername] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [captchaToken, setCaptchaToken] = React.useState('')
  const [captcha, setCaptcha] = React.useState<CaptchaResponse | null>(null)
  const [captchaEnabled, setCaptchaEnabled] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)
  const [captchaLoading, setCaptchaLoading] = React.useState(false)
  const [ssoProviders, setSsoProviders] = React.useState<SSOProvider[]>([])
  const [ssoEnabled, setSsoEnabled] = React.useState(false)
  const [passwordLoginAllowed, setPasswordLoginAllowed] = React.useState(true)
  const [unverifiedEmail, setUnverifiedEmail] = React.useState('')
  const [verificationCode, setVerificationCode] = React.useState('')
  const [showCodeInput, setShowCodeInput] = React.useState(false)
  const [resendCooldown, setResendCooldown] = React.useState(0)
  const pointerTraceRef = React.useRef<CaptchaPointerPoint[]>([])
  const captchaStartedAtRef = React.useRef(0)

  const resetCaptchaTrace = React.useCallback(() => {
    pointerTraceRef.current = []
    captchaStartedAtRef.current = performance.now()
  }, [])

  const recordCaptchaPointer = React.useCallback((
    event: React.PointerEvent<HTMLElement>,
    eventName: CaptchaPointerPoint['event']
  ) => {
    if (pointerTraceRef.current.length >= 80) return
    const rect = event.currentTarget.getBoundingClientRect()
    pointerTraceRef.current.push({
      x: Math.round(event.clientX - rect.left),
      y: Math.round(event.clientY - rect.top),
      t: Math.round(performance.now() - captchaStartedAtRef.current),
      event: eventName,
    })
  }, [])

  const seedKeyboardCaptchaTrace = (event: React.KeyboardEvent<HTMLElement>) => {
    if ((event.key !== 'Enter' && event.key !== ' ') || pointerTraceRef.current.length > 0) return
    const rect = event.currentTarget.getBoundingClientRect()
    const endX = Math.round(Math.max(24, Math.min(rect.width - 24, rect.width / 2)))
    const endY = Math.round(Math.max(16, Math.min(rect.height - 8, rect.height / 2)))
    captchaStartedAtRef.current = performance.now() - 700
    pointerTraceRef.current = [
      { x: endX + 120, y: endY - 2, t: 0, event: 'enter' },
      { x: endX + 92, y: endY + 5, t: 120, event: 'move' },
      { x: endX + 56, y: endY - 4, t: 260, event: 'move' },
      { x: endX + 22, y: endY + 3, t: 390, event: 'move' },
      { x: endX, y: endY, t: 520, event: 'move' },
      { x: endX, y: endY, t: 640, event: 'down' },
      { x: endX + 1, y: endY + 1, t: 700, event: 'up' },
    ]
  }

  // TOTP
  const [tempToken, setTempToken] = React.useState('')
  const [totpCode, setTotpCode] = React.useState('')
  const [useBackupCode, setUseBackupCode] = React.useState(false)
  const [backupCode, setBackupCode] = React.useState('')

  // 倒计时
  React.useEffect(() => {
    if (resendCooldown > 0) {
      const timer = setTimeout(() => setResendCooldown(resendCooldown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendCooldown])

  // 加载验证码
  const loadCaptcha = React.useCallback(async () => {
    setCaptchaLoading(true)
    try {
      const data = await authApi.getCaptcha()
      setCaptcha(data)
      setCaptchaToken('')
      resetCaptchaTrace()
      clearFieldError('captcha')
    } catch {
      // 获取验证码失败
    } finally {
      setCaptchaLoading(false)
    }
  }, [resetCaptchaTrace])

  // 获取站点设置和 SSO 提供商
  React.useEffect(() => {
    const loadSettings = async () => {
      try {
        const settings = await siteSettingsApi.getPublic()
        setCaptchaEnabled(settings.enable_captcha)
        setSsoEnabled(settings.sso_enabled)
        setPasswordLoginAllowed(settings.sso_allow_password_login)

        // 加载 SSO 提供商
        if (settings.sso_enabled) {
          const providers = await ssoApi.getPublicProviders()
          setSsoProviders(providers)
        }
      } catch {
        // 获取设置失败，使用默认值
      }
    }
    loadSettings()
  }, [loadCaptcha])
  
  // 清除单个字段错误
  const clearFieldError = (field: string) => {
    setFieldErrors((prev) => clearValidationError(prev, field))
  }

  const loginSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['username', 'password', 'captcha']),
    [fieldErrors]
  )
  const verificationSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['code']),
    [fieldErrors]
  )
  const totpSummaryEntries = React.useMemo(
    () => getValidationSummaryEntries(fieldErrors, ['totp']),
    [fieldErrors]
  )
  const loginSummaryFieldLabels = React.useMemo(
    () => ({
      username: t('username'),
      password: t('password'),
      captcha: t('captcha'),
    }),
    [t]
  )
  const captchaChallenge = React.useMemo(
    () => parseClickChallenge(captcha?.challenge || ''),
    [captcha]
  )
  const verificationSummaryFieldLabels = React.useMemo(
    () => ({
      code: t('verificationCode'),
    }),
    [t]
  )
  const totpSummaryFieldLabels = React.useMemo(
    () => ({
      totp: t('verificationCode6Digit'),
    }),
    [t]
  )

  const shouldShowCaptcha = captchaEnabled && Boolean(username.trim() && password)

  React.useEffect(() => {
    if (shouldShowCaptcha && !captcha && !captchaLoading) {
      loadCaptcha()
    }
  }, [captcha, captchaLoading, loadCaptcha, shouldShowCaptcha])

  const handleCaptchaClick = async () => {
    const challenge = captcha ? parseClickChallenge(captcha.challenge) : null
    if (!captcha || !challenge) {
      setFieldErrors({ captcha: t('captchaLoadFailed') })
      loadCaptcha()
      return
    }

    const pointer = pointerTraceRef.current
    setCaptchaLoading(true)
    try {
      const proof = await authApi.completeCaptchaClick({
        captcha_id: captcha.captcha_id,
        challenge: captcha.challenge,
        clicked_option: challenge.options[0] || '',
        elapsed_ms: Math.max(0, Math.round(performance.now() - captchaStartedAtRef.current)),
        pointer,
      })
      setCaptchaToken(proof.captcha_token)
      clearFieldError('captcha')
    } catch {
      setCaptchaToken('')
      setFieldErrors({ captcha: t('captchaInvalid') })
      loadCaptcha()
    } finally {
      setCaptchaLoading(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    
    // 验证码检查
    if (captchaEnabled && !captchaToken) {
      setFieldErrors({ captcha: t('captchaRequired') })
      if (!captcha) loadCaptcha()
      return
    }
    
    setLoading(true)

    try {
      const token = await authApi.login({
        username,
        password,
        captcha_id: captcha?.captcha_id,
        captcha_token: captchaToken || undefined,
      })

      // 检查是否需要 TOTP 验证
      if (token.requires_totp && token.temp_token) {
        setTempToken(token.temp_token)
        setStep('totp')
        return
      }

      // 检查是否需要设置 TOTP（管理员要求）
      if (token.requires_totp_setup && token.temp_token) {
        setTempToken(token.temp_token)
        toast.info(t('totpSetupRequiredByAdmin'))
        // 保存临时 token 并跳转到设置页面
        localStorage.setItem('temp_token', token.temp_token)
        router.push('/totp-setup')
        return
      }

      // 保存 token
      localStorage.setItem('access_token', token.access_token)

      // 检查是否需要强制修改密码
      if (token.force_password_change) {
        toast.success(t('loginSuccess'))
        router.push(`/change-password?reason=${token.reason || 'force'}`)
        return
      }

      // 同步当前浏览器语言设置到后端用户数据
      try {
        const user = await authApi.getCurrentUser({ skipAuthRedirect: true })
        if (!user.locale || user.locale !== locale) {
          // 用户数据库中没有语言设置或与当前浏览器语言不同，同步到后端
          await usersApi.updateProfile({ locale }, { skipAuthRedirect: true })
        }
      } catch {
        // 同步语言设置失败，不影响登录流程
      }

      toast.success(t('loginSuccess'))
      // 跳转到重定向页面或 app
      const redirect = searchParams.get('redirect')
      router.push(redirect || '/app')
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isValidationError()) {
          // 字段级验证错误，显示在对应输入框下方
          setFieldErrors(err.getFieldErrors())
        }
        // 验证码错误时刷新验证码 (CAPTCHA_INVALID = 5303, CAPTCHA_REQUIRED = 5302)
        if (err.code === 5303 || err.code === 5302) {
          setFieldErrors({ captcha: t('captchaInvalid') })
          if (captchaEnabled) {
            loadCaptcha()
          }
        }
        // 邮箱未验证 (EMAIL_NOT_VERIFIED = 5004)
        const errData = err.data as Record<string, unknown> | undefined
        if (err.code === 5004 && errData?.email) {
          const emailAddr = errData.email as string
          setUnverifiedEmail(emailAddr)
          try {
            await authApi.sendVerification(emailAddr, 'register')
            setResendCooldown(60)
            toast.success(t('verificationEmailSent'))
          } catch {
            // SMTP 未配置等情况，仍进入验证步骤
          }
          setStep('verification')
        }
      }
      // 其他错误已由 axios 拦截器统一处理显示 toast
    } finally {
      setLoading(false)
    }
  }

  const handleSSOLogin = (providerName: string) => {
    const redirect = searchParams.get('redirect')
    ssoApi.initiateLogin(providerName, redirect || undefined)
  }

  // 验证邮箱验证码
  const handleVerify = async () => {
    if (verificationCode.length !== 6) return

    setLoading(true)
    setFieldErrors({})

    try {
      await authApi.verifyEmail(unverifiedEmail, verificationCode, 'register')
      toast.success(t('emailVerified'))
      setStep('login')
      setVerificationCode('')
      setShowCodeInput(false)
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.isValidationError()) {
          setFieldErrors(err.getFieldErrors())
        } else {
          setFieldErrors({ code: t('verificationCodeInvalid') })
        }
      }
    } finally {
      setLoading(false)
    }
  }

  // 重新发送验证邮件
  const handleResend = async () => {
    if (resendCooldown > 0) return

    try {
      await authApi.sendVerification(unverifiedEmail, 'register')
      setResendCooldown(60)
      toast.success(t('verificationEmailSent'))
    } catch {
      // 错误已由拦截器处理
    }
  }

  // 验证 TOTP 码
  const handleVerifyTOTP = async () => {
    const code = useBackupCode ? backupCode.replace('-', '') : totpCode
    if (!code || (useBackupCode && code.length !== 8) || (!useBackupCode && code.length !== 6)) {
      return
    }

    setLoading(true)
    setFieldErrors({})

    try {
      const token = await authApi.verifyTOTP(tempToken, code, useBackupCode)

      // 保存 token
      localStorage.setItem('access_token', token.access_token)

      // 检查是否需要强制修改密码
      if (token.force_password_change) {
        toast.success(t('loginSuccess'))
        router.push(`/change-password?reason=${token.reason || 'force'}`)
        return
      }

      // 同步当前浏览器语言设置到后端用户数据
      try {
        const user = await authApi.getCurrentUser({ skipAuthRedirect: true })
        if (!user.locale || user.locale !== locale) {
          await usersApi.updateProfile({ locale }, { skipAuthRedirect: true })
        }
      } catch {
        // 同步语言设置失败，不影响登录流程
      }

      toast.success(t('loginSuccess'))
      const redirect = searchParams.get('redirect')
      router.push(redirect || '/app')
    } catch (err) {
      if (err instanceof ApiError) {
        // TOTP_RATE_LIMITED = 5312
        if (err.code === 5312) {
          const errData = err.data as Record<string, unknown> | undefined
          const seconds = errData?.seconds as number | undefined
          setFieldErrors({ totp: t('twoFactorRateLimited', { seconds: seconds || 0 }) })
        } else {
          setFieldErrors({ totp: t('twoFactorInvalid') })
        }
        setTotpCode('')
        setBackupCode('')
      }
    } finally {
      setLoading(false)
    }
  }

  // 返回登录
  const handleBackToLogin = () => {
    setStep('login')
    setVerificationCode('')
    setFieldErrors({})
    setShowCodeInput(false)
    setTotpCode('')
    setBackupCode('')
    setUseBackupCode(false)
  }

  // TOTP 验证步骤
  if (step === 'totp') {
    return (
      <div className="space-y-6">
        <button
          onClick={handleBackToLogin}
          className="flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          {t('backToLogin')}
        </button>

        <div className="space-y-2 text-center">
          <h3 className="text-lg font-semibold">{t('twoFactorRequired')}</h3>
          <p className="text-sm text-muted-foreground">
            {useBackupCode ? t('backupCodeLabel') : t('twoFactorDescription')}
          </p>
        </div>

        <div className="space-y-4">
          {totpSummaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {totpSummaryEntries.map(([field, message]) => (
                <FieldError key={field}>{formatValidationSummaryMessage(field, message, totpSummaryFieldLabels)}</FieldError>
              ))}
            </div>
          )}

          {useBackupCode ? (
            <div className="space-y-2">
              <Label>{t('backupCodeLabel')}</Label>
              <Input
                type="text"
                placeholder={t('backupCodePlaceholder')}
                value={backupCode}
                onChange={(e) => {
                  clearFieldError('totp')
                  setBackupCode(e.target.value)
                }}
                maxLength={9}
                disabled={loading}
              />
              <FieldError>{fieldErrors.totp}</FieldError>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>{t('verificationCode6Digit')}</Label>
              <div className="flex justify-center">
                <InputOTP
                  maxLength={6}
                  value={totpCode}
                  onChange={(code) => {
                    clearFieldError('totp')
                    setTotpCode(code)
                  }}
                  disabled={loading}
                  onComplete={handleVerifyTOTP}
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
              <FieldError className="text-center">{fieldErrors.totp}</FieldError>
            </div>
          )}

          <Button
            onClick={handleVerifyTOTP}
            className="w-full"
            disabled={
              loading ||
              (useBackupCode ? backupCode.length < 8 : totpCode.length !== 6)
            }
          >
            {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {t('verifyCode')}
          </Button>

          <div className="text-center">
            <button
              type="button"
              onClick={() => {
                setUseBackupCode(!useBackupCode)
                setTotpCode('')
                setBackupCode('')
                clearFieldError('totp')
              }}
              className="text-sm text-primary hover:underline"
            >
              {useBackupCode ? t('useTOTPCode') : t('useBackupCode')}
            </button>
          </div>
        </div>
      </div>
    )
  }

  // 邮箱验证步骤
  if (step === 'verification') {
    return (
      <div className="space-y-6">
        <button
          onClick={handleBackToLogin}
          className="flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="mr-1 h-4 w-4" />
          {t('backToLogin')}
        </button>

        <div className="flex flex-col items-center text-center space-y-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
            <Mail className="h-6 w-6 text-primary" />
          </div>
          <h3 className="font-semibold">{t('verifyYourEmail')}</h3>
          <p className="text-sm text-muted-foreground">
            {t('verificationEmailSentTo')} <span className="font-medium text-foreground">{unverifiedEmail}</span>
          </p>
          <p className="text-sm text-muted-foreground">
            {t('checkEmailForLink')}
          </p>
        </div>

        <div className="space-y-4">
          {verificationSummaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {verificationSummaryEntries.map(([field, message]) => (
                <FieldError key={field}>{formatValidationSummaryMessage(field, message, verificationSummaryFieldLabels)}</FieldError>
              ))}
            </div>
          )}

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
              <div className="space-y-2">
                <Label>{t('verificationCode')}</Label>
                <div className="flex justify-center">
                  <InputOTP
                    maxLength={6}
                    value={verificationCode}
                    onChange={(value) => {
                      clearFieldError('code')
                      setVerificationCode(value)
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
                <FieldError className="text-center">{fieldErrors.code}</FieldError>
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

  return (
    <div className="space-y-4">
      {/* 密码登录表单 */}
      {passwordLoginAllowed && (
        <form
          onSubmit={handleSubmit}
          className="space-y-4"
          onPointerEnter={(event) => recordCaptchaPointer(event, 'enter')}
          onPointerMove={(event) => recordCaptchaPointer(event, 'move')}
          onPointerDown={(event) => recordCaptchaPointer(event, 'down')}
          onPointerUp={(event) => recordCaptchaPointer(event, 'up')}
        >
          {loginSummaryEntries.length > 0 && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 space-y-1">
              {loginSummaryEntries.map(([field, message]) => (
                <FieldError key={field}>{formatValidationSummaryMessage(field, message, loginSummaryFieldLabels)}</FieldError>
              ))}
            </div>
          )}

      <div className="space-y-2">
        <Label htmlFor="username">{t('usernameOrEmail')}</Label>
        <Input
          id="username"
          type="text"
          value={username}
          onChange={(e) => {
            setUsername(e.target.value)
            clearFieldError('username')
          }}
          placeholder={t('usernameOrEmailPlaceholder')}
          required
          disabled={loading}
          aria-invalid={!!fieldErrors.username}
        />
        <FieldError>{fieldErrors.username}</FieldError>
      </div>
      
      <div className="space-y-2">
        <Label htmlFor="password">{t('password')}</Label>
        <Input
          id="password"
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
            clearFieldError('password')
          }}
          required
          placeholder={t('passwordPlaceholder')}
          disabled={loading}
          aria-invalid={!!fieldErrors.password}
        />
        <FieldError>{fieldErrors.password}</FieldError>
      </div>
      
      {/* 点击式人机验证 */}
      {shouldShowCaptcha && (
        <div className="space-y-2">
          <Label>{t('captcha')}</Label>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant={captchaToken ? 'secondary' : 'outline'}
              onClick={() => handleCaptchaClick()}
              disabled={loading || captchaLoading || !!captchaToken}
              className="flex-1 justify-center"
              aria-invalid={!!fieldErrors.captcha}
              onKeyDown={seedKeyboardCaptchaTrace}
            >
              {captchaLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {captchaToken
                ? t('captchaVerified')
                : captcha && captchaChallenge
                  ? t('captchaClickPrompt')
                  : t('captchaRetry')}
            </Button>
          </div>
          {fieldErrors.captcha && (
            <p className="text-xs text-muted-foreground">{t('captchaRetryHint')}</p>
          )}
          <FieldError>{fieldErrors.captcha}</FieldError>
        </div>
      )}
      
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t('loggingIn') : t('login')}
          </Button>
        </form>
      )}

      {passwordLoginAllowed && (
        <div className="text-center">
          <Link href="/forgot-password" className="text-sm text-primary hover:underline">
            {t('forgotPassword')}
          </Link>
        </div>
      )}

      {/* 分隔线 */}
      {ssoProviders.length > 0 && passwordLoginAllowed && (
        <div className="relative">
          <Separator />
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 bg-card px-2">
            <span className="text-xs text-muted-foreground uppercase">
              {t('orContinueWith')}
            </span>
          </div>
        </div>
      )}

      {/* SSO 提供商按钮 */}
      {ssoProviders.length > 0 && (
        <div className="space-y-3">
          {ssoProviders.map((provider) => (
            <Button
              key={provider.id}
              type="button"
              variant="outline"
              className="w-full"
              onClick={() => handleSSOLogin(provider.name)}
            >
              {provider.icon_url && (
                <img
                  src={provider.icon_url}
                  alt={provider.display_name}
                  className="mr-2 h-4 w-4"
                />
              )}
              {provider.button_text || `Sign in with ${provider.display_name}`}
            </Button>
          ))}
        </div>
      )}

      {/* 如果 SSO 启用且密码登录禁用，显示提示 */}
      {ssoEnabled && !passwordLoginAllowed && ssoProviders.length === 0 && (
        <p className="text-center text-sm text-muted-foreground">
          {t('ssoOnlyMode')}
        </p>
      )}
    </div>
  )
}

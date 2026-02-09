'use client'

import * as React from 'react'
import Link from 'next/link'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { authApi, siteSettingsApi, ssoApi, ApiError, type CaptchaResponse, type SSOProvider } from '@/lib/api'
import { Loader2, RefreshCw, Mail, ArrowLeft, ChevronDown } from 'lucide-react'
import { Separator } from '@/components/ui/separator'

type LoginStep = 'login' | 'verification'

export function LoginForm() {
  const t = useTranslations('auth')
  const locale = useLocale()
  const router = useRouter()
  const searchParams = useSearchParams()

  const [step, setStep] = React.useState<LoginStep>('login')
  const [username, setUsername] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [captchaAnswer, setCaptchaAnswer] = React.useState('')
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
      setCaptchaAnswer('')
    } catch {
      // 获取验证码失败
    } finally {
      setCaptchaLoading(false)
    }
  }, [])
  
  // 获取站点设置和 SSO 提供商
  React.useEffect(() => {
    const loadSettings = async () => {
      try {
        const settings = await siteSettingsApi.getPublic()
        setCaptchaEnabled(settings.enable_captcha)
        setSsoEnabled(settings.sso_enabled)
        setPasswordLoginAllowed(settings.sso_allow_password_login)

        if (settings.enable_captcha) {
          loadCaptcha()
        }

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
    if (fieldErrors[field]) {
      setFieldErrors(prev => {
        const next = { ...prev }
        delete next[field]
        return next
      })
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setFieldErrors({})
    
    // 验证码检查
    if (captchaEnabled && !captchaAnswer) {
      setFieldErrors({ captcha: t('captchaRequired') })
      return
    }
    
    setLoading(true)

    try {
      const token = await authApi.login({
        username,
        password,
        captcha_id: captcha?.captcha_id,
        captcha_answer: captchaAnswer || undefined,
      })
      // 保存 token
      localStorage.setItem('access_token', token.access_token)

      // 获取用户信息并同步语言设置
      try {
        const user = await authApi.getCurrentUser({ skipAuthRedirect: true })
        if (user.locale && user.locale !== locale) {
          // 用户数据库中的语言与当前页面不同，同步到浏览器
          document.cookie = `locale=${user.locale};path=/;max-age=31536000`
        }
      } catch {
        // 获取用户信息失败，不影响登录流程
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
        if (err.code === 5004 && err.data?.email) {
          const emailAddr = err.data.email as string
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
      await authApi.sendVerification(unverifiedEmail, 'register')
      setResendCooldown(60)
      toast.success(t('verificationEmailSent'))
    } catch {
      // 错误已由拦截器处理
    }
  }

  // 返回登录
  const handleBackToLogin = () => {
    setStep('login')
    setVerificationCode('')
    setFieldErrors({})
    setShowCodeInput(false)
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
                    onChange={setVerificationCode}
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
        <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="username">{t('username')}</Label>
        <Input
          id="username"
          type="text"
          value={username}
          onChange={(e) => {
            setUsername(e.target.value)
            clearFieldError('username')
          }}
          placeholder="admin"
          required
          disabled={loading}
          aria-invalid={!!fieldErrors.username}
        />
        {fieldErrors.username && (
          <p className="text-sm text-destructive">{fieldErrors.username}</p>
        )}
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
          disabled={loading}
          aria-invalid={!!fieldErrors.password}
        />
        {fieldErrors.password && (
          <p className="text-sm text-destructive">{fieldErrors.password}</p>
        )}
      </div>
      
      {/* 验证码输入 */}
      {captchaEnabled && (
        <div className="space-y-2">
          <Label htmlFor="captcha">{t('captcha')}</Label>
          <div className="flex items-center gap-2">
            <div className="flex-1 flex items-center gap-2">
              <div className="flex-shrink-0 px-3 py-2 bg-muted rounded-md font-mono text-sm min-w-[120px] text-center">
                {captchaLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin mx-auto" />
                ) : (
                  captcha?.question || '...'
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={loadCaptcha}
                disabled={captchaLoading}
                className="flex-shrink-0"
              >
                <RefreshCw className={`h-4 w-4 ${captchaLoading ? 'animate-spin' : ''}`} />
              </Button>
            </div>
            <Input
              id="captcha"
              type="text"
              value={captchaAnswer}
              onChange={(e) => {
                setCaptchaAnswer(e.target.value)
                clearFieldError('captcha')
              }}
              placeholder={t('captchaPlaceholder')}
              className="w-24"
              disabled={loading}
              aria-invalid={!!fieldErrors.captcha}
            />
          </div>
          {fieldErrors.captcha && (
            <p className="text-sm text-destructive">{fieldErrors.captcha}</p>
          )}
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

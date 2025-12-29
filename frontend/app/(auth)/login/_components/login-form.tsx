'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { toast } from 'sonner'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { authApi, siteSettingsApi, ApiError, type CaptchaResponse } from '@/lib/api'
import { Loader2, RefreshCw } from 'lucide-react'

export function LoginForm() {
  const t = useTranslations('auth')
  const router = useRouter()
  const searchParams = useSearchParams()
  
  const [username, setUsername] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [captchaAnswer, setCaptchaAnswer] = React.useState('')
  const [captcha, setCaptcha] = React.useState<CaptchaResponse | null>(null)
  const [captchaEnabled, setCaptchaEnabled] = React.useState(false)
  const [fieldErrors, setFieldErrors] = React.useState<Record<string, string>>({})
  const [loading, setLoading] = React.useState(false)
  const [captchaLoading, setCaptchaLoading] = React.useState(false)
  
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
  
  // 获取站点设置，检查是否启用验证码
  React.useEffect(() => {
    const checkCaptcha = async () => {
      try {
        const settings = await siteSettingsApi.getPublic()
        setCaptchaEnabled(settings.enable_captcha)
        if (settings.enable_captcha) {
          loadCaptcha()
        }
      } catch {
        // 获取设置失败，默认不启用验证码
      }
    }
    checkCaptcha()
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
      toast.success(t('loginSuccess'))
      // 跳转到重定向页面或 dashboard
      const redirect = searchParams.get('redirect')
      router.push(redirect || '/dashboard')
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
      }
      // 其他错误已由 axios 拦截器统一处理显示 toast
    } finally {
      setLoading(false)
    }
  }

  return (
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
  )
}

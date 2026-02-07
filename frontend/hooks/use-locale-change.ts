'use client'

import { useRouter } from 'next/navigation'
import { usersApi } from '@/lib/api'
import type { Locale } from '@/i18n/config'

/**
 * Hook for handling locale changes with backend sync
 */
export function useLocaleChange() {
  const router = useRouter()

  const changeLocale = (newLocale: Locale) => {
    // 设置 cookie
    document.cookie = `locale=${newLocale};path=/;max-age=31536000`

    // 如果用户已登录（有 token），同步到后端
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null
    if (token) {
      // 异步更新后端，不阻塞 UI，跳过认证重定向
      usersApi.updateProfile({ locale: newLocale }, { skipAuthRedirect: true }).catch((err) => {
        console.error('Failed to update locale:', err)
      })
    }

    router.refresh()
  }

  return { changeLocale }
}

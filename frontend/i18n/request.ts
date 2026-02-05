import { getRequestConfig } from 'next-intl/server'
import { cookies, headers } from 'next/headers'
import { defaultLocale, locales, type Locale } from './config'

// 动态加载所有翻译模块
async function loadMessages(locale: Locale) {
  const modules = [
    'common',
    'nav',
    'auth',
    'dashboard',
    'teams',
    'users',
    'roles',
    'permissions',
    'settings',
    'siteSettings',
    'errors',
    'models',
    'platform',
    'agents',
    'apps',
    'chat',
    'knowledgeBases',
    'tools',
    'conversations',
    'apiKeys',
    'publicChat',
    'promptGenerator',
    'workflow',
    'activities',
    'auditLogs',
    'sso',
    'notifications',
  ]

  const messages: Record<string, unknown> = {}

  for (const moduleName of modules) {
    try {
      const moduleMessages = (await import(`./${locale}/${moduleName}.json`)).default
      Object.assign(messages, moduleMessages)
    } catch (error) {
      console.warn(`Failed to load ${locale}/${moduleName}.json:`, error)
    }
  }

  return messages
}

export default getRequestConfig(async () => {
  // Try to get locale from cookie first
  const cookieStore = await cookies()
  const localeCookie = cookieStore.get('locale')?.value as Locale | undefined

  if (localeCookie && locales.includes(localeCookie)) {
    return {
      locale: localeCookie,
      messages: await loadMessages(localeCookie),
    }
  }

  // Fall back to Accept-Language header
  const headersList = await headers()
  const acceptLanguage = headersList.get('accept-language')

  if (acceptLanguage) {
    const browserLocale = acceptLanguage.split(',')[0].split('-')[0] as Locale
    if (locales.includes(browserLocale)) {
      return {
        locale: browserLocale,
        messages: await loadMessages(browserLocale),
      }
    }
  }

  // Default locale
  return {
    locale: defaultLocale,
    messages: await loadMessages(defaultLocale),
  }
})

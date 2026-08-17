import { getRequestConfig } from 'next-intl/server'
import { cookies, headers } from 'next/headers'
import { defaultLocale, locales, type Locale } from './config'

// 静态导入全部翻译模块。动态 `await import(expr)` 在 Turbopack 开发模式下会
// 缓存旧的 JSON 模块（新增键后不刷新即 MISSING_MESSAGE），静态导入随构建/HMR
// 一起更新，并让构建期校验所有 JSON 存在。
import enCommon from './en/common.json'
import enNav from './en/nav.json'
import enAuth from './en/auth.json'
import enDashboard from './en/dashboard.json'
import enTeams from './en/teams.json'
import enUsers from './en/users.json'
import enRoles from './en/roles.json'
import enPermissions from './en/permissions.json'
import enSettings from './en/settings.json'
import enSiteSettings from './en/siteSettings.json'
import enErrors from './en/errors.json'
import enModels from './en/models.json'
import enPlatform from './en/platform.json'
import enAgents from './en/agents.json'
import enApps from './en/apps.json'
import enChat from './en/chat.json'
import enKnowledgeBases from './en/knowledgeBases.json'
import enTools from './en/tools.json'
import enConversations from './en/conversations.json'
import enApiKeys from './en/apiKeys.json'
import enPublicChat from './en/publicChat.json'
import enPromptGenerator from './en/promptGenerator.json'
import enWorkflow from './en/workflow.json'
import enActivities from './en/activities.json'
import enAuditLogs from './en/auditLogs.json'
import enSso from './en/sso.json'
import enNotifications from './en/notifications.json'
import enRun from './en/run.json'
import enMemories from './en/memories.json'
import enEmbed from './en/embed.json'
import enPackages from './en/packages.json'
import enOnboarding from './en/onboarding.json'

import zhCommon from './zh/common.json'
import zhNav from './zh/nav.json'
import zhAuth from './zh/auth.json'
import zhDashboard from './zh/dashboard.json'
import zhTeams from './zh/teams.json'
import zhUsers from './zh/users.json'
import zhRoles from './zh/roles.json'
import zhPermissions from './zh/permissions.json'
import zhSettings from './zh/settings.json'
import zhSiteSettings from './zh/siteSettings.json'
import zhErrors from './zh/errors.json'
import zhModels from './zh/models.json'
import zhPlatform from './zh/platform.json'
import zhAgents from './zh/agents.json'
import zhApps from './zh/apps.json'
import zhChat from './zh/chat.json'
import zhKnowledgeBases from './zh/knowledgeBases.json'
import zhTools from './zh/tools.json'
import zhConversations from './zh/conversations.json'
import zhApiKeys from './zh/apiKeys.json'
import zhPublicChat from './zh/publicChat.json'
import zhPromptGenerator from './zh/promptGenerator.json'
import zhWorkflow from './zh/workflow.json'
import zhActivities from './zh/activities.json'
import zhAuditLogs from './zh/auditLogs.json'
import zhSso from './zh/sso.json'
import zhNotifications from './zh/notifications.json'
import zhRun from './zh/run.json'
import zhMemories from './zh/memories.json'
import zhEmbed from './zh/embed.json'
import zhPackages from './zh/packages.json'
import zhOnboarding from './zh/onboarding.json'

const MESSAGE_MODULES: Record<Locale, Record<string, unknown>[]> = {
  en: [
    enCommon, enNav, enAuth, enDashboard, enTeams, enUsers, enRoles,
    enPermissions, enSettings, enSiteSettings, enErrors, enModels,
    enPlatform, enAgents, enApps, enChat, enKnowledgeBases, enTools,
    enConversations, enApiKeys, enPublicChat, enPromptGenerator, enWorkflow,
    enActivities, enAuditLogs, enSso, enNotifications, enRun, enMemories,
    enEmbed, enPackages, enOnboarding,
  ],
  zh: [
    zhCommon, zhNav, zhAuth, zhDashboard, zhTeams, zhUsers, zhRoles,
    zhPermissions, zhSettings, zhSiteSettings, zhErrors, zhModels,
    zhPlatform, zhAgents, zhApps, zhChat, zhKnowledgeBases, zhTools,
    zhConversations, zhApiKeys, zhPublicChat, zhPromptGenerator, zhWorkflow,
    zhActivities, zhAuditLogs, zhSso, zhNotifications, zhRun, zhMemories,
    zhEmbed, zhPackages, zhOnboarding,
  ],
}

function loadMessages(locale: Locale) {
  const messages: Record<string, unknown> = {}
  for (const moduleMessages of MESSAGE_MODULES[locale]) {
    Object.assign(messages, moduleMessages)
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
      messages: loadMessages(localeCookie),
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
        messages: loadMessages(browserLocale),
      }
    }
  }

  // Default locale
  return {
    locale: defaultLocale,
    messages: loadMessages(defaultLocale),
  }
})

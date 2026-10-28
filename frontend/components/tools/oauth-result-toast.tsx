'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { usePathname } from 'next/navigation'
import { toast } from 'sonner'

const KNOWN_ERRORS = new Set([
  'oauth_provider_error',
  'oauth_exchange_failed',
  'oauth_state_invalid',
  'oauth_expired',
  'oauth_reauth_required',
  'oauth_configuration_invalid',
  'oauth_discovery_failed',
  'oauth_scope_escalation',
  'oauth_version_conflict',
  'oauth_callback_failed',
])

/**
 * Consumes the MCP OAuth callback result once and strips it from the URL while
 * preserving every unrelated query parameter (including the current page URI).
 */
export function OAuthResultToast() {
  const t = useTranslations('tools.connections')
  const pathname = usePathname()
  const handled = React.useRef(false)

  React.useEffect(() => {
    if (handled.current || typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    const status = params.get('oauth')
    if (!status) return
    handled.current = true
    const error = params.get('error') || ''
    if (status === 'success') {
      toast.success(t('oauthSuccess'))
    } else {
      toast.error(
        KNOWN_ERRORS.has(error)
          ? t(`oauthErrors.${error}`)
          : t('oauthErrors.oauth_callback_failed')
      )
    }
    params.delete('oauth')
    params.delete('error')
    params.delete('connection_id')
    const query = params.toString()
    window.history.replaceState(
      null,
      '',
      `${pathname || window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`
    )
  }, [pathname, t])

  return null
}

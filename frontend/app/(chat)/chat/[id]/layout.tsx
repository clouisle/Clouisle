import type { Metadata } from 'next'
import { getServerApiBaseUrl, getServerBackendOrigin } from '@/lib/api/server-url'

interface PublicAgentInfo {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
}

async function getAgentInfo(id: string): Promise<PublicAgentInfo | null> {
  try {
    const response = await fetch(`${getServerApiBaseUrl()}/agents/${id}/public`, {
      headers: {
        'Content-Type': 'application/json',
      },
      // Don't cache to always get fresh data
      cache: 'no-store',
    })
    
    if (!response.ok) {
      return null
    }
    
    const data = await response.json()
    return data.data
  } catch {
    return null
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>
}): Promise<Metadata> {
  const { id } = await params
  const agent = await getAgentInfo(id)
  
  if (!agent) {
    return {
      title: 'Chat',
      description: 'AI Chat',
    }
  }
  
  // The favicon <link> is requested by the browser from the frontend origin,
  // so relative paths (e.g. /api/v1/upload/files/...) must stay relative and
  // go through the Next.js API proxy (with auth cookies). openGraph images
  // need an absolute backend URL because external crawlers cannot resolve
  // relative paths.
  let iconUrl: string | undefined
  let ogImageUrl: string | undefined
  if (agent.avatar_url) {
    iconUrl = agent.avatar_url
    ogImageUrl = agent.avatar_url.startsWith('http')
      ? agent.avatar_url
      : `${getServerBackendOrigin()}${agent.avatar_url}`
  } else if (agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))) {
    iconUrl = agent.icon
    ogImageUrl = agent.icon.startsWith('http')
      ? agent.icon
      : `${getServerBackendOrigin()}${agent.icon}`
  }
  
  return {
    title: agent.name,
    description: agent.description || `Chat with ${agent.name}`,
    icons: iconUrl ? { icon: iconUrl } : undefined,
    openGraph: {
      title: agent.name,
      description: agent.description || `Chat with ${agent.name}`,
      images: ogImageUrl ? [ogImageUrl] : undefined,
    },
  }
}

export default function ChatLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return children
}

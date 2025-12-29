import type { Metadata } from 'next'

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

interface PublicAgentInfo {
  id: string
  name: string
  description?: string | null
  icon?: string | null
  avatar_url?: string | null
}

async function getAgentInfo(id: string): Promise<PublicAgentInfo | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/agents/${id}/public`, {
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
  
  // Build icon URL
  let iconUrl: string | undefined
  if (agent.avatar_url) {
    // avatar_url is already a full path like /api/v1/upload/files/...
    iconUrl = agent.avatar_url.startsWith('http') 
      ? agent.avatar_url 
      : `${API_BASE_URL.replace('/api/v1', '')}${agent.avatar_url}`
  } else if (agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))) {
    iconUrl = agent.icon.startsWith('http') 
      ? agent.icon 
      : `${API_BASE_URL.replace('/api/v1', '')}${agent.icon}`
  }
  
  return {
    title: agent.name,
    description: agent.description || `Chat with ${agent.name}`,
    icons: iconUrl ? { icon: iconUrl } : undefined,
    openGraph: {
      title: agent.name,
      description: agent.description || `Chat with ${agent.name}`,
      images: iconUrl ? [iconUrl] : undefined,
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

'use client'

import * as React from 'react'
import type { ChatMessage } from '@/components/chat/types'

export interface EmbedHistoryEntry {
  id: string
  title: string
  createdAt: number
  messages: ChatMessage[]
}

const MAX_ENTRIES = 20

/**
 * Persist embed run/conversation history in the browser's localStorage.
 * Embeds are API-key authenticated with no server-side user, so history is
 * kept locally per agent/workflow id.
 */
export function useEmbedHistory(storageKey: string) {
  const [entries, setEntries] = React.useState<EmbedHistoryEntry[]>([])
  const [loaded, setLoaded] = React.useState(false)

  React.useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (raw) setEntries(JSON.parse(raw) as EmbedHistoryEntry[])
    } catch {
      /* ignore malformed storage */
    }
    setLoaded(true)
  }, [storageKey])

  React.useEffect(() => {
    if (!loaded) return
    try {
      localStorage.setItem(storageKey, JSON.stringify(entries))
    } catch {
      /* storage full or unavailable */
    }
  }, [entries, loaded, storageKey])

  const addEntry = React.useCallback((entry: EmbedHistoryEntry) => {
    setEntries(prev => [entry, ...prev].slice(0, MAX_ENTRIES))
  }, [])

  const updateEntry = React.useCallback((id: string, patch: Partial<EmbedHistoryEntry>) => {
    setEntries(prev => prev.map(e => (e.id === id ? { ...e, ...patch } : e)))
  }, [])

  const removeEntry = React.useCallback((id: string) => {
    setEntries(prev => prev.filter(e => e.id !== id))
  }, [])

  return { entries, addEntry, updateEntry, removeEntry, loaded }
}

'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import {
  Loader2,
  LogIn,
  ArrowLeft,
  AlertCircle,
  SquarePen,
  PanelLeftClose,
  PanelLeft,
  MessageSquare,
  Trash2,
  MoreHorizontal,
  Sparkles,
  Pencil,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import {
  ApiError,
  publicAgentsApi,
  uploadApi,
  type PublicAgent,
  type ConversationListItem,
  type ChatFileUrl,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { cn } from '@/lib/utils'
import {
  ChatContainer,
  ChatInput,
  VariableForm,
  useVariableForm,
  type ChatInputFile,
  type CodePreviewPayload,
} from '@/components/chat'
import { useChat, type ChatImageContent } from '@/hooks/use-chat'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import {Alert, AlertDescription, AlertTitle} from "@/components/ui/alert";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { CodePreviewCanvas } from '@/components/chat/code-preview-canvas'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { toast } from 'sonner'

interface PublicChatPageProps {
  params: Promise<{ id: string }>
}

function showUploadValidationError(error: unknown, tCommon: ReturnType<typeof useTranslations>) {
  if (error instanceof ApiError && error.code === 1001) {
    const payload = error.data as { allowed?: string[] } | undefined
    const allowed = payload?.allowed?.join(', ')
    toast.error(
      allowed
        ? tCommon('invalidFileTypeWithAllowed', { allowed })
        : tCommon('invalidFileType')
    )
  }
}

export default function PublicChatPage({ params }: PublicChatPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('publicChat')
  const tCommon = useTranslations('common')
  
  const [agent, setAgent] = React.useState<PublicAgent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isLoggedIn, setIsLoggedIn] = React.useState<boolean | null>(null)
  
  // Sidebar state - collapsed by default on mobile
  const [sidebarOpen, setSidebarOpen] = React.useState(() => {
    if (typeof window !== 'undefined') {
      return window.innerWidth >= 768 // md breakpoint
    }
    return true
  })
  const [conversations, setConversations] = React.useState<ConversationListItem[]>([])
  const [loadingConversations, setLoadingConversations] = React.useState(false)
  const [conversationPage, setConversationPage] = React.useState(1)
  const [hasMoreConversations, setHasMoreConversations] = React.useState(true)
  const [loadingMore, setLoadingMore] = React.useState(false)
  const [loadingConversation, setLoadingConversation] = React.useState(false)
  const loadMoreRef = React.useRef<HTMLDivElement>(null)
  const suppressUrlConversationReloadRef = React.useRef(false)

  // Rename dialog state
  const [renamingConversation, setRenamingConversation] = React.useState<ConversationListItem | null>(null)
  const [renameDialogOpen, setRenameDialogOpen] = React.useState(false)
  const [conversationPendingDelete, setConversationPendingDelete] = React.useState<ConversationListItem | null>(null)
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false)
  const [newTitle, setNewTitle] = React.useState('')

  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)
  const [input, setInput] = React.useState('')
  const [activeCodePreview, setActiveCodePreview] = React.useState<CodePreviewPayload | null>(null)

  // File upload state with progress tracking
  const [files, setFiles] = React.useState<ChatInputFile[]>([])
  const [isUploading, setIsUploading] = React.useState(false)

  // Variable form state
  const [variablesOpen, setVariablesOpen] = React.useState(true)
  const variables = React.useMemo(() => agent?.variables || [], [agent])
  const {
    values: variableValues,
    setValues: setVariableValues,
    fieldErrors: variableFieldErrors,
    validate: validateVariables,
  } = useVariableForm(variables)

  React.useEffect(() => {
    params.then(setResolvedParams)
  }, [params])
  
  // Check login status first
  React.useEffect(() => {
    const token = localStorage.getItem('access_token')
    setIsLoggedIn(!!token)
  }, [])

  // Refresh conversations list
  const refreshConversations = React.useCallback(async () => {
    if (!resolvedParams) return
    try {
      const convData = await publicAgentsApi.getConversations(resolvedParams.id, { page: 1, pageSize: 5 })
      setConversations(convData.items)
      setConversationPage(1)
      setHasMoreConversations(convData.items.length >= 5 && convData.total > convData.items.length)
    } catch {
      // Ignore errors
    }
  }, [resolvedParams])

  // Use chat hook
  const {
    messages,
    isLoading: chatLoading,
    isStreaming,
    conversationId,
    sendMessage,
    regenerate,
    editMessage,
    switchVersion,
    stop,
    reset: resetChat,
    setMessages,
    setConversationId,
  } = useChat({
    agentId: agent?.id || '',
    variables: variableValues,
    onConversationChange: () => {
      // Refresh conversation list when new conversation is created
      refreshConversations()
    },
    // Don't refresh on every message end - only on conversation creation
    // This prevents unnecessary sidebar refreshes during chat
  })
  
  React.useEffect(() => {
    if (!agent?.name) return
    document.title = agent.name
  }, [agent?.name])

  // Fetch agent and conversations when logged in
  React.useEffect(() => {
    const fetchData = async () => {
      if (!resolvedParams || isLoggedIn === null) return

      if (!isLoggedIn) {
        setIsLoading(false)
        return
      }

      try {
        setIsLoading(true)
        setError(null)

        // Fetch agent info
        const agentData = await publicAgentsApi.getPublicAgent(resolvedParams.id)
        setAgent(agentData)

        // Fetch conversations (first page)
        setLoadingConversations(true)
        try {
          const convData = await publicAgentsApi.getConversations(resolvedParams.id, { page: 1, pageSize: 5 })
          setConversations(convData.items)
          setConversationPage(1)
          setHasMoreConversations(convData.items.length >= 5 && convData.total > convData.items.length)
        } catch {
          // Ignore conversation loading errors
        } finally {
          setLoadingConversations(false)
        }
      } catch (err) {
        const isNotFound = err instanceof ApiError && (err.code === 404 || (err.code >= 4000 && err.code < 5000))
        setError(isNotFound ? t('agentNotFound') : t('loadError'))
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [resolvedParams, isLoggedIn, t])

  const syncConversationUrl = React.useCallback(
    (nextConversationId: string | null, mode: 'push' | 'replace' = 'push') => {
      if (!resolvedParams) return

      const nextParams = new URLSearchParams(searchParams.toString())
      if (nextConversationId) {
        nextParams.set('conversation', nextConversationId)
      } else {
        nextParams.delete('conversation')
      }

      const query = nextParams.toString()
      const newUrl = query ? `/chat/${resolvedParams.id}?${query}` : `/chat/${resolvedParams.id}`
      const historyMethod = mode === 'replace' ? window.history.replaceState : window.history.pushState
      historyMethod.call(window.history, {}, '', newUrl)
    },
    [resolvedParams, searchParams]
  )

  // Load conversation from URL parameter
  React.useEffect(() => {
    const loadConversationFromUrl = async () => {
      if (!resolvedParams || !agent || loadingConversations) return

      const conversationParam = searchParams.get('conversation')
      if (!conversationParam) return

      if (suppressUrlConversationReloadRef.current) {
        suppressUrlConversationReloadRef.current = false
        return
      }

      // Don't reload if already loaded
      if (conversationParam === conversationId) return

      try {
        setLoadingConversation(true)
        const data = await publicAgentsApi.getConversation(conversationParam)
        const chatMessages = convertBackendMessages(data.messages as BackendMessage[])
        setMessages(chatMessages)
        setConversationId(conversationParam)
      } catch (err) {
        console.error('Failed to load conversation from URL:', err)
        // If conversation not found, clear the URL parameter
        syncConversationUrl(null, 'replace')
      } finally {
        setLoadingConversation(false)
      }
    }

    loadConversationFromUrl()
  }, [resolvedParams, agent, loadingConversations, searchParams, conversationId, setConversationId, setMessages, syncConversationUrl])

  // Load more conversations
  const loadMoreConversations = React.useCallback(async () => {
    if (!resolvedParams || loadingMore || !hasMoreConversations) return
    
    setLoadingMore(true)
    try {
      const nextPage = conversationPage + 1
      const convData = await publicAgentsApi.getConversations(resolvedParams.id, { page: nextPage, pageSize: 5 })
      setConversations(prev => [...prev, ...convData.items])
      setConversationPage(nextPage)
      setHasMoreConversations(convData.items.length >= 5 && (conversations.length + convData.items.length) < convData.total)
    } catch {
      // Ignore errors
    } finally {
      setLoadingMore(false)
    }
  }, [resolvedParams, conversationPage, loadingMore, hasMoreConversations, conversations.length])

  // Use IntersectionObserver to detect when sentinel element is visible
  React.useEffect(() => {
    const sentinel = loadMoreRef.current
    if (!sentinel || !hasMoreConversations || loadingConversations) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && !loadingMore) {
          loadMoreConversations()
        }
      },
      { threshold: 0.1 }
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [hasMoreConversations, loadingMore, loadingConversations, loadMoreConversations])

  const handleNewChat = () => {
    suppressUrlConversationReloadRef.current = true
    resetChat()
    setInput('')
    setFiles([])
    setIsUploading(false)
    setLoadingConversation(false)

    syncConversationUrl(null)
  }

  const handleSelectConversation = async (conv: ConversationListItem) => {
    if (conv.id === conversationId || loadingConversation) return

    try {
      setLoadingConversation(true)
      const data = await publicAgentsApi.getConversation(conv.id)

      // Convert messages to ChatMessage format using unified converter
      // This handles text, images, files, reasoning, tool calls, and RAG context
      const chatMessages = convertBackendMessages(data.messages as BackendMessage[])

      setMessages(chatMessages)
      setConversationId(conv.id)

      suppressUrlConversationReloadRef.current = true
      syncConversationUrl(conv.id)
    } catch (err) {
      console.error('Failed to load conversation:', err)
    } finally {
      setLoadingConversation(false)
    }
  }

  const handleDeleteClick = (conv: ConversationListItem, e: React.MouseEvent) => {
    e.stopPropagation()
    setConversationPendingDelete(conv)
    setDeleteDialogOpen(true)
  }

  const handleDeleteConversation = async () => {
    if (!conversationPendingDelete) return

    try {
      await publicAgentsApi.deleteConversation(conversationPendingDelete.id)
      setConversations(prev => prev.filter(c => c.id !== conversationPendingDelete.id))

      // If deleting current conversation, start new chat and clear URL
      if (conversationPendingDelete.id === conversationId) {
        handleNewChat()
      }

      setDeleteDialogOpen(false)
      setConversationPendingDelete(null)
    } catch (err) {
      console.error('Failed to delete conversation:', err)
      toast.error(t('deleteConversationFailed'))
    }
  }

  const handleRenameClick = (conv: ConversationListItem, e: React.MouseEvent) => {
    e.stopPropagation()
    setRenamingConversation(conv)
    setNewTitle(conv.title || '')
    setRenameDialogOpen(true)
  }

  const handleRenameSubmit = async () => {
    if (!renamingConversation || !newTitle.trim()) return

    try {
      await publicAgentsApi.updateConversation(renamingConversation.id, { title: newTitle.trim() })

      // Update local state
      setConversations(prev =>
        prev.map(c => c.id === renamingConversation.id ? { ...c, title: newTitle.trim() } : c)
      )

      setRenameDialogOpen(false)
      setRenamingConversation(null)
      setNewTitle('')
    } catch (err) {
      console.error('Failed to rename conversation:', err)
    }
  }

  // Helper function to convert File to base64 data URL
  const fileToDataUrl = async (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = reject
      reader.readAsDataURL(file)
    })
  }
  
  const handleSubmit = async (message: string, submittedFiles?: ChatInputFile[]) => {
    if (!message.trim() || chatLoading) return

    if (!validateVariables()) {
      setVariablesOpen(true)
      return
    }

    const filesToProcess = submittedFiles || files
    
    // Process images and files
    let images: ChatImageContent[] | undefined
    let fileUrls: ChatFileUrl[] | undefined
    
    if (agent && filesToProcess && filesToProcess.length > 0) {
      // Process image files for vision
      if (agent.enable_vision) {
        const imageFiles = filesToProcess.filter(f => f.type.startsWith('image/') && !f.isDocument)
        if (imageFiles.length > 0) {
          images = await Promise.all(
            imageFiles.map(async (f) => ({
              type: 'image_url' as const,
              url: await fileToDataUrl(f.file),
            }))
          )
        }
      }
      
      // Process document files for file upload - upload to get URLs with progress
      if (agent.enable_file_upload) {
        const documentFiles = filesToProcess.filter(f => f.isDocument)
        if (documentFiles.length > 0) {
          try {
            setIsUploading(true)
            
            // Upload documents with progress tracking
            const uploadPromises = documentFiles.map(async (f) => {
              // Update file progress
              const updateProgress = (progress: { percent: number }) => {
                setFiles(prev => prev.map(file => 
                  file.id === f.id 
                    ? { ...file, isUploading: true, uploadProgress: progress.percent }
                    : file
                ))
              }
              
              // Mark as uploading
              setFiles(prev => prev.map(file => 
                file.id === f.id 
                  ? { ...file, isUploading: true, uploadProgress: 0 }
                  : file
              ))
              
              const result = await uploadApi.uploadFileWithProgress(
                f.file, 
                'documents',
                updateProgress
              )
              
              // Mark as complete
              setFiles(prev => prev.map(file => 
                file.id === f.id 
                  ? { ...file, isUploading: false, uploadProgress: 100 }
                  : file
              ))
              
              return {
                filename: f.name,
                url: result.url,
                size: f.size,
                mime_type: f.type,
              }
            })
            fileUrls = await Promise.all(uploadPromises)
          } catch (err) {
            console.error('Failed to upload files:', err)
            showUploadValidationError(err, tCommon)
            // Reset upload state on error
            setFiles(prev => prev.map(file => ({
              ...file,
              isUploading: false,
              uploadProgress: undefined
            })))
          } finally {
            setIsUploading(false)
          }
        }
      }
    }
    
    setInput('')
    setFiles([])
    await sendMessage(message, images, fileUrls)
  }
  
  if (isLoading || isLoggedIn === null) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }
  
  // Not logged in - show login prompt
  if (!isLoggedIn) {
    return (
      <div className="h-screen flex flex-col items-center justify-center p-4 bg-background">
        <div className="text-center max-w-md">
          <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center mx-auto mb-6">
            <LogIn className="h-10 w-10 text-muted-foreground" />
          </div>
          <h1 className="text-2xl font-medium text-foreground mb-3">{t('loginRequired')}</h1>
          <p className="text-muted-foreground mb-8">{t('loginHint')}</p>
          <Link href={resolvedParams ? `/login?redirect=/chat/${resolvedParams.id}` : '/login'}>
            <Button className="rounded-full px-8 py-2">
              {t('login')}
            </Button>
          </Link>
        </div>
      </div>
    )
  }
  
  if (error || !agent) {
    return (
      <div className="h-screen flex flex-col items-center justify-center p-4 bg-background">
        <Alert variant="destructive" className="max-w-md">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{t('error')}</AlertTitle>
          <AlertDescription>{error || t('agentNotFound')}</AlertDescription>
        </Alert>
        <Button
          variant="ghost"
          className="mt-4"
          onClick={() => router.push('/')}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          {t('backToHome')}
        </Button>
      </div>
    )
  }

  const displayIcon = agent.icon || agent.avatar_url
  const isIconUrl = Boolean(displayIcon && (displayIcon.startsWith('http') || displayIcon.startsWith('/')))
  const hasMessages = messages.length > 0
  
  return (
    <div className="h-full flex overflow-hidden bg-background">
      {/* Sidebar */}
      <div 
        className={cn(
          "flex flex-col bg-muted/50 transition-all duration-300 ease-in-out border-r shrink-0 overflow-hidden",
          sidebarOpen ? "w-64" : "w-0"
        )}
      >
        {sidebarOpen && (
          <>
            {/* Sidebar Header */}
            <div className="flex items-center justify-between p-3 h-14 border-b">
              {/* Agent Info */}
              <button
                type="button"
                className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md text-left transition-colors hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={handleNewChat}
                title={t('newChat')}
              >
                {displayIcon ? (
                  isIconUrl ? (
                    <div className="relative h-6 w-6 overflow-hidden">
                      <Image
                        src={displayIcon}
                        alt={agent.name}
                        fill
                        unoptimized
                        className="object-cover"
                      />
                    </div>
                  ) : (
                    <span className="flex h-6 w-6 items-center justify-center leading-none text-lg">{displayIcon}</span>
                  )
                ) : (
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <Sparkles className="h-3.5 w-3.5" />
                  </div>
                )}
                <span className="truncate text-sm font-medium text-foreground max-w-[120px]">{agent.name}</span>
              </button>
              
              {/* New Chat Button */}
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleNewChat}
                title={t('newChat')}
              >
                <SquarePen className="h-5 w-5" />
              </Button>
            </div>

            {/* Conversation List */}
            <div className="flex-1 min-h-0 overflow-y-auto py-2">
              {loadingConversations ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                </div>
              ) : conversations.length === 0 ? (
                <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                  {t('noConversations')}
                </div>
              ) : (
                <div className="space-y-1 px-2">
                  {conversations.map((conv) => (
                    <div
                      key={conv.id}
                      onClick={() => handleSelectConversation(conv)}
                      className={cn(
                        "group flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer transition-colors",
                        conv.id === conversationId 
                          ? "bg-accent" 
                          : "hover:bg-accent/50"
                      )}
                    >
                      <MessageSquare className="h-4 w-4 text-muted-foreground shrink-0" />
                      <p className="flex-1 text-sm text-foreground truncate">
                        {conv.title || t('untitledChat')}
                      </p>
                      <DropdownMenu>
                        <DropdownMenuTrigger onClick={(e) => e.stopPropagation()}>
                          <span
                            className="h-7 w-7 opacity-0 group-hover:opacity-100 flex items-center justify-center rounded-md hover:bg-accent transition-colors"
                          >
                            <MoreHorizontal className="h-4 w-4" />
                          </span>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={(e) => handleRenameClick(conv, e as unknown as React.MouseEvent)}
                          >
                            <Pencil className="h-4 w-4 mr-2" />
                            {t('rename')}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            variant="destructive"
                            onClick={(e) => handleDeleteClick(conv, e as unknown as React.MouseEvent)}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            {t('delete')}
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  ))}
                  {/* Sentinel element for infinite scroll */}
                  {hasMoreConversations && (
                    <div ref={loadMoreRef} className="flex justify-center py-2">
                      {loadingMore && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 min-w-0 min-h-0">
        <ResizablePanelGroup orientation="horizontal" className="h-full">
          <ResizablePanel defaultSize={activeCodePreview ? '62%' : '100%'} minSize="40%">
            <div className="flex h-full min-w-0 flex-col">
        {/* Header */}
        <header className="flex items-center justify-between px-3 h-14 shrink-0 border-b">
          <div className="flex items-center gap-2">
            {/* Sidebar toggle */}
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              {sidebarOpen ? <PanelLeftClose className="h-5 w-5" /> : <PanelLeft className="h-5 w-5" />}
            </Button>
          </div>
          
          <div className="flex items-center gap-2">
            {hasMessages && !sidebarOpen && (
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleNewChat}
                title={t('newChat')}
              >
                <SquarePen className="h-5 w-5" />
              </Button>
            )}
          </div>
        </header>

        {/* Chat Area */}
        <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
          {/* Loading Skeleton */}
          {loadingConversation ? (
            <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
              {/* Skeleton for user message */}
              <div className="flex justify-end">
                <div className="max-w-[80%] space-y-2">
                  <div className="h-4 w-32 bg-muted rounded animate-pulse" />
                  <div className="bg-muted rounded-2xl p-4 space-y-2">
                    <div className="h-4 w-full bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-3/4 bg-muted-foreground/20 rounded animate-pulse" />
                  </div>
                </div>
              </div>

              {/* Skeleton for assistant message */}
              <div className="flex justify-start">
                <div className="max-w-[80%] space-y-2">
                  <div className="h-4 w-32 bg-muted rounded animate-pulse" />
                  <div className="bg-muted rounded-2xl p-4 space-y-2">
                    <div className="h-4 w-full bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-5/6 bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-4/5 bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-2/3 bg-muted-foreground/20 rounded animate-pulse" />
                  </div>
                </div>
              </div>

              {/* Skeleton for user message */}
              <div className="flex justify-end">
                <div className="max-w-[80%] space-y-2">
                  <div className="h-4 w-32 bg-muted rounded animate-pulse" />
                  <div className="bg-muted rounded-2xl p-4 space-y-2">
                    <div className="h-4 w-full bg-muted-foreground/20 rounded animate-pulse" />
                  </div>
                </div>
              </div>

              {/* Skeleton for assistant message */}
              <div className="flex justify-start">
                <div className="max-w-[80%] space-y-2">
                  <div className="h-4 w-32 bg-muted rounded animate-pulse" />
                  <div className="bg-muted rounded-2xl p-4 space-y-2">
                    <div className="h-4 w-full bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-11/12 bg-muted-foreground/20 rounded animate-pulse" />
                    <div className="h-4 w-3/4 bg-muted-foreground/20 rounded animate-pulse" />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* Messages using ChatContainer */
            <ChatContainer
              key={conversationId ?? 'new-chat'}
              messages={messages}
              isStreaming={isStreaming}
              hideToolCalls={agent.hide_tool_calls}
              className="flex-1 min-h-0 overflow-y-auto"
              onRegenerate={regenerate}
              onEditMessage={editMessage}
              onSwitchVersion={switchVersion}
              onSelectOption={(option) => {
                void handleSubmit(option, [])
              }}
              onOpenCodePreview={setActiveCodePreview}
              emptyState={
              <div className="flex-1 flex flex-col items-center justify-center px-4">
                {/* Agent Icon */}
                <div className="mb-8">
                  {displayIcon ? (
                    isIconUrl ? (
                      <div className="relative h-20 w-20 overflow-hidden">
                        <Image
                          src={displayIcon}
                          alt={agent.name}
                          fill
                          unoptimized
                          className="object-cover"
                        />
                      </div>
                    ) : (
                      <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center ring-2 ring-border">
                        <span className="flex h-full w-full items-center justify-center leading-none text-4xl">{displayIcon}</span>
                      </div>
                    )
                  ) : (
                    <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center">
                      <Sparkles className="h-6 w-6 text-primary" />
                    </div>
                  )}
                </div>

                {/* Welcome Message */}
                <h1 className="text-2xl md:text-3xl font-medium text-foreground text-center mb-4">
                  {agent.opening_message || t('welcomeMessage')}
                </h1>
                
                {agent.description && !agent.opening_message && (
                  <p className="text-muted-foreground text-center max-w-lg text-base">
                    {agent.description}
                  </p>
                )}

                {/* Suggested Questions */}
                {agent.suggested_questions && agent.suggested_questions.length > 0 && (
                  <div className="flex flex-wrap justify-center gap-2 max-w-2xl mt-8">
                    {agent.suggested_questions.slice(0, 4).map((q, i) => (
                      <button
                        key={i}
                        onClick={() => handleSubmit(q)}
                        className="px-4 py-2 text-sm text-foreground/80 border border-border rounded-full hover:bg-accent hover:border-border transition-colors cursor-pointer"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            }
          />
          )}

          {/* Input Area */}
          <div className="relative pb-4 shrink-0">
            {/* Variable Panel - Collapsible above input */}
            {variables.length > 0 && variables.some(v => !v.hidden) && (
              <div className="mx-auto max-w-3xl px-4">
                <Collapsible open={variablesOpen} onOpenChange={setVariablesOpen}>
                  <div className="rounded-t-lg border border-b-0 bg-muted/30 overflow-hidden w-[70%] mx-auto">
                    <CollapsibleTrigger className="flex items-center justify-between w-full px-2.5 py-1.5 text-xs hover:bg-muted/50 transition-colors">
                      <span className="text-xs font-medium flex items-center gap-1.5">
                        {t('configureAgent')}
                        {(() => {
                          const requiredCount = variables.filter(v => !v.hidden && v.required).length
                          const filledRequiredCount = variables.filter((v) => {
                            if (v.hidden || !v.required) return false
                            const value = variableValues[v.name]
                            if (v.type === 'checkbox') return true
                            if (v.type === 'array') {
                              return Array.isArray(value) && value.length > 0
                            }
                            return value !== undefined && value !== null && value !== ''
                          }).length

                          if (requiredCount > 0) {
                            return (
                              <span className={cn(
                                "text-[10px] px-1 py-0.5 rounded",
                                filledRequiredCount === requiredCount
                                  ? "bg-green-100 text-green-700"
                                  : "bg-orange-100 text-orange-700"
                              )}>
                                {filledRequiredCount}/{requiredCount}
                              </span>
                            )
                          }
                          return null
                        })()}
                      </span>
                      {variablesOpen ? (
                        <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <div className="px-2.5 pb-2.5 pt-0.5">
                        <VariableForm
                          variables={variables}
                          values={variableValues}
                          onChange={setVariableValues}
                          fieldErrors={variableFieldErrors}
                          className="space-y-2"
                        />
                      </div>
                    </CollapsibleContent>
                  </div>
                </Collapsible>
              </div>
            )}

            <ChatInput
              value={input}
              onChange={setInput}
              onSubmit={handleSubmit}
              onStop={stop}
              placeholder={t('typePlaceholder')}
              disabled={chatLoading && !isStreaming}
              isLoading={chatLoading}
              isStreaming={isStreaming}
              allowAttachments={agent.enable_vision}
              enableFileUpload={agent.enable_file_upload}
              fileUploadConfig={agent.file_upload_config}
              files={files}
              onFilesChange={setFiles}
              isUploading={isUploading}
            />
            
            {/* Footer */}
            <p className="text-[11px] text-center text-muted-foreground mt-2">
              {t('poweredBy', { name: agent.created_by?.username || 'Clouisle' })}
            </p>
          </div>
        </div>
            </div>
          </ResizablePanel>
          {activeCodePreview && (
            <>
              <ResizableHandle withHandle />
              <ResizablePanel defaultSize="38%" minSize="25%" maxSize="60%">
                <CodePreviewCanvas
                  preview={activeCodePreview}
                  onClose={() => setActiveCodePreview(null)}
                />
              </ResizablePanel>
            </>
          )}
        </ResizablePanelGroup>
      </div>

      {/* Delete Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onOpenChange={(open) => {
          setDeleteDialogOpen(open)
          if (!open) {
            setConversationPendingDelete(null)
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('deleteConversation')}</DialogTitle>
            <DialogDescription>
              {t('deleteConversationDescription', {
                title: conversationPendingDelete?.title || t('untitledChat'),
              })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteDialogOpen(false)}>
              {t('cancel')}
            </Button>
            <Button variant="destructive" onClick={handleDeleteConversation}>
              {t('confirmDeleteConversation')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={renameDialogOpen} onOpenChange={setRenameDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t('renameConversation')}</DialogTitle>
            <DialogDescription>
              {t('renameConversationDescription')}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="title">{t('conversationTitle')}</Label>
              <Input
                id="title"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder={t('conversationTitlePlaceholder')}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    handleRenameSubmit()
                  }
                }}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameDialogOpen(false)}>
              {t('cancel')}
            </Button>
            <Button onClick={handleRenameSubmit} disabled={!newTitle.trim()}>
              {t('save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

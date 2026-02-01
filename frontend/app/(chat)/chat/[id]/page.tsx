'use client'

import * as React from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import Link from 'next/link'
import Image from 'next/image'
import { useTranslations } from 'next-intl'
import {
  Loader2,
  Bot,
  LogIn,
  ArrowLeft,
  AlertCircle,
  Plus,
  RotateCcw,
  PanelLeftClose,
  PanelLeft,
  MessageSquare,
  Trash2,
  MoreHorizontal,
  Sparkles,
  Pencil,
} from 'lucide-react'
import { 
  publicAgentsApi,
  uploadApi,
  type PublicAgent,
  type ConversationListItem,
  type Message,
  type ChatFileUrl,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
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
  type ChatMessage,
  type ChatInputFile,
} from '@/components/chat'
import { useChat, type ChatImageContent } from '@/hooks/use-chat'
import { convertBackendMessages, type BackendMessage } from '@/lib/utils/message-converter'
import {Alert, AlertDescription, AlertTitle} from "@/components/ui/alert";

interface PublicChatPageProps {
  params: Promise<{ id: string }>
}

export default function PublicChatPage({ params }: PublicChatPageProps) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const t = useTranslations('publicChat')
  
  const [agent, setAgent] = React.useState<PublicAgent | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)
  const [isLoggedIn, setIsLoggedIn] = React.useState<boolean | null>(null)
  
  // Sidebar state
  const [sidebarOpen, setSidebarOpen] = React.useState(true)
  const [conversations, setConversations] = React.useState<ConversationListItem[]>([])
  const [loadingConversations, setLoadingConversations] = React.useState(false)
  const [conversationPage, setConversationPage] = React.useState(1)
  const [hasMoreConversations, setHasMoreConversations] = React.useState(true)
  const [loadingMore, setLoadingMore] = React.useState(false)
  const [loadingConversation, setLoadingConversation] = React.useState(false)
  const loadMoreRef = React.useRef<HTMLDivElement>(null)

  // Rename dialog state
  const [renamingConversation, setRenamingConversation] = React.useState<ConversationListItem | null>(null)
  const [renameDialogOpen, setRenameDialogOpen] = React.useState(false)
  const [newTitle, setNewTitle] = React.useState('')

  const [resolvedParams, setResolvedParams] = React.useState<{ id: string } | null>(null)
  const [input, setInput] = React.useState('')
  
  // File upload state with progress tracking
  const [files, setFiles] = React.useState<ChatInputFile[]>([])
  const [isUploading, setIsUploading] = React.useState(false)
  
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
    switchVersion,
    stop,
    reset: resetChat,
    setMessages,
    setConversationId,
  } = useChat({
    agentId: agent?.id || '',
    onConversationChange: (newConversationId) => {
      // Refresh conversation list when new conversation is created
      console.log('New conversation created:', newConversationId)
      refreshConversations()
    },
  })
  
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
        setError((err as Error).message || t('loadError'))
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [resolvedParams, isLoggedIn, t])

  // Load conversation from URL parameter
  React.useEffect(() => {
    const loadConversationFromUrl = async () => {
      if (!resolvedParams || !agent || loadingConversations) return

      const conversationParam = searchParams.get('conversation')
      if (!conversationParam) return

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
        if (resolvedParams) {
          const newUrl = `/chat/${resolvedParams.id}`
          window.history.replaceState({}, '', newUrl)
        }
      } finally {
        setLoadingConversation(false)
      }
    }

    loadConversationFromUrl()
  }, [resolvedParams, agent, loadingConversations, searchParams])

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
    resetChat()
    setInput('')
    setFiles([])
    setIsUploading(false)

    // Clear conversation URL parameter
    if (resolvedParams) {
      const newUrl = `/chat/${resolvedParams.id}`
      window.history.pushState({}, '', newUrl)
    }
  }

  const handleSelectConversation = async (conv: ConversationListItem) => {
    if (conv.id === conversationId || loadingConversation) return

    try {
      setLoadingConversation(true)
      const data = await publicAgentsApi.getConversation(conv.id)

      console.log('[handleSelectConversation] Loaded conversation:', data)
      console.log('[handleSelectConversation] Messages count:', data.messages?.length)

      // Convert messages to ChatMessage format using unified converter
      // This handles text, images, files, reasoning, tool calls, and RAG context
      const chatMessages = convertBackendMessages(data.messages as BackendMessage[])

      console.log('[handleSelectConversation] Converted messages count:', chatMessages.length)
      console.log('[handleSelectConversation] Converted messages:', chatMessages)

      setMessages(chatMessages)
      setConversationId(conv.id)

      // Update URL with conversation ID without page refresh
      if (resolvedParams) {
        const newUrl = `/chat/${resolvedParams.id}?conversation=${conv.id}`
        window.history.pushState({}, '', newUrl)
      }
    } catch (err) {
      console.error('Failed to load conversation:', err)
    } finally {
      setLoadingConversation(false)
    }
  }

  const handleDeleteConversation = async (convId: string, e: React.MouseEvent) => {
    e.stopPropagation()

    try {
      await publicAgentsApi.deleteConversation(convId)
      setConversations(prev => prev.filter(c => c.id !== convId))

      // If deleting current conversation, start new chat and clear URL
      if (convId === conversationId) {
        handleNewChat()
      }
    } catch (err) {
      console.error('Failed to delete conversation:', err)
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

  const isIconUrl = agent.icon && (agent.icon.startsWith('http') || agent.icon.startsWith('/'))
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
              <div className="flex items-center gap-2">
                {agent.icon ? (
                  isIconUrl ? (
                    <div className="relative h-6 w-6 rounded overflow-hidden">
                      <Image
                        src={agent.icon}
                        alt={agent.name}
                        fill
                        unoptimized
                        className="object-cover"
                      />
                    </div>
                  ) : (
                    <span className="text-lg">{agent.icon}</span>
                  )
                ) : (
                  <Bot className="h-5 w-5 text-muted-foreground" />
                )}
                <span className="font-medium text-foreground text-sm truncate max-w-[120px]">{agent.name}</span>
              </div>
              
              {/* New Chat Button */}
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleNewChat}
                title={t('newChat')}
              >
                <Plus className="h-5 w-5" />
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
                            onClick={(e) => handleDeleteConversation(conv.id, e as unknown as React.MouseEvent)}
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
      <div className="flex-1 flex flex-col min-w-0 min-h-0">
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
            {hasMessages && (
              <Button
                variant="ghost"
                size="icon"
                className="h-9 w-9"
                onClick={handleNewChat}
                title={t('newChat')}
              >
                <RotateCcw className="h-5 w-5" />
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
              messages={messages}
              isStreaming={isStreaming}
              className="flex-1 min-h-0 overflow-y-auto"
              onRegenerate={regenerate}
              onSwitchVersion={switchVersion}
              emptyState={
              <div className="flex-1 flex flex-col items-center justify-center px-4">
                {/* Agent Icon */}
                <div className="mb-8">
                  {agent.icon ? (
                    isIconUrl ? (
                      <div className="relative h-20 w-20 rounded-full overflow-hidden ring-2 ring-border">
                        <Image
                          src={agent.icon}
                          alt={agent.name}
                          fill
                          unoptimized
                          className="object-cover"
                        />
                      </div>
                    ) : (
                      <div className="h-20 w-20 rounded-full bg-muted flex items-center justify-center ring-2 ring-border">
                        <span className="text-4xl">{agent.icon}</span>
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

      {/* Rename Dialog */}
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

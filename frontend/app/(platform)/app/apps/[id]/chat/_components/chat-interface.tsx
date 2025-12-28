'use client'

import * as React from 'react'
import { useTranslations } from 'next-intl'
import { Send, Loader2, User, Bot, FileText } from 'lucide-react'
import { 
  agentsApi, 
  parseSSEStream,
  type Agent, 
  type SSEMessageStart,
  type SSEContentDelta,
  type SSERagContext,
  type SSEError,
} from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

interface ChatInterfaceProps {
  agent: Agent
}

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  isStreaming?: boolean
  ragContext?: SSERagContext['contexts']
}

export function ChatInterface({ agent }: ChatInterfaceProps) {
  const t = useTranslations('agents')
  
  const [messages, setMessages] = React.useState<ChatMessage[]>([])
  const [input, setInput] = React.useState('')
  const [isLoading, setIsLoading] = React.useState(false)
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  
  const scrollAreaRef = React.useRef<HTMLDivElement>(null)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  const abortRef = React.useRef<(() => void) | null>(null)
  
  // Auto scroll to bottom
  const scrollToBottom = React.useCallback(() => {
    if (scrollAreaRef.current) {
      const scrollElement = scrollAreaRef.current.querySelector('[data-radix-scroll-area-viewport]')
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight
      }
    }
  }, [])
  
  React.useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])
  
  // Show opening message
  React.useEffect(() => {
    if (agent.opening_message && messages.length === 0) {
      setMessages([{
        id: 'opening',
        role: 'assistant',
        content: agent.opening_message,
      }])
    }
  }, [agent.opening_message, messages.length])
  
  const handleSend = async () => {
    if (!input.trim() || isLoading) return
    
    const userMessage = input.trim()
    setInput('')
    
    // Add user message
    const userMsgId = `user-${Date.now()}`
    setMessages(prev => [...prev, {
      id: userMsgId,
      role: 'user',
      content: userMessage,
    }])
    
    // Add placeholder for assistant message
    const assistantMsgId = `assistant-${Date.now()}`
    setMessages(prev => [...prev, {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    }])
    
    setIsLoading(true)
    
    try {
      const { stream, abort } = agentsApi.chatStream(agent.id, {
        message: userMessage,
        conversation_id: conversationId,
      })
      abortRef.current = abort
      
      const response = await stream
      
      if (!response.ok) {
        throw new Error(`HTTP error: ${response.status}`)
      }
      
      let fullContent = ''
      let ragContext: SSERagContext['contexts'] | undefined
      
      for await (const event of parseSSEStream(response)) {
        switch (event.event) {
          case 'message_start': {
            const data = event.data as SSEMessageStart
            setConversationId(data.conversation_id)
            break
          }
          case 'content_delta': {
            const data = event.data as SSEContentDelta
            fullContent += data.delta
            setMessages(prev => prev.map(msg => 
              msg.id === assistantMsgId 
                ? { ...msg, content: fullContent }
                : msg
            ))
            break
          }
          case 'rag_context': {
            const data = event.data as SSERagContext
            ragContext = data.contexts
            break
          }
          case 'message_end': {
            // const data = event.data as SSEMessageEnd
            setMessages(prev => prev.map(msg => 
              msg.id === assistantMsgId 
                ? { ...msg, isStreaming: false, ragContext }
                : msg
            ))
            break
          }
          case 'error': {
            const data = event.data as SSEError
            setMessages(prev => prev.map(msg => 
              msg.id === assistantMsgId 
                ? { ...msg, content: `Error: ${data.msg}`, isStreaming: false }
                : msg
            ))
            break
          }
        }
      }
    } catch (error) {
      if ((error as Error).name === 'AbortError') {
        // User cancelled
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMsgId 
            ? { ...msg, content: msg.content || '(cancelled)', isStreaming: false }
            : msg
        ))
      } else {
        console.error('Chat error:', error)
        setMessages(prev => prev.map(msg => 
          msg.id === assistantMsgId 
            ? { ...msg, content: 'An error occurred. Please try again.', isStreaming: false }
            : msg
        ))
      }
    } finally {
      setIsLoading(false)
      abortRef.current = null
    }
  }
  
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }
  
  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Messages */}
      <div ref={scrollAreaRef} className="flex-1 overflow-auto">
        <div className="max-w-3xl mx-auto py-6 px-4 space-y-6">
          {messages.length === 0 && !agent.opening_message && (
            <div className="text-center py-12 text-muted-foreground">
              <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>{t('chatWithAgent')}</p>
              {agent.suggested_questions.length > 0 && (
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {agent.suggested_questions.map((q, i) => (
                    <Button
                      key={i}
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setInput(q)
                        textareaRef.current?.focus()
                      }}
                    >
                      {q}
                    </Button>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {messages.map((message) => (
            <div key={message.id} className={cn(
              'flex gap-3',
              message.role === 'user' ? 'justify-end' : 'justify-start'
            )}>
              {message.role === 'assistant' && (
                <div className="rounded-lg bg-primary/10 p-2 h-fit">
                  {agent.icon ? (
                    <span>{agent.icon}</span>
                  ) : (
                    <Bot className="h-4 w-4 text-primary" />
                  )}
                </div>
              )}
              
              <div className={cn(
                'max-w-[80%] rounded-lg px-4 py-2',
                message.role === 'user' 
                  ? 'bg-primary text-primary-foreground' 
                  : 'bg-muted'
              )}>
                <div className="whitespace-pre-wrap">
                  {message.content}
                  {message.isStreaming && (
                    <span className="inline-block w-2 h-4 bg-current animate-pulse ml-1" />
                  )}
                </div>
                
                {/* RAG Context */}
                {message.ragContext && message.ragContext.length > 0 && (
                  <div className="mt-3 pt-3 border-t border-border/50">
                    <div className="flex items-center gap-1 text-xs text-muted-foreground mb-2">
                      <FileText className="h-3 w-3" />
                      <span>{t('ragContext')}</span>
                    </div>
                    <div className="space-y-1">
                      {message.ragContext.slice(0, 3).map((ctx, i) => (
                        <div key={i} className="text-xs text-muted-foreground bg-background/50 rounded px-2 py-1">
                          <span className="font-medium">{ctx.kb_name}</span>
                          <span className="mx-1">·</span>
                          <span>{ctx.document_name}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              
              {message.role === 'user' && (
                <div className="rounded-lg bg-primary/10 p-2 h-fit">
                  <User className="h-4 w-4 text-primary" />
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      
      {/* Input */}
      <div className="border-t bg-background p-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('typePlaceholder')}
            disabled={isLoading}
            rows={1}
            className="min-h-[44px] max-h-32 resize-none"
          />
          <Button 
            onClick={handleSend} 
            disabled={!input.trim() || isLoading}
            size="icon"
            className="h-11 w-11 shrink-0"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </div>
    </div>
  )
}

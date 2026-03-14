/**
 * Chat message types for the universal Chat component
 * Supports: text, reasoning, tool calls, MCP calls, sources, files
 */

export type MessageRole = 'user' | 'assistant' | 'system'

export type MessagePartState = 'streaming' | 'done'

/**
 * Text content part
 */
export interface TextPart {
  type: 'text'
  text: string
  state?: MessagePartState
}

/**
 * Reasoning/Chain of Thought part
 */
export interface ReasoningPart {
  type: 'reasoning'
  text: string
  state?: MessagePartState
  /** Duration in milliseconds */
  duration?: number
  /** Optional metadata for additional context */
  metadata?: Record<string, unknown>
}

/**
 * Tool call part - for function/tool invocations
 */
export interface ToolCallPart {
  type: 'tool-call'
  toolCallId: string
  toolName: string
  /** Display name for the tool (user-friendly) */
  toolDisplayName?: string
  input: Record<string, unknown>
  state?: 'pending' | 'running' | 'done' | 'error'
}

/**
 * Tool result part - result from tool execution
 */
export interface ToolResultPart {
  type: 'tool-result'
  toolCallId: string
  toolName: string
  /** Display name for the tool (user-friendly) */
  toolDisplayName?: string
  output: unknown
  isError?: boolean
}

/**
 * MCP (Model Context Protocol) tool call
 */
export interface McpToolCallPart {
  type: 'mcp-tool-call'
  toolCallId: string
  serverName: string
  toolName: string
  input: Record<string, unknown>
  state?: 'pending' | 'running' | 'done' | 'error'
}

/**
 * MCP tool result
 */
export interface McpToolResultPart {
  type: 'mcp-tool-result'
  toolCallId: string
  serverName: string
  toolName: string
  output: unknown
  isError?: boolean
}

/**
 * Source URL citation
 */
export interface SourceUrlPart {
  type: 'source-url'
  sourceId?: string
  url: string
  title?: string
  snippet?: string
}

/**
 * Source document citation
 */
export interface SourceDocumentPart {
  type: 'source-document'
  sourceId?: string
  documentId?: string
  documentName?: string
  content: string
  metadata?: {
    page?: number
    [key: string]: unknown
  }
}

/**
 * File/Document part - for uploaded documents
 */
export interface FilePart {
  type: 'file'
  filename: string
  url?: string
  mimeType?: string
  size?: number
}

/**
 * Image part - for vision/image messages
 */
export interface ImagePart {
  type: 'image'
  url: string
  alt?: string
}

/**
 * Step start marker (for multi-step reasoning)
 */
export interface StepStartPart {
  type: 'step-start'
  stepIndex?: number
}

/**
 * Task step part - for showing progress like RAG retrieval
 */
export interface TaskPart {
  type: 'task'
  taskType: 'rag' | 'thinking' | 'generating'
  state: 'pending' | 'running' | 'completed' | 'error'
  /** Additional info, e.g., number of sources found */
  info?: string | number
}

/**
 * User input request part - for interactive option selection
 */
export interface UserInputRequestPart {
  type: 'user-input-request'
  question: string
  options: string[]
  state?: 'pending' | 'answered'
  selectedOption?: string
}

/**
 * Output truncated warning part
 */
export interface TruncatedPart {
  type: 'truncated'
}

/**
 * All possible message parts
 */
export type MessagePart =
  | TextPart
  | ReasoningPart
  | ToolCallPart
  | ToolResultPart
  | McpToolCallPart
  | McpToolResultPart
  | SourceUrlPart
  | SourceDocumentPart
  | FilePart
  | ImagePart
  | StepStartPart
  | TaskPart
  | UserInputRequestPart
  | TruncatedPart

/**
 * Chat message
 */
export interface ChatMessage {
  id: string
  role: MessageRole
  parts: MessagePart[]
  createdAt?: Date
  /** Additional metadata */
  metadata?: Record<string, unknown>
  /** Current version number (1-based, from backend) */
  versionNumber?: number
  /** Total version count (from backend) */
  versionCount?: number
}

/**
 * Chat status
 */
export type ChatStatus = 'idle' | 'loading' | 'streaming' | 'error'

/**
 * Chat error
 */
export interface ChatError {
  code?: number
  message: string
  msgKey?: string  // i18n key for the error message
  quotaType?: string
}

/**
 * Suggested question/action
 */
export interface Suggestion {
  id: string
  text: string
  icon?: string
}

/**
 * Type guards
 */
export function isTextPart(part: MessagePart): part is TextPart {
  return part.type === 'text'
}

export function isReasoningPart(part: MessagePart): part is ReasoningPart {
  return part.type === 'reasoning'
}

export function isToolCallPart(part: MessagePart): part is ToolCallPart {
  return part.type === 'tool-call'
}

export function isToolResultPart(part: MessagePart): part is ToolResultPart {
  return part.type === 'tool-result'
}

export function isMcpToolCallPart(part: MessagePart): part is McpToolCallPart {
  return part.type === 'mcp-tool-call'
}

export function isMcpToolResultPart(part: MessagePart): part is McpToolResultPart {
  return part.type === 'mcp-tool-result'
}

export function isSourceUrlPart(part: MessagePart): part is SourceUrlPart {
  return part.type === 'source-url'
}

export function isSourceDocumentPart(part: MessagePart): part is SourceDocumentPart {
  return part.type === 'source-document'
}

export function isFilePart(part: MessagePart): part is FilePart {
  return part.type === 'file'
}

export function isImagePart(part: MessagePart): part is ImagePart {
  return part.type === 'image'
}

export function isStepStartPart(part: MessagePart): part is StepStartPart {
  return part.type === 'step-start'
}

export function isTaskPart(part: MessagePart): part is TaskPart {
  return part.type === 'task'
}

export function isUserInputRequestPart(part: MessagePart): part is UserInputRequestPart {
  return part.type === 'user-input-request'
}

export function isTruncatedPart(part: MessagePart): part is TruncatedPart {
  return part.type === 'truncated'
}

export function isSourcePart(part: MessagePart): part is SourceUrlPart | SourceDocumentPart {
  return part.type === 'source-url' || part.type === 'source-document'
}

export function isToolPart(part: MessagePart): part is ToolCallPart | ToolResultPart {
  return part.type === 'tool-call' || part.type === 'tool-result'
}

export function isMcpPart(part: MessagePart): part is McpToolCallPart | McpToolResultPart {
  return part.type === 'mcp-tool-call' || part.type === 'mcp-tool-result'
}

/**
 * Unified execution types for Agent and Workflow runs
 */

export type NodeStatus = 'pending' | 'running' | 'completed' | 'error' | 'skipped'

/**
 * Unified execution node representation
 * Used to visualize both Agent steps (RAG, reasoning, tool calls) and Workflow nodes
 */
export interface ExecutionNode {
  id: string
  type: string  // 'rag' | 'reasoning' | 'tool' | 'llm' | 'condition' | etc.
  label: string
  status: NodeStatus
  startTime?: Date
  endTime?: Date
  duration?: number
  input?: unknown
  output?: unknown
  error?: string
  metadata?: Record<string, unknown>
}

/**
 * Unified execution state
 */
export interface ExecutionState {
  nodes: Map<string, ExecutionNode>
  currentNodeId?: string
  progress: { current: number; total: number }
}

/**
 * Unified event types from SSE streams
 */
export type UnifiedEvent =
  | { type: 'node_start'; node: ExecutionNode }
  | { type: 'node_complete'; nodeId: string; output: unknown; duration: number }
  | { type: 'node_error'; nodeId: string; error: string }
  | { type: 'token'; nodeId: string; token: string }
  | { type: 'message'; message: ChatMessage }
  | { type: 'complete'; outputs: unknown }

/**
 * Adapter interface for unified run execution
 */
export interface RunAdapter {
  start(inputs: Record<string, unknown>): Promise<void>
  stop(): void
  streamEvents(): AsyncGenerator<UnifiedEvent>
  transformEvent(event: unknown): ChatMessage | ExecutionNode | null
}

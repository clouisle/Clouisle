import type { MessagePart } from './types'
import { isToolCallPart, isMcpToolCallPart, isTaskPart } from './types'

export type ToolActionCategory =
  | 'reading_file'
  | 'editing_file'
  | 'browsing_dir'
  | 'running_code'
  | 'executing_command'
  | 'calculating'
  | 'searching_web'
  | 'searching_kb'
  | 'generating_media'
  | 'collecting_artifacts'
  | 'querying_custom'
  | 'sending_custom'
  | 'creating_custom'
  | 'requesting_custom'
  | 'calling_custom'

export interface ActiveToolAction {
  category: ToolActionCategory
  toolName: string
  displayName: string
}

/** Format identifiers like 'get_user_profile' or 'fetchData' to 'Get User Profile' or 'Fetch Data' */
export function cleanToolDisplayName(rawName: string, displayName?: string): string {
  if (displayName && displayName.trim().length > 0 && displayName.trim() !== rawName) {
    return displayName.trim()
  }

  const trimmed = rawName.trim()
  // If it already contains spaces or non-ASCII (e.g. Chinese), keep it as-is
  if (/\s|[\u4e00-\u9fa5]/.test(trimmed)) {
    return trimmed
  }

  // Convert snake_case, kebab-case, or camelCase to capitalized words
  return trimmed
    .replace(/[-_]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .split(' ')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

const FILE_READ_PATTERNS = /(read|cat|view|get_file|open_file|load_file|parse_file|file_parser)/i
const FILE_EDIT_PATTERNS = /(write|edit|patch|save|create_file|update_file|append_file|touch)/i
const DIR_PATTERNS = /(browse_dir|list_dir|list_files|find_files|\bdir\b|\bls\b|\btree\b)/i
const CODE_PATTERNS = /(eval|python|script|execute_code|run_code|code_runner|sandbox_run)/i
const BASH_PATTERNS = /(bash|terminal|command|cmd|shell|exec)/i
const CALC_PATTERNS = /(calc|math|count|\bstat\b|stats|compute|analyze|分析|计算|统计)/i
const WEB_PATTERNS = /(web_search|search_web|fetch_webpage|fetch_url|scrape|curl|\bbrowse\b)/i
const KB_PATTERNS = /(knowledge|kb|rag|vector|retrieve|search_docs|doc_search)/i
const MEDIA_PATTERNS = /(image|generate_image|video|generate_video|draw|paint|speech|audio|绘图|生成图片|生成视频)/i

// Custom tool semantic verbs
const STATUS_PATTERNS = /status/i
const QUERY_PATTERNS = /(get|fetch|query|search|find|lookup|check|查|获取|搜索|查找)/i
const SEND_PATTERNS = /(send|post|push|notify|mail|email|webhook|发|推送|通知)/i
const CREATE_PATTERNS = /(create|add|insert|new|build|make|建|新增|创建)/i
const REQUEST_PATTERNS = /(api|http|rest|url|endpoint|request|请求|接口)/i

export function categorizeTool(name: string, input?: Record<string, unknown>, displayName?: string): ToolActionCategory {
  const lowerName = name.toLowerCase().trim()
  const combined = `${name} ${displayName || ''}`.toLowerCase().trim()

  // 1. Artifacts collection (e.g. sandbox artifact tool / "生成下载链接")
  if (
    lowerName === 'artifact' ||
    lowerName === 'artifacts' ||
    combined.includes('生成下载链接') ||
    combined.includes('create download link') ||
    combined.includes('artifact')
  ) {
    return 'collecting_artifacts'
  }

  // 2. Asset tools keep document actions grouped with file reading/browsing.
  if (
    lowerName === 'read_asset' ||
    lowerName === 'view_asset' ||
    lowerName === 'inspect_asset' ||
    lowerName === 'search_asset'
  ) {
    return 'reading_file'
  }
  if (lowerName === 'list_assets') return 'browsing_dir'
  if (lowerName === 'materialize_asset') return 'editing_file'

  // 3. Builtin / system capabilities (exact matches or system tool conventions)
  if (MEDIA_PATTERNS.test(combined)) return 'generating_media'
  if (KB_PATTERNS.test(combined)) return 'searching_kb'
  if (DIR_PATTERNS.test(combined)) return 'browsing_dir'
  if (WEB_PATTERNS.test(combined)) return 'searching_web'
  if (CODE_PATTERNS.test(combined)) return 'running_code'
  if (BASH_PATTERNS.test(combined)) return 'executing_command'
  if (FILE_READ_PATTERNS.test(combined)) return 'reading_file'
  if (FILE_EDIT_PATTERNS.test(combined)) return 'editing_file'
  if (CALC_PATTERNS.test(combined)) return 'calculating'

  // 4. Custom tool parameter characteristics
  if (input && typeof input === 'object') {
    if ('url' in input || 'endpoint' in input) return 'requesting_custom'
    if ('sql' in input || 'table' in input) return 'querying_custom'
    if ('email' in input || 'message' in input) return 'sending_custom'
  }

  // 5. Custom tool verb prefix detection
  if (STATUS_PATTERNS.test(combined) || QUERY_PATTERNS.test(combined)) return 'querying_custom'
  if (SEND_PATTERNS.test(combined)) return 'sending_custom'
  if (CREATE_PATTERNS.test(combined)) return 'creating_custom'
  if (REQUEST_PATTERNS.test(combined)) return 'requesting_custom'

  return 'calling_custom'
}

export function getActiveToolActions(parts: MessagePart[]): ActiveToolAction[] {
  const actions: ActiveToolAction[] = []

  for (const part of parts) {
    if (isToolCallPart(part) || isMcpToolCallPart(part)) {
      if (part.state === 'running' || part.state === 'pending') {
        // Exclude ask_user because it is a human-in-the-loop interaction handled separately
        if (part.toolName.toLowerCase() === 'ask_user') continue

        const rawName = isToolCallPart(part)
          ? part.toolName
          : `${part.serverName}/${part.toolName}`
        const rawDisplayName = isToolCallPart(part)
          ? (part.toolDisplayName || part.toolName)
          : `${part.serverName}/${part.toolName}`
        const cleanedName = cleanToolDisplayName(rawName, rawDisplayName)
        const category = categorizeTool(part.toolName, part.input, rawDisplayName)

        actions.push({
          category,
          toolName: rawName,
          displayName: cleanedName,
        })
      }
    } else if (isTaskPart(part) && part.state === 'running') {
      if (part.taskType === 'rag') {
        actions.push({
          category: 'searching_kb',
          toolName: 'knowledge_base',
          displayName: 'Knowledge Base',
        })
      }
    }
  }

  return actions
}

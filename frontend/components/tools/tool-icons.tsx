import type { ComponentType, SVGProps } from 'react'
import {
  Code2,
  Globe,
  Clock3,
  Calculator,
  Search,
  FolderOpen,
  ChartColumn,
  Wrench,
  Link,
} from 'lucide-react'

export interface ToolIconProps extends SVGProps<SVGSVGElement> {
  size?: number | string
}

/**
 * PostgreSQL elephant mark (clean monochrome/currentColor SVG).
 */
export function PostgresIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Head & Ear outline */}
      <path d="M17 18.5c2.5-1.5 4-4.5 4-7.5C21 6.5 17 3 12 3S3 6.5 3 11c0 3 1.5 6 4 7.5" />
      {/* Trunk curving down and back up */}
      <path d="M12 7c-1 2-2 5.5-2 9 0 2.5 1 4.5 2.5 4.5s2.5-2 2.5-4.5c0-1.5-.5-3.5-1-5" />
      {/* Eyes & Brow */}
      <circle cx="8" cy="9" r="1" fill="currentColor" />
      <circle cx="16" cy="9" r="1" fill="currentColor" />
      {/* Tusk hints */}
      <path d="M9 16c-.8 1.2-1.8 2-3 2" />
      <path d="M15 16c.8 1.2 1.8 2 3 2" />
    </svg>
  )
}

/**
 * MySQL Dolphin mark.
 */
export function MysqlIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Arched dolphin body */}
      <path d="M3 13.5C4.5 9 8 5 13.5 4.5c4.5-.5 7.5 2 7.5 6 0 3-2 5.5-5 6.5-3 1-6 2-8.5 4" />
      {/* Beak / snout */}
      <path d="M21 10.5c1 .5 2 .5 2-.5-1-1-2.5-1-4-1" />
      {/* Dorsal fin */}
      <path d="M12 4.5c1-2 3-2.5 4-2-.5 1.5-1 2.5-1.5 3" />
      {/* Pectoral fin */}
      <path d="M11 12c-1.5 1.5-3 2-4.5 1.5.5-1 1.5-2 2.5-2.5" />
      {/* Fluke / tail */}
      <path d="M5.5 20c-1-1.5-2.5-1.5-3.5-1 .5 2 2 3 3.5 3" />
    </svg>
  )
}

/**
 * Redis isometric diamond block with layered segments.
 */
export function RedisIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Top rhombus */}
      <path d="M12 2.5l8 4.2-8 4.2-8-4.2 8-4.2z" />
      {/* Middle layer */}
      <path d="M4 11.2l8 4.2 8-4.2" />
      {/* Bottom layer */}
      <path d="M4 15.5l8 4.2 8-4.2" />
      {/* Center axis */}
      <path d="M12 11v8.5" />
    </svg>
  )
}

/**
 * MongoDB leaf / droplet icon.
 */
export function MongoIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Outer leaf contour */}
      <path d="M12 2C8.5 6 5 10.5 5 15a7 7 0 0014 0c0-4.5-3.5-9-7-13z" />
      {/* Central leaf vein */}
      <path d="M12 5.5v15" />
      {/* Small root cusp */}
      <path d="M12 20.5c-.5 1-1 1.5-1.5 2" />
    </svg>
  )
}

/**
 * HTTP / Web API tool mark.
 */
export function HttpToolIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Two interlinked chain links representing HTTP connectivity */}
      <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
    </svg>
  )
}

/**
 * Code Sandbox / Custom Code tool mark.
 */
export function CodeToolIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
      <line x1="14" y1="4" x2="10" y2="20" />
    </svg>
  )
}

/**
 * MCP Protocol tool mark.
 */
export function McpToolIcon({ size = 16, className, ...props }: ToolIconProps) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      {...props}
    >
      {/* Hexagonal protocol node with connect pins */}
      <path d="M12 2l7 4v8l-7 4-7-4V6z" />
      <circle cx="12" cy="10" r="2.5" />
      <path d="M12 12.5V18" />
      <path d="M9.8 8.8L6.5 7" />
      <path d="M14.2 8.8l3.3-1.8" />
    </svg>
  )
}

export const TOOL_MARKS: Record<string, ComponentType<ToolIconProps>> = {
  // Builtin database tools by name or icon identifier
  postgresql_query: PostgresIcon,
  postgresql: PostgresIcon,
  mysql_query: MysqlIcon,
  mysql: MysqlIcon,
  redis_query: RedisIcon,
  redis: RedisIcon,
  mongodb_query: MongoIcon,
  mongodb: MongoIcon,
  // Custom tool types
  http: HttpToolIcon,
  code: CodeToolIcon,
  mcp: McpToolIcon,
}

export interface ResolveToolIconOptions {
  name?: string | null
  icon?: string | null
  type?: string | null
  custom_type?: string | null
  category?: string | null
  size?: number | string
  className?: string
}
/**
 * Resolves an appropriate SVG mark for a tool:
 * 1. Specific tool name match (e.g. `postgresql_query`, `mysql_query`, `redis_query`, `mongodb_query`)
 * 2. Custom tool type (`http`, `code`)
 * 3. Tool protocol (`mcp`)
 * 4. Fallback to category icon
 */
export function renderToolIcon({
  name,
  icon,
  type,
  custom_type,
  category,
  size = 16,
  className,
}: ResolveToolIconOptions): React.ReactNode {
  // 1. Icon key match (e.g. 'postgresql', 'mysql', 'redis', 'mongodb', 'http', 'code', 'mcp')
  if (icon && TOOL_MARKS[icon]) {
    const Mark = TOOL_MARKS[icon]
    return <Mark size={size} className={className} />
  }

  // 2. Tool name match (e.g. database query builtins)
  if (name && TOOL_MARKS[name]) {
    const Mark = TOOL_MARKS[name]
    return <Mark size={size} className={className} />
  }

  // 3. Custom tool type (http, code)
  if (type === 'custom' && custom_type && TOOL_MARKS[custom_type]) {
    const Mark = TOOL_MARKS[custom_type]
    return <Mark size={size} className={className} />
  }

  // 4. MCP protocol tools
  if (type === 'mcp') {
    return <McpToolIcon size={size} className={className} />
  }
  switch (category) {
    case 'time':
      return <Clock3 className={className} style={{ width: size, height: size }} />
    case 'math':
      return <Calculator className={className} style={{ width: size, height: size }} />
    case 'search':
      return <Search className={className} style={{ width: size, height: size }} />
    case 'web':
      return <Globe className={className} style={{ width: size, height: size }} />
    case 'file':
      return <FolderOpen className={className} style={{ width: size, height: size }} />
    case 'code':
    case 'sandbox':
      return <Code2 className={className} style={{ width: size, height: size }} />
    case 'api':
      return <Link className={className} style={{ width: size, height: size }} />
    case 'data':
      return <ChartColumn className={className} style={{ width: size, height: size }} />
    default:
      return <Wrench className={className} style={{ width: size, height: size }} />
  }
}

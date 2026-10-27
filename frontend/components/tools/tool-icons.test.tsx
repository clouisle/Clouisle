import { describe, expect, test } from 'bun:test'
import { renderToolIcon, TOOL_MARKS, PostgresIcon, MysqlIcon, RedisIcon, MongoIcon, HttpToolIcon, CodeToolIcon, McpToolIcon } from './tool-icons'

describe('tool-icons', () => {
  test('exports components for all supported database engines and custom types', () => {
    expect(TOOL_MARKS.postgresql_query).toBe(PostgresIcon)
    expect(TOOL_MARKS.postgresql).toBe(PostgresIcon)
    expect(TOOL_MARKS.mysql_query).toBe(MysqlIcon)
    expect(TOOL_MARKS.mysql).toBe(MysqlIcon)
    expect(TOOL_MARKS.redis_query).toBe(RedisIcon)
    expect(TOOL_MARKS.redis).toBe(RedisIcon)
    expect(TOOL_MARKS.mongodb_query).toBe(MongoIcon)
    expect(TOOL_MARKS.mongodb).toBe(MongoIcon)
    expect(TOOL_MARKS.http).toBe(HttpToolIcon)
    expect(TOOL_MARKS.code).toBe(CodeToolIcon)
    expect(TOOL_MARKS.mcp).toBe(McpToolIcon)
  })

  test('renderToolIcon matches database engine builtins by tool name', () => {
    const pg = renderToolIcon({ name: 'postgresql_query' }) as { type: unknown }
    expect(pg.type).toBe(PostgresIcon)

    const mysql = renderToolIcon({ name: 'mysql_query' }) as { type: unknown }
    expect(mysql.type).toBe(MysqlIcon)

    const redis = renderToolIcon({ name: 'redis_query' }) as { type: unknown }
    expect(redis.type).toBe(RedisIcon)

    const mongo = renderToolIcon({ name: 'mongodb_query' }) as { type: unknown }
    expect(mongo.type).toBe(MongoIcon)
  })

  test('renderToolIcon matches by icon identifier', () => {
    const pg = renderToolIcon({ icon: 'postgresql' }) as { type: unknown }
    expect(pg.type).toBe(PostgresIcon)

    const redis = renderToolIcon({ icon: 'redis' }) as { type: unknown }
    expect(redis.type).toBe(RedisIcon)
  })

  test('renderToolIcon matches custom types (http, code, mcp)', () => {
    const http = renderToolIcon({ type: 'custom', custom_type: 'http' }) as { type: unknown }
    expect(http.type).toBe(HttpToolIcon)

    const code = renderToolIcon({ type: 'custom', custom_type: 'code' }) as { type: unknown }
    expect(code.type).toBe(CodeToolIcon)

    const mcp = renderToolIcon({ type: 'mcp' }) as { type: unknown }
    expect(mcp.type).toBe(McpToolIcon)
  })

  test('renderToolIcon falls back to category icons', () => {
    const time = renderToolIcon({ category: 'time' })
    expect(time).toBeDefined()

    const search = renderToolIcon({ category: 'search' })
    expect(search).toBeDefined()

    const unknown = renderToolIcon({ category: 'nonexistent' })
    expect(unknown).toBeDefined()
  })
})

import { describe, expect, it } from 'bun:test'
import type { Document } from '@/lib/api/knowledge-bases'
import { isFeishuManaged } from './feishu-document-source'

describe('Feishu source ownership', () => {
  it('locks documents by source identity or explicit read-only metadata', () => {
    expect(isFeishuManaged(null)).toBe(false)
    expect(isFeishuManaged({ metadata: null } as Document)).toBe(false)
    expect(isFeishuManaged({ metadata: { feishu_source_id: 'source' } } as Document)).toBe(true)
    expect(isFeishuManaged({ metadata: { feishu_read_only: true } } as Document)).toBe(true)
    expect(isFeishuManaged({ metadata: { feishu_read_only: false } } as Document)).toBe(false)
  })
})

import { describe, expect, it } from 'bun:test'
import {
  extractToolCitationSources,
  getImageAssetUrl,
  getVideoAssetUrl,
  inferToolResultIsError,
  isMediaImageToolResult,
  isMediaVideoToolResult,
  parseToolResultOutput,
  shouldDisplayMediaResultInBody,
} from './tool-result'

describe('parseToolResultOutput', () => {
  it('parses valid JSON while preserving non-string values', () => {
    const object = { value: 1 }

    expect(parseToolResultOutput('{"value":1}')).toEqual(object)
    expect(parseToolResultOutput(object)).toBe(object)
    expect(parseToolResultOutput(null)).toBeNull()
  })

  it('preserves malformed and empty string output', () => {
    expect(parseToolResultOutput('')).toBe('')
    expect(parseToolResultOutput('{invalid')).toBe('{invalid')
  })
})

describe('extractToolCitationSources', () => {
  it('extracts structured sources from Agentic RAG and web search results', () => {
    expect(extractToolCitationSources('knowledge_search', {
      contexts: [{
        citation_id: 'rag_a1',
        document_id: 'doc-1',
        document_name: 'Guide',
        content: 'Policy text',
        kb_id: 'kb-1',
        score: 0.9,
      }],
    })).toEqual([expect.objectContaining({
      type: 'document',
      citationId: 'rag_a1',
      documentId: 'doc-1',
      title: 'Guide',
      content: 'Policy text',
    })])
    expect(extractToolCitationSources('web_search', JSON.stringify({
      results: [{
        citation_id: 'web_b2',
        title: 'News',
        url: 'https://example.test/news',
        content: 'Latest update',
      }],
    }))).toEqual([{
      type: 'url',
      citationId: 'web_b2',
      title: 'News',
      url: 'https://example.test/news',
      content: 'Latest update',
    }])
  })

  it('extracts sources from fetched webpages and attachment content tools', () => {
    expect(extractToolCitationSources('fetch_webpage', {
      citation_id: 'web_page_1',
      url: 'https://example.test/page',
      title: '  Page Title  ',
      content: 'Page body',
      success: true,
    })).toEqual([{
      type: 'url',
      citationId: 'web_page_1',
      title: 'Page Title',
      url: 'https://example.test/page',
      content: 'Page body',
    }])
    expect(extractToolCitationSources('fetch_webpage', {
      citation_id: 'web_page_2',
      url: 'https://example.test/page2',
      title: '   ',
      content: 'Page body 2',
      success: true,
    })).toEqual([{
      type: 'url',
      citationId: 'web_page_2',
      url: 'https://example.test/page2',
      content: 'Page body 2',
    }])
    expect(extractToolCitationSources('parse_asset', JSON.stringify({
      citation_id: 'asset_doc_1',
      ref: 'a1b2',
      filename: 'report.pdf',
      content: 'Parsed report',
      truncated: false,
    }))).toEqual([{
      type: 'document',
      citationId: 'asset_doc_1',
      documentId: 'a1b2',
      title: 'report.pdf',
      content: 'Parsed report',
      metadata: { ref: 'a1b2', truncated: false },
    }])
    expect(extractToolCitationSources('read_asset', {
      citation_id: 'asset_text_1',
      ref: 'c3d4',
      filename: 'notes.txt',
      content: 'Notes',
    })).toEqual([expect.objectContaining({
      type: 'document',
      citationId: 'asset_text_1',
      documentId: 'c3d4',
      title: 'notes.txt',
      content: 'Notes',
    })])
  })

  it('ignores unrelated, malformed, and uncited tool results', () => {
    expect(extractToolCitationSources('calculator', { results: [] })).toEqual([])
    expect(extractToolCitationSources('knowledge_search', { contexts: [{}] })).toEqual([])
    expect(extractToolCitationSources('web_search', '{invalid')).toEqual([])
  })
})

describe('inferToolResultIsError', () => {
  it('recognizes explicit failures from objects and JSON strings', () => {
    expect(inferToolResultIsError({ success: false })).toBe(true)
    expect(inferToolResultIsError('{"error":"failed"}')).toBe(true)
  })

  it('ignores empty errors and non-error boundary inputs', () => {
    expect(inferToolResultIsError({ error: '   ' })).toBe(false)
    expect(inferToolResultIsError({ error: 0 })).toBe(false)
    expect(inferToolResultIsError({ error: {} })).toBe(true)
    expect(inferToolResultIsError('')).toBe(false)
    expect(inferToolResultIsError('null')).toBe(false)
    expect(inferToolResultIsError([])).toBe(false)
  })
})

describe('media result guards and display', () => {
  const image = { kind: 'media.image', success: true, prompt: 'draw', images: [] }
  const video = { kind: 'media.video', success: true, prompt: 'animate', status: 'complete' }

  it('identifies valid image and video result shapes', () => {
    expect(isMediaImageToolResult(image)).toBe(true)
    expect(isMediaVideoToolResult(video)).toBe(true)
  })

  it('rejects malformed and empty media result shapes', () => {
    expect(isMediaImageToolResult(null)).toBe(false)
    expect(isMediaImageToolResult({ kind: 'media.image', images: {} })).toBe(false)
    expect(isMediaVideoToolResult('')).toBe(false)
    expect(isMediaVideoToolResult({ kind: 'media.video', status: null })).toBe(false)
  })

  it('displays successful recognized media results, including JSON strings', () => {
    expect(shouldDisplayMediaResultInBody(image)).toBe(true)
    expect(shouldDisplayMediaResultInBody(JSON.stringify(video))).toBe(true)
  })

  it('does not display unsuccessful or unrecognized results', () => {
    expect(shouldDisplayMediaResultInBody({ ...image, success: false })).toBe(false)
    expect(shouldDisplayMediaResultInBody({ kind: 'other', success: true })).toBe(false)
    expect(shouldDisplayMediaResultInBody('{invalid')).toBe(false)
  })
})

describe('media asset URLs', () => {
  it('prefers direct URLs and formats image base64 fallback', () => {
    expect(getImageAssetUrl({ url: 'https://example.com/image.png', base64: 'ignored' })).toBe('https://example.com/image.png')
    expect(getImageAssetUrl({ base64: 'abc', format: 'webp' })).toBe('data:image/webp;base64,abc')
    expect(getImageAssetUrl({ base64: 'abc' })).toBe('data:image/png;base64,abc')
  })

  it('formats video base64 fallback and handles empty assets', () => {
    expect(getVideoAssetUrl({ url: 'https://example.com/video.mp4', base64: 'ignored' })).toBe('https://example.com/video.mp4')
    expect(getVideoAssetUrl({ base64: 'abc', format: 'webm' })).toBe('data:video/webm;base64,abc')
    expect(getVideoAssetUrl({ base64: 'abc' })).toBe('data:video/mp4;base64,abc')
    expect(getImageAssetUrl()).toBeNull()
    expect(getImageAssetUrl({})).toBeNull()
    expect(getVideoAssetUrl(null)).toBeNull()
    expect(getVideoAssetUrl({})).toBeNull()
  })
})

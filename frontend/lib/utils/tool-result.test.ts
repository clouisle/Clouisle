import { describe, expect, it } from 'bun:test'
import {
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

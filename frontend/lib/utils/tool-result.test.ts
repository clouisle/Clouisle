import { describe, expect, test } from 'bun:test'
import {
  getImageAssetUrl,
  getVideoAssetUrl,
  inferToolResultIsError,
  parseToolResultOutput,
  shouldDisplayMediaResultInBody,
} from './tool-result'

describe('tool result helpers', () => {
  test('parses JSON strings and preserves other values', () => {
    const object = { id: 'result' }

    expect(parseToolResultOutput('{"id":"result"}')).toEqual(object)
    expect(parseToolResultOutput('{invalid')).toBe('{invalid')
    expect(parseToolResultOutput(object)).toBe(object)
  })

  test('infers explicit failed and error results', () => {
    expect(inferToolResultIsError('{"success":false}')).toBe(true)
    expect(inferToolResultIsError({ error: 'failed' })).toBe(true)
    expect(inferToolResultIsError({ error: { code: 'failed' } })).toBe(true)
    expect(inferToolResultIsError({ success: true, error: '  ' })).toBe(false)
    expect(inferToolResultIsError(null)).toBe(false)
  })

  test('recognizes successful media results only', () => {
    expect(
      shouldDisplayMediaResultInBody({
        kind: 'media.image',
        success: true,
        images: [],
      })
    ).toBe(true)
    expect(
      shouldDisplayMediaResultInBody('{"kind":"media.video","success":true,"status":"ready"}')
    ).toBe(true)
    expect(
      shouldDisplayMediaResultInBody({
        kind: 'media.image',
        success: false,
        images: [],
      })
    ).toBe(false)
    expect(shouldDisplayMediaResultInBody({ kind: 'media.image', success: true })).toBe(false)
  })

  test('returns image URLs or data URIs', () => {
    expect(getImageAssetUrl({ url: 'https://example.test/image.png', base64: 'ignored' })).toBe(
      'https://example.test/image.png'
    )
    expect(getImageAssetUrl({ base64: 'abc' })).toBe('data:image/png;base64,abc')
    expect(getImageAssetUrl({ base64: 'abc', format: 'webp' })).toBe('data:image/webp;base64,abc')
    expect(getImageAssetUrl({ file_path: '/tmp/image.png' })).toBeNull()
  })

  test('returns video URLs or data URIs', () => {
    expect(getVideoAssetUrl({ url: 'https://example.test/video.mp4', base64: 'ignored' })).toBe(
      'https://example.test/video.mp4'
    )
    expect(getVideoAssetUrl({ base64: 'abc' })).toBe('data:video/mp4;base64,abc')
    expect(getVideoAssetUrl({ base64: 'abc', format: 'webm' })).toBe('data:video/webm;base64,abc')
    expect(getVideoAssetUrl()).toBeNull()
  })
})

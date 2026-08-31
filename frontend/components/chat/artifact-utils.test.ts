import { describe, expect, test } from 'bun:test'
import type { ChatMessage } from './types'
import { getArtifactPreviewMode, getMessageArtifacts, getToolArtifacts } from './artifact-utils'

function assistant(id: string, parts: ChatMessage['parts']): ChatMessage {
  return { id, role: 'assistant', parts }
}

describe('artifact utilities', () => {
  test('classifies preview modes from MIME types and filenames', () => {
    expect(getArtifactPreviewMode({ filename: 'photo.PNG' })).toBe('image')
    expect(getArtifactPreviewMode({ filename: 'clip.bin', mimeType: 'video/mp4' })).toBe('video')
    expect(getArtifactPreviewMode({ filename: 'report.pdf' })).toBe('pdf')
    expect(getArtifactPreviewMode({ filename: 'page.bin', mimeType: 'text/html' })).toBe('html')
    expect(getArtifactPreviewMode({ filename: 'notes.md' })).toBe('markdown')
    expect(getArtifactPreviewMode({ filename: 'flow.mmd', mimeType: 'text/plain' })).toBe('mermaid')
    expect(getArtifactPreviewMode({ filename: 'data.bin', mimeType: 'application/octet-stream' })).toBe('unsupported')
  })

  test('parses artifact results, preserves paths, and rejects missing URLs', () => {
    expect(getToolArtifacts(JSON.stringify({
      artifacts: [
        { path: ' /workspace/report.csv ', filename: 'job-123_report.csv', url: ' /files/report.csv ', size: 12, contentType: 'text/csv' },
        { path: '/workspace/missing.txt' },
      ],
    }))).toEqual([
      {
        type: 'file',
        path: '/workspace/report.csv',
        filename: 'report.csv',
        url: '/files/report.csv',
        size: 12,
        mimeType: 'text/csv',
      },
    ])
  })

  test('collects only artifact tool results from one assistant message', () => {
    const firstMessage = assistant('assistant-1', [
      { type: 'tool-call', toolCallId: 'artifact-1', toolName: 'Artifact', input: {}, state: 'done' },
      {
        type: 'tool-result',
        toolCallId: 'artifact-1',
        toolName: 'Artifact',
        output: JSON.stringify({ artifacts: [{ path: '/workspace/report.csv', url: '/files/old.csv', size: 10 }] }),
      },
      {
        type: 'tool-result',
        toolCallId: 'search-1',
        toolName: 'search',
        output: { artifacts: [{ path: '/workspace/ignored.txt', url: '/files/ignored.txt' }] },
      },
    ])
    const secondMessage = assistant('assistant-2', [
      { type: 'tool-call', toolCallId: 'artifact-2', toolName: 'artifact', input: {}, state: 'done' },
      {
        type: 'tool-result',
        toolCallId: 'artifact-2',
        toolName: 'displayed artifact result',
        output: {
          artifacts: [
            { path: '/workspace/report.csv', url: '/files/new.csv', size: 20, content_type: 'text/csv' },
            { path: '/workspace/summary.md', url: '/files/summary.md', contentType: 'text/markdown' },
          ],
        },
      },
    ])

    expect(getMessageArtifacts(firstMessage)).toEqual([
      {
        type: 'file',
        path: '/workspace/report.csv',
        filename: 'report.csv',
        url: '/files/old.csv',
        size: 10,
        mimeType: undefined,
      },
    ])
    expect(getMessageArtifacts(secondMessage)).toEqual([
      {
        type: 'file',
        path: '/workspace/report.csv',
        filename: 'report.csv',
        url: '/files/new.csv',
        size: 20,
        mimeType: 'text/csv',
      },
      {
        type: 'file',
        path: '/workspace/summary.md',
        filename: 'summary.md',
        url: '/files/summary.md',
        mimeType: 'text/markdown',
      },
    ])
    expect(getMessageArtifacts({ id: 'user-1', role: 'user', parts: [{ type: 'text', text: 'make files' }] })).toEqual([])
  })
})

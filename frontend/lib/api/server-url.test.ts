import { describe, expect, it, mock } from 'bun:test'

mock.module('server-only', () => ({}))

const { getServerApiBaseUrl, getServerBackendOrigin } = await import('./server-url')

describe('server URL helpers', () => {
  it('keeps an absolute public API URL unchanged', () => {
    expect(getServerApiBaseUrl()).toBe('http://localhost:8000/api/v1')
  })

  it('removes the API path when deriving the backend origin', () => {
    expect(getServerBackendOrigin()).toBe('http://localhost:8000')
  })
})

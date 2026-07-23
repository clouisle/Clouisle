import { afterEach, describe, expect, test } from 'bun:test'
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'

import { API_BASE_URL } from '@/lib/constants'
import { api, ApiError, axiosInstance } from './client'

const originalAdapter = axiosInstance.defaults.adapter
const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
const originalDocument = Object.getOwnPropertyDescriptor(globalThis, 'document')
const originalLocalStorage = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')
const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')

function restoreGlobal(name: 'window' | 'document' | 'localStorage' | 'fetch', descriptor?: PropertyDescriptor): void {
  if (descriptor) Object.defineProperty(globalThis, name, descriptor)
  else Reflect.deleteProperty(globalThis, name)
}

function useBrowserState(token?: string, locale?: string): Map<string, string> {
  const storage = new Map<string, string>(token ? [['access_token', token]] : [])
  Object.defineProperties(globalThis, {
    window: { configurable: true, value: { location: { pathname: '/', search: '', href: '' } } },
    document: { configurable: true, value: { cookie: locale ? `locale=${locale}` : '' } },
    localStorage: {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        removeItem: (key: string) => storage.delete(key),
      },
    },
  })
  return storage
}

function successAdapter(configs: InternalAxiosRequestConfig[]): AxiosAdapter {
  return async (config) => {
    configs.push(config)
    return {
      config,
      data: config.responseType === 'blob' ? new Blob(['file']) : { code: 0, data: config.url, msg: '' },
      headers: {},
      status: 200,
      statusText: 'OK',
    }
  }
}

afterEach(() => {
  axiosInstance.defaults.adapter = originalAdapter
  restoreGlobal('window', originalWindow)
  restoreGlobal('document', originalDocument)
  restoreGlobal('localStorage', originalLocalStorage)
  restoreGlobal('fetch', originalFetch)
})

describe('ApiError', () => {
  test('normalizes field errors and joins messages', () => {
    const error = new ApiError(1001, 'Invalid fields', {
      errors: { email: 'Required', password: ['Too short', 'Needs a number'] },
    })

    expect(error.name).toBe('ApiError')
    expect(error.code).toBe(1001)
    expect(error.data).toEqual({ errors: { email: 'Required', password: ['Too short', 'Needs a number'] } })
    expect(error.isValidationError()).toBe(true)
    expect(error.getFieldErrorsRaw()).toEqual({ email: ['Required'], password: ['Too short', 'Needs a number'] })
    expect(error.getFieldErrors()).toEqual({ email: 'Required', password: 'Too short; Needs a number' })
  })

  test('returns no field errors for other error codes or missing data', () => {
    expect(new ApiError(400, 'Bad request', { errors: { email: 'Ignored' } }).getFieldErrors()).toEqual({})
    expect(new ApiError(1001, 'Invalid fields').getFieldErrorsRaw()).toEqual({})
  })
})

describe('API request behavior', () => {
  test('unwraps all HTTP method responses and preserves delete/form configuration', async () => {
    const configs: InternalAxiosRequestConfig[] = []
    axiosInstance.defaults.adapter = successAdapter(configs)
    const form = new FormData()
    form.set('username', 'alice')

    expect(await api.get('/get', { params: { page: 2 } })).toBe('/get')
    expect(await api.post('/post', { name: 'post' })).toBe('/post')
    expect(await api.put('/put', { name: 'put' })).toBe('/put')
    expect(await api.patch('/patch', { name: 'patch' })).toBe('/patch')
    expect(await api.delete('/delete', { id: 7 }, { params: { force: true } })).toBe('/delete')
    expect(await api.postForm('/form', form, { timeout: 1234 })).toBe('/form')

    expect(configs.map(({ method }) => method)).toEqual(['get', 'post', 'put', 'patch', 'delete', 'post'])
    expect(configs[0]?.params).toEqual({ page: 2 })
    expect(configs[4]?.params).toEqual({ force: true })
    expect(configs[4]?.data).toBe('{"id":7}')
    expect(configs[5]?.data).toBe(form)
    expect(configs[5]?.timeout).toBe(1234)
    expect(configs[5]?.headers.get('Content-Type')).toBe('application/x-www-form-urlencoded')
  })

  test('passes method, body, and headers through the fetch adapter', async () => {
    let request: Request | undefined
    Object.defineProperty(globalThis, 'fetch', {
      configurable: true,
      value: async (input: RequestInfo | URL) => {
        request = input as Request
        return new Response(JSON.stringify({ code: 0, data: 'saved', msg: '' }), {
          headers: { 'Content-Type': 'application/json' },
        })
      },
    })
    axiosInstance.defaults.adapter = 'fetch'

    expect(await api.post('/fetch-options', { enabled: true }, { headers: { 'X-Custom': 'yes' } })).toBe('saved')
    expect(request?.url).toBe(`${API_BASE_URL}/fetch-options`)
    expect(request?.method).toBe('POST')
    expect(request?.headers.get('X-Custom')).toBe('yes')
    expect(await request?.json()).toEqual({ enabled: true })
  })

  test('uses the configured base URL', () => {
    expect(api.getBaseUrl()).toBe(API_BASE_URL)
    expect(axiosInstance.defaults.baseURL).toBe(API_BASE_URL)
  })

  test('adds auth and language headers in browser state', async () => {
    useBrowserState('secret', 'zh')
    const configs: InternalAxiosRequestConfig[] = []
    axiosInstance.defaults.adapter = successAdapter(configs)

    expect(api.getAuthHeaders()).toEqual({ Authorization: 'Bearer secret', 'X-Language': 'zh' })
    await api.get('/headers')
    expect(configs[0]?.headers.get('Authorization')).toBe('Bearer secret')
    expect(configs[0]?.headers.get('X-Language')).toBe('zh')
  })

  test('omits browser headers without browser state or stored values', async () => {
    expect(api.getAuthHeaders()).toEqual({})

    useBrowserState()
    const configs: InternalAxiosRequestConfig[] = []
    axiosInstance.defaults.adapter = successAdapter(configs)
    expect(api.getAuthHeaders()).toEqual({})
    await api.get('/headers')
    expect(configs[0]?.headers.has('Authorization')).toBe(false)
    expect(configs[0]?.headers.has('X-Language')).toBe(false)
  })
})

describe('API response behavior', () => {
  test('leaves blob responses intact', async () => {
    axiosInstance.defaults.adapter = successAdapter([])
    const response = await axiosInstance.get('/export', { responseType: 'blob' })
    expect(response.data).toBeInstanceOf(Blob)
  })

  test('turns business validation responses into ApiError without losing fields', async () => {
    axiosInstance.defaults.adapter = async (config) => ({
      config,
      data: { code: 1001, data: { errors: { name: 'Required' } }, msg: 'validation.failed' },
      headers: {},
      status: 200,
      statusText: 'OK',
    })

    const error = await api.get('/invalid', { silent: true }).catch(value => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.code).toBe(1001)
    expect(error.message).toBe('Request failed')
    expect(error.getFieldErrors()).toEqual({ name: 'Required' })
  })

  test('uses safe localized backend messages and rejects technical details', async () => {
    useBrowserState(undefined, 'zh-CN')
    const messages: unknown[] = ['资料已更新', 'Public message', 'HTTP 500\nException stack']
    axiosInstance.defaults.adapter = async (config) => ({
      config,
      data: { code: 400, data: null, msg: messages.shift() },
      headers: {},
      status: 200,
      statusText: 'OK',
    })

    const localized = await api.get('/localized', { silent: true }).catch(value => value)
    const wrongLanguage = await api.get('/wrong-language', { silent: true }).catch(value => value)
    const technical = await api.get('/technical', { silent: true }).catch(value => value)

    expect(localized.message).toBe('资料已更新')
    expect(wrongLanguage.message).toBe('Request failed')
    expect(technical.message).toBe('Request failed')
  })

  test('maps timeout and plain HTTP failures to stable ApiError messages', async () => {
    axiosInstance.defaults.adapter = async (config) => {
      throw new AxiosError('timeout', 'ECONNABORTED', config)
    }
    const timeout = await api.get('/timeout', { silent: true }).catch(value => value)
    expect(timeout).toBeInstanceOf(ApiError)
    expect(timeout.code).toBe(-1)
    expect(timeout.message).toBe('Request timeout, please try again later')

    axiosInstance.defaults.adapter = async (config) => {
      throw new AxiosError('missing', 'ERR_BAD_REQUEST', config, undefined, {
        config,
        data: 'not an API envelope',
        headers: {},
        status: 404,
        statusText: 'Not Found',
      })
    }
    const missing = await api.get('/missing', { silent: true }).catch(value => value)
    expect(missing).toBeInstanceOf(ApiError)
    expect(missing.code).toBe(404)
    expect(missing.message).toBe('The requested resource could not be found')
  })

  test('honors skipAuthRedirect for auth business errors', async () => {
    const storage = useBrowserState('secret', 'en')
    axiosInstance.defaults.adapter = async (config) => ({
      config,
      data: { code: 401, data: null, msg: 'Unauthorized' },
      headers: {},
      status: 200,
      statusText: 'OK',
    })

    const error = await api.get('/login/access-token', { silent: true }).catch(value => value)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Session expired. Please login again.')
    expect(storage.get('access_token')).toBe('secret')
  })

  test('redirects auth failures back to the current page', async () => {
    const storage = useBrowserState('secret', 'en')
    window.location.pathname = '/projects'
    window.location.search = '?page=2'
    axiosInstance.defaults.adapter = async (config) => ({
      config,
      data: { code: 401, data: null, msg: 'Unauthorized' },
      headers: {},
      status: 200,
      statusText: 'OK',
    })

    await api.get('/private', { silent: true }).catch(() => undefined)
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(storage.has('access_token')).toBe(false)
    expect(window.location.href).toBe('/login?redirect=%2Fprojects%3Fpage%3D2')
  })

  test('propagates request interceptor failures', async () => {
    const interceptor = axiosInstance.interceptors.request.use(() => Promise.reject(new Error('blocked')))

    const error = await api.get('/blocked').catch(value => value)

    axiosInstance.interceptors.request.eject(interceptor)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.message).toBe('Network error, please check your connection')
  })
})

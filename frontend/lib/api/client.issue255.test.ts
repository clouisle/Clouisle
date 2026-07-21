import { afterEach, beforeAll, describe, expect, mock, test } from 'bun:test'
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'

const toastError = mock(() => {})
mock.module('sonner', () => ({ toast: { error: toastError } }))

const storage = new Map<string, string>()
let cookie = ''

beforeAll(() => {
  Object.defineProperty(globalThis, 'window', { value: { location: { pathname: '/', search: '', href: '' } } })
  Object.defineProperty(globalThis, 'localStorage', {
    value: {
      getItem: (key: string) => storage.get(key) ?? null,
      removeItem: (key: string) => storage.delete(key),
    },
  })
  Object.defineProperty(globalThis, 'document', {
    value: {},
  })
  Object.defineProperty(globalThis.document, 'cookie', {
    get: () => cookie,
    set: (value: string) => { cookie = value },
  })
})

const { ApiError, api, axiosInstance, getErrorMessage } = await import('./client')

function response(data: unknown): AxiosAdapter {
  return async (config): Promise<AxiosResponse> => ({
    data,
    status: 200,
    statusText: 'OK',
    headers: {},
    config,
  })
}

afterEach(() => {
  storage.clear()
  cookie = ''
  toastError.mockClear()
})

describe('API client', () => {
  test('normalizes validation fields and translates known messages', () => {
    const error = new ApiError(1001, 'invalid', {
      errors: { email: 'Fake email only', password: ['Too short', 'Needs a digit'] },
    })

    expect(error.name).toBe('ApiError')
    expect(error.isValidationError()).toBe(true)
    expect(error.getFieldErrorsRaw()).toEqual({
      email: ['Fake email only'],
      password: ['Too short', 'Needs a digit'],
    })
    expect(error.getFieldErrors()).toEqual({
      email: 'Fake email only',
      password: 'Too short; Needs a digit',
    })
    expect(new ApiError(500, 'no fields').getFieldErrorsRaw()).toEqual({})

    cookie = 'locale=zh'
    expect(getErrorMessage('network')).toBe('网络错误，请检查网络连接')
    expect(getErrorMessage('unknown.key')).toBe('unknown.key')
  })

  test('unwraps every request helper and applies auth and locale headers', async () => {
    storage.set('access_token', 'fake-access-token')
    cookie = 'theme=dark; locale=en'
    const seen: InternalAxiosRequestConfig[] = []
    const adapter: AxiosAdapter = async (config) => {
      seen.push(config)
      return response({ code: 0, data: config.method, msg: '' })(config)
    }

    expect(await api.get('/get', { adapter })).toBe('get')
    expect(await api.post('/post', { fake: true }, { adapter })).toBe('post')
    expect(await api.put('/put', { fake: true }, { adapter })).toBe('put')
    expect(await api.patch('/patch', { fake: true }, { adapter })).toBe('patch')
    expect(await api.delete('/delete', { fake: true }, { adapter })).toBe('delete')
    expect(await api.postForm('/form', new FormData(), { adapter })).toBe('post')

    expect(seen[0]?.headers.Authorization).toBe('Bearer fake-access-token')
    expect(seen[0]?.headers['X-Language']).toBe('en')
    expect(seen[4]?.data).toBe(JSON.stringify({ fake: true }))
    expect(seen[5]?.headers['Content-Type']).toBe('application/x-www-form-urlencoded')
    expect(api.getAuthHeaders()).toEqual({
      Authorization: 'Bearer fake-access-token',
      'X-Language': 'en',
    })
    expect(api.getBaseUrl()).toBeString()
  })

  test('preserves blobs and rejects localized business errors without network access', async () => {
    const blob = new Blob(['fake export'])
    const blobResponse = await axiosInstance.get('/download', {
      adapter: response(blob),
      responseType: 'blob',
    })
    expect(blobResponse.data).toBe(blob)

    await expect(api.get('/forbidden', {
      adapter: response({ code: 1004, data: { fake: true }, msg: 'Internal permission detail' }),
    })).rejects.toMatchObject({
      name: 'ApiError',
      code: 1004,
      message: 'You do not have permission to perform this action.',
      data: { fake: true },
    })
    expect(toastError).toHaveBeenCalledWith('You do not have permission to perform this action.')

    toastError.mockClear()
    await expect(api.get('/validation', {
      adapter: response({ code: 1001, data: { errors: {} }, msg: 'Failed to fetch fake details' }),
    })).rejects.toMatchObject({ code: 1001, message: 'Request failed' })
    expect(toastError).not.toHaveBeenCalled()
  })

  test('maps mocked timeout and HTTP failures to safe client errors', async () => {
    const timeout: AxiosAdapter = async (config) => {
      throw new AxiosError('fake timeout', 'ECONNABORTED', config)
    }
    await expect(api.get('/timeout', { adapter: timeout })).rejects.toMatchObject({
      code: -1,
      message: 'Request timeout, please try again later',
    })
    expect(toastError).toHaveBeenLastCalledWith('Request timeout, please try again later')

    const notFound: AxiosAdapter = async (config) => {
      throw new AxiosError('fake 404', 'ERR_BAD_REQUEST', config, undefined, {
        data: 'not-json',
        status: 404,
        statusText: 'Not Found',
        headers: {},
        config,
      })
    }
    await expect(api.get('/missing', { adapter: notFound, silent: true })).rejects.toMatchObject({
      code: 404,
      message: 'The requested resource could not be found',
    })
  })
})

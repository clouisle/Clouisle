import axios, { AxiosInstance, AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios'
import { toast } from 'sonner'
import { API_BASE_URL } from '@/lib/constants'

/** 获取当前语言 */
function getLocale(): string {
  if (typeof window === 'undefined') return 'en'
  const locale = document.cookie
    .split('; ')
    .find(row => row.startsWith('locale='))
    ?.split('=')[1]
  return locale || 'en'
}

/** 前端错误消息翻译 */
const errorMessages: Record<string, Record<string, string>> = {
  timeout: {
    en: 'Request timeout, please try again later',
    zh: '请求超时，请稍后重试',
  },
  network: {
    en: 'Network error, please check your connection',
    zh: '网络错误，请检查网络连接',
  },
  requestFailed: {
    en: 'Request failed',
    zh: '请求失败',
  },
  serverError: {
    en: 'Something went wrong. Please try again later.',
    zh: '出了点问题，请稍后重试。',
  },
  resourceNotFound: {
    en: 'The requested resource could not be found',
    zh: '请求的资源不存在或已被移除',
  },
  permissionDenied: {
    en: 'You do not have permission to perform this action.',
    zh: '当前没有该操作权限。',
  },
  sessionExpired: {
    en: 'Session expired. Please login again.',
    zh: '会话已过期，请重新登录。',
  },
}

/** 获取错误消息 */
export function getErrorMessage(key: string): string {
  const locale = getLocale()
  return errorMessages[key]?.[locale] || errorMessages[key]?.['en'] || key
}

function isLikelyMessageKey(message: string): boolean {
  return /^[a-z0-9]+(?:[._-][a-z0-9]+)+$/i.test(message.trim())
}

function isLikelyTechnicalMessage(message: string): boolean {
  const lowered = message.toLowerCase()
  return (
    message.includes('\n')
    || lowered.startsWith('http ')
    || lowered.includes('traceback')
    || lowered.includes('exception')
    || lowered.includes('stack')
    || lowered.includes('failed to fetch')
  )
}

function shouldUseBackendMessage(message: string): boolean {
  const trimmed = message.trim()
  if (!trimmed || trimmed.length > 200) return false
  if (isLikelyMessageKey(trimmed) || isLikelyTechnicalMessage(trimmed)) return false

  const locale = getLocale().toLowerCase()
  if (locale.startsWith('zh')) {
    return /[\u4e00-\u9fff]/.test(trimmed)
  }

  return true
}

function getStatusErrorMessage(status: number): string {
  if (isAuthErrorCode(status)) return getErrorMessage('sessionExpired')
  if (isPermissionErrorCode(status)) return getErrorMessage('permissionDenied')
  if (status === 404) return getErrorMessage('resourceNotFound')
  if (status >= 500 && status < 600) return getErrorMessage('serverError')
  return getErrorMessage('requestFailed')
}

function resolveApiErrorMessage(code: number, message: unknown): string {
  if (isAuthErrorCode(code)) return getErrorMessage('sessionExpired')
  if (isPermissionErrorCode(code)) return getErrorMessage('permissionDenied')
  if (code === 404 || (code >= 4000 && code < 5000)) return getErrorMessage('resourceNotFound')
  if (code >= 500 && code < 600) return getErrorMessage('serverError')

  if (typeof message === 'string' && shouldUseBackendMessage(message)) {
    return message.trim()
  }

  return getStatusErrorMessage(code)
}

function isAuthErrorCode(code: number): boolean {
  return code === 401 || code === 2000 || code === 2001 || code === 2002 || code === 2004
}

function isPermissionErrorCode(code: number): boolean {
  return code === 403 || code === 1004 || (code >= 3000 && code < 4000)
}

// 防止重复重定向
let isRedirecting = false

function redirectToLogin(): void {
  if (typeof window === 'undefined') return
  if (isRedirecting) return

  const current = `${window.location.pathname}${window.location.search}`
  if (current.startsWith('/login') || current.startsWith('/register')) return

  isRedirecting = true
  const target = encodeURIComponent(current)
  // 使用 setTimeout 确保在当前调用栈完成后执行重定向
  setTimeout(() => {
    window.location.href = `/login?redirect=${target}`
  }, 0)
}

function shouldSkipAuthRedirect(config?: InternalAxiosRequestConfig): boolean {
  if (!config) return false
  if (config.skipAuthRedirect) return true
  const url = config.url || ''
  return url.includes('/login/access-token')
}

export interface ApiResponse<T = unknown> {
  code: number
  data: T
  msg: string
}

/** 字段级验证错误数据 */
export interface ValidationErrorData {
  errors: Record<string, string | string[]>
}

export class ApiError extends Error {
  code: number
  data?: unknown

  constructor(code: number, message: string, data?: unknown) {
    super(message)
    this.code = code
    this.data = data
    this.name = 'ApiError'
  }

  /** 是否为字段级验证错误 (code: 1001) */
  isValidationError(): boolean {
    return this.code === 1001
  }

  /** 获取字段级错误映射（返回字符串数组格式） */
  getFieldErrorsRaw(): Record<string, string[]> {
    if (this.isValidationError() && this.data) {
      const validationData = this.data as ValidationErrorData
      const errors = validationData.errors || {}
      const result: Record<string, string[]> = {}
      for (const [field, value] of Object.entries(errors)) {
        result[field] = Array.isArray(value) ? value : [value]
      }
      return result
    }
    return {}
  }

  /** 获取字段级错误映射（返回字符串格式，多个错误用分号连接） */
  getFieldErrors(): Record<string, string> {
    const rawErrors = this.getFieldErrorsRaw()
    const result: Record<string, string> = {}
    for (const [field, errors] of Object.entries(rawErrors)) {
      result[field] = errors.join('; ')
    }
    return result
  }
}

/** 请求配置扩展 */
interface RequestConfig extends AxiosRequestConfig {
  /** 是否静默处理错误（不显示 toast） */
  silent?: boolean
  /** 是否跳过登录重定向（用于登录接口本身） */
  skipAuthRedirect?: boolean
}

// 扩展 AxiosRequestConfig
declare module 'axios' {
  interface InternalAxiosRequestConfig {
    silent?: boolean
    skipAuthRedirect?: boolean
  }
}

/** 创建 axios 实例 */
const axiosInstance: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 请求拦截器 */
axiosInstance.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    // 添加 token
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token')
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      
      // 添加语言头
      const locale = document.cookie
        .split('; ')
        .find(row => row.startsWith('locale='))
        ?.split('=')[1]
      if (locale) {
        config.headers['X-Language'] = locale
      }
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

/** 响应拦截器 */
axiosInstance.interceptors.response.use(
  (response) => {
    const config = response.config

    // 跳过 blob 响应（文件下载）
    if (config.responseType === 'blob') {
      return response
    }

    const data = response.data as ApiResponse

    // 业务错误
    if (data.code !== 0) {
      const resolvedMessage = resolveApiErrorMessage(data.code, data.msg)
      const error = new ApiError(data.code, resolvedMessage, data.data)
      if (isAuthErrorCode(error.code) && !shouldSkipAuthRedirect(config)) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token')
        }
        redirectToLogin()
        return Promise.reject(error)
      }

      // 非静默模式且非验证错误时显示 toast
      if (!config.silent && !error.isValidationError()) {
        toast.error(resolvedMessage)
      }

      return Promise.reject(error)
    }

    return response
  },
  (error: AxiosError<ApiResponse>) => {
    const config = error.config
    
    // 网络错误或超时
    if (!error.response) {
      const message = error.code === 'ECONNABORTED' 
        ? getErrorMessage('timeout')
        : getErrorMessage('network')
      
      if (!config?.silent) {
        toast.error(message)
      }
      
      return Promise.reject(new ApiError(-1, message))
    }
    
    // 服务器返回的错误
    const responseData = error.response.data
    if (responseData && typeof responseData === 'object' && 'code' in responseData) {
      const resolvedMessage = resolveApiErrorMessage(responseData.code, responseData.msg)
      const apiError = new ApiError(responseData.code, resolvedMessage, responseData.data)
      if (isAuthErrorCode(apiError.code) && !shouldSkipAuthRedirect(config)) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token')
        }
        redirectToLogin()
        return Promise.reject(apiError)
      }

      // 非静默模式且非验证错误时显示 toast
      if (!config?.silent && !apiError.isValidationError()) {
        toast.error(resolvedMessage)
      }

      return Promise.reject(apiError)
    }
    
    // 其他 HTTP 错误
    if (isAuthErrorCode(error.response.status) && !shouldSkipAuthRedirect(config)) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
      }
      redirectToLogin()
      return Promise.reject(new ApiError(error.response.status, getErrorMessage('sessionExpired')))
    }

    const message = getStatusErrorMessage(error.response.status)
    if (!config?.silent) {
      toast.error(message)
    }

    return Promise.reject(new ApiError(error.response.status, message))
  }
)

/** API 请求方法 */
export const api = {
  get: async <T>(url: string, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.get<ApiResponse<T>>(url, config)
    return response.data.data
  },
  
  post: async <T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.post<ApiResponse<T>>(url, data, config)
    return response.data.data
  },
  
  put: async <T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.put<ApiResponse<T>>(url, data, config)
    return response.data.data
  },
  
  patch: async <T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.patch<ApiResponse<T>>(url, data, config)
    return response.data.data
  },
  
  delete: async <T>(url: string, data?: unknown, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.delete<ApiResponse<T>>(url, { ...config, data })
    return response.data.data
  },
  
  /** OAuth2 表单登录 */
  postForm: async <T>(url: string, formData: FormData, config?: RequestConfig): Promise<T> => {
    const response = await axiosInstance.post<ApiResponse<T>>(url, formData, {
      ...config,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    })
    return response.data.data
  },

  /** Get base URL for SSE requests */
  getBaseUrl: (): string => {
    return API_BASE_URL
  },

  /** Get auth headers for SSE requests */
  getAuthHeaders: (): Record<string, string> => {
    const headers: Record<string, string> = {}
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('access_token')
      if (token) {
        headers['Authorization'] = `Bearer ${token}`
      }
      const locale = document.cookie
        .split('; ')
        .find(row => row.startsWith('locale='))
        ?.split('=')[1]
      if (locale) {
        headers['X-Language'] = locale
      }
    }
    return headers
  },
}

export { axiosInstance }

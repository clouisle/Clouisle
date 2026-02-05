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
}

/** 获取错误消息 */
function getErrorMessage(key: string): string {
  const locale = getLocale()
  return errorMessages[key]?.[locale] || errorMessages[key]?.['en'] || key
}

function isAuthErrorCode(code: number): boolean {
  if (code === 4001) return true
  if (code === 401 || code === 403) return true
  return code >= 2000 && code < 3000
}

function redirectToLogin(): void {
  if (typeof window === 'undefined') return
  const current = `${window.location.pathname}${window.location.search}`
  if (current.startsWith('/login') || current.startsWith('/register')) return
  const target = encodeURIComponent(current)
  window.location.replace(`/login?redirect=${target}`)
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
  errors: Record<string, string>
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
  
  /** 获取字段级错误映射 */
  getFieldErrors(): Record<string, string> {
    if (this.isValidationError() && this.data) {
      const validationData = this.data as ValidationErrorData
      return validationData.errors || {}
    }
    return {}
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
      const error = new ApiError(data.code, data.msg, data.data)
      if (isAuthErrorCode(error.code) && !shouldSkipAuthRedirect(config)) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token')
        }
        redirectToLogin()
        return Promise.reject(error)
      }

      // 非静默模式且非验证错误时显示 toast
      if (!config.silent && !error.isValidationError()) {
        toast.error(data.msg)
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
      const apiError = new ApiError(responseData.code, responseData.msg, responseData.data)
      if (isAuthErrorCode(apiError.code) && !shouldSkipAuthRedirect(config)) {
        if (typeof window !== 'undefined') {
          localStorage.removeItem('access_token')
        }
        redirectToLogin()
        return Promise.reject(apiError)
      }

      // 非静默模式且非验证错误时显示 toast
      if (!config?.silent && !apiError.isValidationError()) {
        toast.error(responseData.msg)
      }
      
      return Promise.reject(apiError)
    }
    
    // 其他 HTTP 错误
    if ((error.response.status === 401 || error.response.status === 403) && !shouldSkipAuthRedirect(config)) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('access_token')
      }
      redirectToLogin()
      return Promise.reject(new ApiError(error.response.status, 'Unauthorized'))
    }

    const message = `${getErrorMessage('requestFailed')}: ${error.response.status} ${error.response.statusText}`
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

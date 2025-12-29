import { api, axiosInstance } from './client'

export interface UploadResult {
  url: string
  filename: string
  original_name: string
  size: number
  content_type: string
}

export interface ParsedFileResult {
  filename: string
  content: string
  mime_type: string
  size: number
  truncated: boolean
  original_length?: number | null
  title?: string | null
}

export interface FileParseOptions {
  maxContentLength?: number
  truncateStrategy?: 'end' | 'start' | 'middle'
}

export interface UploadProgress {
  loaded: number
  total: number
  percent: number
}

export const uploadApi = {
  /**
   * 上传图片
   */
  uploadImage: async (file: File, category: string = 'general'): Promise<UploadResult> => {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axiosInstance.post<{ code: number; data: UploadResult; msg: string }>(
      `/upload/image?category=${encodeURIComponent(category)}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data.data
  },

  /**
   * 上传通用文件
   */
  uploadFile: async (file: File, category: string = 'general'): Promise<UploadResult> => {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axiosInstance.post<{ code: number; data: UploadResult; msg: string }>(
      `/upload/file?category=${encodeURIComponent(category)}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data.data
  },

  /**
   * 上传通用文件（带进度回调）
   */
  uploadFileWithProgress: async (
    file: File, 
    category: string = 'general',
    onProgress?: (progress: UploadProgress) => void
  ): Promise<UploadResult> => {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await axiosInstance.post<{ code: number; data: UploadResult; msg: string }>(
      `/upload/file?category=${encodeURIComponent(category)}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        onUploadProgress: (progressEvent) => {
          if (onProgress && progressEvent.total) {
            const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
            onProgress({
              loaded: progressEvent.loaded,
              total: progressEvent.total,
              percent,
            })
          }
        },
      }
    )
    return response.data.data
  },

  /**
   * 解析文件内容
   */
  parseFile: async (file: File, options?: FileParseOptions): Promise<ParsedFileResult> => {
    const formData = new FormData()
    formData.append('file', file)
    
    const params = new URLSearchParams()
    if (options?.maxContentLength) {
      params.append('max_content_length', options.maxContentLength.toString())
    }
    if (options?.truncateStrategy) {
      params.append('truncate_strategy', options.truncateStrategy)
    }
    
    const queryString = params.toString()
    const url = `/upload/parse${queryString ? `?${queryString}` : ''}`
    
    const response = await axiosInstance.post<{ code: number; data: ParsedFileResult; msg: string }>(
      url,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data.data
  },

  /**
   * 批量解析文件
   */
  parseFiles: async (files: File[], options?: FileParseOptions): Promise<ParsedFileResult[]> => {
    const formData = new FormData()
    files.forEach(file => {
      formData.append('files', file)
    })
    
    const params = new URLSearchParams()
    if (options?.maxContentLength) {
      params.append('max_content_length', options.maxContentLength.toString())
    }
    if (options?.truncateStrategy) {
      params.append('truncate_strategy', options.truncateStrategy)
    }
    
    const queryString = params.toString()
    const url = `/upload/parse/batch${queryString ? `?${queryString}` : ''}`
    
    const response = await axiosInstance.post<{ code: number; data: ParsedFileResult[]; msg: string }>(
      url,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data.data
  },

  /**
   * 删除文件
   */
  deleteFile: async (url: string): Promise<void> => {
    // 从 URL 中提取路径部分
    // 完整 URL 格式: http://localhost:8000/api/v1/upload/files/{category}/{year}/{month}/{filename}
    // 或相对路径: /api/v1/upload/files/{category}/{year}/{month}/{filename}
    let path = url
    
    // 处理完整 URL
    if (path.includes('/api/v1/upload/files/')) {
      path = path.substring(path.indexOf('/api/v1/upload/files/'))
    }
    
    // 移除前缀得到 files/{category}/{year}/{month}/{filename}
    path = path.replace('/api/v1/upload/', '')
    await api.delete<null>(`/upload/${path}`)
  },

  /**
   * 获取文件完整 URL
   */
  getFullUrl: (path: string): string => {
    if (!path) return ''
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return path
    }
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
    // 移除 /api/v1 后缀，因为路径已包含
    const apiBase = baseUrl.replace('/api/v1', '')
    return `${apiBase}${path}`
  },
}

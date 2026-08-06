/**
 * 应用常量配置
 * 用于存放版本信息、构建信息等全局常量
 */

// API 基础地址
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

// 应用版本
export const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || '0.0.0-dev'

// 构建日期
export const BUILD_DATE = process.env.NEXT_PUBLIC_BUILD_DATE || 'dev'

// 应用名称
export const APP_NAME = 'Clouisle'

export const KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES = [
  '.pdf',
  '.docx',
  '.doc',
  '.txt',
  '.md',
  '.markdown',
  '.html',
  '.htm',
  '.csv',
  '.xlsx',
  '.xls',
  '.json',
  '.pptx',
]

export const KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB = 50
export const KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB = 1
export const KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB = 1024
export const BYTES_PER_MB = 1024 * 1024
export const GENERAL_UPLOAD_MAX_FILE_SIZE_MB = 10
export const GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES = GENERAL_UPLOAD_MAX_FILE_SIZE_MB * BYTES_PER_MB
export const SKILL_ZIP_MAX_UPLOAD_SIZE_MB = 50
export const SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES = SKILL_ZIP_MAX_UPLOAD_SIZE_MB * BYTES_PER_MB

// GitHub 仓库地址
export const GITHUB_URL = 'https://github.com/yunhai-dev/Clouisle'

// 文档地址
export const DOCS_URL = 'https://github.com/yunhai-dev/Clouisle/blob/main/README.md'

// 更新日志地址
export const CHANGELOG_URL = 'https://github.com/yunhai-dev/Clouisle/blob/main/CHANGELOG.md'

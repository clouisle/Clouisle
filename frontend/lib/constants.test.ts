import { describe, expect, test } from 'bun:test'

import {
  API_BASE_URL,
  APP_NAME,
  APP_VERSION,
  BUILD_DATE,
  BYTES_PER_MB,
  GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES,
  GENERAL_UPLOAD_MAX_FILE_SIZE_MB,
  KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES,
  KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
  KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
  KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB,
  SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES,
  SKILL_ZIP_MAX_UPLOAD_SIZE_MB,
} from './constants'

describe('application constants', () => {
  test('provides local development defaults and application identity', () => {
    expect(API_BASE_URL).toBe('http://localhost:8000/api/v1')
    expect(APP_VERSION).toBe('0.0.0-dev')
    expect(BUILD_DATE).toBe('dev')
    expect(APP_NAME).toBe('Clouisle')
  })

  test('defines supported knowledge document formats and upload bounds', () => {
    expect(KNOWLEDGE_BASE_DOCUMENT_ACCEPTED_TYPES).toEqual(expect.arrayContaining([
      '.pdf',
      '.docx',
      '.txt',
      '.csv',
      '.xlsx',
      '.pptx',
    ]))
    expect(KNOWLEDGE_BASE_DOCUMENT_MIN_MAX_UPLOAD_SIZE_MB).toBeLessThanOrEqual(
      KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB,
    )
    expect(KNOWLEDGE_BASE_DOCUMENT_DEFAULT_MAX_UPLOAD_SIZE_MB).toBeLessThanOrEqual(
      KNOWLEDGE_BASE_DOCUMENT_MAX_MAX_UPLOAD_SIZE_MB,
    )
  })

  test('derives byte upload limits from megabyte limits', () => {
    expect(BYTES_PER_MB).toBe(1024 * 1024)
    expect(GENERAL_UPLOAD_MAX_FILE_SIZE_BYTES).toBe(
      GENERAL_UPLOAD_MAX_FILE_SIZE_MB * BYTES_PER_MB,
    )
    expect(SKILL_ZIP_MAX_UPLOAD_SIZE_BYTES).toBe(SKILL_ZIP_MAX_UPLOAD_SIZE_MB * BYTES_PER_MB)
  })
})
